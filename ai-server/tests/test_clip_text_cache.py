"""Cache equivalence, isolation and concurrent duplicate requests; no real GPU/model."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from threading import Event
from unittest.mock import patch

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.clip_service import ClipError, ClipService


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setenv('CLIP_TEXT_CACHE_SIZE', '2')
    item = ClipService()
    item.model = object()
    item.device = 'cpu'
    with patch('services.clip_service.gpu_available', return_value=True):
        yield item
    item.close()


def unit_vector(*args):
    value = torch.zeros(768)
    value[0] = 1
    return value


def test_exact_keys_lru_and_response_mutation_do_not_change_vectors(service):
    with patch('clip_core.encode_text', side_effect=unit_vector) as encode:
        first = service.encode_text('road')
        first.embedding[0] = 99
        assert service.encode_text('road').embedding[0] == 1
        service.encode_text('Road')
        service.encode_text('road')
        service.encode_text(' road')
        assert list(service.text_cache) == ['road', ' road']
        service.encode_text('Road')
        assert encode.call_count == 4
        assert len(service.text_cache) == 2


def test_duplicate_inflight_requests_encode_once(service):
    entered, release = Event(), Event()
    def encode(*args):
        entered.set()
        assert release.wait(5)
        return unit_vector()
    with patch('clip_core.encode_text', side_effect=encode) as model, ThreadPoolExecutor(max_workers=4) as pool:
        first = pool.submit(service.encode_text, 'same')
        assert entered.wait(5)
        others = [pool.submit(service.encode_text, 'same') for _ in range(3)]
        release.set()
        results = [first.result(5), *(future.result(5) for future in others)]
        assert all(result.embedding == results[0].embedding for result in results)
        assert model.call_count == 1


def test_invalid_result_is_not_cached_and_hit_requires_ready_gpu(service):
    with patch('clip_core.encode_text', return_value=torch.zeros(768)):
        with pytest.raises(ClipError, match='invalid embedding'):
            service.encode_text('retry')
    assert not service.text_cache
    with patch('clip_core.encode_text', side_effect=unit_vector):
        service.encode_text('retry')
    with patch('services.clip_service.gpu_available', return_value=False):
        with pytest.raises(ClipError) as error:
            service.encode_text('retry')
        assert error.value.code == 'GPU_UNAVAILABLE'
    service.close()
    assert not service.text_cache
    with pytest.raises(ClipError) as error:
        service.encode_text('retry')
    assert error.value.code == 'CLIP_NOT_READY'


def test_disabled_cache_keeps_inference_per_call(service):
    service.text_cache_size = 0
    with patch('clip_core.encode_text', side_effect=unit_vector) as encode:
        service.encode_text('same')
        service.encode_text('same')
        assert encode.call_count == 2
        assert not service.text_cache


def test_logs_exclude_query_text(service, caplog):
    with patch('clip_core.encode_text', side_effect=unit_vector), caplog.at_level('INFO', logger='uvicorn.error'):
        service.encode_text('private-query-marker')
        service.encode_text('private-query-marker')
    lines = [record.getMessage() for record in caplog.records if '[CLIP_STAGE]' in record.getMessage()]
    assert len(lines) == 2
    assert 'cache=miss' in lines[0] and 'cache=hit' in lines[1]
    assert all('private-query-marker' not in line for line in lines)
