"""Manage the local backend's existing authenticated maintenance endpoint. Never print its token."""
import argparse
import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.request


def read_values(path):
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


def prepare(path):
    if read_values(path).get('OPERATIONS_TOKEN'):
        return
    lines = [line for line in path.read_text(encoding='utf-8-sig').splitlines() if not line.startswith('OPERATIONS_TOKEN=')]
    lines.append('OPERATIONS_TOKEN=' + secrets.token_hex(32))
    temporary = path.with_suffix('.operations.tmp')
    temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def operation(path, action):
    values = read_values(path)
    token = values.get('OPERATIONS_TOKEN')
    if not token:
        raise RuntimeError('Local operation token is missing; run hybrid.ps1 -Action start.')
    port = int(values.get('APP_PORT', '8080'))
    if not 1 <= port <= 65535:
        raise ValueError('Invalid local application port')
    base = f'http://127.0.0.1:{port}'
    request = urllib.request.Request(base + '/internal/operations' + ('/resume' if action == 'resume' else ''),
        data=b'' if action == 'resume' else None, headers={'X-Operations-Token': token})
    with urllib.request.urlopen(request, timeout=5) as response:
        state = json.load(response)
    if action == 'resume':
        if state.get('maintenance') is not False:
            raise RuntimeError('Backend is still in maintenance mode')
        # An invalid upload must reach validation (400), without creating an upload or dataset.
        probe = urllib.request.Request(base + '/api/dataset-uploads/sessions', data=b'{}', headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(probe, timeout=5):
                raise RuntimeError('Unexpected success for an invalid upload probe')
        except urllib.error.HTTPError as error:
            error.close()
            if error.code != 400:
                raise RuntimeError(f'Upload write path is unavailable: HTTP {error.code}') from error
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'status', 'resume'])
    parser.add_argument('--env-file', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.env_file)
        print('Local operation credential prepared.')
        return
    for attempt in range(20 if args.action == 'resume' else 1):
        try:
            state = operation(args.env_file, args.action)
            print(json.dumps(state))
            return
        except (urllib.error.URLError, TimeoutError):
            if attempt == (19 if args.action == 'resume' else 0):
                raise RuntimeError('Local operations endpoint unavailable; check backend startup and protected runtime settings.') from None
            time.sleep(1)


if __name__ == '__main__':
    main()
