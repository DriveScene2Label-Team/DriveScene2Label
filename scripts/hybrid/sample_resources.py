"""Sample allowlisted local resources alongside a measurement; no app mutations."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import time

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('diagnose', REPO / 'scripts/hybrid/diagnose.py')
diagnose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnose)
GUEST = """
import json, os
from pathlib import Path
info = {'logical_cpu_count': os.cpu_count(), 'affinity_cpu_count': len(os.sched_getaffinity(0))}
for line in Path('/proc/meminfo').read_text().splitlines():
    key, value = line.split(':', 1)
    if key in ('MemTotal','MemAvailable','SwapTotal','SwapFree','Dirty','Writeback'):
        info[key] = value.strip()
for name in ('memory.current','memory.max','memory.swap.current','memory.events','memory.pressure','io.pressure','cpu.pressure','cpu.max','cpuset.cpus.effective'):
    path = Path('/sys/fs/cgroup') / name
    if path.is_file():
        info[name] = path.read_text().strip()
print(json.dumps(info))
"""


def sample():
    tasks = {
        'gpuCsv': lambda: diagnose.command(['docker', 'exec', diagnose.AI, 'nvidia-smi',
            '--query-gpu=' + diagnose.GPU_FIELDS, '--format=csv,noheader,nounits'], 'text'),
        'containers': lambda: diagnose.command(['docker', 'stats', '--no-stream', '--format', '{{json .}}',
            diagnose.AI, 'drivescene-hybrid-backend-1'], 'jsonl'),
        'host': lambda: diagnose.command(['powershell', '-NoProfile', '-NonInteractive', '-Command', diagnose.HOST], 'json'),
        'guest': lambda: diagnose.command(['docker', 'exec', diagnose.AI, 'python', '-c', GUEST], 'json'),
    }
    started = time.monotonic()
    at = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {key: pool.submit(action) for key, action in tasks.items()}
        row = {key: future.result() for key, future in futures.items()}
    return {'at': at, 'sample_seconds': round(time.monotonic()-started, 3), **row}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if not any((args.directory/name).is_file() for name in ('manifest.json', 'test-conditions.json')):
        raise ValueError('Record test conditions in the evidence directory first.')
    deadline = time.monotonic() + 4*3600
    with (args.directory / 'resources.jsonl').open('x', encoding='utf-8') as output:
        while time.monotonic() < deadline and not (args.directory / 'STOP').exists():
            started = time.monotonic()
            row = sample()
            output.write(json.dumps(row, ensure_ascii=False) + '\n')
            output.flush()
            print(json.dumps({'at': row['at'], 'sample_seconds': row['sample_seconds']}), flush=True)
            if args.once:
                break
            while time.monotonic()-started < 30 and not (args.directory / 'STOP').exists():
                time.sleep(1)


if __name__ == '__main__':
    main()
