"""Equivalence against the installed pipeline plus exception-safe instrumentation."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import unittest
import torch
from PIL import Image
from transformers import GroundingDinoImageProcessor
from transformers.pipelines.zero_shot_object_detection import ZeroShotObjectDetectionPipeline

spec = importlib.util.spec_from_file_location('grounding_probe', Path(__file__).resolve().parents[1]/'services/grounding_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def check_cached_chunks(labels):
    # Real image processor, including resize/normalization/padding; no model downloads.
    processor = GroundingDinoImageProcessor(size={'shortest_edge':32, 'longest_edge':64})
    pipeline = SimpleNamespace(framework='pt', torch_dtype=torch.float32, image_processor=processor,
        tokenizer=lambda text, **kw: {'input_ids':torch.tensor([[ord(c) for c in text]])})
    image = Image.frombytes('RGB', (19, 13), bytes((i*31)%256 for i in range(19*13*3)))
    inputs = {'image':image, 'candidate_labels':labels}
    expected = list(ZeroShotObjectDetectionPipeline.preprocess(pipeline, inputs))
    actual = list(probe.cached_preprocess(pipeline, inputs))
    assert len(expected) == len(actual)
    assert len({id(row) for row in actual}) == len(actual)
    for left, right in zip(expected, actual):
        assert left.keys() == right.keys()
        for key in left:
            if isinstance(left[key], torch.Tensor):
                torch.testing.assert_close(left[key], right[key], rtol=0, atol=0)
            else:
                assert left[key] == right[key]
    # ChunkPipeline may pop metadata. The next chunk must remain usable.
    actual[0].pop('is_last')
    assert actual[-1]['is_last'] is True


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.ones(1))
        self.config = SimpleNamespace(model_type='grounding-dino')

    def forward(self, value):
        return value*self.weight


class TinyPipeline:
    framework = 'pt'

    def __init__(self):
        self.model = TinyModel()
        self.image_processor = lambda value: value

    def preprocess(self, inputs):
        return inputs

    def _ensure_tensor_on_device(self, inputs, device):
        if isinstance(inputs, dict):
            return {key:self._ensure_tensor_on_device(value, device) for key,value in inputs.items()}
        return inputs.to(device)


def check_probe_counts_outer_transfer_and_restores_on_failure(test):
    pipeline = TinyPipeline()
    original_processor = pipeline.image_processor
    original_transfer = pipeline._ensure_tensor_on_device
    with test.assertRaisesRegex(RuntimeError, 'expected failure'):
        with probe.observe_detector(pipeline) as metrics:
            value = pipeline.image_processor(torch.tensor([2.]))
            result = pipeline.model(value)
            result = pipeline._ensure_tensor_on_device({'output':result}, torch.device('cpu'))
            assert result['output'].item() == 2
            raise RuntimeError('expected failure')
    assert metrics['forward_calls'] == 1
    assert metrics['image_processor_calls'] == 1
    assert metrics['to_cpu_calls'] == 1
    assert pipeline.image_processor is original_processor
    assert pipeline._ensure_tensor_on_device == original_transfer
    assert not pipeline.model._forward_hooks and not pipeline.model._forward_pre_hooks
    assert '_ensure_tensor_on_device' not in vars(pipeline)


def check_reuse_scope_restores_original_preprocess_after_exception(test, instance_override):
    pipeline = TinyPipeline()
    if instance_override:
        pipeline.preprocess = lambda inputs: inputs
    original = pipeline.preprocess
    with test.assertRaisesRegex(ValueError, 'expected failure'):
        with probe.reuse_image_preprocessing(pipeline):
            assert pipeline.preprocess != original
            raise ValueError('expected failure')
    assert pipeline.preprocess == original
    assert ('preprocess' in vars(pipeline)) == instance_override


def check_incompatible_pipeline_is_rejected_without_changes(test):
    pipeline = TinyPipeline()
    pipeline.model.config.model_type = 'owlvit'
    with test.assertRaisesRegex(ValueError, 'Grounding DINO'):
        with probe.reuse_image_preprocessing(pipeline):
            test.fail('must not enter')
    assert 'preprocess' not in vars(pipeline)


class GroundingProbeTest(unittest.TestCase):
    def test_list_labels_match_installed_pipeline(self):
        check_cached_chunks(['car.', 'traffic cone.', 'pedestrian.'])

    def test_string_labels_match_installed_pipeline(self):
        check_cached_chunks('car.,traffic cone.')

    def test_probe_failure_cleanup(self):
        check_probe_counts_outer_transfer_and_restores_on_failure(self)

    def test_class_preprocess_restored(self):
        check_reuse_scope_restores_original_preprocess_after_exception(self, False)

    def test_instance_preprocess_restored(self):
        check_reuse_scope_restores_original_preprocess_after_exception(self, True)

    def test_reject_other_models(self):
        check_incompatible_pipeline_is_rejected_without_changes(self)


if __name__ == '__main__':
    unittest.main(verbosity=2)
