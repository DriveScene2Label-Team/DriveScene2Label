"""Compare native CPU thread limits in isolated, sequential detector processes.

Run after all application GPU jobs finish. Existing local dataset files are read
only. No model batching, request concurrency, RDS writes or AWS calls are added.
The detector microbenchmark cannot authorize a full-scene production change.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
from evidence_io import save_json

ROOT=Path(__file__).resolve().parents[2]
AI='drivescene-hybrid-ai-server-1'
spec=importlib.util.spec_from_file_location('scene_comparison',ROOT/'ai-server/tools/compare_scene.py')
comparison=importlib.util.module_from_spec(spec);spec.loader.exec_module(comparison)


def run(command,directory,name):
    save_json(directory/(name+'-command.json'),command)
    started=time.monotonic()
    with (directory/(name+'.stdout.log')).open('wb') as out,(directory/(name+'.stderr.log')).open('wb') as err:
        result=subprocess.run(command,stdout=out,stderr=err)
    save_json(directory/(name+'-execution.json'),{'exit_code':result.returncode,'wall_seconds':time.monotonic()-started})
    if result.returncode:raise RuntimeError(name+' failed; inspect saved evidence')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',required=True,type=Path)
    p.add_argument('--dataset-key',required=True)
    a=p.parse_args()
    if not re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',a.dataset_key):raise ValueError('Expected cache UUID')
    if not (a.directory/'manifest.json').is_file():raise ValueError('Use a fresh measurement')
    remote='/tmp/ds2l-threads-'+a.directory.name
    output='/results/experiments/'+a.directory.name+'-threads'
    run(['docker','exec',AI,'mkdir','-p',remote+'/tools',remote+'/services'],a.directory,'prepare-source')
    for relative in ('tools/benchmark_grounding.py','services/grounding_probe.py'):
        run(['docker','cp',str(ROOT/'ai-server'/relative),AI+':'+remote+'/'+relative],a.directory,'copy-'+Path(relative).stem)
    cases=[]
    for repeat,order in enumerate(((1,2,4),(4,1,2),(2,4,1))):
        for threads in order:
            name=f'r{repeat}-t{threads}';case=a.directory/name;case.mkdir(exist_ok=False)
            target=output+'/'+name
            command=['docker','exec','--env',f'VESPA_NUM_THREADS={threads}',AI,'/opt/vespa-env/bin/python',
                remote+'/tools/benchmark_grounding.py','--data-root','/uploads/datasets/'+a.dataset_key,
                '--output',target,'--frames','1','--repeats','1','--mode','reuse','--seed','42']
            print(json.dumps({'event':'thread_case_started','repeat':repeat,'threads':threads}),flush=True)
            run(command,case,'detector')
            for filename in ('manifest.json','events.jsonl','summary.json'):
                run(['docker','cp',AI+':'+target+'/'+filename,str(case/filename)],case,'copy-'+Path(filename).stem)
            manifest=json.loads((case/'manifest.json').read_text(encoding='utf-8-sig'))
            rows=[json.loads(line) for line in (case/'events.jsonl').read_text(encoding='utf-8-sig').splitlines()]
            completed=[r for r in rows if r['event']=='completed']
            if len(completed)!=6 or len({r['image'] for r in completed})!=6:raise RuntimeError('Incomplete image coverage')
            if manifest['threads']!=threads or manifest['torch_threads']!=threads:raise RuntimeError('Thread limit mismatch')
            value={'repeat':repeat,'threads':threads,'directory':str(case),'manifest':manifest,
                'wall_seconds':sum(r['wall_ms'] for r in completed)/1000,
                'command_wall_seconds':json.loads((case/'detector-execution.json').read_text(encoding='utf-8-sig'))['wall_seconds'],
                'model_load_seconds':next(r['seconds'] for r in rows if r['event']=='model_loaded'),
                'cpu_seconds':sum(r['process_cpu_seconds'] for r in completed),
                'voluntary_context_switches':sum(r['voluntary_context_switches'] for r in completed),
                'involuntary_context_switches':sum(r['involuntary_context_switches'] for r in completed),
                'max_allocated_bytes':max(r['peak_allocated_bytes'] for r in completed),
                'forward_calls':sum(r['forward_calls'] for r in completed),
                'processor_calls':sum(r['image_processor_calls'] for r in completed)}
            cases.append(value);save_json(a.directory/'thread-runs.json',cases)
            print(json.dumps({'event':'thread_case_completed',**{k:v for k,v in value.items() if k not in ('manifest','directory')}}),flush=True)
    checks=[]
    for repeat in range(3):
        values={v['threads']:v for v in cases if v['repeat']==repeat}
        def boxes(value):
            rows=[json.loads(line) for line in (Path(value['directory'])/'events.jsonl').read_text(encoding='utf-8-sig').splitlines()]
            return {r['image']:r['boxes'] for r in rows if r['event']=='completed'}
        for threads in (2,4):
            checks.append({'repeat':repeat,'threads':threads,'outputs':comparison.compare(boxes(values[1]),boxes(values[threads])),
                'inputs_equal':values[1]['manifest']['inputs']==values[threads]['manifest']['inputs']})
    medians={str(n):statistics.median(v['wall_seconds'] for v in cases if v['threads']==n) for n in (1,2,4)}
    passed=all(c['inputs_equal'] and c['outputs']['within_tolerance'] for c in checks)
    result={'scope':'six camera detector microbenchmark, three repetitions, fresh process and warmup for each condition; no SAM or 3D evaluation',
        'orders':[[1,2,4],[4,1,2],[2,4,1]],'cases':cases,'quality_checks':checks,'quality_passed':passed,
        'median_seconds':medians,'best_observed_threads':min(medians,key=medians.get),
        'decision':'microbenchmark only; keep production threads=1 until full-scene quality and wall validation',
        'limitation':'Context switches alone do not prove thrashing; inspect CPU-time/wall ratio, memory pressure and elapsed time together.'}
    save_json(a.directory/'thread-comparison.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','quality_checks')}),flush=True)
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
