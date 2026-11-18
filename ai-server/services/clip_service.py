import logging
import os
import sys
import time
from collections import OrderedDict
from pathlib import Path
from threading import Lock

import torch
from PIL import Image, UnidentifiedImageError

# Import only the shared inference module, never the DB-writing CLI.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "embedding"))
import clip_core
from schemas.embedding import EmbeddingResponse
from services.gpu_health import gpu_available

logger = logging.getLogger(__name__)
# uvicorn's logger is the one that reaches `docker logs` (see main.py), which scripts/hybrid/measurement.py collects.
stage_log = logging.getLogger("uvicorn.error")

class ClipError(RuntimeError):
    def __init__(self, status_code, code, message):
        super().__init__(message)
        self.status_code, self.code = status_code, code

class ClipService:
    def __init__(self):
        self.model = self.preprocess = self.tokenizer = None
        self.device = None
        self.lock = Lock()
        self.text_cache_size = int(os.environ.get("CLIP_TEXT_CACHE_SIZE", "0"))
        if not 0 <= self.text_cache_size <= 4096:
            raise ValueError("CLIP_TEXT_CACHE_SIZE must be between 0 and 4096")
        self.text_cache = OrderedDict()
        self.image_root = Path(os.environ.get("CLIP_IMAGE_ROOT", os.environ.get("NUSCENES_ROOT", "/data/nuscenes")))

    def load(self):
        if self.model is not None:
            return
        if not gpu_available():
            raise ClipError(503, "GPU_UNAVAILABLE", "The NVIDIA GPU is unavailable; recover the host GPU and restart AI.")
        # Preserve availability-based cuda -> mps -> cpu selection.
        self.device = clip_core.available_devices()[0]
        self.model, self.preprocess, self.tokenizer = clip_core.load_model(self.device)
        logger.info("CLIP loaded once on %s", self.device)

    def close(self):
        with self.lock:
            self.model = self.preprocess = self.tokenizer = None
            self.text_cache.clear()

    def _ready(self):
        if not gpu_available():
            raise ClipError(503, "GPU_UNAVAILABLE", "The NVIDIA GPU is unavailable; recover the host GPU and restart AI.")
        if self.model is None:
            raise ClipError(503, "CLIP_NOT_READY", "CLIP model is not ready.")

    def _response(self, vector, preprocess):
        if vector.shape != (clip_core.EMBED_DIM,) or not torch.isfinite(vector).all() or not torch.isclose(vector.norm(), torch.tensor(1.0), atol=1e-5):
            raise ClipError(500, "INVALID_MODEL_OUTPUT", "CLIP returned an invalid embedding.")
        return EmbeddingResponse(embedding=vector.tolist(), preprocess=preprocess)

    def encode_text(self, text):
        started = time.perf_counter()
        try:
            with self.lock:
                locked = time.perf_counter()
                # Readiness still applies to cache hits, including a lost GPU.
                self._ready()
                vector = self.text_cache.get(text) if self.text_cache_size else None
                cache = "hit" if vector is not None else "miss" if self.text_cache_size else "disabled"
                encoded = time.perf_counter()
                if vector is None:
                    vector = clip_core.encode_text(self.model, self.tokenizer, text, self.device)
                gpu_finished = time.perf_counter()
                response = self._response(vector, "clip-text-tokenizer")
                # Exact text only: case/whitespace/tokenizer behavior is unchanged.
                # Validation precedes insertion, so failed results are never cached.
                if self.text_cache_size:
                    if cache == "miss":
                        self.text_cache[text] = vector.detach().clone()
                    self.text_cache.move_to_end(text)
                    while len(self.text_cache) > self.text_cache_size:
                        self.text_cache.popitem(last=False)
                count = len(self.text_cache)
            stage_log.info("[CLIP_STAGE] stage=text_embed cache=%s count=%s lock_wait_ms=%.3f encode_ms=%.3f handler_ms=%.3f",
                           cache, count, (locked-started)*1000, (gpu_finished-encoded)*1000,
                           (time.perf_counter()-started)*1000)
            return response
        except ClipError:
            raise
        except Exception as exc:
            logger.exception("CLIP text inference failed")
            raise ClipError(500, "CLIP_INFERENCE_FAILED", "Text inference failed.") from exc

    def encode_image_path(self, image_path, mode, dataset_key=None):
        self._ready()
        try:
            root = self.image_root
            if dataset_key is not None:
                import re
                if not re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", dataset_key):
                    raise ValueError("Invalid dataset key")
                # Spring prepares the shared cache. This route never fetches S3 data.
                uploads = Path(os.environ.get("UPLOAD_ROOT", "/uploads")).resolve() / "datasets"
                root = (uploads / dataset_key).resolve()
                if not root.is_relative_to(uploads):
                    raise ValueError("Invalid uploaded dataset path")
            path = clip_core.resolve(root, image_path)
        except FileNotFoundError as exc:
            raise ClipError(404, "IMAGE_NOT_FOUND", "Image or configured image root does not exist.") from exc
        except ValueError as exc:
            raise ClipError(400, "INVALID_IMAGE_PATH", "A relative image path inside CLIP_IMAGE_ROOT is required.") from exc
        except OSError as exc:
            raise ClipError(400, "IMAGE_NOT_READABLE", "Image path is not readable.") from exc
        try:
            # Same work and the same lock scope as before (decode happened lazily inside the lock); only timed per stage.
            # Spring's ai_ms minus handler_ms is HTTP + JSON + FastAPI overhead.
            started = time.perf_counter()
            with Image.open(path) as image:
                with self.lock:
                    locked = time.perf_counter()
                    image.load()
                    decoded = time.perf_counter()
                    crops = clip_core.preprocess_crops(self.preprocess, image, mode)
                    prepared = time.perf_counter()
                    vector = clip_core.encode_crops(self.model, crops, self.device)
                    encoded = time.perf_counter()
            response = self._response(vector, mode)
            ms = lambda a, b: f"{(b - a) * 1000:.1f}"
            stage_log.info("[CLIP_STAGE] stage=image_embed lock_wait_ms=%s decode_ms=%s preprocess_ms=%s gpu_ms=%s handler_ms=%s",
                           ms(started, locked), ms(locked, decoded), ms(decoded, prepared), ms(prepared, encoded), ms(started, time.perf_counter()))
            return response
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ClipError(400, "INVALID_IMAGE", "File is not a readable image.") from exc
        except ClipError:
            raise
        except Exception as exc:
            logger.exception("CLIP image inference failed")
            raise ClipError(500, "CLIP_INFERENCE_FAILED", "Image inference failed.") from exc
