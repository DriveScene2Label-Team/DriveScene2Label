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
from schemas.embedding import EmbeddingResponse, ImageBatchEmbeddingResponse, ImageBatchItem, ImageEmbeddingError
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
        # Crops per forward pass in /embedding/images (64 images x 2 crops by default). Lower it if VRAM is short.
        self.max_crops = max(1, int(os.environ.get("CLIP_MAX_CROPS_PER_FORWARD", "128")))

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

    def _resolve_image(self, image_path, dataset_key=None):
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
            return clip_core.resolve(root, image_path)
        except FileNotFoundError as exc:
            raise ClipError(404, "IMAGE_NOT_FOUND", "Image or configured image root does not exist.") from exc
        except ValueError as exc:
            raise ClipError(400, "INVALID_IMAGE_PATH", "A relative image path inside CLIP_IMAGE_ROOT is required.") from exc
        except OSError as exc:
            raise ClipError(400, "IMAGE_NOT_READABLE", "Image path is not readable.") from exc

    def encode_image_path(self, image_path, mode, dataset_key=None):
        self._ready()
        path = self._resolve_image(image_path, dataset_key)
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

    def encode_image_paths(self, image_paths, mode, dataset_key=None):
        """Batch of images -> one result per path, in order. Decode and crop preprocessing run per image outside the
        model lock, then every crop goes through the model together (clip_core.encode_crop_batches), so the lock is
        held only for the GPU part and text queries wait less than with N single-image calls.
        A bad path or image fails only its own item, with the same status/code as /embedding/image."""
        self._ready()
        if mode not in clip_core.PREPROCESS_MODES:
            raise ClipError(400, "INVALID_PREPROCESS", "Unsupported image preprocessing.")
        started = time.perf_counter()
        results = [None] * len(image_paths)
        ready = []  # (index, crops)
        decode_s = preprocess_s = 0.0
        for i, image_path in enumerate(image_paths):
            try:
                path = self._resolve_image(image_path, dataset_key)
                t0 = time.perf_counter()
                try:
                    with Image.open(path) as image:
                        image.load()
                        t1 = time.perf_counter()
                        crops = clip_core.preprocess_crops(self.preprocess, image, mode)
                except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                    raise ClipError(400, "INVALID_IMAGE", "File is not a readable image.") from exc
                decode_s += t1 - t0
                preprocess_s += time.perf_counter() - t1
                ready.append((i, crops))
            except ClipError as exc:
                results[i] = ImageBatchItem(image_path=image_path, error=ImageEmbeddingError(status=exc.status_code, code=exc.code, message=str(exc)))
        prepared = locked = encoded = time.perf_counter()
        if ready:
            try:
                with self.lock:
                    locked = time.perf_counter()
                    vectors = clip_core.encode_crop_batches(self.model, [c for _, c in ready], self.device, self.max_crops)
                    encoded = time.perf_counter()
            except Exception as exc:
                logger.exception("CLIP batch image inference failed")
                raise ClipError(500, "CLIP_INFERENCE_FAILED", "Image inference failed.") from exc
            for (i, _), vector in zip(ready, vectors):
                try:
                    one = self._response(vector, mode)
                    results[i] = ImageBatchItem(image_path=image_paths[i], embedding=one.embedding)
                except ClipError as exc:
                    results[i] = ImageBatchItem(image_path=image_paths[i], error=ImageEmbeddingError(status=exc.status_code, code=exc.code, message=str(exc)))
        ms = lambda seconds: f"{seconds * 1000:.1f}"
        # Totals for the whole call. decode/preprocess are sums over images (outside the lock); gpu is one batched span.
        stage_log.info("[CLIP_STAGE] stage=image_embed_batch images=%s count=%s lock_wait_ms=%s decode_ms=%s preprocess_ms=%s gpu_ms=%s handler_ms=%s",
                       len(image_paths), len(ready), ms(locked - prepared), ms(decode_s), ms(preprocess_s), ms(encoded - locked), ms(time.perf_counter() - started))
        return ImageBatchEmbeddingResponse(preprocess=mode, results=results)
