"""Freeze allowlisted stage logs BEFORE removing/recreating a container.

Independent snapshot files avoid racing the active measurement watcher's cursor.
Reads retained Docker logs without --since and filters timestamps locally. It
does not stop/restart services, alter a job, or claim recovery of rotated logs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from measurement import CONTAINERS, timed_rows

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--since',required=True,help='UTC ISO timestamp including timezone')
    a=p.parse_args()
    since=datetime.fromisoformat(a.since.replace('Z','+00:00'))
    if since.tzinfo is None:raise ValueError('An explicit timezone is required')
    directory=a.directory.resolve()
    if not directory.is_relative_to(ROOT/'.local/hybrid'):raise ValueError('Snapshot must stay under .local/hybrid')
    directory.mkdir(parents=True,exist_ok=False)
    manifest={'started_at':datetime.now(timezone.utc).isoformat(),'since':since.isoformat(),
              'scope':'retained allowlisted logs only; no job or service mutation; independent from watch cursor','services':[]}
    for service,container in CONTAINERS.items():
        try:
            result=subprocess.run(['docker','logs','--timestamps',container],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
        except (subprocess.TimeoutExpired, OSError) as error:
            manifest['services'].append({'service':service,'container':container,'exit_code':None,'error':type(error).__name__})
            continue
        row={'service':service,'container':container,'exit_code':result.returncode}
        if result.returncode==0:
            events=timed_rows(result.stdout+'\n'+result.stderr,since.isoformat())
            target=directory/(service+'-events.jsonl')
            with target.open('x',encoding='utf-8',newline='\n') as stream:
                for event in events:
                    event['service']=service;stream.write(json.dumps(event,ensure_ascii=False)+'\n')
            row.update(events=len(events),sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        manifest['services'].append(row)
    manifest['finished_at']=datetime.now(timezone.utc).isoformat()
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest))
    if any(row['exit_code'] != 0 for row in manifest['services']):raise RuntimeError('Snapshot incomplete; do not recreate containers yet')


if __name__=='__main__':main()
