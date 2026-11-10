"""
Tracklet view of the rigid post-processing output (based on render_boxes_on_images.py).

Reads outs/<type>/<exp>/#rigid/<tag>/labels_<scene>_<mapping>.json and tracks_<scene>.json
(written by main_pseudo_vlm_scene_ver2.py) and, per scene:
  - draws every pseudo box coloured and labelled by its track id (T<id>) on the six cameras and the BEV,
    GT boxes in grey; one jpg per keyframe and an mp4. The keyframe index in the title is the index for refs.json.
  - writes track_report_<scene>_<mapping>.md: track lengths and GT-based ID quality. Each pseudo box is matched
    one-to-one to the nearest GT vehicle/pedestrian within 2 m (BEV, class-agnostic) and gets its instance_token.
      purity        : share of a track's matched boxes that belong to its majority GT instance
      ID switches   : consecutive matched boxes of one track with different GT instances
      fragmentation : number of tracks one GT instance is split into
    plus a per-track table to pick reference keyframes from.

Run from the repo root:
python scripts/render_boxes_on_images_ver2.py --config configs/vlm/p_final.yaml --tag base --scenes scene-0061
Output: outs/<type>/<exp>/#rigid/<tag>/images/<mapping>/<scene>/<keyframe>.jpg, <scene>.mp4, track_report_*.md
"""
import argparse
import colorsys
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

import cv2
import numpy as np

from render_boxes_on_images import BEV_PX, BEV_RANGE, CAMS, FONT, HEADER_H, draw_bev, draw_camera, to_frame
from scene_error_analysis import yaw_error

MATCH_DIST = 2.0  # m, nuScenes TP threshold
GREY = (160, 160, 160)
RED = (0, 0, 255)  # BGR, boxes of --compare_tag
GT_CATEGORIES = ('vehicle.', 'human.pedestrian')


def track_color(tid: int):
    hue = 0.1 + 0.8 * ((tid * 0.618034) % 1.0)  # skip red hues, red is reserved for --compare_tag
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return int(b * 255), int(g * 255), int(r * 255)  # BGR


def _med(values: list) -> float:
    return statistics.median(values) if values else float('nan')


def match_to_gt(preds: list, gts: list) -> List[Optional[int]]:
    """One-to-one greedy matching by BEV center distance; returns the GT index per pred or None."""
    pairs = sorted((np.linalg.norm(np.subtract(p.translation[:2], g.translation[:2])), i, j)
                   for i, p in enumerate(preds) for j, g in enumerate(gts))
    out: List[Optional[int]] = [None] * len(preds)
    used = set()
    for dist, i, j in pairs:
        if dist >= MATCH_DIST:
            break
        if out[i] is None and j not in used:
            out[i] = j
            used.add(j)
    return out


def _error_line(name: str, errs: list) -> str:
    """errs: [(center, size, yaw_deg)] for boxes matched to GT."""
    c, s, y = ([e[i] for e in errs] for i in range(3))
    return (f'- box error vs matched GT, {name} (n={len(errs)}, median): center {_med(c):.3f} m, '
            f'size {_med(s):.3f} m (mean |dw|,|dl|,|dh|), yaw {_med(y):.1f} deg')


def track_report(scene_name: str, mapping: str, tokens: List[str], boxes: Dict[str, list],
                 track_ids: Dict[str, List[int]], matched_gt: Dict[str, list], focus: List[int] = ()) -> str:
    members = defaultdict(list)  # tid -> [(keyframe, class, instance)]
    errs, focus_errs = [], defaultdict(list)
    inst_hits, inst_cat = defaultdict(list), {}  # instance -> [(keyframe, tid)], instance -> GT category
    for k, token in enumerate(tokens):
        for box, tid, gt in zip(boxes[token], track_ids[token], matched_gt[token]):
            members[tid].append((k, box.detection_name, None if gt is None else gt.instance_token))
            if gt is not None:
                inst_hits[gt.instance_token].append((k, tid))
                inst_cat[gt.instance_token] = gt.category_name
                err = (float(np.linalg.norm(np.subtract(box.translation[:2], gt.translation[:2]))),
                       float(np.mean(np.abs(np.subtract(box.size, gt.size)))),
                       float(np.degrees(yaw_error(gt, box))))
                errs.append(err)
                if tid in focus:
                    focus_errs[tid].append(err)

    lengths = [len(m) for m in members.values()]
    purities, switches = [], 0
    tracks_of_inst = defaultdict(set)
    rows = []
    for tid, mem in sorted(members.items(), key=lambda x: -len(x[1])):
        matched = [inst for _, _, inst in mem if inst is not None]
        for inst in matched:
            tracks_of_inst[inst].add(tid)
        switches += sum(a != b for a, b in zip(matched, matched[1:]))
        purity = Counter(matched).most_common(1)[0][1] / len(matched) if matched else float('nan')
        if len(matched) >= 2:
            purities.append(purity)
        if len(mem) >= 2:
            cls = Counter(c for _, c, _ in mem).most_common(1)[0][0]
            rows.append(f'| T{tid} | {cls} | {mem[0][0]}-{mem[-1][0]} | {len(mem)} | {len(matched)} | {purity:.2f} |')

    breaks = track_break_rows(inst_hits, inst_cat)
    frag = [len(t) for t in tracks_of_inst.values()]
    lines = [f'# Tracklets: {scene_name} ({mapping})', '',
             f'- keyframes: {len(tokens)}, boxes: {sum(lengths)}, tracks: {len(lengths)} '
             f'(length 1: {sum(n == 1 for n in lengths)})',
             f'- track length: median {statistics.median(lengths) if lengths else 0}, max {max(lengths, default=0)}',
             f'- purity (tracks with >= 2 matched boxes, n={len(purities)}): '
             f'mean {statistics.mean(purities) if purities else float("nan"):.3f}',
             f'- ID switches: {switches}',
             f'- fragmentation (GT instances, n={len(frag)}): mean {statistics.mean(frag) if frag else float("nan"):.2f} '
             f'tracks per instance, split into >1 track: {sum(n > 1 for n in frag)}',
             _error_line('all boxes', errs)]
    lines += [_error_line(f'T{tid}', focus_errs[tid]) for tid in focus]
    lines += ['', '| track | class | keyframes | length | GT-matched | purity |', '|---|---|---|---|---|---|']
    lines += rows
    lines += ['', '## Track breaks per GT object', '',
              'GT objects whose matched pseudo boxes are spread over more than one track, most tracks first.',
              'segments: track[first-last keyframe]. break: last keyframe of one segment -> first keyframe of the next; '
              'missing = keyframes in between with no pseudo box matched to this object (missed or > 2 m off).', '',
              '| GT object | category | keyframes | tracks | segments | breaks (missing keyframes) |',
              '|---|---|---|---|---|---|']
    return '\n'.join(lines + breaks) + '\n'


def track_break_rows(inst_hits: Dict[str, list], inst_cat: Dict[str, str]) -> List[str]:
    rows = []
    for inst, hits in inst_hits.items():
        hits = sorted(hits)
        segments = []  # [tid, first k, last k]
        for k, tid in hits:
            if segments and segments[-1][0] == tid and k == segments[-1][2] + 1:
                segments[-1][2] = k
            else:
                segments.append([tid, k, k])
        n_tracks = len({tid for _, tid in hits})
        if n_tracks < 2:
            continue
        seg = ' → '.join(f'T{t}[{a}-{b}]' for t, a, b in segments)
        brk = ', '.join(f'{p[2]}→{q[1]} ({q[1] - p[2] - 1})' for p, q in zip(segments, segments[1:]))
        rows.append((n_tracks, f'| {inst[:8]} | {inst_cat[inst]} | {hits[0][0]}-{hits[-1][0]} | {n_tracks} | {seg} | {brk} |'))
    return [r for _, r in sorted(rows, key=lambda x: -x[0])]


def render_keyframe(nusc, token: str, preds: list, tids: List[int], gts: list, title: str,
                    cams: List[List[str]] = CAMS, after: list = ()) -> np.ndarray:
    """after: [(box, track id)] of a second tag, drawn in red on top (only boxes that differ from preds)."""
    items = [(g, GREY, '') for g in gts] + [(p, track_color(t), f'T{t}') for p, t in zip(preds, tids)]
    items += [(a, RED, f'T{t} after') for a, t in after]
    sample = nusc.get('sample', token)
    grid = np.vstack([np.hstack([draw_camera(nusc, sample['data'][cam], items) for cam in row]) for row in cams])

    lidar_token = sample['data']['LIDAR_TOP']
    bev = draw_bev(nusc, lidar_token, items)
    pose = nusc.get('ego_pose', nusc.get('sample_data', lidar_token)['ego_pose_token'])
    scale = BEV_PX / (2 * BEV_RANGE)
    # draw_bev draws no labels, so add the track ids (same pixel mapping); "after" labels sit below the box
    labels = [(p, f'T{t}', track_color(t), -6) for p, t in zip(preds, tids)] + [(a, f'T{t}', RED, 16) for a, t in after]
    for p, text, color, dv in labels:
        x, y = to_frame(p, pose).center[:2]
        u, v = int(BEV_PX / 2 - y * scale), int(BEV_PX / 2 - x * scale)
        if 0 <= u < BEV_PX and 0 <= v < BEV_PX:
            cv2.putText(bev, text, (u + 6, v + dv), FONT, 0.5, color, 1, cv2.LINE_AA)

    body = np.hstack([grid, bev])
    header = np.full((HEADER_H, body.shape[1], 3), 255, np.uint8)
    cv2.putText(header, title, (15, 40), FONT, 1.0, (0, 0, 0), 2, cv2.LINE_AA)
    legend = [(GREY, 'GT'), (None, 'pseudo (colour per track)')] + ([(RED, 'after (changed boxes)')] if after else [])
    x = body.shape[1] - 330 * len(legend)
    for color, text in legend:
        if color is None:  # three sample track colours
            for n in range(3):
                cv2.rectangle(header, (x + 10 * n, 18), (x + 10 * n + 9, 44), track_color(n), -1)
        else:
            cv2.rectangle(header, (x, 18), (x + 30, 44), color, -1)
        cv2.putText(header, text, (x + 40, 40), FONT, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
        x += 330
    return np.vstack([header, body])


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import yaml
    from src.data.nuscenes import _NuscenesSingleton

    parser = argparse.ArgumentParser(description='Draw pseudo boxes by track id and report tracklet quality')
    parser.add_argument('--config', type=Path, default=Path('configs/vlm/p_final.yaml'))
    parser.add_argument('--tag', type=str, default='base')
    parser.add_argument('--mapping', type=str, default='8class')
    parser.add_argument('--scenes', type=str, nargs='+', default=['scene-0061'])
    parser.add_argument('--no_video', action='store_true')
    parser.add_argument('--no_images', action='store_true', help='only write the track report')
    parser.add_argument('--focus_tracks', type=int, nargs='*', default=[],
                        help='track ids reported separately (e.g. the ones in refs.json); ids are the same across tags')
    parser.add_argument('--cams', type=str, nargs='+', default=None,
                        help='draw only these cameras in one row next to the BEV, e.g. --cams CAM_FRONT '
                             '(saved under images/<mapping>_<cams>/); default: all six')
    parser.add_argument('--compare_tag', type=str, default=None,
                        help='overlay the boxes of this tag that differ from --tag in red (e.g. --tag base '
                             '--compare_tag ref1); saved under images/<layout>_vs_<compare_tag>/ of --tag')
    args = parser.parse_args()

    cams, layout = CAMS, args.mapping
    if args.cams:
        import render_boxes_on_images as base_render
        cams, layout = [args.cams], f"{args.mapping}_{'_'.join(c.replace('CAM_', '').lower() for c in args.cams)}"
        # one camera row as tall as the BEV panel (full 1600x900 resolution); draw_camera reads these at call time
        base_render.TILE_H = BEV_PX
        base_render.TILE_W = BEV_PX * 16 // 9

    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    exp, data = args.config.stem, config['data']
    nusc = _NuscenesSingleton.get_nuscenes_instance(data['dataset_version'], data['root_path'])
    rigid_dir = Path('outs') / config['type'] / exp / '#rigid' / args.tag

    for scene_name in args.scenes:
        with open(rigid_dir / f'labels_{scene_name}_{args.mapping}.json', 'r') as f:
            results = json.load(f)['results']
        with open(rigid_dir / f'tracks_{scene_name}.json', 'r') as f:
            tracks = json.load(f)
        tokens = tracks['frames']
        boxes = {t: [SimpleNamespace(**b) for b in results[t]] for t in tokens}
        track_ids = tracks['track_ids']
        assert all(len(boxes[t]) == len(track_ids[t]) for t in tokens), 'labels and tracks are not aligned'

        gts, matched_gt = {}, {}
        for token in tokens:
            anns = [nusc.get('sample_annotation', a) for a in nusc.get('sample', token)['anns']]
            gts[token] = [SimpleNamespace(**a) for a in anns if a['category_name'].startswith(GT_CATEGORIES)]
            matched_gt[token] = [None if j is None else gts[token][j] for j in match_to_gt(boxes[token], gts[token])]

        after = {t: [] for t in tokens}
        if args.compare_tag:
            cmp_dir = rigid_dir.parent / args.compare_tag
            with open(cmp_dir / f'labels_{scene_name}_{args.mapping}.json', 'r') as f:
                results_cmp = json.load(f)['results']
            with open(cmp_dir / f'tracks_{scene_name}.json', 'r') as f:
                assert json.load(f)['track_ids'] == track_ids, 'tags have different tracks, cannot compare box by box'
            for t in tokens:
                for b, b_cmp, tid in zip(results[t], results_cmp[t], track_ids[t]):
                    if any(not np.allclose(b[key], b_cmp[key]) for key in ('translation', 'size', 'rotation')):
                        after[t].append((SimpleNamespace(**b_cmp), tid))
            layout = f'{layout}_vs_{args.compare_tag}'
            print(f'{scene_name}: {sum(map(len, after.values()))} boxes differ in {args.compare_tag}', flush=True)

        report = track_report(scene_name, args.mapping, tokens, boxes, track_ids, matched_gt, args.focus_tracks)
        (rigid_dir / f'track_report_{scene_name}_{args.mapping}.md').write_text(report, encoding='utf-8')
        print(report, flush=True)
        if args.no_images:
            continue

        scene_dir = rigid_dir / 'images' / layout / scene_name
        scene_dir.mkdir(parents=True, exist_ok=True)
        writer = None
        for k, token in enumerate(tokens):
            title = f'{exp} #rigid/{args.tag} {args.mapping} | {scene_name} | keyframe {k} (refs index) / {len(tokens) - 1}'
            if args.compare_tag:
                title += f' | red = {args.compare_tag}'
            canvas = render_keyframe(nusc, token, boxes[token], track_ids[token], gts[token], title, cams, after[token])
            cv2.imwrite(str(scene_dir / f'{k:03d}.jpg'), canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not args.no_video:
                if writer is None:
                    writer = cv2.VideoWriter(str(scene_dir.parent / f'{scene_name}.mp4'), cv2.VideoWriter_fourcc(*'mp4v'),
                                             2, (canvas.shape[1], canvas.shape[0]))
                writer.write(canvas)
        if writer is not None:
            writer.release()
        print(f'{scene_name}: {len(tokens)} keyframes -> {scene_dir}', flush=True)


if __name__ == '__main__':
    main()
