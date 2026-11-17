"""Log isolated attention/precision attempts; never change production defaults.

Initialization failures remain evidence, not zero-latency performance results.
Quantized/approximate detections are diagnostic only until complete 3D evaluation.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import time
from evidence_io import save_json
from run_thread_cases import ROOT,AI,comparison


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def command(argv,directory,name):
    save_json(directory/(name+'-command.json'),argv);start=time.monotonic()
    with (directory/(name+'.stdout.log')).open('wb') as out,(directory/(name+'.stderr.log')).open('wb') as err:
        code=subprocess.call(argv,stdout=out,stderr=err)
    save_json(directory/(name+'-execution.json'),{'exit_code':code,'wall_seconds':time.monotonic()-start})
    return code


def iou(left,right):
    width=max(0,min(left['xmax'],right['xmax'])-max(left['xmin'],right['xmin']))
    height=max(0,min(left['ymax'],right['ymax'])-max(left['ymin'],right['ymin']))
    intersection=width*height
    area=lambda b:max(0,b['xmax']-b['xmin'])*max(0,b['ymax']-b['ymin'])
    return intersection/(area(left)+area(right)-intersection) if intersection else 0.


def geometry_diagnostic(baseline,candidate):
    """Greedy same-class IoU matching is diagnostic, not AP or a production gate."""
    matched=[];missing=extra=0;counts_equal=True
    for token,reference in baseline.items():
        values=candidate.get(token,[])
        counts_equal=counts_equal and Counter(b['label'] for b in reference)==Counter(b['label'] for b in values)
        available=set(range(len(values)))
        for box in reference:
            options=[(iou(box['box'],values[i]['box']),i) for i in available if values[i]['label']==box['label']]
            score,index=max(options,default=(0,None))
            if score<.5:missing+=1;continue
            available.remove(index)
            matched.append({'iou':score,'score_absolute_difference':abs(box['score']-values[index]['score'])})
        extra+=len(available)
    return {'method':'greedy same-class IoU>=0.5; diagnostic, not mAP',
            'same_image_set':set(baseline)==set(candidate),'same_per_image_class_counts':counts_equal,
            'matched':len(matched),'unmatched_reference':missing,'unmatched_candidate':extra,
            'minimum_matched_iou':min((m['iou'] for m in matched),default=None),
            'maximum_matched_score_difference':max((m['score_absolute_difference'] for m in matched),default=None)}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--dataset-key',required=True);a=p.parse_args()
    if not re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',a.dataset_key):raise ValueError('Expected dataset UUID')
    if not (a.directory/'manifest.json').is_file():raise ValueError('Begin a fresh measurement')
    remote='/tmp/ds2l-variants-'+a.directory.name;output='/results/experiments/'+a.directory.name+'-variants'
    if command(['docker','exec',AI,'mkdir','-p',remote+'/tools',remote+'/services'],a.directory,'prepare'):raise RuntimeError('Prepare failed')
    for relative in ('tools/benchmark_grounding.py','services/grounding_probe.py'):
        if command(['docker','cp',str(ROOT/'ai-server'/relative),AI+':'+remote+'/'+relative],a.directory,'copy-'+Path(relative).stem):raise RuntimeError('Copy failed')
    settings={'fp32':[],'fp16':['--precision','fp16'],'bf16':['--precision','bf16'],
              'amp_fp16':['--precision','amp_fp16'],'amp_bf16':['--precision','amp_bf16'],
              'tf32':['--matmul-tf32','on']}
    orders=[['fp32','fp16','bf16','amp_fp16','amp_bf16','tf32'],
            ['tf32','amp_bf16','amp_fp16','bf16','fp16','fp32'],
            ['amp_fp16','fp32','tf32','fp16','amp_bf16','bf16']]
    save_json(a.directory/'variant-plan.json',{'orders':orders,'threads':1,'seed':42,'frames':1,
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'ai-server/tools/benchmark_grounding.py',ROOT/'ai-server/services/grounding_probe.py')},
        'gate':'No automatic production adoption. Exact output + full-scene validation required; any approximation reported separately.',
        'attention_checks':'sdpa FP32 and flash_attention_2 FP16 constructor/capability attempts, not a paired performance claim'})
    cases=[];failed=set();boxes={}
    def case(name,flags,repeat,kind):
        label=f'{kind}-r{repeat}-{name}';directory=a.directory/label;directory.mkdir(exist_ok=False);target=output+'/'+label
        print(json.dumps({'event':'variant_started','case':label}),flush=True)
        argv=['docker','exec','--env','VESPA_NUM_THREADS=1','--env','HF_HUB_OFFLINE=1',AI,
              'timeout','--signal=TERM','--kill-after=10s','300s','/opt/vespa-env/bin/python',remote+'/tools/benchmark_grounding.py',
              '--data-root','/uploads/datasets/'+a.dataset_key,'--output',target,'--frames','1','--repeats','1','--mode','reuse','--seed','42',*flags]
        code=command(argv,directory,'detector')
        for file in ('manifest.json','events.jsonl'):
            # Missing manifest on an early failure is explicit evidence, not a successful run.
            command(['docker','cp',AI+':'+target+'/'+file,str(directory/file)],directory,'copy-'+file)
        result={'case':label,'name':name,'repeat':repeat,'kind':kind,'exit_code':code,'directory':str(directory)}
        if code==0:
            rows=[json.loads(line) for line in (directory/'events.jsonl').read_text(encoding='utf-8').splitlines()]
            completed=[r for r in rows if r['event']=='completed'];manifest=read(directory/'manifest.json')
            if len(completed)!=6 or len({r['image'] for r in completed})!=6:raise RuntimeError('Incomplete camera coverage')
            result.update(status='completed',wall_seconds=sum(r['wall_ms'] for r in completed)/1000,
                cpu_seconds=sum(r['process_cpu_seconds'] for r in completed),max_allocated_bytes=max(r['peak_allocated_bytes'] for r in completed),
                model_load_seconds=next(r['seconds'] for r in rows if r['event']=='model_loaded'),
                forward_calls=sum(r['forward_calls'] for r in completed),manifest=manifest)
            boxes[(kind,repeat,name)]={r['image']:r['boxes'] for r in completed}
        else:
            result['status']='failed_or_unsupported';failed.add(name)
            result['diagnostic']='See preserved detector stderr and run_failed event. No inference time claimed.'
        cases.append(result);save_json(a.directory/'variant-runs.json',cases)
        print(json.dumps({k:v for k,v in result.items() if k not in ('manifest','directory')}),flush=True)
    for name,flags in [('sdpa',['--attention','sdpa']),('flash_attention_2',['--attention','flash_attention_2','--precision','fp16'])]:
        case(name,flags,0,'attention')
    for repeat,order in enumerate(orders):
        for name in order:
            if name in failed:
                cases.append({'name':name,'repeat':repeat,'kind':'precision','status':'not_retried_after_failed_smoke'});continue
            case(name,settings[name],repeat,'precision')
            if name=='fp32' and name in failed:raise RuntimeError('Reference failed; stop candidate timing')
    checks=[]
    for item in cases:
        if item['kind']!='precision' or item['name']=='fp32' or item['status']!='completed':continue
        key=('precision',item['repeat'],item['name']);reference=boxes[('precision',item['repeat'],'fp32')]
        baseline_case=next(c for c in cases if c['kind']=='precision' and c['name']=='fp32' and c['repeat']==item['repeat'])
        fields=('inputs','config_sha256','labels','threshold','model_commit','torch_threads','source_sha256','torch','transformers','gpu')
        unchanged=all(item['manifest'][k]==baseline_case['manifest'][k] for k in fields)
        if not unchanged:raise RuntimeError('Non-treatment condition changed')
        checks.append({'repeat':item['repeat'],'name':item['name'],'non_treatment_conditions_match':unchanged,'output_regression':comparison.compare(reference,boxes[key]),
                       'geometry':geometry_diagnostic(reference,boxes[key])})
    aggregate={}
    for name in settings:
        completed=[c for c in cases if c['kind']=='precision' and c['name']==name and c['status']=='completed']
        aggregate[name]={'completed_repeats':len(completed)}
        if len(completed)==3:
            aggregate[name].update(median_seconds=statistics.median(c['wall_seconds'] for c in completed),
                peak_allocated_bytes=max(c['max_allocated_bytes'] for c in completed),
                exact_outputs=all(c['output_regression']['exact'] for c in checks if c['name']==name))
    result={'created_at':datetime.now(timezone.utc).isoformat(),'scope':'six-image isolated detector only; no SAM/full-scene quality',
            'cases':cases,'quality_checks':checks,'aggregate':aggregate,'decision':'experimental evidence only; production precision/attention unchanged'}
    save_json(a.directory/'variant-comparison.json',result)
    print(json.dumps({'event':'variant_matrix_completed','aggregate':aggregate}),flush=True)


if __name__=='__main__':main()
