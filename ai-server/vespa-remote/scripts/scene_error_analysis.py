"""
Per-scene error analysis of pseudo labels against GT, with a light diagnostic rerun recording per scene.

Boxes go through the same class mapping and filtering as the official evaluation (scripts/per_scene_eval.py).
Per keyframe, pseudo boxes are matched to GT boxes of the same class, highest score first, to the nearest free GT
within 2 m center distance (the nuScenes TP threshold). From the matches the report derives, per scene:
precision/recall, translation/orientation errors (incl. 180-degree flips), velocity errors on moving GT,
phantom motion on static GT, and where the misses and false positives are.

Scenes are then judged: 양호, or one or more failure types (검출 누락, 오검출, 방향 뒤집힘, 속도 오류).
The diagnostic .rrd shows per keyframe: LiDAR, CAM_FRONT, GT boxes (green = found, orange = missed),
pseudo boxes (blue = TP, red = FP) labelled with their errors, velocity arrows and TP/FP/FN counts.

Run from the repo root: python scripts/scene_error_analysis.py
"""
import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from pyquaternion import Quaternion

MATCH_DIST = 2.0              # m, nuScenes TP threshold
MOVING_SPEED = 0.5            # m/s, GT faster than this counts as moving
PHANTOM_SPEED = 1.0           # m/s, pseudo box on a static GT faster than this counts as phantom motion
FLIP_ANGLE = math.radians(150)
FAR_DIST = 30.0               # m
SPARSE_PTS = 5                # lidar points

# Failure rules. Recall/precision are relative to the median scene, the rest are absolute.
REL_DROP = 0.8
FLIP_RATE_TH = 0.25
AVE_MOVING_TH = 2.0           # m/s
PHANTOM_RATE_TH = 0.2

GREEN, ORANGE, BLUE, RED = (0, 200, 0), (255, 140, 0), (30, 144, 255), (220, 20, 60)


def center_dist(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a.translation[:2]) - np.asarray(b.translation[:2])))


def yaw_error(gt, pred) -> float:
    """Smallest yaw difference in [0, pi]."""
    d = Quaternion(pred.rotation).yaw_pitch_roll[0] - Quaternion(gt.rotation).yaw_pitch_roll[0]
    return abs((d + math.pi) % (2 * math.pi) - math.pi)


def speed(box) -> float:
    return float(np.linalg.norm(np.asarray(box.velocity[:2], dtype=float)))


def vel_error(gt, pred) -> float:
    return float(np.linalg.norm(np.asarray(pred.velocity[:2], dtype=float) - np.asarray(gt.velocity[:2], dtype=float)))


def _median(values: List[float]) -> float:
    values = [v for v in values if not math.isnan(v)]
    return statistics.median(values) if values else float('nan')


def _rate(flags: List[bool]) -> float:
    return sum(flags) / len(flags) if flags else float('nan')


def match_sample(gts: list, preds: list):
    """Greedy per-class matching as in the nuScenes accumulate(): highest score first, nearest free GT within 2 m."""
    matches, taken = [], set()
    for pred in sorted(preds, key=lambda b: -b.detection_score):
        best, best_dist = None, MATCH_DIST
        for idx, gt in enumerate(gts):
            if idx in taken or gt.detection_name != pred.detection_name:
                continue
            dist = center_dist(gt, pred)
            if dist < best_dist:
                best, best_dist = idx, dist
        if best is not None:
            taken.add(best)
        matches.append((pred, gts[best] if best is not None else None))
    missed = [gt for idx, gt in enumerate(gts) if idx not in taken]
    return matches, missed


def analyse_frames(samples: list) -> List[dict]:
    """samples: (sample_token, time_s, gt_boxes, pred_boxes) per keyframe, in time order."""
    frames = []
    for token, time_s, gts, preds in samples:
        matches, missed = match_sample(gts, preds)
        tp = [(p, g) for p, g in matches if g is not None]
        # An FP close to some GT is a duplicate (1-class) or a wrong class (3/8-class).
        fp = [(p, any(center_dist(g, p) < MATCH_DIST for g in gts)) for p, g in matches if g is None]
        frames.append({'token': token, 'time': time_s, 'tp': tp, 'fp': fp, 'fn': missed})
    return frames


def scene_stats(frames: List[dict]) -> Dict[str, float]:
    tp = [x for f in frames for x in f['tp']]
    fp = [x for f in frames for x in f['fp']]
    fn = [x for f in frames for x in f['fn']]
    yaws = [yaw_error(g, p) for p, g in tp]
    static = [(p, g) for p, g in tp if speed(g) < MOVING_SPEED]
    return {
        'TP': len(tp), 'FP': len(fp), 'FN': len(fn),
        'precision': len(tp) / (len(tp) + len(fp)) if tp or fp else float('nan'),
        'recall': len(tp) / (len(tp) + len(fn)) if tp or fn else float('nan'),
        'ATE': _median([center_dist(g, p) for p, g in tp]),
        'AOE°': math.degrees(_median(yaws)),
        'flip': _rate([y > FLIP_ANGLE for y in yaws]),
        'AVE mov': _median([vel_error(g, p) for p, g in tp if speed(g) >= MOVING_SPEED]),
        'phantom': _rate([speed(p) > PHANTOM_SPEED for p, _ in static]),
        'FP nearGT': _rate([near for _, near in fp]),
        'FN far': _rate([g.ego_dist > FAR_DIST for g in fn]),
        'FN sparse': _rate([g.num_pts < SPARSE_PTS for g in fn]),
    }


def judge(stats: Dict[str, float], median: Dict[str, float]) -> List[str]:
    tags = []
    if stats['recall'] < REL_DROP * median['recall']:
        tags.append('검출 누락')
    if stats['precision'] < REL_DROP * median['precision']:
        tags.append('오검출')
    if stats['flip'] > FLIP_RATE_TH:
        tags.append('방향 뒤집힘')
    if stats['AVE mov'] > AVE_MOVING_TH or stats['phantom'] > PHANTOM_RATE_TH:
        tags.append('속도 오류')
    return tags or ['양호']


def worst_frames(frames: List[dict], top: int = 3) -> str:
    start = frames[0]['time']
    ranked = sorted(enumerate(frames), key=lambda x: -(len(x[1]['fp']) + len(x[1]['fn'])))[:top]
    return ', '.join(f"#{k} (+{f['time'] - start:.1f}s: TP {len(f['tp'])} FP {len(f['fp'])} FN {len(f['fn'])})"
                     for k, f in ranked)


def write_rrd(path: Path, scene_name: str, frames: List[dict]) -> None:
    """frames need 'origin' and 'ego' (xyz), and optionally 'lidar' (N x 3, origin-relative) and 'image' (file path)."""
    import rerun as rr

    def boxes(entity: str, items: list, color, labels: Optional[List[str]], origin: np.ndarray) -> None:
        if not items:
            rr.log(entity, rr.Clear(recursive=False), recording=rec)
            return
        rr.log(entity, rr.Boxes3D(
            centers=[np.asarray(b.translation) - origin for b in items],
            sizes=[(b.size[1], b.size[0], b.size[2]) for b in items],  # nuScenes size is (w, l, h)
            quaternions=[rr.Quaternion(xyzw=[b.rotation[1], b.rotation[2], b.rotation[3], b.rotation[0]]) for b in items],
            colors=[color] * len(items), labels=labels), recording=rec)

    def arrows(entity: str, items: list, color, origin: np.ndarray) -> None:
        items = [b for b in items if not math.isnan(speed(b))]
        if not items:
            rr.log(entity, rr.Clear(recursive=False), recording=rec)
            return
        rr.log(entity, rr.Arrows3D(origins=[np.asarray(b.translation) - origin for b in items],
                                   vectors=[(b.velocity[0], b.velocity[1], 0.0) for b in items],
                                   colors=[color] * len(items)), recording=rec)

    rec = rr.new_recording(f'vespa_diag_{scene_name}')
    rr.save(str(path), recording=rec)
    rr.log('world', rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True, recording=rec)
    for k, f in enumerate(frames):
        origin = f['origin']
        rr.set_time_seconds('timestamp', f['time'], recording=rec)
        if f.get('lidar') is not None:
            rr.log('world/lidar', rr.Points3D(f['lidar'], colors=[(140, 140, 140)], radii=0.03), recording=rec)
        rr.log('world/ego', rr.Points3D([f['ego']], colors=[(255, 255, 255)], radii=0.4, labels=['ego']), recording=rec)

        found = [g for _, g in f['tp']]
        boxes('world/gt_found', found, GREEN, None, origin)
        boxes('world/gt_missed', f['fn'], ORANGE,
              [f"MISS {g.detection_name} {g.ego_dist:.0f}m pts{g.num_pts}" for g in f['fn']], origin)
        boxes('world/pred_tp', [p for p, _ in f['tp']], BLUE,
              [f"{p.detection_name} d{center_dist(g, p):.1f} yaw{math.degrees(yaw_error(g, p)):.0f} "
               f"v{vel_error(g, p):.1f}" for p, g in f['tp']], origin)
        boxes('world/pred_fp', [p for p, _ in f['fp']], RED,
              ['FP near GT' if near else 'FP' for _, near in f['fp']], origin)
        arrows('world/vel_gt', found + f['fn'], GREEN, origin)
        arrows('world/vel_pred', [p for p, _ in f['tp']] + [p for p, _ in f['fp']], RED, origin)

        if f.get('image'):
            rr.log('camera/CAM_FRONT', rr.EncodedImage(path=f['image']), recording=rec)
        for name in ('tp', 'fp', 'fn'):
            rr.log(f'stats/{name.upper()}', rr.Scalar(len(f[name])), recording=rec)
        rr.log('log', rr.TextLog(f"keyframe #{k}: TP {len(f['tp'])} FP {len(f['fp'])} FN {len(f['fn'])}"), recording=rec)
    rr.disconnect(recording=rec)


def attach_sensors(nusc, frames: List[dict]) -> None:
    """Adds keyframe LiDAR (global frame, relative to the first ego pose), ego position and CAM_FRONT path."""
    from nuscenes.utils.data_classes import LidarPointCloud

    origin = None
    for f in frames:
        sample = nusc.get('sample', f['token'])
        lidar_sd = nusc.get('sample_data', sample['data']['LIDAR_TOP'])
        sensor = nusc.get('calibrated_sensor', lidar_sd['calibrated_sensor_token'])
        pose = nusc.get('ego_pose', lidar_sd['ego_pose_token'])
        if origin is None:
            origin = np.asarray(pose['translation'])
        pc = LidarPointCloud.from_file(nusc.get_sample_data_path(lidar_sd['token']))
        pc.rotate(Quaternion(sensor['rotation']).rotation_matrix)
        pc.translate(np.asarray(sensor['translation']))
        pc.rotate(Quaternion(pose['rotation']).rotation_matrix)
        pc.translate(np.asarray(pose['translation']))
        f['lidar'] = (pc.points[:3].T - origin).astype(np.float32)
        f['ego'] = np.asarray(pose['translation']) - origin
        f['origin'] = origin
        f['image'] = nusc.get_sample_data_path(sample['data']['CAM_FRONT'])


def fmt(v) -> str:
    return f'{v:.3f}' if isinstance(v, float) else str(v)


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import yaml
    from nuscenes.utils import splits
    from src.data.nuscenes import _NuscenesSingleton
    from per_scene_eval import make_scene_eval, scene_sample_tokens

    parser = argparse.ArgumentParser(description='Per-scene error analysis of pseudo labels')
    parser.add_argument('--config', type=Path, default=Path('configs/vlm/p_final.yaml'))
    parser.add_argument('--mappings', type=str, nargs='+', default=['1class', '8class'])
    parser.add_argument('--rrd_mapping', type=str, default='8class', help='mapping whose matches the .rrd files show')
    parser.add_argument('--scenes', type=str, nargs='+', default=None, help='default: all mini scenes')
    parser.add_argument('--no_rrd', action='store_true')
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    exp, data = args.config.stem, config['data']
    nusc = _NuscenesSingleton.get_nuscenes_instance(data['dataset_version'], data['root_path'])
    mini = data['dataset_version'] == 'v1.0-mini'
    split_of = {s: 'train' for s in (splits.mini_train if mini else splits.train)}
    split_of.update({s: 'val' for s in (splits.mini_val if mini else splits.val)})
    eval_set = 'mini_train' if mini else 'train'
    scenes = args.scenes or list(split_of)
    out_dir = Path('outs') / config['type'] / exp / '#analysis'

    lines = [f'# Scene error analysis ({exp}, {data["dataset_version"]})', '',
             f'매칭: 같은 class, 중심거리 < {MATCH_DIST} m (nuScenes TP 기준), 점수 높은 순 greedy.',
             f'판정: recall/precision이 scene 중앙값의 {REL_DROP:.0%} 미만이면 검출 누락/오검출, '
             f'yaw {math.degrees(FLIP_ANGLE):.0f}도 이상 틀린 TP 비율(flip) > {FLIP_RATE_TH}이면 방향 뒤집힘, '
             f'움직이는 GT의 속도오차 중앙값(AVE mov) > {AVE_MOVING_TH} m/s 또는 '
             f'정지 GT에 {PHANTOM_SPEED} m/s 넘는 속도를 준 비율(phantom) > {PHANTOM_RATE_TH}이면 속도 오류.',
             f'FP nearGT: GT 옆의 FP(1class는 중복 박스, 8class는 class 오분류). '
             f'FN far/sparse: 놓친 GT 중 {FAR_DIST:.0f} m 밖 / LiDAR {SPARSE_PTS}점 미만 비율.', '']

    for mapping in args.mappings:
        submission_path = Path('outs') / config['type'] / exp / '#out_labels' / f'{config["type"]}_{exp}_all_{mapping}.json'
        with open(submission_path, 'r') as f:
            submission = json.load(f)

        rows = []
        for scene_name in scenes:
            nusc_eval = make_scene_eval(nusc, submission, scene_name, eval_set, mapping, out_dir / 'eval' / mapping / scene_name)
            samples = [(t, nusc.get('sample', t)['timestamp'] * 1e-6,
                        nusc_eval.gt_boxes.boxes.get(t, []), nusc_eval.pred_boxes.boxes.get(t, []))
                       for t in scene_sample_tokens(nusc, scene_name)]
            frames = analyse_frames(samples)
            rows.append({'scene': scene_name, 'split': split_of[scene_name], **scene_stats(frames),
                         'worst': worst_frames(frames)})
            if mapping == args.rrd_mapping and not args.no_rrd:
                attach_sensors(nusc, frames)
                rrd_path = out_dir / 'rrd' / f'diag_{scene_name}.rrd'
                rrd_path.parent.mkdir(parents=True, exist_ok=True)
                write_rrd(rrd_path, scene_name, frames)
            print(f'[{mapping}] {scene_name}: P={rows[-1]["precision"]:.3f} R={rows[-1]["recall"]:.3f}', flush=True)

        keys = ['precision', 'recall', 'flip', 'AVE mov', 'phantom']
        median = {k: _median([r[k] for r in rows]) for k in keys}
        for r in rows:
            r['판정'] = ', '.join(judge(r, median))
        rows.sort(key=lambda r: (r['판정'] != '양호', -(r['precision'] * r['recall'])))

        cols = ['scene', 'split', '판정', 'TP', 'FP', 'FN', 'precision', 'recall', 'ATE', 'AOE°', 'flip',
                'AVE mov', 'phantom', 'FP nearGT', 'FN far', 'FN sparse']
        lines += [f'## {mapping}', '', '| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
        lines += ['| ' + ' | '.join(fmt(r[c]) for c in cols) + ' |' for r in rows]
        lines += ['', '중앙값: ' + ', '.join(f'{k} {v:.3f}' for k, v in median.items()), '',
                  '### FP+FN이 가장 많은 keyframe (rerun 타임라인에서 볼 위치)', '']
        lines += [f"- {r['scene']} ({r['판정']}): {r['worst']}" for r in rows]
        lines.append('')

    if not args.no_rrd:
        lines += [f'진단용 .rrd ({args.rrd_mapping} 기준): {out_dir / "rrd"}/diag_<scene>.rrd',
                  '색: 초록 = 찾은 GT, 주황 = 놓친 GT, 파랑 = TP 가짜 라벨, 빨강 = FP 가짜 라벨. '
                  'TP 라벨의 d/yaw/v = 중심거리(m)/방향오차(도)/속도오차(m/s).']

    report = '\n'.join(lines)
    print('\n' + report)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'scene_error_analysis.md').write_text(report, encoding='utf-8')
    print(f'\nSaved to {out_dir / "scene_error_analysis.md"}')


if __name__ == '__main__':
    main()
