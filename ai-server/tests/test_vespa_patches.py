"""DriveScene2Label VESPA patches (ai-server/vespa-patches).

The visibility filter is a new file inside patch 0002; its source is taken from the patch itself so these
tests check exactly what Docker and Colab apply. Applying the patches to a real checkout is checked only
when VESPA_SRC points to a VESPA clone (no network access in unit tests).
"""
import os
import shutil
import subprocess
import types
from pathlib import Path

import numpy as np
import pytest

PATCH_DIR = Path(__file__).resolve().parents[1] / "vespa-patches"
VESPA_REF = "acb2b6e8683363795528f049fe0444ef9f3efdb9"


def test_environment_has_no_conflicting_duplicate_pins():
    pins = {}
    for line in (PATCH_DIR.parent / 'requirements-vespa.txt').read_text().splitlines():
        if '==' not in line or line.lstrip().startswith('#'):
            continue
        name, version = line.split('==', 1)
        normalized = name.strip().lower().replace('_', '-')
        assert normalized not in pins, f'Duplicate dependency pin: {normalized}'
        pins[normalized] = version.strip()


def _new_file_from_patch(patch: Path, path: str) -> str:
    lines = patch.read_text().splitlines()
    start = lines.index(f"+++ b/{path}")
    body = []
    for line in lines[start + 2:]:  # skip "+++" and the "@@" hunk header
        if not line.startswith("+"):
            break
        body.append(line[1:])
    return "\n".join(body) + "\n"


@pytest.fixture(scope="module")
def vf():
    source = _new_file_from_patch(PATCH_DIR / "0002-visibility-filter.patch", "src/pointcloud/visibility_filter.py")
    module = types.ModuleType("visibility_filter")
    exec(compile(source, "visibility_filter.py", "exec"), module.__dict__)
    return module


def test_occluded_points_behind_the_nearest_surface_are_dropped(vf):
    uv = np.array([[10, 10], [11, 12], [12, 11], [40, 40]], float)  # first three share one 8 px cell
    depth = np.array([10.0, 10.4, 25.0, 30.0])                       # 25 m point is hidden behind the 10 m surface
    keep = vf.occlusion_mask(depth, uv, cell_px=8, margin_m=1.5)
    assert keep.tolist() == [True, True, False, True]                # 30 m point is alone in its cell: kept


def test_points_deeper_than_the_class_allows_are_dropped(vf):
    depth = np.r_[np.full(20, 10.0), 10.5, 13.0, 30.0]
    keep = vf.depth_extent_mask(depth, max_extent_m=5.0, near_percentile=5)
    assert keep.tolist() == [True] * 22 + [False]


def test_filter_combines_both_and_never_returns_empty(vf):
    uv = np.array([[0, 0], [100, 100], [200, 200]], float)
    depth = np.array([8.0, 9.0, 40.0])
    assert vf.filter_object_points(depth, uv, max_extent_m=5.0).tolist() == [True, True, False]
    one = vf.filter_object_points(np.array([12.0]), np.array([[3.0, 3.0]]), max_extent_m=0.1)
    assert one.tolist() == [True]
    assert vf.filter_object_points(np.zeros(0), np.zeros((0, 2)), 5.0).shape == (0,)


def test_no_class_info_skips_depth_extent_only(vf):
    uv = np.array([[0, 0], [100, 100]], float)
    assert vf.filter_object_points(np.array([5.0, 80.0]), uv, max_extent_m=None).tolist() == [True, True]


def test_class_max_extent_is_the_footprint_diagonal(vf):
    info = types.SimpleNamespace(length_max=12.0, width_max=2.7)
    assert vf.class_max_extent({"truck": info}, "truck") == pytest.approx(np.hypot(12.0, 2.7))
    assert vf.class_max_extent({}, "unknown") is None


def test_camera_depth_matches_the_camera_z_axis(vf):
    lidar_to_cam = np.array([[0, -1, 0, 0], [0, 0, -1, 0], [1, 0, 0, 0], [0, 0, 0, 1.]])  # camera looks along lidar +x
    K = np.array([[500, 0, 400, 0], [0, 500, 300, 0], [0, 0, 1, 0.]])
    points = np.array([[10.0, 1.0, 0.5], [3.0, -2.0, 0.0]])
    depth = vf.camera_depth(points, np.eye(4), np.eye(4)[None], K[None], lidar_to_cam[None], np.eye(4))
    assert depth.tolist() == pytest.approx([10.0, 3.0])


def test_class_patch_adds_barrier_and_traffic_cone():
    patch = (PATCH_DIR / "0001-classes-barrier-cone.patch").read_text()
    assert '"barrier", "traffic cone"]' in patch                    # GroundingDINO prompts
    assert '"bicycle", "barrier", "traffic_cone"]' in patch          # 8class output classes
    assert '+  movable_object.trafficcone: "traffic_cone"' in patch  # nuScenes GT mapping


@pytest.mark.skipif(not os.environ.get("VESPA_SRC") or not shutil.which("git"), reason="set VESPA_SRC to a VESPA clone")
def test_patches_apply_to_a_clean_pinned_checkout(tmp_path):
    work = tmp_path / "vespa"
    subprocess.run(["git", "clone", "-q", "--no-checkout", os.environ["VESPA_SRC"], str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "checkout", "-q", VESPA_REF], check=True)
    run = lambda ref: subprocess.run(["bash", str(PATCH_DIR / "apply.sh"), str(work), ref], capture_output=True, text=True)
    assert run(VESPA_REF).returncode == 0
    assert (work / "src/pointcloud/visibility_filter.py").is_file()
    again = run(VESPA_REF)
    assert again.returncode == 1 and "not clean" in again.stderr
