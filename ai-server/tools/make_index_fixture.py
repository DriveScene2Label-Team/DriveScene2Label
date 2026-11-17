"""Create a small two-scene keyframe archive for repeated normal-API CLIP tests.

Preserves original sensor bytes and identifiers. Not a full-sweep VESPA dataset.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scenes',nargs='+',default=['scene-0061','scene-0103'])
    a=p.parse_args(); version='v1.0-mini'; metadata=a.data_root/version
    names=['attribute','calibrated_sensor','category','ego_pose','instance','log','map','sample','sample_annotation','sample_data','scene','sensor','visibility']
    tables={name:json.loads((metadata/(name+'.json')).read_text()) for name in names}
    tables['scene']=[r for r in tables['scene'] if r['name'] in a.scenes]
    if len(tables['scene'])!=len(a.scenes):raise ValueError('Missing scene')
    def retain(name,field,keys):tables[name]=[r for r in tables[name] if r[field] in keys]
    retain('sample','scene_token',{r['token'] for r in tables['scene']})
    sample_tokens={r['token'] for r in tables['sample']}
    tables['sample_data']=[r for r in tables['sample_data'] if r['sample_token'] in sample_tokens and r['is_key_frame']]
    retain('sample_annotation','sample_token',sample_tokens)
    retain('ego_pose','token',{r['ego_pose_token'] for r in tables['sample_data']})
    retain('calibrated_sensor','token',{r['calibrated_sensor_token'] for r in tables['sample_data']})
    retain('sensor','token',{r['sensor_token'] for r in tables['calibrated_sensor']})
    retain('log','token',{r['log_token'] for r in tables['scene']})
    retain('instance','token',{r['instance_token'] for r in tables['sample_annotation']})
    files=sorted({r['filename'] for name in ('sample_data','map') for r in tables[name]})
    for name in files:
        path=(a.data_root/name).resolve(strict=True)
        if not path.is_relative_to(a.data_root.resolve()):raise ValueError('Path escaped dataset')
    if a.output.exists():raise ValueError('Use a new archive path')
    hashes={}
    with tarfile.open(a.output,'x:gz',compresslevel=1) as archive:
        for name,rows in tables.items():
            data=json.dumps(rows,separators=(',',':')).encode();info=tarfile.TarInfo(version+'/'+name+'.json');info.size=len(data);info.mode=0o644
            archive.addfile(info,io.BytesIO(data))
        for name in files:
            data=(a.data_root/name).read_bytes();hashes[name]=hashlib.sha256(data).hexdigest();info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;archive.addfile(info,io.BytesIO(data))
    digest=hashlib.sha256()
    with a.output.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    result={'scope':'two-scene keyframes for indexing; non-keyframe sweeps omitted; do not use for VESPA labeling',
        'scenes':a.scenes,'keyframe_cameras':sum(r['filename'].startswith('samples/CAM_') for r in tables['sample_data']),
        'table_rows':{name:len(rows) for name,rows in tables.items()},'file_sha256':hashes,
        'archive_bytes':a.output.stat().st_size,'archive_sha256':digest.hexdigest()}
    a.output.with_suffix('.manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='file_sha256'}))


if __name__=='__main__':main()
