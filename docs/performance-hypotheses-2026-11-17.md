# 성능 개선 사례 설계 — 2026-11-17

> 후속 실측·채택 판단은 [2026-11-18 통합 보고서](optimization-results-2026-11-18.md)에 정리했다. 아래의 현재 단계·환경 설명은 초기 가설 수립 시점의 기록이다.

> 계측 후 갱신: C0 통합 기준선과 G0/G1 비교를 완료했다. 현재 판정·실행 상태는 [실험 기록](optimization-experiment-log.md)을 따른다. 아래의 미실측 가설·목표는 조사 시점의 제안이며 완료 성과로 읽지 않는다.

공식 문서·설치 소스를 추가 대조한 [후속 조사](optimization-research-2026-11-17.md)에 전처리 재사용과 복수 클래스 추론의 분리, CLIP crop batch, SAM boolean 후처리, AWS 공유 캐시 제약을 정리했다. 아래의 큰 케이스 선정은 유지하되 구체적인 실험 순서는 후속 조사를 함께 참고한다.

현재 단계는 **환경·기존 증거 확인 → 원인 가설 → 검증할 실험 선택**이다. 2026-11-17에 최신 이미지로 CLIP 단독 추론 2,424회를 완료했다. 전체 185.016초, 요청 p50/p95 72.282/92.742 ms였으며 자세한 조건과 한계는 `.local/hybrid/measurements/20261117T122714Z/report.md`에 있다. 업로드·RDS·S3·스케줄러가 빠진 측정이므로 과거 통합 실행과의 속도 향상 배수로 비교할 수 없다. 모델 교체와 새로운 AWS 컴퓨트 배포는 아직 실행하지 않았다. 기존 CLIP_STAGE와 VESPA 단계 계측은 최신 이미지에 포함돼 있다.

## 0. 케이스를 나눈 뒤 우선 다룰 두 가지

2026-11-17 사용자 요청에 따라 다음 실행에 앞서 케이스 선정부터 정리한다. 목표는 **자동 라벨 생성 완료시간**과 **업로드 후 검색 가능해지는 시간**을 각각 줄이는 것이다. 서로 다른 작업의 시간을 하나의 개선율로 합치지 않는다.

| 케이스 | 현재 근거 | 확인할 가설 | 우선순위 |
|---|---|---|---|
| A. VESPA 검출의 반복 추론 | 과거 완료 씬에서 Grounding DINO 1,035.422초, executor의 57.3%. 설치된 pipeline에 클래스별 전처리·입력 생성 루프 존재 | 10개 클래스별 반복 실행을 줄이면 가장 큰 구간이 줄어드는가 | **선정 1** |
| B. SAM의 추론·마스크 후처리 | 같은 과거 씬에서 433.334초, 24.0%. `pred_masks.cpu()` 이후 해상도 복원 | GPU 실행과 CPU 마스크 복원 중 어디가 큰가 | A 이후 재평가할 대체 후보 |
| C. CLIP 검색 준비의 직렬 SQL·HTTP 처리 | 신규 이미지당 source·exists·upsert 3 SQL. 과거 2,424장 기록에 긴 호출 공백 존재. 최신 단독 API는 185.016초 | 최신 scheduler 수정 후에도 항목별 왕복·저장이 전체 인덱싱을 지배하는가 | **선정 2의 첫 검증** |
| D. CLIP 모델 실행·전처리 | 최신 단독 시험에서 `gpu_ms` 합계 98.825초, 전처리 52.969초. handler 합계의 약 58.1%·31.1% | C의 외부 지연을 구분한 뒤 이미지 batch 또는 전처리 병렬화가 처리량을 높이는가 | 선정 2에서 별도 변경으로 비교 |
| E. CPU·메모리·장치 전송 | 단일 스레드 설정과 과거 낮은 가용 메모리 표본. 같은 실행의 원인 증거는 부족 | 메모리 압박·CPU 대기·전송 때문에 GPU가 기다리는가 | 두 케이스의 공통 자원 계측 |
| F. DB 검색·AWS 배치 | 검색 표본 3회뿐. backend와 RDS 사이 네트워크 비용은 미분리 | 데이터 규모 또는 배치 위치가 지연을 지배하는가 | 기준선 확보 후 검증 |

### 선정 1: VESPA 검출 호출 구조 개선

- **문제:** 자동 라벨 생성 약 30분 중 관측상 가장 큰 검출 구간을 줄인다.
- **첫 실험:** 고정된 대표 이미지 6–12장에서 실제 model forward·processor 호출 수를 센다. 코드상 이미지당 10회라는 예측을 런타임으로 확인한다.
- **첫 변경 후보:** 같은 Grounding DINO 가중치를 유지하고 복수 클래스 직접 API를 비교한다. 해상도·정밀도·모델까지 동시에 바꾸지 않는다.
- **성과 지표:** 검출 구간 시간, 씬 전체 완료시간, peak VRAM, 클래스별 검출 품질과 최종 3D 라벨 품질. 호출 수 감소만으로 성공을 선언하지 않는다.
- **채택 조건:** 대표 입력 반복 측정과 전체 씬 검증에서 시간 감소가 재현되고, 미리 정한 품질 기준을 충족해야 한다. 프롬프트 변경으로 누락·오검출이 늘면 채택하지 않고 전처리 재사용 또는 SAM 병목을 검토한다.

### 선정 2: CLIP 인덱싱 전체 경로 개선

- **문제:** 이미지 업로드 후 검색 인덱스가 완료되기까지의 대기를 줄인다. 단독 API 185초는 이 전체 시간과 다르다.
- **첫 실험:** 이미 반영된 `878297b`를 기준선으로 삼고, 기존 RDS·S3를 유지한 통합 실행에서 SQL 횟수·왕복 시간, AI 시간, 저장 시간, 호출 사이 공백을 구분한다. 영호의 scheduler 개선 효과와 이후 변경 효과를 분리한다.
- **변경 순서:** (1) 누락 이미지 메타데이터 일괄 조회, (2) 벡터 일괄 저장, (3) 여러 이미지의 CLIP batch 요청. 각 단계에서 기준선 또는 직전 단계와 비교해 효과가 없는 변경은 제외한다. 세 변경을 한 번에 적용하지 않는다.
- **성과 지표:** 업로드→검색 준비 완료시간, 인덱싱 시간, 이미지/초, SQL 수, 이미지 누락·중복 수, 재시도 복구, 벡터·검색 결과 회귀.
- **채택 조건:** 완료 이미지 수 2,424/2,424와 멱등성을 유지하고 전체 준비시간 감소가 재현돼야 한다. 모델·crop·정규화는 고정한다. SQL 왕복이 작으면 GPU batch/전처리 쪽을 우선하고 DB 변경의 효과를 과장하지 않는다.

두 가지를 선택한 이유는 A가 **측정상 가장 큰 추론 구간**이고, C/D는 **사용자가 기다리는 별도의 검색 준비 경로**이기 때문이다. SAM 역시 큰 후보지만 먼저 두 작업 경로의 기준선을 확보한다. 목표를 자동 라벨 생성 하나로 좁힌다면 A+B 조합이 더 적합하다.

진행 순서는 **케이스 선정 → 필요한 세부 로그 → 현재 코드 기준선 → 한 변경씩 비교 → 전체 경로 검증 → 동일 코드의 AWS 비교**다. AWS에서는 기존 RDS·S3를 유지하며, 코드 최적화와 서버 이전 효과를 각각 측정한다. 현재 개선율과 클라우드 성능 향상은 확정하지 않았다.

## 1. 확인한 환경과 처리 경로

| 항목 | 확인 결과 |
|---|---|
| 소스 | `release-version`, `878297b` |
| GPU | NVIDIA RTX 5060 Ti, 16,311 MiB VRAM, 드라이버 610.88 |
| CPU / 호스트 RAM | Core Ultra 7 258V, 8코어·8스레드 / 약 31.5 GiB |
| Docker / WSL | 엔진 28.5.1, CPU 8개, 메모리 24GB 설정, swap 16GB |
| 컨테이너 자원 | backend·AI 개별 CPU/메모리 상한 미설정, AI shared memory 2GiB, GPU 1개 요청 |
| GPU 연결 | 유휴 조회에서 PCIe Gen2 ×4; 최대 링크 정보는 Gen4 ×16. 부하 중 링크·실제 전송률은 미측정 |
| VESPA | local executor, `VESPA_NUM_THREADS=1`, timeout 7,200초, rigid 후처리 기본 활성화 |
| CLIP | `ViT-L-14-quickgelu/openai`, 768차원, 좌우 crop 평균, 이미지별 요청 |
| VESPA 검출 / 분할 / 외형 특징 | `IDEA-Research/grounding-dino-base` / `facebook/sam-vit-base` / `dinov2_vitb14_reg` |
| 라이브러리 지정 버전 | PyTorch 2.14.1, OpenCLIP 3.3.0, VESPA 환경 Transformers 4.49.0 |
| CLIP 단독 시험 시 실행 상태 | AI 실행, backend Created. RDS·S3를 포함한 통합 시험과 별도 |

실제 컨테이너에서 실행 없이 복사한 소스와 환경 조회는 `.local/hybrid/profiling-source/`에 있다. 모델 dtype, 연산 중 클럭, 실제 PyTorch 스레드 수는 런타임 측정 대상이다. 코드에 AMP가 없다는 이유만으로 모든 연산이 FP32라고 확정하지 않는다.

처리 경로는 다음 세 가지로 나뉜다.

1. **업로드·검색 준비:** 브라우저 → Spring 수신·압축 해제 → S3 보관·RDS 등록 → 이미지 CLIP 임베딩 → RDS 벡터 저장.
2. **자연어 검색:** 질의 CLIP 임베딩 → RDS pgvector 거리 계산·씬별 집계 → 결과 응답.
3. **자동 라벨 생성:** 로컬 캐시 → 지면 제거 → Grounding DINO 검출 → SAM 분할 → DINOv2 특징 → 3D 후처리 → RDS 결과 저장.

Vercel은 프런트엔드와 API 진입 경로에 있다. 위 모델의 GPU 계산은 로컬 AI에서 수행한다. VESPA 전체를 단일 임베딩 모델이라고 부르면 병목을 잘못 구분하게 된다.

## 2. 기존 관측값: 새 빌드의 성능 측정 결과는 아님

2026-11-12 완료 작업 #12: scene-0061, 39키프레임, 6카메라, 1,308박스. executor 경과 시간은 **1,808.547초, 약 30분 9초**다.

| 구간 | 누적 경과 시간 | executor 대비 | 해석 |
|---|---:|---:|---|
| Grounding DINO | 1,035.422초 | 57.3% | 이미지 단위 wrapper 234회 |
| SAM 추론·후처리 | 433.334초 | 24.0% | 233회, GPU와 CPU 작업이 섞인 구간 |
| DINOv2 외형 특징 | 113.028초 | 6.2% | 검출 모델과 별개 |
| 지면 제거 | 98.517초 | 5.4% | CPU 계산 후보 |
| 검출·분할 상위 구간 | 1,524.246초 | 84.3% | 위 Grounding DINO·SAM 등을 포함하므로 더하면 안 됨 |
| 검출·SAM 모델 획득 | 합계 3.773초 | 약 0.2% | 첫 획득에 로딩 포함, 이후 singleton 재사용 |
| 데이터 준비 | 0.002초 | — | 이 실행은 준비된 캐시를 사용한 사례 |
| 결과 저장 | 10.604초 | — | executor 외부 구간, DB 포함 |

근거: [완료 작업 요약](../.local/hybrid/verification-20261112/job12-completed-summary.json), [계측 보고서](../.local/hybrid/measurements/20261112T071715Z/report.md).

검색용 CLIP의 별도 과거 기록은 2,424장이다. 첫 이벤트부터 마지막까지 865.306초, 이미지별 `total_ms` 합계 210.591초, 그중 AI 요청 합계 147.559초와 저장 합계 25.185초였다. **차이 전체를 DB 또는 GPU 비용이라고 해석할 수 없다.** 최장 이미지 사이 공백은 298.764초이고 작업 대기·중단·다른 작업 개입을 구분해야 한다. 이번 pull에는 claim 유지와 scheduler 대기 감소 변경이 포함됐으므로 새 기준선을 먼저 측정한다.

자연어 검색 기록은 단 3회다. DB·매핑 구간 p50은 110ms, 전체 p50은 326ms였다. 이 표본으로 서비스 p95나 대규모 검색 병목을 주장할 수 없다.

2026-11-11 작업 #5의 다른 자원 표본 18개(170초)에서는 GPU 사용률 2–81%, 중앙값 49%, AI CPU 중앙값 약 104%, 호스트 가용 RAM 중앙값 약 1,816MB였다. 이것은 #12와 다른 실행이며 SAM 변경 전후 비교에도 그대로 사용할 수 없다. 호스트 page-in은 관측됐지만 파일 매핑 등의 영향도 있어 swap 병목으로 확정하지 않는다. CPU 100%는 Docker에서 대략 논리 코어 하나 분량이지 8코어 전체 포화가 아니다.

## 3. 가설과 우선순위

### H1. 검출 API가 동일 이미지를 클래스별로 반복 처리한다 — 최우선

현재 VESPA는 검출 후보 10개를 `candidate_labels`로 전달한다. UI의 8개 결과 클래스와 검출기의 10개 프롬프트는 같은 수가 아니다.

실제 설치된 Transformers 4.49.0의 zero-shot object detection pipeline은 후보 라벨을 순회하며 **각각 이미지 전처리를 수행하고 모델 입력을 생성**한다. pipeline 기본 batch size는 1이고 VESPA에서 변경하지 않는다. 따라서 현재 경로는 한 이미지에 클래스별 모델 호출 10회 구조다. 39 × 6 × 10 = **2,340회**는 이 코드 구조에서 산출한 기대 호출 수이며, 기존 단계 로그가 직접 센 것은 바깥 함수 234회뿐이다.

근거: [설치 버전의 pipeline 소스](https://github.com/huggingface/transformers/blob/v4.49.0/src/transformers/pipelines/zero_shot_object_detection.py#L164), [기본 batch 설정](https://github.com/huggingface/transformers/blob/v4.49.0/src/transformers/pipelines/base.py#L1306). 로컬 복사본에서도 같은 루프를 확인했다.

검증: 이미지별 후보 수, image processor 호출 수, 실제 model forward 호출 수, 전처리/장치 전송/forward/후처리 시간을 센다.

후보 개선: 같은 모델의 직접 API로 여러 클래스를 한 입력 문장에 넣어 추론한다. 공식 API는 복수 클래스 입력과 해당 라벨 후처리를 지원한다. 단, 프롬프트 문맥·점수·라벨 매핑이 바뀔 수 있으므로 동일 출력 최적화로 취급하지 않는다. 단순히 라벨 문자열을 합쳐 기존 pipeline에 넘기는 것으로 끝내지 않는다. [Grounding DINO 사용법](https://huggingface.co/docs/transformers/v4.49.0/en/model_doc/grounding-dino#usage-tips)

판정: 처리 시간과 함께 클래스별 박스 매칭, 누락·오검출, 작은 객체, 최종 3D 라벨 품질을 비교한다. 모델 호출 10→1이 전체 처리 10배를 뜻하지 않는다. 예컨대 해당 검출 구간만 10배 빨라진다는 **가정**에서도 나머지를 고정하면 executor는 약 877초이며, 실제 개선치는 실험해야 한다.

### H2. SAM 구간에 CPU 마스크 후처리와 장치 전송 비용이 크다 — 대체 후보

실제 코드에서 `pred_masks.cpu()` 이후 원본 해상도 마스크 복원과 평균·임계처리·NumPy 변환을 한다. 기존 433초 계측에는 이 CPU 작업과 GPU 모델 실행이 함께 들어 있다. 현재 박스들을 한 이미지 입력으로 전달하므로 박스마다 이미지 인코더를 다시 실행한다고 단정할 근거는 없다. SAM의 inference_mode는 이미 적용돼 있다.

검증: 입력 해상도·박스 수를 기록하고 processor, H2D, 모델 forward, D2H, mask resize, reduction, NMS를 나눈다. 대표 몇 장에서만 CPU/CUDA profiler를 사용한다. 전체 작업에 매번 CUDA synchronize를 넣으면 실행 특성이 달라질 수 있다. [PyTorch Profiler](https://docs.pytorch.org/tutorials/recipes/recipes/profiler_recipe.html)

후보 개선: 측정 후 CPU 처리의 GPU 이동, 마스크 단위 chunk 처리, 전처리 재사용 중 실제 비용이 큰 항목을 선택한다. dtype·보간·임계값을 바꾸면 마스크 IoU와 최종 박스 품질을 검증한다.

### H3. 단일 CPU 스레드·호스트 메모리·eGPU 전송이 GPU에 일을 공급하는 속도를 제한한다

`VESPA_NUM_THREADS=1`은 OMP/OPENBLAS/MKL에 적용된다. 코드에는 작은 RANSAC 선형 연산의 과도한 스레드 생성 비용을 줄이려는 이유가 있다. 1→8을 전역 적용하면 다른 구간은 악화될 수 있다.

검증: H1/H2와 같은 시간축으로 host 가용 메모리, page-in, WSL swap, cgroup CPU throttling·memory/IO pressure, GPU 클럭·전력·사용률·VRAM을 수집한다. 그 뒤 CPU-heavy 구간만 1/2/4스레드로 비교한다. 유휴 PCIe 링크나 짧은 GPU 사용률 표본 하나로 원인을 확정하지 않는다. WSL에서는 일부 NVIDIA 관측 기능에도 제한이 있다. [NVIDIA WSL 안내](https://docs.nvidia.com/cuda/wsl-user-guide/)

### H4. CLIP 인덱싱의 항목별 SQL·HTTP·저장이 준비 시간을 늘린다 — 백엔드 개선 사례

신규 이미지의 정상 경로에는 `source` 조회 → `exists` 조회 → AI 요청 → 개별 upsert가 있다. 2,424장에서는 이 세 SQL만 코드상 약 7,272회이며 claim·heartbeat·상태 조회 등은 별도다. 이것은 ORM의 lazy loading N+1이라고 진단한 것이 아니라 명시적인 항목별 반복 호출이다.

`DatasetSearchIndexService.BATCH_SIZE=64`는 heartbeat/yield 구간 크기다. 실제 GPU batch나 JDBC batch가 아니다.

검증: 이미지 수당 SQL 횟수, source/exists/upsert별 latency, connection 대기, 순수 DB 실행 시간, AI 내부 시간, scheduler 공백을 분리한다. 새 커밋 기준으로 먼저 다시 측정한다.

후보 개선: 누락 이미지 메타데이터 일괄 조회 → 여러 이미지 CLIP 요청 → 벡터 batch 저장. 조회 변경·GPU batch·저장 batch를 각각 적용해 효과를 분리한다. GPU 호출 동안 DB transaction을 유지하지 않으며, unique key/upsert·실패 복구·부분 batch 재시도의 멱등성을 유지한다. 모델·crop·정규화 규칙도 고정한다.

근거: [ImageEmbeddingRepository](../src/main/java/com/example/demo/nuscenes/repository/ImageEmbeddingRepository.java), [ImageEmbeddingService](../src/main/java/com/example/demo/nuscenes/service/ImageEmbeddingService.java), [DatasetSearchIndexService](../src/main/java/com/example/demo/nuscenes/service/DatasetSearchIndexService.java).

### H5. 씬 검색의 거리 계산·정렬·집계는 데이터가 커질 때 병목이 될 수 있다 — 후순위

현재 쿼리는 유효 이미지의 거리 계산 → 씬별 window 순위 → MAX/AVERAGE/TOP_K_AVERAGE 집계 → 씬 LIMIT 순서다. 마이그레이션에는 벡터 ANN 인덱스가 없지만, 실행 중 DB의 별도 인덱스 유무는 아직 확인하지 않았다. 작은 데이터에서 인덱스 부재만으로 느리다고 결론 내리지 않는다.

검증: 동일 데이터·질의 집합으로 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`의 실제 행 수·loops·정렬·temp spill을 확인한다. 데이터셋 필터 유무와 크기를 바꾼다. EXPLAIN ANALYZE는 실제 실행하므로 선택한 읽기 쿼리로 범위를 제한한다. [PostgreSQL 실행 계획](https://www.postgresql.org/docs/current/using-explain.html)

후보 개선: 먼저 정확한 씬 집계를 보존한 join/필터/인덱스 개선을 비교한다. ANN으로 이미지 후보를 먼저 제한하면 씬 평균과 순위 의미가 달라질 수 있다. ANN을 검토할 때는 기존 exact 검색을 기준으로 **씬 단위 Recall@K·순위 일치율**을 평가한다. HNSW를 추가하기만 하면 현재 집계 쿼리가 자동으로 빨라진다는 보장은 없다. [pgvector 공식 설명](https://github.com/pgvector/pgvector)

## 4. 먼저 선택할 실험

| 순서 | 실험 | 고정 조건 | 판단 자료 |
|---|---|---|---|
| E0 필수 | 대표 이미지 소량으로 현재 검출·SAM 세부 계측 | 같은 이미지·10개 클래스·모델·해상도·dtype·threshold·캐시 | 호출 수, CPU/CUDA 구간, VRAM, 결과 수 |
| E1 우선 | 기존 클래스별 pipeline vs 다중 클래스 직접 API | 같은 Grounding DINO 가중치·입력 | latency, 클래스별 박스 일치·누락, 최종 라벨 품질 |
| E2 병행 가능한 별도 사례 | CLIP 항목별 DB 호출 vs 일괄 조회/저장 | 같은 벡터·데이터·RDS·캐시, GPU 변경은 별도 | SQL 수, DB 왕복, 이미지/초, 멱등성·실패 복구 |
| E3 조건부 | SAM CPU 후처리 최적화 또는 CPU 스레드 비교 | 같은 검출 박스·입력·마스크 규칙 | 해당 구간 시간·peak memory·마스크 일치 |
| E4 이후 | 최적화한 동일 앱의 로컬 vs 클라우드 실행 | 같은 이미지 digest·가중치·입력·설정, cache 상태 구분 | 씬 완료시간, 준비시간, 처리량, 비용/씬 |

E0은 대표 6–12장으로 먼저 본다. cold 시작은 별도 기록하고, warm-up 이후 동일 입력을 최소 3회 반복해 시간과 분산을 본다. 소표본의 p95를 서비스 SLA로 제시하지 않는다. profiler를 켠 실행과 성능 측정 실행을 구분한다. 소량 시험을 통과한 후보만 고정된 한 씬 전체로 검증한다.

정확도 기준은 실험 전에 정한다. 원본과 결과 일치는 회귀 지표이며 정답 정확도와 동일하지 않다. 정답 라벨이 있으면 그것으로 측정하고, 없으면 사람이 확인한 평가셋과 baseline 차이를 구분해서 기록한다. 작은 물체·가림·혼잡한 이미지도 포함한다.

## 5. 필요한 로그와 현재 준비 상태

| 기록 | 현재 | 보완할 항목 |
|---|---|---|
| CLIP 내부 | lock/decode/preprocess/gpu/handler 시간 있음 | 이미지·요청 상관 ID, batch 크기, 실제 dtype |
| VESPA 단계 | Grounding DINO·SAM·DINOv2·CPU 단계 wall/CPU 시간 있음 | 검출 내부 forward·processor 호출 수, CPU/CUDA 세부 구간 |
| GPU·호스트 | `diagnose.py` 별도 사용 가능 | 이벤트와 같은 디렉터리·시간축, 작업 번호 없이 CLIP부터 수집 |
| SQL | AI 요청·저장·검색 경계 시간 있음 | source/exists/upsert 개별 시간·호출 수, connection 대기 |
| 실험 manifest | Git revision·dirty 여부 있음 | image digest, 모델·버전·dtype·스레드, 입력 ID·크기, cold/warm, 공개/loopback, 동시 작업 |

작업 번호 없이 자원만 수집하는 로컬 보조 스크립트 `.local/hybrid/sample-resources.py`를 준비하고 유휴 상태에서 1회 동작을 확인했다. GPU·Docker·호스트 메모리·cgroup 정보를 같은 시간축에 저장하지만 아직 통합 부하와 함께 실행하지 않았다. 모델 내부 호출 수나 SQL 세부 instrumentation은 아직 추가하지 않았다. 가설에 맞는 로그만 추가해 계측 비용을 관리한다. 로그에는 비밀번호·쿠키·토큰·검색 문장·이미지 본문을 넣지 않는다. 기존 수집기 명령은 `python scripts/hybrid/measurement.py begin`, `watch`, `stop`, `collect`이며 앱 시작·추론 명령은 아니다.

## 6. 클라우드 비교를 하나의 면접 사례로 연결하는 방법

비교 순서는 A 기존 로컬 → B 코드 최적화 로컬 → C 같은 최적화 코드의 클라우드다. 소프트웨어 변경과 장비 변경을 동시에 한 비교로 각각의 효과를 주장하지 않는다.

클라우드 실험은 다음 질문별로 분리한다.

- **AI worker의 GPU·CPU·메모리 차이가 추론을 줄이는가?** 캐시된 동일 입력과 동일 모델로 비교한다. GPU 교체만의 효과를 주장하려면 CPU·OS·메모리 등 차이도 고려한다.
- **Spring과 RDS를 가까이 배치하면 반복 SQL 비용이 줄어드는가?** 모델 실행을 제외한 DB 경계와 SQL 수를 따로 비교한다. AI API까지 멀어지는 구성이라면 새 경계 비용도 잰다.
- **S3와 연산을 같은 리전에 배치하면 cold 데이터 준비가 줄어드는가?** 원본 다운로드·해제·모델 준비와 warm 추론을 분리한다.
- **PC가 꺼져도 작업을 이어갈 운영 가치가 있는가?** 지연시간과 별도로 queue 대기·재시도·장애 복구·가용성 기준을 정한다.

GPU 후보군으로 AWS G6(L4)·G6e(L40S) 등을 검토할 수 있지만 아직 인스턴스를 선정하지 않았다. 리전 가용성·할당량·메모리·현재 요금을 확인한 후 후보를 좁힌다. 서비스 마케팅 배수를 이 프로젝트 예상 개선률로 사용하지 않는다. [AWS GPU 인스턴스 안내](https://docs.aws.amazon.com/dlami/latest/devguide/gpu.html)

비용은 GPU 추론 시간만이 아니라 인스턴스 준비·모델 로딩·유휴시간·스토리지·전송을 포함한 **완료 씬당 비용**으로 비교한다. 현재 자료만으로 클라우드가 더 빠르거나 저렴하다고 결론 내릴 수 없다.

면접 설명의 형태:

> 씬 하나가 약 30분 걸려 단계별 계측을 했고, 해당 실행의 57%가 검출 구간임을 확인했습니다. 설치된 라이브러리까지 따라가 동일 이미지를 클래스별로 반복 처리하는 구조를 발견했습니다. 이를 호출 수와 CPU/CUDA 프로파일로 검증하고, 같은 모델의 호출 방식을 바꿨을 때 시간과 정확도가 어떻게 달라지는지 비교하는 실험을 설계했습니다. 별도로 임베딩 저장의 항목별 SQL 왕복을 측정해 batch 처리 후보를 정했습니다. 이후 동일한 최적화 코드로 로컬과 클라우드의 시간·비용을 비교할 계획입니다.

현재 말할 수 있는 것은 **관측·코드 분석·실험 설계**까지다. 개선율·정확도 유지·클라우드 효과는 실제 실험이 끝난 뒤 수치로 채운다.
