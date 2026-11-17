"""Validate the preselected CPU candidate with all scene geometry and tracking."""
import argparse
import json
from pathlib import Path
from evidence_io import save_json
from run_thread_cases import ROOT,AI,run


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--selection',type=Path,required=True)
    p.add_argument('--dataset-key',required=True)
    p.add_argument('--reference',default='/results/experiments/20261117T140927Z-G2-scene')
    a=p.parse_args()
    import re
    if not re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',a.dataset_key):raise ValueError('Expected cache UUID')
    decision=read(a.selection);threads=decision['candidate_threads']
    if not decision['quality_passed'] or threads not in (2,4):raise ValueError('No eligible microbenchmark candidate')
    if not (a.directory/'manifest.json').is_file():raise ValueError('Begin a fresh measurement')
    target='/results/experiments/'+a.directory.name+'-thread-scene'
    remote='/tmp/ds2l-thread-scene-'+a.directory.name+'.py'
    save_json(a.directory/'microbenchmark-selection.json',decision)
    run(['docker','cp',str(ROOT/'ai-server/tools/benchmark_thread_scene.py'),AI+':'+remote],a.directory,'copy-runner')
    run(['docker','exec',AI,'/opt/vespa-env/bin/python',remote,'--data-root','/uploads/datasets/'+a.dataset_key,
         '--output',target,'--reference',a.reference,'--threads',str(threads)],a.directory,'scene')
    run(['docker','exec',AI,'/opt/vespa-env/bin/python','/app/ai-server/tools/compare_scene.py',
         '--directory',target,'--ground-truth'],a.directory,'compare')
    for file in ('manifest.json','quality-with-gt.json'):
        run(['docker','cp',AI+':'+target+'/'+file,str(a.directory/('scene-'+file))],a.directory,'copy-'+file)
    for mode in ('baseline','reuse'):
        destination=a.directory/mode;destination.mkdir(exist_ok=False)
        for file in ('command.json','execution-summary.json','stage-events.jsonl','detector-results.jsonl','stdout.log','stderr.log'):
            run(['docker','cp',AI+':'+target+'/'+mode+'/'+file,str(destination/file)],a.directory,'copy-'+mode+'-'+file)
        run(['docker','cp',AI+':'+target+'/'+mode+'/outs/vlm/p_final/#out_labels/vlm_p_final_scene-0061_8class.json',
             str(destination/'final-result.json')],a.directory,'copy-'+mode+'-final-result')
    quality=read(a.directory/'scene-quality-with-gt.json')
    exact=quality['quality_passed'] and all(quality[key]['exact'] for key in ('output_regression','detector_regression','ground_truth_regression'))
    timing={mode:row['execution']['wall_seconds'] for mode,row in quality['timings'].items()}
    result={'candidate_threads':threads,'quality_passed':quality['quality_passed'],'exact_quality_passed':exact,
            'adoption_eligible':exact and timing['reuse']<timing['baseline'],
            'wall_seconds':timing,'remote_output':target,
            'timing_scope':'historical threads=1 reuse reference, not contemporaneous controlled causal timing',
            'baseline_means':'G2 preprocessing reuse with native threads=1',
            'reuse_means':'same preprocessing reuse with native threads='+str(threads)}
    save_json(a.directory/'thread-scene-decision.json',result)
    print(json.dumps(result),flush=True)
    # A valid completed experiment can reject a candidate. Keep that distinct
    # from a failed command or missing evidence in the measurement wrapper.


if __name__=='__main__':main()
