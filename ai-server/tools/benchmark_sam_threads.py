"""Time the installed SAM function with fixed detections and a bounded thread limit.

Production inference_mode is retained. Detection, masks, refinement and 3D
algorithms are unchanged; this measures SAM inference plus CPU mask processing.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--detections',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();threads=int(os.environ.get('VESPA_NUM_THREADS','1'))
    if threads not in (1,2,4):raise ValueError('Use bounded 1/2/4 thread conditions')
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]=str(threads)
    a.output.mkdir(parents=True,exist_ok=False)
    import cv2,numpy as np,torch,yaml
    np.__dict__.setdefault('bool',np.bool_)
    np.__dict__.setdefault('concat',np.concatenate)
    np.__dict__.setdefault('atan2',np.arctan2)
    np.__dict__.setdefault('int',int)
    torch.set_num_threads(threads);torch.manual_seed(42);torch.cuda.manual_seed_all(42)
    if not torch.cuda.is_available():raise RuntimeError('CUDA required')
    sys.path.insert(0,'/opt/vespa')
    from src.image import grounding_sam as sam
    from benchmark_grounding import select_images
    config_path=Path('/opt/vespa/configs/vlm/p_final.yaml')
    config=yaml.safe_load(config_path.read_text())['grounding_sam']
    detections={row['image']:[{**b,'label':b['label'].split('.')[0]} for b in row['boxes'] if b['label'].split('.')[0] in config['class_names']]
        for row in (json.loads(line) for line in a.detections.read_text().splitlines()) if row['event']=='completed'}
    images=select_images(a.data_root,'v1.0-mini','scene-0061',1)
    if set(detections)!={r['token'] for r in images}:raise ValueError('Fixed detection coverage mismatch')
    manifest={'threads':threads,'torch_threads':torch.get_num_threads(),'torch_interop_threads':torch.get_num_interop_threads(),
        'opencv_threads':cv2.getNumThreads(),'affinity_cpu_count':len(os.sched_getaffinity(0)),
        'scope':'SAM inference and CPU mask postprocessing, fixed detections, six cameras, one warm repetition',
        'model':config['segmentator'],'config_sha256':hashlib.sha256(config_path.read_bytes()).hexdigest(),
        'detection_input_sha256':hashlib.sha256(a.detections.read_bytes()).hexdigest(),
        'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path(sam.__file__))},
        'inputs':[{'image':r['token'],'sha256':hashlib.sha256((a.data_root/r['filename']).read_bytes()).hexdigest(),'boxes':len(detections[r['token']])} for r in images],
        'torch':torch.__version__,'gpu':torch.cuda.get_device_name(),'inference_mode':True}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    with (a.output/'events.jsonl').open('x') as stream:
        def emit(value):
            value={'at':datetime.now(timezone.utc).isoformat(),**value}
            line=json.dumps(value,allow_nan=False);stream.write(line+'\n');stream.flush();print(line,flush=True)
        started=time.perf_counter();model,processor=sam._SamSegmentatorSingleton.get_model_instance(config['segmentator'])
        emit({'event':'model_loaded','seconds':time.perf_counter()-started})
        call=torch.inference_mode()(sam._sam_segmentation)
        first=next(row for row in images if detections[row['token']])
        frame=cv2.imread(str(a.data_root/first['filename']))
        started=time.perf_counter();call(frame,detections[first['token']],model,processor);torch.cuda.synchronize()
        emit({'event':'warmup','seconds':time.perf_counter()-started})
        for row in images:
            frame=cv2.imread(str(a.data_root/row['filename']))
            if frame is None:raise ValueError('Image decode failed')
            torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats()
            before=resource.getrusage(resource.RUSAGE_SELF);cpu=time.process_time();started=time.perf_counter()
            masks=call(frame,detections[row['token']],model,processor) if detections[row['token']] else []
            torch.cuda.synchronize();elapsed=time.perf_counter()-started;cpu_elapsed=time.process_time()-cpu
            after=resource.getrusage(resource.RUSAGE_SELF)
            if len(masks)!=len(detections[row['token']]):raise ValueError('Mask count mismatch')
            fingerprints=[{'shape':list(m.shape),'dtype':str(m.dtype),'ones':int(np.count_nonzero(m)),
                'sha256':hashlib.sha256(np.ascontiguousarray(m).tobytes()).hexdigest()} for m in masks]
            emit({'event':'completed','image':row['token'],'wall_seconds':elapsed,'process_cpu_seconds':cpu_elapsed,
                'voluntary_context_switches':after.ru_nvcsw-before.ru_nvcsw,'involuntary_context_switches':after.ru_nivcsw-before.ru_nivcsw,
                'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved(),
                'boxes':len(masks),'masks':fingerprints})
        emit({'event':'run_completed'})


if __name__=='__main__':main()
