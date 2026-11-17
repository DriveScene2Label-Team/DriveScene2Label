"""Audit full-scene output regression and official-devkit metrics on that scene only.

Scene-only mAP/NDS are diagnostics, never nuScenes leaderboard scores.
No database writes. The original output and intermediate caches remain untouched.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def compare(left,right,tolerance=1e-6):
    differences=[]; max_abs=0.0
    def visit(a,b,path):
        nonlocal max_abs
        if isinstance(a,(float,int)) and not isinstance(a,bool) and isinstance(b,(float,int)) and not isinstance(b,bool):
            if not (math.isfinite(a) and math.isfinite(b)):
                differences.append({'path':path,'reason':'nonfinite'});return
            delta=abs(a-b);max_abs=max(max_abs,delta)
            # Discrete identities/indices must match exactly.
            if delta > (0 if isinstance(a,int) and isinstance(b,int) else tolerance):
                differences.append({'path':path,'reason':'numeric','absolute_difference':delta})
        elif isinstance(a,dict) and isinstance(b,dict):
            if a.keys()!=b.keys(): differences.append({'path':path,'reason':'keys'})
            for key in sorted(a.keys() & b.keys()): visit(a[key],b[key],path+'/'+key)
        elif isinstance(a,list) and isinstance(b,list):
            if len(a)!=len(b): differences.append({'path':path,'reason':'length','baseline':len(a),'reuse':len(b)})
            for i,(x,y) in enumerate(zip(a,b)):visit(x,y,path+'/'+str(i))
        elif a!=b:
            differences.append({'path':path,'reason':'value'})
    visit(left,right,'')
    return {'exact':left==right,'within_tolerance':not differences,'tolerance':tolerance,
            'max_numeric_absolute_difference':max_abs,'difference_count':len(differences),
            'first_differences':differences[:50]}


def clean(value):
    if isinstance(value,dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def ground_truth_metrics(payload,nusc,cfg):
    from nuscenes.eval.common.data_classes import EvalBoxes
    from nuscenes.eval.common.loaders import load_gt,add_center_dist,filter_eval_boxes
    from nuscenes.eval.detection.data_classes import DetectionBox
    from nuscenes.eval.detection.evaluate import DetectionEval
    prediction=EvalBoxes.deserialize(payload['results'],DetectionBox)
    # VESPA labels this scene "train" even for v1.0-mini. The official devkit
    # requires the version-specific mini_train / mini_val split names.
    split=payload['split']
    if nusc.version=='v1.0-mini' and split in ('train','val'):split='mini_'+split
    all_gt=load_gt(nusc,split,DetectionBox,verbose=False)
    gt=EvalBoxes()
    for token in payload['results']:
        if token not in all_gt.sample_tokens:raise ValueError('Output sample is outside the GT split')
        gt.add_boxes(token,all_gt[token])
    prediction=filter_eval_boxes(nusc,add_center_dist(nusc,prediction),cfg.class_range,verbose=False)
    gt=filter_eval_boxes(nusc,add_center_dist(nusc,gt),cfg.class_range,verbose=False)
    # Reuse the installed evaluator's calculation unchanged after restricting both sides
    # to exactly the same scene. Its normal constructor requires the entire dataset split.
    evaluator=DetectionEval.__new__(DetectionEval)
    evaluator.pred_boxes,evaluator.gt_boxes,evaluator.cfg,evaluator.verbose=prediction,gt,cfg,False
    metrics,details=evaluator.evaluate()
    result=metrics.serialize();result.pop('eval_time',None)
    return clean({'scope':'single scene; official filtering/matching/metric calculation; not full-split benchmark',
        'payload_split':payload['split'],'devkit_split':split,
        'predicted_boxes_after_filter':len(prediction.all),'gt_boxes_after_filter':len(gt.all),
        'gt_by_class':dict(Counter(box.detection_name for box in gt.all)),
        'predicted_by_class':dict(Counter(box.detection_name for box in prediction.all)),
        'metrics':result})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--ground-truth',action='store_true')
    args=p.parse_args();root=args.directory;manifest=read(root/'manifest.json')
    relative=Path('outs/vlm/p_final/#out_labels')/('vlm_p_final_'+manifest['scene']+'_8class.json')
    baseline,reuse=[read(root/mode/relative) for mode in ('baseline','reuse')]
    data=Path(manifest['data_root'])/manifest['version']
    scene=next(row for row in read(data/'scene.json') if row['name']==manifest['scene'])
    expected={row['token'] for row in read(data/'sample.json') if row['scene_token']==scene['token']}
    result={'at':datetime.now(timezone.utc).isoformat(),'scene':manifest['scene'],'expected_keyframes':len(expected),
            'coverage_matches':set(baseline['results'])==set(reuse['results'])==expected,
            'output_regression':compare(baseline,reuse),'geometry_valid':True,
            'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    result['box_counts']={mode:sum(len(boxes) for boxes in payload['results'].values())
                          for mode,payload in [('baseline',baseline),('reuse',reuse)]}
    for payload in (baseline,reuse):
        for token,boxes in payload['results'].items():
            for box in boxes:
                values=box['translation']+box['size']+box['rotation']+box['velocity']
                if (box['sample_token']!=token or not all(math.isfinite(v) for v in values)
                    or not all(v>0 for v in box['size']) or abs(sum(v*v for v in box['rotation'])-1)>0.001):
                    result['geometry_valid']=False
    traces=[]
    for mode in ('baseline','reuse'):
        traces.append([{k:v for k,v in json.loads(line).items() if k!='mode'}
                       for line in (root/mode/'detector-results.jsonl').read_text().splitlines()])
    result['detector_regression']=compare(*traces)
    result['camera_calls']=[len(trace) for trace in traces]
    result['expected_camera_calls']=len(expected)*6
    result['timings']={}
    for mode in ('baseline','reuse'):
        execution=read(root/mode/'execution-summary.json');stage_rows=[json.loads(line) for line in (root/mode/'stage-events.jsonl').read_text().splitlines()]
        totals={}
        for row in stage_rows:
            if row['event']=='completed':totals[row['stage']]=totals.get(row['stage'],0)+row.get('wall_seconds',0)
        result['timings'][mode]={'execution':execution,'stage_totals_seconds':totals,
                                'failed_stages':[row for row in stage_rows if row['event']=='failed']}
    result['wall_reduction']=1-result['timings']['reuse']['execution']['wall_seconds']/result['timings']['baseline']['execution']['wall_seconds']
    if args.ground_truth:
        from nuscenes import NuScenes
        from nuscenes.eval.detection.config import config_factory
        nusc=NuScenes(version=manifest['version'],dataroot=manifest['data_root'],verbose=False)
        cfg=config_factory('detection_cvpr_2019')
        result['ground_truth']={mode:ground_truth_metrics(payload,nusc,cfg) for mode,payload in [('baseline',baseline),('reuse',reuse)]}
        result['ground_truth_regression']=compare(result['ground_truth']['baseline'],result['ground_truth']['reuse'],tolerance=1e-8)
    result['quality_passed']=(result['coverage_matches'] and result['geometry_valid']
        and result['output_regression']['within_tolerance'] and result['detector_regression']['within_tolerance']
        and all(count==len(expected)*6 for count in result['camera_calls'])
        and all(not value['failed_stages'] and value['execution']['exit_code']==0 for value in result['timings'].values())
        and result.get('ground_truth_regression',{}).get('within_tolerance',False))
    result['decision']='eligible_for_application' if result['quality_passed'] and result['wall_reduction']>0 else 'hold'
    target=root/('quality-with-gt.json' if args.ground_truth else 'quality-regression.json')
    with target.open('x',encoding='utf-8') as stream:json.dump(clean(result),stream,indent=2,allow_nan=False)
    print(json.dumps({key:result[key] for key in ('coverage_matches','box_counts','camera_calls','wall_reduction','quality_passed','decision')}))


if __name__=='__main__':main()
