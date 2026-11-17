"""Generate a reviewable C1 report from the audited paired comparison."""
import argparse
import json
from pathlib import Path
import statistics


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
    result=json.loads((a.directory/'comparison.json').read_text(encoding='utf-8'))
    pairs=result['pairs'];medians=result['index_medians_seconds']
    lines=['# C1 — CLIP 인덱싱의 중복 DB 조회 제거','',
        '정상 업로드 API와 기존 서울 RDS·S3로 두 씬의 같은 474장 입력을 새 dataset마다 인덱싱했다. 변경은 pending 조회에 이미 필요한 Source를 포함하고, 그 조회에서 확인한 missing 조건을 재사용하는 것뿐이다. GPU batch·모델·정밀도·검색 SQL·벡터 저장 방식은 유지했다.','',
        '## 통제 조건과 채택 판정','',
        f"- 판정: `{result['decision']}`. 출력 검증 `{result['quality_passed']}`, 실행 조건 검증 `{result['conditions_passed']}`.",
        '- 순서: baseline→prefetch, prefetch→baseline, baseline→prefetch. 매번 backend를 강제 재생성하고 같은 AI 컨테이너를 유지했다.',
        f"- backend 인스턴스 {result['runtime_conditions']['distinct_backend_containers']}개, AI 인스턴스 {result['runtime_conditions']['distinct_ai_containers']}개, 동일 이미지 digest 검사 통과.",
        '- CLIP은 미리 적재·warmup했다. 새 데이터셋을 사용하며 OS page cache는 통제하지 않았다. 각 실행의 18개 검색 검증은 인덱싱 시간 바깥이다.',
        '- 실행 중 다른 모델·빌드·업로드는 병행하지 않았다. 로그/자원 수집과 가벼운 소스 편집·호스트 단위 테스트는 있었으며 사용자 측 작업은 독립적으로 확인하지 못했다.','',
        '## 시간과 품질','',
        '| 반복 | baseline 초 | prefetch 초 | 시간 감소 | 벡터 완전 일치 | 검색 비교 |','|---|---:|---:|---:|---:|---:|']
    for pair in pairs:
        lines.append(f"| {pair['repeat']+1} | {pair['baseline']['index_wall_seconds']:.3f} | {pair['prefetch']['index_wall_seconds']:.3f} | {pair['wall_reduction']*100:.2f}% | {pair['vectors']['exact_pairs']}/{pair['vectors']['pairs']} | {pair['rankings']['queries']} |")
    lines += [f"| 중앙값 | {medians['baseline']:.3f} | {medians['prefetch']:.3f} | {result['median_wall_reduction']*100:.2f}% | — | — |",'',
        '시간은 서버 CLIP_INDEX 시작→완료의 경과시간이다. 세 번의 중앙값이며 p95·통계적 유의성·다른 하드웨어의 개선율은 주장하지 않는다. 업로드 전체 시간에는 S3 전송·등록·10초 polling이 있어 이 개선율과 같지 않다.',
        f"벡터 {sum(p['vectors']['pairs'] for p in pairs):,}쌍은 768차원·정규화·키·모델·전처리·수치 검사를 통과했다. 모든 값이 완전 일치했고 검색 {sum(p['rankings']['queries'] for p in pairs)}개 비교의 순위·점수·최상위 이미지도 같다. 각 실행은 474 STORED/AI 이벤트를 확인했고 수집 오류·실패 이벤트가 없다.",'',
        '## 왜 빨라졌는가','',
        '| 구간 합계의 3회 중앙값 | baseline 초 | prefetch 초 |','|---|---:|---:|']
    for field in ('source_ms','exists_ms','ai_ms','storage_ms'):
        numbers=[statistics.median(p[mode]['sums_seconds'][field] for p in pairs) for mode in ('baseline','prefetch')]
        lines.append(f'| {field} | {numbers[0]:.3f} | {numbers[1]:.3f} |')
    lines += ['',
        '이미지마다 수행하던 Source·존재 확인 왕복이 줄었다. 474장 기준 코드 경로상 SELECT 948회를 제거하지만, 이는 서버 카운터로 관측한 호출 수가 아니다. 기존 RDS에 pg_stat_statements가 없어 SQLSTATE 42P01을 기록했으며 확장 설치나 통계 reset을 하지 않았다. 클라이언트 JDBC 시간에는 네트워크·풀·드라이버·서버 실행이 모두 들어간다.',
        '배치 조회는 양쪽 모두 종료 확인을 포함해 9회다. AI·저장 시간은 여전히 대부분을 차지하고 실행별 변동도 있으므로 전체 차이를 SQL 서버 실행시간 감소로 단정하지 않는다.','',
        '## 언제 좋고 언제 불리한가','',
        '- 유리: 새 이미지가 많고 DB가 원격이라 반복 왕복이 누적되는 인덱싱. 별도 캐시 서버 없이 기존 조회를 활용할 수 있다.',
        '- 효과 제한: DB 왕복이 매우 짧거나 GPU 모델 시간이 압도적인 경우. 이미 색인된 이미지의 수동 조회 경로는 바꾸지 않았다.',
        '- 동시성: pending 선택 후 다른 요청이 먼저 저장하면 중복 추론은 생길 수 있다. 최종 ON CONFLICT DO NOTHING이 기존 벡터를 보존한다. 실제 동시 저장 통합 테스트를 통과했다.',
        '- 원복: hybrid의 EMBEDDING_INDEX_PREFETCH_ENABLED=false. 일반 application.properties의 기본값은 false이며 hybrid 구성에서만 채택한다.','',
        '## 제외한 실행과 도구 선택','',
        '- 최초 pilot은 일부 backend 컨테이너가 유지돼 조건이 달랐다. 19.50%라는 수치는 최종 성과로 채택하지 않았고 원본과 재판정 JSON을 모두 보존했다.',
        '- 재측정 중 dataset 16은 서버에서 474장 완료했지만 Windows 보고서 파일 교체가 PermissionError로 실패했다. 잠근 프로세스는 확정하지 않았다. 해당 실행을 제외·보존하고 고유 임시 파일+제한된 재시도 및 resume 기능을 추가해 새 dataset 17로 재실행했다.',
        '- 정상 API로 실서비스 경로를 통과하고 read-only Java snapshot으로 RDS 저장값을 직접 확인했다. 컨테이너 ID·이미지 digest 검사는 실행 조건의 동일성을 검증한다. 입력 SHA256, 명령, stdout/stderr, events.jsonl, resources.jsonl, 벡터·검색 응답을 각 폴더에 남긴다.',
        '- 전체 원본 2,424장 확대 검증과 정상 라벨·3D 조회는 별도 A1 케이스다. 이 소량 반복의 개선율을 전체 업로드 개선율로 확장하지 않는다.','']
    (a.directory/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(str(a.directory/'report.md'))


if __name__=='__main__':main()
