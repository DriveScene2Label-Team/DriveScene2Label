"""Per-call Grounding preprocessing selection for the isolated VESPA process."""
from contextlib import nullcontext
from functools import wraps
import hashlib
import json
from pathlib import Path

from grounding_probe import reuse_image_preprocessing


def configure_detection(module, mode, trace_path=None):
    if mode not in ('baseline', 'reuse'):
        raise ValueError('Unknown Grounding preprocessing mode')
    original = module._vlm_detection
    calls = 0
    trace = Path(trace_path) if trace_path else None
    if trace:
        trace.parent.mkdir(parents=True, exist_ok=True)
        trace.touch(exist_ok=False)

    @wraps(original)
    def detect(frame, vlm_detector, class_names, threshold):
        nonlocal calls
        scope = reuse_image_preprocessing(vlm_detector) if mode == 'reuse' else nullcontext()
        with scope:
            result = original(frame, vlm_detector, class_names, threshold)
        calls += 1
        if trace:
            row = {'call':calls, 'mode':mode, 'image_sha256':hashlib.sha256(frame.tobytes()).hexdigest(),
                   'shape':list(frame.shape), 'classes':class_names, 'threshold':threshold, 'boxes':result}
            with trace.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(row,allow_nan=False)+'\n')
        return result

    module._vlm_detection = detect
