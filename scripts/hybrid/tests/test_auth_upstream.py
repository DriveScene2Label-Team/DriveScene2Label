"""Isolated Docker regression: no production network, database, GPU, or credentials."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import unittest
from urllib.request import Request, urlopen
from uuid import uuid4

REPO = Path(__file__).resolve().parents[3]
FIXTURE = r'''
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib, json
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path == '/range' and self.headers.get('Range') == 'bytes=2-4':
            self.send_response(206)
            self.send_header('Content-Range', 'bytes 2-4/10')
            self.send_header('ETag', '"fixture-v1"')
            self.send_header('Content-Length', '3')
            self.end_headers()
            self.wfile.write(b'234')
        else:
            self.send_response(204)
            self.end_headers()
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        result = json.dumps({'headers': dict(self.headers),
                             'length': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                             'path': self.path}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(result)))
        self.send_header('X-Request-ID', 'fixture-request')
        self.end_headers()
        self.wfile.write(result)
ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
'''


@unittest.skipUnless(os.environ.get('RUN_GATEWAY_INTEGRATION') == '1',
                     'Set RUN_GATEWAY_INTEGRATION=1 to run isolated Docker gateway tests')
class AuthUpstreamTests(unittest.TestCase):
    @classmethod
    def docker(cls, *args):
        return subprocess.check_output(['docker', *args], text=True, encoding='utf-8', stderr=subprocess.STDOUT).strip()

    @classmethod
    def setUpClass(cls):
        name = 'ds2l-header-test-' + uuid4().hex[:10]
        cls.network, cls.backend, cls.proxy = name, name + '-backend', name + '-proxy'
        cls.addClassCleanup(cls.cleanup)
        cls.docker('network', 'create', cls.network)
        cls.docker('run', '-d', '--name', cls.backend, '--network', cls.network,
                   '--network-alias', 'backend', 'python:3.12-slim-bookworm', 'python', '-u', '-c', FIXTURE)
        image = re.search(r'image: (nginx:\S+)', (REPO / 'compose.hybrid-auth.yml').read_text()).group(1)
        cls.docker('run', '-d', '--name', cls.proxy, '--network', cls.network,
                   '-p', '127.0.0.1::8081', '--mount',
                   f'type=bind,source={REPO / "infra/local/auth-upstream.conf"},target=/etc/nginx/nginx.conf,readonly',
                   image)
        port = json.loads(cls.docker('inspect', cls.proxy))[0]['NetworkSettings']['Ports']['8081/tcp'][0]['HostPort']
        cls.origin = 'http://127.0.0.1:' + port
        for _ in range(30):
            try:
                with urlopen(cls.origin + '/ready', timeout=2) as response:
                    if response.status == 204:
                        return
            except OSError:
                time.sleep(.2)
        raise RuntimeError('Isolated gateway did not reach its fixture backend')

    @classmethod
    def cleanup(cls):
        for name in (cls.proxy, cls.backend):
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, check=False)
        subprocess.run(['docker', 'network', 'rm', cls.network], capture_output=True, check=False)

    def test_large_session_cookie_is_removed_without_changing_upload_or_request_key(self):
        body = b'upload-fixture\x00' * 300000
        request = Request(self.origin + '/upload?part=7', data=body, headers={
            'Cookie': '__Host-ds2l=' + 'x' * 12000,
            'Authorization': 'Bearer fixture-only',
            'Idempotency-Key': 'fixture-key', 'Content-Type': 'application/octet-stream',
            'If-Range': '"fixture-v1"', 'Range': 'bytes=2-4',
        })
        with urlopen(request, timeout=20) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['X-Request-ID'], 'fixture-request')
            result = json.load(response)
        headers = {key.lower(): value for key, value in result['headers'].items()}
        self.assertNotIn('cookie', headers)
        self.assertNotIn('authorization', headers)
        self.assertEqual(headers['idempotency-key'], 'fixture-key')
        self.assertEqual(headers['range'], 'bytes=2-4')
        self.assertEqual(headers['if-range'], '"fixture-v1"')
        self.assertEqual(headers['content-type'], 'application/octet-stream')
        self.assertEqual(result['length'], len(body))
        self.assertEqual(result['sha256'], hashlib.sha256(body).hexdigest())
        self.assertEqual(result['path'], '/upload?part=7')

    def test_partial_download_status_body_and_headers_are_preserved(self):
        request = Request(self.origin + '/range', headers={'Range': 'bytes=2-4'})
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers['Content-Range'], 'bytes 2-4/10')
            self.assertEqual(response.headers['ETag'], '"fixture-v1"')
            self.assertEqual(response.read(), b'234')


if __name__ == '__main__':
    unittest.main()
