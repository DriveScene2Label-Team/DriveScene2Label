"""Verify every 3D output field survives model artifact -> RDS -> API readback."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('compare_scene',ROOT/'ai-server/tools/compare_scene.py')
comparison=importlib.util.module_from_spec(spec);spec.loader.exec_module(comparison)


def normalize_api(payload):
    result={token:[] for token in payload['sampleTokens']}
    indices={token:[] for token in result}
    for box in payload['boxes']:
        token=box['sampleToken'];indices[token].append(box['boxIndex'])
        result[token].append({'sample_token':token,'translation':[box[k] for k in ('centerX','centerY','centerZ')],
            'size':[box[k] for k in ('sizeW','sizeL','sizeH')],
            'rotation':[box[k] for k in ('rotationW','rotationX','rotationY','rotationZ')],
            'velocity':[box[k] for k in ('velocityX','velocityY')],
            'detection_name':box['detectionName'],'detection_score':box['detectionScore'],
            'attribute_name':box['attributeName'],'track_id':box['trackId']})
    return result,all(values==list(range(len(values))) for values in indices.values())


def verify(original,api):
    decoded,indices_valid=normalize_api(api)
    regression=comparison.compare(original['results'],decoded,tolerance=1e-9)
    expected_checksum=hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    artifact=next(row for row in api['artifacts'] if row['artifactType']=='FINAL_JSON')
    checksum_matches=artifact['checksum']==expected_checksum
    geometry_valid=True
    for boxes in decoded.values():
        for box in boxes:
            values=box['translation']+box['size']+box['rotation']+box['velocity']
            geometry_valid=geometry_valid and all(math.isfinite(v) for v in values) and all(v>0 for v in box['size']) and abs(sum(v*v for v in box['rotation'])-1)<=.001
    unchanged_edits=all(box['labelOverride'] is None and not box['deleted'] for box in api['boxes'])
    semantics=api['coordinateFrame']=='WORLD' and api['scoreType']=='VESPA_CONSTANT' and api['mappingName']==original['mapping_name']
    return {'regression':regression,'indices_valid':indices_valid,'checksum_matches':checksum_matches,'geometry_valid':geometry_valid,
        'unchanged_edits':unchanged_edits,'semantics_match':semantics,'keyframes':len(decoded),'boxes':len(api['boxes']),
        'passed':regression['within_tolerance'] and indices_valid and checksum_matches and geometry_valid and unchanged_edits and semantics}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
    original=json.loads((a.directory/'model-result.json').read_text(encoding='utf-8'))
    api=json.loads((a.directory/'rds-results.json').read_text(encoding='utf-8'))
    result=verify(original,api)
    with (a.directory/'roundtrip-quality.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
