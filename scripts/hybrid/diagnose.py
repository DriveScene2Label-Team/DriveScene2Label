"""Read-only sampling of one local labeling run. Writes no credentials or sensor data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
from uuid import UUID

REPO = Path(__file__).resolve().parents[2]
AI = 'drivescene-hybrid-ai-server-1'
CONTAINERS = [AI, 'drivescene-hybrid-backend-1', 'drivescene-hybrid-auth-gateway-1']
GPU_FIELDS = 'timestamp,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,temperature.gpu'
HOST = r"""
$m = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
$os = Get-CimInstance Win32_OperatingSystem
$d = @(Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk | Where-Object Name -ne '_Total' | Select-Object Name,AvgDiskQueueLength,DiskReadBytesPersec,DiskWriteBytesPersec)
@{availableMB=$m.AvailableMBytes; pagesInputPerSec=$m.PagesInputPersec; pagesOutputPerSec=$m.PagesOutputPersec; totalMemoryKB=$os.TotalVisibleMemorySize; disks=$d} | ConvertTo-Json -Depth 4 -Compress
"""
GUEST = r"""
import json, sys
from pathlib import Path
root = Path('/results') / sys.argv[1]
path = root / 'execution.log'
tail = ''
if path.is_file():
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 4000))
        tail = stream.read().decode(errors='replace')
rows = [s.strip() for s in tail.replace('\r', '\n').splitlines() if s.strip()]
info = {}
for line in Path('/proc/meminfo').read_text().splitlines():
    key, value = line.split(':', 1)
    if key in ('MemTotal','MemAvailable','SwapTotal','SwapFree','Dirty','Writeback'):
        info[key] = value.strip()
for name in ('memory.current','memory.max','memory.swap.current','memory.events','memory.pressure','io.pressure','cpu.pressure'):
    p = Path('/sys/fs/cgroup') / name
    if p.is_file():
        info[name] = p.read_text().strip()
print(json.dumps({'memory':info,'logBytes':path.stat().st_size if path.exists() else 0,'progressTail':rows[-4:]}))
"""


def command(args, kind):
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)
        if result.returncode:
            return {'error': 'command_failed', 'exitCode': result.returncode}
        if kind == 'json':
            return json.loads(result.stdout)
        if kind == 'jsonl':
            return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        return {'error': type(error).__name__}


def job_status(job_id):
    started = time.monotonic()
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:8080/api/auto-label/jobs/{job_id}', timeout=10) as response:
            data = json.load(response)
        # Deliberate allowlist; do not log arbitrary server messages or headers.
        value = {key: data.get(key) for key in ('jobId','datasetId','sceneId','sceneName','status','classMode','createdAt','startedAt','completedAt')}
        return {'latencyMs': round((time.monotonic() - started) * 1000, 1), **value}
    except (OSError, ValueError) as error:
        return {'error': type(error).__name__, 'latencyMs': round((time.monotonic() - started) * 1000, 1)}


def sample(job_id, run_id):
    tasks = {
        'job': lambda: job_status(job_id),
        'gpuCsv': lambda: command(['docker','exec',AI,'nvidia-smi',f'--query-gpu={GPU_FIELDS}','--format=csv,noheader,nounits'], 'text'),
        'containers': lambda: command(['docker','stats','--no-stream','--format','{{json .}}',*CONTAINERS], 'jsonl'),
        'host': lambda: command(['powershell','-NoProfile','-NonInteractive','-Command',HOST], 'json'),
        'guest': lambda: command(['docker','exec',AI,'python','-c',GUEST,str(run_id)], 'json'),
    }
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {key: pool.submit(action) for key, action in tasks.items()}
        return {'at': datetime.now(timezone.utc).isoformat(), **{key: future.result() for key, future in futures.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=int, required=True)
    parser.add_argument('--run', type=UUID, required=True)
    parser.add_argument('--samples', type=int, default=12)
    parser.add_argument('--interval', type=float, default=10)
    args = parser.parse_args()
    if args.job <= 0 or not 1 <= args.samples <= 360 or not 5 <= args.interval <= 300:
        parser.error('Use a positive job, 1–360 samples and a 5–300 second interval.')
    directory = REPO / '.local/hybrid/diagnostics'
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f'job-{args.job}-{datetime.now().strftime("%Y%m%d-%H%M%S")}.jsonl'
    print(f'Diagnostic log: {output}', flush=True)
    with output.open('x', encoding='utf-8') as stream:
        for index in range(args.samples):
            started = time.monotonic()
            row = sample(args.job, args.run)
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            print(json.dumps({'sample':index+1,'job':row['job'],'gpu':row['gpuCsv'],'host':row['host']}, ensure_ascii=False), flush=True)
            if index + 1 < args.samples:
                time.sleep(max(0, args.interval - (time.monotonic() - started)))


if __name__ == '__main__':
    main()
