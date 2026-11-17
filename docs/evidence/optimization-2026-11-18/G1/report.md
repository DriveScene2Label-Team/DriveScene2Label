# Grounding DINO — G1 전처리 재사용 비교

## 문제 정의와 해결 후보

기존 VESPA에서 가장 오래 걸린 검출 단계가 같은 이미지를 후보 클래스마다 다시 전처리하고 추론한다. 먼저 실제 호출 횟수를 확인한 뒤, 이미지 전처리를 한 번 계산해 각 클래스에 재사용하는 변경만 비교한다.

## 도구 선택 이유

- 설치된 Transformers pipeline: 현재 서비스와 동일한 모델·후처리·라벨 매핑을 유지하기 위해 선택.
- image_processor proxy와 PyTorch forward hook: 겉 API 호출 수가 아닌 실제 내부 호출 수를 계수.
- context manager: 실험 종료·예외 때 monkey patch와 hook을 복원하여 다음 조건에 변경이 남지 않도록 함.
- unittest: 실제 설치 image processor와 원본 preprocess의 텐서 동등성·청크 분리·예외 복원을 검증. VESPA 환경에 pytest가 없어 표준 라이브러리로 실행.
- JSONL과 입력/소스 SHA256: 이미지·반복·조건별 결과 및 실행 코드를 재현 가능하게 보존.

## 고정 조건

- 모델 `IDEA-Research/grounding-dino-base` revision `12bdfa3120f3e7ec7b434d90674b3396eccf88eb`.
- scene-0061, 2키프레임 × 6카메라 = 12장, 조건별 3회.
- threshold 0.3, 후보 10개, torch.float32, CPU 스레드 1.
- PyTorch 2.14.1+cu130, Transformers 4.49.0, CUDA 13.0, NVIDIA GeForce RTX 5060 Ti.
- diagnostic=False. forward마다 강제 동기화 없음. 호출 계수 hook은 양쪽에 동일 적용.
- 기존 모델·데이터 캐시. 조건마다 같은 첫 이미지 warmup, 반복마다 순서 교대. OS page cache는 통제하지 않음.
- 이미지 파일 디코딩은 이미지별 wall_ms 바깥. pipeline 내부 전처리부터 결과 반환까지 포함. 모델 로드·warmup은 별도 이벤트.
- 검출만 실행. SAM·3D 처리·RDS·S3·웹 요청은 이 측정에 포함되지 않음.

## 측정 결과

| 조건 | 완료 이미지 호출 | 이미지 전처리 | 모델 forward | CPU 복사 | 반복 합계(초) |
|---|---:|---:|---:|---:|---|
| baseline | 36 | 360 | 360 | 360 | 66.254, 64.603, 65.377 |
| reuse | 36 | 36 | 360 | 360 | 57.659, 56.992, 57.690 |

기록 검증: 예상 72건 / 관측 72건 / 고유 (조건·반복·이미지) 72건.

| 조건 | 전처리 합(초) | forward host 합(초) | CPU 복사 합(초) | 최대 allocated GiB |
|---|---:|---:|---:|---:|
| baseline | 25.026 | 155.411 | 11.358 | 2.155 |
| reuse | 1.884 | 154.031 | 12.314 | 2.155 |

host forward 시간은 비동기 CUDA 완료 시간과 다르다. CPU 복사에는 대기·변환이 포함될 수 있다. 하위 구간을 총량과 합산하지 않는다. allocated는 이 프로세스 기준이며 GPU 전체 사용량과 다르다.

## 품질과 판정

- 박스 좌표·점수·클래스·순서의 완전 일치: **36/36쌍**.
- 반복 전체 시간 중앙값 감소: **11.81%**. 개별 반복 감소율: 12.97%, 11.78%, 11.76%.
- 동일 입력에 대한 검출 출력 회귀이며 정답 정확도(mAP) 검증을 대신하지 않음.
- 판정: `candidate_pending_full_scene_validation`. 운영 기본값은 변경하지 않음.
- 전체 씬·최종 3D 결과와 종료/재시도 동작을 검증한 뒤 채택 여부를 결정. 클래스 batching·프롬프트 통합·dtype 변경은 별도 실험으로 분리.

## 원본 로그와 재현

`command.txt`, `stdout.log`, `stderr.log`, `exit-code.txt`, `manifest.json`, `events.jsonl`, `summary.json`, `comparison-summary.json` 보존. G1은 `test-conditions.json`과 30초 간격 `resources.jsonl`도 보존한다. G0은 이미지별 CUDA peak를 기록했으며 별도 호스트 자원 샘플은 수집하지 않았다.
