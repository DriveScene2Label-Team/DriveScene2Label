"""Connect an existing PRIVATE Microsoft tunnel to Vercel. Never grant anonymous access.

The connect-scoped token stays in the protected local runtime and Vercel secret env.
Start refreshes tokens with less than six hours left, then rebuilds production source.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess

import cloud

RUNTIME = Path(os.environ.get('LOCALAPPDATA', '')) / 'DriveScene2Label/hybrid'
CONFIG = RUNTIME / 'tunnel.json'
CACHE = RUNTIME / 'tunnel-token.json'


def config():
    value = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    if value.get('provider') != 'microsoft' or not re.fullmatch(r'[a-zA-Z0-9-]+\.[a-z0-9]+', value.get('tunnelId', '')):
        raise ValueError('Configure an existing private Microsoft tunnel in the protected tunnel.json.')
    if not re.fullmatch(r'https://[a-z0-9-]+-4180\.[a-z0-9]+\.devtunnels\.ms', value.get('origin', '')):
        raise ValueError('Expected the HTTPS origin of the authenticated gateway on port 4180.')
    return value


def valid_token(cached, tunnel_id):
    try:
        raw = cached['expiration']
        expiry = (datetime.strptime(raw, '%Y-%m-%d %H:%M:%S UTC').replace(tzinfo=timezone.utc)
                  if raw.endswith(' UTC') else datetime.fromisoformat(raw.replace('Z', '+00:00')))
        return cached.get('tunnelId') == tunnel_id and bool(cached.get('token')) and expiry > datetime.now(timezone.utc) + timedelta(hours=6)
    except (KeyError, TypeError, ValueError):
        return False


def prepare():
    settings = config()
    project = cloud.vercel('project', 'inspect', cloud.PROJECT, '--json')
    cloud.validate_project(project)
    cached = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}
    if not valid_token(cached, settings['tunnelId']):
        issued = cloud.command_json([str(cloud.REPO / '.local/tools/devtunnel.exe'), 'token', settings['tunnelId'], '--scopes', 'connect', '--json'])
        cached = {'tunnelId': settings['tunnelId'], 'token': issued['token'], 'expiration': issued['expiration'], 'published': False}
        if not valid_token(cached, settings['tunnelId']):
            raise RuntimeError('The CLI did not issue a usable connect token. Renew Dev Tunnels login.')
        cloud.save_connection(CACHE, cached)
    headers = {'X-Tunnel-Authorization': 'tunnel ' + cached['token']}
    cloud.require_auth_gate(settings['origin'], headers)
    changed = not cached.get('published', False)
    if changed:
        # stdin keeps the token out of shell history and process command lines. Never echo CLI output.
        result = subprocess.run([*cloud.vercel_command(), 'env', 'add', 'BACKEND_TUNNEL_TOKEN',
                                 '--environment', 'production', '--project', cloud.PROJECT, '--type', 'secret',
                                 '--force', '--yes', '--scope', cloud.TEAM, '--non-interactive'],
                                input=cached['token'], capture_output=True, text=True, encoding='utf-8', timeout=90)
        if result.returncode:
            raise RuntimeError('Publishing the connect token failed; check Vercel CLI authentication. No secret is logged.')
        cached['published'] = True
        cached['deploymentPending'] = True
        cloud.save_connection(CACHE, cached)
    return settings, headers, changed or cached.get('deploymentPending', False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'sync'])
    args = parser.parse_args()
    settings, headers, changed = prepare()
    if args.action == 'prepare':
        cloud.vercel('env', 'update', 'BACKEND_URL', '--environment', 'production', '--project', cloud.PROJECT,
                     '--value', settings['origin'], '--yes', parse_json=False)
        print('Private gateway verified; production environment prepared. Deploy the reviewed frontend source next.')
    else:
        cloud.sync_vercel(settings['origin'], cloud.REPO / '.local/hybrid/vercel-connection.json', headers, changed)
        cached = json.loads(CACHE.read_text(encoding='utf-8'))
        cached['deploymentPending'] = False
        cloud.save_connection(CACHE, cached)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        # HTTP/library exceptions may carry request information: only emit our controlled messages.
        raise SystemExit(str(error) if type(error) in (RuntimeError, ValueError) else f'Private tunnel setup failed: {type(error).__name__}') from None
