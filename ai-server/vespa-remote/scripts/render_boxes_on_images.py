"""
Draws GT and pseudo-label 3D boxes onto the six camera images and a LiDAR bird's-eye view, one image per keyframe,
plus an mp4 per scene, so results can be shared without the rerun viewer.

Boxes, matching and colours follow scripts/scene_error_analysis.py (same filters and 2 m matching as the evaluation):
green = GT found by a pseudo label, orange = GT missed, blue = matched pseudo label (labelled with its 3D IoU),
red = pseudo label without a GT (false positive). The line from a box centre marks its front.

Run from the repo root:
python scripts/render_boxes_on_images.py --config configs/vlm/p_final_trainval.yaml --scenes scene-0553 scene-0655
Output: outs/<type>/<exp>/#analysis/images/<mapping>/<scene>/<keyframe>.jpg and <scene>.mp4 (mp4v; plays in VLC)
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from pyquaternion import Quaternion
from nuscenes.utils.data_classes import Box, LidarPointCloud
from nuscenes.utils.geometry_utils import BoxVisibility, box_in_image, view_points

from box_error_report import iou_3d
from scene_error_analysis import analyse_frames

CAMS = [['CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT'], ['CAM_BACK_LEFT', 'CAM_BACK', 'CAM_BACK_RIGHT']]
TILE_W, TILE_H = 800, 450
BEV_PX, BEV_RANGE = 2 * TILE_H, 50.0     # BEV panel size [px] and half range around the ego vehicle [m]
HEADER_H = 60
GREEN, ORANGE, BLUE, RED = (0, 200, 0), (0, 140, 255), (255, 144, 30), (60, 20, 220)  # BGR
FONT = cv2.FONT_HERSHEY_SIMPLEX

Item = Tuple[object, Tuple[int, int, int], str]  # (eval box in the global frame, colour, label)


def to_frame(eval_box, *poses) -> Box:
    """Global-frame eval box -> devkit Box in the frame of the last pose; each pose is undone in order."""
    box = Box(list(eval_box.translation), list(eval_box.size), Quaternion(eval_box.rotation))
    for pose in poses:
        box.translate(-np.asarray(pose['translation']))
        box.rotate(Quaternion(pose['rotation']).inverse)
    return box


def draw_camera(nusc, sd_token: str, items: List[Item]) -> np.ndarray:
    sd = nusc.get('sample_data', sd_token)
    cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
    pose = nusc.get('ego_pose', sd['ego_pose_token'])
    img = cv2.imread(nusc.get_sample_data_path(sd_token))
    intrinsic = np.asarray(cs['camera_intrinsic'])
    for eval_box, color, label in items:
        box = to_frame(eval_box, pose, cs)
        if not box_in_image(box, intrinsic, (img.shape[1], img.shape[0]), vis_level=BoxVisibility.ANY):
            continue
        rgb = color[::-1]  # render_cv2 takes RGB and flips it to BGR itself
        box.render_cv2(img, view=intrinsic, normalize=True, colors=(rgb, rgb, rgb), linewidth=3)
        if label:
            u, v = view_points(box.corners(), intrinsic, normalize=True)[:2].min(axis=1)
            cv2.putText(img, label, (int(np.clip(u, 0, img.shape[1] - 200)), int(np.clip(v - 8, 30, img.shape[0]))),
                        FONT, 1.4, color, 3, cv2.LINE_AA)
    cv2.putText(img, sd['channel'], (20, 50), FONT, 1.6, (255, 255, 255), 3, cv2.LINE_AA)
    return cv2.resize(img, (TILE_W, TILE_H))


def draw_bev(nusc, lidar_token: str, items: List[Item]) -> np.ndarray:
    sd = nusc.get('sample_data', lidar_token)
    cs = nusc.get('calibrated_sensor', sd['calibrated_sensor_token'])
    pose = nusc.get('ego_pose', sd['ego_pose_token'])
    scale = BEV_PX / (2 * BEV_RANGE)

    def px(xy: np.ndarray) -> np.ndarray:  # ego frame, x forward = up, y left = left
        return np.stack([BEV_PX / 2 - xy[..., 1] * scale, BEV_PX / 2 - xy[..., 0] * scale], axis=-1).astype(np.int32)

    img = np.full((BEV_PX, BEV_PX, 3), 25, np.uint8)
    pc = LidarPointCloud.from_file(nusc.get_sample_data_path(lidar_token))
    pc.rotate(Quaternion(cs['rotation']).rotation_matrix)
    pc.translate(np.asarray(cs['translation']))
    uv = px(pc.points[:2].T)
    ok = (uv >= 0).all(axis=1) & (uv < BEV_PX).all(axis=1)
    img[uv[ok, 1], uv[ok, 0]] = (150, 150, 150)
    for radius in (10, 20, 30, 40, 50):
        cv2.circle(img, (BEV_PX // 2, BEV_PX // 2), int(radius * scale), (70, 70, 70), 1)
    for eval_box, color, _ in items:
        bottom = to_frame(eval_box, pose).bottom_corners()[:2].T  # first two corners face forward
        cv2.polylines(img, [px(bottom)], True, color, 2)
        cv2.line(img, tuple(px(bottom.mean(axis=0))), tuple(px(bottom[:2].mean(axis=0))), color, 2)
    cv2.rectangle(img, tuple(px(np.array([2.3, 1.0]))), tuple(px(np.array([-2.3, -1.0]))), (255, 255, 255), -1)
    cv2.putText(img, f'BEV  rings every 10 m', (15, 35), FONT, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def render_keyframe(nusc, sample_token: str, frame: dict, title: str) -> np.ndarray:
    items: List[Item] = [(g, GREEN, '') for _, g in frame['tp']]
    items += [(g, ORANGE, 'MISS') for g in frame['fn']]
    items += [(p, BLUE, f'{p.detection_name} IoU{iou_3d(p, g):.2f}') for p, g in frame['tp']]
    items += [(p, RED, f'FP {p.detection_name}') for p, _ in frame['fp']]
    sample = nusc.get('sample', sample_token)
    grid = np.vstack([np.hstack([draw_camera(nusc, sample['data'][cam], items) for cam in row]) for row in CAMS])
    body = np.hstack([grid, draw_bev(nusc, sample['data']['LIDAR_TOP'], items)])

    header = np.full((HEADER_H, body.shape[1], 3), 255, np.uint8)
    cv2.putText(header, title, (15, 40), FONT, 1.0, (0, 0, 0), 2, cv2.LINE_AA)
    x = body.shape[1] - 1200
    for color, text in ((GREEN, 'GT found'), (ORANGE, 'GT missed'), (BLUE, 'pseudo TP'), (RED, 'pseudo FP')):
        cv2.rectangle(header, (x, 18), (x + 30, 44), color, -1)
        cv2.putText(header, text, (x + 40, 40), FONT, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
        x += 300
    return np.vstack([header, body])


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import yaml
    from nuscenes.utils import splits
    from src.data.nuscenes import _NuscenesSingleton
    from per_scene_eval import make_scene_eval, scene_sample_tokens

    parser = argparse.ArgumentParser(description='Draw GT and pseudo-label boxes on camera images and BEV')
    parser.add_argument('--config', type=Path, default=Path('configs/vlm/p_final_trainval.yaml'))
    parser.add_argument('--mapping', type=str, default='8class')
    parser.add_argument('--scenes', type=str, nargs='+', default=['scene-0553', 'scene-0655', 'scene-0757', 'scene-1077'])
    parser.add_argument('--no_video', action='store_true')
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    exp, data = args.config.stem, config['data']
    nusc = _NuscenesSingleton.get_nuscenes_instance(data['dataset_version'], data['root_path'])
    mini = data['dataset_version'] == 'v1.0-mini'
    split_of = {s: 'train' for s in (splits.mini_train if mini else splits.train)}
    split_of.update({s: 'val' for s in (splits.mini_val if mini else splits.val)})
    eval_set = 'mini_train' if mini else 'train'
    out_dir = Path('outs') / config['type'] / exp / '#analysis'
    with open(out_dir.parent / '#out_labels' / f'{config["type"]}_{exp}_all_{args.mapping}.json', 'r') as f:
        submission = json.load(f)

    for scene_name in args.scenes:
        nusc_eval = make_scene_eval(nusc, submission, scene_name, eval_set, args.mapping,
                                    out_dir / 'eval' / args.mapping / scene_name)
        tokens = scene_sample_tokens(nusc, scene_name)
        frames = analyse_frames([(t, nusc.get('sample', t)['timestamp'] * 1e-6, nusc_eval.gt_boxes.boxes.get(t, []),
                                  nusc_eval.pred_boxes.boxes.get(t, [])) for t in tokens])
        scene_dir = out_dir / 'images' / args.mapping / scene_name
        scene_dir.mkdir(parents=True, exist_ok=True)
        writer = None
        for k, (token, frame) in enumerate(zip(tokens, frames)):
            title = (f'{exp} {args.mapping} | {scene_name} ({split_of.get(scene_name, "?")}) | keyframe {k + 1}/{len(frames)}'
                     f' +{frame["time"] - frames[0]["time"]:.1f}s | TP {len(frame["tp"])} FP {len(frame["fp"])}'
                     f' FN {len(frame["fn"])}')
            canvas = render_keyframe(nusc, token, frame, title)
            cv2.imwrite(str(scene_dir / f'{k:03d}.jpg'), canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not args.no_video:
                if writer is None:
                    writer = cv2.VideoWriter(str(scene_dir.parent / f'{scene_name}.mp4'), cv2.VideoWriter_fourcc(*'mp4v'),
                                             2, (canvas.shape[1], canvas.shape[0]))
                writer.write(canvas)
        if writer is not None:
            writer.release()
        print(f'{scene_name}: {len(frames)} keyframes -> {scene_dir}', flush=True)


if __name__ == '__main__':
    main()
