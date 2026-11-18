"""Separate first model access from later cached accesses in existing runner logs.

Read-only input: stage-events.jsonl or measurement events.jsonl. Does not load a
model or contact a running service. A getter includes construction/cache lookup,
disk/network access and device transfer; it is NOT a pure CUDA transfer timer.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import median

MODEL_STAGES = ('detector_model_get', 'sam_model_get', 'dinov2_model_get')
CONTEXT = ('runtime_import', 'dataset_load', 'ground_removal', 'image_detection_segmentation', 'dinov2_features')


def summarize(rows, run_id=None):
    # Container and results-volume copies of an event must count only once.
    keys = ('at', 'run_id', 'job_id', 'scene', 'stage', 'event', 'call', 'wall_seconds', 'error_type')
    unique = {}
    for raw in rows:
        if not raw.get('run_id') or not raw.get('stage'):
            continue
        if run_id is not None and raw['run_id'] != run_id:
            continue
        row = {key: raw[key] for key in keys if key in raw}
        unique[json.dumps(row, sort_keys=True)] = row
    runs = {}
    for row in unique.values():
        runs.setdefault(row['run_id'], []).append(row)
    result = []
    for identity, events in sorted(runs.items()):
        events.sort(key=lambda row: row.get('at', ''))
        def completed(stage):
            return [r for r in events if r['stage'] == stage and r['event'] == 'completed'
                    and isinstance(r.get('wall_seconds'), (float, int))
                    and math.isfinite(r['wall_seconds']) and r['wall_seconds'] >= 0]
        models = {}
        for stage in MODEL_STAGES:
            observed = completed(stage)
            first = next((r for r in observed if r.get('call') == 1), None)
            later = [r['wall_seconds'] for r in observed if isinstance(r.get('call'), int) and r['call'] > 1]
            models[stage] = {
                'first_access_seconds': first['wall_seconds'] if first else None,
                'later_access_count': len(later),
                'later_access_median_seconds': median(later) if later else None,
                'completed_access_count': len(observed),
                'failure_count': sum(r['stage'] == stage and r['event'] == 'failed' for r in events),
            }
        terminated = {(r['stage'], r.get('call')) for r in events if r['event'] in ('completed', 'failed')}
        result.append({
            'run_id': identity, 'job_id': events[0].get('job_id'), 'scene': events[0].get('scene'),
            'last_observed_at': events[-1].get('at'),
            'runner_result_written': bool(completed('result_json_write')),
            'open_spans': [{'stage': r['stage'], 'call': r.get('call'), 'started_at': r.get('at')}
                           for r in events if r['event'] == 'started' and (r['stage'], r.get('call')) not in terminated],
            'models': models,
            'context_completed_seconds': {s: [r['wall_seconds'] for r in completed(s)] for s in CONTEXT},
        })
    return {'generated_at': datetime.now(timezone.utc).isoformat(), 'units': 'seconds', 'runs': result,
            'limitations': [
                'First access is a cold-process candidate, not proof of cold disk/network cache.',
                'Getter timings include construction, cache lookup, I/O and device transfer; CUDA kernels are not separately synchronized.',
                'Missing first access is null, never zero. Missing DINOv2 timing in older runners is unmeasured.',
                'Inclusive stage spans overlap: do not add getters to enclosing detection/feature stages.',
                'Open spans may be running, interrupted or missing their tail; result writing does not prove backend persistence.',
            ]}


def markdown(report):
    lines = ['# 모델 로딩 관측', '', '단위: 초. 첫 접근은 로딩 포함 구간이며 디스크 cold 여부와 순수 GPU 전송 시간은 미측정.', '']
    for run in report['runs']:
        lines += [f"## Job {run['job_id']} / {run['run_id']}", '',
                  '| 모델 getter | 첫 접근 | 이후 접근 수 | 이후 중앙값 |', '|---|---:|---:|---:|']
        for stage, value in run['models'].items():
            first = value['first_access_seconds']; later = value['later_access_median_seconds']
            lines.append(f"| {stage} | {first if first is not None else '미측정'} | {value['later_access_count']} | {later if later is not None else '미측정'} |")
        lines += ['', '미종료 관측 구간: ' + ', '.join(s['stage'] for s in run['open_spans']), '']
    lines += report['limitations']
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--events', type=Path, required=True)
    p.add_argument('--run-id')
    p.add_argument('--output', type=Path, required=True, help='New directory; never overwrite the active watcher report')
    a = p.parse_args()
    raw = a.events.read_text(encoding='utf-8-sig')
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    report = summarize(rows, a.run_id)
    if not report['runs']:
        raise ValueError('No matching runner evidence; no measurements fabricated')
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / 'model-load-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (a.output / 'report.md').write_text(markdown(report), encoding='utf-8')
    print(json.dumps({'directory': str(a.output), 'runs': len(report['runs'])}))


if __name__ == '__main__':
    main()
