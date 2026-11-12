"""Capture allowlisted stage logs locally; never upload logs or start a GPU job.

begin prints the evidence directory; watch collects every 30 seconds (up to 48 h).
collect can also be run after a job. stop creates a cooperative stop marker.
Reports contain observations, not estimates for missing stages. Inclusive spans overlap.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time
from uuid import UUID

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / '.local/hybrid/measurements'
CONTAINERS = {'backend': 'drivescene-hybrid-backend-1', 'ai': 'drivescene-hybrid-ai-server-1'}
TAGS = 'HTTP|UPLOAD_CLIENT|UPLOAD_TRANSFER|UPLOAD_STAGE|UPLOAD|DB_IMPORT|SEARCH|VESPA_STAGE|VESPA|AUTO_LABEL_STAGE|AUTO_LABEL|CLIP_INDEX|CLIP|RERUN_STAGE|RERUN|RECORDING|UPLOAD_CACHE|CACHE'
TAG = re.compile(r'\[(' + TAGS + r')\]')
PAIR = re.compile(r'([A-Za-z_]+)=([^\s,]+)')
FIELDS = set('request method route status stage event upload dataset job run scene recording image table rows batches bytes offset received source outcome transfer_ms processing_ms total_ms sent_bytes resumed_bytes receive_ms db_lock_ms file_ms db_update_ms transaction_ms status_ms jdbc_ms wall_ms stage_wall_ms total_wall_ms ai_ms storage_ms db_mapping_ms cache wall_seconds cpu_seconds ai_seconds storage_seconds total_seconds prepare_seconds executor_seconds frames images count boxes samples scenes topK aggregation remote format'.split())


def now():
    return datetime.now(timezone.utc)


def parse_line(line):
    if 'DS2L_STAGE ' in line:
        try:
            raw = json.loads(line.split('DS2L_STAGE ', 1)[1])
            keys = ('at', 'job_id', 'run_id', 'scene', 'stage', 'event', 'call', 'wall_seconds', 'cpu_seconds', 'error_type')
            return {'tag': 'DS2L_STAGE', **{key: raw[key] for key in keys if key in raw}}
        except (ValueError, TypeError):
            return None
    # Legacy import logs predate bracketed tags. Normalize their correlation names.
    if 'Dataset upload ' in line:
        line = line.replace('Dataset upload failed ', '[UPLOAD_STAGE] event=failed ').replace('Dataset upload ', '[UPLOAD_STAGE] ')
        line = re.sub(r'\bid=', 'upload=', line)
        line = re.sub(r'\bdatasetId=', 'dataset=', line)
    match = TAG.search(line)
    if not match:
        return None
    fields = {key: value for key, value in PAIR.findall(line[match.end():]) if key in FIELDS}
    # Only explicit structured fields: no request bodies, cookies, queries or free-form exceptions.
    if not fields:
        return None
    at = line.split(' ', 1)[0]
    return {'tag': match[1], 'at': at, **fields}


def event_key(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()


def summarize(rows):
    unique = {event_key(row): row for row in rows}
    groups = {}
    failures = []
    for row in unique.values():
        if (row.get('event') == 'failed' or row.get('outcome') == 'failed' or row.get('status') == 'FAILED'
                or (row.get('tag') == 'HTTP' and str(row.get('status', '')).startswith('5'))):
            failures.append(row)
        if row.get('event') == 'started':
            continue
        scope = row.get('stage', row.get('table', row.get('route', row.get('event', 'boundary'))))
        # Keep runs/uploads independent. No sum across different jobs is presented as one job time.
        context = row.get('run_id', row.get('run', row.get('upload', row.get('recording', row.get('job', row.get('dataset', 'all'))))))
        for field, value in row.items():
            if not (field.endswith('_ms') or field.endswith('_seconds')):
                continue
            try:
                duration = float(value) * (1000 if field.endswith('_seconds') else 1)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(duration) or duration < 0:
                continue
            label = f"{row['tag']} / {scope} / {context} / {row.get('event', row.get('outcome', 'observed'))} / {field}"
            groups.setdefault(label, []).append(duration)
    aggregates = []
    for key, values in sorted(groups.items()):
        values.sort()
        aggregates.append({'boundary': key, 'count': len(values), 'sum_ms': round(sum(values), 3),
                           'p50_ms': round(values[math.ceil(len(values)*.5)-1], 3),
                           'p95_ms': round(values[math.ceil(len(values)*.95)-1], 3), 'max_ms': round(values[-1], 3)})
    return {'events': len(unique), 'timings': aggregates, 'failures': failures,
            'limitation': 'Inclusive/nested spans overlap; do not sum rows. Missing stages are unmeasured. Browser metrics are self-reported. CPU time is not CUDA kernel time.'}


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed (exit {result.returncode}); inspect the local service')
    return result.stdout + '\n' + result.stderr


def directory(value):
    path = Path(value).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not (path / 'manifest.json').is_file():
        raise ValueError('Use a directory created by begin inside .local/hybrid/measurements')
    return path


def save(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def timed_rows(output, since):
    cutoff = datetime.fromisoformat(since.replace('Z', '+00:00'))
    result = []
    for line in output.splitlines():
        try:
            at = datetime.fromisoformat(line.split(' ', 1)[0].replace('Z', '+00:00'))
        except ValueError:
            continue
        if at >= cutoff:
            row = parse_line(line)
            if row:
                result.append(row)
    return result


def collect(path):
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    events_path = path / 'events.jsonl'
    rows = [json.loads(line) for line in events_path.read_text(encoding='utf-8').splitlines()] if events_path.exists() else []
    seen = {event_key(row) for row in rows}
    new = []
    errors = []
    cursors = manifest.setdefault('cursors', {})
    # Overlap covers events written while collecting. Identity de-duplicates subsequent captures.
    next_cursor = (now() - timedelta(seconds=2)).isoformat()
    for service, container in CONTAINERS.items():
        try:
            since = cursors.get(service, manifest['started_at'])
            output = command(['docker', 'logs', '--timestamps', '--since', since, container])
            captured = timed_rows(output, since)
            # Docker Desktop was observed to omit the newest segment after restart.
            # A tail probe detects that case; it cannot establish full coverage by itself.
            tail = timed_rows(command(['docker', 'logs', '--timestamps', '--tail', '50', container]), since)
            captured_keys = {event_key(row) for row in captured}
            # Events arriving after the main read are not evidence of a historical gap.
            boundary = datetime.fromisoformat(next_cursor)
            gap = any(event_key(row) not in captured_keys and datetime.fromisoformat(row['at'].replace('Z', '+00:00')) < boundary for row in tail)
            if gap:
                warning = {'service': service, 'error': 'LogCursorMismatch', 'since': since, 'note': 'Partial capture; recreate idle container before a new measurement.'}
                warnings = manifest.setdefault('capture_warnings', [])
                if warning not in warnings:
                    warnings.append(warning)
            else:
                cursors[service] = next_cursor
            for row in captured + tail:
                row['service'] = service
                if event_key(row) not in seen:
                    seen.add(event_key(row)); new.append(row)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as error:
            errors.append({'service': service, 'error': type(error).__name__})
    rows.extend(new)
    # Runner timings live on the results volume, independently of the API container log.
    run_ids = {row.get('run') or row.get('run_id') for row in rows}
    for candidate in sorted(str(value) for value in run_ids if value):
        try:
            run_id = str(UUID(candidate))
        except ValueError:
            continue
        try:
            output = command(['docker', 'exec', CONTAINERS['ai'], 'cat', f'/results/{run_id}/stage-events.jsonl'])
            for line in output.splitlines():
                row = parse_line('DS2L_STAGE ' + line)
                if row:
                    row['service'] = 'ai'
                if row and event_key(row) not in seen:
                    seen.add(event_key(row)); new.append(row); rows.append(row)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as error:
            errors.append({'run': run_id, 'error': type(error).__name__, 'note': 'stage file may not exist yet'})
    if new:
        with events_path.open('a', encoding='utf-8') as stream:
            for row in new:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    errors.extend(manifest.get('capture_warnings', []))
    report = {'collected_at': now().isoformat(), 'started_at': manifest['started_at'], 'capture_errors': errors, **summarize(rows)}
    save(path / 'report.json', report)
    lines = ['# 로컬 계측 결과', '', f"수집 시작: {manifest['started_at']} · 마지막 수집: {report['collected_at']}", '',
             '중첩된 구간을 합산하지 않습니다. 없는 구간은 미측정입니다. 브라우저 수치는 클라이언트 보고값이며 GPU 커널 시간은 별도 프로파일러가 필요합니다.', '',
             f"관측 이벤트 {report['events']}개 · 실패 이벤트 {len(report['failures'])}개 · 수집 오류 {len(errors)}개", '',
             '| 경계 / 문맥 / 상태 / 지표 | 횟수 | 합계 ms | p50 ms | p95 ms | 최대 ms |', '|---|---:|---:|---:|---:|---:|']
    for row in report['timings']:
        lines.append('| ' + ' | '.join(str(row[key]).replace('|', '/') for key in ('boundary', 'count', 'sum_ms', 'p50_ms', 'p95_ms', 'max_ms')) + ' |')
    (path / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    save(path / 'manifest.json', manifest)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['begin', 'collect', 'watch', 'stop'])
    parser.add_argument('--directory')
    args = parser.parse_args()
    if args.action == 'begin':
        path = ROOT / now().strftime('%Y%m%dT%H%M%SZ')
        path.mkdir(parents=True, exist_ok=False)
        revision = command(['git', '-C', str(REPO), 'rev-parse', 'HEAD']).strip()
        save(path / 'manifest.json', {'started_at': now().isoformat(), 'git_revision': revision,
                                     'dirty': bool(command(['git', '-C', str(REPO), 'status', '--porcelain']).strip()),
                                     'cache_condition': 'Not automatically inferred; record cold/warm and dataset when testing.'})
        save(ROOT / 'active.json', {'directory': str(path)})
        # ASCII relative output survives Windows PowerShell/native code-page boundaries.
        print(path.relative_to(REPO).as_posix())
        return
    selected = args.directory or json.loads((ROOT / 'active.json').read_text(encoding='utf-8'))['directory']
    path = directory(selected)
    if args.action == 'stop':
        (path / 'STOP').touch()
        return
    deadline = time.monotonic() + 48 * 3600
    while True:
        report = collect(path)
        print(json.dumps({'events': report['events'], 'capture_errors': len(report['capture_errors']), 'directory': str(path)}), flush=True)
        if args.action != 'watch' or (path / 'STOP').exists() or time.monotonic() >= deadline:
            return
        time.sleep(30)


if __name__ == '__main__':
    main()
