import importlib.util
from pathlib import Path
from datetime import datetime, timezone
import unittest
import json
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('measurement', Path(__file__).resolve().parents[1] / 'measurement.py')
measurement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measurement)


class MeasurementTests(unittest.TestCase):
    def test_docker_cursor_gap_is_reported_and_cursor_not_advanced(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            measurement.save(path / 'manifest.json', {'started_at': '2026-11-12T00:00:00+00:00'})
            def fake_command(args):
                return '2026-11-12T01:00:00Z [HTTP] request=one route=/api/test status=200 wall_ms=15' if '--tail' in args else ''
            with patch.object(measurement, 'command', side_effect=fake_command), patch.object(measurement, 'now', return_value=datetime(2026, 11, 13, tzinfo=timezone.utc)):
                report = measurement.collect(path)
            self.assertEqual(len(report['capture_errors']), 2)
            self.assertEqual(report['capture_errors'][0]['error'], 'LogCursorMismatch')
            self.assertEqual(json.loads((path / 'manifest.json').read_text())['cursors'], {})

    def test_capture_retry_preserves_cursor_and_deduplicates_observations(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            measurement.save(path / 'manifest.json', {'started_at': '2026-11-12T00:00:00+00:00'})
            def fake_command(args):
                if args[-1] == measurement.CONTAINERS['ai']:
                    raise RuntimeError('offline')
                return '2026-11-12T01:00:00Z [HTTP] request=one route=/api/test status=503 wall_ms=15'
            with patch.object(measurement, 'command', side_effect=fake_command):
                first = measurement.collect(path)
                second = measurement.collect(path)
            self.assertEqual((first['events'], second['events']), (1, 1))
            self.assertEqual(len(second['failures']), 1)
            self.assertEqual(second['capture_errors'], [{'service': 'ai', 'error': 'RuntimeError'}])
            manifest = json.loads((path / 'manifest.json').read_text())
            self.assertIn('backend', manifest['cursors'])
            self.assertNotIn('ai', manifest['cursors'])
            self.assertTrue((path / 'report.md').is_file())

    def test_import_clip_and_recording_timings_are_captured(self):
        row = measurement.parse_line('2026-11-12T01:00:00Z INFO Dataset upload id=abc stage=STORING_ORIGINAL event=completed wall_ms=358100')
        self.assertEqual(row['upload'], 'abc')
        self.assertEqual(row['wall_ms'], '358100')
        row = measurement.parse_line('time [CLIP] dataset=5 image=8 ai_ms=100 storage_ms=20 total_ms=120')
        self.assertEqual(row['storage_ms'], '20')
        row = measurement.parse_line('time [RERUN_STAGE] recording=5 stage=ai_export wall_ms=3000')
        self.assertEqual(row['recording'], '5')

    def test_excludes_unstructured_messages_and_secrets(self):
        self.assertIsNone(measurement.parse_line('Exception password=secret'))
        row = measurement.parse_line('2026-11-12T01:00:00Z [HTTP] request=abc route=/api/search status=200 wall_ms=42 cookie=SECRET query=PRIVATE')
        self.assertEqual(row['wall_ms'], '42')
        self.assertNotIn('cookie', row)
        self.assertNotIn('query', row)

    def test_deduplicates_overlapping_capture_and_normalizes_units(self):
        row = {'tag': 'DS2L_STAGE', 'run_id': 'one', 'stage': 'model', 'event': 'completed', 'call': 1, 'wall_seconds': 1.5}
        result = measurement.summarize([row, row])
        self.assertEqual(result['events'], 1)
        self.assertEqual(result['timings'][0]['sum_ms'], 1500)

    def test_started_and_missing_times_are_not_zero_duration_success(self):
        rows = [{'tag': 'VESPA', 'stage': 'started'}, {'tag': 'DS2L_STAGE', 'event': 'started', 'wall_seconds': 4}]
        self.assertEqual(measurement.summarize(rows)['timings'], [])

    def test_failures_remain_distinct_from_completed_and_other_runs(self):
        rows = [{'tag': 'DS2L_STAGE', 'run_id': run, 'stage': 'model', 'event': event, 'wall_seconds': 2}
                for run, event in [('a', 'completed'), ('a', 'failed'), ('b', 'completed')]]
        report = measurement.summarize(rows)
        self.assertEqual(len(report['timings']), 3)
        self.assertEqual(len(report['failures']), 1)

    def test_malformed_runner_and_nonfinite_durations(self):
        self.assertIsNone(measurement.parse_line('DS2L_STAGE {broken'))
        rows = [{'tag': 'HTTP', 'wall_ms': value} for value in ('nan', '-1', 'inf', 'no')]
        self.assertEqual(measurement.summarize(rows)['timings'], [])

    def test_percentiles_are_nearest_rank(self):
        rows = [{'tag': 'HTTP', 'request': str(index), 'route': '/api/test', 'wall_ms': index} for index in range(1, 101)]
        result = measurement.summarize(rows)['timings'][0]
        self.assertEqual((result['p50_ms'], result['p95_ms'], result['max_ms']), (50, 95, 100))


if __name__ == '__main__':
    unittest.main()
