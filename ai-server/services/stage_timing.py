"""Wall/CPU stage timings for the isolated VESPA runner; no model arguments are logged."""
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import json
from pathlib import Path
import time


class StageTimer:
    def __init__(self, directory, scene, job_id=None):
        self.directory = Path(directory)
        self.context = {'job_id': job_id, 'run_id': self.directory.name, 'scene': scene}
        self.calls = {}

    def emit(self, stage, event, **values):
        row = {'at': datetime.now(timezone.utc).isoformat(), **self.context,
               'stage': stage, 'event': event, **values}
        line = json.dumps(row, allow_nan=False)
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / 'stage-events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(line + '\n')
        print('DS2L_STAGE ' + line, flush=True)

    @contextmanager
    def stage(self, name):
        call = self.calls.get(name, 0) + 1
        self.calls[name] = call
        self.emit(name, 'started', call=call)
        wall, cpu = time.perf_counter(), time.process_time()
        try:
            yield
        except BaseException as error:
            self.emit(name, 'failed', call=call, wall_seconds=round(time.perf_counter()-wall, 6),
                      cpu_seconds=round(time.process_time()-cpu, 6), error_type=type(error).__name__)
            raise
        else:
            self.emit(name, 'completed', call=call, wall_seconds=round(time.perf_counter()-wall, 6),
                      cpu_seconds=round(time.process_time()-cpu, 6))

    def wrap(self, name, function):
        @wraps(function)
        def measured(*args, **kwargs):
            with self.stage(name):
                return function(*args, **kwargs)
        return measured

    def instrument(self, module, stages):
        for function, stage in stages.items():
            setattr(module, function, self.wrap(stage, getattr(module, function)))


VESPA_STAGES = {
    'load_dataset_scene': 'dataset_load',
    'remove_ground': 'ground_removal',
    'generate_segmentation_masks': 'image_detection_segmentation',
    'reproject_lidar_to_segmentation': 'lidar_reprojection',
    'denoise_object_clusters': 'cluster_denoising',
    'appearance_embed_mask_based': 'dinov2_features',
    'merge_multicamera_objects': 'multicamera_merge',
    'estimate_velocity_by_appearance_tracking': 'velocity_tracking',
    'estimate_yaw_from_tracking_and_shape': 'yaw_estimation',
    'inflate_bboxes_to_common_size': 'bbox_inflation',
    'filter_objects': 'object_filtering',
    'assign_pseudo_class_labels_from_sam_label': 'class_assignment',
    'get_scene_pseudo_annotations_by_mapping': 'annotation_mapping',
}
