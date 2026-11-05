import hashlib
import math
import sys
import time
from datetime import timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from routers import recording
from schemas.recording import RecordingRequest
from services.recording_service import RecordingError, RecordingService
from recording_fixtures import SENSOR_ROTATION, SENSOR_TRANSLATION, make_request, write_lidar

import rerun  # requirements.txt pins 0.38.1; a missing SDK must fail, not skip.
from rerun.chunk import RrdReader


@pytest.fixture
def service(tmp_path, monkeypatch):
    for key, value in {"NUSCENES_ROOT": tmp_path/"data", "RECORDING_OUTPUT_ROOT": tmp_path/"recordings",
                       "RECORDING_TIMEOUT_SECONDS": "120"}.items():
        monkeypatch.setenv(key, str(value))
    monkeypatch.delenv("RECORDING_PYTHON", raising=False)
    (tmp_path/"data").mkdir()
    return RecordingService()


@pytest.fixture
def client(service):
    # main.py needs torch/CLIP; this app mounts the same router and error format.
    app = FastAPI()
    app.state.recording_service = service
    app.include_router(recording.router)
    @app.exception_handler(RecordingError)
    async def handler(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": {"code": exc.code, "message": str(exc)}})
    return TestClient(app)


def read_back(path):
    """Per entity: sample index -> instance count, plus timelines and the stores in the file."""
    reader = RrdReader(path)
    counts, timelines, rows = {}, set(), {}
    for chunk in reader.store().stream():
        timelines.update(chunk.timeline_names)
        batch = chunk.to_record_batch()
        rows.setdefault(chunk.entity_path, []).append(batch)
        main = next((c for c in batch.schema.names if c.endswith((":half_sizes", ":positions"))), None)
        if main and "sample" in batch.schema.names:
            for index, values in zip(batch.column("sample").to_pylist(), batch.column(main).to_pylist()):
                counts.setdefault(chunk.entity_path, {})[index] = len(values)
    return reader.recordings(), counts, timelines, rows


def column(rows, entity, name, index):
    for batch in rows[entity]:
        if name in batch.schema.names and "sample" in batch.schema.names:
            for i, value in zip(batch.column("sample").to_pylist(), batch.column(name).to_pylist()):
                if i == index:
                    return value
    raise KeyError(name)


def test_real_export_with_predictions(service, tmp_path):
    body = make_request(tmp_path/"data", samples=4, gt=3, predictions=2, job_id=12, recording_id=5)
    body["samples"][2]["gt"], body["samples"][2]["predictions"] = [], []  # empty batch must clear latest-at
    body["samples"][3]["lidar"] = None
    result = service.export(RecordingRequest(**body))
    path = service.output_root / result.relative_path
    data = path.read_bytes()
    assert result.relative_path == "5-5a3e0000-0000-4000-8000-000000000001/scene-0000.rrd"
    assert result.size_bytes == len(data) and result.checksum == hashlib.sha256(data).hexdigest()
    assert result.sdk_version == rerun.__version__ == "0.38.1"
    assert (result.export_version, result.application_id, result.rerun_recording_id) == ("ds2l-rrd-v3", "drivescene2label", "ds2l-recording-5")
    assert result.entities.model_dump() == {"lidar": "world/lidar", "ego": "world/ego", "gt": "world/gt", "prediction": "world/prediction"}
    points = write_lidar(tmp_path/"count.bin")
    assert [(s.index, s.sample_token, s.lidar_points, s.gt_boxes, s.prediction_boxes) for s in result.samples] == [
        (0, "synthetic-sample-0", points, 3, 2), (1, "synthetic-sample-1", points, 3, 2),
        (2, "synthetic-sample-2", points, 0, 0), (3, "synthetic-sample-3", 0, 3, 2)]
    assert not list(path.parent.glob("*.tmp")) and (path.parent/"request.json").is_file()

    stores, counts, timelines, rows = read_back(path)
    assert [(s.application_id, s.recording_id) for s in stores] == [("drivescene2label", "ds2l-recording-5")]
    assert {"/world", "/world/lidar", "/world/ego", "/world/gt", "/world/prediction"} <= set(rows)
    assert timelines == {"sample", "timestamp"}
    assert counts["/world/gt"] == {0: 3, 1: 3, 2: 0, 3: 3}
    assert counts["/world/prediction"] == {0: 2, 1: 2, 2: 0, 3: 2}
    assert counts["/world/lidar"] == {0: points, 1: points, 2: points, 3: 0}
    assert column(rows, "/world/gt", "timestamp", 1).replace(tzinfo=timezone.utc).timestamp() == pytest.approx((1700000000000000 + 500000) / 1e6)
    assert column(rows, "/world/gt", "Boxes3D:labels", 0) == ["vehicle.car", "human.pedestrian.adult", "vehicle.car"]
    assert column(rows, "/world/prediction", "Boxes3D:labels", 0) == ["car", "pedestrian"]
    # v2: box names are data only; the decluttered text layer draws them (GT+prediction pairs share one label).
    assert column(rows, "/world/gt", "Boxes3D:show_labels", 0) == [False]
    assert column(rows, "/world/prediction", "Boxes3D:show_labels", 0) == [False]
    # GT+prediction pairs share one label in the "both" layer; the app hides gt/pred layers with its toggles.
    assert sorted(column(rows, "/world/labels/both", "Points3D:labels", 0)) == ["car", "pedestrian"]
    assert column(rows, "/world/labels/gt", "Points3D:labels", 0) == ["car"]  # third GT box has no matching prediction
    assert column(rows, "/world/labels/pred", "Points3D:labels", 0) == []
    for entity in ("/world/labels/gt", "/world/labels/pred", "/world/labels/both"):
        assert column(rows, entity, "Points3D:labels", 2) == [] and column(rows, entity, "Points3D:labels", 3) == []  # empty sample / no lidar

    box = body["samples"][1]["gt"][1]
    w, l, h = box["size_wlh"]
    qw, qx, qy, qz = box["rotation_wxyz"]
    assert column(rows, "/world/gt", "Boxes3D:half_sizes", 1)[1] == pytest.approx([l/2, w/2, h/2])
    assert column(rows, "/world/gt", "Boxes3D:quaternions", 1)[1] == pytest.approx([qx, qy, qz, qw], abs=1e-6)
    assert column(rows, "/world/gt", "Boxes3D:centers", 1)[1] == pytest.approx(box["center"])

    # First stored point (10,0,0): yaw+90 sensor -> ego (0.94, 10, 1.84), then ego yaw/translation -> world.
    lidar = body["samples"][1]["lidar"]
    a = 2*math.atan2(lidar["ego_rotation"][3], lidar["ego_rotation"][0])
    ex, ey, ez = 0.94, 10.0, 1.84
    expected = [math.cos(a)*ex - math.sin(a)*ey + lidar["ego_translation"][0], math.sin(a)*ex + math.cos(a)*ey + lidar["ego_translation"][1], ez]
    assert SENSOR_ROTATION[0] == pytest.approx(math.sqrt(0.5)) and SENSOR_TRANSLATION == [0.94, 0.0, 1.84]
    assert column(rows, "/world/lidar", "Points3D:positions", 1)[0] == pytest.approx(expected, abs=1e-3)
    ego = column(rows, "/world/ego", "Transform3D:translation", 1)[0]
    assert ego == pytest.approx(lidar["ego_translation"])


def test_without_job_has_no_prediction_entity(client, service, tmp_path):
    body = make_request(tmp_path/"data", samples=2, job_id=None)
    r = client.post("/recordings", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["entities"]["prediction"] is None
    assert [s["prediction_boxes"] for s in r.json()["samples"]] == [0, 0]
    _, counts, _, rows = read_back(service.output_root / r.json()["relative_path"])
    assert "/world/prediction" not in rows and counts["/world/gt"] == {0: 2, 1: 2}


def test_invalid_requests(client, tmp_path):
    base = make_request(tmp_path/"data", samples=2, job_id=None)
    bad = []
    for mutate in [lambda b: b["samples"][0]["gt"][0].update(rotation_wxyz=[2, 0, 0, 0]),
                   lambda b: b["samples"][0]["gt"][0].update(size_wlh=[0, 1, 1]),
                   lambda b: b["samples"][1].update(index=5),
                   lambda b: b["samples"][1].update(timestamp_us=0),
                   lambda b: b.update(scene_name="../scene"),
                   lambda b: b.update(unexpected=True),
                   lambda b: b["samples"][0].update(predictions=[{"id": 1, "detection_name": "car", "center": [0, 0, 0], "size_wlh": [1, 1, 1], "rotation_wxyz": [1, 0, 0, 0]}])]:
        body = make_request(tmp_path/"data", samples=2, job_id=None)
        mutate(body)
        bad.append(body)
    for path in ["../outside.pcd.bin", "/etc/passwd", "samples/../../outside.pcd.bin", "samples\\x.bin", "link.pcd.bin"]:
        body = make_request(tmp_path/"data", samples=2, job_id=None)
        body["samples"][0]["lidar"]["relative_path"] = path
        bad.append(body)
    (tmp_path/"outside.pcd.bin").write_bytes(b"\0"*20)
    (tmp_path/"data/link.pcd.bin").symlink_to(tmp_path/"outside.pcd.bin")
    for body in bad:
        r = client.post("/recordings", json=body)
        assert r.status_code == 422, (body, r.text)
        assert set(r.json()["detail"]) == {"code", "message"}
        assert r.json()["detail"]["code"] in {"RECORDING_INVALID_REQUEST", "RECORDING_INVALID_PATH"}
    assert client.post("/recordings", json=base).status_code == 200


def test_missing_and_corrupt_lidar(client, tmp_path):
    body = make_request(tmp_path/"data", samples=2, job_id=None)
    body["samples"][1]["lidar"]["relative_path"] = "samples/LIDAR_TOP/missing.pcd.bin"
    r = client.post("/recordings", json=body)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "RECORDING_LIDAR_NOT_FOUND"
    (tmp_path/"data/samples/LIDAR_TOP/corrupt.pcd.bin").write_bytes(b"\0"*21)
    body["samples"][1]["lidar"]["relative_path"] = "samples/LIDAR_TOP/corrupt.pcd.bin"
    r = client.post("/recordings", json=body)
    assert r.status_code == 502 and r.json()["detail"]["code"] == "RECORDING_EXPORT_FAILED"
    assert "Traceback" not in r.text


def fake_python(tmp_path, script):
    path = tmp_path/"fake-python"
    path.write_text("#!/bin/sh\n" + script + "\n")
    path.chmod(0o755)
    return path


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell fake interpreter")
@pytest.mark.parametrize("script,status,code", [("exec sleep 30", 504, "RECORDING_TIMEOUT"), ("exit 1", 502, "RECORDING_EXPORT_FAILED"),
                                                 ("exit 3", 503, "RECORDING_SDK_UNAVAILABLE"), ("exit 0", 502, "RECORDING_INVALID_RESULT")])
def test_subprocess_failures(client, service, tmp_path, script, status, code):
    service.python, service.timeout = fake_python(tmp_path, script), 1
    started = time.monotonic()
    r = client.post("/recordings", json=make_request(tmp_path/"data", samples=1, job_id=None))
    assert r.status_code == status and r.json()["detail"]["code"] == code, r.text
    assert time.monotonic() - started < 10


def test_not_configured(client, service, tmp_path):
    service.data_root = tmp_path/"absent"
    assert not service.configured()
    r = client.post("/recordings", json=make_request(tmp_path/"data", samples=1, job_id=None))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "RECORDING_NOT_CONFIGURED"


def test_main_wiring(service, tmp_path):
    pytest.importorskip("torch")
    from unittest.mock import patch
    from main import app  # adds embedding/ to sys.path for clip_core
    import clip_core
    with patch.object(clip_core, "load_model", return_value=(object(), None, None)):
        with TestClient(app) as c:
            app.state.recording_service = service
            assert c.get("/health").json()["inference"]["recording"] == "configured"
            r = c.post("/recordings", json=make_request(tmp_path/"data", samples=2, job_id=3))
            assert r.status_code == 200, r.text
            assert c.post("/recordings", json={"recording_id": 1}).json()["detail"]["code"] == "RECORDING_INVALID_REQUEST"


def box(cls, x, y, z=0.8, h=1.6, source="gt"):
    row = {"center": [x, y, z], "size_wlh": [1.0, 1.0, h], "rotation_wxyz": [1, 0, 0, 0]}
    row["category_name" if source == "gt" else "detection_name"] = cls
    return row


def test_label_layer_declutters():
    from services.recording_exporter import BOTH_COLOR, GT_COLOR, PREDICTION_COLOR, label_layer
    gt = [box("vehicle.car", 10, 0), box("human.pedestrian.adult", 20, 5, h=1.8), box("human.pedestrian.child", 21, 6),
          box("human.pedestrian.adult", 22, 7), box("movable_object.barrier", 15, -4), box(None, 12, 3), box("vehicle.car", 60, 0)]
    preds = [box("car", 10.5, 0.4, h=1.7, source="pred"), box("truck", 25, -6, source="pred")]
    out = {text: (pos, color, source) for pos, text, color, source in label_layer(gt, preds, (0.0, 0.0))}
    assert set(out) == {"car", "pedestrian ×3", "movable_object.barrier", "GT", "truck"}  # 60 m car has no label
    assert out["car"][1] == BOTH_COLOR and out["car"][0][2] == pytest.approx(0.8 + 1.7 / 2 + 0.6)  # higher top of the pair
    assert out["pedestrian ×3"][1] == GT_COLOR and out["pedestrian ×3"][0][:2] == pytest.approx([21, 6])
    assert out["truck"][1] == PREDICTION_COLOR
    assert {t: v[2] for t, v in out.items()} == {"car": "both", "pedestrian ×3": "gt", "movable_object.barrier": "gt", "GT": "gt", "truck": "pred"}


def test_label_layer_keeps_different_classes_and_far_pairs_apart():
    from services.recording_exporter import label_layer
    gt = [box("vehicle.car", 10, 0), box("vehicle.truck", 11, 0)]
    preds = [box("car", 13, 0, source="pred")]  # same class but 3 m away: not the same object, still one group within 4 m
    texts = sorted(t for _, t, _, _ in label_layer(gt, preds, (0.0, 0.0)))
    assert texts == ["car ×2", "truck"]
    assert label_layer(gt, preds, None) == []
