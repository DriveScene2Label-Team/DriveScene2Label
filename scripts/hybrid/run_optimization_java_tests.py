"""Run CLIP regression tests in an isolated Linux workspace and temporary pgvector DB.

Uses synthetic AI responses. No AWS credentials, RDS URL, production volume, GPU,
or host listening port is passed into the test containers. Run after benchmarks.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
    a.directory.mkdir(parents=True,exist_ok=False)
    suffix=datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    network='ds2l-opt-test-'+suffix;db=network+'-db';runner=network+'-java'
    owned=[];counter=0
    def run(command,label,check=True):
        nonlocal counter
        counter+=1;prefix=a.directory/(str(counter).zfill(2)+'-'+label)
        prefix.with_suffix('.command.json').write_text(json.dumps(command,indent=2),encoding='utf-8')
        with prefix.with_suffix('.stdout.log').open('wb') as out,prefix.with_suffix('.stderr.log').open('wb') as err:
            result=subprocess.run(command,stdout=out,stderr=err,cwd=ROOT)
        prefix.with_suffix('.exit.json').write_text(json.dumps({'exit_code':result.returncode}),encoding='utf-8')
        if check and result.returncode:raise RuntimeError(label+' failed; see preserved log')
        return result.returncode
    save={'scope':'isolated Linux test workspace + ephemeral pgvector; synthetic AI; no AWS resources',
          'started_at':datetime.now(timezone.utc).isoformat(),'network':network,'containers':[db,runner]}
    (a.directory/'manifest.json').write_text(json.dumps(save,indent=2),encoding='utf-8')
    try:
        run(['docker','network','create','--label','ds2l.experiment='+suffix,network],'network');owned.append(('network',network))
        run(['docker','run','-d','--name',db,'--label','ds2l.experiment='+suffix,'--network',network,
             '-e','POSTGRES_USER=drivescene','-e','POSTGRES_DB=drivescene_test','-e','POSTGRES_PASSWORD=isolated-test-only',
             'pgvector/pgvector:pg16-trixie'],'start-db');owned.append(('container',db))
        for attempt in range(30):
            if run(['docker','exec',db,'pg_isready','-U','drivescene','-d','drivescene_test'],'db-ready',False)==0:break
            time.sleep(1)
        else:raise RuntimeError('Test database not ready')
        run(['docker','run','-d','--name',runner,'--label','ds2l.experiment='+suffix,'--network',network,
             '--user','root','--workdir','/workspace','--memory','3g','--cpus','2',
             '-v','ds2l-gradle-cache:/home/gradle/.gradle','-e','GRADLE_USER_HOME=/home/gradle/.gradle',
             '-e','TEST_DB_URL=jdbc:postgresql://'+db+':5432/drivescene_test','-e','TEST_DB_USERNAME=drivescene',
             '-e','TEST_DB_PASSWORD=isolated-test-only','gradle:9.7.1-jdk21','sleep','infinity'],'start-java');owned.append(('container',runner))
        for name in ('src','build.gradle','settings.gradle'):
            run(['docker','cp',str(ROOT/name),runner+':/workspace/'+name],'copy-'+name.replace('.','-'))
        command=['docker','exec',runner,'gradle','--no-daemon','--max-workers=2','test',
                 '--tests','com.example.demo.SceneSearchTests','--tests','com.example.demo.PrefetchedSceneSearchTests',
                 '--tests','com.example.demo.WorkerConcurrencyTests']
        result=run(command,'java-tests',False)
        run(['docker','cp',runner+':/workspace/build/test-results/test',str(a.directory/'test-results')],'copy-results',False)
        results=[]
        for path in sorted((a.directory/'test-results').glob('*.xml')):
            row=ET.parse(path).getroot();results.append({k:row.attrib[k] for k in ('name','tests','failures','errors','skipped','time')})
        save.update(exit_code=result,suites=results,finished_at=datetime.now(timezone.utc).isoformat())
        (a.directory/'summary.json').write_text(json.dumps(save,indent=2),encoding='utf-8')
        print(json.dumps(save),flush=True)
        if result or len(results)!=3 or any(int(row['failures'])+int(row['errors']) for row in results):raise RuntimeError('Java regression gate did not pass')
    finally:
        # Only names created by this invocation, with an independently checked ownership label.
        for kind,name in reversed(owned):
            inspect=['docker',kind,'inspect','--format','{{index .Labels "ds2l.experiment"}}',name] if kind=='network' else ['docker','inspect','--format','{{index .Config.Labels "ds2l.experiment"}}',name]
            observed=subprocess.run(inspect,capture_output=True,text=True)
            if observed.returncode==0 and observed.stdout.strip()==suffix:
                run(['docker','rm','-f',name] if kind=='container' else ['docker','network','rm',name],'cleanup-'+kind,False)


if __name__=='__main__':main()
