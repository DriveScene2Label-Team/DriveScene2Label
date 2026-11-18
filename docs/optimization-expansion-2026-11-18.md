# 추가 최적화 실험 계획과 판정 기준

작성 당시의 가설·판정 기준을 보존한다. 재개 후 실제 실행한 R1/R2·S2·Q2·Q3 결과와 다음 Q4/Q5 후보는 [후속 보고서](optimization-resume-2026-11-18.md)에 있다.

사용자 요청: 기존 두 최적화에 CPU 스레드, Grounding DINO Attention·정밀도·추론 엔진, S3 전송, RDS 쿼리 분석을 하나씩 추가한다. [완료된 결과](optimization-results-2026-11-18.md)와 분리해 가설·선정 이유·실행 여부를 기록한다. 계획 자체를 측정 성과로 표현하지 않는다.

## 실험 순서

| 케이스 | 문제 위치·가설 | 비교·선택 이유 | 품질·성능 경계 |
|---|---|---|---|
| G2·C1 | 이미지 전처리 반복·이미지별 DB 왕복 | 구현 의미를 유지하는 작은 변경부터 | 완료·채택. 기존 보고서 참조 |
| T3·T4 | SAM CPU 후처리의 native thread 제한 | 1·2·4 교차 반복 → 최소한의 유효 병렬도 | T3 후보 2를 T4 전체 씬에서 기각. 한 박스 9개 필드 차이로 운영 1 유지 |
| A2 | Attention 구현·커널 지원 | 현재 설치 버전·모델의 실제 지원 플래그와 초기화 실패를 기록 | FlashAttention 이름만 설정한 실행을 가속 성공으로 세지 않음 |
| P1/P2/P3 | Grounding FP32 연산 비용 | FP16 / BF16 / matmul TF32를 각각 FP32와 비교 | 같은 입력·10개 클래스·threshold·forward 수. 시간·VRAM·검출 차이 기록 |
| R1/R2 | Python/PyTorch 실행 비용 | ONNX export·ORT CUDA와 TensorRT 호환성·실행을 단계별 확인 | export 성공, GPU provider 사용, 전체 연산 coverage와 출력 일치 확인 전 성능 채택 금지 |
| S2 | 단일 S3 PUT/GET의 전송 대기 | 같은 파일·리전에서 단일 전송과 제한된 multipart/Range 병렬도 비교 | byte SHA256·크기·request/retry·전송량·CPU/메모리. 기존 원본과 구분한 실험 key |
| Q2 | 검색/인덱싱 SQL의 서버 실행·왕복 | 실제 SQL의 read-only EXPLAIN ANALYZE BUFFERS와 반복 경과시간 | 결과·순위 의미 유지. 실행계획 증거 없이 index나 근사 검색 적용 금지 |

한 번에 하나의 변경만 비교한다. GPU 시험끼리, 대용량 S3 전송·빌드와 GPU 시험을 함께 실행하지 않는다. 모델 로딩·엔진 빌드·warmup·정상 처리 시간은 분리한다. 실패도 새 폴더·명령·stdout/stderr·환경/입력 해시로 남긴다. 같은 입력을 반복한 소량 결과는 일반화나 p95 증거가 아니다.

## 모델 경로에서 먼저 확인할 것

현재 환경은 Transformers **4.49.0**, PyTorch **2.14.1+cu130**, RTX 5060 Ti 16GB다. 설치된 Grounding DINO 소스에는 일반 multi-head attention, 양방향 fusion, multi-scale deformable attention이 함께 있다. 최상위 모델의 SDPA/FlashAttention 지원과 각 하위 모듈의 지원은 구분해야 한다. 실험 시작 시 운영 환경에는 ONNX·ONNX Runtime·TensorRT·Torch-TensorRT·flash-attn 패키지가 없었다. R1/R2에서 설치한 선택적 dependency는 별도 experiment 경로로 격리한다.

FlashAttention은 지원되는 attention 연산의 메모리 접근을 줄이는 구현이며 전체 Grounding의 deformable attention을 자동 대체하는 옵션이 아니다. 최신 Transformers의 지원 목록을 4.49 설치에 그대로 적용하지 않는다. 라이브러리 업그레이드는 별도 변경이고, 모델·전처리 출력 회귀가 필요하다. [Hugging Face Attention backend](https://huggingface.co/docs/transformers/attention_interface).

FP16/BF16은 부동소수점 정밀도 선택이고 INT8/INT4 양자화와 구분한다. dtype을 낮추면 threshold 근처 score·박스·mask·최종 3D가 달라질 수 있다. 우선 정확히 같은 검출인지 확인하고, 달라지면 개수·클래스·score·IoU 및 원본 출력을 보존한다. 작은 실행의 속도만으로 운영 기본값을 바꾸지 않는다. 정밀도가 달라지는 후보는 후속 전체 씬/GT·추적 품질 근거를 함께 요구한다.

TensorRT는 엔진 변환·최적화 실행 도구이고 Triton은 모델을 요청에 따라 서빙하는 서버다. 서버 교체만으로 모델 연산이 빨라졌다고 해석하지 않는다. ONNX Runtime도 CUDA provider가 사용되지 않고 CPU로 fallback할 수 있으므로 실제 provider·연산 배치를 확인한다. CUDA/cuDNN 주요 버전도 맞춰야 한다. [ORT CUDA 요구사항](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html), [TensorRT 지원·엔진 호환성](https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/support-matrix.html).

NVIDIA TAO의 Grounding DINO export/deploy는 참고 가능한 공식 경로지만, 지금 사용하는 Hugging Face checkpoint와 TAO 모델의 architecture·weights·tokenizer가 같다는 증거는 아니다. 모델 교체를 엔진만 바꾼 비교로 보고하지 않는다. 지원하지 않는 연산과 PyTorch fallback 비율도 측정 대상이다. [TAO Grounding DINO 배포](https://docs.nvidia.com/tao/tao-toolkit/latest/text/tao_deploy/grounding_dino.html), [Torch-TensorRT 미지원 연산 처리](https://docs.pytorch.org/TensorRT/user_guide/compilation/unsupported_ops.html).

## S3와 RDS에서 먼저 확인할 것

`UploadArchiveStore.put`은 Java SDK 동기 `putObject`, `fetch`는 한 GET stream을 64KiB 버퍼로 복사한다. S1의 4.168GB cold 복원에서는 다운로드가 369.100초, 해제가 62.330초였다. multipart/Range 병렬 전송은 네트워크 대기를 겹칠 수 있지만 회선 대역폭·디스크가 포화면 이득이 작다. 대역폭 변동을 코드 효과로 오인하지 않도록 교차 반복하며 해시 계산은 타이밍 밖에 둔다. [S3 성능 가이드](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-guidelines.html), [multipart 동작](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html).

직접 S3 업로드는 브라우저→로컬 PC→S3의 이중 경로를 바꿀 수 있지만, 현재 로컬 GPU의 해제본 준비를 위한 재다운로드·검증 비용까지 포함해야 한다. S3 Transfer Acceleration은 주로 장거리 경로에 유리하므로 서울 사용자·서울 버킷에서 개선을 가정하지 않는다. 같은 리전의 EC2 배치 역시 네트워크를 바꾸지만 보유 로컬 GPU 대비 연산·상시 비용을 별도 비교해야 한다. 이번 S2의 전송 실험과 전체 AWS 이전은 다른 변경이다.

`SceneSearchRepository.search`는 eligible image 전체의 거리와 씬별 집계를 계산한 뒤 씬 수를 제한한다. MAX·AVERAGE·TOP_K_AVERAGE의 의미가 다르므로 전역 image top-k를 먼저 자르면 기존 씬 순위가 달라질 수 있다. HNSW/IVFFlat을 추가하기 전에 서버 실행시간·join·sort·buffer·필터 선택도를 확인한다. 근사 index는 recall·필터 후 누락을 검사해야 한다. [pgvector 공식 exact/approximate 검색 설명](https://github.com/pgvector/pgvector), [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).

`EXPLAIN ANALYZE`는 실제 쿼리를 실행한다. 이번 분석은 SELECT만 read-only transaction과 timeout으로 수행하고 공유 통계 reset·extension 설치·사용자 데이터 삭제는 하지 않는다. 네트워크 왕복 시간과 서버 실행시간을 함께 기록해 “SQL 자체가 느린지, 작은 호출이 많은지”를 구분한다.

## 종료·공유 기준

실험 완료 후 케이스별 채택/보류/실행 불가와 정확한 이유, 코드 위치, 재현 명령, 품질·성능 범위를 결과 문서와 README에 반영한다. 테스트·secret 검사 후 `release-version`에 commit/push하고 CI를 확인한다. AWS는 추가 측정이 끝나면 다시 stopped를 확인하며 최종 자동 재시작 시각을 갱신한다. S3·RDS 데이터와 로컬 볼륨은 유지한다.

## 오늘 종료 시점

A2/P: 미지원 또는 출력 차이로 운영 유지. R1: bool OR adapter 이후 ONNX/ORT CUDA 실행 성공, raw 품질 게이트 실패. R2: parser 성공 후 사용자 요청으로 GPU 중단. S2/Q2: 도구 준비·추가 AWS 비교 미실행. 인증·캐시·중복 요청의 새 후보는 [후속 학습·계획](request-cache-query-study-2026-11-18.md)을 따른다. GPU는 다시 켜지 않았다.
