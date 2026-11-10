"""
Rigid post-processing for VESPA-Direct pseudo labels.

1. build_tracklets: chains the pairwise keyframe matches of stage 07 (track_objects_in_next_frames) into tracks.
2. propagate: for each track with a user-chosen reference keyframe, every other member gets
   - size: the reference box size (rigid object),
   - position: its own box bottom center (taken directly from that frame),
   - yaw: heading from the velocity direction (central difference over the neighbouring members) plus the
     reference offset (reference yaw - reference heading); below speed_thr the previous yaw is kept.

Self-check: python -m src.postprocess.rigid_tracklet
"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.pointcloud.bbox import get_bbox_yaw

logger = logging.getLogger(__name__)

Track = List[Tuple[int, int]]  # [(frame_idx, obj_idx), ...] in frame order


def chain_matches(n_objects: List[int], matches: List[List[Optional[int]]]) -> List[Track]:
    """matches[t][i] = index of object i of frame t in frame t+1, or None. Matches are 1:1 (bidirectional check)."""
    assert len(matches) == max(len(n_objects) - 1, 0)
    tracks: List[Track] = []
    track_of: Dict[Tuple[int, int], int] = {}
    for t, n in enumerate(n_objects):
        for i in range(n):
            if (t, i) not in track_of:
                track_of[(t, i)] = len(tracks)
                tracks.append([(t, i)])
            if t < len(matches) and matches[t][i] is not None:
                nxt = (t + 1, matches[t][i])
                track_of[nxt] = track_of[(t, i)]
                tracks[track_of[nxt]].append(nxt)
    return tracks


def build_tracklets(scene, obj_info: dict, config: dict) -> List[Track]:
    """config: the 'velocity_by_app_tracking' section, same inputs as estimate_velocity_by_appearance_tracking."""
    from src.image.object_merge import _get_class_compatibility_mapping
    from src.tracking.appearance_tracking import track_objects_in_next_frames

    if config.get('use_highway_speeds', False):
        speed = lambda x: obj_info[x].speed_max_hw if config['velocity_ref_types'][x] == 'max' else obj_info[x].speed_avg_hw
    else:
        speed = lambda x: obj_info[x].speed_max if config['velocity_ref_types'][x] == 'max' else obj_info[x].speed_avg
    ref_speeds = {obj_type: speed(obj_type) for obj_type in obj_info.keys()}
    compat = _get_class_compatibility_mapping(config['compatible_class_groups'])

    frames = scene.frames
    matches = [track_objects_in_next_frames(scene, frames[t], ref_speeds, compat, frames[t + 1], config)
               for t in range(len(frames) - 1)]
    return chain_matches([len(f.objects) for f in frames], matches)


def _wrap(angle: float) -> float:
    return (angle + np.pi) % (2 * np.pi) - np.pi


def _lidar_to_world(scene, frame) -> np.ndarray:
    return np.linalg.inv(frame.world_to_ego) @ np.linalg.inv(scene.ego_to_lidar)


def propagate(scene, tracks: List[Track], refs: Dict[int, int], speed_thr: float):
    """refs: {track_id: reference keyframe index}. Tracks not in refs are left untouched."""
    objects = [list(f.objects) for f in scene.frames]
    for tid, ref_t in refs.items():
        track = tracks[tid]
        k_ref = next((k for k, (t, _) in enumerate(track) if t == ref_t), None)
        if k_ref is None:
            logger.warning(f"track {tid} has no member in keyframe {ref_t}, skipped")
            continue
        to_world = [_lidar_to_world(scene, scene.frames[t]) for t, _ in track]
        objs = [objects[t][i] for t, i in track]
        # obj.velocity is in that frame's lidar coordinates; only the rotation is needed (as in assign_labels.py)
        vel = [None if o.velocity is None else (tw[:3, :3] @ [o.velocity[0], o.velocity[1], 0.0])[:2]
               for o, tw in zip(objs, to_world)]

        def heading(k: int) -> Optional[float]:
            vs = [vel[j] for j in (k - 1, k) if j >= 0 and vel[j] is not None]  # (t-1 -> t) and (t -> t+1)
            if not vs:
                return None
            v = np.mean(vs, axis=0)
            return float(np.arctan2(v[1], v[0])) if np.linalg.norm(v) >= speed_thr else None

        yaw_ref = get_bbox_yaw(to_world[k_ref] @ objs[k_ref].bbox_to_lidar)
        h_ref = heading(k_ref)
        offset = _wrap(yaw_ref - h_ref) if h_ref is not None else 0.0
        dims = tuple(objs[k_ref].bbox_dims)

        for order in (range(k_ref + 1, len(track)), range(k_ref - 1, -1, -1)):
            yaw = yaw_ref
            for k in order:
                h = heading(k)
                yaw = yaw if h is None else _wrap(h + offset)
                box_world = np.eye(4)
                box_world[:2, :2] = [[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]]
                box_world[:3, 3] = (to_world[k] @ objs[k].bbox_to_lidar)[:3, 3]  # own bottom center
                t, i = track[k]
                objects[t][i] = objs[k].with_box(np.linalg.inv(to_world[k]) @ box_world, dims)

    return scene.with_new_frames([f.with_objects(o) for f, o in zip(scene.frames, objects)])


def _demo() -> None:
    from types import SimpleNamespace as NS
    from src.structures import Object

    # chaining: 0->0->(end), 1 starts at frame 0 and ends, a new track starts at frame 2
    tracks = chain_matches([2, 1, 2], [[0, None], [1]])
    assert tracks == [[(0, 0), (1, 0), (2, 1)], [(0, 1)], [(2, 0)]], tracks

    class F(NS):
        def with_objects(self, objs):
            return F(**{**vars(self), 'objects': objs})

    class S(NS):
        def with_new_frames(self, frames):
            return S(**{**vars(self), 'frames': frames})

    def pose(x: float, y: float, yaw: float) -> np.ndarray:
        m = np.eye(4)
        m[:2, :2] = [[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]]
        m[:3, 3] = (x, y, 0.3)
        return m

    # ego drives and turns; object moves +x in world at 2 m/s; frames 1, 2 have a small, badly rotated box
    ego_to_lidar = pose(0.5, 0.0, 0.1)
    world_to_ego = [pose(-3.0 * t, 1.0, 0.2 * t) for t in range(3)]
    scene = S(ego_to_lidar=ego_to_lidar, frames=[])
    for t in range(3):
        lidar_to_world = np.linalg.inv(world_to_ego[t]) @ np.linalg.inv(ego_to_lidar)
        world_to_lidar = np.linalg.inv(lidar_to_world)
        v_lidar = (world_to_lidar[:3, :3] @ [2.0, 0.0, 0.0])[:2]
        box = world_to_lidar @ pose(10.0 + t, 5.0, 0.0 if t == 0 else 0.7)
        dims = (4.5, 1.9, 1.6) if t == 0 else (2.0, 1.0, 1.2)
        obj = Object(np.zeros((1, 3)), box, dims, velocity=tuple(v_lidar))
        scene.frames.append(F(world_to_ego=world_to_ego[t], objects=[obj]))

    out = propagate(scene, [[(0, 0), (1, 0), (2, 0)]], {0: 0}, speed_thr=0.5)
    for t, frame in enumerate(out.frames):
        o = frame.objects[0]
        box_world = _lidar_to_world(scene, frame) @ o.bbox_to_lidar
        assert tuple(o.bbox_dims) == (4.5, 1.9, 1.6)
        assert abs(_wrap(get_bbox_yaw(box_world))) < 1e-9, get_bbox_yaw(box_world)
        assert np.allclose(box_world[:3, 3], (10.0 + t, 5.0, 0.3)), box_world[:3, 3]  # own center kept

    # slow object: yaw is held at the reference yaw
    for f in scene.frames:
        f.objects[0].velocity = (0.0, 0.0)
    out = propagate(scene, [[(0, 0), (1, 0), (2, 0)]], {0: 2}, speed_thr=0.5)
    yaw_ref = get_bbox_yaw(_lidar_to_world(scene, scene.frames[2]) @ scene.frames[2].objects[0].bbox_to_lidar)
    for frame in out.frames:
        assert abs(_wrap(get_bbox_yaw(_lidar_to_world(scene, frame) @ frame.objects[0].bbox_to_lidar) - yaw_ref)) < 1e-9
    print('rigid_tracklet self-check passed')


if __name__ == '__main__':
    _demo()
