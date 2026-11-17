"""Exercise normal label-job/RDS-results/3D-recording APIs on one uploaded scene.

Idempotency key and job ID are saved before polling, so rerunning the same command
resumes an existing job. No existing labels are edited or removed. Original model
artifact is copied for a separate complete RDS round-trip comparison.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import time
import urllib.request
from evidence_io import save_json

ORIGIN='http://127.0.0.1:8080'


def save(path,value):
    save_json(path,value)


def request(path,body=None,key=None):
    headers={'Content-Type':'application/json'}
    if key:headers['Idempotency-Key']=key
    req=urllib.request.Request(ORIGIN+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
    with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)


def wait_for(path,finished,directory,label,timeout):
    deadline=time.monotonic()+timeout;previous=None
    while True:
        row=request(path);save(directory/(label+'-status.json'),row)
        if row['status']!=previous:
            event={'at':datetime.now(timezone.utc).isoformat(),'event':label,'status':row['status']}
            with (directory/'cycle-events.jsonl').open('a',encoding='utf-8') as output:output.write(json.dumps(event)+'\n')
            print(json.dumps(event),flush=True);previous=row['status']
        if row['status']==finished:return row
        if row['status']=='FAILED':raise RuntimeError(label+' failed; inspect saved status')
        if time.monotonic()>deadline:raise TimeoutError(label+' still incomplete; resume polling same job later')
        time.sleep(15)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--dataset-id',type=int,required=True)
    a=p.parse_args()
    if not (a.directory/'manifest.json').is_file():raise ValueError('Begin a measurement first')
    scenes=request(f'/api/datasets/{a.dataset_id}/scenes')
    scene=next(row for row in scenes if row['name']=='scene-0061')
    samples=request(f'/api/scenes/{scene["id"]}/samples?limit=500')
    save(a.directory/'target-scene.json',{'scene':scene,'samples':samples})
    jobfile=a.directory/'created-job.json'
    if jobfile.exists():job=json.loads(jobfile.read_text(encoding='utf-8'))
    else:
        body={'datasetId':a.dataset_id,'sceneToken':scene['token'],'classMode':8}
        key='full-cycle-'+a.directory.name+'-'+str(a.dataset_id)
        save(a.directory/'create-job-request.json',{'body':body,'idempotency_key':key})
        job=request('/api/auto-label/jobs',body=body,key=key);save(jobfile,job)
    jobid=job['jobId'];wait_for(f'/api/auto-label/jobs/{jobid}','COMPLETED',a.directory,'label',8000)
    results=request(f'/api/auto-label/jobs/{jobid}/results');save(a.directory/'rds-results.json',results)
    if set(results['sampleTokens'])!={row['token'] for row in samples}:raise RuntimeError('RDS result sample coverage mismatch')
    artifact=next(row for row in results['artifacts'] if row['artifactType']=='FINAL_JSON')
    relative=PurePosixPath(artifact['relativePath'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unexpected artifact path')
    copied=subprocess.run(['docker','cp','drivescene-hybrid-ai-server-1:/results/'+str(relative),str(a.directory/'model-result.json')],capture_output=True,text=True)
    save(a.directory/'copy-artifact-execution.json',{'exit_code':copied.returncode,'stdout':copied.stdout,'stderr':copied.stderr})
    if copied.returncode:raise RuntimeError('Could not preserve original model artifact')
    recordingfile=a.directory/'created-recording.json'
    if recordingfile.exists():created=json.loads(recordingfile.read_text(encoding='utf-8'))
    else:
        created=request(f'/api/scenes/{scene["id"]}/recordings',body={'jobId':jobid});save(recordingfile,created)
    recording=wait_for(f'/api/recordings/{created["recordingId"]}','READY',a.directory,'recording',900)
    if set(row['sampleToken'] for row in recording['samples'])!=set(results['sampleTokens']):raise RuntimeError('Recording sample coverage mismatch')
    predictionids=[i for row in recording['samples'] for i in row['predictionIds']]
    if len(predictionids)!=len(set(predictionids)) or set(predictionids)!={box['id'] for box in results['boxes']}:raise RuntimeError('Recording prediction coverage mismatch')
    started=time.monotonic();digest=hashlib.sha256();size=0;header=b''
    with urllib.request.urlopen(ORIGIN+recording['contentUrl'],timeout=120) as response:
        while block:=response.read(1024*1024):
            if not header:header=block[:12]
            digest.update(block);size+=len(block)
    download={'bytes':size,'sha256':digest.hexdigest(),'first_12_bytes_hex':header.hex(),'wall_seconds':time.monotonic()-started,
              'size_matches':size==recording['sizeBytes'],'url':recording['contentUrl']}
    save(a.directory/'recording-download.json',download)
    req=urllib.request.Request(ORIGIN+recording['contentUrl'],headers={'Range':'bytes=0-11'})
    with urllib.request.urlopen(req,timeout=120) as response:
        rangepassed=response.status==206 and response.read()==header
    download['range_request_passed']=rangepassed;save(a.directory/'recording-download.json',download)
    if not download['size_matches'] or not rangepassed:raise RuntimeError('Recording full/range download mismatch')
    save(a.directory/'cycle-completed.json',{'at':datetime.now(timezone.utc).isoformat(),'dataset':a.dataset_id,'job':jobid,
        'recording':created['recordingId'],'keyframes':len(samples),'boxes':len(results['boxes']),
        'scope':'normal APIs through local backend to existing RDS; GPU inference and recording generation on local GPU host',
        'recording_binary_downloaded_and_range_checked':True,'browser_render_visual_check':False})
    print(json.dumps({'event':'cycle_completed','job':jobid,'recording':created['recordingId'],'boxes':len(results['boxes'])}),flush=True)


if __name__=='__main__':main()
