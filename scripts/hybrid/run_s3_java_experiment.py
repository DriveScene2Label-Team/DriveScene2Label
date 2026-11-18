"""Real Java S3 round trips with exact-key/version cleanup and immutable per-case logs.

Mounts the existing dataset volume read-only. Uses a fresh labelled work volume
per case; never starts Spring workers, RDS or GPU. Run pilot before large cases.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
from uuid import uuid4
from operations import read_values

ROOT=Path(__file__).resolve().parents[2]
SMALL='bd78307e-83c5-4215-a06f-f569a6bba684'
LARGE='f00cc327-dc93-4e82-a8aa-ef9d18dcc550'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--env-file',type=Path,required=True)
    p.add_argument('--image',default='ds2l-s3-java-experiment:20261118')
    p.add_argument('--phase',choices=('pilot','faults','large','large-pair','threshold'),required=True);a=p.parse_args()
    directory=a.directory.resolve();directory.mkdir(parents=True,exist_ok=False)
    values=read_values(a.env_file);bucket=values['UPLOAD_S3_BUCKET']
    if bucket!='ds2l-189750306426-ap-northeast-2-data':raise ValueError('Unexpected bucket')
    def save(path,data):path.write_text(json.dumps(data,indent=2),encoding='utf-8')
    counter=0
    def run(command,label,folder=directory,check=True):
        nonlocal counter
        counter+=1;prefix=folder/f'{counter:03d}-{label}'
        save(prefix.with_suffix('.command.json'),command)
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',cwd=ROOT)
        prefix.with_suffix('.stdout.log').write_text(result.stdout,encoding='utf-8')
        prefix.with_suffix('.stderr.log').write_text(result.stderr,encoding='utf-8');save(prefix.with_suffix('.exit.json'),{'exit_code':result.returncode})
        if check and result.returncode:raise RuntimeError(label+' failed; logs retained')
        return result
    def aws(label,*args,folder=directory):
        output=run(['aws',*args,'--profile','ds2l-seoul','--region','ap-northeast-2','--output','json','--no-cli-pager'],label,folder)
        return json.loads(output.stdout) if output.stdout.strip() else {}
    if aws('identity','sts','get-caller-identity')['Account']!='189750306426':raise ValueError('Wrong AWS account')
    run(['docker','image','inspect','--format','{{.Id}}',a.image],'image-id')
    (directory/'s3-profile.ini').write_text('[default]\nregion=ap-northeast-2\ncredential_process=cat /run/hybrid-aws/session.json\n',encoding='utf-8')
    if a.phase in ('pilot','large-pair'):cases=[('single','none'),('multipart','none')]
    elif a.phase=='faults':cases=[('multipart',f) for f in ('transient503','permanent503','complete-lost','download-cut','crash')]
    elif a.phase=='threshold':cases=[('automatic','none')]
    else:cases=[(m,'none') for order in [('single','multipart'),('multipart','single'),('single','multipart')] for m in order]
    manifest={'started_at':datetime.now(timezone.utc).isoformat(),'phase':a.phase,'cases':[],
              'scope':'actual Java production storage methods against existing S3; this process does not access RDS or GPU; record external activity separately',
              'source_id':LARGE if a.phase in ('large','large-pair') else SMALL,'case_order':cases,
              'source_hashes':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),*ROOT.glob('src/main/java/com/example/demo/nuscenes/storage/*.java')]}}
    save(directory/'manifest.json',manifest)
    try:
        for index,(mode,fault) in enumerate(cases):
            label=f'{index:02d}-{mode}-{fault}';folder=directory/label;folder.mkdir()
            identifier=str(uuid4());key='uploads/'+identifier+'.tar.gz';name='ds2l-s3-'+identifier
            owned={'label':label,'uuid':identifier,'key':key,'container':name,'volume':name+'-work','cleaned':False}
            manifest['cases'].append(owned);save(directory/'manifest.json',manifest)
            print(json.dumps({'event':'case_start','case':label,'phase':a.phase}),flush=True)
            volume_created=False;container_created=False
            def versions(stage):
                result=aws(stage+'-versions','s3api','list-object-versions','--bucket',bucket,'--prefix',key,folder=folder)
                return [v for k in ('Versions','DeleteMarkers') for v in result.get(k,[]) if v['Key']==key]
            def uploads(stage):
                result=aws(stage+'-uploads','s3api','list-multipart-uploads','--bucket',bucket,'--prefix',key,folder=folder)
                return [v for v in result.get('Uploads',[]) if v['Key']==key]
            if versions('before') or uploads('before'):raise ValueError('Fresh UUID key unexpectedly exists')
            try:
                run(['python','scripts/hybrid/refresh-s3-session.py','--directory',str(a.env_file.parent/'aws')],'refresh-session',folder)
                run(['docker','volume','create','--label','ds2l.s3-experiment='+identifier,owned['volume']],'volume-create',folder);volume_created=True
                run(['docker','run','--rm','--network','none','--user','root','-v',owned['volume']+':/work','--entrypoint','chown',a.image,'10001:10001','/work'],'volume-owner',folder)
                fixture=LARGE if a.phase in ('large','large-pair') else SMALL
                original='/fixtures/datasets/'+fixture if a.phase=='large' and index<2 else 'none'
                command=['docker','run','--name',name,'--label','ds2l.s3-experiment='+identifier,'--memory','768m','--cpus','4',
                         '-v','drivescene-hybrid_uploaded_datasets:/fixtures:ro','-v',owned['volume']+':/work',
                         '-v',str(folder)+':/evidence','-v',str(directory/'s3-profile.ini')+':/run/s3-profile.ini:ro',
                         '-v',str(a.env_file.parent/'aws')+':/run/hybrid-aws:ro',
                         '-e','AWS_PROFILE=default','-e','AWS_REGION=ap-northeast-2','-e','AWS_SHARED_CREDENTIALS_FILE=/run/s3-profile.ini',
                         '-e','AWS_EC2_METADATA_DISABLED=true','--entrypoint','java',a.image,'-Xmx256m',
                         '-Dloader.main=com.example.demo.nuscenes.storage.S3ArchiveExperiment','-cp','/app/app.jar',
                         'org.springframework.boot.loader.launch.PropertiesLauncher',bucket,'/fixtures/archives/'+fixture+'.tar.gz',
                         identifier,'/work/run','/evidence',mode,fault,original]
                save(folder/'java-command.json',command)
                with (folder/'java.stdout.log').open('wb') as out,(folder/'java.stderr.log').open('wb') as err:
                    process=subprocess.Popen(command,stdout=out,stderr=err,cwd=ROOT);container_created=True
                    if fault=='crash':
                        deadline=time.monotonic()+180
                        while not (folder/'crash-ready.json').exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(1)
                        if not (folder/'crash-ready.json').exists():raise RuntimeError('Crash case never accepted a real part')
                        run(['docker','kill',name],'injected-kill',folder)
                    try:exit_code=process.wait(timeout=2100)
                    except subprocess.TimeoutExpired:
                        run(['docker','kill',name],'timeout-kill',folder);process.wait(timeout=30);raise
                save(folder/'java-exit.json',{'exit_code':exit_code})
                pending=uploads('after-java');stored=versions('after-java')
                if fault=='crash':
                    if exit_code==0 or not pending or stored:raise AssertionError('Crash did not leave expected incomplete-only state')
                    owned['result']={'pass':True,'expected_abrupt_exit':exit_code,'orphan_uploads_observed':len(pending),
                                     'lifecycle_expiration_observed':False,'recovery':'operator exact upload-ID abort, verified below'}
                    save(folder/'result.json',owned['result'])
                else:
                    result=json.loads((folder/'result.json').read_text(encoding='utf-8'));owned['result']=result
                    if exit_code or not result.get('pass') or pending:raise AssertionError('Java result/cleanup gate failed')
                    if a.phase=='threshold' and (result['mode']!='single' or result['multipart_threshold_bytes']!=1073741824):raise AssertionError('Small-file threshold guard failed')
                    if len(stored)!=(0 if fault=='permanent503' else 1):raise AssertionError('Unexpected completed version count')
                print(json.dumps({'event':'case_complete','case':label,**owned['result']}),flush=True)
            finally:
                # Stop only our labelled process before checking/deleting its exact S3 keys.
                if container_created:
                    found=run(['docker','inspect','--format','{{index .Config.Labels "ds2l.s3-experiment"}}',name],'container-owner',folder,False)
                    if found.returncode==0 and found.stdout.strip()==identifier:
                        run(['docker','inspect','--format','{{json .State}}',name],'container-state',folder)
                        run(['docker','rm','-f',name],'container-remove',folder)
                for pending in uploads('cleanup'):
                    aws('abort-owned-upload','s3api','abort-multipart-upload','--bucket',bucket,'--key',key,'--upload-id',pending['UploadId'],folder=folder)
                    verification=run(['aws','s3api','list-parts','--bucket',bucket,'--key',key,'--upload-id',pending['UploadId'],
                                      '--profile','ds2l-seoul','--region','ap-northeast-2','--output','json','--no-cli-pager'],
                                     'aborted-parts-verification',folder,False)
                    if verification.returncode==0 or 'NoSuchUpload' not in verification.stderr:raise AssertionError('Aborted parts not confirmed absent')
                for version in versions('cleanup'):
                    aws('delete-owned-version','s3api','delete-object','--bucket',bucket,'--key',key,'--version-id',version['VersionId'],folder=folder)
                if uploads('final') or versions('final'):raise AssertionError('Owned S3 data remains')
                if volume_created:
                    found=run(['docker','volume','inspect','--format','{{index .Labels "ds2l.s3-experiment"}}',owned['volume']],'volume-owner-check',folder)
                    if found.stdout.strip()!=identifier:raise AssertionError('Work volume ownership changed')
                    run(['docker','volume','rm',owned['volume']],'volume-remove',folder)
                owned['cleaned']=True;save(directory/'manifest.json',manifest)
        manifest['pass']=True
        if a.phase in ('large','large-pair'):
            comparison={}
            for mode in ('single','multipart'):
                rows=[c['result'] for c in manifest['cases'] if c['result']['mode']==mode]
                comparison[mode]={metric:[r[metric] for r in rows] for metric in ('upload_s','download_s','peak_heap_bytes','peak_rss_bytes')}
                comparison[mode]['upload_median_s']=statistics.median(r['upload_s'] for r in rows)
                comparison[mode]['download_median_s']=statistics.median(r['download_s'] for r in rows)
            comparison['upload_reduction']=1-comparison['multipart']['upload_median_s']/comparison['single']['upload_median_s']
            save(directory/'comparison.json',comparison)
    finally:
        manifest['finished_at']=datetime.now(timezone.utc).isoformat();save(directory/'manifest.json',manifest)


if __name__=='__main__':main()
