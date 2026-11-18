# 최적화 코드 위치·선택 이유·검증 방법

실측 결과와 채택 여부는 [결과 보고서](optimization-results-2026-11-18.md), 추가 가설은 [실험 계획](optimization-expansion-2026-11-18.md)을 따른다. 실험용 CLI를 추가한 것과 운영 기본값을 바꾼 것을 구분한다.

## 운영 경로에 적용한 두 변경

| 문제와 위치 | 구현 | 선택 이유·보존한 계약 | 검증·원복 |
|---|---|---|---|
| VESPA 클래스별 Grounding 호출에서 같은 이미지 resize/normalize 반복 | [grounding_probe.py](../ai-server/services/grounding_probe.py)의 이미지 tensor 재사용, [grounding_runtime.py](../ai-server/services/grounding_runtime.py)의 child-process adapter, [vespa_runner.py](../ai-server/services/vespa_runner.py) 연결 | 모델 backbone feature나 결과를 재사용하지 않는다. 같은 image processor 결과만 재사용하므로 클래스별 prompt·threshold·forward를 유지할 수 있다. upstream checkout 자체는 수정하지 않음 | 실제 processor tensor·예외 복원 테스트, G1 검출, G2 전체 234검출·39프레임 3D/track/GT. `VESPA_GROUNDING_PREPROCESS=baseline` 원복 |
| CLIP 인덱싱에서 pending 조회 뒤 이미지마다 source/exists SELECT 반복 | [DatasetSearchIndexService](../src/main/java/com/example/demo/nuscenes/service/DatasetSearchIndexService.java)의 pending source 전달, [ImageEmbeddingService](../src/main/java/com/example/demo/nuscenes/service/ImageEmbeddingService.java)의 `embedPending` | 이미 조회한 불변 source와 미저장 조건을 재사용한다. GPU batch 변경과 무관하다. 최종 INSERT의 `ON CONFLICT`, worker claim/heartbeat/yield, 일반 embed API의 검사 경로 유지 | 양쪽 설정 Spring 통합 테스트·중복/동시성·C1 RDS 3쌍 벡터/검색 완전 일치. `EMBEDDING_INDEX_PREFETCH_ENABLED=false` 원복 |

기본값은 [compose.hybrid.yml](../compose.hybrid.yml)과 [.env.hybrid.example](../.env.hybrid.example)에 기록했다. 일반 Spring property는 보수적인 false 기본값을 유지하고 검증된 hybrid 구성에서 prefetch를 켠다. CPU native 스레드는 1, 모델 정밀도/서빙 엔진은 기존 값을 유지한다. 설정을 바꾼 뒤 기존 컨테이너를 `--no-recreate`로 시작하면 이전 환경이 남으므로 명시적으로 재생성이 필요하다.

## 계측과 증거 생성

| 파일 | 기록·검증 범위 | 이 도구를 고른 이유 |
|---|---|---|
| [record_command.py](../scripts/hybrid/record_command.py) | 새 measurement 폴더, 명령 argv·소스 hash·이미지 digest, stdout/stderr, collector 종료와 최종 수집 | 성공·실패 모두 같은 생명주기로 기록. 종료 code와 품질 판정 분리 |
| [measurement.py](../scripts/hybrid/measurement.py), [sample_resources.py](../scripts/hybrid/sample_resources.py) | CLIP/업로드/라벨/저장소 단계 JSONL, 호스트·Docker·GPU·cgroup 표본 | 네트워크·CPU·GPU·DB 구간을 분리. 중첩 단계는 단순 합산하지 않음 |
| [evidence_io.py](../scripts/hybrid/evidence_io.py) | 고유 임시 파일과 bounded PermissionError 재시도로 JSON 교체 | Windows 교체 실패를 무한 retry하거나 기존 증거 손상으로 숨기지 않음 |
| [export_review_evidence.py](../scripts/hybrid/export_review_evidence.py) | 명시적 선택 파일만 Git 증거로 복사·경로 정규화·원본/출력 hash | 데이터/모델/credential 덤프 없이 결과를 리뷰 가능하게 보존 |

## 케이스별 실행 코드

| ID | 실행·비교 코드 | 결과를 해석할 때의 경계 |
|---|---|---|
| G1/G2 | [benchmark_grounding.py](../ai-server/tools/benchmark_grounding.py), [benchmark_scene.py](../ai-server/tools/benchmark_scene.py), [compare_scene.py](../ai-server/tools/compare_scene.py), [render_scene_quality.py](../ai-server/tools/render_scene_quality.py) | 검출 microbenchmark와 전체 3D 씬 시간을 구분. 공식 GT 계산도 단일 씬 범위 |
| C1 | [run_index_cases.py](../scripts/hybrid/run_index_cases.py), [compare_index_cases.py](../scripts/hybrid/compare_index_cases.py), [IndexExperimentSnapshot.java](../src/main/java/com/example/demo/nuscenes/benchmark/IndexExperimentSnapshot.java) | 재시작·warmup·이미지 digest 조건 검사. 코드상 제거된 SELECT 수와 DB 계측 수를 구분 |
| A1 | [benchmark_clip.py](../scripts/hybrid/benchmark_clip.py), [benchmark_index_quality.py](../scripts/hybrid/benchmark_index_quality.py), [benchmark_label_cycle.py](../scripts/hybrid/benchmark_label_cycle.py), [compare_label_roundtrip.py](../scripts/hybrid/compare_label_roundtrip.py) | 정상 API 업로드→RDS/S3→검색→라벨→RRD/Range. loopback 시험과 공개 브라우저 시험을 구분 |
| S1 | [benchmark_storage_cycle.py](../scripts/hybrid/benchmark_storage_cycle.py) | warm/압축본/S3 cold를 원본 삭제 없이 cache rename으로 분리. 해시 검사 범위 명시 |
| T3/T4 | [run_thread_cases.py](../scripts/hybrid/run_thread_cases.py), [run_sam_thread_cases.py](../scripts/hybrid/run_sam_thread_cases.py), [run_thread_scene.py](../scripts/hybrid/run_thread_scene.py), [benchmark_thread_scene.py](../ai-server/tools/benchmark_thread_scene.py) | 1·2·4 제한, 별도 프로세스 교차 반복. 소량 SAM mask 통과가 최종 3D 보존을 보장하지 않음 |
| A2/P | [run_grounding_variants.py](../scripts/hybrid/run_grounding_variants.py) | 실제 attention 초기화, FP32/FP16/BF16/autocast/TF32. 실패에 가상 시간 부여 금지. 2D IoU는 진단이며 AP 아님 |
| R1/R2 | [run_runtime_probe.py](../scripts/hybrid/run_runtime_probe.py), [probe_grounding_runtime.py](../ai-server/tools/probe_grounding_runtime.py) | pinned optional dependency를 별도 경로에 설치. 실제 ONNX export/check, ORT provider 배치, TRT parser/build/실행을 단계별 확인. static probe는 배포 통과가 아님 |
| S2 | [benchmark_s3_transfers.py](../scripts/hybrid/benchmark_s3_transfers.py) | 16MiB multipart/Range와 concurrency 1·2·4. byte hash·요청/retry·CPU 기록. 새 UUID key의 소유 metadata를 확인한 뒤 해당 실험 객체만 정리 |
| Q2 | [QueryExperiment.java](../src/main/java/com/example/demo/nuscenes/benchmark/QueryExperiment.java), [run_query_experiment.py](../scripts/hybrid/run_query_experiment.py) | 원본 SQL 보존 후 MATERIALIZED, auto/custom/generic, 후보 SET LOCAL 비용 포함 비교. read-only SELECT·ordered 결과·client/server·temp I/O·준비문 카운터. raw vector plan은 로컬 보존 |
| Q3 | [clip_service.py](../ai-server/services/clip_service.py), [benchmark_clip_serving.py](../ai-server/tools/benchmark_clip_serving.py), [캐시 테스트](../ai-server/tests/test_clip_text_cache.py) | 프로세스/모델 수명 안의 exact-text LRU. 같은 lock으로 중복 진행 요청 1회 계산. 실 GPU FastAPI/JSON 비교와 mock 계약 테스트를 구분 |
| Q2+Q3 API | [benchmark_search_api.py](../scripts/hybrid/benchmark_search_api.py), [SceneSearchRepository.java](../src/main/java/com/example/demo/nuscenes/repository/SceneSearchRepository.java) | loopback Spring→CLIP→RDS의 54쌍 응답 비교. `SEARCH_EXACT_OPTIMIZATION_ENABLED=false`, `CLIP_TEXT_CACHE_SIZE=0`으로 원복 |
| R1/R2 후속 | [resume_runtime_probe.py](../scripts/hybrid/resume_runtime_probe.py), [benchmark_runtime_detections.py](../ai-server/tools/benchmark_runtime_detections.py) | 보존 graph 재사용, 새 디렉터리, 6카메라 양성 검출. TRT 빌드 완료와 배포 품질 통과를 구분 |
| 보고서 | [summarize_index.py](../scripts/hybrid/summarize_index.py), [summarize_cycle.py](../scripts/hybrid/summarize_cycle.py), [summarize_threads.py](../scripts/hybrid/summarize_threads.py), [summarize_expansion.py](../scripts/hybrid/summarize_expansion.py) | 원본 JSON에서 report.md 생성. generic 단계 보고서는 별도 보존 |

## 테스트를 어디서 실행했는가

[run_optimization_java_tests.py](../scripts/hybrid/run_optimization_java_tests.py)는 임시 pgvector/PostgreSQL과 Java 21 컨테이너에 소스를 복사한다. 운영 RDS나 GPU를 쓰지 않으며 자신이 만든 label/name을 확인한 뒤 임시 컨테이너만 정리한다. [SceneSearchTests](../src/test/java/com/example/demo/SceneSearchTests.java)와 [PrefetchedSceneSearchTests](../src/test/java/com/example/demo/PrefetchedSceneSearchTests.java)는 기존 경로·새 경로의 검색, 중복 및 재시도 계약을 확인한다.

[host tests](../scripts/hybrid/tests)에서는 잘못된 비교가 성공으로 표시되지 않는지, 누락·NaN·순위/track 변경과 파일 교체 실패를 검사한다. 실제 Transformers image processor 회귀는 [AI tests](../ai-server/tests/test_grounding_probe.py), adapter 복원은 [runtime tests](../ai-server/tests/test_grounding_runtime.py)다. CI의 mock 모델 테스트를 실제 GPU 품질 시험으로 표현하지 않는다.

## 아직 별도 설계가 필요한 변경

Java S3 후속은 [S3-J 구현·실측·채택 결정](s3-java-optimization-2026-11-18.md)에 정리했다. `UploadArchiveStore`의 단일 경로와 `MultipartArchiveUploader`의 제한된 병렬 경로를 실제 4.17GB로 비교하고, `S3ArchiveExperiment`와 `run_s3_java_experiment.py`가 장애·SHA·정리 증거를 남긴다. 기본 multipart는 false이며 다운로드 완전성·실패 기록은 운영에 반영한다. `reset_app_data.py`는 별도 복원 검증 뒤 명시한 앱 테이블만 초기화하고 원본·계정·모델·시퀀스를 보존한다.

INT8/INT4는 calibration 데이터·지원 연산·정확도 예산이 필요하다. FlashAttention·TensorRT 설치만으로 현재 모델을 자동 변환하지 않는다. S3 직접 업로드/씬별 저장은 업로드 프로토콜·검증·캐시 복구를 함께 바꾸는 설계다. RDS HNSW는 현재 씬 전체 집계와 의미가 달라 recall·scene ranking 검증이 필요하다. 이런 변경은 이번에 검증한 두 기본값과 섞지 않고 새로운 케이스로 추가한다.
