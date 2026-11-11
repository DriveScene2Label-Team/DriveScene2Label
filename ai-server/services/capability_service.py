"""Per-feature readiness for Spring (GET /capabilities). Internal only; the browser never calls the AI server.

States: READY (light required checks passed), CONFIGURED (settings present, runtime/connection not checked),
UNAVAILABLE (missing/failed), UNKNOWN is left to Spring for an unreachable AI. A check never starts inference,
sbatch, embedding generation or imports: VESPA is checked by importing its entry module (local) or by read-only
`test`/`command -v` over SSH, and only when refresh=true. Results are cached per process with an expiry.
"""
import hashlib
import logging
import os
import subprocess
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from services.gpu_health import gpu_available

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
EXPECTED_RERUN = "0.38.1"
EXPORT_VERSION = "ds2l-rrd-v1"
# Same order Spring's NuscenesImporter hashes (ImportSchema.TABLES): sha256(name + bytes) for each table.
CHECKSUM_TABLES = ("log", "map", "scene", "sample", "sensor", "calibrated_sensor", "ego_pose", "sample_data",
                   "category", "instance", "visibility", "attribute", "sample_annotation")


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z") if ts else None


def metadata_checksum(version_dir: Path):
    """sha256 compatible with Spring's dataset.source_checksum. Returns None if any table is missing."""
    digest = hashlib.sha256()
    for table in CHECKSUM_TABLES:
        path = version_dir / f"{table}.json"
        if not path.is_file():
            return None
        digest.update(table.encode())
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
    return digest.hexdigest()


class CapabilityService:
    def __init__(self, clip_service=None, vespa_service=None, recording_service=None, clip_error=None):
        self.clip, self.vespa, self.recording = clip_service, vespa_service, recording_service
        self.clip_error = clip_error
        self.ttl = float(os.environ.get("CAPABILITY_TTL_SECONDS", "600"))
        self.vespa_check_timeout = float(os.environ.get("VESPA_CHECK_TIMEOUT_SECONDS", "60"))
        self.check_lock = Lock()          # one VESPA readiness check at a time (single flight)
        self.vespa_check = None           # {"state","reasonCode","checkedAt","expiresAt"}
        self.recording_check = None
        self.checksum_cache = {}          # version dir -> (stamp, checksum)
        self.dataset_services = OrderedDict()
        self.dataset_lock = Lock()

    # ---------------- public ----------------
    def snapshot(self, refresh=False, dataset_key=None, dataset_version=None):
        if dataset_key is not None:
            with self.dataset_lock:
                key = (dataset_key, dataset_version)
                scoped = self.dataset_services.get(key)
                if scoped is None:
                    scoped = CapabilityService(self.clip, self.vespa.for_dataset(*key), None, self.clip_error)
                    self.dataset_services[key] = scoped
                self.dataset_services.move_to_end(key)
                if len(self.dataset_services) > 32:
                    self.dataset_services.popitem(last=False)
            result = scoped.snapshot(refresh)
            result["vespa"]["datasetKey"] = dataset_key
            return result
        now = time.time()
        return {
            "schemaVersion": SCHEMA_VERSION,
            "service": "drivescene-ai",
            "checkedAt": _iso(now),
            "clip": self._clip(),
            "vespa": self._vespa(refresh, now),
            "recording": self._recording(refresh, now),
        }

    # ---------------- CLIP ----------------
    def _clip(self):
        base = {"modelName": None, "imagePreprocess": [], "textPreprocess": "clip-text-tokenizer", "dimension": None, "device": None}
        if not gpu_available():
            return {"state": "UNAVAILABLE", "reasonCode": "GPU_UNAVAILABLE", **base}
        if self.clip is None:
            return {"state": "UNAVAILABLE", "reasonCode": "CLIP_NOT_DEPLOYED", **base}
        try:
            import clip_core  # noqa: imported lazily so a recording-only process does not need torch
            base.update(modelName=f"{clip_core.MODEL_NAME}/{clip_core.PRETRAINED}", imagePreprocess=list(clip_core.PREPROCESS_MODES),
                        dimension=clip_core.EMBED_DIM, device=self.clip.device)
        except Exception:  # pragma: no cover - environment specific
            pass
        if self.clip.model is not None:
            return {"state": "READY", "reasonCode": None, **base}
        return {"state": "UNAVAILABLE", "reasonCode": self.clip_error or "MODEL_NOT_READY", **base}

    # ---------------- VESPA ----------------
    def _vespa(self, refresh, now):
        if self.vespa is None:
            return {"state": "UNAVAILABLE", "reasonCode": "VESPA_NOT_DEPLOYED", "executor": None, "datasetVersion": None,
                    "metadataChecksum": None, "checkedAt": None, "expiresAt": None}
        v = self.vespa
        out = {"executor": v.executor, "datasetVersion": v.version, "metadataChecksum": None}
        if v.executor == "local" and not gpu_available():
            return {**out, "state": "UNAVAILABLE", "reasonCode": "GPU_UNAVAILABLE", "checkedAt": _iso(now), "expiresAt": None}
        if not v.configured():
            self.vespa_check = None
            return {**out, "state": "UNAVAILABLE", "reasonCode": "VESPA_NOT_CONFIGURED", "checkedAt": _iso(now), "expiresAt": None}
        if refresh:
            self._run_vespa_check(now)
        check = self.vespa_check
        if check and check["expiresAtTs"] > now:
            out["metadataChecksum"] = check.get("metadataChecksum")
            return {**out, "state": check["state"], "reasonCode": check["reasonCode"],
                    "checkedAt": _iso(check["checkedAtTs"]), "expiresAt": _iso(check["expiresAtTs"])}
        return {**out, "state": "CONFIGURED", "reasonCode": "EXECUTOR_NOT_CHECKED", "checkedAt": _iso(now), "expiresAt": None}

    def _run_vespa_check(self, now):
        # Single flight: a concurrent refresh waits for the running check and reuses its result.
        acquired = self.check_lock.acquire(timeout=self.vespa_check_timeout + 5)
        try:
            if not acquired:
                return
            if self.vespa_check and self.vespa_check["checkedAtTs"] >= now:
                return
            state, reason = self._probe_vespa()
            checksum = self._dataset_checksum() if state == "READY" else None
            started = time.time()
            self.vespa_check = {"state": state, "reasonCode": reason, "metadataChecksum": checksum,
                                "checkedAtTs": started, "expiresAtTs": started + (self.ttl if state == "READY" else 60)}
        finally:
            if acquired:
                self.check_lock.release()

    def _probe_vespa(self):
        v = self.vespa
        try:
            if v.executor == "ssh":
                root = v.ssh_remote_root
                remote = (f"cd {_q(root)} && test -f {_q(v.ssh_script)} && test -d configs "
                          f"&& command -v sbatch >/dev/null && command -v squeue >/dev/null")
                proc = subprocess.run(v._ssh_command(remote), capture_output=True, timeout=min(v.ssh_command_timeout, 30))
                if proc.returncode == 255:
                    return "UNAVAILABLE", "VESPA_REMOTE_UNREACHABLE"
                return ("READY", None) if proc.returncode == 0 else ("UNAVAILABLE", "VESPA_REMOTE_NOT_READY")
            code = f"import sys; sys.path.insert(0, {str(v.repo)!r}); import main_pseudo_vlm, main_pseudo_union"
            proc = subprocess.run([str(v.python), "-c", code], cwd=v.repo, capture_output=True, timeout=self.vespa_check_timeout)
            if proc.returncode != 0:
                logger.warning("VESPA runtime check failed: %s", proc.stderr.decode(errors="replace")[-400:])
                return "UNAVAILABLE", "VESPA_RUNTIME_NOT_READY"
            return "READY", None
        except subprocess.TimeoutExpired:
            return "UNAVAILABLE", "VESPA_REMOTE_UNREACHABLE" if v.executor == "ssh" else "VESPA_CHECK_TIMEOUT"
        except OSError:
            return "UNAVAILABLE", "VESPA_RUNTIME_NOT_READY"

    def _dataset_checksum(self):
        version_dir = self.vespa.data_root / self.vespa.version
        try:
            stamp = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(version_dir.glob("*.json")))
        except OSError:
            return None
        cached = self.checksum_cache.get(str(version_dir))
        if cached and cached[0] == stamp:
            return cached[1]
        checksum = metadata_checksum(version_dir)
        self.checksum_cache[str(version_dir)] = (stamp, checksum)
        return checksum

    # ---------------- recording ----------------
    def _recording(self, refresh, now):
        base = {"expectedSdkVersion": EXPECTED_RERUN, "exportVersion": EXPORT_VERSION, "sdkVersion": None}
        r = self.recording
        if r is None:
            return {**base, "state": "UNAVAILABLE", "reasonCode": "RECORDING_NOT_DEPLOYED", "checkedAt": None, "expiresAt": None}
        check = self.recording_check
        if refresh or not check or check["expiresAtTs"] <= now:
            check = self.recording_check = self._probe_recording(now)
        return {**base, "sdkVersion": check["sdkVersion"], "state": check["state"], "reasonCode": check["reasonCode"],
                "checkedAt": _iso(check["checkedAtTs"]), "expiresAt": _iso(check["expiresAtTs"])}

    def _probe_recording(self, now):
        r = self.recording

        def result(state, reason, sdk=None):
            return {"state": state, "reasonCode": reason, "sdkVersion": sdk, "checkedAtTs": now,
                    "expiresAtTs": now + (self.ttl if state == "READY" else 60)}
        if not r.python.is_file() or not r.data_root.is_dir():
            return result("UNAVAILABLE", "RECORDING_NOT_CONFIGURED")
        try:
            proc = subprocess.run([str(r.python), "-c", "import rerun; print(rerun.__version__)"], capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return result("UNAVAILABLE", "RECORDING_SDK_UNAVAILABLE")
        if proc.returncode != 0:
            return result("UNAVAILABLE", "RECORDING_SDK_UNAVAILABLE")
        sdk = proc.stdout.decode().strip()
        if sdk != EXPECTED_RERUN:
            return result("UNAVAILABLE", "RECORDING_SDK_MISMATCH", sdk)
        try:
            r.output_root.mkdir(parents=True, exist_ok=True)
            writable = os.access(r.output_root, os.W_OK)
        except OSError:
            writable = False
        if not writable:
            return result("UNAVAILABLE", "RECORDING_OUTPUT_NOT_WRITABLE", sdk)
        return result("READY", None, sdk)


def _q(value):
    import shlex
    return shlex.quote(str(value))
