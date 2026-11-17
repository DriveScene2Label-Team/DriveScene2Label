"""Compare the installed detector with image preprocessing reuse on cached data.

Run inside the existing VESPA environment. Never writes RDS, S3 or app datasets.
Output is append-only JSONL plus a manifest; one fresh directory per invocation.
"""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services'))
from grounding_probe import observe_detector, reuse_image_preprocessing


def now():
    return datetime.now(timezone.utc).isoformat()


def select_images(root, version, scene_name, frames):
    metadata = root / version
    read = lambda name: json.loads((metadata / (name+'.json')).read_text())
    scenes = [row for row in read('scene') if row['name'] == scene_name]
    if len(scenes) != 1:
        raise ValueError('Expected exactly one matching scene')
    samples = sorted((row for row in read('sample') if row['scene_token'] == scenes[0]['token']),
                     key=lambda row: (row['timestamp'], row['token']))
    if len(samples) < frames:
        raise ValueError('Requested more frames than available')
    selected = {samples[index]['token'] for index in range(frames)}
    rows = sorted((row for row in read('sample_data') if row['is_key_frame']
                   and row['sample_token'] in selected and row['filename'].startswith('samples/CAM_')),
                  key=lambda row: (row['timestamp'], row['filename'], row['token']))
    if len(rows) != frames*6:
        raise ValueError('Expected six keyframe camera images per frame')
    for row in rows:
        path = (root / row['filename']).resolve(strict=True)
        if not path.is_relative_to(root.resolve()):
            raise ValueError('Dataset path escaped root')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('/opt/vespa/configs/vlm/p_final.yaml'))
    parser.add_argument('--version', default='v1.0-mini')
    parser.add_argument('--scene', default='scene-0061')
    parser.add_argument('--frames', type=int, default=2)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--mode', choices=('baseline','reuse','compare'), default='compare')
    parser.add_argument('--diagnostic', action='store_true')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--precision', choices=('fp32','fp16','bf16','amp_fp16','amp_bf16'), default='fp32')
    parser.add_argument('--attention', choices=('auto','eager','sdpa','flash_attention_2'), default='auto')
    parser.add_argument('--matmul-tf32', choices=('baseline','on','off'), default='baseline')
    args = parser.parse_args()
    if not 1 <= args.frames <= 39 or not 1 <= args.repeats <= 10:
        parser.error('Use 1..39 frames and 1..10 repeats')
    args.output.mkdir(parents=True, exist_ok=False)
    event_file = (args.output / 'events.jsonl').open('x', encoding='utf-8')

    def emit(**row):
        line = json.dumps({'at': now(), **row}, allow_nan=False)
        event_file.write(line+'\n')
        event_file.flush()
        print(line, flush=True)

    try:
        import os
        import resource
        import random
        threads = int(os.environ.get('VESPA_NUM_THREADS', '1'))
        for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
            os.environ[key] = str(threads)
        import torch
        import transformers
        import yaml
        from PIL import Image
        torch.set_num_threads(threads)
        if args.matmul_tf32!='baseline':torch.backends.cuda.matmul.allow_tf32=args.matmul_tf32=='on'
        random.seed(args.seed)
        torch.manual_seed(args.seed)
        torch.cuda.manual_seed_all(args.seed)
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA is required for this benchmark')
        if 'bf16' in args.precision and not torch.cuda.is_bf16_supported():raise RuntimeError('BF16 unsupported by this GPU/runtime')
        config = yaml.safe_load(args.config.read_text())['grounding_sam']
        labels = [name+'.' for name in config['class_names']]
        rows = select_images(args.data_root, args.version, args.scene, args.frames)
        manifest = {'started_at': now(), 'scope': 'detector only; no SAM/3D/RDS/S3',
            'scene': args.scene, 'frames': args.frames, 'images': len(rows), 'repeats': args.repeats,
            'mode': args.mode, 'diagnostic': args.diagnostic, 'threads': threads, 'seed': args.seed,
            'requested_precision':args.precision,'requested_attention':args.attention,'requested_matmul_tf32':args.matmul_tf32,
            'torch_threads': torch.get_num_threads(), 'torch_interop_threads': torch.get_num_interop_threads(),
            'cpu_affinity_count': len(os.sched_getaffinity(0)),
            'source_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in (Path(__file__), Path(__file__).resolve().parents[1]/'services/grounding_probe.py')},
            'model': config['detector'], 'threshold': config['det_threshold'], 'labels': labels,
            'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
            'torch': torch.__version__, 'transformers': transformers.__version__,
            'cuda': torch.version.cuda, 'cudnn': torch.backends.cudnn.version(),
            'gpu': torch.cuda.get_device_name(), 'arch_list': torch.cuda.get_arch_list(),
            'matmul_tf32': torch.backends.cuda.matmul.allow_tf32,
            'cudnn_tf32': torch.backends.cudnn.allow_tf32, 'cudnn_benchmark': torch.backends.cudnn.benchmark,
            'inputs': [{'token': row['token'], 'path': row['filename'],
                        'sha256': hashlib.sha256((args.data_root/row['filename']).read_bytes()).hexdigest()} for row in rows],
            'cache': 'existing model/data files; OS page cache uncontrolled; same first image warmup for each mode'}
        began = time.perf_counter()
        kwargs={}
        if args.precision in ('fp16','bf16'):kwargs['torch_dtype']={'fp16':torch.float16,'bf16':torch.bfloat16}[args.precision]
        if args.attention!='auto':kwargs['model_kwargs']={'attn_implementation':args.attention}
        # Save requested conditions even when the architecture rejects initialization.
        (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        detector = transformers.pipeline(model=config['detector'], task='zero-shot-object-detection', device=0,**kwargs)
        manifest['dtype'] = str(next(detector.model.parameters()).dtype)
        manifest['model_class']=type(detector.model).__name__
        manifest['actual_attention']=getattr(detector.model.config,'_attn_implementation',None)
        manifest['attention_support']={key:getattr(detector.model,key,None) for key in ('_supports_sdpa','_supports_flash_attn_2','_supports_flex_attn')}
        manifest['disable_custom_kernels']=getattr(detector.model.config,'disable_custom_kernels',None)
        from collections import Counter
        from transformers.models.grounding_dino import modeling_grounding_dino
        import shutil
        manifest['custom_deformable_kernel_loaded']=modeling_grounding_dino.MultiScaleDeformableAttention is not None
        manifest['ninja_executable']=shutil.which('ninja')
        manifest['nvcc_executable']=shutil.which('nvcc')
        manifest['attention_module_types']=dict(Counter(type(m).__name__ for m in detector.model.modules() if 'Attention' in type(m).__name__))
        manifest['model_commit'] = getattr(detector.model.config, '_commit_hash', None)
        manifest['pipeline_batch_size'] = detector._batch_size
        (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        emit(event='model_loaded', seconds=time.perf_counter()-began)
        results = []
        modes = ['baseline','reuse'] if args.mode == 'compare' else [args.mode]
        # Match the installed pipeline's no-grad execution; do not add inference_mode as a second change.
        autocast=(torch.autocast('cuda',dtype=torch.float16 if args.precision=='amp_fp16' else torch.bfloat16)
                  if args.precision.startswith('amp_') else nullcontext())
        with torch.no_grad(),autocast:
            for repeat in range(args.repeats):
                # Alternate order to reduce systematic warm-cache/order bias.
                for mode in (modes if repeat % 2 == 0 else list(reversed(modes))):
                    scope = reuse_image_preprocessing(detector) if mode == 'reuse' else nullcontext()
                    with scope:
                        with Image.open(args.data_root/rows[0]['filename']) as image:
                            started = time.perf_counter()
                            detector(image.convert('RGB'), candidate_labels=labels, threshold=config['det_threshold'])
                            torch.cuda.synchronize()
                            emit(event='warmup', mode=mode, repeat=repeat, seconds=time.perf_counter()-started)
                        for row in rows:
                            with Image.open(args.data_root/row['filename']) as image:
                                image = image.convert('RGB')
                                torch.cuda.synchronize()
                                torch.cuda.reset_peak_memory_stats()
                                usage_before = resource.getrusage(resource.RUSAGE_SELF)
                                cpu_started = time.process_time()
                                started = time.perf_counter()
                                with observe_detector(detector, synchronize=args.diagnostic) as metrics:
                                    boxes = detector(image, candidate_labels=labels, threshold=config['det_threshold'])
                                    torch.cuda.synchronize()
                                value = {'event':'completed', 'mode':mode, 'repeat':repeat, 'image':row['token'],
                                         'wall_ms':(time.perf_counter()-started)*1000, **metrics,
                                         'process_cpu_seconds': time.process_time()-cpu_started,
                                         'voluntary_context_switches': resource.getrusage(resource.RUSAGE_SELF).ru_nvcsw-usage_before.ru_nvcsw,
                                         'involuntary_context_switches': resource.getrusage(resource.RUSAGE_SELF).ru_nivcsw-usage_before.ru_nivcsw,
                                         'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
                                         'peak_reserved_bytes':torch.cuda.max_memory_reserved(),
                                         'boxes':boxes}
                                emit(**value)
                                results.append(value)
        summary = {'completed_at':now(), 'status':'completed', 'scope':manifest['scope'],
            'diagnostic':args.diagnostic, 'timings':{
                mode: {'images':sum(v['mode']==mode for v in results),
                       'repeat_total_ms':[sum(v['wall_ms'] for v in results if v['mode']==mode and v['repeat']==repeat)
                                          for repeat in range(args.repeats)],
                       'median_image_ms':statistics.median(v['wall_ms'] for v in results if v['mode']==mode)}
                for mode in modes}}
        if args.mode == 'compare':
            baseline = {(v['repeat'],v['image']):v for v in results if v['mode']=='baseline'}
            pairs = [(baseline[(v['repeat'],v['image'])],v) for v in results if v['mode']=='reuse']
            summary['regression'] = {'pairs':len(pairs),
                'exact_output_matches':sum(a['boxes']==b['boxes'] for a,b in pairs),
                'baseline_forward_calls':sum(a['forward_calls'] for a,b in pairs),
                'reuse_forward_calls':sum(b['forward_calls'] for a,b in pairs),
                'baseline_processor_calls':sum(a['image_processor_calls'] for a,b in pairs),
                'reuse_processor_calls':sum(b['image_processor_calls'] for a,b in pairs)}
        (args.output/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        emit(event='run_completed', **summary)
    except BaseException as error:
        emit(event='run_failed', error_type=type(error).__name__)
        raise
    finally:
        event_file.close()


if __name__ == '__main__':
    main()
