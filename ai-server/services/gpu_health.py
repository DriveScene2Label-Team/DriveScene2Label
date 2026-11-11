"""Short read-only NVML probe for deployments that explicitly require an NVIDIA GPU."""
import os
import subprocess
import time
from threading import Lock

_lock = Lock()
_checked = 0.0
_available = False

def gpu_available():
    global _checked, _available
    if os.environ.get('AI_REQUIRE_GPU', 'false').lower() != 'true':
        return True
    with _lock:
        now = time.monotonic()
        if now - _checked < 5:
            return _available
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'], capture_output=True, timeout=3)
            _available = result.returncode == 0 and result.stdout.strip().startswith(b'GPU-')
        except (OSError, subprocess.TimeoutExpired):
            _available = False
        _checked = now
        return _available
