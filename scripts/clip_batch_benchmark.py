"""Single-image vs batched CLIP image embedding on real weights and real nuScenes keyframes.

Runs the exact service code paths without HTTP: the single path is clip_core.encode_image per image (what
/embedding/image does), the batched path is per-image preprocess_crops then clip_core.encode_crop_batches (what
/embedding/images does). Reports wall time per stage and the minimum cosine between the two vectors of each image.
Nothing is written to a DB. Example:

  .venv/bin/python scripts/clip_batch_benchmark.py --root v1.0-mini --images 256 --device mps --out result.json
"""
import argparse
import json
import platform
import sys
import time
from pathlib import Path

import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "embedding"))
import clip_core  # noqa: E402


def keyframes(root: Path, version: str, limit: int) -> list[str]:
    """Same selection as the 2026-11-17 report: is_key_frame and samples/CAM_*, ordered by timestamp then token."""
    rows = json.loads((root / version / "sample_data.json").read_text())
    picked = sorted((r for r in rows if r["is_key_frame"] and r["filename"].startswith("samples/CAM_")), key=lambda r: (r["timestamp"], r["token"]))
    return [r["filename"] for r in picked[:limit]]


def sync(device):
    if device == "cuda":
        torch.cuda.synchronize()
    elif device == "mps":
        torch.mps.synchronize()


def run_single(model, preprocess, root, paths, device, mode):
    decode = prep = gpu = 0.0
    vectors = []
    started = time.perf_counter()
    for p in paths:
        t0 = time.perf_counter()
        with Image.open(root / p) as image:
            image.load()
            t1 = time.perf_counter()
            crops = clip_core.preprocess_crops(preprocess, image, mode)
        t2 = time.perf_counter()
        vectors.append(clip_core.encode_crops(model, crops, device))
        t3 = time.perf_counter()
        decode += t1 - t0; prep += t2 - t1; gpu += t3 - t2
    return torch.stack(vectors), {"wall_s": time.perf_counter() - started, "decode_s": decode, "preprocess_s": prep, "gpu_s": gpu}


def run_batched(model, preprocess, root, paths, device, mode, batch, max_crops):
    decode = prep = gpu = 0.0
    vectors = []
    started = time.perf_counter()
    for start in range(0, len(paths), batch):
        crops = []
        for p in paths[start:start + batch]:
            t0 = time.perf_counter()
            with Image.open(root / p) as image:
                image.load()
                t1 = time.perf_counter()
                crops.append(clip_core.preprocess_crops(preprocess, image, mode))
            decode += t1 - t0; prep += time.perf_counter() - t1
        t2 = time.perf_counter()
        vectors.append(clip_core.encode_crop_batches(model, crops, device, max_crops))
        gpu += time.perf_counter() - t2
    return torch.cat(vectors), {"wall_s": time.perf_counter() - started, "decode_s": decode, "preprocess_s": prep, "gpu_s": gpu}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True, help="nuScenes root containing samples/ and <version>/")
    ap.add_argument("--version", default="v1.0-mini")
    ap.add_argument("--images", type=int, default=256)
    ap.add_argument("--device", default=None, help="cuda / mps / cpu (default: cuda -> mps -> cpu)")
    ap.add_argument("--batches", default="8,16,32,64", help="batched runs to compare, images per call")
    ap.add_argument("--max-crops", type=int, default=128, help="crops per forward pass (CLIP_MAX_CROPS_PER_FORWARD)")
    ap.add_argument("--mode", default=clip_core.LR_SQUARE_CROP_MEAN)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    device = args.device or clip_core.available_devices()[0]
    paths = keyframes(args.root, args.version, args.images)
    loaded = time.perf_counter()
    model, preprocess, _ = clip_core.load_model(device)
    load_s = time.perf_counter() - loaded
    # Warm-up outside the timings (first forward pass compiles kernels / allocates; the 11-17 report saw 1.5 s).
    with Image.open(args.root / paths[0]) as image:
        clip_core.encode_crop_batches(model, [clip_core.preprocess_crops(preprocess, image, args.mode)] * 2, device)
    sync(device)

    reference, single = run_single(model, preprocess, args.root, paths, device, args.mode)
    runs = [{"name": "single", "images_per_call": 1, **single}]
    for b in [int(x) for x in args.batches.split(",") if x]:
        vectors, timing = run_batched(model, preprocess, args.root, paths, device, args.mode, b, args.max_crops)
        cos = (reference * vectors).sum(dim=1)
        runs.append({"name": f"batch{b}", "images_per_call": b, **timing,
                     "min_cosine_vs_single": float(cos.min()), "max_abs_diff_vs_single": float((reference - vectors).abs().max())})
    for r in runs:
        r["images_per_s"] = len(paths) / r["wall_s"]
        r["ms_per_image"] = r["wall_s"] * 1000 / len(paths)
        r["gpu_ms_per_image"] = r["gpu_s"] * 1000 / len(paths)
    result = {
        "images": len(paths), "device": device, "model": clip_core.model_key(clip_core.MODEL_NAME, clip_core.PRETRAINED),
        "preprocess": args.mode, "max_crops": args.max_crops, "model_load_s": load_s, "torch": torch.__version__,
        "platform": platform.platform(), "machine": platform.machine(), "processor": platform.processor(),
        "first_image": paths[0], "last_image": paths[-1], "runs": runs,
    }
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
