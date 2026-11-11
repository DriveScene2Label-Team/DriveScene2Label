"""
Per-scene VESPA-Direct + rigid post-processing (based on main_pseudo_vlm_scene.py).

Same stages as process_scene in main_pseudo_vlm.py (01-07 load from cache), plus:
  after 07           : build tracklets by chaining the pairwise keyframe matches (src/postprocess/rigid_tracklet.py)
  before filtering   : if --refs is given, rewrite every member of a referenced track from its reference box
                       (size and yaw from the reference, bottom center from the frame itself)

python main_pseudo_vlm_scene_ver2.py --config configs/vlm/p_final.yaml --scenes scene-0061 --tag base
python main_pseudo_vlm_scene_ver2.py --config configs/vlm/p_final.yaml --scenes scene-0061 --tag ref1 --refs refs.json

refs.json: {"scene-0061": {"<track_id>": <keyframe index>, ...}, ...}
Output: outs/vlm/<exp>/#rigid/<tag>/
  labels_<scene>_<mapping>.json : same format as #out_labels_scene (nuScenes submission)
  tracks_<scene>.json           : {"frames": [sample_token per keyframe index],
                                   "track_ids": {sample_token: [track id per box, same order as the labels]}}
Without --refs the labels must equal main_pseudo_vlm_scene.py's output (regression check).
"""
import argparse
import json
import logging
from pathlib import Path

import yaml

from main_pseudo_union import get_out_dir
from main_pseudo_vlm import (load_dataset_scene, remove_ground, generate_segmentation_masks,
                             reproject_lidar_to_segmentation, denoise_object_clusters, appearance_embed_mask_based,
                             merge_multicamera_objects, estimate_velocity_by_appearance_tracking,
                             estimate_yaw_from_tracking_and_shape, inflate_bboxes_to_common_size, filter_objects,
                             assign_pseudo_class_labels_from_sam_label, get_scene_pseudo_annotations_by_mapping)
from src.data.dataset import get_dataset_scene_names
from src.labeling.prior_info import get_common_object_infos_sam
from src.labeling.submission import _get_annotation_dict
from src.postprocess.rigid_tracklet import build_tracklets, propagate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_scene_rigid(scene_name: str, obj_info: dict, config: dict, refs: dict, prepared=None):
    scene = load_dataset_scene(config['data'], scene_name)
    scene = remove_ground(scene, config['remove_ground'], get_out_dir(config, '01_remove_ground'))
    scene = generate_segmentation_masks(scene, config['grounding_sam'], get_out_dir(config, '02_grounding_sam'))
    scene = reproject_lidar_to_segmentation(scene, config['reprojection'], get_out_dir(config, '03_reprojection'))
    scene = denoise_object_clusters(scene, obj_info, config['denoising'], get_out_dir(config, '04_denoising'))
    scene = appearance_embed_mask_based(scene, config['appearance_embedding'],
                                        get_out_dir(config, '05_appearance_embedding_mask'))
    scene = merge_multicamera_objects(scene, obj_info, config['multicam_object_merge'],
                                      get_out_dir(config, '06_multicam_object_merge'))
    scene = estimate_velocity_by_appearance_tracking(scene, obj_info, config['velocity_by_app_tracking'],
                                                     get_out_dir(config, '07_velocity_by_tracking'))

    logger.info("Building tracklets")
    tracks = build_tracklets(scene, obj_info, config['velocity_by_app_tracking'])
    lengths = sorted(len(t) for t in tracks)
    logger.info(f"{scene_name}: {len(tracks)} tracks, median length {lengths[len(lengths) // 2] if lengths else 0}, "
                f"max {lengths[-1] if lengths else 0}")

    # yaw heuristic and inflation keep frame.objects 1:1, so track indices stay valid
    scene = estimate_yaw_from_tracking_and_shape(scene, obj_info, config['yaw_heuristic'])
    scene = inflate_bboxes_to_common_size(scene, obj_info, config['bbox_inflation'])
    if prepared is not None:
        prepared(scene, tracks)
    return finish_scene_rigid(scene, tracks, config, refs)


def finish_scene_rigid(scene, tracks, config: dict, refs: dict, prepared=None):
    """CPU-only replay of the same pre-filter state; never reruns stages 01–07."""
    for tid, frame in refs.items():
        if tid < 0 or tid >= len(tracks) or not any(t == frame for t, _ in tracks[tid]):
            raise ValueError("Reference must belong to the selected track")
    if refs:
        logger.info(f"Propagating {len(refs)} reference boxes")
        scene = propagate(scene, tracks, refs, config['yaw_heuristic']['speed_threshold'])
    if prepared is not None:
        prepared(scene, tracks)

    # filtering drops objects and later steps copy them, but every copy shares the bbox_to_lidar array
    track_of = {(t, i): tid for tid, track in enumerate(tracks) for t, i in track}
    tid_of_box = {id(o.bbox_to_lidar): track_of[(t, i)]
                  for t, f in enumerate(scene.frames) for i, o in enumerate(f.objects)}

    scene = filter_objects(scene, config['object_filtering'])
    scene = assign_pseudo_class_labels_from_sam_label(scene)
    annotations_by_mapping = get_scene_pseudo_annotations_by_mapping(scene)
    tracks_out = {'frames': [f.sample_token for f in scene.frames],
                  'track_ids': {f.sample_token: [tid_of_box[id(o.bbox_to_lidar)] for o in f.objects]
                                for f in scene.frames}}
    return annotations_by_mapping, scene.split, tracks_out


def write_outputs(annotations_by_mapping: dict, split: str, tracks_out: dict, scene_name: str, out_dir: Path) -> None:
    for mapping_name, annotations_by_sample in annotations_by_mapping.items():
        submission = {
            "split": split,
            "mapping_name": mapping_name,
            "meta": {"use_camera": True, "use_lidar": True, "use_radar": False, "use_map": False, "use_external": False},
            "results": {token: [_get_annotation_dict(a, token) for a in annotations]
                        for token, annotations in annotations_by_sample.items()},
        }
        with open(out_dir / f"labels_{scene_name}_{mapping_name}.json", 'w') as f:
            json.dump(submission, f, indent=2)
    with open(out_dir / f"tracks_{scene_name}.json", 'w') as f:
        json.dump(tracks_out, f)
    logger.info(f"Wrote {scene_name} -> {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description='Per-scene pseudo labels with rigid tracklet post-processing')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--scenes', type=str, nargs='+', required=True)
    parser.add_argument('--refs', type=Path, default=None, help='{scene: {track_id: keyframe index}}')
    parser.add_argument('--tag', type=str, default='base')
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    assert config['type'] == 'vlm', f"Config file {args.config} is not a valid config file for this script"
    config['exp_name'] = args.config.stem

    scene_names_all = get_dataset_scene_names(config['data'])
    assert all(s in scene_names_all for s in args.scenes), f"Some scenes {args.scenes} are not in the dataset"
    refs_all = {}
    if args.refs is not None:
        with open(args.refs, 'r') as f:
            refs_all = json.load(f)

    obj_info = get_common_object_infos_sam(config['grounding_sam']['class_names'])
    out_dir = get_out_dir(config, f"#rigid/{args.tag}")
    for idx, scene_name in enumerate(args.scenes, 1):
        logger.info(f"Running scene {scene_name}, {idx}/{len(args.scenes)}")
        refs = {int(tid): int(k) for tid, k in refs_all.get(scene_name, {}).items()}
        annotations_by_mapping, split, tracks_out = process_scene_rigid(scene_name, obj_info, config, refs)
        write_outputs(annotations_by_mapping, split, tracks_out, scene_name, out_dir)


if __name__ == '__main__':
    main()
