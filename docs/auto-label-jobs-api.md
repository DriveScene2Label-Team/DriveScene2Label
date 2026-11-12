# Spring auto-label jobs

## 역할 / DB

Controller -> AutoLabelService -> AutoLabelRepository가 job 및 대상 sample을 PENDING으로 저장합니다. POST는 202 응답을 반환합니다. DB polling worker가 committed PENDING job을 SELECT ... FOR UPDATE SKIP LOCKED로 claim하고 RUNNING/실행 UUID를 저장합니다. 별도 scheduler thread에서 AutoLabelClient가 FastAPI /auto-label을 호출합니다. HTTP 요청 thread와 DB transaction을 추론 완료까지 유지하지 않습니다.

결과 테이블은 기존 V4의 predicted_annotation을 사용합니다 (predicted_3d_box와 같은 역할). GT는 gt_annotation에만 저장합니다. 실패 이유는 기존 failure_reason 컬럼에 저장하고 GET 응답에서는 errorMessage로 노출합니다. 새 migration/GT 스키마 변경은 없습니다.

## 요청 / 상태 조회

```bash
curl -X POST http://localhost:8080/api/auto-label/jobs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: scene-0061-vespa-8-v1' \
  -d '{"sceneToken":"실제-scene-token","datasetId":1,"classMode":8}'
curl http://localhost:8080/api/auto-label/jobs/12
```

새 작업 응답 (202): `{"jobId":12,"status":"PENDING"}`. 실제 상태는 이후 GET으로 확인합니다. classMode=1/3/8. datasetId는 선택이지만 같은 token이 여러 dataset에 있으면 지정해야 합니다. sceneToken은 이름 scene-0061이 아닌 원본 scene.token입니다. Spring이 DB에서 이름과 sample 목록을 해석합니다.

같은 dataset에서 동일 Idempotency-Key와 동일 scene/classMode는 기존 job을 반환합니다. 이미 진행됐으면 기존 상태를 반환합니다. 동일 키를 다른 scene/classMode에 사용하면 409입니다. 헤더 생략 시 새 UUID 요청 키를 발급하므로 재전송도 새 작업이 됩니다. FAILED 작업을 실제 재계산하려면 새 키로 요청합니다. 현재 API는 retry_of_job_id 연결을 제공하지 않습니다.

2026-11-12 실행 순서 보완: 업로드 데이터셋은 현재 모델·전처리 기준 모든 카메라 키프레임의 임베딩이 완료된 뒤에만 새 라벨 요청을 받습니다. 미완료이면 `503 EMBEDDINGS_INCOMPLETE`이며 작업 행을 만들지 않습니다. 완료 상태 조회도 작업을 만들지 않으며 이후 사용자 클릭이 필요합니다. 이미 접수한 Idempotency-Key 재조회는 준비 상태와 무관하게 기존 작업을 반환합니다. 이는 GPU 작업 순서를 위한 제품 정책이며 VESPA 알고리즘이 CLIP 검색 벡터를 요구한다는 뜻은 아닙니다.

운영자가 사용자의 요청으로 중단한 작업은 현재 상태 enum에 취소가 없어 `FAILED` + `USER_CANCELLED`로 보존하고 UI에는 ‘중단됨’으로 표시합니다. 일반 사용자를 위한 취소 API는 아직 없습니다. 자동 재실행하지 않습니다.

GET 응답: jobId, datasetId, status, errorMessage, createdAt, startedAt, completedAt. 없는 scene/job=404, ambiguous token/키 충돌=409, 잘못된 입력/설정 dataset version 불일치=400.

## 저장 transaction

1. job 생성과 exact target sample snapshot 저장: 한 transaction.
2. worker claim 및 RUNNING 전환: 짧은 별도 transaction.
3. VESPA HTTP 호출: transaction 바깥.
4. job row lock + execution token 검증 + 모든 결과 박스 INSERT + 빈 sample 포함 결과 수신 표시 + 최종 JSON artifact 등록 + COMPLETED 전환: 한 transaction.
5. 어떤 validation/storage/terminal status update가 실패해도 4번 전체 rollback. 이후 별도 transaction에서 RUNNING job을 FAILED로 전환하고 failure_reason 기록. stale token/terminal job은 failure update로 덮어쓰지 않습니다.

FastAPI의 job_id/execution_token/scene_name/class_mode/mapping_name, WORLD 좌표, VESPA_CONSTANT 점수, exact sample coverage를 검증합니다. finite XYZ/WLH/velocity, positive dimensions, unit quaternion, 클래스 및 score=1.0을 확인합니다. 중간 NPZ는 저장하지 않습니다. raw_payload는 개별 최종 box JSON이며 artifact는 AI 서버의 결과 root 기준 상대 경로입니다.

GT와 비교하는 키는 (dataset_id,sample_token)입니다. 이 관계는 기존 sample 및 job target FK로 강제됩니다. 같은 sample의 GT와 prediction은 독립 박스이므로 개별 매칭은 거리/IoU/클래스로 결정하세요.

```sql
SELECT p.*, s.scene_token
FROM predicted_annotation p
JOIN sample s ON s.dataset_id=p.dataset_id AND s.token=p.sample_token
JOIN auto_label_job j ON j.id=p.job_id
WHERE p.job_id=:jobId AND j.status='COMPLETED';
-- 같은 dataset/sample의 GT는 gt_annotation에서 별도 조회.
```

## 실행 설정

AI 서버는 ai-server/VESPA.md에 따라 VESPA_PYTHON/VESPA_DATA_ROOT/VESPA_DATASET_VERSION을 설정해야 합니다. Spring의 VESPA_DATASET_VERSION은 DB dataset.version 및 AI의 설정과 같아야 합니다. 이름이 같은 다른 데이터 root를 잘못 연결하지 않도록 운영자가 dataset root를 맞춰야 합니다. FastAPI는 한 dataset root/version을 사용하는 MVP입니다.

Spring 환경값:

- AI_SERVER_BASE_URL: host Spring 기본 http://127.0.0.1:8000, Compose 기본 http://host.docker.internal:8000.
- VESPA_DATASET_VERSION: 기본 v1.0-trainval; mini 사용 시 Spring과 AI 모두 v1.0-mini 설정.
- VESPA_MODEL_VERSION: 기본 현재 확인한 upstream commit acb2b6e8683363795528f049fe0444ef9f3efdb9. 실제 실행 코드 버전에 맞춰 설정.
- AUTO_LABEL_READ_TIMEOUT: 기본 7300s; AI VESPA timeout 7200s보다 길게 설정.
- AUTO_LABEL_WORKER_ENABLED: 기본 true; false면 API는 저장/조회만 하고 worker는 실행하지 않음.
- VESPA_ARTIFACT_STORAGE_KEY: 기본 vespa-results. AI VESPA_OUTPUT_ROOT와 대응하는 저장소 식별자.

model_config에는 config 이름과 dataset version snapshot을 저장합니다. 전체 resolved YAML/checkpoint hash는 현재 응답 계약에 없으므로 model_version 및 고정 p_final 설정을 운영에서 맞춰야 합니다.

## MVP 한계 / 복구

DB에 PENDING을 저장하므로 요청 서버가 재시작해도 대기 작업은 다음 polling에서 처리됩니다. worker는 기본 하나의 scheduler thread로 순차 실행합니다. 여러 Spring instance는 DB claim을 중복하지 않지만 FastAPI의 worker별 실행 제한과 GPU를 공유하므로 MVP에서는 dispatch하는 Spring worker도 하나만 켜세요.

RUNNING 중 Spring 프로세스가 종료되면 job이 자동 복구되지 않습니다. AI 프로세스 상태를 확인한 후 운영자가 해당 job을 FAILED로 정리하고 새 키로 재요청해야 합니다. HTTP timeout/클라이언트 연결 종료 후 AI 계산이 계속될 수도 있습니다. 외부 durable queue, heartbeat/lease, 자동 retry/cancel은 이 구현에 포함되지 않습니다. DB 저장은 실패로 남더라도 AI 결과 파일은 AI 로그/출력 root에 남을 수 있습니다.

AI 오류 및 validation/storage 오류는 FAILED로 기록합니다. 실제 상세 exception은 Spring 로그에 남기며 DB/응답에는 민감한 경로·upstream body 대신 오류 분류 메시지를 저장합니다. DB 자체가 끊기면 FAILED 갱신도 실패할 수 있으므로 worker 로그를 확인해야 합니다.

## 검증

`bash scripts/docker-test.sh`는 기존 서비스와 분리된 PostgreSQL/pgvector에서 전체 Spring 테스트를 실행합니다. AutoLabelTests는 실제 HTTP 테스트 서버와 DB를 사용해 성공 결과 다중 박스/빈 sample/GT 분리, Idempotency-Key, AI 실패/coverage 오류, COMPLETED UPDATE 강제 실패 시 전체 결과 rollback 후 FAILED를 검증합니다. 테스트 AI는 합성 VESPA 결과를 반환하며 실제 모델 end-to-end 추론은 별도 환경 검증입니다.

2026-10-03: Java 컴파일 및 전체 Spring 테스트 14개 통과 (auto-label 4개 포함). 모든 테스트 failure/error=0, Compose 설정 검증 통과. 임시 테스트 DB/네트워크는 정리했으며 기존 DB는 수정하지 않았습니다.

## 결과 조회

GET `/api/auto-label/jobs/{id}/results`는 COMPLETED 작업의 sampleTokens, boxes, artifacts를 반환한다. 미완료/실패는409, 없는 작업은404. 최신 전체 계약은 [README_API.md](../README_API.md)를 참조한다.
