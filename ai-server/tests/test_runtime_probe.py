"""CPU-only regression guards for the optional runtime probe, not model accuracy."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('runtime_probe',Path(__file__).resolve().parents[1]/'tools/probe_grounding_runtime.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class RuntimeProbeComparisonTest(unittest.TestCase):
    def reference(self):return {'logits':np.array([1.,-np.inf]),'pred_boxes':np.ones((1,4))}

    def test_padding_negative_infinity_is_allowed_but_nan_is_not(self):
        self.assertTrue(probe.compare_arrays(self.reference(),self.reference())['passed'])
        candidate=self.reference();candidate['logits'][0]=np.nan
        self.assertFalse(probe.compare_arrays(self.reference(),candidate)['passed'])

    def test_wrong_infinity_sign_shape_and_box_drift_fail(self):
        for name,value in [('logits',np.array([1.,np.inf])),('pred_boxes',np.ones((2,4))),
                           ('pred_boxes',np.ones((1,4))+.1)]:
            candidate=self.reference();candidate[name]=value
            self.assertFalse(probe.compare_arrays(self.reference(),candidate)['passed'])


if __name__=='__main__':unittest.main()
