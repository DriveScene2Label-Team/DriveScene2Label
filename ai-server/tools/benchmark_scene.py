"""Run baseline and reuse through the complete production VESPA runner sequentially.

Separate fresh output caches; fixed input, seed, settings and thread count.
Writes no app database, labels or S3 objects. Run only while the GPU is idle.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scene',default='scene-0061')
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--repo',type=Path,default=Path('/opt/vespa'))
    p.add_argument('--version',default='v1.0-mini')
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    services=Path(__file__).resolve().parents[1]/'services'
    source_paths=[services/name for name in ('vespa_runner.py','grounding_probe.py','grounding_runtime.py','stage_timing.py','rigid_cache.py')]
    config=args.repo/'configs/vlm/p_final.yaml'
    import torch, transformers, numpy, yaml
    settings=yaml.safe_load(config.read_text())['grounding_sam']
    manifest={'started_at':now(),'scene':args.scene,'seed':args.seed,'data_root':str(args.data_root),
        'version':args.version,'scope':'complete VESPA rigid pipeline, fresh per-mode intermediate caches; no API/DB/S3',
        'modes':['baseline','reuse'],'threads':1,'dtype_change':False,'detector_trace':True,
        'quality_gate':'same 39 sample tokens; same classes, counts and tracks; exact 2D/3D outputs expected. Investigate any difference before adoption.',
        'config_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),
        'model':settings['detector'],'threshold':settings['det_threshold'],'labels':settings['class_names'],
        'torch':torch.__version__,'transformers':transformers.__version__,'numpy':numpy.__version__,
        'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),'arch_list':torch.cuda.get_arch_list(),
        'matmul_tf32':torch.backends.cuda.matmul.allow_tf32,'cudnn_tf32':torch.backends.cudnn.allow_tf32,
        'sources':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths+[Path(__file__)]},
        'metadata_sha256':{name:hashlib.sha256((args.data_root/args.version/(name+'.json')).read_bytes()).hexdigest()
                           for name in ('scene','sample','sample_data','sample_annotation')}}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    events=(args.output/'events.jsonl').open('x',encoding='utf-8')
    def emit(**row):
        line=json.dumps({'at':now(),**row});events.write(line+'\n');events.flush();print(line,flush=True)
    env=os.environ.copy()
    env.update(PYTHONUNBUFFERED='1',PYTHONHASHSEED=str(args.seed),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    try:
        for mode in ('baseline','reuse'):
            run=args.output/mode
            run.mkdir(exist_ok=False)
            command=[sys.executable,str(services/'vespa_runner.py'),'--repo',str(args.repo),'--config',str(config),
                '--scene',args.scene,'--class-mode','8','--output-root',str(run),'--data-root',str(args.data_root),
                '--dataset-version',args.version,'--rigid','--grounding-preprocess',mode,
                '--experiment-seed',str(args.seed),'--detector-trace']
            (run/'command.json').write_text(json.dumps(command,indent=2),encoding='utf-8')
            emit(event='started',mode=mode)
            start=time.perf_counter()
            with (run/'stdout.log').open('wb') as stdout,(run/'stderr.log').open('wb') as stderr:
                process=subprocess.Popen(command,cwd=args.repo,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
                (run/'pid.txt').write_text(str(process.pid))
                try:
                    code=process.wait(timeout=7200)
                except BaseException:
                    os.killpg(process.pid,signal.SIGTERM)
                    try: process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL);process.wait()
                    raise
            result={'mode':mode,'exit_code':code,'wall_seconds':time.perf_counter()-start,'finished_at':now()}
            (run/'execution-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            emit(event='completed' if code==0 else 'failed',**result)
            if code:
                raise RuntimeError('VESPA runner failed; retain the original stderr and stage events.')
        emit(event='pair_completed')
    except BaseException as error:
        emit(event='experiment_failed',error_type=type(error).__name__)
        raise
    finally:
        events.close()


if __name__=='__main__':
    main()
