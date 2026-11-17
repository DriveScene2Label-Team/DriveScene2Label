"""Upload the existing nuScenes archive through loopback and wait for CLIP indexing.

Uses the normal application APIs. Never deletes an existing dataset or triggers labeling.
Client observations are stored separately from server events, not labeled as browser data.
"""
import argparse
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import time
from evidence_io import save_json


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    save_json(path,value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not (directory / 'manifest.json').is_file():
        raise ValueError('Create a measurement directory first.')
    client_file = directory / 'client-report.json'
    if client_file.exists():
        raise ValueError('A client run already exists here; do not duplicate this upload.')
    client_events = (directory/'client-events.jsonl').open('x', encoding='utf-8')
    def emit(row):
        line = json.dumps({'at':now(), **row}, ensure_ascii=False)
        client_events.write(line+'\n')
        client_events.flush()
        print(line, flush=True)
    connection = http.client.HTTPConnection('127.0.0.1', 8080, timeout=120)

    def request(method, path, body=None, binary=False):
        headers = {'Content-Type': 'application/octet-stream' if binary else 'application/json'}
        payload = body if binary or body is None else json.dumps(body).encode('utf-8')
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        if not 200 <= response.status < 300:
            # Avoid storing arbitrary response bodies or headers in shareable evidence.
            raise RuntimeError(f'{method} {path.split("?")[0]} returned HTTP {response.status}')
        return json.loads(raw) if raw else None

    report = {'started_at': now(), 'origin': 'http://127.0.0.1:8080',
              'client': 'Python HTTP client, normal resumable upload API; not a browser',
              'archive_name': args.archive.name, 'archive_bytes': args.archive.stat().st_size,
              'concurrent_agent_work': 'Only log/status collection; no VESPA, builds, or AWS deployment',
              'status': 'starting'}
    save(client_file, report)
    started = time.monotonic()
    try:
        session = request('POST', '/api/dataset-uploads/sessions',
                          {'filename': args.archive.name, 'sizeBytes': report['archive_bytes']})
        if not session['workerEnabled']:
            raise RuntimeError('Upload worker is disabled.')
        report.update(upload_id=session['id'], status='transferring', upload_created_at=now())
        save(client_file, report)
        emit({'event': 'upload_created', 'upload': session['id']})
        route = '/api/dataset-uploads/sessions/' + session['id']
        last_progress = -1
        with args.archive.open('rb') as stream:
            offset = 0
            while data := stream.read(session['chunkBytes']):
                for attempt in range(3):
                    try:
                        session = request('POST', route + '/parts?offset=' + str(offset), data, binary=True)
                        break
                    except (OSError, http.client.HTTPException):
                        connection.close()
                        if attempt == 2:
                            raise
                offset += len(data)
                if session['receivedBytes'] != offset:
                    raise RuntimeError('Server acknowledged an unexpected upload offset.')
                progress = offset * 10 // report['archive_bytes']
                if progress != last_progress:
                    report.update(sent_bytes=offset, transfer_elapsed_seconds=round(time.monotonic()-started, 3))
                    save(client_file, report)
                    emit({'event': 'transfer', 'percent': round(offset/report['archive_bytes']*100, 1),
                          'elapsed_seconds': report['transfer_elapsed_seconds']})
                    last_progress = progress
        report.update(transfer_completed_at=now(), transfer_seconds=round(time.monotonic()-started, 3))
        session = request('POST', route + '/complete')
        report.update(status='processing', submitted_at=now())
        save(client_file, report)
        emit({'event': 'submitted', 'transfer_seconds': report['transfer_seconds']})
        deadline = time.monotonic() + 7200
        previous = None
        while session['status'] != 'COMPLETED':
            if session['status'] == 'FAILED':
                raise RuntimeError('Server reported upload processing failure; inspect local server logs.')
            if time.monotonic() >= deadline:
                raise TimeoutError('Upload processing did not finish within two hours.')
            if session['status'] != previous:
                emit({'event': 'upload_status', 'status': session['status']})
                previous = session['status']
            time.sleep(10)
            session = request('GET', route)
        dataset = session['datasetId']
        report.update(status='indexing', dataset_id=dataset, scene_count=session['sceneCount'],
                      import_completed_at=now(), elapsed_to_import_seconds=round(time.monotonic()-started, 3))
        save(client_file, report)
        emit({'event': 'import_completed', 'dataset': dataset, 'scenes': session['sceneCount']})
        index_route = f'/api/datasets/{dataset}/search-index'
        previous = None
        while True:
            status = request('GET', index_route)
            state = (status['status'], status['indexedImages'], status['totalImages'])
            if state != previous:
                report.update(index_status=status, last_observed_at=now())
                save(client_file, report)
                emit({'event': 'index', **status})
                previous = state
            if status['status'] == 'COMPLETED':
                if status['totalImages'] <= 0 or status['indexedImages'] != status['totalImages']:
                    raise RuntimeError('Inconsistent completed index counts.')
                break
            if not status['workerEnabled'] or status['status'] in ('FAILED', 'EMPTY'):
                raise RuntimeError('CLIP index worker is unavailable or failed.')
            if time.monotonic() >= deadline:
                raise TimeoutError('CLIP indexing did not finish within the observation window.')
            time.sleep(10)
        report.update(status='completed', completed_at=now(), total_seconds=round(time.monotonic()-started, 3))
        save(client_file, report)
        emit({'event': 'completed', 'dataset': dataset, 'images': status['indexedImages'],
              'total_seconds': report['total_seconds']})
    except Exception as error:
        report.update(status='failed', failed_at=now(), error_type=type(error).__name__, error=str(error))
        save(client_file, report)
        emit({'event':'failed', 'error_type':type(error).__name__})
        raise
    finally:
        connection.close()
        client_events.close()


if __name__ == '__main__':
    main()
