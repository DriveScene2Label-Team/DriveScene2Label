# Rerun recording 계약과 구현 기준

작성: 2026-10-04, 브랜치 `codex/frontend-implementation`. [기획서 9장](frontend-product-plan.md)의 recording API 초안을 실제 구현 계약으로 정리한 문서다. 프론트가 호출하는 REST 계약은 [README_API.md](../README_API.md)에도 요약한다.

## 1. 버전 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| Python SDK | `rerun-sdk==0.38.1` (AI 기본 환경, exporter 전용) | 기존 pin `0.21.0`의 웹 Viewer는 `ready`/`fullscreen` 이벤트만 제공하고 시간 읽기·설정, 선택 이벤트가 없다(`@rerun-io/web-viewer@0.21.0` `index.d.ts` 확인). 0.38.1은 `time_update`, `timeline_change`, `selection_change`(entity_path + instance_id), `recording_open`, `set_current_time`, `set_active_timeline`, `set_playing`, `get_time_range`를 제공한다. |
| 웹 Viewer | `@rerun-io/web-viewer@0.38.1` (React wrapper 미사용, 직접 `WebViewer` 제어) | SDK와 같은 버전으로 고정해야 `.rrd` 호환이 보장된다. 이벤트·시간 제어를 직접 다루기 위해 wrapper 대신 클래스를 사용한다. |
| VESPA 환경 | `requirements-vespa.txt`의 `rerun-sdk==0.21.0` 유지 | VESPA는 `visualize=False`로 실행하며 upstream 의존성을 바꾸지 않는다. VESPA venv의 패키지가 system site-packages보다 우선하므로 두 버전이 충돌하지 않는다. |

버전을 올릴 때는 Python SDK, npm 패키지, `export_version`을 함께 바꾸고 작은 recording으로 시간/선택 이벤트를 다시 검증한다.

## 2. 흐름

```text
Browser ─POST /api/scenes/{sceneId}/recordings {jobId?}─▶ Spring (scene_recording PENDING)
Spring RecordingWorker ─claim RUNNING─▶ DB에서 keyframe sample·LIDAR_TOP·pose·calibration·GT(category)·예측을 읽음
Spring ─POST /recordings (내부)─▶ FastAPI ─subprocess─▶ recording_exporter.py (rerun-sdk 0.38.1) ─▶ /recordings/<id>-<token>/<scene>.rrd
FastAPI ─결과 metadata─▶ Spring 검증 후 READY + metadata 저장 (실패 시 FAILED + 이유)
Browser ─GET /api/recordings/{id}─▶ 상태·timeline·box mapping ─GET /api/recordings/{id}/content─▶ .rrd bytes ─▶ WebViewer
```

- 브라우저는 Spring만 호출한다. AI는 DB에 접근하지 않고 Spring이 보낸 값과 nuScenes 원본 파일만 사용한다.
- recording 상태(`PENDING/RUNNING/READY/FAILED`)는 라벨 job 상태와 별개다. recording 실패는 recording만 다시 만들며 VESPA job을 다시 실행하지 않는다.
- `auto_label_artifact.relativePath`는 사용하지 않는다. recording 파일은 별도 volume `rerun_recordings`에 저장하고 Spring content endpoint로만 제공한다.

## 3. REST 계약 (Spring, 브라우저용)

### POST `/api/scenes/{sceneId}/recordings`

body 생략 또는 `{"jobId": 12}`. 같은 dataset·scene·job·exportVersion의 FAILED가 아닌 recording이 있으면 그것을 재사용해 `200`, 새로 만들면 `202`.

```json
{"recordingId":5,"status":"PENDING","reused":false}
```

- 404: scene 없음, job 없음(같은 dataset 안에서).
- 409: job이 다른 scene 대상(`requested_targets`), job이 COMPLETED가 아님.
- 400: 잘못된 jobId.
- 최신 recording이 FAILED이면 같은 요청이 새 recording을 만든다. 이것이 “recording만 다시 생성”이다.

### GET `/api/scenes/{sceneId}/recordings`

해당 scene의 recording 요약 배열, 최신순. 새로고침 후 복원과 이미 준비된 recording 재사용에 쓴다. 각 항목은 아래 상세에서 `samples`를 뺀 형태다(필드 자체가 없음). 404: scene 없음.

### GET `/api/recordings/{recordingId}`

```json
{
 "recordingId":5,"datasetId":1,"sceneId":7,"sceneToken":"scene-token","sceneName":"scene-0061","jobId":12,
 "status":"READY","sdkVersion":"0.38.1","exportVersion":"ds2l-rrd-v2","coordinateFrame":"WORLD",
 "applicationId":"drivescene2label","rerunRecordingId":"ds2l-recording-5",
 "timeline":"sample","timeTimeline":"timestamp",
 "entities":{"lidar":"world/lidar","ego":"world/ego","gt":"world/gt","prediction":"world/prediction"},
 "samples":[{"index":0,"sampleToken":"s0","timestampUs":1532402927647951,"lidarPoints":34688,
   "gtAnnotationIds":[11,12],"predictionIds":[100]}],
 "contentUrl":"/api/recordings/5/content","sizeBytes":1234567,"errorMessage":null,
 "createdAt":"...","startedAt":"...","completedAt":"..."
}
```

- `timeline`은 sequence timeline 이름이고 값은 `samples[].index`다. `timeTimeline`은 같은 sample의 `timestampUs/1e6` 초 timestamp timeline이다.
- 박스 선택 mapping: Viewer `selection_change`의 `entity_path`가 `entities.gt`이면 현재 sample의 `gtAnnotationIds[instance_id]`, `entities.prediction`이면 `predictionIds[instance_id]`가 REST의 GT annotation `id` / 예측 box `id`다. 다른 sample의 같은 instance 번호를 같은 객체로 간주하지 않는다.
- `entities.prediction`은 jobId가 없으면 `null`이다. `contentUrl`은 READY일 때만 값이 있다. 상태가 READY가 아니면 `samples`는 빈 배열이다.
- (구현 확인) READY 전에는 AI 결과에서 오는 `applicationId,rerunRecordingId,timeline,timeTimeline,entities,sizeBytes`도 `null`이다. `sdkVersion/exportVersion`은 생성 시 Spring 설정값이며 READY 때 AI 응답과 일치를 확인한다.
- 404: recording 없음.

### GET `/api/recordings/{recordingId}/content`

READY recording의 `.rrd` bytes. `application/octet-stream`, `Content-Length`, `X-Content-Type-Options: nosniff`. Spring의 `Resource` 응답이라 Range 요청도 처리한다. 404 없음/파일 없음, 409 READY 아님.

재열기·유실(2026-10-05): READY content 다운로드 실패와 Viewer 시작 실패는 같은 recordingId로 다시 열며 새 생성·VESPA를 요청하지 않는다. 서버가 파일 부재를 확인하면 404 `RECORDING_FILE_MISSING`과 함께 행을 FAILED로 정정하고, recording root를 읽을 수 없으면 503 `RECORDING_STORAGE_UNAVAILABLE`(유실로 단정하지 않음). 새 recording POST는 재사용 확인 후 recording 준비 상태(`/api/system/status`의 recording)를 서버에서 확인한다.

Viewer 연결(2026-10-04 브라우저 확인): `@rerun-io/web-viewer@0.38.1`의 `start(url)`/`open(url)`은 `.rrd`로 끝나지 않는 HTTP URL을 `Failed to parse URL`로 거부한다. 프론트는 contentUrl을 `fetch`(AbortController로 취소, HTTP 오류 표시)한 bytes를 `WebViewer.open_channel(name).send_rrd(bytes)`로 전달하고, 언마운트 시 채널을 닫고 `stop()`한다. Viewer는 `start()`가 받은 요소에 인라인 `position: relative`를 넣으므로 절대 배치 래퍼 안의 100% 크기 요소에 붙인다.

## 4. 내부 FastAPI 계약 (Spring → AI)

`POST /recordings`, 동기 처리. AI는 요청 파일 경로를 dataset root 아래로 제한하고 결과를 `RECORDING_OUTPUT_ROOT` 아래에 쓴다.

```json
{
 "recording_id":5,"execution_token":"UUID","scene_name":"scene-0061","scene_token":"scene-token","job_id":12,
 "samples":[{"index":0,"sample_token":"s0","timestamp_us":1532402927647951,
   "lidar":{"relative_path":"samples/LIDAR_TOP/x.pcd.bin","sensor_translation":[0,0,1.8],"sensor_rotation":[1,0,0,0],
            "ego_translation":[400,1100,0],"ego_rotation":[1,0,0,0]},
   "gt":[{"id":11,"category_name":"vehicle.car","center":[1,2,3],"size_wlh":[2,4,1.5],"rotation_wxyz":[1,0,0,0]}],
   "predictions":[{"id":100,"detection_name":"car","center":[1,2,3],"size_wlh":[2,4,1.5],"rotation_wxyz":[1,0,0,0]}]}]
}
```

응답:

```json
{"recording_id":5,"execution_token":"UUID","relative_path":"5-UUID/scene-0061.rrd","size_bytes":1234567,
 "checksum":"64-hex sha256 of file bytes","sdk_version":"0.38.1","export_version":"ds2l-rrd-v2",
 "application_id":"drivescene2label","rerun_recording_id":"ds2l-recording-5","timeline":"sample","time_timeline":"timestamp",
 "entities":{"lidar":"world/lidar","ego":"world/ego","gt":"world/gt","prediction":"world/prediction"},
 "samples":[{"index":0,"sample_token":"s0","lidar_points":34688,"gt_boxes":1,"prediction_boxes":1}]}
```

- `lidar`가 `null`이면 그 sample의 점군을 비운다(`lidar_points=0`). 파일 누락은 404/503이 아닌 실패로 처리해 잘못된 recording을 READY로 만들지 않는다.
- 오류는 `{"detail":{"code","message"}}`: 422 입력, 404 lidar 파일 없음, 503 SDK/설정 없음, 502 exporter 실패, 504 timeout.
- Spring은 recording_id/execution_token/sample 순서·개수/gt·prediction 개수/relative_path 안전성/sdk_version을 검증한 뒤 READY로 저장한다.
- (구현 확인) 추가로 export_version 일치, `lidar=null` sample의 `lidar_points=0`, `relative_path`가 `.rrd`로 끝나고 `recording.root` 아래 실제 파일(symlink 탈출 거부)인지, 파일 크기=`size_bytes`, 파일 sha256=`checksum`, timeline/entity 이름 존재를 확인한다. `job_id`가 없으면 요청의 `job_id`는 `null`, 각 sample `predictions`는 빈 배열이다. GT 순서는 annotation API와 같은 `token` 오름차순, 예측 순서는 `box_index`.

## 5. exporter 기록 규칙

- `ViewCoordinates.RIGHT_HAND_Z_UP`을 `world`에 static으로 기록한다. 모든 데이터는 WORLD 미터.
- sample마다 `sample`(sequence=index), `timestamp`(초) timeline을 설정한다.
- `world/lidar`: `.pcd.bin` float32×5(x,y,z,intensity,ring)를 sensor→ego(calibration), ego→world(pose)로 변환한 `Points3D`. 높이 기반 색.
- `world/ego`: ego pose `Transform3D`와 차량 크기 상자.
- `world/gt`: GT `Boxes3D`. half_sizes는 로컬 x=L/2, y=W/2, z=H/2. quaternion은 API의 W/X/Y/Z를 Rerun의 x,y,z,w로 변환. 노랑, label은 원본 category 이름 또는 `GT`.
- `world/prediction`: 예측 `Boxes3D`, 민트, label은 detection_name. jobId가 없으면 기록하지 않는다.
- `world/labels` (export `ds2l-rrd-v2`, 2026-11-05): 박스 이름이 뭉쳐 읽기 어려워 이름표를 별도 `Points3D` 레이어로 정리한다. 박스 엔티티는 `show_labels=False`(이름은 데이터로 남아 선택 패널에 보임). ego 기준 30 m 안의 객체만, 같은 클래스 GT·예측이 1.5 m 안이면 하나로(흰색), 같은 클래스가 4 m 안이면 `class ×n`으로 묶고, 무리 윗면 0.6 m 위에 둔다. Viewer 엔티티 목록에서 이 레이어만 켜고 끌 수 있다. 응답 `entities`와 선택 매핑에는 포함하지 않는다(박스 인스턴스가 아니므로 선택 시 인스펙터 연결 없음). v1 recording은 재사용되지 않고 새로 만들어진다.
- 박스가 없는 sample도 빈 batch를 기록해 이전 sample의 박스가 latest-at으로 남지 않게 한다.
- instance 순서는 요청 배열 순서와 같다. Spring은 같은 순서로 `gtAnnotationIds`/`predictionIds`를 저장한다.

## 6. 저장소와 배포

- Compose volume `rerun_recordings`: ai-server `/recordings` 쓰기, backend `/recordings` 읽기 전용. 기존 `postgres_data`, `model_cache`, `vespa_results`는 그대로다.
- Spring 설정: `recording.root=${RECORDING_ROOT:/recordings}`, `recording.worker.enabled=${RECORDING_WORKER_ENABLED:true}`, `recording.read-timeout=${RECORDING_READ_TIMEOUT:660s}`, `recording.sdk-version=${RECORDING_SDK_VERSION:0.38.1}`, `recording.export-version=${RECORDING_EXPORT_VERSION:ds2l-rrd-v2}`, `recording.poll-delay-ms`(기본 1000).
- DB: `V5__scene_recording.sql`의 `scene_recording`. FAILED가 아닌 행은 `(dataset_id,scene_token,COALESCE(job_id,0),export_version)` partial unique index로 하나만 존재한다. job FK는 `(dataset_id,job_id)`.
- 생성된 `.rrd`는 Git에 넣지 않는다(`*.rrd` ignore).

## 7. 검증 상태

이 문서의 계약은 구현 기준이다. 실제 검증 결과는 [구현 체크리스트](frontend-implementation-checklist.md)의 검증 기록을 따른다.
