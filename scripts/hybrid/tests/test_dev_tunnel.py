import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dev_tunnel


class PrivateTunnelTests(unittest.TestCase):
    def test_microsoft_sync_rejects_cloudflare_routes_before_changing_environment(self):
        with patch.object(dev_tunnel, 'config', return_value={}), patch.object(dev_tunnel.cloud, 'vercel') as vercel:
            with self.assertRaisesRegex(RuntimeError, 'Current frontend routing uses Cloudflare'):
                dev_tunnel.prepare()
            vercel.assert_not_called()

    def test_cloudflare_routes_do_not_forward_microsoft_credentials(self):
        config = json.loads((dev_tunnel.cloud.REPO / 'frontend/vercel.json').read_text())
        for route in config['routes'][:2]:
            self.assertNotIn('BACKEND_TUNNEL_TOKEN', json.dumps(route))
            self.assertNotIn('X-Tunnel-Authorization', json.dumps(route))
            self.assertEqual(route['headers']['Cache-Control'], 'private, no-store')

    def test_expired_wrong_scope_cache_and_refresh_window(self):
        future = datetime.now(timezone.utc) + timedelta(hours=20)
        for stamp in (future.isoformat(), future.strftime('%Y-%m-%d %H:%M:%S UTC')):
            cached = {'tunnelId': 'fixture.jpe1', 'token': 'fixture-only', 'expiration': stamp}
            self.assertTrue(dev_tunnel.valid_token(cached, 'fixture.jpe1'))
            self.assertFalse(dev_tunnel.valid_token(cached, 'another.jpe1'))
        for stamp in ('bad', (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()):
            self.assertFalse(dev_tunnel.valid_token({**cached, 'expiration': stamp}, 'fixture.jpe1'))
        self.assertFalse(dev_tunnel.valid_token({}, 'fixture.jpe1'))


if __name__ == '__main__':
    unittest.main()
