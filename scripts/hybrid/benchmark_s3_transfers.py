"""Measure bounded S3 transfer concurrency with byte integrity and owned-key cleanup.

Uses the app's existing S3-only temporary session. No RDS/API mutation. This is a
Python SDK transfer experiment, not a claim about Java application latency.
Never log credentials, signed URLs, HTTP headers or full SDK responses.
"""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import threading
import time
from uuid import uuid4

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError
from evidence_io import save_json
from operations import read_values


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def copy_response_body(body, destination):
    # Some botocore versions return the underlying HTTPResponse from __enter__.
    # closing keeps the StreamingBody wrapper (and its length validation).
    with closing(body), destination.open('xb') as stream:
        for chunk in body.iter_chunks(chunk_size=65536):
            stream.write(chunk)


def cleanup_cli(*args):
    """Existing operator profile, only for exact owned-key version/MPU cleanup.

    The application role intentionally lacks Get/DeleteObjectVersion and Abort
    MultipartUpload. Do not broaden its policy merely for this experiment.
    """
    result=subprocess.run(['aws',*args,'--profile','ds2l-seoul','--region','ap-northeast-2',
                           '--output','json','--no-cli-pager'],capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise RuntimeError('Scoped cleanup CLI failed; exit '+str(result.returncode))
    return json.loads(result.stdout) if result.stdout.strip() else {}


def experiment(a):
    root=a.directory.resolve()
    if not (root/'manifest.json').is_file():raise ValueError('Begin a fresh measurement')
    size=a.source.stat().st_size
    if not 32*1024*1024<=size<=512*1024*1024:raise ValueError('Use a bounded 32..512MiB fixture first')
    if shutil.disk_usage(root).free<size*14:raise ValueError('Insufficient free space for preserved downloads')
    values=read_values(a.env_file);bucket=values['UPLOAD_S3_BUCKET']
    credentials=json.loads((a.env_file.parent/'aws/session.json').read_text(encoding='utf-8-sig'))
    expiry=datetime.fromisoformat(credentials['Expiration'].replace('Z','+00:00'))
    if (expiry-datetime.now(timezone.utc)).total_seconds()<1800:raise ValueError('Refresh S3-only session before this experiment')
    session=boto3.Session(aws_access_key_id=credentials['AccessKeyId'],aws_secret_access_key=credentials['SecretAccessKey'],
                          aws_session_token=credentials['SessionToken'],region_name='ap-northeast-2')
    config=Config(connect_timeout=5,read_timeout=60,max_pool_connections=8,retries={'total_max_attempts':3,'mode':'standard'})
    with closing(session.client('sts',config=config)) as identity:
        account=identity.get_caller_identity()
    if account['Account']!='189750306426' or ':assumed-role/ds2l-hybrid-storage/' not in account['Arn']:
        raise ValueError('Expected existing project S3-only role')
    if cleanup_cli('sts','get-caller-identity')['Account']!='189750306426':
        raise ValueError('Cleanup operator account mismatch')
    expected=digest(a.source);orders=[['stream','mp1','mp2','mp4'],['mp4','mp2','mp1','stream'],['mp2','stream','mp4','mp1']]
    plan={'started_at':datetime.now(timezone.utc).isoformat(),'bucket':bucket,'region':'ap-northeast-2',
          'benchmark_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'source_bytes':size,'source_sha256':expected,'source_name':a.source.name,'orders':orders,'part_bytes':16*1024*1024,
          'scope':'isolated Python SDK upload/download; not Java app end-to-end timing','versions':{n:importlib.metadata.version(n) for n in ('boto3','botocore','s3transfer')},
          'cleanup':'existing operator profile deletes only new UUID object versions with matching owner metadata and aborts incomplete uploads for those exact keys; app IAM policy unchanged',
          'status':'running','cases':[],'created':[],'cleanup_errors':[]}
    save_json(root/'s3-transfer-experiment.json',plan)
    lock=threading.Lock();context={'phase':'setup','case':None}
    with closing(session.client('s3',config=config)) as s3,(root/'s3-requests.jsonl').open('x',encoding='utf-8') as requests:
        def observed(model,http_response,parsed,**kwargs):
            meta=parsed.get('ResponseMetadata',{})
            with lock:
                requests.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),**context,'operation':model.name,
                    'http_status':http_response.status_code,'retry_attempts':meta.get('RetryAttempts'),
                    'request_id':meta.get('RequestId')})+'\n');requests.flush()
        s3.meta.events.register('after-call.s3',observed)
        try:
            for repeat,order in enumerate(orders):
                for mode in order:
                    label=f'r{repeat}-{mode}';directory=root/label;directory.mkdir(exist_ok=False)
                    key='uploads/'+str(uuid4())+'.tgz';context.update(case=label,phase='upload')
                    owned={'key':key,'case':label,'version_id':None,'deleted':False};plan['created'].append(owned)
                    save_json(root/'s3-transfer-experiment.json',plan)
                    metadata={'ds2l-experiment':root.name,'source-sha256':expected}
                    concurrency=1 if mode=='stream' else int(mode[-1])
                    transfer=TransferConfig(multipart_threshold=16*1024*1024,multipart_chunksize=16*1024*1024,
                         max_concurrency=concurrency,max_io_queue=16,io_chunksize=256*1024,use_threads=True,preferred_transfer_client='classic')
                    started=time.perf_counter();cpu=time.process_time()
                    if mode=='stream':
                        with a.source.open('rb') as stream:s3.put_object(Bucket=bucket,Key=key,Body=stream,ContentLength=size,Metadata=metadata)
                    else:s3.upload_file(str(a.source),bucket,key,ExtraArgs={'Metadata':metadata},Config=transfer)
                    upload={'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu}
                    context['phase']='verify_head';head=s3.head_object(Bucket=bucket,Key=key)
                    owned['version_id']=head.get('VersionId')
                    if head['ContentLength']!=size or head['Metadata']!=metadata:raise ValueError('Uploaded object metadata/size mismatch')
                    destination=directory/'download.tgz';context['phase']='download';started=time.perf_counter();cpu=time.process_time()
                    # Fresh UUID key has exactly our new version. The app role
                    # permits current-object GET, not GetObjectVersion.
                    extra={}
                    if mode=='stream':
                        copy_response_body(s3.get_object(Bucket=bucket,Key=key,**extra)['Body'],destination)
                    else:s3.download_file(bucket,key,str(destination),ExtraArgs=extra,Config=transfer)
                    download={'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu}
                    context['phase']='hash';matched=destination.stat().st_size==size and digest(destination)==expected
                    result={'repeat':repeat,'mode':mode,'concurrency':concurrency,'upload':upload,'download':download,
                            'bytes':size,'sha256_matches':matched,'source_sha256':expected,'object_key':key,'etag':head['ETag']}
                    plan['cases'].append(result);save_json(directory/'result.json',result);save_json(root/'s3-transfer-experiment.json',plan)
                    print(json.dumps({'event':'s3_case_completed',**result}),flush=True)
                    if not matched:raise ValueError('Downloaded bytes differ')
            plan['status']='completed'
        except Exception as error:
            plan['status']='failed'
            plan['error_type']=type(error).__name__
            raise
        finally:
            context.update(phase='owned_key_cleanup',case=None)
            for owned in plan['created']:
                key=owned['key']
                try:
                    head=s3.head_object(Bucket=bucket,Key=key)
                    if head.get('Metadata',{}).get('ds2l-experiment')!=root.name:raise ValueError('Cleanup ownership mismatch')
                    version=owned.get('version_id') or head.get('VersionId')
                    if owned.get('version_id') and head.get('VersionId')!=owned['version_id']:
                        raise ValueError('Owned object version changed; refusing cleanup')
                    if version:
                        cleanup_cli('s3api','delete-object','--bucket',bucket,'--key',key,'--version-id',version)
                    else:s3.delete_object(Bucket=bucket,Key=key)
                    owned['deleted']=True
                except ClientError as error:
                    if error.response['ResponseMetadata']['HTTPStatusCode']==404:owned['deleted']=True
                    else:plan['cleanup_errors'].append({'key':key,'code':error.response['Error']['Code']})
                except (ValueError,RuntimeError) as error:plan['cleanup_errors'].append({'key':key,'code':str(error)})
                save_json(root/'s3-transfer-experiment.json',plan)
                try:
                    pending=cleanup_cli('s3api','list-multipart-uploads','--bucket',bucket,'--prefix',key)
                    owned['aborted_incomplete_uploads']=0
                    for upload in pending.get('Uploads',[]):
                        if upload['Key']==key:
                            cleanup_cli('s3api','abort-multipart-upload','--bucket',bucket,'--key',key,'--upload-id',upload['UploadId'])
                            owned['aborted_incomplete_uploads']+=1
                    if owned['deleted']:
                        versions=cleanup_cli('s3api','list-object-versions','--bucket',bucket,'--prefix',key)
                        owned['absence_verified']=not any(v['Key']==key for field in ('Versions','DeleteMarkers') for v in versions.get(field,[]))
                        if not owned['absence_verified']:raise ValueError('Owned key still has a version; retained for investigation')
                except (ValueError,RuntimeError) as error:plan['cleanup_errors'].append({'key':key,'code':str(error)})
            plan['finished_at']=datetime.now(timezone.utc).isoformat();save_json(root/'s3-transfer-experiment.json',plan)
    if plan['status']!='completed' or plan['cleanup_errors']:raise RuntimeError('Transfer or owned-key cleanup incomplete; inspect evidence')
    plan['medians']={mode:{phase:statistics.median(c[phase]['wall_seconds'] for c in plan['cases'] if c['mode']==mode)
                         for phase in ('upload','download')} for mode in orders[0]}
    save_json(root/'s3-transfer-experiment.json',plan)
    print(json.dumps({'event':'s3_experiment_completed','medians':plan['medians'],'hashes_passed':True,'owned_keys_cleaned':True}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--env-file',type=Path,required=True);a=p.parse_args()
    try:experiment(a)
    except ClientError as error:
        # No arbitrary AWS response body, headers or credential data in logs.
        save_json(a.directory/'s3-error.json',{'code':error.response['Error']['Code'],'status':error.response['ResponseMetadata']['HTTPStatusCode']})
        raise RuntimeError('S3 request failed; allowlisted error code saved') from None


if __name__=='__main__':main()
