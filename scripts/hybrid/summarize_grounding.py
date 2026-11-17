"""Generate a Grounding DINO experiment report from preserved JSONL observations."""
import argparse
import json
from pathlib import Path
import statistics


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args=parser.parse_args()
    path=args.directory
    manifest, summary=read(path/'manifest.json'),read(path/'summary.json')
    rows=[json.loads(x) for x in (path/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    completed=[row for row in rows if row['event']=='completed']
    modes=list(summary['timings'])
    totals={mode:{key:sum(row[key] for row in completed if row['mode']==mode)
                  for key in ('wall_ms','image_processor_calls','image_processor_ms','forward_calls',
                              'forward_host_ms','to_cpu_calls','to_cpu_ms','to_device_ms','postprocess_ms')}
            for mode in modes}
    expected=manifest['images']*manifest['repeats']*len(modes)
    unique=len({(row['mode'],row['repeat'],row['image']) for row in completed})
    result={'expected_observations':expected,'observations':len(completed),'unique_observations':unique,
            'complete':len(completed)==unique==expected and summary['status']=='completed', 'totals':totals,
            'quality_scope':'exact 2D detector output regression; not ground-truth accuracy or end-to-end 3D quality'}
    lines=['# Grounding DINO — '+('G0 호출 구조 진단' if manifest['diagnostic'] else 'G1 전처리 재사용 비교'),'',
        '## 문제 정의와 해결 후보','',
        '기존 VESPA에서 가장 오래 걸린 검출 단계가 같은 이미지를 후보 클래스마다 다시 전처리하고 추론한다. 먼저 실제 호출 횟수를 확인한 뒤, 이미지 전처리를 한 번 계산해 각 클래스에 재사용하는 변경만 비교한다.', '',
        '## 도구 선택 이유','',
        '- 설치된 Transformers pipeline: 현재 서비스와 동일한 모델·후처리·라벨 매핑을 유지하기 위해 선택.',
        '- image_processor proxy와 PyTorch forward hook: 겉 API 호출 수가 아닌 실제 내부 호출 수를 계수.',
        '- context manager: 실험 종료·예외 때 monkey patch와 hook을 복원하여 다음 조건에 변경이 남지 않도록 함.',
        '- unittest: 실제 설치 image processor와 원본 preprocess의 텐서 동등성·청크 분리·예외 복원을 검증. VESPA 환경에 pytest가 없어 표준 라이브러리로 실행.',
        '- JSONL과 입력/소스 SHA256: 이미지·반복·조건별 결과 및 실행 코드를 재현 가능하게 보존.', '',
        '## 고정 조건','',
        f"- 모델 `{manifest['model']}` revision `{manifest['model_commit']}`.",
        f"- {manifest['scene']}, {manifest['frames']}키프레임 × 6카메라 = {manifest['images']}장, 조건별 {manifest['repeats']}회.",
        f"- threshold {manifest['threshold']}, 후보 {len(manifest['labels'])}개, {manifest['dtype']}, CPU 스레드 {manifest['threads']}.",
        f"- PyTorch {manifest['torch']}, Transformers {manifest['transformers']}, CUDA {manifest['cuda']}, {manifest['gpu']}.",
        f"- diagnostic={manifest['diagnostic']}. {'forward마다 CUDA 동기화와 event 측정: 속도 채택용 결과와 구분.' if manifest['diagnostic'] else 'forward마다 강제 동기화 없음. 호출 계수 hook은 양쪽에 동일 적용.'}",
        '- 기존 모델·데이터 캐시. 조건마다 같은 첫 이미지 warmup, 반복마다 순서 교대. OS page cache는 통제하지 않음.',
        '- 이미지 파일 디코딩은 이미지별 wall_ms 바깥. pipeline 내부 전처리부터 결과 반환까지 포함. 모델 로드·warmup은 별도 이벤트.',
        '- 검출만 실행. SAM·3D 처리·RDS·S3·웹 요청은 이 측정에 포함되지 않음.', '',
        '## 측정 결과','', '| 조건 | 완료 이미지 호출 | 이미지 전처리 | 모델 forward | CPU 복사 | 반복 합계(초) |', '|---|---:|---:|---:|---:|---|']
    for mode in modes:
        values=summary['timings'][mode]; t=totals[mode]
        times=', '.join(f'{value/1000:.3f}' for value in values['repeat_total_ms'])
        lines.append(f"| {mode} | {values['images']} | {t['image_processor_calls']} | {t['forward_calls']} | {t['to_cpu_calls']} | {times} |")
    lines += ['', f"기록 검증: 예상 {expected}건 / 관측 {len(completed)}건 / 고유 (조건·반복·이미지) {unique}건.", '',
              '| 조건 | 전처리 합(초) | forward host 합(초) | CPU 복사 합(초) | 최대 allocated GiB |', '|---|---:|---:|---:|---:|']
    for mode in modes:
        t=totals[mode]; peak=max(row['peak_allocated_bytes'] for row in completed if row['mode']==mode)/1024**3
        lines.append(f"| {mode} | {t['image_processor_ms']/1000:.3f} | {t['forward_host_ms']/1000:.3f} | {t['to_cpu_ms']/1000:.3f} | {peak:.3f} |")
    lines += ['', 'host forward 시간은 비동기 CUDA 완료 시간과 다르다. CPU 복사에는 대기·변환이 포함될 수 있다. 하위 구간을 총량과 합산하지 않는다. allocated는 이 프로세스 기준이며 GPU 전체 사용량과 다르다.', '', '## 품질과 판정', '']
    if 'regression' in summary:
        regression=summary['regression']
        base=summary['timings']['baseline']['repeat_total_ms']; reuse=summary['timings']['reuse']['repeat_total_ms']
        reduction=1-statistics.median(reuse)/statistics.median(base)
        exact=regression['exact_output_matches']==regression['pairs']==manifest['images']*manifest['repeats']
        result.update(exact_regression_passed=exact, regression=regression,
                      median_repeat_wall_reduction=reduction,
                      repeat_wall_reductions=[1-b/a for a,b in zip(base,reuse)],
                      decision='candidate_pending_full_scene_validation' if result['complete'] and exact and reduction>0 else 'not_accepted')
        lines += [f"- 박스 좌표·점수·클래스·순서의 완전 일치: **{regression['exact_output_matches']}/{regression['pairs']}쌍**.",
            f"- 반복 전체 시간 중앙값 감소: **{reduction*100:.2f}%**. 개별 반복 감소율: "+', '.join(f'{x*100:.2f}%' for x in result['repeat_wall_reductions'])+'.',
            '- 동일 입력에 대한 검출 출력 회귀이며 정답 정확도(mAP) 검증을 대신하지 않음.',
            f"- 판정: `{result['decision']}`. 운영 기본값은 변경하지 않음.",
            '- 전체 씬·최종 3D 결과와 종료/재시도 동작을 검증한 뒤 채택 여부를 결정. 클래스 batching·프롬프트 통합·dtype 변경은 별도 실험으로 분리.']
    else:
        result['decision']='diagnosis_only'
        lines += ['- 진단 결과로 실제 호출 횟수를 확인. 이 수치로 최적화 전후 개선율을 계산하지 않음.',
                  '- 다음 실험은 클래스별 추론·CPU 복사를 유지하고 이미지 전처리 재사용 하나만 변경.']
    lines += ['', '## 원본 로그와 재현', '',
        '`command.txt`, `stdout.log`, `stderr.log`, `exit-code.txt`, `manifest.json`, `events.jsonl`, `summary.json`, `comparison-summary.json` 보존. G1은 `test-conditions.json`과 30초 간격 `resources.jsonl`도 보존한다. G0은 이미지별 CUDA peak를 기록했으며 별도 호스트 자원 샘플은 수집하지 않았다.', '']
    (path/'comparison-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (path/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({key:value for key,value in result.items() if key!='totals'},ensure_ascii=False))


if __name__=='__main__':
    main()
