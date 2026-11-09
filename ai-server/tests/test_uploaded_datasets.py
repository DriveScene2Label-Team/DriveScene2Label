"""Uploaded dataset contract tests. No model weights, GPU or torch installation required."""
import json
import zipfile
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schemas.auto_label import AutoLabelRequest
from services.vespa_service import VespaService, VespaError
from services.capability_service import CapabilityService, CHECKSUM_TABLES
from routers.system import router
from services.uploaded_dataset import UploadedDatasetCache, extract_archive


@pytest.fixture
def uploaded(tmp_path, monkeypatch):
    key = str(uuid4())
    root = tmp_path / "datasets" / key / "v1.0-mini"
    root.mkdir(parents=True)
    for table in CHECKSUM_TABLES:
        (root / f"{table}.json").write_text("[]")
    (root / "scene.json").write_text(json.dumps([{"name": "scene-0061", "token": "scene"}]))
    (root / "sample.json").write_text(json.dumps([{"token": "sample", "scene_token": "scene"}]))
    repo = tmp_path / "repo"
    (repo / "configs/vlm").mkdir(parents=True)
    (repo / "configs/vlm/p_final.yaml").write_text("")
    (repo / "main_pseudo_vlm.py").write_text("")
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path))
    monkeypatch.setenv("VESPA_ROOT", str(repo))
    monkeypatch.setenv("VESPA_OUTPUT_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("VESPA_EXECUTOR", "local")
    monkeypatch.setenv("VESPA_PYTHON", sys.executable)
    return VespaService(), key, root.parent


def test_dataset_scope_preserves_default_and_shares_gpu_lock(uploaded):
    service, key, root = uploaded
    default = service.data_root
    scoped = service.for_dataset(key, "v1.0-mini")
    assert scoped.data_root == root
    assert scoped.configured()
    assert scoped.lock is service.lock
    assert service.data_root == default
    assert scoped._targets("scene-0061") == {"sample"}


@pytest.mark.parametrize("key", ["../escape", "/tmp/escape", r"..\escape", "not-a-uuid"])
def test_invalid_keys_never_select_a_directory(uploaded, key):
    service, _, _ = uploaded
    with pytest.raises(ValidationError):
        AutoLabelRequest(scene_name="scene-0061", dataset_key=key, dataset_version="v1.0-mini")
    with pytest.raises(VespaError):
        service.for_dataset(key, "v1.0-mini")


def test_request_requires_both_dataset_fields_and_local_executor(uploaded):
    service, key, _ = uploaded
    with pytest.raises(ValidationError):
        AutoLabelRequest(scene_name="scene-0061", dataset_key=key)
    service.executor = "ssh"
    with pytest.raises(VespaError, match="local GPU"):
        service.for_dataset(key, "v1.0-mini")


def test_generate_uses_uploaded_metadata_without_mutating_default(uploaded, monkeypatch):
    service, key, root = uploaded
    default = service.data_root
    def run(scoped, request, run_id, run_dir):
        assert scoped.data_root == root
        result = run_dir / "labels.json"
        result.write_text(json.dumps({"mapping_name": "8class", "split": "mini_train",
                                     "meta": {"use_camera": True}, "results": {"sample": []}}))
        return result
    monkeypatch.setattr(VespaService, "_run_local", run)
    result = service.generate(AutoLabelRequest(scene_name="scene-0061", dataset_key=key, dataset_version="v1.0-mini"))
    assert result.results == {"sample": []}
    assert service.data_root == default
    assert service.lock.acquire(blocking=False)
    service.lock.release()


def test_capabilities_are_cached_per_dataset_and_validate_route(uploaded, monkeypatch):
    service, key, _ = uploaded
    caps = CapabilityService(vespa_service=service)
    monkeypatch.setattr(CapabilityService, "_probe_vespa", lambda self: ("READY", None))
    app = FastAPI()
    app.state.capability_service = caps
    app.include_router(router)
    with TestClient(app) as client:
        params = {"dataset_key": key, "dataset_version": "v1.0-mini", "refresh": True}
        response = client.get("/capabilities", params=params)
        assert response.status_code == 200
        vespa = response.json()["vespa"]
        assert vespa["state"] == "READY"
        assert vespa["datasetKey"] == key
        assert len(vespa["metadataChecksum"]) == 64
        params["refresh"] = False
        assert client.get("/capabilities", params=params).json()["vespa"]["state"] == "READY"
        assert client.get("/capabilities", params={"dataset_key": key}).status_code == 422
        assert client.get("/capabilities", params={"dataset_key": "../bad", "dataset_version": "v1.0-mini"}).status_code == 422


def test_s3_cache_downloads_once_and_publishes_only_complete_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("UPLOAD_S3_BUCKET", "contract-test-bucket")
    key = str(uuid4())
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("samples/image.jpg", b"fixture-image")
    calls = []
    class Client:
        def head_object(self, **kwargs):
            assert kwargs == {"Bucket": "contract-test-bucket", "Key": f"uploads/{key}.zip"}
            return {"ContentLength": archive.stat().st_size}
        def download_file(self, bucket, object_key, filename, **kwargs):
            calls.append(object_key)
            shutil.copyfile(archive, filename)
    cache = UploadedDatasetCache()
    cache.client = Client()
    target = cache.ensure(key)
    assert (target / "samples/image.jpg").read_bytes() == b"fixture-image"
    assert cache.ensure(key) == target
    assert calls == [f"uploads/{key}.zip"]


@pytest.mark.parametrize("name,size,limit", [("../outside", 1, 100), ("file.bin", 101, 100)])
def test_archive_rejects_escape_and_excessive_expansion(tmp_path, name, size, limit):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(name, b"x" * size)
    root = tmp_path / "data"
    root.mkdir()
    with pytest.raises(ValueError):
        extract_archive(archive, root, limit)
    assert not (tmp_path / "outside").exists()
