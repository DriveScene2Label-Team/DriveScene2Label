"""Build case reports from recorded results, including rejected candidates."""
import argparse
import json
from pathlib import Path
from evidence_io import save_json


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def thread(root):
    decision=read(root/'thread-scene-decision.json')
    quality=read(root/'scene-quality-with-gt.json')
    lines=['# T4: CPU 스레드 전체 씬 검증', '',
        '| 항목 | 결과 |', '|---|---|',
        f"| 과거 1스레드 / 새 2스레드 | {decision['wall_seconds']['baseline']:.3f} / {decision['wall_seconds']['reuse']:.3f}초 |",
        f"| 234개 검출 완전 일치 | {quality['detector_regression']['exact']} |",
        f"| 최종 3D 완전 일치 | {quality['output_regression']['exact']} |",
        f"| GT 계산 결과 일치 | {quality['ground_truth_regression']['exact']} |", '',
        '결정: 전체 결과 보존 기준 미달로 운영 native 스레드 1 유지. 시간 비교는 과거 기준선이므로 인과적 개선율을 주장하지 않는다.', '',
        '39프레임·1,308박스 중 한 박스의 9개 수치가 달랐다. 검출·GT 요약 지표가 같아도 모든 3D 필드가 같다는 뜻은 아니다. 스레드 수에 따른 중간 연산 차이의 발생 지점은 추가 분리가 필요하며 원인을 단정하지 않는다.', '',
        '차이 목록은 `scene-quality-with-gt.json`의 `output_regression.first_differences`, 원본은 `baseline/final-result.json`과 `reuse/final-result.json`에 보존했다.']
    return lines


def variants(root):
    value=read(root/'variant-comparison.json')
    lines=['# A2 / P1–P3: Grounding Attention·정밀도', '',
        '동일 6카메라·10클래스·60 forward, seed 42, native 스레드 1. 각 모드 3회 교차 순서의 새 프로세스. 로딩·warmup은 처리 시간에서 제외한다.', '',
        '| 모드 | 완료 반복 | 검출 중앙값 초 | 최대 할당 VRAM MiB | FP32와 출력 완전 일치 |', '|---|---:|---:|---:|---|']
    for name,row in value['aggregate'].items():
        seconds=f"{row['median_seconds']:.3f}" if 'median_seconds' in row else '측정 없음'
        memory=f"{row['peak_allocated_bytes']/1024**2:.1f}" if 'peak_allocated_bytes' in row else '—'
        exact='기준' if name=='fp32' else row.get('exact_outputs','—')
        lines.append(f"| {name} | {row['completed_repeats']} | {seconds} | {memory} | {exact} |")
    lines+=['', '## 실제 실패·미지원 시도', '']
    for case in value['cases']:
        if case['status']=='failed_or_unsupported':
            lines.append(f"- `{case['case']}`: exit {case['exit_code']}; 해당 폴더의 events.jsonl / detector.stderr.log 보존. 성공 실행 시간으로 계산하지 않음.")
    lines+=['', '## 출력 차이', '']
    for check in value['quality_checks']:
        geo=check['geometry'];reg=check['output_regression']
        lines.append(f"- {check['name']} 반복 {check['repeat']}: exact={reg['exact']}, 클래스별 개수 일치={geo['same_per_image_class_counts']}, 누락/추가={geo['unmatched_reference']}/{geo['unmatched_candidate']}, 최소 matched IoU={geo['minimum_matched_iou']}, 최대 score 차이={geo['maximum_matched_score_difference']}.")
    lines+=['', '결정: 운영 dtype/attention 유지. 작은 입력의 속도·greedy IoU는 전체 씬 3D/GT 품질이나 mAP를 대체하지 않는다. 출력이 달라지는 정밀도는 후속 정확도 허용 기준과 다중 씬 검증이 필요하다. INT8/INT4 calibration·양자화는 이 FP16/BF16 시험과 다르며 이번에 실행하지 않았다.']
    return lines


def runtime(root):
    value=read(root/'runtime-probe-result.json')
    lines=['# R1 / R2: 실제 Grounding ONNX·추론 엔진 호환성', '',
        '동일 HF checkpoint의 실제 한 카메라·`car.` 입력으로 수행한 고정 shape probe다. 전처리는 graph 밖이다. production pip 환경과 서빙 모델은 변경하지 않았다.', '',
        '## 단계별 실행', '']
    for row in value['cases']:lines.append('- '+json.dumps(row,ensure_ascii=False))
    if (root/'user-interruption.json').exists():
        lines+=['', '**사용자 요청으로 GPU 컨테이너를 중지했다. TensorRT exit 137은 빌드 중 사용자 중단이며 OOM·엔진 성능 실패의 근거가 아니다. 완성된 엔진·추론 시간·품질 결과는 없다.**']
    for file in sorted(root.glob('*/*-failure.json')):
        item=read(file);lines+=['', f"### {file.parent.name}/{file.name}", '', f"`{item['type']}`: {item['message']}"]
    for file in sorted(root.glob('*/*-result.json')):
        item=read(file)
        if 'median_seconds' in item:
            lines+=['', f"- {file.parent.name}/{file.name}: median={item['median_seconds']:.6f}초; raw 출력 품질={item.get('quality',{}).get('passed')}. 전체 class·동적 shape·full-scene 검증은 아님."]
            if 'profile_node_provider_counts' in item:
                lines.append('  실제 profile node 이벤트의 provider 분포: '+json.dumps(item['profile_node_provider_counts'])+'. 개수가 실행시간 비중을 뜻하지 않는다.')
    for file in sorted(root.glob('*/pytorch-timing.json')):
        item=read(file);lines+=['', f"- {file.parent.name} PyTorch 기준: {item['median_seconds']:.6f}초, {item['repetitions']}회, {item['boundary']}."]
    for file in sorted(root.glob('diagnostic-*.json')):
        item=read(file);lines+=['',f"- {file.name}: raw 슬롯 비교={item['raw_slot_parity']}, thresholded 박스 기준/후보={item['reference_count']}/{item['candidate_count']}, 누락/추가={item['missing']}/{item['extra']}, 최소 matched IoU={item['minimum_matched_iou']}, 최대 score 차이={item['maximum_matched_score_difference']}."]
    lines+=['', '엔진 export/parse 실패는 배포나 속도 향상으로 계산하지 않는다. 성공하더라도 host→GPU→host raw forward 경계이며 서버 HTTP·SAM·3D 파이프라인과 구분한다. 공식 TAO 경로는 참고 자료이며 다른 checkpoint로 바꾼 수치를 같은 모델의 엔진 개선으로 표현하지 않는다.']
    return lines


def s3(root):
    value=read(root/'s3-transfer-experiment.json')
    lines=['# S2: S3 전송 병렬도', '',
        f"동일 {value['source_bytes']:,}바이트 파일, SHA256 `{value['source_sha256']}`. 각 모드 3회 교차 반복. 해시 계산은 시간 밖이며 전송 전후 전체 byte 검증.", '',
        '| 모드 | 업로드 중앙값 초 | 다운로드 중앙값 초 |', '|---|---:|---:|']
    for mode,row in value.get('medians',{}).items():lines.append(f"| {mode} | {row['upload']:.3f} | {row['download']:.3f} |")
    lines+=['', f"실행 상태: {value['status']}. 생성 객체 {len(value['created'])}개, 삭제 확인 {sum(c['deleted'] for c in value['created'])}개, cleanup 오류 {len(value['cleanup_errors'])}개.", '',
        'stream은 단일 PUT/GET, mp1/mp2/mp4는 16MiB multipart 및 Range download를 concurrency 1/2/4로 실행한다. max connection pool 8, connect/read timeout 5/60초, 최대 3회 표준 retry다. 요청·재시도는 s3-requests.jsonl에 남기며 credential·서명·HTTP header는 기록하지 않는다.', '',
        '범위: Python SDK 전송 실험이다. Java 서비스 전체 업로드가 이만큼 개선됐다는 뜻은 아니며 4.168GB 원본·실제 Java adapter·메모리 및 장애 복구 검증 후 적용해야 한다. 기존 S3 원본·RDS 데이터는 보존한다.']
    return lines


def query(root):
    value=read(root/'query-comparison.json')
    lines=['# Q2: 기존 RDS exact 검색 쿼리', '',
        f"저장된 이미지 벡터 3개 × dataset/global × MAX/AVERAGE/TOP_K_AVERAGE × 3쌍. 총 {value['pairs']}쌍의 모든 정렬된 SQL 결과 필드 일치: {value['quality_passed']}.", '',
        '단 하나의 변경은 distances CTE의 AS MATERIALIZED다. readonly transaction·statement timeout을 사용했으며 extension·index·schema·공유 통계는 변경하지 않았다. warmup 뒤 교차 순서로 client 경과시간을 측정하고 별도의 EXPLAIN ANALYZE BUFFERS로 server 시간과 I/O를 확인했다.', '',
        '| 시나리오 | 기준/후보 client 중앙값 ms | 기준/후보 server 실행 ms |', '|---|---:|---:|']
    for row in value['scenarios']:
        b=row['modes']['baseline'];c=row['modes']['materialized']
        lines.append(f"| {row['scenario']} | {b['client_median_seconds']*1000:.2f} / {c['client_median_seconds']*1000:.2f} | {b['server_execution_ms']:.2f} / {c['server_execution_ms']:.2f} |")
    lines+=['', '서버 값은 각 시나리오별 별도 EXPLAIN 1회이며 client 중앙값의 구성 항목으로 빼거나 더하지 않는다. 텍스트 임베딩·HTTP 전체 검색 시간은 포함하지 않는다. materialization은 반복 거리 연산을 줄일 수 있지만 buffer/임시 저장·실행 계획 비용이 커질 수 있어 결과를 보고 적용 여부를 정한다. global image top-k를 앞에 넣는 HNSW 치환은 씬 집계 의미가 달라 별도 recall 검증이 필요하다.', '',
        '전체 계획은 query-output/*-plan.json에 로컬 보존한다. vector literal은 Git에서 제외하고 query-comparison.json에 허용한 plan 필드만 공유한다.']
    return lines


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('kind',choices=('thread','variants','runtime','s3','query'))
    p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
    lines=globals()[a.kind](a.directory)
    path=a.directory/'report.md'
    if path.exists() and not (a.directory/'report-stage-timings.md').exists():
        (a.directory/'report-stage-timings.md').write_bytes(path.read_bytes())
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'kind':a.kind,'report':str(path)},ensure_ascii=False))


if __name__=='__main__':main()
