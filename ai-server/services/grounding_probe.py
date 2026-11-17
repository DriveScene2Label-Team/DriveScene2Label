"""Scoped Grounding DINO measurement and an opt-in preprocessing experiment.

No weights, prompts, thresholds, forward batching or postprocessing are changed.
Use only in an isolated runner: a pipeline instance must not serve concurrent calls.
"""
from contextlib import contextmanager
import time
from types import MethodType


class ProcessorProbe:
    def __init__(self, processor, metrics):
        self.processor, self.metrics = processor, metrics

    def __getattr__(self, name):
        return getattr(self.processor, name)

    def __call__(self, *args, **kwargs):
        started = time.perf_counter()
        self.metrics['image_processor_calls'] += 1
        try:
            return self.processor(*args, **kwargs)
        finally:
            self.metrics['image_processor_ms'] += (time.perf_counter()-started)*1000

    def post_process_object_detection(self, *args, **kwargs):
        started = time.perf_counter()
        self.metrics['postprocess_calls'] += 1
        try:
            return self.processor.post_process_object_detection(*args, **kwargs)
        finally:
            self.metrics['postprocess_ms'] += (time.perf_counter()-started)*1000


def cached_preprocess(pipeline, inputs, timeout=None):
    """Same 4.49 pipeline chunks; compute image features once for this image."""
    from transformers.image_utils import load_image
    import torch

    image = load_image(inputs['image'], timeout=timeout)
    candidates = inputs['candidate_labels']
    if isinstance(candidates, str):
        candidates = candidates.split(',')
    if not candidates:
        return
    target_size = torch.tensor([[image.height, image.width]], dtype=torch.int32)
    image_features = pipeline.image_processor(image, return_tensors=pipeline.framework)
    image_features = image_features.to(pipeline.torch_dtype)
    for index, candidate in enumerate(candidates):
        text = pipeline.tokenizer(candidate, return_tensors=pipeline.framework)
        yield {'is_last': index == len(candidates)-1, 'target_size': target_size,
               'candidate_label': candidate, **text, **image_features}


@contextmanager
def reuse_image_preprocessing(pipeline):
    if pipeline.framework != 'pt' or pipeline.model.config.model_type != 'grounding-dino':
        raise ValueError('This experiment requires a PyTorch Grounding DINO pipeline.')
    was_instance_attribute = 'preprocess' in vars(pipeline)
    previous = pipeline.preprocess
    pipeline.preprocess = MethodType(cached_preprocess, pipeline)
    try:
        yield
    finally:
        if was_instance_attribute:
            pipeline.preprocess = previous
        else:
            del pipeline.preprocess


@contextmanager
def observe_detector(pipeline, *, synchronize=False):
    """Count real forwards. CUDA timings are emitted only in diagnostic mode.

    CUDA event time covers a stream interval, not the sum of kernel durations.
    Transfer wall time includes recursive tensor conversion and synchronization.
    """
    import torch

    metrics = dict(image_processor_calls=0, image_processor_ms=0.0,
                   forward_calls=0, forward_host_ms=0.0,
                   postprocess_calls=0, postprocess_ms=0.0,
                   to_cpu_calls=0, to_cpu_ms=0.0,
                   to_device_calls=0, to_device_ms=0.0,
                   diagnostic=synchronize)
    if synchronize:
        metrics['forward_cuda_ms'] = 0.0
    original_processor = pipeline.image_processor
    original_transfer = pipeline._ensure_tensor_on_device
    transfer_was_instance = '_ensure_tensor_on_device' in vars(pipeline)
    pipeline.image_processor = ProcessorProbe(original_processor, metrics)
    transfer_depth = 0
    started = None
    start_event = end_event = None
    device = next(pipeline.model.parameters()).device
    use_cuda = device.type == 'cuda'

    def before(model, args, kwargs):
        nonlocal started, start_event, end_event
        metrics['forward_calls'] += 1
        if synchronize and use_cuda:
            torch.cuda.synchronize(device)
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            start_event.record()
        started = time.perf_counter()

    def after(model, args, output):
        if synchronize and use_cuda:
            end_event.record()
            torch.cuda.synchronize(device)
            metrics['forward_cuda_ms'] += start_event.elapsed_time(end_event)
        metrics['forward_host_ms'] += (time.perf_counter()-started)*1000

    def transfer(inputs, device):
        nonlocal transfer_depth
        outer = transfer_depth == 0
        transfer_depth += 1
        began = time.perf_counter()
        try:
            return original_transfer(inputs, device)
        finally:
            transfer_depth -= 1
            if outer:
                name = 'to_cpu' if str(device) == 'cpu' else 'to_device'
                metrics[name+'_calls'] += 1
                metrics[name+'_ms'] += (time.perf_counter()-began)*1000

    pipeline._ensure_tensor_on_device = transfer
    before_handle = pipeline.model.register_forward_pre_hook(before, with_kwargs=True)
    after_handle = pipeline.model.register_forward_hook(after)
    try:
        yield metrics
    finally:
        before_handle.remove()
        after_handle.remove()
        pipeline.image_processor = original_processor
        if transfer_was_instance:
            pipeline._ensure_tensor_on_device = original_transfer
        else:
            del pipeline._ensure_tensor_on_device
