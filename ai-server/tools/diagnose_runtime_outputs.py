"""Separate raw query-slot drift from thresholded box drift after a static export.

This is a one-prompt diagnostic, not AP, full pipeline accuracy or a timing run.
"""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--provider',choices=('cuda','cpu'),required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to('/results/experiments'):raise ValueError('Use experiment output root')
    a.output.mkdir(parents=True,exist_ok=False)
    import torch
    import numpy as np
    import onnxruntime as ort
    torch.set_num_threads(1)
    options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
    providers=[('CUDAExecutionProvider',{'use_tf32':0,'gpu_mem_limit':4*1024**3}),'CPUExecutionProvider'] if a.provider=='cuda' else ['CPUExecutionProvider']
    session=ort.InferenceSession(str(a.reference/'model.onnx'),sess_options=options,providers=providers)
    if a.provider=='cuda' and 'CUDAExecutionProvider' not in session.get_providers():raise RuntimeError('CUDA provider unavailable')
    session.disable_fallback();names={v.name for v in session.get_inputs()}
    inputs=dict(np.load(a.reference/'inputs.npz'))
    result=session.run(None,{k:v for k,v in inputs.items() if k in names})
    actual=dict(zip([v.name for v in session.get_outputs()],result));reference=dict(np.load(a.reference/'reference.npz'))
    np.savez(a.output/'ort-output.npz',**actual)
    def boxes(value):
        scores=1/(1+np.exp(-np.clip(value['logits'][0].max(axis=-1),-80,80)))
        rows=[]
        for score,box in zip(scores,value['pred_boxes'][0]):
            if score>.3:
                x,y,w,h=map(float,box)
                rows.append({'score':float(score),'xyxy':[x-w/2,y-h/2,x+w/2,y+h/2]})
        return sorted(rows,key=lambda r:r['score'],reverse=True)
    def iou(a,b):
        intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
        area=lambda v:max(0,v[2]-v[0])*max(0,v[3]-v[1])
        return intersection/(area(a)+area(b)-intersection) if intersection else 0.
    left,right=boxes(reference),boxes(actual);remaining=set(range(len(right)));matches=[];missing=0
    for box in left:
        overlap,index=max(((iou(box['xyxy'],right[i]['xyxy']),i) for i in remaining),default=(0,None))
        if overlap<.5:missing+=1;continue
        remaining.remove(index);matches.append({'iou':overlap,'score_absolute_difference':abs(box['score']-right[index]['score'])})
    summary={'scope':'one fixed image/car. prompt; threshold score>0.3; greedy IoU>=0.5; no text decoder/NMS/AP/full-scene claim',
        'reference':str(a.reference),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'providers':session.get_providers(),'requested_provider':a.provider,
        'raw_slot_parity':{key:bool(np.allclose(reference[key],actual[key],rtol=1e-4,atol=1e-5,equal_nan=False)) for key in reference},
        'reference_count':len(left),'candidate_count':len(right),
        'matched':len(matches),'missing':missing,'extra':len(remaining),
        'minimum_matched_iou':min((v['iou'] for v in matches),default=None),
        'maximum_matched_score_difference':max((v['score_absolute_difference'] for v in matches),default=None),
        'reference_boxes':left,'candidate_boxes':right,
        'interpretation':'raw query slot mismatch alone does not establish detection AP regression; preserve both comparisons; production unchanged'}
    (a.output/'diagnostic.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('reference_boxes','candidate_boxes')}),flush=True)


if __name__=='__main__':main()
