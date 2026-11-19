# 최적화 전후와 해결하지 못한 문제

정리일: 2026-11-19. 11월 17~18일 코드·실험 로그·마감 보고서를 대조한 기록이다. 이번 문서 작업에서는 서비스를 재시작하거나 새 성능 실험을 하지 않았다. **채택**은 마지막 운영 구성에 반영했다는 뜻이며 현재 서비스 실행 여부와는 다르다.

**[Claude에 전달할 PPT 제작 프롬프트](prompts/claude-optimization-ppt-2026-11-19.md)**에는 아래 사실, 사용자 제안에서 시작한 실험, 실패·보류 이유와 슬라이드 구성을 함께 넣었다.

## 1. 무엇을 바꿔서 빨라졌나

처음부터 모델이나 DB를 교체한 것은 아니다. 먼저 단계별 로그로 반복 작업을 찾고, 출력이 같은지 확인하면서 CPU 전처리·원격 DB 왕복·검색 실행 계획·반복 추론을 줄였다.

| 케이스 | 이전 | 변경 후 | 실측과 검증 | 마지막 적용 상태 |
|---|---|---|---|---|
| G1/G2: Grounding 전처리 | 같은 이미지도 클래스마다 resize·normalize 반복 | 한 이미지 처리 안에서 전처리 tensor 재사용. 클래스별 prompt·forward·threshold 유지 | 소량 시험 전처리 360→36회, forward 360→360회. 전체 씬 **2,242.293→2,173.204초, 3.08% 감소**. Grounding 구간 **1,213.790→1,122.069초, 7.56% 감소** | `VESPA_GROUNDING_PREPROCESS=reuse` 채택 |
| C1: CLIP 인덱싱 DB | pending 목록 조회 후 이미지마다 source SELECT와 exists SELECT 반복 | pending 조회에서 얻은 source와 미저장 조건 재사용. INSERT 충돌 처리·일반 API 검사는 유지 | 474장 × 3쌍 중앙값 **49.192→42.948초, 12.69% 감소**. 벡터 1,422쌍·검색 54개 일치 | hybrid prefetch 채택. GPU batch 변경과 별개 |
| Q2: RDS 벡터 검색 | 거리 CTE와 준비문 auto 계획. 반복 호출에서 느린 generic 계획 관측 | `MATERIALIZED`로 거리 계산 결과 재사용, 검색 트랜잭션에서만 `force_custom_plan` | SQL 데이터셋 **789.562→55.290ms**, 전체 **4,397.725→218.554ms**. 비교 216쌍의 모든 결과 필드 일치 | 검색 전용 스위치 채택. exact 검색 유지 |
| Q3: CLIP 텍스트 검색 | 모델은 이미 상주하지만 같은 문장도 매번 추론 | 같은 모델 수명에서 exact-text LRU 256개. 동시 동일 요청도 lock 안에서 한 번 계산 | 반복 32요청 추론 **32→1회**, 순차 배치 **0.9309→0.3262초**. 보강 시험 응답 1,152쌍 일치 | 캐시 채택. 다른 문장에는 추론 절감 없음 |
| Q2+Q3: 검색 API | 기존 SQL + 텍스트 캐시 없음 | 위 두 변경 결합 | loopback HTTP 데이터셋 **990.226→88.371ms**, 전체 **5,433.339→245.678ms**. 응답 54쌍 일치 | warm 모델·반복 문장 조건의 관측값 |

G2는 39프레임·234검출·1,308박스·track·3D 좌표/크기/회전/속도가 같았고, 단일 씬 GT mAP **0.15510248**, NDS **0.19750182**도 같았다. 이는 품질을 보존했다는 뜻이지 전체 데이터셋에서 높은 정확도를 달성했다는 뜻은 아니다.

C1에서 없앤 SELECT는 474장당 코드 경로상 948회다. RDS에 `pg_stat_statements`가 없어 서버 카운터로 직접 확인한 횟수는 아니다. Q2는 prepared statement 카운터와 auto/custom/generic 비교로 원인을 좁혔으며 어느 SQL 조건 하나만이 유일한 원인이라고 단정하지 않았다.

검색 API 결과에는 Vercel·공개 터널·인증·브라우저 렌더링 시간이 없다. 기준/후보를 번갈아 재시작한 API 시험도 아니므로 환경 변화 가능성이 있다. 별도의 SQL 교차 실험과 캐시 실험이 원인 분리를 보강한다. **각 개선율을 더하거나 업로드·라벨링 전체의 개선율로 사용하지 않는다.**

근거: [G2 전후](evidence/optimization-2026-11-18/G2/report.md), [G2 품질](evidence/optimization-2026-11-18/G2/quality-with-gt.json), [C1 전후](evidence/optimization-2026-11-18/C1/report.md), [Q2/Q3 및 실제 검색 API](optimization-resume-2026-11-18.md).

## 2. 어떤 로그를 어디까지 남겼나

| 계층·로그 | 남긴 항목 | 확인하려던 문제 |
|---|---|---|
| HTTP / UPLOAD_CLIENT | 요청·route·status·시간, 클라이언트 업로드 시간 | 브라우저 보고 시간과 서버 처리 경계 구분 |
| UPLOAD_TRANSFER / UPLOAD_STAGE / DB_IMPORT | 파일 수신·로컬 기록·DB lock/update·트랜잭션·압축 해제·원본 보관·catalog 등록 | 큰 파일 전송, 압축 해제, DB 등록 중 어디서 대기하는가 |
| CLIP / CLIP_INDEX | source_ms, exists_ms, cache_ms, ai_ms, storage_ms, total_ms, 완료 이미지 수 | GPU 추론 이전의 이미지별 DB 왕복과 저장 비용 |
| CLIP_STAGE | lock 대기, 이미지 decode·preprocess·GPU 호출 구간·handler, 텍스트 cache hit/miss·추론 | GPU 바쁨과 CPU/lock 대기, 반복 텍스트 재추론 분리 |
| SEARCH / SQL 실험 | ai_ms·db_mapping_ms·total_ms, EXPLAIN ANALYZE/BUFFERS, 준비문 계획 카운터, 순서 있는 결과 | CLIP 지연과 DB 실행 계획·거리 계산 지연 구분 |
| VESPA / AUTO_LABEL / DS2L_STAGE | job/run/scene, 시작·완료·실패, wall_seconds·cpu_seconds, 모델 getter, 각 처리 단계 | import·데이터·지면 제거·검출·분할·3D·저장 시간 분리 |
| S3_TRANSFER / UPLOAD_CACHE | 파일 크기·mode·파트·동시성·요청 시간·상태, retry/abort·완료 불명 상태, 캐시 경로 | 네트워크 병렬화 효과, 부분 전송·정리 실패, 캐시 miss 비용 |
| RERUN_STAGE / RECORDING | 3D 기록 생성·전송·다운로드/Range 검증 | 라벨 추론과 결과 시각화 준비 비용 구분 |
| 별도 자원 표본 | GPU 사용률·메모리·전력·온도, Docker CPU/RAM/I/O, 호스트·cgroup 메모리/swap/pressure | 자원 압박과 단계 시간의 관계. 모든 실행에 완전한 표본이 있는 것은 아님 |
| 재현·품질 파일 | 명령·환경·소스/이미지 digest·종료 코드, stdout/stderr, 벡터/박스/track 비교, GT, SHA256 | 빨라진 이유를 추적하고 실패·정확도 저하를 숨기지 않기 |

수집기는 허용된 구조화 필드만 모아 `events.jsonl`에 저장하고 `report.json`/`report.md`에 호출 수·합계·p50·p95·최댓값을 집계한다. job/run/upload별로 나눈다. 자유 형식 로그나 인증 헤더 전체를 공개하는 방식이 아니다. CLI 실행·실패 로그와 민감할 수 있는 원본은 별도 로컬 보관하며 검토용 파일만 선택해 Git으로 내보낸다.

**계측 한계도 남긴다.** 부모/자식 span은 중첩되므로 합산하면 안 된다. `gpu_ms`나 stage wall time은 순수 CUDA kernel 시간이 아니다. 자원 표본은 peak나 GPU별 연산 기여율을 뜻하지 않는다. 현재 공용 collector의 허용 필드에는 텍스트 원본 로그의 `encode_ms`가 없어 그 값은 일반 `events.jsonl`에 보존되지 않는다. 텍스트 실험의 상세 성능은 해당 benchmark 결과를 함께 확인해야 하며 collector 보강은 남은 계측 작업이다.

마지막 수집본은 **11,096이벤트, 분류된 실패 이벤트 0, 수집 오류 0**이다. 이 숫자는 모든 과거 실험에 실패가 없었다는 뜻이 아니다. 중단·dtype 오류·품질 불일치·CI 실패는 각각의 실험 폴더에 남아 있다.

위치와 생성 코드:

- 원본: 원래 `DriveScene2Label` 작업 트리의 `.local/hybrid/measurements/20261118T091728Z/` 및 `.local/hybrid/experiments/`. 문서용 worktree에 원본 전체를 복사하지 않았다.
- 공유본: [마감 report](reports/2026-11-18/report.md), [집계 report](evidence/session-close-2026-11-18/measurement/report.md), [job 14 단계 JSONL](evidence/session-close-2026-11-18/user-job14/stage-events.jsonl), [증거 manifest](evidence/session-close-2026-11-18/manifest.json).
- 도구: [measurement.py](../scripts/hybrid/measurement.py), [record_command.py](../scripts/hybrid/record_command.py), [sample_resources.py](../scripts/hybrid/sample_resources.py), [model_load_report.py](../scripts/hybrid/model_load_report.py), [export_review_evidence.py](../scripts/hybrid/export_review_evidence.py).

## 3. S3는 무엇이 좋아졌고 무엇은 아직 불확실한가

| 케이스 | 이전·비교 조건 | 결과 | 해석 |
|---|---|---|---|
| S1 캐시 | 추출된 캐시 / 로컬 압축본만 있음 / S3에서 다시 받음 | 같은 13파일 GET 총 **0.359 / 71.078 / 431.500초** | 기존 캐시의 효과를 확인. 이번에 S3 자체를 몇백 배 빠르게 바꾼 수치가 아님 |
| S2 Python 전송 | 109.7MB, 단일 stream과 제한된 병렬 전송 | **13.107→4.996초, 61.88% 감소**, SHA 일치 | Python SDK 실험. Java 앱·브라우저·4GB 파일에 그대로 적용 불가 |
| S3-J Java 전송 | 실제 4.17GB, single PUT과 최대 4파트 병렬 | 3쌍 시간 감소 **-1.54% / 12.50% / 4.21%** | 항상 빠르지 않아 코드 기본값 OFF. 마지막 운영 설정에서는 업로드 완료 후 ON |
| S3-J 실패 처리 | 다운로드 최종 파일 오염·실패 후 multipart 상태 불명 위험 | 임시 `.part`, 완전성 확인 후 이동, retry·abort·Complete 응답 유실 대조, 중단 경쟁 조건 보완 | 속도와 별개의 신뢰성 개선. 성공 파일 SHA와 실패 정리 검증 |

실제 S3를 사용한 장애 시험은 일시적 파트 503, 지속 503, Complete 성공 응답 유실, 다운로드 중단, 프로세스 SIGKILL이다. 503은 시험 interceptor로 주입했다. 강제 종료 뒤 자동 재개는 구현하지 않았으며 정확한 upload ID로 운영자 정리했다. 후속 취소 경합을 포함한 관련 회귀 65개와 실제 왕복·5종 장애 재검증을 기록했다.

브라우저→백엔드의 조각 업로드는 순차다. 백엔드→S3의 병렬 파트 전송과 구분한다. dataset 22의 사용자 업로드는 single PUT 기준선이며 그 뒤 켠 multipart의 효과로 주장하지 않는다. 병렬화에는 스레드·메모리·요청 수·대역폭 경쟁 비용이 있다.

근거: [Java S3 전후·장애·선택 이유](s3-java-optimization-2026-11-18.md), [S3 안전성 후속 증거](evidence/s3-interruption-2026-11-18/README.md), [전체 사이클·캐시 비교](optimization-results-2026-11-18.md).

## 4. VESPA는 왜 아직 오래 걸리나

여기서 VESPA는 Grounding DINO·SAM·DINOv2와 점군 기하 처리를 묶은 **3D 자동 라벨링 파이프라인**이다. 검색 엔진 Vespa로 설명하지 않는다. CLIP 검색 임베딩은 별도 경로다. 마지막 배포 모델은 `grounding-dino-base`, `sam-vit-base`, `dinov2_vitb14_reg`이며 DINOv3·SAM2로 교체한 상태가 아니다.

| 계층 | 주 자원 | 남은 부담 |
|---|---|---|
| 실행 환경·데이터 로딩 | CPU·RAM·디스크, 캐시 miss 시 S3 네트워크 | import·압축 해제·파일 읽기·배열 구성 |
| 지면 제거 | CPU·RAM·디스크 | LiDAR 누적·RANSAC, 전체 382 sweep의 지면 계산·NPZ 기록 |
| Grounding DINO | CPU 전처리·전송 + GPU/VRAM 추론 | 이미지 전처리만 줄였고 클래스별 forward는 여전히 반복 |
| SAM | GPU/VRAM + CPU/RAM·캐시 | 마스크 추론·변환·정리·NMS |
| LiDAR 투영·노이즈 제거 | CPU·RAM | 2D 마스크와 점군의 기하 계산·배열 처리 |
| DINOv2 | CPU 전처리 → GPU → CPU RAM | feature 추출 후 CPU 복사·객체별 집계 |
| 카메라 병합·추적·3D 박스 | CPU·RAM·디스크 | 병합·속도·yaw·track·중간 캐시 |
| 결과 저장 | CPU·디스크·RDS 네트워크 | 직렬화·검증·DB 저장 |

**여러 자원을 쓴다는 사실과 overhead가 주원인이라는 결론은 다르다.** 단계 의존성, 전처리, 복사, 동기화, 중간 파일, 프로세스 재생성은 비용 후보다. 현재 로그는 순수 GPU 계산·H2D/D2H 복사·대기·할당을 충분히 분리하지 않았으므로 “대부분 전송 overhead”라고 단정할 수 없다. CPU 단계에서 GPU가 쉬는 모습만으로 GPU 고장을 판단하지 않는다.

job 14의 AI executor는 **4,072.075초**였다. 이미지 검출·분할 부모 구간 **3,139.559초, 약 77.1%** 안에 Grounding **1,569.743초**, SAM **1,395.867초**가 포함된다. 지면 제거 **349.953초**, DINOv2 **217.388초**, 후처리 캐시 저장 **89.569초**였다. backend 결과 저장 **29.466초**는 executor 밖의 별도 경계이며 순수 DB SQL 시간도 아니다.

이 사용자 실행은 앞의 G2 통제 비교와 환경이 같지 않다. RAM 95~97%인 시점이 있었지만 느려진 유일한 원인이나 paging 발생량을 입증하지 않는다. **G2의 2,173초와 job 14의 4,072초로 성능 회귀율을 만들지 않는다.**

### CLIP은 상주하고 VESPA는 왜 매번 로드하는가

CLIP은 FastAPI lifespan에서 모델을 올리고 서비스 객체가 살아 있는 동안 재사용한다. VESPA는 요청마다 별도 자식 프로세스에서 모델을 필요할 때 로드한다. 같은 작업에서는 singleton을 재사용하지만 프로세스가 종료되면 그 작업의 모델 수명도 끝난다.

**VESPA 모델 GPU 상주는 기술적으로 가능하다. 지금 배포 코드가 그렇게 구성되지 않았고 새 worker의 검증이 끝나지 않은 것이다.** RAM·VRAM이 충분한지, 작업 데이터가 해제되는지, CLIP과 공존하는지, 오류/시간 초과 뒤 복구되는지를 확인해야 한다. 가중치 preload와 첫 입력 inference warmup도 다르다.

job 14의 첫 getter는 Grounding **15.594초**, SAM **5.746초**, 이후 38회 중앙값은 각각 **0.000015초 / 0.000006초**였다. 확인된 두 초기 로딩의 합은 약 **21.34초**다. 상주화로 이 시간이 없어지는 이상적인 경우도 이 두 항목만으로 전체 약 4,072초를 크게 줄일 수는 없다. DINOv2 로딩은 해당 배포에 getter 계측이 없어 총 로딩 절감량을 단정하지 않는다. 상주화는 특히 첫 응답·반복 작업 준비 지연을 개선하는 후보이며 Grounding/SAM의 반복 forward를 없애지 않는다.

근거: [자원 지도·이미지](vespa-resource-map-2026-11-18.md), [병목 진단](vespa-bottleneck-diagnosis-2026-11-18.md), [job 14 실제 단계 시간](evidence/session-close-2026-11-18/summary.json), [모델 로딩](evidence/session-close-2026-11-18/user-job14/model-load.md).

## 5. 사용자가 제안해서 검토한 방법과 해결하지 못한 이유

대화에서 사용자가 질문·제안한 방향과 실제 실행 증거를 연결했다. 아래의 “실행”은 프로젝트에서 도구로 수행하고 로그를 남긴 시험을 뜻한다. 제안자가 모든 코드를 직접 작성·실행했다고 확대하지 않는다.

| 제안·시도 | 실행 결과 | 현재 판단·남은 일 |
|---|---|---|
| CPU 스레드 늘리기, 과도한 경쟁 방지 | 1·2·4 비교, 일부 단계 가속. 2스레드 전체 씬은 최종 한 박스 9필드 차이 | GT 집계가 같아도 엄격한 출력 일치 기준에서 보류. native thread 1 유지 |
| FlashAttention / SDPA | 현재 Transformers 4.49.0 Grounding 조합에서 미지원 오류 | 설정만으로 활성화 실패. 5060 Ti가 원천적으로 불가능하다는 결론이 아님. 모델 연산·커널 경로 지원 검토 필요 |
| FP16/BF16로 비트 낮추기 | 전체 cast는 dtype 불일치. AMP FP16은 **30.198→22.428초**, 45박스 유지하나 최소 IoU 0.994792·점수 차이 | 소량 forward 가속만 확인. 전체 씬 3D·track·GT 품질 기준 전 보류 |
| BF16 / TF32 | BF16은 45박스 중 1개 누락, TF32도 박스·점수 차이 | 출력 완전 일치 기본값으로 채택하지 않음. 품질 허용 범위를 정한다면 재평가 가능 |
| ONNX Runtime CUDA | export/checker/실행 성공, raw 출력 일치 실패 | 실행 성공과 품질 통과는 다름. 제한된 입력 외 전체 클래스·3D 미검증 |
| TensorRT | 엔진 빌드 **143.666초**, 제한된 추론 중앙값 **0.2122초**, 6카메라 자동차 대응 | 박스·점수/raw 차이, 전체 클래스·3D 미검증. 엔진 교체 보류. 사용자 중지 exit 137을 OOM으로 부르지 않음 |
| INT8 / INT4 | 미실행 | calibration 데이터·지원 연산·품질 허용 기준 준비 필요. 실패 실험으로 표시하지 않음 |
| G3: CPU 지면 제거 범위 축소 | 382 sweep 전체에서 실제 소비되는 39키프레임 지면만 계산하는 후보 준비. 이웃 raw sweep 누적은 보존 | 첫 기준선 중 사용자 요청으로 종료, exit 143. 전후 개선율·3D 검증 없음, 미적용 |
| R3: VESPA GPU 상주 | 직렬 resident worker와 작업별 상태 정리 후보 준비, GPU 없는 helper 시험 11개 통과 | 실제 GPU 상주·VRAM·반복 씬·오류 복구·3D 비교 미실행, 미적용 |
| CLIP 이미지 batch C2 | 별도 팀 커밋. 64장/호출, 실제 256장 최소 cosine 0.99999982 | M5 MPS에서 속도 차이 없음, 5060 Ti 전후 미측정. 기본 OFF. 기존 C1 성과와 구분 |
| N+1·중복 쿼리·인증 조사 | C1의 이미지별 중복 조회와 Q2 검색 개선은 적용 | 인증 중복 제거 성과는 입증하지 않음. Q4 카메라 metadata 묶음, Q5 라벨 INSERT batch는 미적용 후보 |
| S3 병렬·캐시·저장 구조 | 기존 캐시 효과, Python/Java 병렬 전송과 실제 장애 검증 | Java 대용량은 효과 편차. 브라우저 병렬·씬별 저장·필요 범위 다운로드는 별도 설계/검증 필요 |
| Redis·DynamoDB·Elasticsearch·Kafka·Spark/Hadoop | 역할·교체 가능성 질문과 검토 | 운영 도입/이전 없음. 모델 계산·작은 요청 DB 왕복·대용량 분석은 다른 문제이므로 이름만 추가해 빨라진다고 결론 내리지 않음 |

수치 오차가 있다는 이유만으로 AMP나 TensorRT가 실용적으로 쓸 수 없다는 뜻은 아니다. 이번 기본값의 출력 보존 기준을 아직 통과하지 못한 것이다. 허용 가능한 2D/3D 오차·검출 누락·track 변화와 정확도 예산을 먼저 정하면 다음 실험의 판단 기준이 달라질 수 있다.

## 6. 코드 위치·선택 이유와 남은 검증

| 변경 | 코드 | 선택 이유·비용 |
|---|---|---|
| G2 | [grounding_probe.py](../ai-server/services/grounding_probe.py), [grounding_runtime.py](../ai-server/services/grounding_runtime.py) | 모델 의미를 유지하며 반복 전처리 제거. forward 비용은 남음 |
| C1 | [DatasetSearchIndexService](../src/main/java/com/example/demo/nuscenes/service/DatasetSearchIndexService.java), [ImageEmbeddingService](../src/main/java/com/example/demo/nuscenes/service/ImageEmbeddingService.java) | 이미 얻은 데이터를 재사용해 RDS 왕복 절감. 기존 동시성·중복 저장 방어 유지 |
| Q2 | [SceneSearchRepository](../src/main/java/com/example/demo/nuscenes/repository/SceneSearchRepository.java) | exact 결과 유지. 매 요청 계획·SET LOCAL 왕복 비용, materialization 임시 I/O 증가 가능 |
| Q3·CLIP 상주 | [clip_service.py](../ai-server/services/clip_service.py), [main.py](../ai-server/main.py) | 별도 Redis 없이 제한된 메모리 캐시. 프로세스 종료 시 사라지며 no-hit에는 이득 없음 |
| S3-J | [UploadArchiveStore](../src/main/java/com/example/demo/nuscenes/storage/UploadArchiveStore.java), [MultipartArchiveUploader](../src/main/java/com/example/demo/nuscenes/storage/MultipartArchiveUploader.java) | 병렬도 제한과 실패 정리를 명시적으로 검증. 요청 수·스레드·대역폭 비용 |
| VESPA 수명·계측 | [vespa_service.py](../ai-server/services/vespa_service.py), [vespa_runner.py](../ai-server/services/vespa_runner.py) | 현재 작업별 프로세스 수명. G3/R3 미검증 코드는 원래 로컬 작업 트리에 별도 보존 |

다음 실험의 우선순위는 **G3 CPU 지면 계산 범위**와 **R3 작업 간 모델 유지**다. G3는 소비 키프레임의 mask/변환/cone와 전체 3D/track/GT를 비교하고, R3는 시작/준비 시간·첫 작업/다음 작업·RSS/VRAM·CLIP 공존·실패 복구를 비교한다. baseline/candidate 순서를 바꾸고 같은 입력·캐시·스레드·정밀도로 반복해 새 로그를 남겨야 한다. R3의 주된 목표는 준비 지연이며 전체 실행시간 최대 병목은 여전히 Grounding/SAM이다.

그 뒤 CUDA profiling으로 실제 forward·H2D/D2H·CPU 대기를 분리하고, 품질 허용 기준에 따라 AMP/엔진을 재평가한다. DB 라벨 저장 batch는 다른 실험으로 떼어낸다. 이것은 **후속 제안이며 이번에 새 시험을 실행했다는 뜻이 아니다.**

마지막 종료 확인은 2026-11-18 21:06 KST의 RDS stopped, 로컬 컨테이너/터널 종료, Vercel DEPLOYMENT_PAUSED다. [종료 증거](evidence/session-close-2026-11-18/shutdown/summary.json)를 보존한다. 이번 정리는 성능 변경·배포를 추가하지 않는다.
