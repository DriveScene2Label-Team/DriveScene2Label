"""Small real VESPA CPU replay; run in the VESPA environment, without GPU inference."""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import numpy as np
import pytest

REPO = Path(os.environ.get('VESPA_ROOT', '/opt/vespa'))
pytestmark = pytest.mark.skipif(not (REPO / 'main_pseudo_vlm.py').is_file(), reason='Requires the VESPA runtime')

def test_real_cached_replay_matches_baseline_and_preserves_bottom_center(tmp_path):
    np.__dict__.setdefault('bool', np.bool_)
    np.__dict__.setdefault('atan2', np.arctan2)
    np.__dict__.setdefault('concat', np.concatenate)
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(project))
    import src
    src.__path__.append(str(project / 'vespa-remote/src'))
    sys.path.insert(0, str(project / 'vespa-remote'))
    from src.structures import Frame, Scene, Object
    from src.labeling.assign_labels import assign_pseudo_class_labels_from_sam_label, get_scene_pseudo_annotations_by_mapping
    from src.labeling.submission import _get_annotation_dict
    from main_pseudo_vlm_scene_ver2 import finish_scene_rigid
    from services.rigid_cache import save, checksum
    frames = []
    for index in range(3):
        pose = np.eye(4); pose[:3, 3] = [10+index, 3, .25]
        yaw = 0 if index == 0 else .8
        pose[:2, :2] = [[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]]
        obj = Object(np.zeros((10, 3)), pose, (4., 2., 2.) if index == 0 else (2., 1., 1.), sam_label='car', velocity=(2., 0.))
        frames.append(Frame(True, np.zeros((10, 3)), index*.5, {}, {}, {}, np.eye(4), [], f'sample-{index}', objects=[obj]))
    scene = Scene('scene-0061', .5, np.eye(4), {}, {}, frames, 'mini_train')
    tracks = [[(0, 0), (1, 0), (2, 0)]]
    config = {'yaw_heuristic': {'speed_threshold': .5}, 'object_filtering': None}
    baseline, _, ids = finish_scene_rigid(scene, tracks, config, {})
    original = get_scene_pseudo_annotations_by_mapping(assign_pseudo_class_labels_from_sam_label(scene))
    serial = lambda value: {t: [_get_annotation_dict(box, t) for box in boxes] for t, boxes in value['8class'].items()}
    assert serial(baseline) == serial(original)
    assert ids['track_ids'] == {f'sample-{i}': [0] for i in range(3)}
    source = tmp_path / str(uuid4()); source.mkdir()
    scope = {'scene': 'scene-0061', 'root': '/fixture', 'version': 'v1.0-mini', 'class_mode': 8}
    save(source, scene, tracks, config, scope)
    before = checksum(source / 'rigid-state.pkl.gz')
    output = tmp_path / str(uuid4()); output.mkdir()
    refs = output / 'references.json'; refs.write_text(json.dumps({'0': 'sample-0'}))
    command = [sys.executable, str(project / 'services/vespa_runner.py'), '--repo', str(REPO), '--config', str(REPO / 'configs/vlm/p_final.yaml'),
               '--scene', 'scene-0061', '--class-mode', '8', '--output-root', str(output), '--data-root', '/fixture', '--dataset-version', 'v1.0-mini',
               '--rigid', '--source-run', str(source), '--references', str(refs)]
    process = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert process.returncode == 0, process.stderr
    result = json.loads((output / 'outs/vlm/p_final/#out_labels/vlm_p_final_scene-0061_8class.json').read_text())
    for index in range(3):
        box = result['results'][f'sample-{index}'][0]
        assert box['track_id'] == 0
        assert box['size'] == [2., 4., 2.]
        assert np.allclose(box['translation'], [10+index, 3, 1.25])
        assert np.allclose(box['rotation'], [1, 0, 0, 0])
    assert checksum(source / 'rigid-state.pkl.gz') == before
    assert (output / 'rigid-manifest.json').is_file()
    # No stage cache was generated: replay does not run the detector or load source sensor files.
    assert not (output / 'outs/vlm/p_final/02_grounding_sam').exists()
