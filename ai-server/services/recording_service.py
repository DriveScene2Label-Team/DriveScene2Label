import copy
import hashlib
import importlib.util
import json
import logging
import os
import re
import signal
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

from schemas.recording import RecordingEntities, RecordingRequest, RecordingResponse
from services.recording_exporter import APPLICATION_ID, ENTITIES, EXIT_LIDAR_MISSING, EXIT_SDK_MISSING, EXPORT_VERSION
from services.uploaded_dataset import UploadedDatasetCache
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)
SDK_VERSION = "0.38.1"  # Must match @rerun-io/web-viewer; bump together with export_version.


class RecordingError(RuntimeError):
    def __init__(self, status_code, code, message):
        super().__init__(message)
        self.status_code, self.code = status_code, code


class RecordingService:
    def __init__(self):
        project = Path(__file__).resolve().parents[2]
        # Preserve the venv interpreter path: resolving its symlink would bypass the venv.
        self.python = Path(os.environ.get("RECORDING_PYTHON", sys.executable)).absolute()
        self.data_root = Path(os.environ.get("NUSCENES_ROOT", os.environ.get("VESPA_DATA_ROOT", "/data/nuscenes"))).resolve()
        self.output_root = Path(os.environ.get("RECORDING_OUTPUT_ROOT", str(project / ".local/recordings"))).resolve()
        self.timeout = int(os.environ.get("RECORDING_TIMEOUT_SECONDS", "600"))
        self.uploaded_datasets = UploadedDatasetCache()
        if self.timeout <= 0:
            raise ValueError("RECORDING_TIMEOUT_SECONDS must be positive")

    def configured(self):
        sdk = self.python != Path(sys.executable).absolute() or importlib.util.find_spec("rerun") is not None
        return sdk and self.python.is_file() and self.data_root.is_dir()

    def for_dataset(self, key, version):
        if not re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", key) or version not in ("v1.0-mini", "v1.0-trainval"):
            raise RecordingError(422, "INVALID_DATASET", "Invalid uploaded dataset key/version.")
        try:
            root = self.uploaded_datasets.ensure(key)
        except (OSError, ValueError, zipfile.BadZipFile, BotoCoreError, ClientError) as error:
            raise RecordingError(503, "UPLOAD_STORAGE_UNAVAILABLE", "Uploaded dataset cache could not be prepared.") from error
        scoped = copy.copy(self)
        scoped.data_root = root
        return scoped

    def _lidar_path(self, relative):
        parts = PurePosixPath(relative).parts
        if relative.startswith(("/", "\\")) or "\\" in relative or ":" in relative or ".." in parts or not parts:
            raise RecordingError(422, "RECORDING_INVALID_PATH", "lidar relative_path must stay under the dataset root.")
        path = (self.data_root / relative).resolve()
        if not path.is_relative_to(self.data_root):
            raise RecordingError(422, "RECORDING_INVALID_PATH", "lidar relative_path must stay under the dataset root.")
        if not path.is_file():
            raise RecordingError(404, "RECORDING_LIDAR_NOT_FOUND", "A requested lidar file does not exist on the AI server.")
        return path

    def export(self, request: RecordingRequest):
        if request.dataset_key is not None:
            scoped = self.for_dataset(request.dataset_key, request.dataset_version)
            return scoped.export(request.model_copy(update={"dataset_key": None, "dataset_version": None}))
        if not self.configured():
            raise RecordingError(503, "RECORDING_NOT_CONFIGURED", "Install rerun-sdk and configure the dataset root first.")
        for sample in request.samples:
            if sample.lidar is not None:
                self._lidar_path(sample.lidar.relative_path)
        run_dir = self.output_root / f"{request.recording_id}-{request.execution_token}"
        output = run_dir / f"{request.scene_name}.rrd"
        logger.info("[RECORDING] recording=%s scene=%s job=%s samples=%s started", request.recording_id, request.scene_name, request.job_id, len(request.samples))
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "request.json").write_text(request.model_dump_json())
            summary_path = run_dir / "summary.json"
            summary_path.unlink(missing_ok=True)
            command = [str(self.python), str(Path(__file__).with_name("recording_exporter.py")),
                       "--request", str(run_dir / "request.json"), "--data-root", str(self.data_root),
                       "--output", str(output), "--summary", str(summary_path)]
            with (run_dir / "execution.log").open("wb") as log:
                with subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=(os.name == "posix")) as process:
                    try:
                        code = process.wait(timeout=self.timeout)
                    except subprocess.TimeoutExpired as exc:
                        if os.name == "posix":
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        else:
                            process.kill()
                        process.wait()
                        logger.error("Recording timeout: recording %s", request.recording_id)
                        raise RecordingError(504, "RECORDING_TIMEOUT", "Recording export exceeded the configured runtime limit.") from exc
        except OSError as exc:
            raise RecordingError(503, "RECORDING_LAUNCH_FAILED", "Could not launch the exporter or write its run files.") from exc
        if code == EXIT_SDK_MISSING:
            raise RecordingError(503, "RECORDING_SDK_UNAVAILABLE", "rerun-sdk is not installed in the exporter environment.")
        if code == EXIT_LIDAR_MISSING:
            raise RecordingError(404, "RECORDING_LIDAR_NOT_FOUND", "A requested lidar file does not exist on the AI server.")
        if code != 0:
            logger.error("Recording %s exporter exited with %s; see execution.log", request.recording_id, code)
            raise RecordingError(502, "RECORDING_EXPORT_FAILED", "Recording export failed; check the AI server run log.")
        try:
            summary = json.loads(summary_path.read_text())
            if summary["sdk_version"] != SDK_VERSION:
                raise RecordingError(503, "RECORDING_SDK_MISMATCH", f"Exporter rerun-sdk must be {SDK_VERSION}.")
            expected = [(s.index, s.sample_token, len(s.gt), len(s.predictions)) for s in request.samples]
            if [(r["index"], r["sample_token"], r["gt_boxes"], r["prediction_boxes"]) for r in summary["samples"]] != expected:
                raise ValueError("Sample order or box counts differ from the request")
            data = output.read_bytes()
            response = RecordingResponse(recording_id=request.recording_id, execution_token=request.execution_token,
                relative_path=output.relative_to(self.output_root).as_posix(), size_bytes=len(data),
                checksum=hashlib.sha256(data).hexdigest(), sdk_version=summary["sdk_version"], export_version=EXPORT_VERSION,
                application_id=APPLICATION_ID, rerun_recording_id=f"ds2l-recording-{request.recording_id}",
                entities=RecordingEntities(prediction=ENTITIES["prediction"] if request.job_id is not None else None),
                samples=summary["samples"])
        except RecordingError:
            raise
        except (OSError, KeyError, TypeError, ValueError) as exc:
            logger.exception("Invalid exporter output for recording %s", request.recording_id)
            raise RecordingError(502, "RECORDING_INVALID_RESULT", "Exporter output is missing or invalid.") from exc
        logger.info("[RECORDING] recording=%s completed bytes=%s", request.recording_id, response.size_bytes)
        return response
