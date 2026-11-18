"""Read-only Docker resource observations for an existing labelled S3 experiment.

Stop when the controller records finished_at. No environment, headers, credentials
or production containers are inspected. Samples are partial if started mid-run;
the Java result separately records peak JVM heap/RSS over each whole transfer.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
    with (a.directory/'docker-resources.jsonl').open('x',encoding='utf-8') as stream:
        while True:
            manifest=json.loads((a.directory/'manifest.json').read_text(encoding='utf-8'))
            if 'finished_at' in manifest:return
            if manifest['cases']:
                case=manifest['cases'][-1]
                owner=subprocess.run(['docker','inspect','--format','{{index .Config.Labels "ds2l.s3-experiment"}}',case['container']],capture_output=True,text=True,encoding='utf-8')
                if owner.returncode==0 and owner.stdout.strip()==case['uuid']:
                    result=subprocess.run(['docker','stats','--no-stream','--format',
                        '{{json .}}',case['container']],capture_output=True,text=True,encoding='utf-8')
                    if result.returncode==0 and result.stdout.strip():
                        raw=json.loads(result.stdout)
                        row={'utc':datetime.now(timezone.utc).isoformat(),'case':case['label'],
                             **{k:raw[k] for k in ('CPUPerc','MemUsage','MemPerc','NetIO','BlockIO','PIDs') if k in raw}}
                        stream.write(json.dumps(row)+'\n');stream.flush()
            time.sleep(15)


if __name__=='__main__':main()
