# 중단 실험 재개 — 2026-11-18

사용자가 작업과 GPU 실험 재개를 허용했다. 출발 코드는 `f9de3f1`이며 [이전 결과](optimization-results-2026-11-18.md)의 원본·판정은 보존한다. 기존 RDS·S3를 사용하고 케이스마다 새 측정 폴더에 명령, 입력·코드 해시, stdout/stderr, 자원, 결과를 남긴다. 비교가 끝나면 AWS와 로컬 추론을 다시 중지한다.

## 문제와 선택한 검증

| 케이스 | 문제·가설 | 도구를 선택한 이유 | 적용 기준 |
|---|---|---|---|
| R1 후속 | raw query slot 차이만으로 실제 검출 차이를 판단할 수 없음 | 보존한 ONNX·입력으로 ORT CUDA/CPU 재실행, 6개 카메라에서 PyTorch와 박스 대응 비교 | 빈 검출만으로 통과하지 않음. 전체 클래스·3D 검증 전 운영 교체 보류 |
| R2 재개 | 지난 TensorRT 빌드는 사용자 요청으로 중단돼 완료 여부를 모름 | 같은 graph와 격리된 TensorRT 패키지 사용, 900초 한도로 빌드·실행·출력 확인 | parser 통과와 engine 실행을 구분. 빌드 시간은 정상 요청 시간에 섞지 않음 |
| S2 | 큰 S3 객체의 단일 PUT/GET에서 네트워크 대기 | 같은 109,696,439바이트 파일을 stream/병렬도 1·2·4로 3회 교차 비교 | 모든 다운로드 SHA 일치, 실험 객체·multipart 정리 확인. Python SDK 결과를 Java 앱 개선율로 주장하지 않음 |
| Q2 | 거리식 반복 계산과 반복 호출의 계획 변화 | MATERIALIZED 비교 후 auto/custom/generic 분리, 실제 준비문 카운터 확인 | 각 54쌍의 정렬된 결과 동일. 최종 후보 SET LOCAL 비용 및 실제 API 검증 |
| Q3 | 같은 문장을 매번 추론하며 lock 대기 | bounded exact-text LRU, 실제 GPU FastAPI/JSON 및 동시 요청 비교 | 전체 벡터·응답 동일, 실패/동시 중복/모델 수명 회귀. no-hit 시간 차이 별도 해석 |

기존 기본값인 Grounding 전처리 `reuse`, CLIP source prefetch, native thread 1, FP32는 유지한 상태에서 비교한다. GPU 시험과 대용량 S3 전송·SQL 성능 시험은 겹치지 않는다. RDS 시작 대기만 원격에서 진행한다.

## R1: 빈 검출을 발견하고 양성 입력으로 보강

원래 정적 export는 첫 프레임의 `CAM_FRONT_LEFT`, `car.` 프롬프트 한 개였다. 20261118T053436Z 재실행에서 **PyTorch·ORT CUDA·ORT CPU 모두 score > 0.3 검출이 0개**였다. raw logits/boxes는 여전히 다르다. 빈 결과의 일치로 검출 품질을 통과시킬 수 없으므로 이 케이스는 품질 판단 불충분으로 기록한다.

20261118T053854Z에서는 같은 프레임의 6개 카메라를 모두 검사했다. 모델 revision·입력 크기·전처리·정밀도를 확인하고 각 이미지의 입력, PyTorch raw 출력, ORT raw 출력을 보존했다. 동일 `car.` 프롬프트에서 Hungarian IoU 대응으로 박스를 비교했다.

| 카메라 | 기준 검출 | ORT 검출 | 대응 | 최소 IoU | 최대 score 차이 |
|---|---:|---:|---:|---:|---:|
| CAM_FRONT | 3 | 3 | 3 | 0.9996050000 | 0.0009805858 |
| CAM_BACK | 3 | 3 | 3 | 0.9996992350 | 0.0016434789 |
| 나머지 4개 | 0 | 0 | 0 | 해당 없음 | 해당 없음 |

검출 6개에서 누락·추가가 없었지만 raw 출력 및 박스·점수의 정확한 일치는 아니다. 이전 raw slot 최대 차이를 곧바로 검출 품질 붕괴로 해석할 수 없다는 증거이며, 반대로 이것이 전체 클래스 mAP·SAM mask·3D·추적의 보존을 증명하지도 않는다. **운영 엔진 교체는 보류한다.**

## R2: TensorRT 빌드·실행 완료, 운영 적용 보류

20261118T053959Z에서 TensorRT 11.4.0.106이 같은 graph를 파싱하고 **143.665927초**에 968,472,860바이트 엔진을 생성했다. warmup 3회 뒤 10회 측정의 host 입력 → GPU 실행 → host 출력 중앙값은 **0.212216798초**였다. 이전 PyTorch/ORT 측정과는 실행 날짜·프로세스가 다르므로 이를 통제된 개선율로 계산하지 않는다. 기본 CUDA stream 사용 경고도 남겼다.

raw logits/boxes 품질 게이트는 여전히 실패했다. 20261118T054437Z에서 자동차가 있는 6개 카메라 입력으로 보강했을 때 기준·후보 모두 6개, 누락·추가 0, 최소 IoU **0.999643326**, 최대 점수 차이 **0.003325641**였다. 모델 구조·정밀도·엔진에 의한 수치 차이를 분리해 더 검증해야 한다. 현재 엔진은 고정 이미지 크기·`car.` 프롬프트용이며, 10개 클래스·다른 텍스트 길이·전체 씬에 사용할 서빙 엔진으로 배포하지 않는다.

## S2: 업로드 병렬화는 유망, 다운로드는 보류

성공 실행은 20261118T054854Z다. 같은 파일과 16MiB part 크기로 순서를 교차해 각 모드를 3회 측정했다. 아래 값은 각 모드 3회 중앙값이다.

| 모드 | 업로드 초 | 단일 대비 시간 감소 | 다운로드 초 | 단일 대비 시간 감소 |
|---|---:|---:|---:|---:|
| 단일 PUT/GET | 13.106848 | 기준 | 3.207650 | 기준 |
| multipart/Range, 동시성 1 | 15.284773 | -16.62% | 4.250251 | -32.50% |
| 동시성 2 | 8.056320 | 38.53% | 3.534931 | -10.20% |
| 동시성 4 | 4.995964 | 61.88% | 3.105931 | 3.17% |

업로드는 병렬도 4가 세 번 모두 유리했다. 다운로드는 차이가 작거나 역효과였으므로 일괄 병렬화를 선택하지 않는다. 12개 다운로드의 전체 SHA가 원본과 일치했고, 새 UUID 객체 12개의 버전 삭제와 부재를 검증했다. cleanup 오류는 0개다. 이 결과는 Python SDK 전송 구간에 한정되며 **Java 서비스 전체 업로드 개선율은 아니다**. 서비스 반영 후보는 업로드만 제한된 병렬도로 처리하고, 큰 파일·재시도·실패 정리·메모리까지 추가 검증하는 방식이다.

첫 시도 20261118T054546Z는 설치된 boto3 1.35.99 client가 context manager를 지원하지 않아 S3 객체 생성 전에 실패했다. 두 번째 20261118T054724Z는 StreamingBody의 context manager가 내부 HTTPResponse를 반환해 `iter_chunks`가 없는 오류였다. 만든 1개 객체는 삭제·부재 확인했다. `contextlib.closing`으로 wrapper를 유지하고 실제 botocore StreamingBody로 정상 복사·잘린 응답 거부·close 회귀 테스트를 추가했다. 두 실패는 서비스 성능 결과에 합치지 않고 원본 로그를 보존한다.

RDS 시작 중 `rebooting`을 즉시 오류로 처리하던 시작 도구도 수정했다. 재시작 요청을 추가로 보내지 않고 기존 timeout 안에서 `available`을 기다리며 이를 회귀 테스트로 확인했다. [RDS 상태 정의](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/accessing-monitoring.html).

## 코드와 원본 경로

- [재개 실행기](../scripts/hybrid/resume_runtime_probe.py): 이전 artifact의 해시 확인, 새 디렉터리, 별도 dependency 사용, 단계별 timeout·명령·실패 보존.
- [6개 카메라 검출 비교](../ai-server/tools/benchmark_runtime_detections.py): 같은 입력의 raw 출력 저장, 양성 검출 필수 확인, 박스 대응 및 누락·추가 집계.
- [S3 전송 비교](../scripts/hybrid/benchmark_s3_transfers.py): 제한된 동시성, 재시도·요청 기록, SHA 검증, 이번 실험의 UUID 객체만 정리.
- [쿼리 비교 실행기](../scripts/hybrid/run_query_experiment.py), [읽기 전용 JDBC 도구](../src/main/java/com/example/demo/nuscenes/benchmark/QueryExperiment.java): 운영 worker 없이 SELECT만 실행하고 raw plan의 벡터 literal은 로컬에 보존.

로컬 묶음: `.local/hybrid/experiments/20261118T053317Z-resume/`. 각 실행의 상세 경로와 완료 여부는 이 폴더의 manifest·report를 따른다.

S3 동시 연결·Range 요청은 전송 대기를 겹치는 후보이며 요청 수와 네트워크 전송 비용도 함께 증가할 수 있다. 기존 버킷·IAM 정책을 바꾸지 않고 제한된 파일로 먼저 측정한다. [AWS S3 성능 가이드](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-guidelines.html), [S3 요금 항목](https://aws.amazon.com/s3/pricing/). RDS는 시작 시 과금이 재개되므로 비교 종료 후 중지하고 실제 자동 재시작 예정 시각을 기록한다. [RDS 시작](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StartInstance.html), [RDS 중지](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html).

## Q2: 반복 검색의 실행 계획과 거리식 계산을 분리

실제 RDS PostgreSQL 16.15, pgvector 0.8.2, `work_mem=4MB`, JIT off에서 dataset 21의 기존 이미지 벡터 3개를 질의 입력으로 사용했다. 데이터셋 한정/전체 × MAX/AVERAGE/TOP_K_AVERAGE × 교차 순서 3회로 **실험마다 54쌍·108개 SELECT**를 비교했다. 각 경로의 warmup은 시간에서 제외했다. 아래 중앙값은 범위별 9개 시나리오 중앙값의 중앙값이며 텍스트 추론·API 시간은 포함하지 않는다.

| 실행·설정 | 원래 SQL 데이터셋 / 전체 ms | MATERIALIZED 데이터셋 / 전체 ms | 관찰 |
|---|---:|---:|---|
| 055335 · auto | 801.953 / 4,488.779 | 364.576 / 1,996.241 | 반복하면서 급격히 느려짐. EXPLAIN 시간과 불일치 |
| 060035 · force_custom_plan | 82.055 / 399.738 | 48.308 / 206.788 | 입력값별 계획에서 안정. 설정 비용은 측정 전 |
| 060123 · force_generic_plan | 797.465 / 4,374.256 | 363.548 / 1,954.439 | 느린 경로 재현. 설정 비용은 측정 전 |
| 060849 · 기준 auto vs 후보 custom + MATERIALIZED | 789.562 / 4,397.725 | **55.290 / 218.554** | 후보의 매 요청 `SET LOCAL` 왕복도 측정 안에 포함 |

모든 216쌍에서 순서·점수·집계·대표 이미지 등 모든 SQL 결과 필드가 정확히 일치했다. 최종 paired 실험의 prepared statement 카운터는 기준에서 custom 5회 후 generic 사용, 후보에서 custom만 사용했음을 보여 준다. 처음 auto 실행의 시간 차이를 네트워크 비용으로 단정하지 않고, 강제 custom/generic으로 재현해 가설을 좁혔다. 원래 SQL의 데이터셋 nullable OR, 바인딩된 모델/전처리 등과 계획 선택이 관련될 수 있으나 어느 predicate 하나가 유일한 원인이라고 결론 내리지는 않는다.

PostgreSQL은 준비된 문장에서 처음 5회의 custom 비용을 참고해 generic 사용 여부를 판단한다. pgJDBC의 `prepareThreshold=5`는 서버 준비문 사용을 시작하는 별도 임계값이므로 두 숫자를 혼동하면 안 된다. `EXPLAIN ANALYZE`로 새 문장을 실행한 시간도 이미 캐시된 실제 문장의 시간과 다를 수 있다. [PostgreSQL PREPARE](https://www.postgresql.org/docs/16/sql-prepare.html), [pgJDBC 설정](https://jdbc.postgresql.org/documentation/use/).

후보 코드는 `SceneSearchRepository.search`의 **읽기 전용 트랜잭션 안에서만** custom 계획을 선택하고, 거리 CTE를 materialize한다. 전역 RDS 설정·연결 풀·인덱스·pgvector 근사 검색은 변경하지 않는다. 한 번 더 DB 왕복하고 매번 계획을 만드는 비용이 있으므로 작고 균일한 데이터에서 항상 유리하다는 주장은 하지 않는다. global plan에서 temp written blocks는 예시 949→1,421로 증가했다. 더 큰 데이터에서는 임시 I/O까지 다시 측정해야 한다. [CTE materialization의 손익](https://www.postgresql.org/docs/16/queries-with.html).

hybrid 기본값에 채택하며 원복 스위치는 `SEARCH_EXACT_OPTIMIZATION_ENABLED=false`다. 기존 SQL과 auto 계획으로 함께 돌아간다. 아래 실제 Spring·검색 HTTP 검증과 회귀 테스트를 함께 확인한다. `--baseline-sql` 옵션으로 보존된 원본 SQL을 지정하면 운영 코드가 바뀐 뒤에도 같은 기준을 재현할 수 있다.

### Q2 + Q3: 실제 검색 API 검증

`20261118T061542Z`에서 같은 이미지/소스의 baseline 설정(기존 SQL, text cache 0)과 optimized 설정(custom + MATERIALIZED, text cache 256)을 차례로 실행했다. 쓰기 worker는 전부 끄고 기존 dataset 21만 읽었다. 공개 테스트 문장 3개 × dataset/global × 집계 3개 × 반복 3회로 **54쌍의 HTTP 응답 전체가 정확히 일치**했다. 같은 문장 재사용, warm 모델, 시나리오별 1회 warmup 제외 조건이다.

| loopback HTTP → Spring → CLIP → RDS → 응답 | 기준 중앙값 | 후보 중앙값 | 감소 |
|---|---:|---:|---:|
| dataset 21 | 990.226ms | **88.371ms** | **91.08%** |
| 전체 dataset | 5,433.339ms | **245.678ms** | **95.48%** |

기준과 후보의 순서를 번갈아 재시작한 시험은 아니므로 환경 변화 가능성을 포함한 이번 실행의 관측값이다. 쿼리 단독 교차 실험과 캐시 단독 실험이 원인 분리를 보강한다. 두 변경의 효과를 각각 위 감소율로 주장하지 않는다. Hikari 연결별 준비문 상태로 기준 경로에서도 빠른/느린 요청이 섞였고, 단일 긴 JDBC 세션의 분포와도 달랐다. Vercel·공개 터널·Cognito·브라우저 시간, cold 모델 로딩, 동시 사용자 p95, 업로드/라벨 전체 작업 시간은 포함하지 않는다.

447개 단계 이벤트를 수집했고 수집 오류는 0개다. `benchmark_search_api.py`는 응답 및 해시, 요청별 시간, 품질 판정, 비교 summary를 보존한다. RDS 라벨·벡터를 변경하거나 AI 라벨 작업을 새로 만들지 않는다. 이전 G2 전체 씬 3D 검증을 이번에 다시 수행한 것으로 표현하지 않으며, 이번 채택 후보는 Grounding/SAM/3D 계산을 바꾸지 않는다.

## Q3: CLIP 텍스트 서빙 캐시

모델을 한 번 로딩하는 기존 방식은 유지하고, 같은 모델 인스턴스 수명 동안 정확히 같은 문장의 벡터를 재사용한다. 별도 Redis·배포 서버·worker 증설 없이 기존 lock 안에서 lookup→추론→출력 검증→삽입을 수행해 동시 중복 miss도 한 번만 계산한다. LRU 256개를 hybrid 기본값으로 채택했다. 응답은 새 list로 반환하고 저장 벡터는 복사해 호출자의 응답 수정이 다음 요청을 바꾸지 못하게 한다. 실패 결과는 캐시하지 않으며 hit에도 GPU/model readiness를 검사한다. close/reload 때 캐시를 비운다. 모델·토크나이저를 프로세스 안에서 임의로 교체하는 기능은 없으며 향후 이를 추가하면 cache invalidation도 함께 필요하다.

RTX 5060 Ti, torch 2.14.1+cu130, native thread 1, 같은 로딩된 모델로 FastAPI route+JSON+lock을 TestClient에서 측정했다. TCP·Spring·RDS는 제외했다. 각 배치 시작 시 캐시를 비우고 모델만 warm 상태였다.

첫 실행 `061354`는 16요청 × 3회 × 6조건, **288쌍 일치**였다. 반복 문장은 빨랐지만 distinct 동시성 4가 **0.3124→0.4036초, 29.18% 느림**을 보여 보강했다. warmup 20회·32요청·순서 교대 6회로 늘린 `062125`는 **1,152쌍 일치**, 총 72개 배치를 기록했다.

| 32요청 배치·6회 중앙값 | 동시 요청 | cache 0 초 | cache 256 초 | 실제 추론 횟수 |
|---|---:|---:|---:|---:|
| 같은 문장 반복 | 1 | 0.9309 | 0.3262 | 32→1 |
| 같은 문장 반복 | 4 | 0.6775 | 0.2234 | 32→1 |
| 반복/신규 혼합 | 1 | 0.6474 | 0.5129 | 32→17 |
| 반복/신규 혼합 | 4 | 0.6691 | 0.5021 | 32→17 |
| 모두 다른 문장 | 1 | 0.8427 | 0.6985 | 32→32 |
| 모두 다른 문장 | 4 | 0.8594 | 0.6801 | 32→32 |

반복 문장 배치의 관측 감소는 64.96~67.03%, 혼합은 20.77~24.96%다. **distinct는 cache hit가 0이므로 시간 감소를 캐시의 인과적 효과로 주장하지 않는다.** 첫 실행의 역효과와 보강 실행의 차이는 짧은 GPU 요청/ASGI 스케줄링의 편차 한계를 보여 준다. 모든 요청을 병렬화하면 빨라진다는 결론도 아니다. 실제 GPU 계산은 같은 lock에서 직렬화하고, 반복 요청에서 계산 자체를 줄였다.

256개 float32 768차원 벡터만 약 0.75MiB이고, 문장 key와 Python 객체 메모리는 별도다. API는 문장 10,000자 제한이 있으므로 무한 cache가 아니다. 새 문장만 오는 워크로드는 추론 절감이 없고 저장·lookup 비용이 추가된다. `CLIP_TEXT_CACHE_SIZE=0`으로 비활성화할 수 있다. `[CLIP_STAGE]`에 hit/miss/disabled, cache 항목 수, lock 대기·encode·handler 시간을 남기고 문장 원문은 남기지 않는다. encode 시간은 GPU kernel 전용 시간이 아니다.

GPU 없는 mock 계약 테스트는 exact key/LRU, 응답 수정 격리, 동시 4요청 중복 1회 추론, 실패 미저장, GPU 상실/close, 비활성화, 문장 비노출을 검사했다. 기존 API·GPU health와 함께 **16개 통과**했다. 별도 경로에 pytest를 설치해 운영 Python 의존성은 변경하지 않았다.

## FlashAttention과 서빙 엔진 선택

현재 Grounding DINO의 Transformers 4.49 경로는 모델 전체 `attn_implementation="sdpa"`/`"flash_attention_2"`를 지원하지 않아 이전 실제 초기화 시험에서 거부됐다. 11월 18일 조회한 upstream에서도 모델 전체 지원을 확인하지 못했다. BERT 하위 모듈의 SDPA 사용 여부와 전체 Grounding 엔진 지원은 별개다. FlashAttention은 일반 attention 연산의 후보이며 Grounding의 deformable sampling 전체를 대체하지 않는다. 직접 SDPA로 바꿀 경우 boolean mask의 의미·dtype·출력 오차를 확인해야 한다. 단순 패키지 설치나 버전 상승을 개선으로 취급하지 않는다. [Grounding DINO 문서](https://huggingface.co/docs/transformers/model_doc/grounding-dino), [attention backend 계약](https://huggingface.co/docs/transformers/attention_interface), [PyTorch SDPA](https://docs.pytorch.org/docs/main/generated/torch.nn.functional.scaled_dot_product_attention.html).

현재 환경은 별도 deformable CUDA kernel이 로드되지 않았고 ninja/nvcc도 없었다. 다음 모델 실험은 profiler로 attention·grid_sample·전처리·전송 비중을 확인한 후 해당 구간만 바꾸는 것이다. CUDA 개발 이미지/커스텀 연산, TensorRT 동적 shape·텍스트 길이, FP16/INT8은 각각 별도 케이스다. 현재 수치 차이가 확인된 엔진이나 저정밀도를 전체 씬 3D 검증 없이 기본값으로 넣지 않는다. [현재 버전 모델 소스](https://github.com/huggingface/transformers/blob/v4.49.0/src/transformers/models/grounding_dino/modeling_grounding_dino.py), [PyTorch profiler](https://docs.pytorch.org/docs/main/profiler).

서비스는 uvicorn worker 1개와 모델별 lock을 사용한다. worker를 늘리면 모델 메모리가 프로세스마다 복제되고, async로 바꾸는 것만으로 GPU 계산이 빨라지지는 않는다. Triton dynamic batching은 서로 다른 요청이 충분히 모일 때 처리량 후보지만 대기 시간과 VRAM이 증가할 수 있다. 현재 반복 문장 중복 제거는 더 작은 변경으로 직접 검증할 수 있어 먼저 선택했다. [FastAPI 배포·메모리](https://fastapi.tiangolo.com/deployment/concepts/), [Triton 최적화](https://docs.nvidia.com/deeplearning/triton-inference-server/archives/triton-inference-server-2600/user-guide/docs/user_guide/optimization.html).

## N+1 조사: 실제 후보와 아닌 경로

| 경로 | 코드에서 확인한 동작 | 판단·다음 검증 |
|---|---|---|
| 검색 | `SceneSearchRepository` 한 번의 집합 SQL, matchScore는 메모리 계산 | N+1이 아니라 이번 Q2의 실행 계획·거리 계산 문제 |
| sample 상세 | sample 조회 + sensor 파일 JOIN + map 조회, 고정 3회 | 행마다 조회하는 N+1로 분류하지 않음 |
| 6개 카메라 geometry | `useFrameBundle`에서 calibration/pose 각각 요청. calibration은 dataset+sensor 캐시 존재 | cold 최대 12개 HTTP/SQL, 새 프레임 pose 최대 6개. Q4: 기존 sample JOIN에 필요한 geometry를 포함하거나 batch endpoint 비교 |
| 자동 라벨 저장 | `AutoLabelService.complete`가 박스마다 INSERT | Q5: 제한된 JDBC batch 후보. 1,308박스 저장 구간 11.570초였으며 전체 모델 실행 시간과 구분 |
| RRD 입력 조회 | sample·LiDAR·GT·prediction을 집합 조회 후 메모리에서 그룹화 | 무조건 JOIN/FETCH로 재작성할 근거 없음 |

Q4는 카메라별 고유 timestamp/ego pose, 누락 metadata 오류, dataset 간 cache key, 최종 3D 투영 일치를 검증해야 한다. Q5는 동일 트랜잭션, 일부 실패 전체 rollback, stale lease·중복 완료·멱등성을 유지해야 한다. JPA `LabelRevision`의 LAZY 관계는 존재하지만 history는 DTO projection이므로 코드 전체에 ORM N+1이 있다고 단정하지 않는다. [Spring JDBC batch](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html).

S3 Java 적용은 upload만 병렬도 4로 시작하는 후보다. 현재 앱 전용 IAM에는 `AbortMultipartUpload`가 없으므로 실패·취소 시 미완료 part를 정리하는 권한과 동작을 함께 준비해야 한다. 이번 Python 시험은 기존 운영자 권한으로 **이번 UUID 객체/버전만** 정리했고 운영 IAM은 넓히지 않았다. 작은 파일은 단일 PUT, 큰 파일은 bounded multipart, 다운로드는 현재 스트림을 유지하는 분기가 다음 검증 대상이다. 원본 4GB, 중간 실패, 재시도, 최대 메모리까지 Java 경로로 통과하기 전에는 Python 수치만으로 운영 기본값을 바꾸지 않는다.

## 검증·로그·최종 상태

- 격리된 Java 21 + pgvector/PostgreSQL에서 **23개 통과**: 원래/최적화 검색, 집계·dataset 격리·오류·index 재시도·worker 경쟁, custom 계획의 트랜잭션 종료 후 복구.
- AI **16개 통과**: 실제 모델 성능과 별도의 mock/API/GPU health 계약. host **44개 통과·2개 선택적 통합 테스트 skip**, 실제 botocore StreamingBody **2개 통과**, Python 구문 검사 통과. 전체 원격 CI는 Git push 후 별도 확인한다.
- [229개 공개 증거와 SHA 연결](evidence/optimization-resume-2026-11-18/README.md). 원본 로그/벡터/plan은 `.local/hybrid/measurements/<UTC>/`, 요약은 `.local/hybrid/experiments/20261118T053317Z-resume/report.md`에 있다.
- RDS `stopped`, GPU·backend·auth exited 확인. 다음 RDS 자동 시작은 **11월 25일 15:24:52 KST**. [중지 증거·재시작·원복](shutdown-2026-11-18.md).

재현 순서: 새 `measurement.py begin` → 해당 도구 실행 → 단계/자원 수집 → 출력/조건 확인 → report 작성 → stop. Q2의 변경 전 SQL은 이전 measurement의 `search-baseline.sql`을 `--baseline-sql`로 전달한다. Q3는 `tools/benchmark_clip_serving.py --output <새 폴더> --repeats 6 --requests 32`를 AI 이미지의 별도 프로세스에서 실행한다. 현재 실행 중인 작업과 벤치마크를 겹치지 않는다. 비교 스크립트는 운영 설정을 자동으로 채택하지 않는다.
