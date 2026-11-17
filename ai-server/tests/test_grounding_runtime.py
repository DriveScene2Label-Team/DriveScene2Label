import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import json
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'))
from grounding_runtime import configure_detection


class Pipeline:
    framework='pt'
    model=SimpleNamespace(config=SimpleNamespace(model_type='grounding-dino'))
    def preprocess(self,inputs):
        return inputs


class RuntimeTest(unittest.TestCase):
    def test_modes_preserve_results_restore_pipeline_and_trace_exact_input(self):
        for mode in ('baseline','reuse'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                pipeline=Pipeline(); previous=pipeline.preprocess
                expected=[{'label':'car.','score':0.5,'box':{'xmin':1,'ymin':2,'xmax':3,'ymax':4}}]
                def detect(frame,detector,classes,threshold):
                    self.assertEqual(detector.preprocess==previous,mode=='baseline')
                    self.assertEqual(classes,['car']);self.assertEqual(threshold,0.3)
                    return expected
                module=SimpleNamespace(_vlm_detection=detect); trace=Path(directory)/'trace.jsonl'
                configure_detection(module,mode,trace)
                result=module._vlm_detection(np.zeros((2,3,3),dtype=np.uint8),pipeline,['car'],0.3)
                self.assertIs(result,expected);self.assertEqual(pipeline.preprocess,previous)
                row=json.loads(trace.read_text());self.assertEqual(row['boxes'],expected)
                self.assertEqual(row['shape'],[2,3,3]);self.assertEqual(row['mode'],mode)

    def test_failure_restores_pipeline_and_does_not_record_success(self):
        pipeline=Pipeline();previous=pipeline.preprocess
        def fail(*args): raise RuntimeError('expected')
        with tempfile.TemporaryDirectory() as directory:
            trace=Path(directory)/'trace.jsonl';module=SimpleNamespace(_vlm_detection=fail)
            configure_detection(module,'reuse',trace)
            with self.assertRaises(RuntimeError): module._vlm_detection(np.zeros((1,1,3)),pipeline,['car'],0.3)
            self.assertEqual(pipeline.preprocess,previous);self.assertEqual(trace.read_text(),'')

    def test_invalid_mode_rejected_before_mutation(self):
        original=lambda *args:[];module=SimpleNamespace(_vlm_detection=original)
        with self.assertRaises(ValueError): configure_detection(module,'invalid')
        self.assertIs(module._vlm_detection,original)


if __name__=='__main__': unittest.main(verbosity=2)
