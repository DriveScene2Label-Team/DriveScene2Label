"""Combine two CPU microbenchmarks without presenting them as a full scene test."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from evidence_io import save_json


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def summarize_cases(cases):
    if sorted((c['repeat'], c['threads']) for c in cases) != [(r,t) for r in range(3) for t in (1,2,4)]:
        raise ValueError('Expected exactly three repeats for each thread limit')
    return {str(t): {field: statistics.median(c[field] for c in cases if c['threads']==t)
                     for field in ('wall_seconds','cpu_seconds','voluntary_context_switches',
                                   'involuntary_context_switches','model_load_seconds','command_wall_seconds')}
            for t in (1,2,4)}


def resource_summary(directory):
    rows=[json.loads(line) for line in (directory/'resources.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    guests=[r['guest'] for r in rows if isinstance(r.get('guest'),dict) and 'memory.events' in r['guest']]
    hosts=[r['host']['availableMB'] for r in rows if isinstance(r.get('host'),dict) and 'availableMB' in r['host']]
    def counter(row, name):
        return int(dict(line.split() for line in row['memory.events'].splitlines())[name])
    def pressure(row,name):
        return float(row[name].split('avg10=')[1].split()[0])
    return {'samples':len(rows),'valid_guest_samples':len(guests),
            'host_available_mb_min':min(hosts) if hosts else None,
            'oom_kill_delta':counter(guests[-1],'oom_kill')-counter(guests[0],'oom_kill') if guests else None,
            'max_sampled_memory_some_avg10':max(pressure(r,'memory.pressure') for r in guests) if guests else None,
            'max_sampled_cpu_some_avg10':max(pressure(r,'cpu.pressure') for r in guests) if guests else None,
            'note':'30-second samples include model loading and warmup; not per-case causal attribution or unsampled peak.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--grounding-directory',type=Path,required=True)
    p.add_argument('--sam-directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    ground=read(a.grounding_directory/'thread-comparison.json')
    sam=read(a.sam_directory/'sam-thread-comparison.json')
    summaries={'grounding':summarize_cases(ground['cases']),'sam':summarize_cases(sam['cases'])}
    gates=[]
    for directory in (a.grounding_directory,a.sam_directory):
        if not (directory/'STOP').exists():raise ValueError('Wait for collection to finish')
        execution=read(directory/'execution-summary.json');report=read(directory/'report.json')
        gates.append(execution['exit_code']==execution['final_collect_exit_code']==0
                     and not execution.get('collector_errors') and not report['capture_errors'] and not report['failures'])
    # All cases must retain their implementation, model and input configuration.
    for experiment in (ground,sam):
        manifests=[c['manifest'] for c in experiment['cases']]
        fields=('source_sha256','config_sha256','inputs','torch','gpu')
        gates.append(all(all(m[k]==manifests[0][k] for k in fields) for m in manifests))
        gates.append(all(c['manifest']['torch_threads']==c['threads'] for c in experiment['cases']))
    combined={t:sum(s[t]['wall_seconds'] for s in summaries.values()) for t in ('1','2','4')}
    best=min(combined,key=combined.get)
    selected=min(int(t) for t,value in combined.items() if value<=combined[best]*1.05)
    passed=all(gates) and ground['quality_passed'] and sam['quality_passed']
    value={'created_at':datetime.now(timezone.utc).isoformat(),
           'scope':'separate six-image Grounding and fixed-box SAM medians; not total pipeline latency',
           'grounding_directory':str(a.grounding_directory),'sam_directory':str(a.sam_directory),
           'quality_passed':passed,'summaries':summaries,'combined_median_seconds':combined,
           'best_observed_threads':int(best),'candidate_threads':selected if passed else None,
           'predeclared_selection':'lowest thread count within 5% of best combined median; operational headroom criterion, not statistical significance',
           'decision':'keep threads=1' if passed and selected==1 else 'full-scene quality and wall-time gate required; no production change',
           'resources':{'grounding':resource_summary(a.grounding_directory),'sam':resource_summary(a.sam_directory)}}
    a.output.mkdir(parents=True,exist_ok=False);save_json(a.output/'comparison.json',value)
    lines=['# T3 CPU 스레드 제한 비교','',
        '동일 입력 6카메라를 각 설정 3회, 순서 1/2/4 → 4/1/2 → 2/4/1로 측정했다. 매번 새 프로세스이며 모델 로딩·warmup은 아래 단계 시간에서 제외했다. 원격 DB·S3·다른 GPU 작업은 함께 실행하지 않았다.','',
        '| 스레드 | Grounding 중앙값 초 | SAM 중앙값 초 | 단계 중앙값 합 초 | Grounding CPU 초 | SAM CPU 초 |',
        '|---|---:|---:|---:|---:|---:|']
    for t in ('1','2','4'):
        g=summaries['grounding'][t];s=summaries['sam'][t]
        lines.append(f"| {t} | {g['wall_seconds']:.3f} | {s['wall_seconds']:.3f} | {combined[t]:.3f} | {g['cpu_seconds']:.3f} | {s['cpu_seconds']:.3f} |")
    lines += ['',f"검출·전체 mask byte 해시 및 실행 조건 검사: **{'통과' if passed else '실패'}**.",
        f"사전 기준(최고 관측값의 5% 이내 중 최소 스레드) 후보: **{value['candidate_threads']}**. `{value['decision']}`.",
        '이 합은 별도 단계의 중앙값이며 실제 전체 씬 시간이 아니다. 3회·한 프레임의 결과를 전체 데이터나 p95 성능으로 확대하지 않는다.',
        '', '| 단계·스레드 | voluntary 중앙값 | involuntary 중앙값 | CPU/벽시계 비율 |', '|---|---:|---:|---:|']
    for name,summary in summaries.items():
        for t,row in summary.items():
            lines.append(f"| {name} / {t} | {row['voluntary_context_switches']:.0f} | {row['involuntary_context_switches']:.0f} | {row['cpu_seconds']/row['wall_seconds']:.2f} |")
    lines += ['', '문맥 전환 증가만으로 thrashing이라고 판정하지 않는다. 경과시간·CPU 사용량·메모리 pressure·OOM과 함께 판단한다. 자원 표본에는 모델 로딩 구간도 포함된다. inter-op/OpenCV 설정은 manifest에 기록하며 별도 변경하지 않았다.',
              '', '[판정·자원 요약 JSON](comparison.json). 실행별 manifest·원본 이벤트·stdout/stderr는 지정된 측정 폴더에 보존한다.','']
    (a.output/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:value[k] for k in ('quality_passed','combined_median_seconds','candidate_threads','decision')}))
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
