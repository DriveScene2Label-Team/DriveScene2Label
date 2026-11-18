"""Back up and reset this project's app data, retaining S3, accounts, models and sequences.

Default is read-only inventory. --apply requires stopped backend/AI containers,
maintenance mode, and a successful isolated restore with matching table contents.
The private dump is written beside compose.env, never into the repository.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from urllib.parse import urlparse
from operations import read_values

ROOT = Path(__file__).resolve().parents[2]
HOST = 'ds2l-hybrid-database.c1quca8ggb9y.ap-northeast-2.rds.amazonaws.com'
BUCKET = 'ds2l-189750306426-ap-northeast-2-data'
IMAGE = 'pgvector/pgvector:pg16-trixie'
KEEP = {'system_instance', 'deployment_control', 'flyway_schema_history'}
TABLES = KEEP | set('annotation_attribute attribute auto_label_artifact auto_label_job auto_label_job_sample '
    'calibrated_sensor capture_log category dataset dataset_provenance dataset_search_index dataset_upload_session '
    'ego_pose gt_annotation image_embedding label_document label_edit label_edit_target label_override label_revision '
    'map_asset map_log object_instance predicted_annotation sample sample_data scene scene_recording sensor visibility'.split())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    output = args.directory.resolve()
    if not output.is_relative_to(ROOT / '.local/hybrid'):
        raise ValueError('Evidence must stay under .local/hybrid')
    output.mkdir(parents=True, exist_ok=False)
    values = read_values(args.env_file)
    url = urlparse(values['DB_URL'].removeprefix('jdbc:'))
    if (url.hostname != HOST or url.path != '/drivescene' or url.port not in (None, 5432)
            or values['DB_USERNAME'] != 'ds2l_app' or values['UPLOAD_S3_BUCKET'] != BUCKET):
        raise ValueError('Unexpected database or bucket; refusing reset')
    ca = ROOT / '.local/hybrid/rds-ca.pem'
    if not ca.is_file():
        raise ValueError('Existing RDS CA bundle is required')
    env = os.environ.copy()
    env.update(PGPASSWORD=values['DB_PASSWORD'], PGCONNECT_TIMEOUT='15')
    connection = f'host={HOST} user=ds2l_app dbname=drivescene sslmode=verify-full sslrootcert=/ca.pem'
    base = ['docker', 'run', '--rm', '--env', 'PGPASSWORD', '--env', 'PGCONNECT_TIMEOUT',
            '--mount', f'type=bind,source={ca},target=/ca.pem,readonly', IMAGE]
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'applied': False,
              'scope': 'app rows only; no S3/account/model/local cache mutation; sequences continue'}

    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

    def run(command, label, *, input=None, timeout=900):
        result = subprocess.run(command, env=env, input=input, capture_output=True, timeout=timeout)
        error = result.stderr.decode('utf-8', errors='replace').replace(values['DB_PASSWORD'], '[REDACTED]')
        if error:
            (output / (label + '.stderr.log')).write_text(error, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(label + ' failed; inspect local error log; no credentials are printed')
        return result.stdout

    def sql(query, local=None):
        prefix = (['docker', 'exec', local, 'psql', '-U', 'ds2l_app', '-d', 'restore_check'] if local
                  else base + ['psql', connection])
        return run(prefix + ['-X', '-v', 'ON_ERROR_STOP=1', '-At', '-c', query], 'sql', timeout=240).decode().strip()

    def aws(*arguments):
        return json.loads(run(['aws', *arguments, '--profile', 'ds2l-seoul', '--region', 'ap-northeast-2',
                               '--output', 'json', '--no-cli-pager'], 'aws', timeout=90))

    def inventory():
        objects = aws('s3api', 'list-objects-v2', '--bucket', BUCKET).get('Contents', [])
        return sorted([{'key': r['Key'], 'bytes': r['Size'], 'etag': r['ETag']} for r in objects], key=lambda r: r['key'])

    def stopped():
        for name in ('drivescene-hybrid-backend-1', 'drivescene-hybrid-ai-server-1'):
            state = json.loads(run(['docker', 'inspect', '--format', '{{json .State}}', name], 'container-state'))
            if state['Running']:
                raise RuntimeError('Stop backend and AI before backup/reset')

    try:
        if aws('sts', 'get-caller-identity')['Account'] != '189750306426':
            raise ValueError('Unexpected AWS account')
        tables = sql("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
        if set(tables) != TABLES:
            raise ValueError('Table set changed; review schema before reset')
        # Order-independent digest of every row, including duplicates. This is restore
        # equivalence checking, not a cryptographic signature; the dump has SHA-256.
        snapshot_query = ' UNION ALL '.join(
            f"SELECT '{table}', count(*), md5(coalesce(string_agg(d, '' ORDER BY d), '')) "
            f'FROM (SELECT md5(row_to_json(t)::text) d FROM public."{table}" t) row_hashes' for table in tables)

        def snapshot(local=None):
            return {name: {'rows': int(count), 'content_md5': digest}
                    for name, count, digest in (line.split('|') for line in sql(snapshot_query, local).splitlines())}

        sequence_names = sql("SELECT sequencename FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename").splitlines()
        if any(not re.fullmatch('[a-z_][a-z0-9_]*', name) for name in sequence_names):
            raise ValueError('Unexpected sequence identifier')
        sequence_query = ' UNION ALL '.join(f"SELECT '{name}',last_value,is_called FROM public.\"{name}\"" for name in sequence_names)
        before = snapshot()
        before_sequences = sql(sequence_query)
        report.update(before=before, before_sequences=before_sequences)
        save('plan.json', {'tables_to_clear': sorted(TABLES - KEEP), 'tables_to_keep': sorted(KEEP),
                          'before': before, 'continue_identity': True, 's3_deletion': False})
        if not args.apply:
            print(json.dumps({'plan': str(output / 'plan.json'), 'tables': len(tables)}))
            return
        stopped()
        if sql('SELECT maintenance FROM deployment_control WHERE id=1') != 't':
            raise RuntimeError('Maintenance mode must be enabled before reset')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = args.env_file.resolve().parent / f'pre-app-reset-{stamp}.dump'
        dump = run(base + ['pg_dump', '--dbname', connection, '--format=custom', '--no-owner', '--no-acl'], 'pg-dump')
        if len(dump) < 1000:
            raise RuntimeError('Unexpectedly small backup; nothing reset')
        with backup.open('xb') as stream:
            stream.write(dump)
            stream.flush()
            os.fsync(stream.fileno())
        digest = hashlib.sha256(dump).hexdigest()
        if hashlib.sha256(backup.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Backup readback mismatch')
        report.update(backup=str(backup), backup_bytes=len(dump), backup_sha256=digest)
        save('backup.json', report)
        name = 'ds2l-reset-restore-' + stamp.lower()
        env['POSTGRES_PASSWORD'] = secrets.token_hex(24)
        run(['docker', 'run', '-d', '--name', name, '--label', 'ds2l.reset-validation=' + stamp,
             '--network', 'none', '--cpus', '2', '--memory', '1g', '-e', 'POSTGRES_USER=ds2l_app',
             '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_DB=restore_check', IMAGE], 'restore-start')
        try:
            for _ in range(45):
                ready = subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'ds2l_app', '-d', 'restore_check'], capture_output=True)
                if ready.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Isolated restore database is not ready')
            run(['docker', 'exec', '-i', name, 'pg_restore', '--exit-on-error', '--no-owner', '--no-acl',
                 '-U', 'ds2l_app', '-d', 'restore_check'], 'pg-restore', input=dump)
            restored = snapshot(name)
            restored_sequences = sql(sequence_query, name)
            save('restore-validation.json', {'tables': restored, 'sequences': restored_sequences,
                  'tables_match': restored == before, 'sequences_match': restored_sequences == before_sequences})
            if restored != before or restored_sequences != before_sequences:
                raise RuntimeError('Restore contents differ; nothing reset')
            report['restore_validated'] = True
        finally:
            owner = run(['docker', 'inspect', '--format', '{{index .Config.Labels "ds2l.reset-validation"}}', name], 'restore-owner').decode().strip()
            if owner != stamp:
                raise RuntimeError('Restore container ownership mismatch')
            run(['docker', 'rm', '-f', '-v', name], 'restore-remove')
        stopped()
        if snapshot() != before or sql(sequence_query) != before_sequences:
            raise RuntimeError('Database changed during backup; nothing reset')
        before_s3 = inventory()
        save('s3-before.json', before_s3)
        guards = ' '.join(f"IF (SELECT md5(coalesce(string_agg(d, '' ORDER BY d), '')) FROM "
            f'(SELECT md5(row_to_json(t)::text) d FROM public."{table}" t) row_hashes) '
            f"<> '{before[table]['content_md5']}' THEN RAISE EXCEPTION 'retained table changed'; END IF;" for table in sorted(KEEP))
        # All reviewed app tables are explicit. RESTRICT prevents a changed schema from
        # silently cascading into unrelated objects. No sequences or schema are reset.
        targets = ','.join('public."' + table + '"' for table in sorted(TABLES - KEEP))
        sql("BEGIN; SET LOCAL lock_timeout='10s'; SET LOCAL statement_timeout='60s'; "
            + f'TRUNCATE TABLE {targets} CONTINUE IDENTITY RESTRICT; DO $$ BEGIN {guards} END; $$; COMMIT;')
        report['applied'] = True
        after = snapshot()
        after_s3 = inventory()
        save('s3-after.json', after_s3)
        report.update(after=after, s3_preserved=before_s3 == after_s3, s3_objects=len(after_s3),
                      sequences_preserved=sql(sequence_query) == before_sequences,
                      retained_tables_preserved=all(after[t] == before[t] for t in KEEP),
                      app_tables_empty=all(after[t]['rows'] == 0 for t in TABLES - KEEP))
        if not all(report[k] for k in ('s3_preserved', 'sequences_preserved', 'retained_tables_preserved', 'app_tables_empty')):
            raise RuntimeError('Post-reset verification mismatch; backup and report retained')
        report['pass'] = True
        print(json.dumps({'pass': True, 'restored_tables': len(tables), 's3_objects_preserved': len(after_s3),
                          'backup': str(backup), 'report': str(output / 'report.json')}))
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save('report.json', report)


if __name__ == '__main__':
    main()
