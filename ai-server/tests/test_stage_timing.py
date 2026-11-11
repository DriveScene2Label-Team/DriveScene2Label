import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('stage_timing', Path(__file__).resolve().parents[1] / 'services/stage_timing.py')
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


def test_timing_preserves_result_arguments_and_records_scope(tmp_path, capsys):
    timer = timing.StageTimer(tmp_path, 'scene-0103', 5)
    result = object()
    def stage(value, *, flag):
        assert value is result and flag is True
        return value
    module = SimpleNamespace(stage=stage)
    timer.instrument(module, {'stage':'image_detection_segmentation'})
    assert module.stage(result, flag=True) is result
    rows = [json.loads(line) for line in (tmp_path/'stage-events.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows] == ['started','completed']
    assert all(row['job_id']==5 and row['scene']=='scene-0103' for row in rows)
    assert rows[1]['wall_seconds'] >= 0 and rows[1]['cpu_seconds'] >= 0
    assert capsys.readouterr().out.count('DS2L_STAGE') == 2


def test_failed_stage_preserves_exception_and_omits_sensitive_message(tmp_path):
    timer = timing.StageTimer(tmp_path, 'scene-0103')
    error = ValueError('private argument must not be logged')
    with pytest.raises(ValueError) as caught:
        with timer.stage('dataset_load'):
            raise error
    assert caught.value is error
    raw = (tmp_path/'stage-events.jsonl').read_text()
    assert 'private argument' not in raw
    last = json.loads(raw.splitlines()[-1])
    assert last['event']=='failed' and last['error_type']=='ValueError'
