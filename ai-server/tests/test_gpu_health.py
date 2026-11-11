import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import gpu_health
from services.capability_service import CapabilityService

def test_lost_gpu_is_not_reported_ready(monkeypatch):
    monkeypatch.setenv('AI_REQUIRE_GPU', 'true')
    monkeypatch.setattr(gpu_health, '_checked', 0)
    with patch.object(gpu_health.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout=b'')) as probe:
        assert not gpu_health.gpu_available()
        clip = SimpleNamespace(model=object(), device='cuda')
        assert CapabilityService(clip_service=clip)._clip()['reasonCode'] == 'GPU_UNAVAILABLE'
        assert probe.call_count == 1
    monkeypatch.setattr(gpu_health, '_checked', 0)
    with patch.object(gpu_health.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=b'GPU-test-id\n')):
        assert gpu_health.gpu_available()
