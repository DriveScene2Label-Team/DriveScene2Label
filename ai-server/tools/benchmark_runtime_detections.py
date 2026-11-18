"""Compare a preserved static car-prompt ONNX graph on all six camera images.

This diagnostic requires positive reference detections and preserves raw arrays.
It does not establish full-class, scene, SAM, tracking or final 3D quality.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', choices=('ort', 'trt'), default='ort')
    parser.add_argument('--engine', type=Path)
    args = parser.parse_args()
    if args.runtime == 'trt' and (args.engine is None or not args.engine.resolve().is_relative_to('/results/experiments')):
        raise ValueError('TensorRT diagnostics require an existing experiment engine')
    if not args.output.resolve().is_relative_to('/results/experiments'):
        raise ValueError('Use a fresh results experiment directory')
    args.output.mkdir(parents=True, exist_ok=False)
    import numpy as np
    import torch
    from PIL import Image
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    from benchmark_grounding import select_images
    from probe_grounding_runtime import compare_arrays
    from scipy.optimize import linear_sum_assignment
    torch.set_num_threads(1)
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    torch.backends.cuda.matmul.allow_tf32 = False
    manifest = json.loads((args.reference / 'manifest.json').read_text())
    torch.backends.cudnn.allow_tf32 = manifest['cudnn_tf32']
    model_id = manifest['model']
    processor = AutoProcessor.from_pretrained(model_id, local_files_only=True)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id, local_files_only=True).eval().cuda()
    if model.config._commit_hash != manifest['model_commit']:
        raise ValueError('Cached model revision changed')
    rows = select_images(args.data_root, 'v1.0-mini', 'scene-0061', 1)
    for index, row in enumerate(rows):
        target = args.output / str(index)
        target.mkdir()
        image = args.data_root / row['filename']
        with Image.open(image) as frame:
            batch = processor(images=frame.convert('RGB'), text='car.', return_tensors='pt')
        if any(list(batch[name].shape) != details['shape'] for name, details in manifest['inputs'].items()):
            raise ValueError('Image input shape differs from the static exported graph')
        np.savez(target / 'inputs.npz', **{name: tensor.numpy() for name, tensor in batch.items()})
        with torch.no_grad():
            output = model(**{name: tensor.cuda() for name, tensor in batch.items()}, return_dict=True)
        np.savez(target / 'reference.npz', logits=output.logits.cpu().numpy(), pred_boxes=output.pred_boxes.cpu().numpy())
        row['image_sha256'] = hashlib.sha256(image.read_bytes()).hexdigest()
        del output
    del model, processor
    gc.collect()
    torch.cuda.empty_cache()
    engine_hash = None
    if args.runtime == 'ort':
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(args.reference / 'model.onnx'), sess_options=options,
            providers=[('CUDAExecutionProvider', {'use_tf32': 0, 'gpu_mem_limit': 4 * 1024**3}), 'CPUExecutionProvider'])
        if 'CUDAExecutionProvider' not in session.get_providers():
            raise RuntimeError('CUDA provider unavailable')
        session.disable_fallback()
        names = {item.name for item in session.get_inputs()}
        providers = session.get_providers()
        def infer(inputs):
            values = session.run(None, {k: v for k, v in inputs.items() if k in names})
            return dict(zip([item.name for item in session.get_outputs()], values))
    else:
        import tensorrt as trt
        engine_bytes = args.engine.read_bytes()
        engine_hash = hashlib.sha256(engine_bytes).hexdigest()
        runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
        engine = runtime.deserialize_cuda_engine(engine_bytes)
        del engine_bytes
        context = engine.create_execution_context()
        providers = ['TensorRT ' + trt.__version__]
        def infer(inputs):
            buffers = {}; outputs = []
            for i in range(engine.num_io_tensors):
                name = engine.get_tensor_name(i)
                shape = tuple(context.get_tensor_shape(name))
                if any(v < 0 for v in shape):
                    raise ValueError('Dynamic shape outside fixed-input diagnostic')
                dtype = trt.nptype(engine.get_tensor_dtype(name))
                if engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                    values = inputs[name].astype(dtype, copy=False)
                    if values.shape != shape or not np.array_equal(values, inputs[name]):
                        raise ValueError('TensorRT input shape/type conversion changes values')
                else:
                    values = np.zeros(shape, dtype=dtype); outputs.append(name)
                buffers[name] = torch.from_numpy(values).cuda()
                context.set_tensor_address(name, buffers[name].data_ptr())
            if not context.execute_async_v3(torch.cuda.current_stream().cuda_stream):
                raise RuntimeError('TensorRT execution failed')
            result = {name: buffers[name].cpu().numpy() for name in outputs}
            torch.cuda.synchronize()
            return result

    def detections(value):
        scores = 1 / (1 + np.exp(-np.clip(value['logits'][0].max(axis=-1), -80, 80)))
        mask = scores > .3
        box = value['pred_boxes'][0][mask]
        return scores[mask], np.concatenate((box[:, :2] - box[:, 2:] / 2, box[:, :2] + box[:, 2:] / 2), axis=1)

    summaries = []
    for index, row in enumerate(rows):
        target = args.output / str(index)
        inputs = dict(np.load(target / 'inputs.npz'))
        reference = dict(np.load(target / 'reference.npz'))
        actual = infer(inputs)
        np.savez(target / (args.runtime + '-output.npz'), **actual)
        left_score, left = detections(reference)
        right_score, right = detections(actual)
        overlaps = np.zeros((len(left), len(right)))
        for i, a in enumerate(left):
            for j, b in enumerate(right):
                intersection = np.maximum(0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2])).prod()
                union = (a[2:] - a[:2]).prod() + (b[2:] - b[:2]).prod() - intersection
                overlaps[i, j] = intersection / union if union > 0 else 0
        ii, jj = linear_sum_assignment(-overlaps)
        matches = [(int(i), int(j)) for i, j in zip(ii, jj) if overlaps[i, j] >= .5]
        summary = {'camera': Path(row['filename']).parts[1], 'token': row['token'], 'image_sha256': row['image_sha256'],
            'raw_quality': compare_arrays(reference, actual), 'reference_count': len(left), 'candidate_count': len(right),
            'matched': len(matches), 'missing': len(left) - len(matches), 'extra': len(right) - len(matches),
            'minimum_iou': min((float(overlaps[i, j]) for i, j in matches), default=None),
            'maximum_score_difference': max((float(abs(left_score[i] - right_score[j])) for i, j in matches), default=None),
            'reference_scores': left_score.tolist(), 'candidate_scores': right_score.tolist(),
            'reference_boxes': left.tolist(), 'candidate_boxes': right.tolist()}
        summaries.append(summary)
        print(json.dumps({k: v for k, v in summary.items() if k not in ('reference_scores', 'candidate_scores', 'reference_boxes', 'candidate_boxes', 'raw_quality')}), flush=True)
    result = {'scope': 'six cameras, first frame scene-0061, car. only; score>0.3; Hungarian IoU assignment >=0.5; not AP or full-scene quality',
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'reference': str(args.reference),
        'model_commit': manifest['model_commit'], 'providers': providers, 'runtime': args.runtime,
        'engine_sha256': engine_hash, 'cases': summaries,
        'positive_reference_images': sum(row['reference_count'] > 0 for row in summaries),
        'raw_quality_passed': all(row['raw_quality']['passed'] for row in summaries),
        'all_detection_counts_match': all(row['reference_count'] == row['candidate_count'] for row in summaries),
        'decision': 'diagnostic only; no production engine change'}
    (args.output / 'comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    if not result['positive_reference_images']:
        raise RuntimeError('No positive reference detections; quality diagnostic is inconclusive')


if __name__ == '__main__':
    main()
