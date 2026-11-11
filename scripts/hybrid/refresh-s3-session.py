"""Refresh the local app's one-hour, S3-only session without printing credentials."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROLE = 'arn:aws:iam::189750306426:role/ds2l-hybrid-storage'

def refresh(directory):
    response = subprocess.run(['aws', 'sts', 'assume-role', '--role-arn', ROLE,
        '--role-session-name', 'ds2l-local-storage', '--duration-seconds', '3600',
        '--profile', 'ds2l-seoul', '--region', 'ap-northeast-2', '--output', 'json'],
        capture_output=True, text=True, encoding='utf-8')
    if response.returncode:
        raise RuntimeError('S3 session refresh failed: ' + response.stderr.strip())
    credentials = json.loads(response.stdout)['Credentials']
    payload = {'Version': 1, **{k: credentials[k] for k in ('AccessKeyId', 'SecretAccessKey', 'SessionToken', 'Expiration')}}
    temporary = directory / 'session.json.tmp'
    temporary.write_text(json.dumps(payload), encoding='utf-8')
    os.replace(temporary, directory / 'session.json')
    print('S3 session refreshed; expires ' + credentials['Expiration'], flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    while True:
        try:
            refresh(args.directory)
        except RuntimeError as error:
            print(str(error), flush=True)
            if not args.watch:
                raise SystemExit(1)
        if not args.watch:
            break
        time.sleep(2400)
