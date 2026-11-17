"""Record one authorized experiment command with stage/resource logs and fresh evidence.

Use the exact argv token {directory} where the command needs its evidence folder.
Commands must not contain credentials; use protected file paths or existing profiles.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from evidence_io import save_json

ROOT=Path(__file__).resolve().parents[2]


def save(path,value):save_json(path,value)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment',required=True);p.add_argument('--conditions',type=Path)
    p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
    command=a.command[1:] if a.command and a.command[0]=='--' else a.command
    if not command:raise ValueError('Specify an experiment command')
    began=subprocess.run([sys.executable,'scripts/hybrid/measurement.py','begin'],cwd=ROOT,capture_output=True,text=True,check=True)
    directory=(ROOT/began.stdout.strip()).resolve()
    command=[str(directory) if value=='{directory}' else value for value in command]
    conditions=json.loads(a.conditions.read_text(encoding='utf-8-sig')) if a.conditions else {}
    save(directory/'test-conditions.json',{'experiment':a.experiment,'upload_origin':'http://127.0.0.1:8080',
         'other_user_work':'not independently verified','assistant_work':'resource/log collection and source/document editing only; no concurrent model/build/upload',**conditions})
    save(directory/'command.json',command)
    sources={}
    for argument in command:
        candidate=Path(argument)
        if candidate.suffix=='.py' and candidate.is_file():sources[str(candidate)]=hashlib.sha256(candidate.read_bytes()).hexdigest()
    save(directory/'command-source-sha256.json',sources)
    with (directory/'images.stdout.log').open('wb') as out:
        subprocess.run(['docker','inspect','--format','{{.Image}}','drivescene-hybrid-backend-1','drivescene-hybrid-ai-server-1'],stdout=out,check=True)
    processes=[];handles=[];summary={'started_at':datetime.now(timezone.utc).isoformat(),'directory':str(directory),'command':command}
    started=time.monotonic();code=1
    try:
        for name,args in [('collector',['scripts/hybrid/measurement.py','watch','--directory',str(directory)]),
                          ('resources',['scripts/hybrid/sample_resources.py','--directory',str(directory)])]:
            out=(directory/(name+'.stdout.log')).open('wb');err=(directory/(name+'.stderr.log')).open('wb');handles.extend([out,err])
            process=subprocess.Popen([sys.executable,*args],cwd=ROOT,stdout=out,stderr=err);processes.append(process)
        save(directory/'collector-pids.json',[process.pid for process in processes])
        print(json.dumps({'event':'measurement_started','experiment':a.experiment,'directory':str(directory)}),flush=True)
        with (directory/'action.stdout.log').open('wb') as out,(directory/'action.stderr.log').open('wb') as err:
            code=subprocess.call(command,cwd=ROOT,stdout=out,stderr=err)
        summary.update(exit_code=code,command_wall_seconds=time.monotonic()-started,finished_at=datetime.now(timezone.utc).isoformat())
    finally:
        (directory/'STOP').touch()
        for process in processes:
            try:process.wait(timeout=100)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=15);summary.setdefault('collector_errors',[]).append('cooperative stop timed out')
        for handle in handles:handle.close()
        with (directory/'final-collect.stdout.log').open('wb') as out,(directory/'final-collect.stderr.log').open('wb') as err:
            collected=subprocess.call([sys.executable,'scripts/hybrid/measurement.py','collect','--directory',str(directory)],cwd=ROOT,stdout=out,stderr=err)
        summary['final_collect_exit_code']=collected
        save(directory/'execution-summary.json',summary)
        print(json.dumps({'event':'measurement_finished','directory':str(directory),'exit_code':code,'final_collect_exit_code':collected}),flush=True)
    raise SystemExit(code or collected or bool(summary.get('collector_errors')))


if __name__=='__main__':main()
