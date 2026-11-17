"""Warm six image requests in the live AI process without writing embeddings to RDS."""
import argparse
import json
from pathlib import Path
import subprocess
import urllib.request

GUEST=r'''
import hashlib,json,sys,time,urllib.request
requests=json.loads(sys.argv[1]);rows=[]
for body in requests:
 started=time.monotonic()
 req=urllib.request.Request('http://127.0.0.1:8000/embedding/image',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=120) as response:output=json.load(response)
 rows.append({'image_path':body['image_path'],'wall_seconds':time.monotonic()-started,'model_name':output['model_name'],
  'dimension':output['dimension'],'preprocess':output['preprocess'],
  'vector_sha256':hashlib.sha256(json.dumps(output['embedding'],separators=(',',':')).encode()).hexdigest()})
print(json.dumps(rows))
'''


def request(path):
    with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=30) as response:return json.load(response)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset-id',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Preserve old warmup evidence')
    dataset=next(d for d in request('/api/datasets') if d['id']==a.dataset_id)
    if dataset['storageKey']!='uploads':raise ValueError('Expected uploaded dataset')
    scene=next(d for d in request(f'/api/datasets/{a.dataset_id}/scenes') if d['name']=='scene-0061')
    sample=request(f'/api/scenes/{scene["id"]}/samples?limit=1')[0]
    assets=request(f'/api/samples/{sample["id"]}')['sensorFiles']
    bodies=[{'image_path':d['relativePath'],'preprocess':'lr-square-crop-mean','dataset_key':dataset['rootRelativePath']} for d in assets if d['modality']=='camera']
    if len(bodies)!=6:raise ValueError('Expected six camera views')
    result=subprocess.run(['docker','exec','drivescene-hybrid-ai-server-1','python','-c',GUEST,json.dumps(bodies)],capture_output=True,text=True,timeout=800)
    if result.returncode:
        a.output.with_suffix('.failure.json').write_text(json.dumps({'exit_code':result.returncode,'stderr':result.stderr},indent=2),encoding='utf-8')
        raise RuntimeError('CLIP warmup failed')
    observations=json.loads(result.stdout)
    a.output.write_text(json.dumps({'scope':'six normal AI image requests, no DB embedding writes; outside index timing','observations':observations},indent=2),encoding='utf-8')
    print('CLIP warmup completed: six image requests.')


if __name__=='__main__':main()
