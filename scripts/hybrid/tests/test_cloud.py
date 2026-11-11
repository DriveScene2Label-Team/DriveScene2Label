import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('cloud', Path(__file__).resolve().parents[1] / 'cloud.py')
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class CloudTests(unittest.TestCase):
    def test_redeploy_accepts_single_cli_deployment_and_rejects_ambiguity(self):
        for response in ({'id': 'dpl_new'}, {'deploymentId': 'dpl_new'}, {'deployment': {'id': 'dpl_new'}}, {'deployments': [{'id': 'dpl_new'}]}):
            self.assertEqual(cloud.created_deployment_id(response), 'dpl_new')
        with self.assertRaises(RuntimeError):
            cloud.created_deployment_id({'deployments': [{'id': 'dpl_a'}, {'id': 'dpl_b'}]})

    def test_running_database_is_never_restarted(self):
        with patch.object(cloud, 'database_state', return_value='available'), patch.object(cloud, 'aws') as aws:
            cloud.ensure_database()
            aws.assert_not_called()

    def test_stopped_database_is_started_once_and_waited_for(self):
        with patch.object(cloud, 'database_state', side_effect=['stopped', 'stopped', 'starting', 'available']), \
             patch.object(cloud, 'aws') as aws, patch.object(cloud.time, 'sleep'):
            cloud.ensure_database()
            aws.assert_called_once_with('rds', 'start-db-instance', '--db-instance-identifier', cloud.DATABASE)

    def test_wrong_account_never_reaches_rds(self):
        with patch.object(cloud, 'aws', return_value={'Account': 'wrong'}) as aws:
            with self.assertRaisesRegex(RuntimeError, 'account mismatch'):
                cloud.database_state()
            aws.assert_called_once_with('sts', 'get-caller-identity')

    def test_wrong_engine_is_not_started(self):
        with patch.object(cloud, 'aws', side_effect=[{'Account': cloud.ACCOUNT}, {
            'DBInstances': [{'DBInstanceIdentifier': cloud.DATABASE, 'Engine': 'aurora-postgresql'}]}]):
            with self.assertRaisesRegex(RuntimeError, 'existing PostgreSQL'):
                cloud.ensure_database()

    def test_public_gate_must_deny_anonymous_requests(self):
        for code in (401, 302, 502):
            error = HTTPError('https://test.invalid/api/datasets', code, 'fixture', {}, io.BytesIO())
            with patch.object(cloud.urllib.request.OpenerDirector, 'open', side_effect=error):
                if code == 401:
                    cloud.require_auth_gate('https://test.invalid')
                else:
                    with self.assertRaises(RuntimeError):
                        cloud.require_auth_gate('https://test.invalid')

    def test_unchanged_connection_does_not_redeploy(self):
        origin = 'https://fixture-tunnel.trycloudflare.com'
        current = {'id': 'dpl_old', 'name': cloud.PROJECT_NAME, 'contextName': cloud.TEAM_SLUG, 'target': 'production', 'readyState': 'READY'}
        row = {'key': 'BACKEND_URL', 'target': ['production'], 'value': 'encrypted-fixture', 'updatedAt': 1}
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'connection.json'
            cloud.save_connection(state, {'origin': origin, 'deploymentId': current['id'], 'envRevision': cloud.environment_revision(row)})
            with patch.object(cloud, 'require_auth_gate'), patch.object(cloud, 'vercel', side_effect=[
                {'id': cloud.PROJECT, 'owner': {'slug': cloud.TEAM_SLUG}}, current,
                {'envs': [row]}
            ]) as vercel:
                cloud.sync_vercel(origin, state)
                self.assertEqual(vercel.call_count, 3)

    def test_failed_deploy_can_be_checked_again_without_duplicate_creation(self):
        origin = 'https://fixture-tunnel.trycloudflare.com'
        old = {'id': 'dpl_old', 'projectId': cloud.PROJECT, 'target': 'production', 'readyState': 'READY'}
        ready = {**old, 'id': 'dpl_new'}
        project = {'id': cloud.PROJECT, 'accountId': cloud.TEAM}
        env = {'envs': [{'key': 'BACKEND_URL', 'target': ['production'], 'value': 'encrypted-fixture', 'updatedAt': 1}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'connection.json'
            with patch.object(cloud, 'require_auth_gate'), patch.object(cloud, 'vercel', side_effect=[
                project, old, env, None, env, {'id': 'dpl_new'}, RuntimeError('network unavailable')
            ]):
                with self.assertRaisesRegex(RuntimeError, 'network'):
                    cloud.sync_vercel(origin, path)
            self.assertTrue(json.loads(path.read_text())['pending'])
            with patch.object(cloud, 'require_auth_gate'), patch.object(cloud, 'vercel', side_effect=[
                project, old, env, ready, ready
            ]) as vercel:
                cloud.sync_vercel(origin, path)
                self.assertFalse(any(call.args[0] == 'redeploy' for call in vercel.call_args_list))
            self.assertEqual(json.loads(path.read_text()), {'origin': origin, 'deploymentId': 'dpl_new', 'envRevision': cloud.environment_revision(env['envs'][0])})

    def test_changed_environment_blocks_pending_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'connection.json'
            cloud.save_connection(state, {'origin': 'https://fixture.trycloudflare.com', 'pending': True, 'envRevision': 'old'})
            with patch.object(cloud, 'require_auth_gate'), patch.object(cloud, 'vercel', side_effect=[
                {'id': cloud.PROJECT, 'owner': {'slug': cloud.TEAM_SLUG}},
                {'id': 'dpl_old', 'name': cloud.PROJECT_NAME, 'contextName': cloud.TEAM_SLUG, 'target': 'production', 'readyState': 'READY'},
                {'envs': [{'key': 'BACKEND_URL', 'target': ['production'], 'value': 'changed'}]}
            ]) as cli:
                with self.assertRaisesRegex(RuntimeError, 'environment changed'):
                    cloud.sync_vercel('https://fixture.trycloudflare.com', state)
                self.assertEqual(cli.call_count, 3)

    def test_project_mismatch_blocks_environment_changes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(cloud, 'require_auth_gate'), \
             patch.object(cloud, 'vercel', return_value={'id': 'another-project', 'accountId': cloud.TEAM}) as vercel:
            with self.assertRaisesRegex(RuntimeError, 'mismatch'):
                cloud.sync_vercel('https://fixture-tunnel.trycloudflare.com', Path(directory) / 'connection.json')
            self.assertEqual(vercel.call_count, 1)


if __name__ == '__main__':
    unittest.main()
