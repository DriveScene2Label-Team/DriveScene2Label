import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('evidence_io',Path(__file__).resolve().parents[1]/'evidence_io.py')
evidence=importlib.util.module_from_spec(spec);spec.loader.exec_module(evidence)


class EvidenceIOTest(unittest.TestCase):
    def test_locked_destination_preserves_old_report_then_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'report.json';target.write_text('{"status":"running"}')
            replace=os.replace;calls=[]
            def transient(source,destination):
                calls.append(1)
                if len(calls)==1:
                    self.assertEqual(json.loads(target.read_text())['status'],'running')
                    raise PermissionError('destination temporarily locked')
                return replace(source,destination)
            with patch.object(evidence.os,'replace',side_effect=transient),patch.object(evidence.time,'sleep'):
                evidence.save_json(target,{'status':'completed'})
            self.assertEqual(json.loads(target.read_text()),{'status':'completed'})
            self.assertEqual(list(Path(folder).glob('*.tmp')),[])

    def test_persistent_lock_is_reported_and_new_payload_is_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'report.json';target.write_text('{"status":"running"}')
            with patch.object(evidence.os,'replace',side_effect=PermissionError('locked')),patch.object(evidence.time,'sleep'):
                with self.assertRaises(PermissionError):evidence.save_json(target,{'status':'completed'})
            self.assertEqual(json.loads(target.read_text())['status'],'running')
            pending=list(Path(folder).glob('*.tmp'))
            self.assertEqual(len(pending),1)
            self.assertEqual(json.loads(pending[0].read_text())['status'],'completed')


if __name__=='__main__':unittest.main()
