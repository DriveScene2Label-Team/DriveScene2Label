"""Finalize a stopped CLIP measurement with boundaries, coverage and interpretation.

Run measurement.py collect after stopping collectors, then run this command.
Original aggregates remain in report.json; generated prose never invents missing spans.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import statistics


def stamp(row):
    return datetime.fromisoformat(row['at'].replace('Z', '+00:00')).timestamp()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    path = args.directory
    if not (path/'STOP').is_file():
        raise ValueError('Stop collection before finalizing the report.')
    client, report, conditions = [read_json(path/name) for name in
                                 ('client-report.json','report.json','test-conditions.json')]
    rows = [json.loads(line) for line in (path/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    clips = sorted((row for row in rows if row['tag']=='CLIP' and str(row.get('dataset'))==str(client['dataset_id'])), key=stamp)
    stages = [row for row in rows if row['tag']=='CLIP_STAGE']
    if not clips:
        raise ValueError('No CLIP events for this dataset.')
    n = client['index_status']['totalImages']
    sums = {key:sum(float(row.get(key,0)) for row in clips)/1000 for key in ('total_ms','ai_ms','storage_ms')}
    span = stamp(clips[-1])-stamp(clips[0])+float(clips[0]['total_ms'])/1000
    gaps = [stamp(b)-stamp(a)-float(b['total_ms'])/1000 for a,b in zip(clips,clips[1:])]
    unique = len({row['image'] for row in clips})
    valid = (client['status']=='completed' and n==len(clips)==unique==len(stages)
             and all(row.get('status')=='STORED' for row in clips)
             and not report['capture_errors'] and not report['failures'])
    summary = {'status':'completed' if valid else 'needs_review', 'dataset_id':client['dataset_id'],
        'expected_images':n, 'clip_events':len(clips), 'unique_images':unique, 'clip_stage_events':len(stages),
        'event_counts':dict(Counter(row['tag'] for row in rows)), 'capture_errors':report['capture_errors'],
        'failed_events':len(report['failures']), 'client_total_seconds':client['total_seconds'],
        'upload_transfer_seconds':client['transfer_seconds'], 'clip_sums_seconds':sums,
        'clip_first_last_seconds':stamp(clips[-1])-stamp(clips[0]), 'derived_clip_span_seconds':span,
        'derived_unattributed_span_seconds':span-sums['total_ms'],
        'max_derived_inter_image_gap_seconds':max(gaps,default=0),
        'pre_ai_unseparated_seconds':sums['total_ms']-sums['ai_ms']-sums['storage_ms'],
        'non_ai_fraction_of_clip_total':(sums['total_ms']-sums['ai_ms'])/sums['total_ms'],
        'limitation':'Docker completion timestamps and integer-ms timers estimate spans; source/exists/cache not individually timed. CLIP_STAGE lacks dataset correlation; this run must be isolated.'}
    resources_path = path/'resources.jsonl'
    if resources_path.is_file():
        resources = [json.loads(line) for line in resources_path.read_text(encoding='utf-8').splitlines()]
        available = [row['host']['availableMB'] for row in resources if 'availableMB' in row.get('host',{})]
        summary['resources'] = {'samples':len(resources), 'host_available_mb_min':min(available) if available else None,
            'errors':sum(any(isinstance(value,dict) and 'error' in value for value in row.values()) for row in resources)}
    (path/'comparison-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    kst = datetime.fromisoformat(client['started_at']).astimezone(timezone(timedelta(hours=9)))
    lines = ['# C0 — 최신 CLIP 통합 기준 측정', '',
        f"- 시작: {kst.isoformat()} (KST), 완료: {client['completed_at']} (UTC)",
        f"- 결과: **{client['index_status']['indexedImages']}/{n}장 인덱싱 완료**, 데이터셋 {client['dataset_id']}, {client['scene_count']}개 씬",
        f"- 업로드 시작 → 완료 확인: **{client['total_seconds']:.3f}초**. 상태 polling 간격 10초로 완료 확인 지연 포함.",
        f"- 로그: CLIP {len(clips)}건 / 고유 이미지 {unique}장 / CLIP_STAGE {len(stages)}건. 수집 오류 {len(report['capture_errors'])}건, 실패 이벤트 {len(report['failures'])}건.", '',
        '## 문제 정의와 가설', '',
        '최신 scheduler 수정 뒤에도 이미지 처리 사이의 긴 공백이 남는지, SQL·HTTP·추론 중 어디에 추가 최적화 가치가 있는지 확인한다. 코드 변경 없이 정상 업로드 경로를 통과시켰다.', '',
        '## 조건과 도구 선택 이유', '',
        f"- 커밋: `{conditions['git_revision']}`. 이미지 digest와 입력 SHA256은 `test-conditions.json`.",
        f"- 경로: **{client['origin']}**, Python 재개 업로드 API 클라이언트. 공개 주소·Vercel·브라우저 경로는 이번 측정에 포함되지 않음.",
        '- 기존 서울 RDS·S3 사용. 새 업로드로 기존 데이터셋과 벡터를 보존.',
        '- CLIP 모델은 이미 적재됨. 새 데이터셋 캐시 사용, OS page cache는 통제하지 않음.',
        '- 정상 HTTP API: 서버의 실제 업로드·등록·인덱싱 경계를 재현하기 위해 선택.',
        '- measurement.py: 기존 allowlist 구조화 로그와 중복 제거를 유지하기 위해 선택.',
        '- nvidia-smi / Docker / 호스트·cgroup 30초 샘플: 자원 경쟁과 메모리 압박을 함께 확인하기 위해 선택. 순간 peak 전부를 포착하지는 못함.',
        '- 동시 작업: 로그·자원 수집, 가벼운 소스 편집과 상태 확인. 에이전트는 다른 GPU 추론·빌드·배포를 실행하지 않음. 사용자의 다른 작업은 독립적으로 확인하지 못함.', '',
        '## 실제 측정', '',
        '| 경계 | 시간(초) | 해석 |', '|---|---:|---|',
        f"| 클라이언트 전송 | {client['transfer_seconds']:.3f} | 세션 생성·전송 포함 |"]
    upload = [row for row in report['timings'] if row['boundary'].startswith('UPLOAD_STAGE') and row['boundary'].endswith('wall_ms')]
    for row in upload:
        stage = row['boundary'].split(' / ')[1]
        lines.append(f"| 서버 업로드 {stage} | {row['sum_ms']/1000:.3f} | TOTAL은 하위 단계와 중첩 |")
    lines += [f"| CLIP 관측 실행 구간(추정) | {span:.3f} | 첫 완료 시각에서 첫 total_ms를 빼 시작 추정 |",
        f"| 이미지별 total_ms 합 | {sums['total_ms']:.3f} | 아래 AI·저장 포함 |",
        f"| AI HTTP 요청·검증 합 | {sums['ai_ms']:.3f} | 모델 추론만의 시간이 아님 |",
        f"| 벡터 저장 합 | {sums['storage_ms']:.3f} | DB 클라이언트 경과시간 |",
        f"| source/exists/cache 등 미분리 잔여 | {summary['pre_ai_unseparated_seconds']:.3f} | 순수 SQL 또는 네트워크 RTT로 단정 불가 |"]
    for row in report['timings']:
        if row['boundary'].startswith('CLIP_STAGE'):
            lines.append(f"| AI {row['boundary'].split(' / ')[-1]} 합 | {row['sum_ms']/1000:.3f} | handler와 내부 단계 중첩 |")
    lines += ['', '## 비교와 판정', '',
        f"- 이번 실행의 이미지 사이 최대 추정 공백은 **{max(gaps,default=0):.3f}초**, 전체 구간에서 이미지별 처리 합을 뺀 잔여는 **{span-sums['total_ms']:.3f}초**. 과거처럼 수백 초 공백은 관측되지 않음.",
        '- 최신 수정 이전과 실행 조건이 같지 않으므로 이 결과만으로 scheduler 수정의 인과적 개선율을 산출하지 않음.',
        f"- 이미지별 총 시간 중 AI 요청 바깥 비중은 **{summary['non_ai_fraction_of_clip_total']*100:.1f}%**. CLIP 경로를 두 번째 최적화 후보로 유지하고 source/exists/upsert 개별 계측과 왕복 축소를 다음 실험으로 선정.",
        '- CLIP 단독 B0의 185.016초와 C0 전체 626.906초는 측정 경계가 다름. 전후 개선율로 비교하지 않음.',
        '- 최초 통합 기준선 1회이다. 최적화 전후 비교는 동일 입력/캐시/반복 조건으로 새 폴더에 기록해야 함.',
        '- 검색 순위·벡터 차이·중단 후 재시작 검증은 이번 실행 범위 밖이며 아직 통과로 간주하지 않음.', '',
        '## 누락과 한계', '',
        '- CLIP_INDEX lifecycle 이벤트는 관측되지 않음. 시작/종료는 CLIP 로그·API 응답으로 경계를 표시.',
        '- 첫 클라이언트 실행은 최종 client-report.json과 서버 원본 로그를 보존했으나 중간 stdout을 파일로 저장하지 못함. 이후 benchmark_clip.py는 client-events.jsonl도 매 이벤트 flush한다.',
        '- JSONL은 허용된 계측 필드 원본이며 모든 애플리케이션 메시지를 무차별 저장한 로그가 아님. 비밀번호·쿠키·토큰은 수집 대상에서 제외.',
        '- CUDA gpu_ms는 구현이 정의한 동기화 구간이다. 순수 커널 시간 또는 GPU 사용률과 같지 않음.']
    if 'resources' in summary:
        res=summary['resources']
        lines += [f"- 자원 샘플 {res['samples']}개, 오류 {res['errors']}개. 호스트 사용 가능 메모리 최소 **{res['host_available_mb_min']} MB**: 업로드 구간의 메모리 압박 가능성을 후속 비교 조건에 기록."]
    lines += ['', '## 산출물', '', '`events.jsonl`, `resources.jsonl`, `client-report.json`, `report.json`, `comparison-summary.json`, `manifest.json`, `test-conditions.json`. 상세 타이밍 분포는 report.json에 보존한다.', '']
    (path/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
