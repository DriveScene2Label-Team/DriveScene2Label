"""Pair SAM thread measurements using the same successful Grounding reference.

Run sequentially after the application GPU job and Grounding thread experiment.
It writes only experiment artifacts and never changes production thread limits.
"""
import argparse
import json
from pathlib import Path
import re
import statistics
from evidence_io import save_json
from run_thread_cases import ROOT,AI,run


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--grounding-directory',type=Path,required=True);p.add_argument('--dataset-key',required=True)
    a=p.parse_args()
    if not re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',a.dataset_key):raise ValueError('Expected cache UUID')
    if not re.fullmatch(r'\d{8}T\d{6}Z',a.grounding_directory.name):raise ValueError('Expected measurement directory')
    ground=json.loads((a.grounding_directory/'thread-comparison.json').read_text(encoding='utf-8-sig'))
    if not ground['quality_passed']:raise ValueError('Grounding reference did not pass')
    if not (a.directory/'manifest.json').is_file():raise ValueError('Begin a fresh measurement')
    remote='/tmp/ds2l-sam-threads-'+a.directory.name
    output='/results/experiments/'+a.directory.name+'-sam-threads'
    detection='/results/experiments/'+a.grounding_directory.name+'-threads/r0-t1/events.jsonl'
    run(['docker','exec',AI,'mkdir','-p',remote+'/tools',remote+'/services'],a.directory,'prepare')
    # benchmark_grounding imports grounding_probe on module import but does not load a model.
    for relative in ('tools/benchmark_sam_threads.py','tools/benchmark_grounding.py'):
        run(['docker','cp',str(ROOT/'ai-server'/relative),AI+':'+remote+'/'+relative],a.directory,'copy-'+Path(relative).stem)
    run(['docker','cp',str(ROOT/'ai-server/services/grounding_probe.py'),AI+':'+remote+'/services/grounding_probe.py'],a.directory,'copy-probe')
    cases=[];outputs={}
    for repeat,order in enumerate(((1,2,4),(4,1,2),(2,4,1))):
        for threads in order:
            name=f'r{repeat}-t{threads}';case=a.directory/name;case.mkdir(exist_ok=False);target=output+'/'+name
            print(json.dumps({'event':'sam_thread_case_started','repeat':repeat,'threads':threads}),flush=True)
            run(['docker','exec','--env',f'VESPA_NUM_THREADS={threads}',AI,'/opt/vespa-env/bin/python',remote+'/tools/benchmark_sam_threads.py',
                '--data-root','/uploads/datasets/'+a.dataset_key,'--detections',detection,'--output',target],case,'sam')
            for file in ('manifest.json','events.jsonl'):
                run(['docker','cp',AI+':'+target+'/'+file,str(case/file)],case,'copy-'+Path(file).stem)
            manifest=json.loads((case/'manifest.json').read_text(encoding='utf-8-sig'));rows=[json.loads(line) for line in (case/'events.jsonl').read_text(encoding='utf-8-sig').splitlines()]
            completed=[r for r in rows if r['event']=='completed']
            if len(completed)!=6 or len({r['image'] for r in completed})!=6 or manifest['torch_threads']!=threads:raise RuntimeError('Incomplete or mismatched case')
            outputs[(repeat,threads)]={r['image']:r['masks'] for r in completed}
            value={'repeat':repeat,'threads':threads,'manifest':manifest,'directory':str(case),
                'wall_seconds':sum(r['wall_seconds'] for r in completed),'cpu_seconds':sum(r['process_cpu_seconds'] for r in completed),
                'voluntary_context_switches':sum(r['voluntary_context_switches'] for r in completed),
                'involuntary_context_switches':sum(r['involuntary_context_switches'] for r in completed),
                'max_allocated_bytes':max(r['peak_allocated_bytes'] for r in completed),'mask_count':sum(r['boxes'] for r in completed),
                'command_wall_seconds':json.loads((case/'sam-execution.json').read_text(encoding='utf-8-sig'))['wall_seconds'],
                'model_load_seconds':next(r['seconds'] for r in rows if r['event']=='model_loaded')}
            cases.append(value);save_json(a.directory/'sam-thread-runs.json',cases)
            print(json.dumps({'event':'sam_thread_case_completed','repeat':repeat,'threads':threads,'seconds':value['wall_seconds']}),flush=True)
    checks=[{'repeat':repeat,'threads':threads,'mask_fingerprints_exact':outputs[(repeat,1)]==outputs[(repeat,threads)]} for repeat in range(3) for threads in (2,4)]
    inputs=all(c['manifest']['inputs']==cases[0]['manifest']['inputs'] and c['manifest']['detection_input_sha256']==cases[0]['manifest']['detection_input_sha256'] for c in cases)
    medians={str(t):statistics.median(c['wall_seconds'] for c in cases if c['threads']==t) for t in (1,2,4)}
    result={'scope':'fixed boxes; SAM inference and CPU postprocessing, six cameras x three repeats; no full scene/3D',
        'cases':cases,'quality_checks':checks,'same_inputs':inputs,'quality_passed':inputs and all(c['mask_fingerprints_exact'] for c in checks),
        'median_seconds':medians,'best_observed_threads':min(medians,key=medians.get),
        'decision':'keep production threads=1 until full-scene validation; use together with Grounding timings'}
    save_json(a.directory/'sam-thread-comparison.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','quality_checks')}),flush=True)
    if not result['quality_passed']:raise SystemExit(1)


if __name__=='__main__':main()
