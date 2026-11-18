"""Recover only unfinished, provably fresh UUIDs from an interrupted S3 experiment.

Original manifests/logs remain unchanged. No application dataset, source volume,
account or model is reset here. --apply removes exact test versions/upload IDs
and labelled experiment containers/work volumes after preserving observations.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
from uuid import UUID

BUCKET='ds2l-189750306426-ap-northeast-2-data'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);sequence=0
    def save(name,value):(a.output/name).write_text(json.dumps(value,indent=2),encoding='utf-8')
    def run(label,command,missing=None):
        nonlocal sequence
        sequence+=1;r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
        save(f'{sequence:02d}-{label}.json',{'command':command,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        if r.returncode and not (missing and missing in r.stderr):raise RuntimeError(label+' failed')
        return r
    def aws(label,*args,missing=None):
        r=run(label,['aws',*args,'--profile','ds2l-seoul','--region','ap-northeast-2','--output','json','--no-cli-pager'],missing)
        return json.loads(r.stdout) if r.stdout.strip() else {}
    if aws('identity','sts','get-caller-identity')['Account']!='189750306426':raise ValueError('Wrong account')
    manifest=json.loads((a.directory/'manifest.json').read_text(encoding='utf-8'))
    result={'started_at':datetime.now(timezone.utc).isoformat(),'applied':a.apply,'original_manifest_preserved':True,'cases':[]}
    for case in manifest['cases']:
        if case.get('cleaned'):continue
        identifier=str(UUID(case['uuid']));key='uploads/'+identifier+'.tar.gz';name='ds2l-s3-'+identifier
        if case['key']!=key or case['container']!=name or case['volume']!=name+'-work':raise ValueError('Unexpected ownership record')
        folder=a.directory/case['label']
        for kind,fields in [('versions',('Versions','DeleteMarkers')),('uploads',('Uploads',))]:
            paths=list(folder.glob('*before-'+kind+'.stdout.log'))
            if len(paths)!=1:raise ValueError('Fresh-key precondition evidence missing')
            before=json.loads(paths[0].read_text(encoding='utf-8'))
            if any(before.get(field) for field in fields):raise ValueError('Key existed before experiment; refuse cleanup')
        state=run('container-state',['docker','inspect','--format','{{json .State}}',name],missing='No such object')
        owner=run('container-owner',['docker','inspect','--format','{{index .Config.Labels "ds2l.s3-experiment"}}',name],missing='No such object')
        if owner.returncode==0 and owner.stdout.strip()!=identifier:raise ValueError('Container ownership differs')
        if state.returncode==0 and json.loads(state.stdout)['Running']:raise ValueError('Experiment still running; do not interrupt a live owner')
        uploads=aws('pending-before','s3api','list-multipart-uploads','--bucket',BUCKET,'--prefix',key).get('Uploads',[])
        versions=aws('versions-before','s3api','list-object-versions','--bucket',BUCKET,'--prefix',key)
        row={'case':case['label'],'uuid':identifier,'key':key,'pending':[],'cleaned':False}
        for pending in uploads:
            if pending['Key']!=key:raise ValueError('Prefix returned a different key')
            parts=aws('parts-before','s3api','list-parts','--bucket',BUCKET,'--key',key,'--upload-id',pending['UploadId'])
            row['pending'].append({'upload_id':pending['UploadId'],'parts':len(parts.get('Parts',[])),
                                   'bytes':sum(p['Size'] for p in parts.get('Parts',[]))})
            if a.apply:
                aws('abort','s3api','abort-multipart-upload','--bucket',BUCKET,'--key',key,'--upload-id',pending['UploadId'])
                check=run('verify-aborted-parts',['aws','s3api','list-parts','--bucket',BUCKET,'--key',key,'--upload-id',pending['UploadId'],
                          '--profile','ds2l-seoul','--region','ap-northeast-2','--output','json','--no-cli-pager'],missing='NoSuchUpload')
                if check.returncode==0:raise ValueError('Multipart parts still exist')
        if a.apply:
            for version in versions.get('Versions',[])+versions.get('DeleteMarkers',[]):
                if version['Key']!=key:raise ValueError('Different version key')
                aws('delete-owned-version','s3api','delete-object','--bucket',BUCKET,'--key',key,'--version-id',version['VersionId'])
            final_uploads=aws('pending-after','s3api','list-multipart-uploads','--bucket',BUCKET,'--prefix',key)
            final_versions=aws('versions-after','s3api','list-object-versions','--bucket',BUCKET,'--prefix',key)
            if final_uploads.get('Uploads') or final_versions.get('Versions') or final_versions.get('DeleteMarkers'):raise ValueError('Cleanup incomplete')
            if owner.returncode==0:run('remove-stopped-container',['docker','rm',name])
            volume=run('volume-owner',['docker','volume','inspect','--format','{{index .Labels "ds2l.s3-experiment"}}',case['volume']],missing='no such volume')
            if volume.returncode==0:
                if volume.stdout.strip()!=identifier:raise ValueError('Volume ownership differs')
                run('remove-owned-work-volume',['docker','volume','rm',case['volume']])
            row['cleaned']=True
        result['cases'].append(row);save('result.json',result)
    result['finished_at']=datetime.now(timezone.utc).isoformat();result['pass']=a.apply and all(r['cleaned'] for r in result['cases'])
    save('result.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
