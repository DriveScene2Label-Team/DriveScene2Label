"""Compare all stored vectors and scene searches for two identical full uploads.

Read-only: historical baseline is a quality reference, never a controlled timing
baseline. Fresh upload/index wall comparisons belong to the paired C1 experiment.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request

from compare_index_cases import vectors_match,rankings_match
from evidence_io import save_json


def request(path):
    with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=120) as response:return json.load(response)


def save(path,value):save_json(path,value)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--baseline-dataset-id',type=int,required=True);p.add_argument('--candidate-dataset-id',type=int,required=True)
    a=p.parse_args();datasets={d['id']:d for d in request('/api/datasets')};vectors=[];rankings=[];stats=[]
    for name,identifier in [('baseline',a.baseline_dataset_id),('candidate',a.candidate_dataset_id)]:
        save(a.directory/(name+'-dataset.json'),datasets[identifier])
        index=request(f'/api/datasets/{identifier}/search-index');save(a.directory/(name+'-index.json'),index)
        if index['status']!='COMPLETED' or index['totalImages']!=2424 or index['indexedImages']!=2424:raise RuntimeError('Expected completed full mini index of 2424 images')
        counts=request(f'/api/datasets/{identifier}/stats');stats.append(counts);save(a.directory/(name+'-catalog.json'),counts)
        remote='/tmp/full-index-quality-'+a.directory.name+'-'+name+'.json'
        command=['docker','exec','drivescene-hybrid-backend-1','java','-Dloader.main=com.example.demo.nuscenes.benchmark.IndexExperimentSnapshot',
                 '-cp','/app/app.jar','org.springframework.boot.loader.launch.PropertiesLauncher',str(identifier),remote]
        save(a.directory/(name+'-snapshot-command.json'),command)
        with (a.directory/(name+'-snapshot.stdout.log')).open('wb') as out,(a.directory/(name+'-snapshot.stderr.log')).open('wb') as err:
            subprocess.run(command,stdout=out,stderr=err,check=True)
        target=a.directory/(name+'-vectors.json')
        subprocess.run(['docker','cp','drivescene-hybrid-backend-1:'+remote,str(target)],check=True,capture_output=True)
        vector=json.loads(target.read_text(encoding='utf-8'));vectors.append(vector)
        if len(vector['vectors'])!=2424:raise RuntimeError('Readback omitted vectors')
        rows=[]
        for query in ('a red car','pedestrians crossing the street','a bus at an intersection','a bicycle','traffic cones','night driving'):
            for aggregation in ('MAX','AVERAGE','TOP_K_AVERAGE'):
                parameters={'q':query,'aggregation':aggregation,'k':10,'imageTopK':3};started=time.monotonic()
                response=request('/api/search/scenes?'+urllib.parse.urlencode({**parameters,'datasetId':identifier}))
                rows.append({'parameters':parameters,'response':response,'wall_seconds':time.monotonic()-started})
                save(a.directory/(name+'-rankings.json'),rows)
        rankings.append(rows)
    baseline,candidate=datasets[a.baseline_dataset_id],datasets[a.candidate_dataset_id]
    result={'scope':'full mini quality regression only; historical reference is not a controlled timing baseline',
        'datasets':[a.baseline_dataset_id,a.candidate_dataset_id],'same_metadata_checksum':baseline['sourceChecksum']==candidate['sourceChecksum'],
        'same_version':baseline['version']==candidate['version'],'same_catalog':stats[0]==stats[1],
        'vectors':vectors_match(*vectors),'rankings':rankings_match(*rankings)}
    result['passed']=(result['same_metadata_checksum'] and result['same_version'] and result['same_catalog']
                      and result['vectors']['passed'] and result['rankings']['passed'])
    save(a.directory/'full-index-quality.json',result);print(json.dumps(result),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
