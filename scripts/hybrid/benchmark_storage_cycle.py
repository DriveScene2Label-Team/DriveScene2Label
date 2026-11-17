"""Measure real API reads from warm files, local archive, and S3-only recovery.

Only the explicitly selected uploaded dataset's cache is renamed. Original files
are retained under /uploads/experiment-backups. RDS rows and S3 objects are never
deleted. On failure, missing cache paths are restored from the retained backup.
Run against a fresh experiment dataset after all GPU/index jobs have completed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request

from operations import read_values
from evidence_io import save_json

BACKEND='drivescene-hybrid-backend-1'
AI='drivescene-hybrid-ai-server-1'
ORIGIN='http://127.0.0.1:8080'

# Arguments are passed as separate argv entries, never interpolated into shell code.
# All source/destination paths are validated before either rename. No deletion.
MOVE=r'''
set -eu
key="$1"; case_name="$2"; archive_mode="$3"; action="$4"
root=/uploads
target="$root/datasets/$key"
archive="$root/archives/$key.tar.gz"
backup="$root/experiment-backups/$case_name"
test "$(readlink -f "$root")" = "$root"
test "$(readlink -f "$root/datasets")" = "$root/datasets"
test "$(readlink -f "$root/archives")" = "$root/archives"
if test "$action" = move; then
  test -d "$target"; test ! -L "$target"
  test "$(readlink -f "$target")" = "$target"
  test -f "$archive"; test ! -L "$archive"
  test "$(readlink -f "$archive")" = "$archive"
  test ! -e "$backup"
  mkdir -p "$root/experiment-backups"
  test "$(readlink -f "$root/experiment-backups")" = "$root/experiment-backups"
  mkdir "$backup"
  mv -- "$target" "$backup/dataset"
  if test "$archive_mode" = archive; then mv -- "$archive" "$backup/archive.tgz"; fi
else
  test "$(readlink -f "$backup")" = "$backup"
  if test ! -e "$target" && test -d "$backup/dataset"; then mv -- "$backup/dataset" "$target"; fi
  if test ! -e "$archive" && test -f "$backup/archive.tgz"; then mv -- "$backup/archive.tgz" "$archive"; fi
fi
printf 'cache action completed\n'
'''

AUDIT=r'''
import hashlib,json,pathlib,sys
key=sys.argv[1]; root=pathlib.Path('/uploads/datasets')/key
archive=pathlib.Path('/uploads/archives')/(key+'.tar.gz')
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
files=[p for p in root.rglob('*') if p.is_file()]
metadata={p.name:digest(p) for p in (root/'v1.0-mini').glob('*.json')}
print(json.dumps({'archive_sha256':digest(archive),'archive_bytes':archive.stat().st_size,
 'files':len(files),'expanded_bytes':sum(p.stat().st_size for p in files),'metadata_sha256':metadata}))
'''


def save(path,value):
    save_json(path,value)


def request(path,body=None,token=None):
    headers={}
    if token:headers['X-Operations-Token']=token
    if body is not None:headers['Content-Type']='application/json'
    req=urllib.request.Request(ORIGIN+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
    with urllib.request.urlopen(req,timeout=1200) as response:return json.load(response)


def safe_identifiers(key,case):
    if not re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',key):raise ValueError('Invalid dataset key')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',case):raise ValueError('Invalid experiment case')


def move_cache(key,case,archive,action,directory):
    safe_identifiers(key,case)
    command=['docker','exec',BACKEND,'sh','-c',MOVE,'experiment',key,case,'archive' if archive else 'files',action]
    save(directory/(case+'-'+action+'-command.json'),command)
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    save(directory/(case+'-'+action+'-execution.json'),{'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    if result.returncode:raise RuntimeError('Cache rename/restore failed; inspect preserved execution log')


def fetch(path):
    started=time.monotonic();digest=hashlib.sha256();size=0
    with urllib.request.urlopen(ORIGIN+path,timeout=1200) as response:
        status=response.status
        while block:=response.read(1024*1024):digest.update(block);size+=len(block)
    return {'path':path,'http_status':status,'bytes':size,'sha256':digest.hexdigest(),'wall_seconds':time.monotonic()-started}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--dataset-id',type=int,required=True)
    p.add_argument('--expected-archive-sha256',required=True)
    p.add_argument('--env-file',type=Path,required=True)
    a=p.parse_args()
    if not (a.directory/'manifest.json').is_file():raise ValueError('Begin a measurement first')
    target=a.directory/'storage-cycle.json'
    if target.exists():raise ValueError('Use a new evidence directory')
    token=read_values(a.env_file)['OPERATIONS_TOKEN']
    state=request('/internal/operations',token=token)
    if state['maintenance'] or any(state[k] for k in ('activeWrites','runningLabels','runningRecordings')):raise RuntimeError('Backend must be idle and resumed')
    dataset=next(d for d in request('/api/datasets') if d['id']==a.dataset_id)
    if dataset['storageKey']!='uploads' or dataset['version']!='v1.0-mini':raise ValueError('Expected a mini upload dataset')
    index=request(f'/api/datasets/{a.dataset_id}/search-index')
    if index['status']!='COMPLETED':raise RuntimeError('Index must be complete')
    key=dataset['rootRelativePath'];safe_identifiers(key,a.directory.name+'-archive')
    scenes=request(f'/api/datasets/{a.dataset_id}/scenes')
    scene=next(row for row in scenes if row['name']=='scene-0061')
    samples=request(f'/api/scenes/{scene["id"]}/samples?limit=500')
    detail=request(f'/api/samples/{samples[0]["id"]}')
    assets=detail['sensorFiles']+detail['maps']
    routes=list(dict.fromkeys(row['contentUrl'] for row in assets))
    report={'started_at':datetime.now(timezone.utc).isoformat(),'origin':ORIGIN,'dataset':dataset,'scene':scene,
        'keyframes':len(samples),'stats_before':request(f'/api/datasets/{a.dataset_id}/stats'),
        'scope':'normal API; first keyframe all sensor modalities and maps; archive SHA256 and full extracted file inventory',
        'backups_retained':True,'cases':[],'status':'running'}
    save(target,report)
    state=request('/internal/operations/quiesce',body={},token=token)
    backups=[]
    try:
        if any(state[k] for k in ('activeWrites','runningLabels','runningRecordings')):raise RuntimeError('Work became active; no caches moved')
        reference=None;inventory=None
        for name,archive in [('warm',False),('archive-only',False),('s3-cold',True)]:
            label=a.directory.name+'-'+name
            if name!='warm':
                backups.append((label,archive))
                move_cache(key,label,archive,'move',a.directory)
            case_started=datetime.now(timezone.utc).isoformat()
            started=time.monotonic();reads=[fetch(route) for route in routes];elapsed=time.monotonic()-started
            hashes=[(row['path'],row['bytes'],row['sha256']) for row in reads]
            audit_command=['docker','exec',AI,'python','-c',AUDIT,key]
            save(a.directory/(label+'-audit-command.json'),audit_command)
            audited=subprocess.run(audit_command,capture_output=True,encoding='utf-8',timeout=300)
            save(a.directory/(label+'-audit-execution.json'),{'exit_code':audited.returncode,'stderr':audited.stderr})
            if audited.returncode:raise RuntimeError('Cache audit failed; inspect audit-execution.json')
            audit=json.loads(audited.stdout)
            if reference is None:reference=hashes;inventory=audit
            case={'mode':name,'started_at':case_started,'read_seconds':elapsed,
                'first_read_seconds':reads[0]['wall_seconds'],'reads':reads,'audit':audit,
                'files_match_warm':hashes==reference,'archive_matches_original':audit['archive_sha256'].lower()==a.expected_archive_sha256.lower(),
                'inventory_matches_warm':audit==inventory}
            report['cases'].append(case);save(target,report)
            print(json.dumps({'event':'storage_case_completed','mode':name,'read_seconds':elapsed,
                'quality_passed':case['files_match_warm'] and case['archive_matches_original'] and case['inventory_matches_warm']}),flush=True)
            if not all(case[k] for k in ('files_match_warm','archive_matches_original','inventory_matches_warm')):raise RuntimeError('Restored file integrity mismatch')
        report['stats_after']=request(f'/api/datasets/{a.dataset_id}/stats')
        report['status']='completed' if report['stats_before']==report['stats_after'] else 'failed'
        if report['status']!='completed':raise RuntimeError('Dataset catalog changed during cache recovery')
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__)
        raise
    finally:
        # Restore only paths missing after a failed request; never overwrite generated data.
        for label,archive in reversed(backups):
            try:move_cache(key,label,archive,'restore',a.directory)
            except Exception as error:report.setdefault('recovery_errors',[]).append(type(error).__name__)
        report['maintenance_after']=request('/internal/operations/resume',body={},token=token)
        report['finished_at']=datetime.now(timezone.utc).isoformat();save(target,report)


if __name__=='__main__':main()
