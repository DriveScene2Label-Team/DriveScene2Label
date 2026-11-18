import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('evidence_export', Path(__file__).resolve().parents[1] / 'export_review_evidence.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class EvidenceExportTests(unittest.TestCase):
    def test_rejects_reserved_and_colliding_paths_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection = root / 'selection.json'
            output = root / 'docs/evidence/check'
            for targets in (['manifest.json'], ['case/../manifest.json'], ['result.json', 'case/../result.json']):
                selection.write_text(json.dumps([{'source': '.local/hybrid/data.json', 'target': name} for name in targets]))
                with patch.object(exporter, 'ROOT', root), patch('sys.argv', ['export', '--selection', str(selection), '--output', str(output)]):
                    with self.assertRaisesRegex(ValueError, 'unique'):
                        exporter.main()
                self.assertFalse(output.exists())

    def test_source_manifest_is_exported_under_distinct_name_with_valid_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / '.local/hybrid/manifest.json'
            source.parent.mkdir(parents=True)
            source.write_text('{"complete":true}')
            selection = root / 'selection.json'
            selection.write_text(json.dumps([{'source': '.local/hybrid/manifest.json', 'target': 'experiment-manifest.json'}]))
            output = root / 'docs/evidence/check'
            with patch.object(exporter, 'ROOT', root), patch('sys.argv', ['export', '--selection', str(selection), '--output', str(output)]):
                exporter.main()
            index = json.loads((output / 'manifest.json').read_text())
            for row in index['files']:
                self.assertEqual(hashlib.sha256((output / row['target']).read_bytes()).hexdigest(), row['export_sha256'])
            self.assertEqual(json.loads((output / 'experiment-manifest.json').read_text()), {'complete': True})


if __name__ == '__main__':
    unittest.main()
