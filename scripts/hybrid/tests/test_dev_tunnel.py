import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dev_tunnel


class PrivateTunnelTests(unittest.TestCase):
    def test_secret_is_only_an_upstream_request_transform(self):
        config = json.loads((dev_tunnel.cloud.REPO / 'frontend/vercel.json').read_text())
        for route in config['routes'][:2]:
            transform = route['transforms'][0]
            self.assertEqual(transform['type'], 'request.headers')
            self.assertEqual(transform['env'], ['BACKEND_TUNNEL_TOKEN'])
            self.assertEqual(transform['args'], 'tunnel $BACKEND_TUNNEL_TOKEN')
            self.assertNotIn('X-Tunnel-Authorization', route['headers'])

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
