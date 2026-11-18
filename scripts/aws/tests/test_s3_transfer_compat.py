"""Exercise actual botocore StreamingBody contracts without AWS/network access."""
import io
from pathlib import Path
import sys
import tempfile
import unittest

from botocore.exceptions import IncompleteReadError
from botocore.response import StreamingBody

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hybrid'))
from benchmark_s3_transfers import copy_response_body


class S3StreamContractTests(unittest.TestCase):
    def test_stream_copy_preserves_bytes_and_closes_response(self):
        content = b'fixture' * 20000
        raw = io.BytesIO(content)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'download.tgz'
            copy_response_body(StreamingBody(raw, len(content)), destination)
            self.assertEqual(destination.read_bytes(), content)
        self.assertTrue(raw.closed)

    def test_truncated_response_is_rejected_and_closed(self):
        raw = io.BytesIO(b'partial')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(IncompleteReadError):
                copy_response_body(StreamingBody(raw, 100), Path(folder) / 'download.tgz')
        self.assertTrue(raw.closed)


if __name__ == '__main__':
    unittest.main()
