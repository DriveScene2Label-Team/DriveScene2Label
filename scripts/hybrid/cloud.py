"""Start the existing hybrid database and reconnect the existing Vercel deployment.

Credentials stay in the official AWS/Vercel CLI stores. No EC2/ECS/EKS resources
are created, started or inspected. Vercel redeploys reviewed production source,
never the possibly modified working tree.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[2]
ACCOUNT = '189750306426'
PROFILE = 'ds2l-seoul'
REGION = 'ap-northeast-2'
DATABASE = 'ds2l-hybrid-database'
TEAM = 'team_Mu6arR8bulAiFe0hRw8ocLIf'
PROJECT = 'prj_4oVMQaMlPUX7KYegmRBW18XFd3rM'
SITE = 'https://drivescene2label.vercel.app'


def command_json(command, timeout=90, parse_json=True):
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    if result.returncode:
        # CLI responses can contain environment values; do not echo them into logs.
        raise RuntimeError(f'{Path(command[0]).name} command failed (exit {result.returncode}). Check CLI login and target access.')
    return json.loads(result.stdout) if parse_json else None


def aws(*args):
    return command_json(['aws', *args, '--profile', PROFILE, '--region', REGION, '--output', 'json', '--no-cli-pager'])


def database_state():
    identity = aws('sts', 'get-caller-identity')
    if identity.get('Account') != ACCOUNT:
        raise RuntimeError('AWS account mismatch; refusing to operate on the database.')
    result = aws('rds', 'describe-db-instances', '--db-instance-identifier', DATABASE)
    rows = result.get('DBInstances', [])
    if len(rows) != 1 or rows[0].get('DBInstanceIdentifier') != DATABASE or rows[0].get('Engine') != 'postgres':
        raise RuntimeError('Expected existing PostgreSQL instance was not found. No replacement is created.')
    return rows[0]['DBInstanceStatus']


def ensure_database(timeout=1800):
    deadline = time.monotonic() + timeout
    started = False
    previous = None
    while True:
        state = database_state()
        if state != previous:
            print(f'RDS {DATABASE}: {state}', flush=True)
            previous = state
        if state == 'available':
            return
        if state == 'stopped' and not started:
            aws('rds', 'start-db-instance', '--db-instance-identifier', DATABASE)
            started = True
        elif state not in ('starting', 'stopping', 'stopped', 'backing-up', 'modifying', 'maintenance'):
            raise RuntimeError(f'RDS is in {state}; manual diagnosis is required.')
        if time.monotonic() >= deadline:
            raise TimeoutError('RDS is not available yet. Retry start later; the existing instance is preserved.')
        time.sleep(20)


def vercel_command():
    local_node = REPO / '.local/tools/node-v24.22.2-win-x64/node.exe'
    node = str(local_node) if local_node.exists() else shutil.which('node')
    cli = REPO / '.local/tools/vercel-cli/node_modules/vercel/dist/vc.js'
    if not node or not cli.exists():
        raise RuntimeError('Install the pinned Vercel CLI as described in docs/hybrid-setup.md.')
    return [node, str(cli)]


def vercel(*args, parse_json=True):
    return command_json([*vercel_command(), *args, '--scope', TEAM, '--non-interactive'], parse_json=parse_json)


def tunnel_origin(path, timeout=60):
    deadline = time.monotonic() + timeout
    while True:
        if path.exists():
            matches = re.findall(r'https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com\b', path.read_text(encoding='utf-8', errors='replace'))
            if matches:
                return matches[-1]
        if time.monotonic() >= deadline:
            raise TimeoutError('The current tunnel did not publish its HTTPS address.')
        time.sleep(1)


def require_auth_gate(origin):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(origin + '/api/datasets', timeout=20):
            raise RuntimeError('Public API unexpectedly allowed anonymous access.')
    except urllib.error.HTTPError as error:
        error.close()
        if error.code != 401:
            raise RuntimeError(f'Authentication gateway is not ready: HTTP {error.code}') from None


def validate_project(project):
    if project.get('id') != PROJECT or project.get('accountId') != TEAM:
        raise RuntimeError('Vercel project/team mismatch; refusing to change deployment.')


def validate_deployment(deployment):
    if deployment.get('projectId') != PROJECT or deployment.get('target') != 'production':
        raise RuntimeError('Expected production deployment was not found.')
    if (deployment.get('readyState') or deployment.get('state')) != 'READY':
        raise RuntimeError('Production deployment is not READY; preserve it and diagnose first.')


def save_connection(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value), encoding='utf-8')
    os.replace(temporary, path)


def sync_vercel(origin, state_path):
    require_auth_gate(origin)
    project = vercel('project', 'inspect', PROJECT, '--json')
    validate_project(project)
    current = vercel('inspect', SITE, '--json')
    validate_deployment(current)
    environment = vercel('env', 'ls', '--environment', 'production', '--project', PROJECT, '--json')
    rows = environment.get('envs', [])
    selected = [row for row in rows if row.get('key') == 'BACKEND_URL' and 'production' in row.get('target', [])]
    if len(selected) != 1:
        raise RuntimeError('Expected one existing production BACKEND_URL. No environment is created automatically.')
    saved = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    if selected[0].get('value') == origin and saved == {'origin': origin, 'deploymentId': current['id']}:
        require_auth_gate(SITE)
        print(f'Vercel already connected: {SITE}', flush=True)
        return
    if saved.get('pending') and saved.get('origin') != origin:
        raise RuntimeError('A previous tunnel deployment is pending. Resolve it before changing the origin again.')
    if selected[0].get('value') != origin:
        vercel('env', 'update', 'BACKEND_URL', '--environment', 'production', '--project', PROJECT,
               '--value', origin, '--yes', parse_json=False)
    if saved.get('pending'):
        if current['id'] not in (saved['sourceDeploymentId'], saved['deploymentId']):
            raise RuntimeError('Production changed during reconnect. Inspect the new deployment before retrying.')
        deployment_id = saved['deploymentId']
        print('Resuming the pending frontend deployment check.', flush=True)
    else:
        print('Rebuilding the existing production frontend with the current tunnel address.', flush=True)
        created = vercel('redeploy', current['id'], '--environment', 'production', '--json', '--no-wait')
        deployment_id = created['id']
        save_connection(state_path, {'origin': origin, 'deploymentId': deployment_id,
                                    'sourceDeploymentId': current['id'], 'pending': True})
    deadline = time.monotonic() + 900
    previous = None
    while True:
        deployment = vercel('inspect', deployment_id, '--json')
        state = deployment.get('readyState') or deployment.get('state')
        if state != previous:
            print(f'Vercel deployment: {state}', flush=True)
            previous = state
        if state == 'READY':
            validate_deployment(deployment)
            break
        if state in ('ERROR', 'CANCELED') or time.monotonic() >= deadline:
            raise RuntimeError('Frontend redeploy did not become READY. Local services remain running.')
        time.sleep(10)
    active = vercel('inspect', SITE, '--json')
    if active.get('id') != deployment_id:
        raise RuntimeError('Ready deployment is not assigned to the public site. Check Vercel promotion settings.')
    require_auth_gate(SITE)
    save_connection(state_path, {'origin': origin, 'deploymentId': deployment_id})
    print(f'Vercel connected: {SITE}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['rds-start', 'rds-status', 'vercel-login', 'vercel-sync'])
    args = parser.parse_args()
    if args.action == 'rds-start':
        ensure_database()
    elif args.action == 'rds-status':
        print(f'RDS {DATABASE}: {database_state()}')
    elif args.action == 'vercel-login':
        raise SystemExit(subprocess.call([*vercel_command(), 'login']))
    else:
        local = REPO / '.local/hybrid'
        sync_vercel(tunnel_origin(local / 'tunnel.stderr.log'), local / 'vercel-connection.json')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, TimeoutError, subprocess.TimeoutExpired, urllib.error.URLError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from None
