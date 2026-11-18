"""Paired real-GPU CLIP route benchmark; TestClient includes ASGI/JSON, not a network hop."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.embedding import router
from services.clip_service import ClipService
import clip_core


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=6)
    parser.add_argument('--requests', type=int, default=32)
    args = parser.parse_args()
    if not 2 <= args.repeats <= 10 or not 16 <= args.requests <= 128:
        raise ValueError('Expected 2..10 repeats and 16..128 requests')
    args.output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    os.environ['CLIP_TEXT_CACHE_SIZE'] = '0'
    stage = logging.getLogger('uvicorn.error')
    stage.setLevel(logging.INFO)
    stage.addHandler(logging.FileHandler(args.output / 'clip-stage.log'))
    service = ClipService()
    service.load()
    if service.device != 'cuda':
        raise RuntimeError('This comparison requires the approved CUDA GPU')
    application = FastAPI()
    application.state.clip_service = service
    application.include_router(router)
    manifest = {
        'boundary': 'FastAPI text route via TestClient, JSON and lock included; no TCP/Spring/RDS',
        'model': clip_core.model_key(clip_core.MODEL_NAME, clip_core.PRETRAINED),
        'same_loaded_model_for_both_modes': True, 'torch': torch.__version__,
        'python': platform.python_version(), 'gpu': torch.cuda.get_device_name(),
        'threads': torch.get_num_threads(), 'cache_sizes': [0, 256],
        'cache_condition': 'cleared at each batch; model warm; alternating paired execution order',
        'requests_per_batch': args.requests, 'paired_repeats': args.repeats,
        'source_sha256': {str(p.relative_to(Path(__file__).resolve().parents[1])):
                          hashlib.sha256(p.read_bytes()).hexdigest() for p in
                          [Path(__file__), Path(__file__).resolve().parents[1] / 'services/clip_service.py']},
    }
    save(args.output / 'manifest.json', manifest)
    original_encode = clip_core.encode_text
    calls = 0
    def counted(*values):
        nonlocal calls
        calls += 1  # Called while ClipService holds its lock.
        return original_encode(*values)
    clip_core.encode_text = counted
    runs, checks = [], []
    try:
        with TestClient(application) as client:
            for _ in range(20):
                assert client.post('/embedding/text', json={'text': 'warm road'}).status_code == 200
            for concurrency in (1, 4):
                for case in ('repeated', 'mixed', 'distinct'):
                    texts = [('road with cars' if case == 'repeated' or case == 'mixed' and i % 2 == 0
                              else f'road with cars number {i}') for i in range(args.requests)]
                    for repeat in range(args.repeats):
                        outputs = {}
                        for size in ((0, 256) if repeat % 2 == 0 else (256, 0)):
                            service.text_cache.clear()
                            service.text_cache_size = size
                            calls = 0
                            torch.cuda.reset_peak_memory_stats()
                            def request(text):
                                started = time.perf_counter()
                                result = client.post('/embedding/text', json={'text': text})
                                elapsed = time.perf_counter() - started
                                if result.status_code != 200:
                                    raise RuntimeError(f'Unexpected HTTP status {result.status_code}')
                                return result.json(), elapsed
                            start = time.perf_counter()
                            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                                values = list(pool.map(request, texts))
                            wall = time.perf_counter() - start
                            outputs[size] = [value[0] for value in values]
                            run = {'case': case, 'concurrency': concurrency, 'repeat': repeat,
                                   'cache_size': size, 'requests': len(texts), 'inferences': calls,
                                   'wall_seconds': wall, 'latency_seconds': [value[1] for value in values],
                                   'cache_entries': len(service.text_cache),
                                   'cuda_peak_allocated_bytes': torch.cuda.max_memory_allocated(),
                                   'response_sha256': [hashlib.sha256(json.dumps(value[0], sort_keys=True).encode()).hexdigest()
                                                       for value in values]}
                            runs.append(run)
                            with (args.output / 'events.jsonl').open('a', encoding='utf-8') as stream:
                                stream.write(json.dumps(run) + '\n')
                        equal = outputs[0] == outputs[256]
                        checks.append({'case': case, 'concurrency': concurrency, 'repeat': repeat,
                                       'exact_response_vectors_and_metadata': equal, 'responses': len(texts)})
                        if not equal:
                            raise RuntimeError('Cache response equivalence failed')
        summaries = []
        for case in ('repeated', 'mixed', 'distinct'):
            for concurrency in (1, 4):
                modes = {str(size): statistics.median(r['wall_seconds'] for r in runs if
                         r['case'] == case and r['concurrency'] == concurrency and r['cache_size'] == size)
                         for size in (0, 256)}
                summaries.append({'case': case, 'concurrency': concurrency, 'median_batch_seconds': modes,
                                  'reduction': 1 - modes['256'] / modes['0']})
        save(args.output / 'comparison.json', {'all_exact': all(c['exact_response_vectors_and_metadata'] for c in checks),
             'checks': checks, 'scenarios': summaries, 'runs': len(runs),
             'paired_responses': sum(c['responses'] for c in checks)})
    finally:
        clip_core.encode_text = original_encode
        service.close()


if __name__ == '__main__':
    main()
