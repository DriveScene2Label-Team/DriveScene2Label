"""Copy an explicit, reviewed selection of experiment files for Git review.

The JSON selection contains source (under .local/hybrid) and target paths.
Original bytes stay untouched. Text paths are made repository-relative; original
and exported SHA256 hashes record that transformation. Never select credentials,
datasets, model weights or full vector dumps. A separate private ZIP may retain
those experiment outputs that are too large for Git.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
ALLOWED={'.json','.jsonl','.md','.txt','.svg','.png'}
SECRET=re.compile(rb'(?:AKIA|ASIA)[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}')


def relative_strings(value):
    if isinstance(value,str):
        return value.replace(str(ROOT),'$REPO').replace(ROOT.as_posix(),'$REPO')
    if isinstance(value,list):return [relative_strings(v) for v in value]
    if isinstance(value,dict):return {k:relative_strings(v) for k,v in value.items()}
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--selection',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    destination=a.output.resolve()
    if not destination.is_relative_to(ROOT/'docs/evidence'):raise ValueError('Output must be under docs/evidence')
    selections=json.loads(a.selection.read_text(encoding='utf-8-sig'))
    destination.mkdir(parents=True,exist_ok=False)
    manifest=[]
    for selected in selections:
        source=(ROOT/selected['source']).resolve();target=(destination/selected['target']).resolve()
        if (not source.is_relative_to(ROOT/'.local/hybrid') or not target.is_relative_to(destination)
                or source.suffix not in ALLOWED or 'vectors' in source.name or 'session' in source.name.lower()):
            raise ValueError('Selection outside reviewed file classes: '+selected['source'])
        raw=source.read_bytes()
        if len(raw)>8*1024*1024:raise ValueError('Git evidence file too large: '+selected['source'])
        if SECRET.search(raw):raise ValueError('Potential credential pattern in selected file: '+selected['source'])
        if source.suffix=='.json':output=json.dumps(relative_strings(json.loads(raw.decode('utf-8-sig'))),ensure_ascii=False,indent=2).encode()
        elif source.suffix=='.jsonl':output=('\n'.join(json.dumps(relative_strings(json.loads(line)),ensure_ascii=False) for line in raw.decode('utf-8-sig').splitlines())+'\n').encode()
        elif source.suffix=='.png':output=raw
        else:output=relative_strings(raw.decode('utf-8-sig')).encode()
        # Git normalizes text on this Windows checkout. Hash the portable bytes
        # that reviewers actually receive rather than a CRLF-only worktree view.
        if source.suffix!='.png':output=output.replace(b'\r\n',b'\n')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(output)
        manifest.append({'source':source.relative_to(ROOT).as_posix(),'target':target.relative_to(destination).as_posix(),
            'source_sha256':hashlib.sha256(raw).hexdigest(),'export_sha256':hashlib.sha256(output).hexdigest(),'export_bytes':len(output)})
    value={'created_at':datetime.now(timezone.utc).isoformat(),'transformation':'JSON formatting, absolute repository path replacement and LF text line endings; original evidence is retained locally',
        'scope':'explicit selection; full vectors, original media, credentials and large raw output excluded','files':manifest}
    (destination/'manifest.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'directory':str(destination),'files':len(manifest),'bytes':sum(v['export_bytes'] for v in manifest)}))


if __name__=='__main__':main()
