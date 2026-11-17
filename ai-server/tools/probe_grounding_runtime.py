"""Real-model export/runtime compatibility probe; static one-image, one-prompt scope.

Run with isolated optional dependencies, after all GPU jobs. A successful probe
does not validate dynamic shapes, every class, the HTTP adapter or full 3D labels.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import sys
import time
import traceback


def save(root,name,value):
    with (root/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2,allow_nan=False)


def compare_arrays(reference,actual):
    import numpy as np
    result=[]
    for name in ('logits','pred_boxes'):
        left,right=reference[name],actual[name]
        shape=left.shape==right.shape
        finite=np.isfinite(left)&np.isfinite(right) if shape else np.zeros(0,dtype=bool)
        result.append({'name':name,'same_shape':shape,'reference_shape':list(left.shape),'actual_shape':list(right.shape),
            'max_finite_absolute_difference':float(np.max(np.abs(left[finite]-right[finite]))) if finite.any() else None,
            'infinity_signs_match':bool(np.array_equal(np.isposinf(left),np.isposinf(right)) and np.array_equal(np.isneginf(left),np.isneginf(right))),
            'has_nan':bool(np.isnan(left).any() or np.isnan(right).any()),
            'within_tolerance':bool(shape and np.allclose(left,right,rtol=1e-4,atol=1e-5,equal_nan=False))})
    return {'outputs':result,'passed':all(r['within_tolerance'] and not r['has_nan'] for r in result),'rtol':1e-4,'atol':1e-5,
            'scope':'raw logits/boxes for one fixed image and prompt only; padding negative infinities compared by sign'}


def register_boolean_or():
    import torch
    def boolean_ior(graph,left,right):
        if any(v.type().scalarType()!='Bool' for v in (left,right)):
            raise ValueError('Only boolean in-place OR is supported by this experimental symbolic')
        if left.type().sizes()!=right.type().sizes():
            raise ValueError('Boolean OR broadcast is outside this fixed-shape adapter')
        return graph.op('Or',left,right).setType(left.type())
    torch.onnx.register_custom_op_symbolic('aten::__ior_',boolean_ior,18)


def adapter_test(a):
    import torch
    import numpy as np
    import onnx
    import onnxruntime as ort
    a.output.mkdir(parents=True,exist_ok=False)
    register_boolean_or()
    class BooleanOr(torch.nn.Module):
        def forward(self,left,right):
            left |= right
            return left
    left=torch.tensor([False,False,True,True]);right=torch.tensor([False,True,False,True])
    torch.onnx.export(BooleanOr(),(left.clone(),right.clone()),str(a.output/'boolean-or.onnx'),
        input_names=['left','right'],output_names=['output'],opset_version=18,dynamo=False)
    onnx.checker.check_model(str(a.output/'boolean-or.onnx'))
    session=ort.InferenceSession(str(a.output/'boolean-or.onnx'),providers=['CPUExecutionProvider'])
    actual=session.run(None,{'left':left.numpy(),'right':right.numpy()})[0]
    passed=bool(np.array_equal(actual,np.logical_or(left.numpy(),right.numpy())))
    save(a.output,'adapter-test.json',{'all_four_boolean_combinations_match':passed,'scope':'small exporter truth-table guard, not model accuracy'})
    if not passed:raise ValueError('Boolean OR adapter truth-table failed')


def export_model(a):
    import numpy as np
    import torch
    from PIL import Image
    from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection
    from benchmark_grounding import select_images
    torch.set_num_threads(1);torch.manual_seed(42);torch.cuda.manual_seed_all(42)
    torch.backends.cuda.matmul.allow_tf32=False
    a.output.mkdir(parents=True,exist_ok=False)
    images=select_images(a.data_root,'v1.0-mini','scene-0061',1);image=a.data_root/images[0]['filename']
    model_id='IDEA-Research/grounding-dino-base'
    processor=AutoProcessor.from_pretrained(model_id,local_files_only=True)
    model=AutoModelForZeroShotObjectDetection.from_pretrained(model_id,local_files_only=True).eval().cuda()
    with Image.open(image) as frame:batch=processor(images=frame.convert('RGB'),text='car.',return_tensors='pt')
    names=list(batch.keys());inputs=tuple(batch[n].cuda() for n in names)
    class Wrapper(torch.nn.Module):
        def __init__(self,inner):super().__init__();self.inner=inner
        def forward(self,*values):
            output=self.inner(**dict(zip(names,values)),return_dict=True)
            return output.logits,output.pred_boxes
    wrapper=Wrapper(model)
    manifest={'at':datetime.now(timezone.utc).isoformat(),'scope':'static one image, prompt car.; no dynamic/general/full-scene claim',
        'model':model_id,'model_commit':getattr(model.config,'_commit_hash',None),'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
        'inputs':{n:{'shape':list(v.shape),'dtype':str(v.dtype)} for n,v in zip(names,inputs)},'input_names':names,
        'output_names':['logits','pred_boxes'],'exporter':a.exporter,'opset':18,'torch':torch.__version__,
        'transformers':importlib.metadata.version('transformers'),'cuda':torch.version.cuda,'cudnn':torch.backends.cudnn.version(),
        'gpu':torch.cuda.get_device_name(),'matmul_tf32':False,'cudnn_tf32':torch.backends.cudnn.allow_tf32,
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'production_environment_modified':False}
    save(a.output,'manifest.json',manifest)
    with torch.no_grad():
        result=wrapper(*inputs);torch.cuda.synchronize()
        np.savez(a.output/'reference.npz',**{n:v.detach().cpu().numpy() for n,v in zip(('logits','pred_boxes'),result)})
        np.savez(a.output/'inputs.npz',**{n:v.detach().cpu().numpy() for n,v in zip(names,inputs)})
        # Include host input copy and output readback in both runtime timing boundaries.
        host=[v.cpu() for v in inputs];times=[]
        for repeat in range(13):
            torch.cuda.synchronize();started=time.perf_counter()
            values=wrapper(*(v.cuda() for v in host))
            copied=[v.detach().cpu().numpy() for v in values];torch.cuda.synchronize()
            if repeat>=3:times.append(time.perf_counter()-started)
        save(a.output,'pytorch-timing.json',{'boundary':'host tensors -> CUDA forward -> host output arrays','repetitions':10,'warmups':3,
                'seconds':times,'median_seconds':statistics.median(times),'finite_boxes':bool(np.isfinite(copied[1]).all())})
        if a.exporter=='legacy_bool_or':
            register_boolean_or()
            save(a.output,'export-adapter.json',{'operator':'aten::__ior_','onnx_operator':'Or',
                 'guards':'both operands bool and identical static shape','scope':'export process only; production source and weights unchanged',
                 'reason':'original legacy exporter failed at boolean special-token mask OR'})
        started=time.perf_counter()
        torch.onnx.export(wrapper,inputs,str(a.output/'model.onnx'),input_names=names,output_names=['logits','pred_boxes'],
            opset_version=18,dynamo=a.exporter=='dynamo',external_data=True)
    import onnx
    onnx.checker.check_model(str(a.output/'model.onnx'))
    graph=onnx.load(str(a.output/'model.onnx'),load_external_data=False)
    save(a.output,'export-result.json',{'status':'exported_and_checked','export_seconds':time.perf_counter()-started,
        'operators':dict(Counter(node.op_type for node in graph.graph.node)),'nodes':len(graph.graph.node),
        'files':[{'name':p.name,'bytes':p.stat().st_size} for p in a.output.iterdir() if p.is_file()]})


def ort_probe(a):
    import numpy as np
    import torch  # Load this environment's CUDA/cuDNN libraries before ORT.
    import onnxruntime as ort
    torch.set_num_threads(1)
    root=a.output;manifest=json.loads((root/'manifest.json').read_text())
    inputs=dict(np.load(root/'inputs.npz'));reference=dict(np.load(root/'reference.npz'))
    providers=[('CUDAExecutionProvider',{'use_tf32':0,'gpu_mem_limit':4*1024**3}), 'CPUExecutionProvider']
    options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
    options.enable_profiling=True;options.profile_file_prefix=str(root/'ort-profile')
    start=time.perf_counter();session=ort.InferenceSession(str(root/'model.onnx'),sess_options=options,providers=providers)
    if 'CUDAExecutionProvider' not in session.get_providers():raise RuntimeError('CUDA provider unavailable; reject silent CPU-only execution')
    session.disable_fallback();available={i.name for i in session.get_inputs()};feed={k:v for k,v in inputs.items() if k in available}
    output=session.run(None,feed);profile=session.end_profiling();initialization=time.perf_counter()-start
    events=json.loads(Path(profile).read_text());placement=Counter(e.get('args',{}).get('provider') for e in events if e.get('cat')=='Node' and e.get('args',{}).get('provider'))
    quality=compare_arrays(reference,dict(zip(manifest['output_names'],output)))
    del session;gc.collect()
    options.enable_profiling=False;session=ort.InferenceSession(str(root/'model.onnx'),sess_options=options,providers=providers);session.disable_fallback()
    times=[]
    for repeat in range(13):
        started=time.perf_counter();session.run(None,feed)
        if repeat>=3:times.append(time.perf_counter()-started)
    save(root,'ort-result.json',{'status':'completed','version':ort.__version__,'providers':session.get_providers(),'profile_node_provider_counts':dict(placement),
        'diagnostic_initialization_seconds':initialization,'quality':quality,'timing_boundary':'host arrays -> ORT forward -> host arrays',
        'repetitions':10,'warmups':3,'seconds':times,'median_seconds':statistics.median(times),
        'decision':'static raw-model probe only; no production adoption or full pipeline claim'})


def trt_probe(a):
    import torch  # Preload the existing CUDA runtime libraries; do not install another torch.
    import tensorrt as trt
    root=a.output;logger=trt.Logger(trt.Logger.WARNING);builder=trt.Builder(logger)
    network=builder.create_network(0);parser=trt.OnnxParser(network,logger);started=time.perf_counter()
    parsed=parser.parse_from_file(str(root/'model.onnx'))
    errors=[str(parser.get_error(i)) for i in range(parser.num_errors)]
    save(root,'trt-parse.json',{'version':trt.__version__,'parsed':parsed,'errors':errors,'seconds':time.perf_counter()-started,
        'layers':network.num_layers,'inputs':network.num_inputs,'outputs':network.num_outputs,
        'scope':'real exported model parser compatibility; not engine execution or performance'})
    if not parsed:raise RuntimeError('TensorRT parser rejected this exported graph; errors preserved')
    config=builder.create_builder_config();config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE,2*1024**3)
    if hasattr(trt.BuilderFlag,'TF32'):config.clear_flag(trt.BuilderFlag.TF32)
    started=time.perf_counter();engine=builder.build_serialized_network(network,config)
    if engine is None:raise RuntimeError('TensorRT engine build failed')
    (root/'model.engine').write_bytes(bytes(engine))
    save(root,'trt-build.json',{'status':'built','seconds':time.perf_counter()-started,'engine_bytes':len(bytes(engine)),
        'scope':'static engine build; execution parity and end-to-end timing still required before deployment'})
    import numpy as np
    import torch
    manifest=json.loads((root/'manifest.json').read_text());inputs=dict(np.load(root/'inputs.npz'))
    runtime=trt.Runtime(logger);loaded=runtime.deserialize_cuda_engine(engine);context=loaded.create_execution_context()
    buffers={};outputs=[]
    for i in range(loaded.num_io_tensors):
        name=loaded.get_tensor_name(i);shape=tuple(context.get_tensor_shape(name))
        if any(v<0 for v in shape):raise ValueError('Dynamic TensorRT shape is outside this fixed-input probe')
        buffers[name]=torch.from_numpy(np.zeros(shape,dtype=trt.nptype(loaded.get_tensor_dtype(name)))).cuda()
        if loaded.get_tensor_mode(name)==trt.TensorIOMode.OUTPUT:outputs.append(name)
    if set(outputs)!=set(manifest['output_names']):raise ValueError('Unexpected engine outputs')
    times=[];actual=None
    for repeat in range(13):
        torch.cuda.synchronize();started=time.perf_counter()
        for name in buffers:
            if loaded.get_tensor_mode(name)==trt.TensorIOMode.INPUT:
                converted=inputs[name].astype(trt.nptype(loaded.get_tensor_dtype(name)),copy=False)
                if not np.array_equal(converted,inputs[name]):raise ValueError('Engine input conversion would change values')
                buffers[name]=torch.from_numpy(converted).cuda()
            context.set_tensor_address(name,buffers[name].data_ptr())
        if not context.execute_async_v3(torch.cuda.current_stream().cuda_stream):raise RuntimeError('TensorRT execution failed')
        actual={name:buffers[name].cpu().numpy() for name in outputs};torch.cuda.synchronize()
        if repeat>=3:times.append(time.perf_counter()-started)
    save(root,'trt-result.json',{'status':'completed','version':trt.__version__,
        'quality':compare_arrays(dict(np.load(root/'reference.npz')),actual),
        'boundary':'host arrays -> CUDA TensorRT forward -> host arrays','repetitions':10,'warmups':3,
        'seconds':times,'median_seconds':statistics.median(times),
        'decision':'one static prompt/image only; no full-class/dynamic/full-scene deployment gate'})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('export','ort','trt','adapter_test'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--data-root',type=Path)
    p.add_argument('--exporter',choices=('dynamo','legacy','legacy_bool_or'),default='dynamo');a=p.parse_args()
    if not a.output.resolve().is_relative_to(Path('/results/experiments')):raise ValueError('Use results experiment root')
    for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[name]='1'
    try:{'export':export_model,'ort':ort_probe,'trt':trt_probe,'adapter_test':adapter_test}[a.phase](a)
    except Exception as error:
        a.output.mkdir(parents=True,exist_ok=True)
        save(a.output,a.phase+'-failure.json',{'at':datetime.now(timezone.utc).isoformat(),'type':type(error).__name__,'message':str(error),
            'phase':a.phase,'status':'failed_not_deployed'})
        traceback.print_exc();raise SystemExit(1)


if __name__=='__main__':main()
