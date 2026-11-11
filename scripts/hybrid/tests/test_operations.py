import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('operations', Path(__file__).resolve().parents[1] / 'operations.py')
operations = importlib.util.module_from_spec(spec);spec.loader.exec_module(operations)


class OperationsTests(unittest.TestCase):
    def test_prepare_preserves_settings_and_existing_token(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'compose.env';path.write_text('DB_USERNAME=example\nOPERATIONS_TOKEN=\n')
            operations.prepare(path)
            before = path.read_text();operations.prepare(path)
            self.assertEqual(before, path.read_text())
            self.assertEqual(operations.read_values(path)['DB_USERNAME'], 'example')
            self.assertEqual(len(operations.read_values(path)['OPERATIONS_TOKEN']), 64)

    def test_resume_checks_actual_write_path_without_creating_data(self):
        with patch.object(operations, 'read_values', return_value={'OPERATIONS_TOKEN': 'test-only'}):
            for status in (400, 503):
                response = io.BytesIO(json.dumps({'maintenance': False}).encode())
                error = HTTPError('http://127.0.0.1:8080/api/dataset-uploads/sessions', status, 'fixture', {}, io.BytesIO())
                with patch.object(operations.urllib.request, 'urlopen', side_effect=[response, error]) as request:
                    if status == 400:
                        self.assertFalse(operations.operation(None, 'resume')['maintenance'])
                    else:
                        with self.assertRaises(RuntimeError): operations.operation(None, 'resume')
                    self.assertEqual(request.call_args_list[1].args[0].data, b'{}')

    def test_resume_rejects_still_quiesced_backend(self):
        with patch.object(operations, 'read_values', return_value={'OPERATIONS_TOKEN': 'test-only'}), patch.object(operations.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"maintenance":true}')):
            with self.assertRaises(RuntimeError): operations.operation(None, 'resume')


if __name__ == '__main__': unittest.main()
