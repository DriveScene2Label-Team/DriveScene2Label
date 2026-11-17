"""Run three alternating baseline/prefetch pairs through the normal upload API.

Requires the verified new backend image, an idle GPU and a prepared keyframe fixture.
Every upload creates a new dataset; existing vectors and AWS statistics are retained.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from evidence_io import save_json

ROOT=Path(__file__).resolve().parents[2]
BACKEND='drivescene-hybrid-backend-1'


def save(path,value):save_json(path,value)


def run(command,directory,label):
    save(directory/(label+'-command.json'),command)
    with (directory/(label+'.stdout.log')).open('wb') as out,(directory/(label+'.stderr.log')).open('wb') as err:
        code=subprocess.call(command,cwd=ROOT,stdout=out,stderr=err)
    save(directory/(label+'-exit.json'),{'exit_code':code})
    if code:raise RuntimeError(label+' failed; see preserved output')


def request(path):
    with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=120) as response:return json.load(response)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--fixture-manifest',type=Path,required=True)
    p.add_argument('--env-file',type=Path,required=True)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--warmup-dataset-id',type=int,required=True)
    p.add_argument('--resume',action='store_true',help='Keep completed cases; failed case is rerun in a new directory/dataset')
    a=p.parse_args()
    if a.resume:
        if not (a.directory/'manifest.json').is_file():raise ValueError('No existing experiment to resume')
        attempt=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        preparation=a.directory/('resume-'+attempt);preparation.mkdir()
        runs=json.loads((a.directory/'runs.json').read_text(encoding='utf-8'))
    else:
        a.directory.mkdir(parents=True,exist_ok=False);preparation=a.directory;runs=[]
        save(a.directory/'runs.json',runs)
    fixture=json.loads(a.fixture_manifest.read_text(encoding='utf-8'))
    base=['docker','compose','--env-file',str(a.env_file),'-f','compose.hybrid.yml','-f','compose.gpu.yml','-f','compose.hybrid-auth.yml']
    if a.resume:
        original=json.loads((a.directory/'manifest.json').read_text(encoding='utf-8'))
        if fixture['archive_sha256']!=original['fixture']['archive_sha256']:raise ValueError('Cannot resume with a different input')
        save(preparation/'manifest.json',{'resumed_at':datetime.now(timezone.utc).isoformat(),'retained_runs':runs,'fixture_sha256':fixture['archive_sha256']})
    else:save(a.directory/'manifest.json',{'started_at':datetime.now(timezone.utc).isoformat(),'fixture':fixture,
        'order':['baseline','prefetch','prefetch','baseline','baseline','prefetch'],
        'backend_force_recreated_each_case':True,
        'scope':'normal API upload/S3/import/index; compare index wall separately; same AI image throughout',
        'quality_gates':{'vector_linf':1e-5,'vector_min_cosine':0.99999,'same_scene_order':True,'score_linf':1e-5}})
    run([sys.executable,'scripts/hybrid/operations.py','status','--env-file',str(a.env_file)],preparation,'warmup-preflight')
    initial=json.loads((preparation/'warmup-preflight.stdout.log').read_text(encoding='utf-8-sig'))
    if any(initial[k] for k in ('activeWrites','runningLabels','runningRecordings')):raise RuntimeError('Existing work is active')
    for dataset in request('/api/datasets'):
        if dataset['storageKey']=='uploads' and request(f'/api/datasets/{dataset["id"]}/search-index')['status'] in ('RUNNING','PENDING'):
            raise RuntimeError('An uploaded dataset index is active or pending')
    warm_begin=subprocess.run([sys.executable,'scripts/hybrid/measurement.py','begin'],cwd=ROOT,capture_output=True,text=True,check=True)
    warm_directory=(ROOT/warm_begin.stdout.strip()).resolve()
    save(warm_directory/'test-conditions.json',{'experiment':'CLIP six-image warmup','dataset':a.warmup_dataset_id,'outside_trial_timing':True})
    save(preparation/'warmup-evidence.json',{'directory':str(warm_directory)})
    run([sys.executable,'scripts/hybrid/warm_clip.py','--dataset-id',str(a.warmup_dataset_id),'--output',str(warm_directory/'warmup.json')],warm_directory,'warmup')
    (warm_directory/'STOP').touch()
    run([sys.executable,'scripts/hybrid/measurement.py','collect','--directory',str(warm_directory)],warm_directory,'collect')
    for repeat in range(3):
        for mode in (['baseline','prefetch'] if repeat%2==0 else ['prefetch','baseline']):
            if any(row['repeat']==repeat and row['mode']==mode for row in runs):continue
            case=a.directory/(str(repeat)+'-'+mode)
            if case.exists():
                if not a.resume:raise ValueError('Case already exists')
                case=case.with_name(case.name+'-retry-'+attempt)
            case.mkdir()
            run([sys.executable,'scripts/hybrid/operations.py','status','--env-file',str(a.env_file)],case,'preflight')
            status=json.loads((case/'preflight.stdout.log').read_text(encoding='utf-8-sig'))
            if any(status[key] for key in ('activeWrites','runningLabels','runningRecordings')):raise RuntimeError('Existing work is active')
            overlay=case/'compose.case.yml'
            overlay.write_text('services:\n  backend:\n    environment:\n      EMBEDDING_INDEX_PREFETCH_ENABLED: "'+('true' if mode=='prefetch' else 'false')+'"\n',encoding='utf-8')
            run(base+['-f',str(overlay),'up','-d','--no-build','--no-deps','--force-recreate','backend'],case,'apply-mode')
            deadline=time.monotonic()+180
            while True:
                try:request('/api/datasets');break
                except Exception:
                    if time.monotonic()>deadline:raise
                    time.sleep(2)
            run([sys.executable,'scripts/hybrid/operations.py','resume','--env-file',str(a.env_file)],case,'resume')
            begin=subprocess.run([sys.executable,'scripts/hybrid/measurement.py','begin'],cwd=ROOT,capture_output=True,text=True,check=True)
            directory=(ROOT/begin.stdout.strip()).resolve()
            save(directory/'test-conditions.json',{'experiment':'CLIP DB '+mode,'mode':mode,'repeat':repeat,
                'expected_images':fixture['keyframe_cameras'],'archive_sha256':fixture['archive_sha256'],
                'upload_origin':'http://127.0.0.1:8080','cache':'new dataset cache, persistent already-loaded CLIP; backend recreated for every condition',
                'concurrency':'resource/log collection only; no other assistant model/build/upload job',
                'other_user_work':'not independently verified'})
            # Image digests, not environment variables or credentials.
            run(['docker','inspect','--format','{{.Image}}',BACKEND,'drivescene-hybrid-ai-server-1'],directory,'images')
            run(['docker','inspect','--format','{"id":"{{.Id}}","started_at":"{{.State.StartedAt}}","image":"{{.Image}}"}',
                 BACKEND,'drivescene-hybrid-ai-server-1'],directory,'instances')
            # Optional server counters are sampled without resetting shared RDS statistics.
            before='/tmp/index-experiment-before-'+directory.name+'.json'
            run(['docker','exec',BACKEND,'java','-Dloader.main=com.example.demo.nuscenes.benchmark.IndexExperimentSnapshot',
                '-cp','/app/app.jar','org.springframework.boot.loader.launch.PropertiesLauncher','0',before,'--stats-only'],directory,'db-before')
            run(['docker','cp',BACKEND+':'+before,str(directory/'db-before.json')],directory,'copy-db-before')
            handles=[];collectors=[]
            try:
                for name,command in [('collector',[sys.executable,'scripts/hybrid/measurement.py','watch','--directory',str(directory)]),
                    ('resources',[sys.executable,'scripts/hybrid/sample_resources.py','--directory',str(directory)])]:
                    out=(directory/(name+'.stdout.log')).open('wb');err=(directory/(name+'.stderr.log')).open('wb');handles += [out,err]
                    collectors.append(subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err))
                print(json.dumps({'event':'case_started','repeat':repeat,'mode':mode,'directory':str(directory)}),flush=True)
                run([sys.executable,'scripts/hybrid/benchmark_clip.py','--directory',str(directory),'--archive',str(a.archive)],directory,'upload-client')
            finally:
                (directory/'STOP').touch()
                for process in collectors:process.wait(timeout=100)
                for handle in handles:handle.close()
                run([sys.executable,'scripts/hybrid/measurement.py','collect','--directory',str(directory)],directory,'final-collect')
            client=json.loads((directory/'client-report.json').read_text());dataset=client['dataset_id']
            if client['status']!='completed' or client['index_status']['indexedImages']!=fixture['keyframe_cameras']:
                raise RuntimeError('Incomplete index')
            remote='/tmp/index-experiment-'+str(dataset)+'.json'
            run(['docker','exec',BACKEND,'java','-Dloader.main=com.example.demo.nuscenes.benchmark.IndexExperimentSnapshot',
                '-cp','/app/app.jar','org.springframework.boot.loader.launch.PropertiesLauncher',str(dataset),remote],directory,'vector-snapshot')
            run(['docker','cp',BACKEND+':'+remote,str(directory/'vectors.json')],directory,'copy-vectors')
            query_begin=subprocess.run([sys.executable,'scripts/hybrid/measurement.py','begin'],cwd=ROOT,capture_output=True,text=True,check=True)
            query_directory=(ROOT/query_begin.stdout.strip()).resolve()
            save(query_directory/'test-conditions.json',{'experiment':'search ranking regression','parent_index_run':str(directory),'dataset':dataset,'mode':mode,'repeat':repeat,'scope':'six queries times three aggregation modes; outside index timing'})
            save(directory/'query-evidence.json',{'directory':str(query_directory)})
            ranks=[]
            for query in ('a red car','pedestrians crossing the street','a bus at an intersection','a bicycle','traffic cones','night driving'):
                for aggregation in ('MAX','AVERAGE','TOP_K_AVERAGE'):
                    parameters={'q':query,'aggregation':aggregation,'k':10,'imageTopK':3}
                    response=request('/api/search/scenes?'+urllib.parse.urlencode({**parameters,'datasetId':dataset}))
                    ranks.append({'parameters':parameters,'response':response})
                    save(directory/'rankings.json',ranks)
            (query_directory/'STOP').touch()
            run([sys.executable,'scripts/hybrid/measurement.py','collect','--directory',str(query_directory)],query_directory,'final-collect')
            runs.append({'repeat':repeat,'mode':mode,'directory':str(directory),'dataset':dataset});save(a.directory/'runs.json',runs)
            print(json.dumps({'event':'case_completed',**runs[-1]}),flush=True)
    run([sys.executable,'scripts/hybrid/compare_index_cases.py','--directory',str(a.directory)],a.directory,'compare')
    comparison=json.loads((a.directory/'comparison.json').read_text())
    print(json.dumps({key:value for key,value in comparison.items() if key!='pairs'}),flush=True)


if __name__=='__main__':main()
