"""Verify a promising CPU thread setting through the complete production runner.

Uses the preserved fixed-seed G2/reuse output as the threads=1 quality reference.
That earlier run is not a contemporaneous causal timing baseline. The candidate
gets a fresh cache; only native thread limits change. No app DB or AWS writes.
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


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True,help='Completed G2 root containing reuse and manifest.json')
    p.add_argument('--threads',type=int,choices=(2,4),required=True)
    p.add_argument('--runner',type=Path,default=Path('/app/ai-server/services/vespa_runner.py'))
    a=p.parse_args();reference=a.reference.resolve();output=a.output.resolve()
    if not reference.is_relative_to(Path('/results/experiments')) or not output.is_relative_to(Path('/results/experiments')):
        raise ValueError('Experiment paths must stay under the results experiment directory')
    prior=json.loads((reference/'manifest.json').read_text())
    if prior['threads']!=1 or prior['seed']!=42:raise ValueError('Unexpected reference conditions')
    if json.loads((reference/'reuse/execution-summary.json').read_text())['exit_code']!=0:raise ValueError('Reference was not successful')
    hashes={name:hashlib.sha256((a.data_root/prior['version']/(name+'.json')).read_bytes()).hexdigest() for name in prior['metadata_sha256']}
    if hashes!=prior['metadata_sha256']:raise ValueError('Metadata changed since reference')
    config=Path('/opt/vespa/configs/vlm/p_final.yaml')
    if hashlib.sha256(config.read_bytes()).hexdigest()!=prior['config_sha256']:raise ValueError('Model configuration changed')
    sources={name:hashlib.sha256((a.runner.parent/name).read_bytes()).hexdigest() for name in ('vespa_runner.py','grounding_probe.py','grounding_runtime.py','stage_timing.py','rigid_cache.py')}
    if any(prior['sources'][name]!=value for name,value in sources.items()):raise ValueError('Production source differs from reference')
    import torch,transformers,numpy
    versions={'torch':torch.__version__,'transformers':transformers.__version__,'numpy':numpy.__version__,
        'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name()}
    if any(prior[name]!=value for name,value in versions.items()):raise ValueError('Runtime differs from reference')
    if a.threads>len(os.sched_getaffinity(0)):raise ValueError('Requested threads exceed CPU affinity')
    output.mkdir(parents=True,exist_ok=False)
    (output/'baseline').symlink_to(reference/'reuse',target_is_directory=True)
    run=output/'reuse';run.mkdir()
    manifest={**prior,'started_at':datetime.now(timezone.utc).isoformat(),'data_root':str(a.data_root),
        'scope':'CPU thread candidate full-scene quality versus preserved threads=1 reuse reference; historical timing is not a controlled causal comparison',
        'reference':str(reference/'reuse'),'reference_threads':1,'threads':a.threads,'sources':sources,**versions,
        'quality_gate':'complete detector, final 3D/track and official scene GT metrics unchanged',
        'grounding_preprocessing':'reuse for both conditions','candidate_fresh_intermediate_cache':True}
    command=[sys.executable,str(a.runner),'--repo','/opt/vespa','--config',str(config),'--scene',prior['scene'],
        '--class-mode','8','--output-root',str(run),'--data-root',str(a.data_root),'--dataset-version',prior['version'],
        '--rigid','--grounding-preprocess','reuse','--experiment-seed','42','--detector-trace']
    (run/'command.json').write_text(json.dumps(command,indent=2))
    env=os.environ.copy();env.update(PYTHONUNBUFFERED='1',PYTHONHASHSEED='42',VESPA_NUM_THREADS=str(a.threads))
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):env[name]=str(a.threads)
    # Verify the child's native initialization rather than reporting the parent's setting.
    check=subprocess.run([sys.executable,'-c','import torch,json; print(json.dumps({"torch_threads":torch.get_num_threads(),"interop_threads":torch.get_num_interop_threads()}))'],
                         env=env,capture_output=True,text=True,check=True)
    manifest['child_thread_preflight']=json.loads(check.stdout)
    if manifest['child_thread_preflight']['torch_threads']!=a.threads:raise ValueError('Child thread cap mismatch')
    manifest['native_environment']={key:env[key] for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VESPA_NUM_THREADS')}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    started=time.perf_counter()
    with (run/'stdout.log').open('wb') as out,(run/'stderr.log').open('wb') as err:
        process=subprocess.Popen(command,cwd='/opt/vespa',env=env,stdout=out,stderr=err,start_new_session=True)
        (run/'pid.txt').write_text(str(process.pid))
        print(json.dumps({'event':'thread_scene_started','threads':a.threads,'pid':process.pid,'output':str(output)}),flush=True)
        try:code=process.wait(timeout=7200)
        except BaseException:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=20)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            raise
    result={'mode':'reuse','threads':a.threads,'exit_code':code,'wall_seconds':time.perf_counter()-started,'finished_at':datetime.now(timezone.utc).isoformat()}
    (run/'execution-summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    if code:raise SystemExit(code)


if __name__=='__main__':main()
