import importlib.util
from pathlib import Path
import unittest
from decimal import Decimal

spec = importlib.util.spec_from_file_location('costs', Path(__file__).resolve().parents[1] / 'summarize_cost_inputs.py')
costs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(costs)


class CostScenariosTests(unittest.TestCase):
    def test_binary_units_request_overhead_and_shared_allowance_boundaries(self):
        prices = dict(rds_instance='0.05', rds_gp3='0.1', s3_standard='0.02', s3_put='0.000005', s3_get='0.0000004', egress='0.1')
        r = costs.calculate(prices, 20, 10 * costs.GIB, archive_bytes=costs.GIB)
        self.assertEqual(r['multipart_parts'], 64)
        self.assertEqual(r['multipart_put_class_requests_no_retry'], 66)
        self.assertEqual(Decimal(r['scenarios']['multipart_extra_requests_per_upload']), Decimal('0.000325'))
        self.assertEqual(Decimal(r['scenarios']['rds_730h_compute_and_storage']), Decimal('38.50'))
        self.assertEqual(Decimal(r['scenarios']['100_archive_downloads_with_100GiB_free_remaining']), Decimal('0.00004'))
        self.assertEqual(Decimal(r['scenarios']['100_archive_downloads_with_no_free_remaining']), Decimal('10.00004'))
        with self.assertRaises(ValueError):
            costs.calculate(prices, 20, 51200 * costs.GIB)
