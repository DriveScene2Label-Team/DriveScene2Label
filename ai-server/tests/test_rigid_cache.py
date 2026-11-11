import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.rigid_cache import save, load, references
from schemas.auto_label import AutoLabelRequest

def test_cache_identity_checksum_and_frame_membership(tmp_path):
    scene = SimpleNamespace(frames=[SimpleNamespace(sample_token='a'), SimpleNamespace(sample_token='b')])
    tracks = [[(0, 0), (1, 0)], [(1, 1)]]
    scope = {'scene': 'scene-0061', 'root': '/uploads/one', 'class_mode': 8}
    save(tmp_path, scene, tracks, {'speed': .5}, scope)
    restored, restored_tracks, config = load(tmp_path, scope)
    assert references(restored, restored_tracks, {'0': 'b', '1': 'b'}) == {0: 1, 1: 1}
    assert config == {'speed': .5}
    for selected in ({'1': 'a'}, {'9': 'a'}, {'0': 'other'}, {'-1': 'b'}):
        with pytest.raises(ValueError): references(scene, tracks, selected)
    with pytest.raises(ValueError): load(tmp_path, {**scope, 'root': '/uploads/other'})
    with (tmp_path / 'rigid-state.pkl.gz').open('ab') as file: file.write(b'corruption')
    with pytest.raises(ValueError): load(tmp_path, scope)

def test_postprocess_request_requires_source_and_valid_refs():
    for value in ({'references': {'0': 'a'}}, {'source_artifact_path': 'a.json'}, {'source_artifact_path': 'a.json', 'references': {'-1': 'a'}}):
        with pytest.raises(ValueError): AutoLabelRequest(scene_name='scene-0061', **value)
