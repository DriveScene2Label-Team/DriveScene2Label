"""GET /capabilities and the non-fatal CLIP startup (IN-03/IN-04). Checks never start inference or sbatch."""
import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.capability_service import CapabilityService, metadata_checksum, EXPECTED_RERUN
from services.vespa_service import VespaService
from services.recording_service import RecordingService

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "src/test/resources/nuscenes/v1.0-mini"


def _script(path, body):
    path.write_text(body); path.chmod(0o755)


@pytest.fixture
def env(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; (repo / "configs/vlm").mkdir(parents=True)
    (repo / "configs/vlm/p_final.yaml").write_text("type: vlm\n")
    (repo / "main_pseudo_union.py").write_text("X = 1\n")
    (repo / "main_pseudo_vlm.py").write_text("import main_pseudo_union\n")
    data = tmp_path / "data"; (data / "v1.0-mini").mkdir(parents=True)
    for f in FIXTURE.glob("*.json"):
        (data / "v1.0-mini" / f.name).write_bytes(f.read_bytes())
    for key, value in {"VESPA_ROOT": repo, "VESPA_PYTHON": sys.executable, "VESPA_DATA_ROOT": data, "NUSCENES_ROOT": data,
                       "VESPA_DATASET_VERSION": "v1.0-mini", "VESPA_OUTPUT_ROOT": tmp_path / "runs",
                       "RECORDING_OUTPUT_ROOT": tmp_path / "recordings", "VESPA_EXECUTOR": "local"}.items():
        monkeypatch.setenv(key, str(value))
    return tmp_path


class Clip:
    model = object()
    device = "cpu"


def test_checksum_matches_spring_importer():
    # Spring imported this exact fixture and stored dataset.source_checksum = 1c6245… (2026-10-04 live run).
    assert metadata_checksum(FIXTURE) == "1c624507d9191a58b13cd3ca64c960c9047c84ddd3c1b5e2db3a3da9463f6c39"
    assert metadata_checksum(FIXTURE.parent / "missing") is None


def test_vespa_configured_is_not_ready_until_refresh(env):
    svc = CapabilityService(Clip(), VespaService(), RecordingService())
    with patch.object(VespaService, "generate", side_effect=AssertionError("must not run inference")):
        vespa = svc.snapshot()["vespa"]
        assert (vespa["state"], vespa["reasonCode"], vespa["executor"]) == ("CONFIGURED", "EXECUTOR_NOT_CHECKED", "local")
        vespa = svc.snapshot(refresh=True)["vespa"]
    assert (vespa["state"], vespa["reasonCode"]) == ("READY", None)
    assert vespa["metadataChecksum"] == metadata_checksum(FIXTURE)
    assert vespa["expiresAt"] and vespa["datasetVersion"] == "v1.0-mini"
    assert not (env / "runs").exists() or not any((env / "runs").iterdir())  # no VESPA run directory created
    # cached READY is reused without refresh until it expires
    assert svc.snapshot()["vespa"]["state"] == "READY"
    svc.vespa_check["expiresAtTs"] = 0
    assert svc.snapshot()["vespa"]["state"] == "CONFIGURED"


def test_vespa_broken_runtime_and_unconfigured(env):
    (env / "repo/main_pseudo_vlm.py").write_text("raise ImportError('missing dependency')\n")
    svc = CapabilityService(Clip(), VespaService(), RecordingService())
    vespa = svc.snapshot(refresh=True)["vespa"]
    assert (vespa["state"], vespa["reasonCode"]) == ("UNAVAILABLE", "VESPA_RUNTIME_NOT_READY")
    (env / "repo/configs/vlm/p_final.yaml").unlink()
    assert svc.snapshot()["vespa"]["reasonCode"] == "VESPA_NOT_CONFIGURED"


@pytest.mark.parametrize("exit_code,state,reason", [(0, "READY", None), (255, "UNAVAILABLE", "VESPA_REMOTE_UNREACHABLE"), (1, "UNAVAILABLE", "VESPA_REMOTE_NOT_READY")])
def test_vespa_ssh_probe_is_read_only(env, monkeypatch, exit_code, state, reason):
    log = env / "ssh_args"
    _script(env / "fake-ssh", f'#!/usr/bin/env bash\necho "$@" >> {log}\nexit {exit_code}\n')
    for key, value in {"VESPA_EXECUTOR": "ssh", "VESPA_SSH_BIN": env / "fake-ssh", "VESPA_SSH_TARGET": "user@fake-host",
                       "VESPA_SSH_REMOTE_ROOT": "/remote/VESPA"}.items():
        monkeypatch.setenv(key, str(value))
    svc = CapabilityService(Clip(), VespaService(), RecordingService())
    vespa = svc.snapshot(refresh=True)["vespa"]
    assert (vespa["state"], vespa["reasonCode"], vespa["executor"]) == (state, reason, "ssh")
    sent = log.read_text()
    assert "command -v sbatch" in sent and "sbatch --" not in sent and "pseudo_scenes_lowmem.sh &&" not in sent.replace("test -f pseudo_scenes_lowmem.sh &&", "")


def test_recording_probe(env, tmp_path):
    svc = CapabilityService(Clip(), VespaService(), RecordingService())
    rec = svc.snapshot()["recording"]
    try:
        import rerun
        expected = ("READY", None) if rerun.__version__ == EXPECTED_RERUN else ("UNAVAILABLE", "RECORDING_SDK_MISMATCH")
    except ImportError:
        expected = ("UNAVAILABLE", "RECORDING_SDK_UNAVAILABLE")
    assert (rec["state"], rec["reasonCode"]) == expected
    fake = tmp_path / "fake-python"
    _script(fake, "#!/usr/bin/env bash\necho 0.21.0\n")
    svc.recording.python = fake
    rec = svc.snapshot(refresh=True)["recording"]
    assert (rec["state"], rec["reasonCode"], rec["sdkVersion"]) == ("UNAVAILABLE", "RECORDING_SDK_MISMATCH", "0.21.0")


def test_missing_services_are_unavailable_not_ready():
    snap = CapabilityService().snapshot()
    assert snap["schemaVersion"] == 1
    assert [snap[k]["state"] for k in ("clip", "vespa", "recording")] == ["UNAVAILABLE"] * 3
    assert snap["clip"]["reasonCode"] == "CLIP_NOT_DEPLOYED"


def test_uploaded_recording_capability_is_scoped_without_default_dataset(env, monkeypatch):
    key = "00000000-0000-4000-8000-000000000001"
    upload = env / "uploads" / "datasets" / key
    upload.mkdir(parents=True)
    monkeypatch.setenv("UPLOAD_ROOT", str(env / "uploads"))
    monkeypatch.setenv("UPLOAD_S3_BUCKET", "")
    monkeypatch.setenv("NUSCENES_ROOT", str(env / "missing-default"))
    svc = CapabilityService(recording_service=RecordingService())
    assert svc.snapshot()["recording"]["state"] == "UNAVAILABLE"
    assert svc.snapshot(dataset_key=key, dataset_version="v1.0-mini")["recording"]["state"] == "READY"
    assert svc.snapshot()["recording"]["state"] == "UNAVAILABLE"


def test_clip_failure_keeps_exporter_and_capabilities(env, monkeypatch):
    torch = pytest.importorskip("torch")  # main.py imports the CLIP stack
    from fastapi.testclient import TestClient
    from main import app  # adds the shared embedding/ module path
    import clip_core
    with patch.object(clip_core, "load_model", side_effect=RuntimeError("weights unavailable")):
        with TestClient(app) as client:
            assert client.get("/livez").json()["status"] == "alive"
            health = client.get("/health")
            assert health.status_code == 503 and health.json()["inference"]["clip"] == "not_ready"
            caps = client.get("/capabilities").json()
            assert (caps["clip"]["state"], caps["clip"]["reasonCode"]) == ("UNAVAILABLE", "CLIP_LOAD_FAILED")
            assert caps["vespa"]["state"] == "CONFIGURED"
            assert client.post("/embedding/text", json={"text": "rain"}).json()["detail"]["code"] == "CLIP_NOT_READY"
            # the recording route is still served (validation error, not a dead server)
            assert client.post("/recordings", json={}).status_code == 422
    monkeypatch.setenv("AI_REQUIRE_CLIP", "true")
    with patch.object(clip_core, "load_model", side_effect=RuntimeError("weights unavailable")):
        with pytest.raises(RuntimeError, match="weights unavailable"):
            with TestClient(app):
                pass
    del torch
