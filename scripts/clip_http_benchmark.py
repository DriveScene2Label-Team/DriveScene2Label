"""End-to-end HTTP comparison against a running AI server: POST /embedding/image once per image (what Spring
indexing did before) vs POST /embedding/images with up to 64 images per call (what it does now).
Client wall time includes HTTP, FastAPI, JSON in both directions and the model. Read-only; nothing is stored.

  .venv/bin/python scripts/clip_http_benchmark.py --base http://127.0.0.1:8010 --root v1.0-mini --images 256
"""
import argparse
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clip_batch_benchmark import keyframes  # noqa: E402


def post(base, route, body, timeout=600):
    req = urllib.request.Request(base + route, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--version", default="v1.0-mini")
    ap.add_argument("--images", type=int, default=256)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    paths = keyframes(args.root, args.version, args.images)
    post(args.base, "/embedding/images", {"image_paths": paths[:2]})  # warm-up, not timed

    single, single_ms = [], []
    started = time.perf_counter()
    for p in paths:
        t = time.perf_counter()
        single.append(post(args.base, "/embedding/image", {"image_path": p})["embedding"])
        single_ms.append((time.perf_counter() - t) * 1000)
    single_s = time.perf_counter() - started

    batched, call_ms = [], []
    started = time.perf_counter()
    for i in range(0, len(paths), args.batch):
        t = time.perf_counter()
        res = post(args.base, "/embedding/images", {"image_paths": paths[i:i + args.batch]})["results"]
        call_ms.append((time.perf_counter() - t) * 1000)
        assert all(r["error"] is None for r in res), [r["error"] for r in res if r["error"]]
        batched += [r["embedding"] for r in res]
    batch_s = time.perf_counter() - started

    cos = [sum(a * b for a, b in zip(x, y)) for x, y in zip(single, batched)]
    single_ms.sort()
    result = {
        "base": args.base, "images": len(paths), "batch": args.batch,
        "single": {"calls": len(paths), "wall_s": single_s, "ms_per_image": single_s * 1000 / len(paths),
                   "p50_ms": single_ms[len(single_ms) // 2], "p95_ms": single_ms[math.ceil(len(single_ms) * 0.95) - 1]},
        "batched": {"calls": len(call_ms), "wall_s": batch_s, "ms_per_image": batch_s * 1000 / len(paths), "call_ms": call_ms},
        "min_cosine_vs_single": min(cos),
    }
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
