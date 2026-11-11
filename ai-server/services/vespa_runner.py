"""External adapter executed in VESPA's environment. Does not edit upstream files."""
import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from stage_timing import StageTimer, VESPA_STAGES


def main():
    p = argparse.ArgumentParser()
    for name in ("repo", "config", "scene", "output-root", "data-root", "dataset-version"):
        p.add_argument("--"+name, required=True)
    p.add_argument("--class-mode", type=int, choices=(1,3,8), required=True)
    p.add_argument("--rigid", action="store_true")
    p.add_argument("--source-run", type=Path)
    p.add_argument("--references", type=Path)
    p.add_argument("--job-id", type=int)
    a = p.parse_args()
    timer = StageTimer(a.output_root, a.scene, a.job_id)
    sys.path.insert(0, str(Path(a.repo).resolve()))
    with timer.stage("runtime_import"):
        import yaml
        import numpy as np
        # Scope compatibility to this subprocess; leave upstream files intact.
        np.__dict__.setdefault("bool", np.bool_)
        np.__dict__.setdefault("concat", np.concatenate)
        np.__dict__.setdefault("atan2", np.arctan2)
        np.__dict__.setdefault("int", int)
        import main_pseudo_union
        import main_pseudo_vlm
        from src.labeling.submission import _get_annotation_dict
        from src.labeling.prior_info import get_common_object_infos_sam
    # Install before the rigid module imports these functions. Algorithms/arguments stay unchanged.
    timer.instrument(main_pseudo_vlm, VESPA_STAGES)
    import src.image.grounding_sam as grounding_sam
    import torch
    # SAM is only used for inference. Upstream calls its model directly with autograd enabled.
    # Keep the change scoped to this child process; preserve weights, precision and mask operations.
    grounding_sam._sam_segmentation = torch.inference_mode()(grounding_sam._sam_segmentation)
    timer.emit("sam_inference_mode", "enabled")
    timer.instrument(grounding_sam, {
        "_vlm_detection": "grounding_dino_detection",
        "_sam_segmentation": "sam_inference_postprocess",
        "_refine_masks": "mask_refinement",
        "_non_max_suppression": "mask_nms",
    })
    # The singleton caches remain intact; first access includes model loading, later accesses are cache hits.
    for owner, name in ((grounding_sam._VlmDetectorSingleton, "detector_model_get"),
                        (grounding_sam._SamSegmentatorSingleton, "sam_model_get")):
        owner.get_model_instance = staticmethod(timer.wrap(name, owner.get_model_instance))

    path = Path(a.config)
    config = yaml.safe_load(path.read_text())
    if config["type"] != "vlm" or config["data"]["dataset"] != "nuscenes":
        raise ValueError("Expected nuScenes VLM configuration")
    config["exp_name"] = path.stem
    config["data"]["root_path"] = a.data_root
    config["data"]["dataset_version"] = a.dataset_version
    main_pseudo_union.EXP_PSEUDO_OUT_PATH = Path(a.output_root).resolve() / "outs"
    with timer.stage("class_prior_preparation"):
        infos = get_common_object_infos_sam(config["grounding_sam"]["class_names"])
    tracks = None
    if a.rigid:
        remote = Path(__file__).resolve().parents[1] / "vespa-remote"
        import src
        src.__path__.append(str(remote / "src"))
        sys.path.insert(0, str(remote))
        import main_pseudo_vlm_scene_ver2 as rigid
        timer.instrument(rigid, {"build_tracklets": "tracklet_build", "propagate": "reference_propagation"})
        from rigid_cache import save, load, references
        save = timer.wrap("rigid_cache_save", save)
        load = timer.wrap("rigid_cache_load", load)
        scope = {"scene": a.scene, "root": str(Path(a.data_root).resolve()), "version": a.dataset_version, "class_mode": a.class_mode}
        if a.source_run:
            scene, tracklets, cached_config = load(a.source_run, scope)
            refs = references(scene, tracklets, json.loads(a.references.read_text()))
            annotations, split, tracks = rigid.finish_scene_rigid(scene, tracklets, cached_config, refs,
                prepared=lambda corrected, tracklets: save(Path(a.output_root), corrected, tracklets, cached_config, scope))
        else:
            annotations, split, tracks = rigid.process_scene_rigid(a.scene, infos, config, {},
                prepared=lambda scene, tracklets: save(Path(a.output_root), scene, tracklets, config, scope))
    else:
        annotations, split = main_pseudo_vlm.process_scene(a.scene, infos, config, SimpleNamespace(visualize=False))
    mapping = f"{a.class_mode}class"
    payload = {"split": split, "mapping_name": mapping,
        "meta": {"use_camera": True, "use_lidar": True, "use_radar": False, "use_map": False, "use_external": False},
        "results": {token: [_get_annotation_dict(box, token) for box in boxes]
                    for token, boxes in annotations[mapping].items()}}
    if tracks is not None:
        for token, boxes in payload["results"].items():
            ids = tracks["track_ids"][token]
            if len(ids) != len(boxes):
                raise ValueError("Track/box mapping mismatch")
            for box, tid in zip(boxes, ids):
                box["track_id"] = tid
        payload["track_frames"] = tracks["frames"]
    output = main_pseudo_union.get_out_dir(config, "#out_labels") / f"vlm_{config['exp_name']}_{a.scene}_{mapping}.json"
    with timer.stage("result_json_write"):
        output.write_text(json.dumps(payload, indent=2, allow_nan=False))

if __name__ == "__main__":
    main()
