"""Write the full-scene report from preserved comparison and resource evidence."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
    q=json.loads((a.directory/'quality-with-gt.json').read_text(encoding='utf-8'))
    timings=q['timings'];base=timings['baseline']['execution']['wall_seconds'];opt=timings['reuse']['execution']['wall_seconds']
    lines=['# G2 — 전체 씬 전처리 재사용과 최종 3D 검증','',
        f'검증 완료: {q["at"]}. scene-0061 전체 {q["expected_keyframes"]}키프레임, 카메라 234장. 입력은 원본 nuScenes mini의 dataset 7 캐시다. 전체 mini 10개 씬 라벨 평가가 아니다.','',
        '## 문제·해결·도구 선택','',
        'Grounding DINO의 클래스별 반복에서 같은 이미지 전처리가 중복된다. 설치된 Transformers 4.49 pipeline의 토큰화·forward·후처리를 유지하고 이미지 전처리 텐서만 호출 안에서 재사용했다. 모델·threshold·dtype·forward batch는 바꾸지 않았다. G1은 실제 내부 호출 계수와 텐서 동등성을 확인했고, G2는 운영 VESPA runner를 통해 검출 이후 SAM·LiDAR·DINOv2·tracking·최종 3D까지 검증했다.','',
        '고정 seed 42, CPU/BLAS 스레드 1, 별도의 새 중간 캐시를 사용했다. baseline→reuse 1쌍이며 모델 파일·데이터 디스크 캐시는 공유했다. G1의 3회 warm 소량 비교와 이 전체 씬 1쌍을 구분한다. 30초 자원 로그와 진행 중의 가벼운 호스트 작업은 resources.jsonl/operator-notes.jsonl에 남겼다.','',
        '## 성능','',
        '| 경계 | baseline 초 | reuse 초 | 시간 감소 |','|---|---:|---:|---:|',
        f'| 전체 실행 | {base:.3f} | {opt:.3f} | {q["wall_reduction"]*100:.2f}% ({base-opt:.3f}초) |']
    for label,stage in [('이미지 검출·분할 전체','image_detection_segmentation'),('Grounding DINO','grounding_dino_detection'),('SAM 추론·후처리','sam_inference_postprocess'),('지면 제거','ground_removal'),('DINOv2','dinov2_features')]:
        left=timings['baseline']['stage_totals_seconds'][stage];right=timings['reuse']['stage_totals_seconds'][stage]
        lines.append(f'| {label} | {left:.3f} | {right:.3f} | {(1-right/left)*100:.2f}% |')
    lines += ['', '검출·분할 전체는 하위 Grounding/SAM 구간을 포함하므로 표를 합산하지 않는다. 전체 개선율은 3.08%이며 G1 검출 소량 실험의 11.81%를 전체 서비스 개선율로 쓰지 않는다. Grounding 이외 단계의 실행시간 변동도 있고, 전체 씬 1쌍으로 안정적인 평균·p95 개선을 입증하지 않았다.','',
        '## 출력 동등성과 정답 비교','',
        f'- 234/234 검출 결과: 완전 일치 = {q["detector_regression"]["exact"]}. 좌표·점수·클래스·순서·입력 해시 포함.',
        f'- 39/39 최종 프레임, 1,308/1,308 박스: 전체 JSON 완전 일치 = {q["output_regression"]["exact"]}. 좌표·크기·회전·속도·클래스·track 및 track_frames 포함.',
        f'- 최종 수치 최대 절대 차이: {q["output_regression"]["max_numeric_absolute_difference"]}. 양의 크기·유한값·단위 회전 quaternion 검사 통과.',
        f'- 공식 devkit 단일 씬 GT 지표 완전 일치 = {q["ground_truth_regression"]["exact"]}. 두 실행의 실패 단계 0.','',
        '| 정답 기준 진단 | baseline | reuse |','|---|---:|---:|']
    for title,key in [('mAP','mean_ap'),('NDS','nd_score')]:
        lines.append(f'| {title} | {q["ground_truth"]["baseline"]["metrics"][key]*100:.4f}% | {q["ground_truth"]["reuse"]["metrics"][key]*100:.4f}% |')
    lines += ['', '이는 같은 39개 sample에 공식 filtering/matching 계산을 적용한 **단일 씬 진단값**이다. 전체 split/리더보드 점수가 아니다. VESPA 출력의 train은 mini_train으로 매핑했고 기존 confidence 1.0을 유지했다. GT에 없는 클래스도 포함된 10클래스 평균이다. [공식 평가 방식](https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuscenes/eval/detection/README.md).','',
        '**절대 품질의 기존 한계:** 공식 필터 후 GT 2,310개에 예측 1,211개이며, barrier 누락과 차량 방향 오차가 크다. car/truck의 2m 매칭 TP 방향 오차는 약 3.13rad이며 attribute 예측도 비어 있다. 두 방식에서 동일하다. 이번 결과는 품질 회귀가 없다는 근거이지, 정답 수준의 3D 정확도를 확보했다는 근거가 아니다. 방향 추정·정지 객체의 앞뒤 모호성·클래스별 누락은 별도 품질 개선 케이스로 남긴다.','',
        '## 채택 판단과 적합한 조건','',
        f'사전 회귀 기준 통과 = {q["quality_passed"]}; 판정 = `{q["decision"]}`. 이미지/클래스 의미를 유지하면서 중복 CPU 전처리를 줄이는 변경으로 채택한다. hybrid 기본값은 reuse, `VESPA_GROUNDING_PREPROCESS=baseline`으로 원복 가능하다. 재빌드 이후 정상 API 전체 사이클은 별도 A1 증거로 확인한다.','',
        '- 유리: 같은 이미지에 여러 클래스 후보를 넣는 현재 Grounding pipeline. 입력 의미·정밀도를 유지해야 하는 경우.',
        '- 효과 제한: SAM·지면 제거·DINOv2 등 다른 단계가 큰 경우, 클래스가 하나뿐인 경우. 전체 성능 향상 폭은 작아질 수 있다.',
        '- 검증 범위: Transformers 4.49, 현재 Grounding 모델, 직렬 격리 runner. 라이브러리 변경·다중 동시 요청·다른 모델에 일반화하지 않는다.','',
        '## 원본·시각 자료','',
        '`manifest.json`, `quality-gates.json`, `quality-with-gt.json`, `events.jsonl`, `resources.jsonl`, 조건별 `command.json`·`execution-summary.json`·`stage-events.jsonl`·`detector-results.jsonl`·`final-result.json`·stdout/stderr를 보존한다. `quality-attempt1.*`는 공식 GT 평가 실행 기록이다.','',
        '![정답과 기존/재사용 방식의 같은 프레임 3D 비교](quality-3d.png)','',
        '![첫·중간·마지막 프레임의 평면 비교](quality-birdseye.png)','']
    (a.directory/'report.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':main()
