# Claude 전달용: DriveScene2Label 최적화 과정 PPT 제작 프롬프트

아래 구분선 이후부터 끝까지 복사해 전달한다. 실험은 2026-11-17~18일 기록이며 정리일은 2026-11-19다. 가능하면 [전후 전체 정리](../optimization-before-after-2026-11-19.md), [마감 report](../reports/2026-11-18/report.md), [자원 지도](../vespa-resource-map-2026-11-18.md)도 첨부한다. 이 프롬프트만으로도 초안을 만들 수 있게 핵심 근거를 포함했다.

---

너는 모델 서빙·백엔드·DB·스토리지 성능을 설명하는 기술 발표 자료 작성자다. 아래 프로젝트 사실만을 근거로 한국어 PPT를 만들어라. 청중은 개발 경험은 있지만 GPU 서빙·DB 실행 계획에는 익숙하지 않은 사람이다. 도구 이름 나열보다 **문제 정의 → 가설 → 계측 → 변경 전후 → 품질 검증 → 채택/보류 → 미해결 과제**를 전달하라.

## 결과물 형식

- 본문 16장, 부록 3장. 각 장에 제목, 한 문장 결론, 화면에 넣을 핵심 내용 3~5개, 그림/표 제안, 40~60초 발표자 노트를 작성하라.
- PPTX 제작 도구가 있다면 편집 가능한 도형·표·차트로 파일까지 만들고, 없다면 그대로 옮길 수 있는 장별 원고를 만들어라.
- CPU·RAM·GPU/VRAM·디스크·네트워크/RDS/S3를 일관된 색으로 구분하라. 발표자가 “어디를 왜 바꿨는가”를 따라갈 수 있도록 변경 부분을 표시하라.
- 차트마다 단위·입력 범위·반복 횟수·측정 경계·warm/cache 조건을 붙여라. 미측정 값에는 숫자를 만들지 말고 ‘미측정’으로 표시하라.
- 각 방법을 ‘실측·채택’, ‘실행했으나 보류’, ‘코드 준비·미검증’, ‘미실행 제안’ 중 하나로 표시하라. 실패를 감추지 말고 기능 미지원·실행 오류·품질 미달·사용자 중단을 구분하라.
- 마지막 부록에는 예상 기술 질문과 답변을 넣어라. 금액·청구서가 없으므로 비용은 정성 비교만 하라.

## 1. 프로젝트와 사용자 주도 문제 정의

DriveScene2Label은 nuScenes 원본 업로드 → CLIP 임베딩 → 자연어 씬 검색 → 선택한 씬의 VESPA 3D 자동 라벨링 → 결과 저장·3D 확인/편집 서비스다.

사용자는 “왜 오래 걸리는지 먼저 로그로 가설을 세우자”, “case별로 전후 비교하자”, “정확도와 3D 품질도 확인하자”, “GPU 모델 상주, CPU 스레드, FlashAttention, 저정밀도, TensorRT, 중복 쿼리, S3 병렬·캐시까지 검토하자”라고 제안했다. 이 제안을 실제 수행한 시험과 미실행 후보로 나눠 설명하라. 사용자 개인이 모든 코드·실험을 직접 작성했다고 주장하지 말고 ‘사용자가 제안하고 프로젝트에서 검증한 과정’으로 표현하라.

운영 구조는 Vercel 프론트 + 로컬 Windows/Docker의 Spring 백엔드·FastAPI/GPU + AWS RDS PostgreSQL/pgvector + S3 원본 저장이다. 로컬 GPU는 RTX 5060 Ti 16GB다. EC2/ECS/EKS로 전체 이전한 상태가 아니다. 이번 설명의 VESPA는 **3D 라벨링 파이프라인**이며 검색 엔진 Vespa가 아니다. 사용 모델은 Grounding DINO base, SAM ViT-B, DINOv2 ViT-B/14 reg다. DINOv3·SAM2로 교체하지 않았다. CLIP은 별도의 검색 임베딩 경로다.

## 2. 이전 구조와 로그 설계

최적화 이전 동작:

1. Grounding은 같은 이미지도 클래스별 호출마다 resize/normalize를 반복했다.
2. CLIP 인덱싱은 pending 목록을 구한 뒤 이미지마다 source SELECT와 exists SELECT를 반복했다.
3. 벡터 검색 SQL은 거리 CTE와 준비문 auto 계획을 사용했고 반복 호출에서 느린 generic 계획이 관측됐다.
4. CLIP은 서버 시작부터 모델이 상주했지만 동일한 문장도 매번 다시 추론했다.
5. S3 원본 전송은 single PUT 경로를 사용했다. 기존 로컬 캐시 효과와 병렬 전송 효과를 별도 비교했다.
6. VESPA는 작업별 자식 프로세스에서 모델을 지연 로드했다. 같은 작업 안에서는 재사용하지만 작업이 끝나면 프로세스가 종료됐다.

수집한 로그:

| 로그 | 내용·목적 |
|---|---|
| HTTP / UPLOAD_CLIENT / UPLOAD_TRANSFER / UPLOAD_STAGE / DB_IMPORT | 요청·상태·시간, 파일 수신·파일 기록·DB lock/update·압축 해제·S3 보관·DB 등록을 분리 |
| CLIP / CLIP_INDEX | source_ms, exists_ms, cache_ms, ai_ms, storage_ms, total_ms, 처리 이미지 수 |
| CLIP_STAGE | lock 대기, decode, preprocess, GPU 호출 구간, handler, 텍스트 캐시 hit/miss·추론 |
| SEARCH + SQL 실험 | ai_ms, db_mapping_ms, total_ms, EXPLAIN ANALYZE/BUFFERS, custom/generic 준비문 카운터, 결과 순서·점수 |
| DS2L_STAGE / VESPA / AUTO_LABEL | job/run/scene, 시작·완료·실패, wall/cpu time, 모델 getter, 지면·검출·분할·3D·저장 단계 |
| S3_TRANSFER / CACHE | 크기·파트·동시성·요청 시간·실패·abort·완료 확인·캐시 상태 |
| RERUN_STAGE | 라벨 추론과 별도인 3D 기록 생성·전송·다운로드/Range |
| 별도 자원 표본·재현 파일 | GPU 사용률/VRAM/전력/온도, CPU/RAM/I/O, 명령·설정·소스 hash·이미지 digest·종료 코드·품질 비교·파일 SHA256 |

로그는 events.jsonl, report.json/report.md, 명령/환경 manifest, 품질 JSON과 해시로 남겼다. 공용 수집기는 허용된 구조화 필드만 내보낸다. 마지막 마감은 11,096이벤트·분류된 실패 0·수집 오류 0이다. 과거 실험의 오류·중단이 없었다는 뜻은 아니다.

계측 한계: 부모/자식 시간은 겹친다. wall time과 gpu_ms는 순수 CUDA kernel 시간이 아니다. 자원 표본을 모든 단계의 정확한 peak로 표현하지 마라. 현재 일반 collector에는 원본 텍스트 로그의 encode_ms가 빠지므로 텍스트 상세 시간은 별도 benchmark 결과를 함께 본다. 모든 CPU↔GPU 전송량·동기화 시간이 측정된 것은 아니다.

## 3. 적용한 개선과 실측

### G1/G2 — Grounding 이미지 전처리 재사용

- 변경: 한 이미지 호출 안에서 image processor tensor만 재사용. 클래스별 tokenizer/prompt/threshold/model forward/postprocess는 유지. backbone 특징 캐시나 GPU batch를 했다고 설명하지 마라.
- 소량 시험: 12이미지 × 3쌍, 전처리 360→36회, forward 360→360회. 검출 시간 65.377→57.659초(11.81% 감소), 36쌍 검출 일치.
- 전체 씬 1쌍: 전체 2,242.293→2,173.204초(3.08% 감소), Grounding 구간 1,213.790→1,122.069초(7.56% 감소).
- 39프레임·234검출·1,308박스·track 및 3D 좌표/크기/회전/속도 일치. 단일 씬 GT mAP 0.15510248·NDS 0.19750182 동일. 전체 데이터셋 정확도 검증은 아니다.
- 채택: VESPA_GROUNDING_PREPROCESS=reuse. 코드: grounding_probe.py / grounding_runtime.py / vespa_runner.py.
- 핵심 해석: CPU 중복은 줄였지만 비싼 클래스별 forward는 그대로여서 전체 개선은 제한적이었다.

### C1 — CLIP 인덱싱의 중복 DB 조회 제거

- 변경: pending 조회에 source를 포함하고 미저장 조건을 재사용. 이미지별 source/exists 조회를 생략. INSERT ON CONFLICT, worker claim/heartbeat, 일반 API 검사는 유지.
- 같은 474장 × 3쌍, 실행 순서 교차 및 재시작 조건 통제. 중앙값 49.192→42.948초(12.69% 감소).
- 코드 경로상 SELECT 948회 제거/474장. 서버 pg_stat_statements는 없었으므로 서버 카운터로 직접 측정한 숫자라고 쓰지 마라.
- 벡터 1,422쌍·검색 결과 54개 일치. hybrid prefetch 채택.
- 코드: DatasetSearchIndexService / ImageEmbeddingService.embedPending / ImageEmbeddingRepository.
- 핵심 해석: 모델이 느리다고 생각한 인덱싱에도 원격 DB의 반복 왕복이 섞여 있었다. GPU batch 가속과 다른 개선이다.

### Q2 — RDS 정확 검색의 실행 계획 개선

- 변경: distances CTE를 MATERIALIZED로 유지하고 검색 트랜잭션에서만 SET LOCAL plan_cache_mode='force_custom_plan'. 전역 DB 설정·근사 검색 전환은 하지 않았다.
- 실제 RDS에서 auto/custom/generic 분리 비교, 준비문 카운터 확인. 최종 SQL 데이터셋 789.562→55.290ms, 전체 4,397.725→218.554ms. 최종 후보 시간에 SET LOCAL 왕복 포함.
- 비교 216쌍의 순서·점수·집계·대표 이미지 등 모든 결과 필드 동일. exact 검색 유지, 채택.
- 코드: SceneSearchRepository.search / QueryExperiment.java.
- 비용: 매 요청 계획 및 설정 왕복, materialization 임시 I/O 증가 가능. 모든 규모에서 항상 유리하다는 뜻이 아니다.

### Q3 — CLIP 텍스트 임베딩 캐시

- 변경: 기존 상주 모델 수명 안에서 exact-text LRU 256개. 기존 lock 안에서 조회→추론→검증→저장해 동시 중복 miss도 한 번 계산. 실패 결과는 캐시하지 않고 모델 close 시 비운다.
- 실제 GPU, warm 모델, FastAPI TestClient+JSON+lock, TCP/Spring/RDS 제외. 32요청·순서 교대 6회, 보강 비교 1,152쌍 응답 동일.
- 동일 문장 순차: 0.9309→0.3262초. 동시성 4: 0.6775→0.2234초. 추론 32→1회. 약 65~67% 배치 시간 감소.
- 모든 문장이 다르면 추론 절감 없음. 초기 소량 no-hit 동시 시험은 0.3124→0.4036초(29.18% 느림)도 기록했다.
- 채택, 코드 clip_service.py. Redis를 추가하지 않았고 프로세스 종료 시 캐시는 사라진다.

### Q2+Q3 — 실제 검색 HTTP

- loopback HTTP→Spring→CLIP→RDS, warm 모델·반복 문장, warmup 제외, 54쌍 전체 응답 동일.
- 데이터셋 검색 990.226→88.371ms(91.08% 감소), 전체 검색 5,433.339→245.678ms(95.48% 감소).
- 기준/후보 순서를 번갈아 재시작하지 않았으므로 환경 변화 가능성을 밝힌다. 독립 SQL/캐시 시험이 원인 분리를 보강한다.
- 공개 Vercel·인증·터널·브라우저, cold 모델, 동시 사용자 p95, 업로드·라벨링 전체 개선율이 아니다.

## 4. S3·캐시·실패 처리

- S1: 같은 13파일 GET 총 시간, 추출 캐시 0.359초 / 로컬 압축본에서 복원 71.078초 / S3부터 복원 431.500초. 기존 캐시 경로의 차이를 확인한 비교이며 새 코드가 S3를 수백 배 빠르게 했다는 뜻이 아니다.
- S2 Python: 109.7MB, 단일/병렬 비교 13.107→4.996초(61.88% 감소), 해시 일치. Java 앱 성과로 옮겨 쓰지 마라.
- S3-J Java: 실제 4.17GB, single/multipart 3쌍 감소율 -1.54% / 12.50% / 4.21%. 편차 때문에 코드 기본값 OFF. 마지막 운영 설정에서는 사용자 업로드 완료 후 1GiB 초과·16MiB 파트·최대 4병렬을 켰다. 해당 사용자 업로드는 single PUT 기준선이다.
- 브라우저→backend 조각 업로드는 순차이고 backend→S3 병렬 파트와 다르다.
- 신뢰성 변경: 다운로드는 임시 .part에 쓰고 완전성 확인 후 이동. 파트 실패 retry/abort, Complete 응답 유실 때 metadata/length 대조, 중단 경쟁 조건 보완.
- 실제 S3에서 일시적 파트 503, 지속 503, Complete 응답 유실, 다운로드 중단, SIGKILL 5종 시험. 503은 시험 주입. 강제 종료 뒤 자동 재개는 구현하지 않았고 exact upload ID로 정리했다.
- 후속 회귀 65개(중단 경합 50회 포함), 실제 왕복·장애 재검증을 남겼다. 비용은 요청·스레드·메모리·대역폭 경쟁이며 새 Spark/Hadoop 도입 성과가 아니다.

## 5. VESPA 계층과 남은 병목

아래 순서를 CPU/GPU의 처리 흐름으로 그려라. 각 단계가 별도 서버라는 뜻은 아니다.

| 계층 | 자원·처리 |
|---|---|
| 데이터 준비 | CPU/RAM/디스크. cache miss일 때 S3 네트워크·압축 해제 |
| 지면 제거 | CPU/RAM, LiDAR 누적·RANSAC, NPZ 압축·디스크 |
| Grounding DINO | CPU resize/normalize/tokenization → GPU/VRAM forward → 후처리 |
| SAM | GPU 마스크 추론 + CPU/GPU 후처리·NMS·RAM/디스크 |
| LiDAR 투영·노이즈 제거 | CPU/RAM 기하·배열 계산 |
| DINOv2 | CPU 전처리 → GPU feature → CPU RAM 복사·객체 집계 |
| 병합·추적·3D 박스 | CPU/RAM, 속도·yaw·track·기하, 중간 캐시 |
| 저장·시각화 | CPU 직렬화·디스크·RDS 네트워크, 별도 Rerun 생성·브라우저 GPU |

job 14 실제 관측은 AI executor 4,072.075초다. 이미지 검출·분할 부모 3,139.559초(약 77.1%), 그 안에 Grounding 1,569.743초와 SAM 1,395.867초. 지면 제거 349.953초, DINOv2 217.388초, rigid cache 저장 89.569초. backend 결과 저장 29.466초는 executor 밖의 별도 경계이며 순수 DB SQL 시간도 아니다. 부모와 자식 시간을 합하지 마라.

이 job은 앞선 G2와 실행 환경을 통제한 비교가 아니므로 2,173초와 4,072초를 전후 회귀율로 비교하지 마라. Windows RAM 사용률 95~97%인 시점이 있었지만 swap·메모리 부족이 유일한 원인이라는 증거는 없다.

**해석:** 반복 forward, CPU 점군 처리, 전처리/후처리, 파일 기록, 프로세스 생성·모델 로딩이 섞인 이질적인 파이프라인이다. CPU↔GPU 복사·동기화·대기 overhead는 후보지만 분리 실측이 부족하다. ‘CPU/RAM/GPU를 모두 쓰므로 대부분 overhead다’라고 결론 내리지 마라. GPU를 항상 100% 쓰지 않는 이유를 단계 의존성과 함께 설명하라.

## 6. CLIP 상주와 VESPA 상주의 정확한 차이

- CLIP: FastAPI startup/lifespan에서 모델 로드, 서버 객체 수명 동안 재사용.
- 현재 VESPA: 작업별 Python 자식 프로세스 생성 → 모델 첫 접근 시 로드 → 작업 안에서 재사용 → 프로세스 종료. 매 이미지마다 모델을 다시 로드하는 구조는 아니다.
- **VESPA도 상주 가능하다. 현재 구현이 작업 간 모델을 유지하지 않으며, 상주 후보의 실제 GPU·메모리·복구·품질 검증이 끝나지 않았다. ‘VESPA는 상주 불가능’이라고 쓰지 마라.**
- job 14 첫 getter: Grounding 15.594초, SAM 5.746초. 이후 38회 중앙값 0.000015초 / 0.000006초. 확인된 초기 두 로딩 합 약 21.34초. DINOv2 getter 로딩 시간은 배포에서 미계측.
- 상주화는 반복 작업 준비/첫 응답 지연을 줄이는 후보다. 이 두 로딩만 제거해서 약 4,072초의 전체 작업이 몇 배 빨라지지는 않는다. 시작 시 preload는 실제 입력 inference warmup과 다르다.
- 비용: 유휴 VRAM/RAM, CLIP과 메모리 경쟁, 서버 시작 지연, 작업별 데이터 정리·오류 복구 복잡성. 가중치만 유지하고 씬 데이터/중간 결과는 해제해야 한다.

## 7. 시도했으나 해결하지 못한 것

| 시도 | 실제 결과·현재 상태 | 이유와 다음 판단 |
|---|---|---|
| CPU 스레드 1/2/4 | 일부 단계 빨라짐, 2스레드 전체 씬 한 박스 9필드 차이 | 엄격한 출력 일치 기준에서 보류, 기본 1. 단순 증설이 해결책은 아님 |
| FlashAttention2/SDPA | Transformers 4.49.0 Grounding 조합에서 미지원 오류 | 모델/연산 경로 지원 문제. GPU 하드웨어가 원천적으로 불가능하다는 뜻 아님 |
| 전체 FP16/BF16 cast | Float/Half 등 dtype 불일치 | 단순 cast 실패, 올바른 혼합 정밀도 경로 필요 |
| AMP FP16 | 60 forward×3회 30.198→22.428초, 45박스 유지, 최소 IoU 0.994792, 점수 차이 | 소량 가속 확인, 전체 3D/track/GT 미검증으로 보류 |
| AMP BF16 / TF32 | BF16 45개 중 1개 누락, TF32도 박스·점수 차이 | 완전 일치 기본값으로 미채택. 허용 오차를 정하면 재평가 가능 |
| ORT CUDA | ONNX export/checker/실행 성공, raw 출력 불일치 | 실행 성공과 품질 검증은 다름. 전체 클래스·3D 미검증 |
| TensorRT | build 143.666초, 제한된 inference 중앙값 0.2122초, 6카메라 자동차 대응 | 값 차이·전체 씬 품질 미검증. 작은 추론 시간을 전체 씬 시간과 나누지 말 것 |
| INT8/INT4 | 미실행 | calibration·연산 지원·품질 예산 준비 필요 |
| G3 지면 계산 범위 | 후보 준비, 첫 baseline 중 사용자 종료 요청 exit 143 | 완료된 전후 비교 없음. 실패/성공 성능 수치를 만들지 말 것 |
| R3 모델 상주 | 후보 준비, GPU 없는 helper 시험 11개 통과 | 실제 GPU 상주·메모리·복구·3D 비교 미실행. 미적용 |
| C2 CLIP 이미지 batch | 별도 팀 커밋, 64장/호출. 256장 최소 cosine 0.99999982 | M5 MPS에서 속도 차이 없음, 5060 Ti 전후 미측정·기본 OFF. C1 성과와 분리 |

TensorRT의 과거 exit 137은 사용자 중단 기록이다. OOM으로 단정하지 마라. 작은 수치 차이가 있다는 이유만으로 AMP·TensorRT가 실용적으로 불가능하다고 말하지 마라. 이번 채택 조건이 출력 보존이었고 전체 3D의 허용 가능한 변화와 성능을 아직 비교하지 못한 것이다.

## 8. 다음 두 후보와 기타 제안

1. **G3 CPU 지면 제거:** 현재 382 sweep 전체를 처리하지만 다음 영상 단계는 39개 키프레임을 소비한다. 후보는 필요한 키프레임의 지면만 계산하되 원래 전체 Scene·인덱스와 이웃 raw sweep 누적을 보존한다. Scene 자체를 39개로 잘라 결과를 바꾸지 않는다. 3쌍 교차 실험, 소비 mask/변환/cone, 전체 3D/track/GT 비교가 필요하다. 아직 개선율은 없다.
2. **R3 GPU 상주:** 직렬 worker에 Grounding/SAM/DINOv2 가중치를 유지하되 작업별 데이터·로그·상태는 분리/해제한다. 첫/반복 작업 지연, startup/readiness, RAM/VRAM, CLIP 공존, 실패/timeout/복구, 전체 3D를 비교해야 한다. helper 테스트가 실제 모델 통과는 아니다.

그 뒤 CPU/GPU profiler로 forward·복사·동기화·대기·파일 I/O를 분리하고 AMP/엔진을 품질 허용 기준에 맞춰 재평가한다. 기존 단계 wall log만으로 CUDA 커널 병목을 단정하지 않는다.

기타 사용자 제안: 카메라 metadata 묶음(Q4), 라벨 INSERT batch(Q5), 인증·중복 조회 조사, 브라우저 병렬 전송, S3 씬별 저장/필요 범위 다운로드, Redis/DynamoDB/Elasticsearch/Kafka/Spark/Hadoop. C1/Q2 외에 이들을 적용해 빨라졌다는 근거는 없다. 라벨 저장 반복 INSERT는 N+1 SELECT와 구분한다. DynamoDB로 바꾸면 모델 추론이 빨라진다고 설명하지 마라. 이 자료는 DB 제품 기능의 최신 비교가 아니므로 미검증 기능 지원 여부를 단정하지 마라.

## 9. 권장 슬라이드 순서

1. 목표: 사용자 대기시간을 어디서 줄일 것인가
2. 전체 서비스 구조와 업로드→검색→라벨링 흐름
3. 사용자 제안과 가설: 모델·CPU·DB·S3를 분리
4. 어떤 로그를 찍었고 어떻게 전후·품질을 비교했나
5. VESPA 계층별 CPU/RAM/GPU/디스크 사용 지도
6. 실제 job 14 시간 분해: 최대 구간과 미측정 부분
7. G1/G2: 반복 전처리 제거, 전체 효과가 제한된 이유
8. C1: 이미지별 원격 SELECT 중복 제거
9. Q2: 실행 계획·거리 계산을 나눠 검증한 과정
10. Q3와 검색 API: 모델 상주와 결과 캐시는 다르다
11. S3: 캐시·병렬 전송·대용량 편차
12. 실패 처리도 성과: 부분 파일·retry·abort·중단 경합
13. CLIP vs VESPA 모델 수명: 상주가 가능한데 아직 적용하지 않은 이유
14. FlashAttention·저정밀도·CPU 스레드·ORT/TRT 시도와 보류
15. 남은 G3/R3: 검증 계획·기대 범위·비용과 위험
16. 성과와 한계: 적용한 개선/미해결 문제/다음 실험을 구분

부록 A: 변경 코드·원복 스위치·로그 위치. 부록 B: 실험 조건·정확도 검증·사용자 중단·실패 기록. 부록 C: 기술 질문 답변 8개(왜 GPU 사용률이 낮은가, 왜 상주만으로 충분하지 않은가, 왜 FlashAttention 설정 실패인가, 왜 TRT를 바로 적용하지 않았나, 왜 스레드를 늘리지 않았나, 왜 DB를 교체하지 않았나, 왜 S3 병렬이 항상 빠르지 않나, 정확도와 속도의 허용 기준은 무엇인가).

## 10. 근거 파일과 표현 규칙

저장소: https://github.com/DriveScene2Label-Team/DriveScene2Label , 브랜치 release-version.

- docs/optimization-before-after-2026-11-19.md: 전체 정리·코드 위치
- docs/evidence/optimization-2026-11-18/G2/report.md 및 quality-with-gt.json: 전체 씬 전후·품질
- docs/evidence/optimization-2026-11-18/C1/report.md: CLIP DB 3쌍
- docs/optimization-resume-2026-11-18.md: Q2/Q3·검색 API·엔진 실험
- docs/s3-java-optimization-2026-11-18.md: 실제 Java 큰 파일·실패·채택 판단
- docs/vespa-resource-map-2026-11-18.md 및 docs/images/vespa-resource-baseline-2026-11-18.png: 계층·자원 구조
- docs/vespa-bottleneck-diagnosis-2026-11-18.md: 시도·G3/R3
- docs/reports/2026-11-18/report.md 및 docs/evidence/session-close-2026-11-18/: 완료 job·시간·모델 로딩·중단·종료 근거
- 로컬 원본은 .local/hybrid/measurements/ 및 .local/hybrid/experiments/에 보존하고 검토용 증거만 Git에 공개했다.

자료를 열 수 없으면 열어 검증했다고 쓰지 말고 이 프롬프트에 제공된 기록의 범위를 밝혀라. 측정/코드로 확인/가설/미실행을 구분하라. 개선율을 합산하거나 다른 입력·범위의 시간을 나눠 배수를 만들지 마라. 2026-11-18 최종 확인 시 로컬 서비스와 RDS는 중지, Vercel은 paused였다. 새 실험·배포를 완료했다고 쓰지 마라.
