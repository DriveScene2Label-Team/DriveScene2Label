# DriveScene2Label 프론트

React 19 + TypeScript + Vite 8 앱이다. 브라우저는 Spring `/api/*`만 호출한다. 개발·미리보기 서버는 `/api`(JSON, JPG, `.rrd`)를 Spring으로 proxy하며 FastAPI·DB 주소는 프론트에 두지 않는다. 기준 문서는 [개발 기획서](../docs/frontend-product-plan.md), [구현 체크리스트](../docs/frontend-implementation-checklist.md), [REST 계약](../README_API.md), [Rerun recording 계약](../docs/rerun-recording.md)이다.

## 실행

```bash
cd frontend
npm ci
cp .env.example .env.local      # 필요 시 API_PROXY_TARGET 변경 (기본 http://127.0.0.1:8080)
npm run dev                     # http://localhost:5173
```

Spring이 다른 PC에 있으면 `API_PROXY_TARGET`을 그 주소로 바꾼다. 배포는 같은 origin의 reverse proxy가 `/api`를 Spring으로 전달하고 나머지 경로에는 `dist/index.html`을 돌려주도록 구성한다(BrowserRouter, 새 탭 링크).

Vercel 구성은 [`vercel.json`](vercel.json)에 있다. Root Directory를 `frontend`로 지정하고, 인증 게이트웨이가 있는 공개 HTTPS origin을 `BACKEND_URL`에 넣는다. `/api`와 `/oauth2`를 전달하고 정적 자산을 먼저 제공한 뒤 SPA 경로를 처리한다. `VITE_AUTH_REQUIRED=true`로 로그인 gate를 활성화한다. API의 실제 접근 제어는 서버의 oauth2-proxy가 담당한다. 누락되거나 잘못된 origin은 Vercel 빌드에서 차단하며, 로컬 `npm run build`에는 이 값이 필요 없다. [혼합 실행 준비와 미완료 연결 항목](../docs/hybrid-setup.md)을 함께 확인한다.

| script | 내용 |
|---|---|
| `npm run typecheck` | `tsc -b --noEmit` |
| `npm run build` | 타입 검사 + 제품 빌드(`dist/`). Rerun WASM(약 51MB, gzip 16MB)은 별도 asset이며 작업대 화면에서만 lazy load |
| `npm test` | Vitest 단위 테스트(기하·DTO 변환·시간·재시도·receipt·A/B 상태·이미지 캐시) |
| `npm run test:e2e` | Playwright. `/api/*`를 실제 DTO 형식 route fixture로 응답하는 UI 흐름 검증(실제 서버 연동 아님). `webkit-1440` project는 `@a11y` 검사만 Playwright headless WebKit으로 실행(Safari 앱 검수 아님, `npx playwright install webkit` 필요) |

Rerun 기술 검증 e2e는 실제 rerun-sdk 0.38.1로 만든 `.rrd`가 있을 때만 실행된다.

```bash
# ai-server/RECORDING.md 의 방법으로 합성 recording 생성 후
DS2L_RRD=/path/to/scene-test.rrd npx playwright test tests/e2e/viewer.spec.ts --project=desktop-1440
```

실행 중인 Spring을 대상으로 한 live 검증(route mock 없음, 데이터 내용과 무관한 검사):

```bash
DS2L_API=http://127.0.0.1:8080 npx playwright test -c playwright.live.config.ts tests/live/live.spec.ts
# 선택: DS2L_LIVE_JOB_ID=<기존 job>  /  DS2L_LIVE_ALLOW_POST=1 (recording 생성 허용)
# 이미 떠 있는 앱을 쓰려면 DS2L_BASE_URL=http://127.0.0.1:5174 (빌드·preview 생략)
```

`live.spec.ts`는 데이터와 무관한 점검이라 검색 오류·빈 결과·recording FAILED도 "표시됨"으로 통과한다(장애 안내 확인용). **실제 nuScenes 성공 검증은 `actual-mini.spec.ts`**이며 출처 NUSCENES, 여러 프레임의 6카메라 ready, API와 같은 GT 수, LIDAR_TOP 존재를 모두 요구한다. 합성/출처 미확인 데이터에서는 실패한다.

```bash
DS2L_ACTUAL=1 DS2L_API=http://127.0.0.1:8080 [DS2L_DATASET=<id>] [DS2L_SCENE=<id>] [DS2L_LIVE_ALLOW_POST=1] \
  npx playwright test -c playwright.live.config.ts tests/live/actual-mini.spec.ts
```

live 검증은 job을 만들지 않는다. VESPA job 생성은 실제 GPU 실행이므로 사람이 화면에서 실행한다.

## 구조

```text
src/
  app/          router, QueryClient, URL 문맥(urls.ts)
  api/          dto.ts(Spring 그대로) → mappers.ts → models.ts, http.ts(오류 모델), queries.ts(query key)
  pages/        SceneSearchPage, SceneWorkspacePage, SceneComparePage
  features/
    frames/     useFrameBundle·usePaneFrames: requested/displayed 프레임, prefetch, 재생
    cameras/    CameraGrid/Tile/Overlay/Dialog
    timeline/   FrameTimeline
    objects/    LayerToggles, ObjectInspector, 예측 연결
    labeling/   JobPanel(생성·receipt·polling·소속 검증), jobLogic
    viewer/     RecordingPanel, RerunViewer, recordingMap
    workspace/  PaneView, 단축키·숨김 탭 정지
  stores/       workspace(single/A/B 패널 상태), layout(선호), toast
  lib/          geometry(투영), time(timeline), jobs(idempotency·receipt), classes(VESPA mapping), imageCache
  styles/       index.css(시안 토큰 + 컴포넌트 스타일)
tests/e2e/      Playwright + fixtures/mockApi.ts
tests/live/     실제 Spring 대상 검증
```

## 상태 책임

| 위치 | 내용 |
|---|---|
| TanStack Query | dataset·scene·samples·sample detail·GT·calibration(`calibratedSensorToken`별)·pose(파일별)·검색·job·recording |
| Zustand | 패널별 dataset/scene/requested·displayed sample/재생/속도/레이어/선택/classMode/job/결과 job/recording/보기 |
| URL | `/scenes?dataset&q`, `/scenes/:id?dataset&sample&job&view=split|six`, `/compare?datasetA&sceneA&sampleA&jobA&…&sync=relative&active=B` |
| localStorage | 배치 선호(`ds2l.layout`), job 생성 receipt(`ds2l.jobReceipts.v2`, 서버 instanceId별, 최대 120개). v1 `ds2l.jobReceipts`는 읽기만 하고 수정·연결하지 않음. 이미지·점군·결과는 저장하지 않음 |
| 메모리 | 카메라 JPG blob URL LRU(참조 중인 이미지 유지, 나머지 48개 초과 시 revoke·다운로드 취소) |

## 주요 구현 결정

### 연동 개선 (2026-10-05, [개선 기획서](../docs/frontend-integration-plan.md))

- `GET /api/system/status`를 읽어 데이터 출처 배지(테스트 데이터/출처 미확인/nuScenes 원본)와 기능별 준비 상태를 표시한다. VESPA 실행·recording 생성은 `canExecute=true`일 때만 버튼을 연다. CONFIGURED/UNKNOWN은 "실행 환경 확인"(refresh=true, 읽기 전용)으로 다시 확인한다. 상태 API가 없는 이전 서버는 실행을 막고 "출처 정보 없음"으로 표시한다. 검색은 서버가 UNAVAILABLE이라고 할 때만 막는다.
- 준비 상태 판정(2026-10-06, FU-01): 화면이 쓰는 값은 "현재 판정"뿐이다. 최신 status 조회가 실패하면(연결 실패·HTTP 오류) Query 캐시에 이전 READY가 남아 있어도 모든 기능을 `UNKNOWN / STATUS_UNREACHABLE`로 보고 실행을 막는다. 유효 시간은 브라우저 시계로 `응답 수신 시각 + min(서버 expiresAt − checkedAt, 90초)`이며 지나면 `UNKNOWN / STATUS_EXPIRED`다(서버·브라우저 시계 차이 무시). 이전 응답은 "마지막 확인 HH:MM:SS: …(현재 판정에는 쓰지 않아요)"로만 보인다. 다시 읽기 간격은 실행 기능(media·search·vespa·recording) 중 가장 이른 만료 1초 전, 최소 10초·최대 30초이며 만료 시각과 탭 복귀 때도 다시 읽는다. 기능마다 만료 시각이 다르면 새 응답이 없어도 각 만료 시각에 화면을 다시 평가한다(예: search 15초 → VESPA 60초 → recording 90초, 2026-10-06 보완). 만료 시각의 재조회는 진행 중인 GET이 있으면 그 요청을 함께 기다리고 새로 보내지 않는다(이 hook을 쓰는 컴포넌트가 여럿이어도 만료 1회당 최대 1건). `STATUS_*` 사유의 "상태 다시 확인"은 가벼운 GET이고, 실제 기능 사유일 때만 `refresh=true`("실행 환경 확인")를 보낸다. 이미 받은 완료 결과·박스 표시는 막지 않는다.
- 이전 작업 이력(FU-02): v1 receipt(`ds2l.jobReceipts`)와 이전 자동 이전이 만든 v2 `paneId='legacy'` 항목은 원래 DB를 증명할 수 없어 어떤 서버의 job으로도 복원·선택·소속 검증에 쓰지 않는다. 같은 jobId·dataset·sceneToken이 일치해도 마찬가지다(재import된 DB는 같은 값을 가질 수 있음). 저장 내용은 지우지 않고 작업 패널에 "확인되지 않은 이전 기록 N건"으로만 표시한다.
- job 실패는 서버 `errorCode`로 원인·조치를 안내한다(`lib/errorCodes.ts`). 코드 없는 HTTP 502/504는 중계/상위 서비스 오류로 표시하며 모델 실패로 단정하지 않는다.
- 요청 snapshot(`lib/jobs/submissions.ts`): instanceId·dataset/checksum·scene·pane·classMode·key·요청 시각·UI generation. 요청은 컴포넌트 밖에서 이어지며, 응답은 snapshot으로 receipt를 남기고 그 pane이 같은 서버·dataset·scene·generation일 때만 화면에 연결한다. pane generation은 다른 씬을 열 때마다 증가한다(A→B→A도 새 값).
- receipt는 `ds2l.jobReceipts.v2`에 서버 instanceId별로 저장한다. instanceId가 바뀌면 서버 데이터 캐시와 패널의 job/recording 선택을 비운다.
- Rerun: 파일 다운로드 실패와 Viewer 시작 실패를 구분하고 "같은 recording 다시 열기"는 이전 fetch·channel·listener·Viewer를 정리한 뒤 같은 파일만 다시 연다(생성 POST 없음). 45초 이상 열리지 않으면 다시 열기를 안내한다. 서버가 `RECORDING_FILE_MISSING`을 주면 recording 상태를 다시 읽어 재생성을 안내한다.
- GT/예측 토글은 **카메라 라벨 범위**다(그룹 이름·안내 표시). 3D 보기의 표시는 Viewer에서 조절하며, 토글↔3D 연동과 목록→3D 선택 강조는 후속 미완료다.

- 카메라 배치는 channel 이름 기준(FL/F/FR, BL/B/BR). 빈 영역 크기에 따라 3×2/2×3을 자동 선택한다.
- 프레임은 sample detail, GT, 카메라별 calibration·pose, 6개 JPG decode가 모두 끝나야 화면에 전환한다. 그 전에는 이전 프레임을 유지하고 “불러오는 중”을 표시한다. 늦은 응답은 다른 sample의 묶음이라 표시 프레임에 섞이지 않는다.
- 재생 간격은 인접 sample `timestampUs` 차이 / 속도(0.5·1·2×). 다음 프레임이 준비될 때까지 기다린다. 탭이 숨겨지거나 작업대를 떠나면 정지한다.
- 투영: `p_world = R·p_local + c`(local x=L, y=W, z=H) → ego pose 역변환 → calibration 역변환 → K. 12개 edge를 near plane(0.1 m)에서 자른 뒤 이미지 사각형으로 clip한다. overlay SVG는 원본 width×height viewBox와 `xMidYMid meet`로 이미지 `object-fit: contain`과 같은 매핑을 쓴다.
- GT 원본 category를 보존하고, 1/3/8종 비교 분류는 VESPA upstream `assets/class_mapping/*.yaml`(commit acb2b6e) 표를 그대로 쓴다. 미매핑은 “비교 분류 없음”.
- job: 사용자 실행마다 새 Idempotency-Key, 응답 유실·502~504는 같은 key로 최대 2회 자동 재시도 후 “같은 요청 다시 보내기”. status 3초 polling, GET 실패는 5초 재시도하며 “연결을 확인할 수 없어요”로만 표시. 완료 결과 GET 실패는 결과만 다시 읽는다.
- job 소속 검증: 서버 job 문맥(sceneToken) → 로컬 receipt → 완료 결과 sampleTokens 순서. 확인 전에는 “작업 대상 확인 필요”, 불일치하면 결과를 연결하지 않는다.
- Rerun: `@rerun-io/web-viewer@0.38.1`. Spring content를 fetch해 `open_channel().send_rrd()`로 전달한다(0.38.1은 `.rrd`로 끝나지 않는 HTTP URL을 recording으로 인식하지 않음). React 타임라인이 기준이며 Viewer의 `sample` 타임라인과 양방향 연결, 자기 echo는 무시한다. 선택은 entity path + instance id → recording metadata의 GT/예측 id로 바꾼다. 비교 화면에서는 활성 패널 하나만 Viewer를 연다.
- 버튼 대비: 주요 파랑 `#216FE5`(흰 글자 4.70:1), hover `#1D64D6`(5.46:1).
