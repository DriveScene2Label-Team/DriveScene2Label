"""Narrow Autopilot output to multipart cleanup actions on the existing archive role.

Default is read/prepare/validate. --apply preserves existing IAM statements and
adds only an incomplete-upload lifecycle rule, never completed-object expiration.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess

BUCKET='ds2l-189750306426-ap-northeast-2-data'
ROLE='ds2l-hybrid-storage'
POLICY='DatasetArchivesOnly'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--autopilot-json',type=Path,required=True)
    p.add_argument('--apply',action='store_true');a=p.parse_args()
    a.directory.mkdir(parents=True,exist_ok=False)
    sequence=0
    def aws(label,*args,missing=None):
        nonlocal sequence
        sequence+=1
        command=['aws',*args,'--profile','ds2l-seoul','--region','ap-northeast-2','--output','json','--no-cli-pager']
        run=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        value=json.loads(run.stdout) if run.stdout.strip() else None
        (a.directory/f'{sequence:02d}-{label}.json').write_text(json.dumps({'command':command,'exit_code':run.returncode,'result':value,'error':run.stderr},indent=2),encoding='utf-8')
        if run.returncode and not (missing and missing in run.stderr):raise RuntimeError(label+' failed')
        return value
    if aws('identity','sts','get-caller-identity')['Account']!='189750306426':raise ValueError('Wrong AWS account')
    before=aws('policy-before','iam','get-role-policy','--role-name',ROLE,'--policy-name',POLICY)['PolicyDocument']
    generated=json.loads(a.autopilot_json.read_text(encoding='utf-8-sig'))
    actions={action for policy in generated['Policies'] for statement in policy['Policy']['Statement'] for action in statement['Action']}
    needed={'s3:AbortMultipartUpload','s3:ListMultipartUploadParts'}
    if not needed<=actions:raise ValueError('Expected actions absent from Autopilot output')
    after=copy.deepcopy(before)
    targets=[s for s in after['Statement'] if s['Effect']=='Allow' and s['Resource']==f'arn:aws:s3:::{BUCKET}/uploads/*']
    if len(targets)!=1:raise ValueError('Unexpected existing policy scope')
    added=needed-set(targets[0]['Action'])
    targets[0]['Action']=sorted(set(targets[0]['Action'])|needed)
    policy=a.directory.resolve()/'policy-candidate.json';policy.write_text(json.dumps(after,indent=2),encoding='utf-8')
    findings=aws('policy-validation','accessanalyzer','validate-policy','--policy-type','IDENTITY_POLICY','--policy-document','file://'+str(policy))
    if any(f['findingType'] in ('ERROR','SECURITY_WARNING') for f in findings['findings']):raise ValueError('IAM validation gate failed')
    pending=aws('pending-before','s3api','list-multipart-uploads','--bucket',BUCKET,'--prefix','uploads/')
    if pending.get('Uploads'):raise ValueError('Existing incomplete uploads require review before applying lifecycle')
    lifecycle=aws('lifecycle-before','s3api','get-bucket-lifecycle-configuration','--bucket',BUCKET,missing='NoSuchLifecycleConfiguration')
    # Preserve every existing rule. Do not silently replace an operator's rule.
    rule={'ID':'ds2l-abort-incomplete-archive-uploads','Status':'Enabled','Filter':{'Prefix':'uploads/'},'AbortIncompleteMultipartUpload':{'DaysAfterInitiation':1}}
    rules=(lifecycle or {}).get('Rules',[])
    matched=[r for r in rules if r.get('ID')==rule['ID']]
    if matched and matched!=[rule]:raise ValueError('Lifecycle rule ID already used with different settings')
    desired={'Rules':rules if matched else rules+[rule]}
    path=a.directory.resolve()/'lifecycle-candidate.json';path.write_text(json.dumps(desired,indent=2),encoding='utf-8')
    if a.apply:
        observed=aws('policy-recheck','iam','get-role-policy','--role-name',ROLE,'--policy-name',POLICY)['PolicyDocument']
        if observed!=before:raise ValueError('Concurrent IAM change; abort')
        aws('policy-apply','iam','put-role-policy','--role-name',ROLE,'--policy-name',POLICY,'--policy-document','file://'+str(policy))
        current=aws('lifecycle-recheck','s3api','get-bucket-lifecycle-configuration','--bucket',BUCKET,missing='NoSuchLifecycleConfiguration')
        if current!=lifecycle:raise ValueError('Concurrent lifecycle change; abort')
        transition=(lifecycle or {}).get('TransitionDefaultMinimumObjectSize')
        options=['--transition-default-minimum-object-size',transition] if transition else []
        aws('lifecycle-apply','s3api','put-bucket-lifecycle-configuration','--bucket',BUCKET,'--lifecycle-configuration','file://'+str(path),*options)
        if aws('policy-after','iam','get-role-policy','--role-name',ROLE,'--policy-name',POLICY)['PolicyDocument']!=after:raise ValueError('Policy readback differs')
        observed=aws('lifecycle-after','s3api','get-bucket-lifecycle-configuration','--bucket',BUCKET)
        if observed['Rules']!=desired['Rules'] or (transition and observed.get('TransitionDefaultMinimumObjectSize')!=transition):raise ValueError('Lifecycle readback differs')
    (a.directory/'result.json').write_text(json.dumps({'applied':a.apply,'actions_added':sorted(added),'resource':f'arn:aws:s3:::{BUCKET}/uploads/*','completed_objects_expired':False,'lifecycle_observed_expiration':False},indent=2),encoding='utf-8')


if __name__=='__main__':main()
