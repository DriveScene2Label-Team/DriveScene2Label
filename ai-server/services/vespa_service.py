import hashlib
import copy
import re
import json
import logging
import os
import shlex
import signal
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from threading import Lock
from uuid import uuid4

from schemas.auto_label import AutoLabelRequest, AutoLabelResponse
from services.uploaded_dataset import UploadedDatasetCache
from services.gpu_health import gpu_available
from botocore.exceptions import BotoCoreError, ClientError

# Child of uvicorn.error so INFO progress lines (slurm job id, state) reach the server log.
logger = logging.getLogger("uvicorn.error").getChild("vespa")
CLASSES = {1: {"vehicle"}, 3: {"vehicle", "pedestrian", "bicycle"},
           8: {"car", "truck", "bus", "trailer", "construction_vehicle", "pedestrian", "motorcycle", "bicycle"}}
EXECUTORS = ("local", "ssh")
SSH_UNREACHABLE = 255  # ssh's own exit code when the connection itself fails
SSH_MAX_POLL_FAILURES = 5
SSH_OUTPUT_CHECKS = 3  # the login node's NFS cache can lag behind the compute node briefly

class VespaError(RuntimeError):
    def __init__(self, status_code, code, message):
        super().__init__(message)
        self.status_code, self.code = status_code, code

class VespaService:
    """Runs VESPA for one scene and validates its final JSON.

    VESPA_EXECUTOR selects where VESPA runs; validation and the response are shared:
    - local (default): subprocess in this container/host via vespa_runner.py.
    - ssh: Slurm job on a remote cluster (sbatch over SSH), then the per-scene JSON is copied back.
    """

    def __init__(self):
        project = Path(__file__).resolve().parents[2]
        self.executor = os.environ.get("VESPA_EXECUTOR", "local").strip().lower()
        if self.executor not in EXECUTORS:
            raise ValueError(f"VESPA_EXECUTOR must be one of {EXECUTORS}")
        self.repo = Path(os.environ.get("VESPA_ROOT", str(project / ".local/VESPA"))).resolve()
        # Preserve the venv interpreter path: resolving its symlink would bypass the venv.
        self.python = Path(os.environ.get("VESPA_PYTHON", sys.executable)).absolute()
        self.data_root = Path(os.environ.get("VESPA_DATA_ROOT", os.environ.get("NUSCENES_ROOT", "/data/nuscenes"))).resolve()
        self.version = os.environ.get("VESPA_DATASET_VERSION", "v1.0-trainval")
        self.output_root = Path(os.environ.get("VESPA_OUTPUT_ROOT", str(project / ".local/vespa-runs"))).resolve()
        self.timeout = int(os.environ.get("VESPA_TIMEOUT_SECONDS", "7200"))
        if self.timeout <= 0 or self.version not in ("v1.0-mini", "v1.0-trainval"):
            raise ValueError("Invalid VESPA timeout/dataset version")
        self.num_threads = int(os.environ.get("VESPA_NUM_THREADS", "1"))
        if self.num_threads <= 0:
            raise ValueError("VESPA_NUM_THREADS must be positive")
        # SSH executor. Connection details stay in .env / ~/.ssh, never in the repository.
        self.ssh_bin = os.environ.get("VESPA_SSH_BIN", "ssh")
        self.ssh_target = os.environ.get("VESPA_SSH_TARGET", "").strip()
        self.ssh_port = os.environ.get("VESPA_SSH_PORT", "").strip()
        self.ssh_key = os.environ.get("VESPA_SSH_KEY", "").strip()
        self.ssh_known_hosts = os.environ.get("VESPA_SSH_KNOWN_HOSTS", "").strip()
        self.ssh_remote_root = os.environ.get("VESPA_SSH_REMOTE_ROOT", "").strip()
        self.ssh_exp = os.environ.get("VESPA_SSH_EXP", "p_final").strip()
        self.ssh_script = os.environ.get("VESPA_SSH_SBATCH_SCRIPT", "pseudo_scenes_lowmem.sh").strip()
        self.ssh_poll = float(os.environ.get("VESPA_SSH_POLL_SECONDS", "30"))
        self.ssh_command_timeout = float(os.environ.get("VESPA_SSH_COMMAND_TIMEOUT", "120"))
        if self.ssh_poll < 0 or self.ssh_command_timeout <= 0:
            raise ValueError("Invalid VESPA SSH poll/command timeout")
        if self.ssh_port and not self.ssh_port.isdigit():
            raise ValueError("VESPA_SSH_PORT must be a number")
        self.lock = Lock()
        self.uploaded_datasets = UploadedDatasetCache()

    # ---------- configuration ----------
    def _metadata_ready(self):
        return all((self.data_root / self.version / f"{t}.json").is_file() for t in ("scene", "sample"))

    def configured(self):
        if not self._metadata_ready():
            return False
        if self.executor == "ssh":
            return (bool(self.ssh_target) and bool(self.ssh_remote_root) and bool(self.ssh_exp) and bool(self.ssh_script)
                    and (not self.ssh_key or Path(self.ssh_key).is_file())
                    and (not self.ssh_known_hosts or Path(self.ssh_known_hosts).is_file()))
        return ((self.repo / "main_pseudo_vlm.py").is_file() and self.python.is_file()
                and (self.repo / "configs/vlm/p_final.yaml").is_file())

    def _targets(self, scene_name):
        try:
            scenes = json.loads((self.data_root / self.version / "scene.json").read_text())
            samples = json.loads((self.data_root / self.version / "sample.json").read_text())
            scene = next((s for s in scenes if s["name"] == scene_name), None)
            if scene is None:
                raise VespaError(404, "SCENE_NOT_FOUND", "Scene does not exist in the configured dataset.")
            tokens = {s["token"] for s in samples if s["scene_token"] == scene["token"]}
            if not tokens:
                raise ValueError("No samples")
            return tokens
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise VespaError(503, "VESPA_DATA_NOT_READY", "nuScenes metadata is unavailable or invalid.") from exc

    # ---------- entry point ----------
    def for_dataset(self, key, version):
        if self.executor != "local":
            raise VespaError(422, "UPLOAD_EXECUTOR_UNSUPPORTED", "Uploaded datasets require the local GPU executor.")
        if not re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", key) or version not in ("v1.0-mini", "v1.0-trainval"):
            raise VespaError(422, "INVALID_DATASET", "Invalid uploaded dataset key/version.")
        try:
            root = self.uploaded_datasets.ensure(key)
        except (OSError, ValueError, zipfile.BadZipFile, BotoCoreError, ClientError) as error:
            logger.exception("Uploaded dataset could not be prepared")
            raise VespaError(503, "UPLOAD_STORAGE_UNAVAILABLE", "Check upload bucket, region, task role and local disk space.") from error
        scoped = copy.copy(self)
        scoped.data_root, scoped.version = root, version
        # The shallow copy deliberately shares the worker's lock. Only one GPU run at a time.
        return scoped

    def generate(self, request: AutoLabelRequest):
        if self.executor == "local" and not request.source_artifact_path and not gpu_available():
            raise VespaError(503, "GPU_UNAVAILABLE", "The NVIDIA GPU is unavailable; recover the host GPU and restart AI.")
        if request.source_artifact_path and self.executor != "local":
            raise VespaError(409, "RIGID_EXECUTOR_UNSUPPORTED", "Rigid postprocessing requires the local executor.")
        if request.dataset_key is not None:
            scoped = self.for_dataset(request.dataset_key, request.dataset_version)
            return scoped.generate(request.model_copy(update={"dataset_key": None, "dataset_version": None}))
        if not self.lock.acquire(blocking=False):
            raise VespaError(409, "VESPA_BUSY", "A VESPA run is already active on this AI worker.")
        try:
            if not self.configured():
                raise VespaError(503, "VESPA_NOT_CONFIGURED", "Configure VESPA repository, Python environment and nuScenes data first."
                                 if self.executor == "local" else
                                 "Configure the VESPA SSH target, remote VESPA path, SSH key and nuScenes metadata first.")
            expected = self._targets(request.scene_name)
            run_id = uuid4()
            logger.info("[VESPA] job=%s scene=%s run=%s executor=%s started", request.job_id, request.scene_name, run_id, self.executor)
            run_dir = self.output_root / str(run_id)
            try:
                run_dir.mkdir(parents=True, exist_ok=False)
            except OSError as exc:
                raise VespaError(503, "VESPA_LAUNCH_FAILED", "Could not launch VESPA or write its run files.") from exc
            run = self._run_ssh if self.executor == "ssh" else self._run_local
            path = run(request, run_id, run_dir)
            return self._build_response(request, run_id, path, expected)
        finally:
            self.lock.release()

    # ---------- local executor (unchanged behaviour) ----------
    def _run_local(self, request, run_id, run_dir):
        try:
            command = [str(self.python), str(Path(__file__).with_name("vespa_runner.py")),
                       "--repo", str(self.repo), "--config", str(self.repo / "configs/vlm/p_final.yaml"),
                       "--scene", request.scene_name, "--class-mode", str(request.class_mode),
                       "--output-root", str(run_dir), "--data-root", str(self.data_root), "--dataset-version", self.version]
            if os.environ.get("VESPA_RIGID_ENABLED", "true").lower() == "true":
                command += ["--rigid"]
            if request.source_artifact_path:
                source = self._source_run(request.source_artifact_path)
                if "--rigid" not in command:
                    raise VespaError(409, "RIGID_DISABLED", "Rigid postprocessing is disabled.")
                refs_path = run_dir / "references.json"
                refs_path.write_text(json.dumps(request.references))
                command += ["--source-run", str(source), "--references", str(refs_path)]
            # Small RANSAC linear solves suffer from BLAS oversubscription.
            env = os.environ.copy()
            for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
                env[key] = str(self.num_threads)
            with (run_dir / "execution.log").open("wb") as log:
                with subprocess.Popen(command, cwd=self.repo, stdout=log, stderr=subprocess.STDOUT,
                                      start_new_session=(os.name == "posix"), env=env) as process:
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
                        logger.error("VESPA timeout: run %s", run_id)
                        raise VespaError(504, "VESPA_TIMEOUT", "VESPA exceeded the configured runtime limit.") from exc
            if code != 0:
                logger.error("VESPA run %s exited with %s; see execution.log", run_id, code)
                raise VespaError(502, "VESPA_EXECUTION_FAILED", "VESPA execution failed; check the AI server run log.")
        except OSError as exc:
            raise VespaError(503, "VESPA_LAUNCH_FAILED", "Could not launch VESPA or write its run files.") from exc
        mapping = f"{request.class_mode}class"
        return run_dir / "outs/vlm/p_final/#out_labels" / f"vlm_p_final_{request.scene_name}_{mapping}.json"

    def _source_run(self, relative):
        from uuid import UUID
        try:
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts or "\\" in relative or ":" in relative:
                raise ValueError("Invalid source path")
            run = self.output_root / str(UUID(candidate.parts[0]))
            path = (self.output_root / candidate).resolve()
            if not path.is_relative_to(run.resolve()) or not run.resolve().is_relative_to(self.output_root.resolve()) or not path.is_file():
                raise ValueError("Invalid source artifact")
            if not (run / "rigid-manifest.json").is_file() or not (run / "rigid-state.pkl.gz").is_file():
                raise ValueError("Source has no rigid cache")
            return run
        except (OSError, ValueError, IndexError) as exc:
            raise VespaError(409, "RIGID_CACHE_UNAVAILABLE", "Source postprocessing cache is unavailable; generate a new base result.") from exc

    # ---------- ssh executor (remote Slurm) ----------
    def _ssh_command(self, remote_command):
        command = [self.ssh_bin, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30"]
        if self.ssh_port:
            command += ["-p", self.ssh_port]
        if self.ssh_key:
            command += ["-i", self.ssh_key, "-o", "IdentitiesOnly=yes"]
        if self.ssh_known_hosts:
            command += ["-o", f"UserKnownHostsFile={self.ssh_known_hosts}", "-o", "StrictHostKeyChecking=yes"]
        return command + [self.ssh_target, remote_command]

    def _ssh(self, remote_command, log, keep_output=False):
        """Runs one command on the login node. Returns (exit code, stdout); 255 means SSH itself failed."""
        log.write(f"$ {remote_command}\n")
        try:
            # sh -c keeps the command independent of the account's login shell (bash, csh, ...).
            done = subprocess.run(self._ssh_command("sh -c " + shlex.quote(remote_command)), capture_output=True, text=True,
                                  timeout=self.ssh_command_timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            log.write("(ssh command timed out)\n")
            return SSH_UNREACHABLE, ""
        for text in ((done.stdout, done.stderr) if keep_output else (done.stderr,)):
            if text.strip():
                log.write(text if text.endswith("\n") else text + "\n")
        log.flush()
        return done.returncode, done.stdout

    def _in_root(self, command):
        return f"cd {shlex.quote(self.ssh_remote_root)} && {command}"

    def _run_ssh(self, request, run_id, run_dir):
        mapping = f"{request.class_mode}class"
        scene = request.scene_name  # validated by the request schema (^scene-[0-9]{4}$) and local metadata
        remote_rel = f"outs/vlm/{self.ssh_exp}/#out_labels_scene/{scene}/vlm_{self.ssh_exp}_{scene}_{mapping}.json"
        remote_file = shlex.quote(remote_rel)
        mtime = f"(stat -c %Y {remote_file} 2>/dev/null || echo 0)"
        try:
            log = (run_dir / "execution.log").open("w", encoding="utf-8")
        except OSError as exc:
            raise VespaError(503, "VESPA_LAUNCH_FAILED", "Could not launch VESPA or write its run files.") from exc
        with log:
            # 1) Submit. The previous mtime tells a fresh result apart from an older run's file at the same path.
            code, out = self._ssh(self._in_root(
                f"mkdir -p logs && {mtime} && EXP={shlex.quote(self.ssh_exp)} SCENES={shlex.quote(scene)} "
                f"sbatch --parsable {shlex.quote(self.ssh_script)}"), log)
            lines = out.split()
            job = lines[-1].split(";")[0] if lines else ""
            if code != 0 or len(lines) < 2 or not job.isdigit():
                logger.error("[VESPA] run %s: sbatch submission failed (exit %s); see execution.log", run_id, code)
                raise VespaError(503, "VESPA_LAUNCH_FAILED", "Could not submit the VESPA Slurm job over SSH; check the AI server run log.")
            before = lines[-2]
            log.write(f"slurm job {job} submitted; previous output mtime {before}\n")
            logger.info("[VESPA] job=%s run=%s slurm_job=%s submitted", request.job_id, run_id, job)

            # 2) Wait while Slurm still lists the job (PENDING/RUNNING/...).
            deadline = time.monotonic() + self.timeout
            failures, last_state = 0, None
            while True:
                code, out = self._ssh(f'out=$(squeue -h -j {job} -o %T 2>&1); echo "$?"; echo "$out"', log)
                status, _, text = out.partition("\n")
                text = text.strip()
                # A finished job either vanishes from squeue or, once purged, gives "Invalid job id".
                finished = status.strip() == "0" and not text or "Invalid job id" in text
                if code != 0 or not finished and status.strip() != "0":
                    if text:
                        log.write(f"squeue: {text}\n")
                    failures += 1
                    if failures >= SSH_MAX_POLL_FAILURES:
                        logger.error("[VESPA] run %s: lost SSH contact while slurm job %s was active", run_id, job)
                        raise VespaError(503, "VESPA_REMOTE_UNREACHABLE",
                                         "Lost contact with the cluster (SSH or Slurm) while the VESPA job was active.")
                else:
                    failures = 0
                    if finished:
                        break
                    state = text
                    if state != last_state:
                        log.write(f"slurm job {job}: {state}\n")
                        logger.info("[VESPA] run=%s slurm_job=%s state=%s", run_id, job, state)
                        last_state = state
                if time.monotonic() >= deadline:
                    self._ssh(f"scancel {job}", log)
                    logger.error("VESPA timeout: run %s, slurm job %s cancelled", run_id, job)
                    raise VespaError(504, "VESPA_TIMEOUT", "VESPA exceeded the configured runtime limit.")
                time.sleep(self.ssh_poll)

            # 3) Keep the Slurm accounting state and log tail with this run (best effort; sacct may be disabled).
            self._ssh(self._in_root(
                f"echo \"sacct: $(sacct -n -X -j {job} -o State 2>/dev/null | head -n 1)\"; "
                f"tail -n 200 logs/slurm-{job}.out 2>/dev/null || true"), log, keep_output=True)

            # 4) The batch script always exits 0, so a new output file is the success signal.
            for attempt in range(SSH_OUTPUT_CHECKS):
                code, out = self._ssh(self._in_root(mtime), log)
                after = out.strip()
                if code == 0 and after not in ("", "0", before):
                    break
                if attempt + 1 < SSH_OUTPUT_CHECKS:
                    time.sleep(min(self.ssh_poll, 10))
            else:
                logger.error("[VESPA] run %s: slurm job %s finished without a new %s", run_id, job, remote_rel)
                raise VespaError(502, "VESPA_EXECUTION_FAILED",
                                 "VESPA execution failed; check the AI server run log and the Slurm log on the cluster.")
            code, out = self._ssh(self._in_root(f"cat {remote_file}"), log)
            if code != 0 or not out:
                raise VespaError(502, "VESPA_INVALID_RESULT", "Final VESPA JSON is missing or invalid.")
            log.write(f"copied {remote_rel} ({len(out)} bytes)\n")
        path = run_dir / remote_rel
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(out, encoding="utf-8")
        except OSError as exc:
            raise VespaError(503, "VESPA_LAUNCH_FAILED", "Could not write the VESPA result to the run folder.") from exc
        return path

    # ---------- shared validation ----------
    def _build_response(self, request, run_id, path, expected):
        mapping = f"{request.class_mode}class"
        try:
            payload = json.loads(path.read_text())
            if payload["mapping_name"] != mapping or set(payload["results"]) != expected:
                raise ValueError("Mapping/sample coverage mismatch")
            response = AutoLabelResponse(run_id=run_id, scene_name=request.scene_name,
                class_mode=request.class_mode, job_id=request.job_id, execution_token=request.execution_token,
                mapping_name=payload["mapping_name"], split=payload["split"], meta=payload["meta"], results=payload["results"],
                artifact_path=str(path.relative_to(self.output_root)),
                result_checksum=hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest())
            for token, boxes in response.results.items():
                for box in boxes:
                    if box.sample_token != token or box.detection_name not in CLASSES[request.class_mode] or box.detection_score != 1.0:
                        raise ValueError("Invalid box class, token or score")
            logger.info("[VESPA] job=%s run=%s completed boxes=%s", request.job_id, run_id, sum(len(b) for b in response.results.values()))
            return response
        except (OSError, KeyError, TypeError, ValueError) as exc:
            logger.exception("Invalid final JSON for run %s", run_id)
            raise VespaError(502, "VESPA_INVALID_RESULT", "Final VESPA JSON is missing or invalid.") from exc
