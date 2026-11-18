import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_load_report import summarize


class ModelLoadReportTests(unittest.TestCase):
    def test_first_later_and_duplicate_events_stay_separate_across_runs(self):
        first = dict(at='2026-11-18T10:00:00Z', run_id='a', stage='detector_model_get', event='completed', call=1, wall_seconds=9)
        rows = [first, dict(first, service='ai', tag='DS2L_STAGE'), dict(first, call=2, wall_seconds=.001),
                dict(first, run_id='b', wall_seconds=4),
                dict(first, stage='sam_model_get', event='failed', error_type='RuntimeError'),
                dict(first, stage='ground_removal', event='started')]
        result = summarize(rows)['runs']
        self.assertEqual(len(result), 2)
        model = result[0]['models']['detector_model_get']
        self.assertEqual((model['first_access_seconds'], model['later_access_count'], model['completed_access_count']), (9, 1, 2))
        self.assertEqual(result[1]['models']['detector_model_get']['first_access_seconds'], 4)
        self.assertIsNone(result[0]['models']['sam_model_get']['first_access_seconds'])
        self.assertEqual(result[0]['models']['sam_model_get']['failure_count'], 1)
        self.assertEqual(result[0]['open_spans'][0]['stage'], 'ground_removal')
        self.assertFalse(result[0]['runner_result_written'])

    def test_missing_first_sample_and_non_finite_are_not_zero_or_cold_load(self):
        rows = [dict(run_id='a', stage='detector_model_get', event='completed', call=2, wall_seconds=.001),
                dict(run_id='a', stage='sam_model_get', event='completed', call=1, wall_seconds=float('nan'))]
        models = summarize(rows, 'a')['runs'][0]['models']
        self.assertIsNone(models['detector_model_get']['first_access_seconds'])
        self.assertIsNone(models['sam_model_get']['first_access_seconds'])
        self.assertIsNone(models['dinov2_model_get']['first_access_seconds'])
        self.assertEqual(summarize(rows, 'missing')['runs'], [])
