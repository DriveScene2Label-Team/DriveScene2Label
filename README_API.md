# DriveScene2Label Backend API Specification

검증 기준: 2026-10-03, origin/main `ffb6dc8` 위 로컬 통합 변경. Docker 통합과 함께 제공하는 REST 계약이다.
2026-10-04 `codex/frontend-implementation`: GT category 필드, job status 문맥 필드, Rerun recording API(9장) 추가. 기존 필드는 유지한다.

## 1. 서버 구성

- Spring Boot: `http://localhost:8080`. 프론트엔드는 아래 `/api/*`만 호출한다.
- FastAPI: `http://localhost:8000`. Spring 내부 호출용이며 DB에 접근하지 않는다.
- PostgreSQL/pgvector: Spring이 metadata, embedding, job, prediction을 저장한다. GT와 prediction은 별도 테이블이다.
- 브라우저는 같은 origin의 reverse proxy를 권장한다. 별도 origin CORS 설정/인증은 현재 제공하지 않는다.
- Spring과 AI의 이미지 root는 동일한 파일 집합을 가리켜야 한다. 요청에는 DB에서 읽은 상대 경로만 전달한다.
- mini는 Spring 및 AI 모두 `VESPA_DATASET_VERSION=v1.0-mini`로 실행한다. 기본 VESPA 버전은 trainval이다.

## 2. 기본 응답 및 타입

성공 응답은 별도 envelope 없이 객체 또는 배열이다. JSON 필드는 Spring camelCase, AI snake_case이다.
`id`는 DB 숫자 ID, `token`은 nuScenes 문자열 식별자이다. 서로 바꾸어 전달하지 않는다.
정수 BIGINT 값은 JS 안전 정수 범위를 넘을 수 있으므로 대규모 운영 시 문자열 ID 정책이 추가로 필요하다.
시간은 `timestampUs`(epoch microseconds) 또는 ISO-8601 job 시간이다. 좌표/길이는 m, 속도는 m/s.
아래 표에서 body `없음`은 전송하지 않는다는 뜻이다. 경로의 `{id}`는 해당 행의 숫자 ID이다.
모든 API는 잘못된 필드 타입 400, DB 작업 불가 503, 예상하지 못한 서버 오류 500이 가능하다.

### 공통 오류

검증/업무 오류 및 DB 예외는 다음 형태다:

```json
{"code":"HTTP_404","message":"Job not found"}
```

- `HTTP_400/404/409/502/503`: 각 업무 오류. message는 설명이며 프로그램 분기는 status/code를 사용한다.
- `INVALID_REQUEST` (400): 필수값 누락, JSON 또는 타입 오류.
- `DATABASE_UNAVAILABLE` (503): DB 접근 또는 transaction 실패. SQL/접속 정보는 응답에 포함하지 않는다.
- 라우팅 404, 허용되지 않은 method 405, 기타 미처리 500은 Spring 기본 오류 형태일 수 있다. 모든 오류를 단일 형태로 가정하지 않는다.

## 3. Dataset API

|Method|URL / path variable|Query / body|200 Response|추가 오류|
|---|---|---|---|---|
|GET|`/api/datasets`|없음 / 없음|`Dataset[]`|—|
|GET|`/api/datasets/{id}/scenes` dataset ID|없음 / 없음|`Scene[]`|404 dataset 없음|
|GET|`/api/datasets/{id}/stats` dataset ID|없음 / 없음|`{scenes,samples,sensorFiles,keyframeFiles,gtBoxes,maps}` 모두 정수|404|
|GET|`/api/datasets/{id}/categories` dataset ID|없음 / 없음|`Category[]`|404|

타입:
- Dataset: `id:number,name:string,version:string,storageKey:string,rootRelativePath:string,sourceChecksum:string`.
- Scene: `id,datasetId` 숫자; `token,logToken,name,description,firstSampleToken,lastSampleToken` 문자열; `nbrSamples` 정수.
- Category: `id,datasetId` 숫자; `token,name,description` 문자열.

## 4. Scene / Sample / Sensor / GT API

|Method|URL / path variable|Query (기본값) / body|200 Response|추가 오류|
|---|---|---|---|---|
|GET|`/api/scenes/{id}/samples` scene ID|`limit=100` (1..500), `offset=0` (>=0) / 없음|`Sample[]`|400,404|
|GET|`/api/samples/{id}` sample ID|`keyframesOnly=true` / 없음|`{sample:Sample,sensorFiles:SensorFile[],maps:MapView[]}`|404|
|GET|`/api/samples/{id}/annotations` sample ID|`includeDeleted=false` / 없음|`GtAnnotation[]`|404|
|GET|`/api/scenes/{id}/annotations` scene ID|없음 / 없음|scene 전체 sample의 `GtAnnotation[]` (삭제 편집 제외, sampleToken·token 순)|404|
|GET|`/api/sensor-files/{id}/calibration` sample_data ID|없음 / 없음|`CalibratedSensor`|404|
|GET|`/api/sensor-files/{id}/pose` sample_data ID|없음 / 없음|`EgoPose`|404|
|GET|`/api/sensor-files/{id}/content` sample_data ID|없음 / 없음|파일 bytes|404 metadata/파일 없음|
|GET|`/api/maps/{id}/content` map ID|없음 / 없음|파일 bytes|404|

타입:
- Sample: `id,datasetId,timestampUs` 숫자; `token,sceneToken,prevToken,nextToken` 문자열. 연결 토큰은 없을 수 있다.
- SensorFile: `id,token,channel,modality,relativePath,timestampUs,isKeyFrame,width,height,egoPoseToken,calibratedSensorToken,vehicleX,vehicleY,vehicleZ,contentUrl`. `isKeyFrame` boolean, ID/시간/크기/좌표 numeric, 나머지 string. vehicleXYZ는 해당 센서 시간의 ego world 위치다.
- MapView: `id:number,token:string,relativePath:string,location:string,contentUrl:string`.
- GtAnnotation: `id,datasetId,token,sampleToken,instanceToken,visibilityToken,centerX,centerY,centerZ,sizeW,sizeL,sizeH,rotationW,rotationX,rotationY,rotationZ,numLidarPts,numRadarPts,prevToken,nextToken,categoryToken,categoryName`. ID/box/point count numeric, token string. 일부 관계값 nullable. `categoryToken/categoryName`은 같은 dataset의 object_instance→category JOIN 결과이며 연결이 없으면 null. `labelOverride`(string|null)는 라벨 편집으로 바뀐 클래스(8-1장), `deleted`(boolean)는 `includeDeleted=true`일 때만 true가 될 수 있다. 기본 응답은 삭제 편집된 박스를 빼고 원본 행·category는 바꾸지 않는다.
- CalibratedSensor: `id,datasetId,token,sensorToken,translationX/Y/Z,rotationW/X/Y/Z,intrinsic00/01/02/10/11/12/20/21/22` (슬래시는 실제 JSON 필드 각각을 뜻함). 카메라 외 intrinsic은 null 가능. sensor→ego 변환.
- EgoPose: `id,datasetId,token,timestampUs,translationX/Y/Z,rotationW/X/Y/Z`. ego→world 변환.

GT/예측 모두 world 중심 좌표, size W,L,H, quaternion W,X,Y,Z. GT `categoryName`은 nuScenes 원본 이름(`vehicle.car` 등)이며 서버가 vehicle/car 등으로 바꾸지 않는다. classMode별 표시 분류 매핑은 클라이언트가 하고 미매핑은 그대로 표시한다. 순서는 `token` 오름차순. GT 비교는 datasetId+sampleToken으로 같은 프레임을 찾은 뒤 공간적으로 매칭해야 하며 box끼리 일대일 FK는 없다.

파일 응답은 JPEG/PNG에 대응 MIME, 그 외 `application/octet-stream`, `Content-Length`, `X-Content-Type-Options: nosniff`를 사용한다. 반환된 contentUrl은 Spring 기준 상대 URL이다.

## 5. Embedding 저장 / 이미지 검색 API

|Method|URL / path variable|Query / body|200 Response|추가 오류|
|---|---|---|---|---|
|POST|`/api/sensor-files/{id}/embedding` sample_data ID|`overwrite=false` / 없음|`EmbeddingWriteResult`|400 카메라 아님,404 파일 없음,409 root 매핑 불가,502 AI 응답 오류,503 연결/timeout|
|GET|`/api/datasets/{id}/embeddings` dataset ID|없음 / 없음|`[{modelName,preprocess,images}]`|없는 dataset도 빈 배열|
|GET|`/api/sensor-files/{id}/similar` source sample_data ID|`limit=10` (1..100), `modelName`, `preprocess`, `excludeSameScene=false` / 없음|`SimilarImage[]`|400,404 source embedding 없음|

```json
{"sensorFileId":42,"datasetId":1,"sampleDataToken":"camera-token","modelName":"ViT-L-14-quickgelu/openai","preprocess":"lr-square-crop-mean","dimension":768,"status":"STORED"}
```

`STORED`는 생성 또는 덮어쓰기, `SKIPPED`는 기존 항목 유지. unique 키는 `(dataset_id,sample_data_token,model_name,preprocess)`이다. skip는 AI를 호출하지 않는다. 동시 생성도 ON CONFLICT로 중복 방지한다. overwrite는 마지막 저장이 적용된다. AI 호출 중 DB transaction을 유지하지 않는다. 모델/전처리/차원/유한수/L2 norm을 확인한 뒤 단일 upsert한다. 실패한 추론은 기존 벡터를 변경하지 않는다.
배치 endpoint는 없다. 작업 스크립트에서 이미지 ID를 순차 호출하고 실패한 항목만 재시도한다. 현재 CLIP inference lock 때문에 높은 병렬도는 피한다.

SimilarImage: `id,token,sceneName,sampleToken,channel,relativePath,timestampUs,distance,contentUrl`. source와 같은 dataset/model/preprocess에서 자기 자신을 제외하고 cosine distance 오름차순으로 반환한다. default model/preprocess는 위 예시와 동일하다.

## 6. Natural Language Scene Search API

`GET /api/search/scenes` — request body 없음.

|Query|필수|기본 / 제한|
|---|---|---|
|q|예|공백 제거 후 1..10000자|
|k|아니오|10, 1..100 scenes|
|datasetId|아니오|양수, 생략하면 모든 dataset|
|aggregation|아니오|TOP_K_AVERAGE, MAX, AVERAGE (대소문자 무관)|
|imageTopK|아니오|3, 1..100; TOP_K_AVERAGE에 적용|
|keyframesOnly|아니오|true|

```bash
curl --get http://localhost:8080/api/search/scenes --data-urlencode 'q=rainy night road' --data 'k=10'
```

응답 예시 (수치는 설명용):

```json
{"query":"rainy night road","modelName":"ViT-L-14-quickgelu/openai","preprocess":"lr-square-crop-mean","aggregation":"TOP_K_AVERAGE","imageTopK":3,"keyframesOnly":true,"scenes":[{"sceneId":7,"datasetId":1,"sceneToken":"scene-token","sceneName":"scene-0061","description":"...","score":0.31,"distance":0.69,"matchedImages":234,"contributingImages":3,"bestImageId":42,"bestSampleToken":"sample-token","bestImagePath":"samples/CAM_FRONT/example.jpg","contentUrl":"/api/sensor-files/42/content"}]}
```

Text는 `clip-text-tokenizer`, image는 `lr-square-crop-mean`이 정상이다. modality별 preprocess 이름을 같은 문자열로 비교하지 않는다. 두 modality의 model은 `ViT-L-14-quickgelu/openai`로 일치한다.
DB는 같은 image model/preprocess의 camera만 선택해 `<=>` 거리 계산 → scene별 aggregation → score 내림차순으로 k개를 반환한다. score=1-distance이며 확률이 아니다. MAX는 최고 이미지, AVERAGE는 전체 평균, TOP_K_AVERAGE는 scene 내 상위 N개 평균이다. N보다 적으면 존재하는 개수로 평균낸다. 대표 이미지는 가장 가까운 이미지다. image LIMIT를 먼저 적용하지 않는다.
200 + `scenes:[]`는 정상적인 빈 결과. 없는 양수 datasetId도 빈 결과다. 400 잘못된 입력, 502 AI 비정상 응답/HTTP 오류, 503 AI 연결 실패/timeout. 한국어 검색은 요청 가능하지만 이 OpenAI CLIP의 한국어 검색 품질은 검증하지 않았다.

## 7. Auto Label Job 생성 / 상태

`POST /api/auto-label/jobs` — query 없음. 선택 header `Idempotency-Key` (1..200자).

```json
{"sceneToken":"scene-token","datasetId":1,"classMode":8}
```

sceneToken/classMode 필수, datasetId 선택 양수. 동일 token이 여러 dataset에 있으면 datasetId가 필요하다. scene의 dataset version이 설정된 VESPA version과 같아야 한다.

202 응답:

```json
{"jobId":12,"status":"PENDING"}
```

같은 dataset/Idempotency-Key/scene/classMode 재요청은 기존 job을 반환하며 status가 이미 COMPLETED/FAILED일 수도 있다. 키 생략은 매번 새 job. 같은 키로 다른 scene/classMode는409. 실패 작업 재실행은 새 키 사용.
처리 순서(2026-10-05): ① target 확인과 같은 key의 기존 job 재조회(AI 장애 중에도 응답) ② **새 job일 때만** transaction 밖에서 VESPA 준비 검사(`/api/system/status`의 vespa와 같은 판정, CONFIGURED/UNKNOWN이면 읽기 전용 재확인 1회) ③ insert. 준비되지 않았으면 job을 만들지 않고 `503 {"code":"<reasonCode>","message":"..."}`(예: `VESPA_NOT_CONFIGURED`, `EXECUTOR_NOT_CHECKED`, `SYNTHETIC_DATASET`, `DATASET_MISMATCH`, `AI_UNREACHABLE`, `AI_ENDPOINT_UNSUPPORTED`).
400 classMode/버전/빈 scene 오류,404 scene 없음,409 token 모호/키 충돌,503 준비 안 됨(code는 위) 또는 DB 오류.

`GET /api/auto-label/jobs/{id}` — job 숫자 ID, query/body 없음. 200:

```json
{"jobId":12,"datasetId":1,"status":"RUNNING","errorMessage":null,"createdAt":"2026-10-03T12:00:00Z","startedAt":"2026-10-03T12:00:01Z","completedAt":null,
 "sceneToken":"scene-token","sceneId":7,"sceneName":"scene-0061","classMode":8,"mappingName":"8class","errorCode":null}
```

`sceneToken`은 job 생성 시 대상(`requested_targets[0]`), `sceneId/sceneName`은 같은 dataset의 scene JOIN으로 없으면 null, `classMode`(1/3/8)는 `mappingName`에서 계산한다. 새로고침 후 receipt 없이도 대상 문맥을 복원할 수 있다.
404 job 없음. FAILED는 errorMessage 및 completedAt이 채워진다. DB 컬럼명은 `failure_reason`, 외부 필드는 `errorMessage`다.
`errorCode`(V6, nullable): 실패 지점의 안정 식별자. `AI_ENDPOINT_UNSUPPORTED`(AI에 `/auto-label` 라우트 없음, HTTP 404), `AI_UNREACHABLE`(연결 거부·DNS·connect timeout), `AI_TIMEOUT`(응답 대기 초과), `AI_HTTP_ERROR`(AI 코드 없는 HTTP 오류), AI가 보낸 `VESPA_*`/`SCENE_NOT_FOUND`, `RESULT_VALIDATION_FAILED`(결과가 job·sample과 불일치), `RESULT_STORAGE_FAILED`(DB 저장 실패). V6 이전 행은 null이며 기존 message를 다시 해석하지 않는다. HTTP 502 자체를 모델 실패로 보지 않는다.
job 생성과 sample snapshot은 한 transaction. worker가 PENDING을 claim하고 짧은 transaction으로 RUNNING을 저장한 다음 HTTP 호출한다. 프론트엔드는 2~5초 간격으로 조회하고 terminal 상태에서 중단한다. 최대 예상 대기시간은 배포 timeout에 맞춰 안내한다.

## 8. Auto Label Result / Artifact

`GET /api/auto-label/jobs/{id}/results` — job 숫자 ID, query/body 없음.
200 응답 예시:

```json
{"jobId":12,"datasetId":1,"mappingName":"8class","coordinateFrame":"WORLD","scoreType":"VESPA_CONSTANT","sampleTokens":["sample-a","sample-empty"],"boxes":[{"id":100,"sampleToken":"sample-a","boxIndex":0,"detectionName":"car","centerX":1.0,"centerY":2.0,"centerZ":3.0,"sizeW":2.0,"sizeL":4.0,"sizeH":1.0,"rotationW":1.0,"rotationX":0.0,"rotationY":0.0,"rotationZ":0.0,"velocityX":0.0,"velocityY":0.0,"detectionScore":1.0,"attributeName":""}],"artifacts":[{"id":9,"artifactType":"FINAL_JSON","storageKey":"vespa-results","relativePath":"run/outs/vlm/p_final/#out_labels/vlm_p_final_scene-0061_8class.json","checksum":"64-character-sha256","contentType":"application/json"}]}
```

query `includeDeleted=false`(기본). 각 box에 `labelOverride`(라벨 편집 클래스, 없으면 null)와 `deleted`가 추가되었다(2026-11-05). 기본 응답은 삭제 편집된 box를 빼며 `detectionName`은 원본 그대로다.
404 job 없음,409 PENDING/RUNNING/FAILED. sampleTokens에 모든 처리 sample이 들어가며 box 없는 sample도 유지한다. boxes는 sampleToken,boxIndex 순서. 결과는 현재 전체 반환이므로 대규모 scene에는 pagination이 후속으로 필요하다.
`detectionScore=1.0`은 VESPA 고정값이며 calibrated confidence가 아니다. velocity는 원본 변환 출력이며 GT sample_annotation에는 직접 대응 필드가 없다. tracking instanceToken, visibility, lidar/radar point counts는 예측에 존재하지 않는다.
`predicted_annotation` + sample receipt + artifact + job COMPLETED를 같은 transaction으로 저장한다. 실패 시 전체 rollback 후 별도 transaction으로 FAILED 기록한다. DB 자체가 다운이면 FAILED 기록도 실패하므로 복구 작업이 필요하다.
Artifact는 metadata만 제공한다. relativePath는 다운로드 URL이 아니다. 최종 JSON artifact 다운로드 endpoint는 현재 없다. Rerun 파일은 artifact가 아니라 9장 recording API로 제공한다. checksum은 FastAPI가 canonical JSON으로 계산한 값이며 파일 bytes SHA와 동일하다고 가정하지 않는다. NPZ는 DB 저장/REST 반환 대상이 아니다.

## 8-1. Label Edit API (2026-11-05)

GT annotation과 VESPA 예측 박스의 클래스 변경·삭제·되돌리기·기록. **원본 행(gt_annotation, category, predicted_annotation)은 바꾸지 않는다.** 현재 상태는 `label_override`, 이력과 각 대상의 이전 상태는 `label_edit`/`label_edit_target`(V7 migration)에 저장한다. 바뀐 상태는 4장 GT 조회와 8장 결과 조회에 `labelOverride`/`deleted`로 반영된다. Rerun recording(9장)은 원본 박스를 기록하며 편집을 반영하지 않는다.

|Method|URL|Query / body|200 Response|오류|
|---|---|---|---|---|
|PATCH|`/api/annotations/{id}` gt_annotation ID|`{"label":"truck","scope":"SAMPLE"\|"INSTANCE"}` (scope 기본 SAMPLE)|`{edit:LabelEdit}`|400 `INVALID_LABEL`/`INVALID_SCOPE`/`SAME_LABEL`/`INVALID_REQUEST`, 404, 409 `TARGET_DELETED`|
|DELETE|`/api/annotations/{id}`|`scope=SAMPLE`\|`INSTANCE` (기본 SAMPLE) / 없음|`{edit:LabelEdit}`|400 `INVALID_SCOPE`, 404, 409 `TARGET_DELETED`|
|PATCH|`/api/auto-label/predictions/{id}` predicted_annotation ID|`{"label":"bus"}` (scope는 SAMPLE만)|`{edit:LabelEdit}`|400, 404, 409 `TARGET_DELETED`/`JOB_NOT_COMPLETED`/`SCENE_NOT_FOUND`|
|DELETE|`/api/auto-label/predictions/{id}`|없음|`{edit:LabelEdit}`|404, 409 `TARGET_DELETED`/`JOB_NOT_COMPLETED`|
|GET|`/api/scenes/{sceneId}/label-edits`|`jobId` (선택)|`LabelEdit[]` 최신순, 최대 200|404 scene 없음|
|POST|`/api/label-edits/{id}/revert`|없음|`{edit:LabelEdit}`|404, 409 `ALREADY_REVERTED`/`LATER_EDIT_EXISTS`|

- `label`은 `car,truck,bus,trailer,construction_vehicle,pedestrian,motorcycle,bicycle,vehicle` 중 하나(VESPA 8class + 1/3class의 vehicle).
- 원래 클래스: GT는 원본 category의 VESPA 8class 비교 분류(`vehicle.car`→`car`), VESPA가 평가하지 않는 category는 category 이름 그대로(임의로 vehicle로 바꾸지 않음). 예측은 `detectionName`. 원래 클래스로 되돌리는 이름 변경은 override를 지운다.
- `scope=INSTANCE`: 같은 dataset·scene에서 같은 `instanceToken`인 모든 GT. 이미 삭제된 프레임은 건너뛰고, 이름 변경은 실제로 클래스가 바뀌는 박스만 대상이다. 선택한 박스가 이미 그 클래스이면 400 `SAME_LABEL`.
- 기록 조회는 그 scene의 GT 편집 전체와 `jobId`가 주어졌을 때 그 job의 예측 편집을 돌려준다.
- 되돌리기는 이 편집 직전 상태를 복원한다. 같은 박스에 되돌리지 않은 나중 편집이 있으면 409 `LATER_EDIT_EXISTS`(최신부터 되돌림). `revertible`이 이 조건을 미리 알려 준다.
- 동시성: 대상 원본 행을 id 순으로 `FOR UPDATE` 잠근 transaction에서 처리한다. 편집 요청은 자동 재시도하지 않는다(응답 유실 시 기록 조회로 상태를 확인).

LabelEdit: `id,datasetId,sceneId` number, `jobId` number|null(GT는 null), `targetType` ANNOTATION|PREDICTION, `action` RENAME|DELETE, `scope` SAMPLE|INSTANCE, `instanceToken` string|null, `fromLabel` string, `toLabel` string|null(DELETE), `targetIds` number[], `sampleTokens` string[](targetIds와 같은 순서), `count` number, `createdAt` ISO-8601, `revertedAt` ISO-8601|null, `revertible` boolean.

```json
{"edit":{"id":3,"datasetId":1,"sceneId":7,"jobId":null,"targetType":"ANNOTATION","action":"RENAME","scope":"INSTANCE","instanceToken":"inst-car","fromLabel":"car","toLabel":"truck","targetIds":[101,102],"sampleTokens":["sample-a","sample-b"],"count":2,"createdAt":"2026-11-05T05:12:00Z","revertedAt":null,"revertible":true}}
```

## 9. Rerun Recording API

상세 계약·버전·exporter 규칙: [Rerun recording 계약](docs/rerun-recording.md). recording 상태는 라벨 job 상태와 별개다.

|Method|URL / path variable|Query / body|성공 Response|추가 오류|
|---|---|---|---|---|
|POST|`/api/scenes/{sceneId}/recordings` scene ID|없음 / 생략 또는 `{"jobId":12}`|202 새 생성, 200 재사용: `{recordingId,status,reused}`|400 잘못된 jobId,404 scene/job 없음,409 job이 다른 scene 대상 또는 COMPLETED 아님|
|GET|`/api/scenes/{sceneId}/recordings` scene ID|없음 / 없음|`RecordingSummary[]` 최신순|404 scene 없음|
|GET|`/api/recordings/{id}` recording ID|없음 / 없음|`Recording`|404|
|GET|`/api/recordings/{id}/content` recording ID|없음 / 없음|`.rrd` bytes|404 없음/파일 없음,409 READY 아님|

```json
{"recordingId":5,"status":"PENDING","reused":false}
```

- 같은 dataset·scene·jobId(없으면 GT·점군만)·exportVersion의 FAILED가 아닌 recording이 있으면 재사용(200, 현재 status 반환). 최신이 FAILED면 같은 요청이 새 recording을 만든다(202). recording 재생성은 VESPA job을 다시 실행하지 않고 job 행을 바꾸지 않는다.
- jobId는 같은 dataset의 job만 찾는다(다른 dataset은 404). 숫자가 아니면 `INVALID_REQUEST`, 0 이하면 `HTTP_400`.
- Recording: `recordingId,datasetId,sceneId,sceneToken,sceneName,jobId,status,sdkVersion,exportVersion,coordinateFrame,applicationId,rerunRecordingId,timeline,timeTimeline,entities{lidar,ego,gt,prediction},samples[],contentUrl,sizeBytes,errorMessage,createdAt,startedAt,completedAt`. jobId nullable, coordinateFrame `WORLD`.
- samples[]: `{index,sampleToken,timestampUs,lidarPoints,gtAnnotationIds[],predictionIds[]}`. Viewer `selection_change`의 entity_path가 `entities.gt`면 `gtAnnotationIds[instance_id]`가 GT annotation `id`, `entities.prediction`이면 `predictionIds[instance_id]`가 예측 box `id`다. 다른 sample의 같은 instance 번호는 같은 객체가 아니다.
- READY 전에는 `applicationId,rerunRecordingId,timeline,timeTimeline,entities,contentUrl,sizeBytes`가 null이고 `samples`는 빈 배열이다. jobId 없는 recording은 `entities.prediction=null`. FAILED는 `errorMessage`(짧은 원인)를 채운다.
- RecordingSummary: Recording에서 `samples` 필드를 뺀 형태.
- Viewer 연결: `@rerun-io/web-viewer@0.38.1`은 `.rrd`로 끝나지 않는 HTTP URL을 recording으로 열지 않는다(`Failed to parse URL`, 2026-10-04 브라우저 확인). 프론트는 `contentUrl`을 fetch한 bytes를 `WebViewer.open_channel().send_rrd()`로 전달한다. contentUrl을 Viewer에 직접 넘기지 않는다.
- content: `application/octet-stream`, `Content-Length`, `X-Content-Type-Options: nosniff`, `Range` 요청은 206. 파일은 `recording.root` 아래 상대 경로만 허용한다(절대 경로, `..`, root 밖 symlink 거부).
- 생성 처리(2026-10-05): 같은 설정의 FAILED가 아닌 recording 재사용을 먼저 확인한다(AI 장애 중에도 200). 재사용 후보가 READY인데 recording root는 읽히고 파일만 없음이 확인되면 그 행을 `FAILED(RECORDING_FILE_MISSING)`로 조건부 전환하고 새로 만든다. 새 생성일 때만 recording 준비 검사 후 insert하며, 준비되지 않았으면 `503 {"code":"<reasonCode>"}`.
- content: READY인데 파일 부재가 확인되면 `404 {"code":"RECORDING_FILE_MISSING"}`(행은 위와 같이 FAILED로 정정), recording root 자체를 읽을 수 없으면 `503 {"code":"RECORDING_STORAGE_UNAVAILABLE"}`(유실로 단정하지 않음), 허용 범위 밖 경로는 404.
- `errorCode`(V6, nullable): `RECORDING_INVALID_RESULT`, `RECORDING_FILE_MISSING`, `DATA_NOT_READY`, AI가 보낸 `RECORDING_*`, `AI_ENDPOINT_UNSUPPORTED/AI_UNREACHABLE/AI_TIMEOUT/AI_HTTP_ERROR`, `RESULT_STORAGE_FAILED`.
- Status: PENDING → RUNNING → READY 또는 FAILED. Spring worker가 짧은 transaction으로 claim하고 transaction 없이 AI `/recordings`를 동기 호출한 뒤, 응답의 recording_id·execution_token·sample 순서/개수·GT/예측 개수·SDK/export 버전·경로·파일 size/sha256을 검증해 READY로 저장한다. 프론트는 2~5초 간격 polling 후 READY/FAILED에서 중단한다.

## 9-1. System Status API (2026-10-05)

`GET /api/system/status?datasetId={id}&refresh=false` — 기능별 준비 상태. datasetId 선택 양수(0 이하 400, 없는 dataset 404), refresh 기본 false. 일부 기능 미지원도 200으로 표현한다. 상세 설계: [개선 기획서 7장](docs/frontend-integration-plan.md).

```json
{"schemaVersion":1,"instanceId":"<uuid>","checkedAt":"...",
 "dataset":{"id":1,"version":"v1.0-mini","origin":"SYNTHETIC","metadataChecksum":"<64-hex>","mediaValidation":"PARTIAL"},
 "capabilities":{"catalog":{"state":"READY","canExecute":true,"reasonCode":null,"message":null,"checkedAt":"...","expiresAt":"..."},
  "media":{...},"search":{...},"vespa":{...,"executor":"local"},"recording":{...}}}
```

- `instanceId`: DB에 한 번 생성되는 공개 UUID(`system_instance`, 재시작해도 동일). 다른 DB의 같은 jobId를 구분하는 용도이며 비밀값이 아니다.
- `dataset.origin`: SYNTHETIC/NUSCENES/UNKNOWN. importer가 `NUSCENES_DATA_ORIGIN` 설정을 import checksum과 함께 `dataset_provenance`에 기록한 경우에만 그 값을 쓰고, 기록이 없거나 checksum이 다르면 UNKNOWN. 이름·version·sample 수로 추정하지 않는다. 기존 명시 출처는 덮어쓰지 않고 UNKNOWN만 같은 checksum에서 갱신한다.
- `mediaValidation`: NOT_CHECKED/PARTIAL/VERIFIED/FAILED. PARTIAL은 import 때 모든 sample_data/map 파일 경로 존재를 확인했다는 뜻이며 내용 검증이 아니다.
- `state`: READY(가벼운 필수 검사 통과, 실제 추론 성공 보장 아님)·CONFIGURED(설정만 확인)·UNAVAILABLE(미지원/누락/실패)·UNKNOWN(AI 연결 실패·timeout 등). 작업 시작 가능 여부는 `canExecute`만 본다. reasonCode 예: `MEDIA_NOT_FULLY_VALIDATED`, `MEDIA_FILES_MISSING`, `MEDIA_ROOT_UNAVAILABLE`, `EMBEDDINGS_NOT_READY`, `MODEL_NOT_READY`, `CLIP_NOT_DEPLOYED`, `MODEL_MISMATCH`, `EXECUTOR_NOT_CHECKED`, `VESPA_NOT_CONFIGURED`, `VESPA_RUNTIME_NOT_READY`, `VESPA_REMOTE_UNREACHABLE`, `VESPA_REMOTE_NOT_READY`, `SYNTHETIC_DATASET`, `DATASET_MISMATCH`, `LEGACY_NOT_VERIFIED`, `AI_UNREACHABLE`, `AI_TIMEOUT`, `AI_ENDPOINT_UNSUPPORTED`, `AI_HTTP_ERROR`, `RECORDING_SDK_MISMATCH`, `RECORDING_STORAGE_UNAVAILABLE`. message는 한국어 안내.
- media: 첫 sample의 keyframe 파일만 확인하는 표본 검사(READY는 VERIFIED provenance일 때만). search: AI CLIP READY + model/preprocess 일치 + 선택 dataset의 해당 model/preprocess embedding 1개 이상(전체 coverage 검증 아님). vespa: worker 설정, SYNTHETIC 차단, Spring 설정 version·AI datasetVersion/metadataChecksum 일치, AI READY 만료 전. recording: worker 설정, recording root 읽기, AI recording READY + SDK 0.38.1.
- 이전 AI(`/capabilities` 404)는 `/health`로 읽는다. configured는 READY로 올리지 않고 `LEGACY_NOT_VERIFIED`(CONFIGURED, canExecute=false)로 둔다. AI 연결 실패는 UNKNOWN이며 mock으로 대체하지 않는다.
- AI 응답은 Spring에서 15초 캐시(`system-status.ai-cache`), 동시에 하나만 조회한다. `refresh=true`는 AI에 읽기 전용 재확인을 요청하며 추론·sbatch·embedding 생성·import를 실행하지 않는다. 실패한 refresh가 이전 READY를 대체한다.

## 10. Enum / 상태

- Job status: PENDING → RUNNING → COMPLETED 또는 FAILED. claim 전 실패도 DB schema상 가능하다.
- ClassMode: 1 (`vehicle`), 3 (`vehicle,pedestrian,bicycle`), 8 (`car,truck,bus,trailer,construction_vehicle,pedestrian,motorcycle,bicycle`).
- mappingName: 1class/3class/8class. coordinateFrame: WORLD. scoreType: VESPA_CONSTANT (현재 wrapper).
- ArtifactType: FINAL_JSON/RERUN/OTHER (현재 저장 경로는 FINAL_JSON만 생성).
- Embedding status: STORED/SKIPPED.
- Recording status: PENDING → RUNNING → READY 또는 FAILED. job status와 별개다.

## 11. 내부 FastAPI 계약 / Health

추가(2026-10-05): `GET /livez`(프로세스 생존만), `GET /capabilities?refresh=false`(clip/vespa/recording의 state·reasonCode·modelName/preprocess·executor·datasetVersion·metadataChecksum·sdkVersion·checkedAt/expiresAt). refresh=true일 때만 VESPA 확인: local은 `VESPA_PYTHON`으로 entry module import, ssh는 원격 `test -f`/`command -v sbatch squeue`만 실행(시간 상한, 단일 실행, 결과 만료 기본 600초). CLIP 로딩 실패는 서버를 종료하지 않고 CLIP만 UNAVAILABLE(`CLIP_LOAD_FAILED`)로 둔다; `/health`는 기존처럼 503. 이전 fail-fast 동작은 `AI_REQUIRE_CLIP=true`.

프론트엔드에서 직접 호출하지 않는다. `/docs`, `/openapi.json`으로 Pydantic 계약 확인 가능.

|Method|Path|body|성공|오류|
|---|---|---|---|---|
|GET|`/health`|없음|200 `{status,service,inference:{clip,vespa},device}`|503 CLIP not ready; 모델 startup 실패는 프로세스 기동 자체 실패|
|POST|`/embedding/text`|`{"text":"rainy night road"}`|200 `{model_name,dimension:768,embedding:[...],preprocess:"clip-text-tokenizer"}`|422 입력,503 미준비,500 inference|
|POST|`/embedding/image`|`{"image_path":"samples/CAM_FRONT/example.jpg","preprocess":"lr-square-crop-mean"}`|200 같은 embedding 구조|422 입력,404 파일 없음,400 잘못된 경로/이미지,503 미준비,500 inference|
|POST|`/auto-label`|`{"scene_name":"scene-0061","class_mode":8,"job_id":12,"execution_token":"UUID"}`|200 아래 구조|422 입력,404 scene 없음,409 실행 중,503 미설정/실행불가,502 실행/출력 오류,504 timeout|
|POST|`/recordings`|Spring이 DB에서 만든 scene sample·LIDAR_TOP·pose·calibration·GT·예측 (snake_case)|200 파일 경로·checksum·timeline·entity·sample별 개수|422 입력,404 lidar 파일 없음,503 SDK/설정 없음,502 exporter 실패,504 timeout|

AI 요청에는 path/query 변수가 없다. image 파일 upload는 현재 지원하지 않고 상대 경로 JSON만 받는다. image preprocess 대안 `openclip-eval-224-centercrop`도 AI는 지원하지만 Spring 기본 저장/검색 정책은 lr-square-crop-mean이다.
Auto-label job_id/execution_token은 둘 다 생략하거나 둘 다 제공하며 Spring은 항상 제공한다. 응답: `run_id,scene_name,class_mode,job_id,execution_token,mapping_name,split,coordinate_frame,score_type,meta,results,artifact_path,result_checksum`. results는 `{sample_token:[{sample_token,translation:[x,y,z],size:[w,l,h],rotation:[w,x,y,z],velocity:[vx,vy],detection_name,detection_score,attribute_name}]}`.
`/recordings` 요청/응답 필드는 [Rerun recording 계약](docs/rerun-recording.md) 4장. AI 업무 오류는 `{"detail":{"code":"...","message":"..."}}`, Pydantic 422는 detail 배열이다. Spring이 이를 그대로 프론트에 중계하지 않는다.
`health.inference.vespa=configured`는 경로/파일 설정 검사이고 모델 실행 성공 보장이 아니다. Spring 별도 health endpoint는 현재 없다. 단순 접근 확인은 GET /api/datasets를 사용한다.

## 12. 프론트엔드 호출 순서

1. GET /api/datasets → dataset ID 확보.
2. 목록 탐색은 dataset scenes → scene samples → sample detail → camera contentUrl.
3. 이미지 embedding 준비는 POST /api/sensor-files/{id}/embedding (이미 준비되어 있으면 SKIPPED).
4. 자연어 검색은 GET /api/search/scenes → sceneId/sceneToken/datasetId 확보.
5. 선택 scene의 token으로 POST /api/auto-label/jobs, 새 사용자 실행마다 새 Idempotency-Key. 네트워크 재시도에는 같은 키 유지.
6. GET /api/auto-label/jobs/{id} polling. FAILED는 errorMessage 표시, COMPLETED일 때 /results 호출.
7. results.sampleTokens와 scene sample 목록의 token을 연결해 sample ID를 구하고 /api/samples/{id}/annotations로 GT를 읽는다.
8. 같은 world 좌표계에서 GT/예측을 비교한다. 카메라 투영 시 world→ego→sensor 역변환과 intrinsic 적용이 필요하다.
9. 3D는 GET /api/scenes/{sceneId}/recordings로 기존 recording을 찾고, 없거나 FAILED뿐이면 POST(필요 시 COMPLETED jobId) → GET /api/recordings/{id} polling → READY의 contentUrl을 Web Viewer에 연다.
10. 라벨 편집은 8-1장 PATCH/DELETE 후 해당 GT(sample annotations, scene annotations)나 job 결과와 기록(label-edits)만 다시 읽는다. 결과 재조회는 새 VESPA 작업을 만들지 않는다.

## 13. 운영 제약 / 실행 / 검증

- MVP는 Spring DB polling worker + FastAPI sync subprocess. VESPA 프로세스 timeout 7200초, Spring read timeout7300초, connect5초. CLIP read timeout30초. timeout 설정은 Spring이 VESPA보다 충분히 길어야 한다.
- Recording: Spring read timeout `recording.read-timeout`(기본 660s, exporter 600s보다 길게), 파일 root `recording.root`(기본 `/recordings`), 기대 SDK `recording.sdk-version`(0.38.1), `recording.export-version`(ds2l-rrd-v3). RUNNING 도중 종료 복구는 job과 같이 없다.
- FastAPI `--workers 1`, Spring worker 한 인스턴스를 권장한다. VESPA lock은 프로세스별이다. 여러 Spring worker를 동시에 돌리면 AI busy409로 job FAILED가 될 수 있다.
- RUNNING 도중 Spring 종료/네트워크 단절 후 자동 lease 복구, retry queue, 취소 API는 없다. 운영 전 복구 정책이 필요하다. 결과를 받지 못해 FAILED여도 AI 파일이 남을 수 있다.
- VESPA 원본 main의 부분 scene 출력 제한을 외부 vespa_runner.py에서 우회하고 원본 writer 변환 함수를 재사용한다. 원본 저장소는 수정하지 않는다. 자세한 설정은 [VESPA wrapper](ai-server/VESPA.md).
- 실행 절차/실제 mini 시나리오/발표 설명: [통합 검증](docs/integration-verification.md).
