# 프론트 구현 체크리스트

## 2026-11-11 혼합 MVP 후속 검증

- [x] ZIP/TGZ/TAR.GZ 선택과 분할 업로드 연결. 손상된 ZIP 끝부분과 gzip footer, TAR 링크·경로·해제 한도 검증 추가.
- [x] 복원 DB에 남은 maintenance 플래그로 POST가 503이던 원인 확인·운영 플래그 해제. 시작 절차에 인증된 resume와 무자료 쓰기 경로 확인 추가.

- [x] 업로드 데이터셋 검색 인덱스 진행률·자동 생성·재시도 UI 및 실제 GPU CLIP 이미지 1개 인덱싱/검색 검증(별도 테스트 DB).
- [x] 4MB 분할 전송·세션 재개·비동기 등록 UI, 서버 조각 순서·중복 전송 검증.
- [x] 신규 VESPA 결과의 trackId 표시 및 객체별 기준 프레임 후처리 UI. 원본 작업을 유지하고 새 작업을 생성하며, 재시도 시 idempotency key를 유지한다.
- [x] 프론트 빌드와 75개 테스트 통과. Spring 49개 테스트와 별도 AI/실제 VESPA 객체 기반 후처리 fixture 검증 통과.
- [ ] 사용자 공개 경로에서 실제 4.34GB ZIP 업로드부터 전체 씬 VESPA·후처리까지 완료.
- [ ] 반복 eGPU TDR의 근본 원인 규명 및 장시간 안정성 검증.

세부 결과와 제한은 [MVP 갱신 기록](hybrid-mvp-update-2026-11-11.md)에 있다. 아래는 기존 개발 시점의 기록이다.

> **2026-11-05 UI/UX 리뉴얼**(브랜치 `feature/frontend-renewal`)의 범위·목업과의 차이·검증(R-01~R-07)은 [프론트 리뉴얼 기록](frontend-renewal.md)에 따로 남긴다. 라벨 편집 API는 [README_API 8-1장](../README_API.md). 아래 M1~M6 기록의 화면 묘사(다크 시안, 6개 카메라 버튼 이름 등)는 리뉴얼 이전 상태다.
>
> 후속 개선은 [개선 기획서](frontend-integration-plan.md)와 [별도 개선 체크리스트](frontend-integration-checklist.md)에서 추적한다. 아래 M1~M6 및 V-01~V-10은 기존 구현·검증 범위의 기록이며 새 개선 완료로 옮겨 체크하지 않는다.

기준: [개발 기획서 v1.2](frontend-product-plan.md). 작업 브랜치: `codex/frontend-implementation` (시작 HEAD `501da08`, 이번 작업은 미커밋 작업 트리). 기능별 세부 요구는 기획서 FR-01~24, 검증은 QA-01~17을 따른다.

**현재 상태 (2026-10-04):** M1~M6의 코드와 GT category·job 문맥·Rerun recording 백엔드/AI 보완을 구현했다. 단위·fixture e2e·Spring/AI 테스트와, 실제 Spring+PostgreSQL(저장소 test fixture 메타데이터)·실제 rerun-sdk 0.38.1 exporter를 잇는 브라우저 통합을 확인했다. **실제 nuScenes mini 데이터, 실제 CLIP 검색, 실제 VESPA(GPU) job, Docker 이미지 빌드/compose 기동은 이 환경에서 검증하지 못했다.** 따라서 어떤 단계도 “실제 데이터 기준 완료”로 표시하지 않는다.

완료한 항목만 체크한다. 체크는 “코드 구현 + 표기한 범위의 검증”을 뜻하며 실제 mini 통합 여부는 각 단계의 상태 줄과 검증 기록에 따로 적는다.

## 이번 작업 환경

| 항목 | 확인 결과 |
|---|---|
| 도구 | macOS(Apple M4), Node 24.15 / npm 11.12, Docker 29.2(Desktop), Python 3.13. 로컬 JDK 없음 → Spring은 `scripts/docker-test.sh`와 temurin 컨테이너로 빌드·테스트 |
| 데이터 | nuScenes 원본 없음. 저장소 `src/test/resources/nuscenes/v1.0-mini`(씬 1·sample 1·센서 7) 합성 메타데이터만 사용 |
| AI | GPU 없음, CLIP/VESPA 모델 미다운로드. recording 라우터만 호스트에서 개발 하네스로 실행 |
| 버전 고정 | React 19.3, react-router 7.18.4, TanStack Query 5.104.1, Zustand 5.0.15, Vite 8.3.2, TypeScript 5.9.3, Tailwind 4.3.3, Radix(shadcn) Dialog/Slot, Vitest 5.0.3, Playwright 1.63.0, `@rerun-io/web-viewer` 0.38.1 / `rerun-sdk` 0.38.1 (exporter) |

## P0 · 준비 및 Rerun 기술 검증

- [x] 수정 HTML·핸드오프 원본과 디자인 결정을 `docs/frontend-design/`에 보관.
- [x] 기존 Spring API를 기준으로 프론트 기획서 v1.1 정리 (구현 반영 v1.2).
- [x] 구현용 브랜치, CLAUDE.md, 체크리스트, 시작 프롬프트 준비.
- [x] 현재 코드·실행 환경·사용 가능한 실제 dataset/scene/job 확인. HEAD `501da08`. 실제 dataset/job은 이 환경에 없음(위 표).
- [x] Python Rerun pin과 웹 Viewer 호환 조합 확인·기록. 0.21.0 Viewer는 `ready`/`fullscreen` 이벤트만 있고 시간·선택 API가 없음 → exporter `rerun-sdk==0.38.1` + `@rerun-io/web-viewer@0.38.1`로 함께 고정, VESPA venv 0.21.0 유지. [근거](rerun-recording.md#1-버전-결정)
- [x] 작은 실제 .rrd 생성 및 브라우저 로딩·시간 제어·선택 이벤트·resize·자원 해제 검증. 실제 SDK로 만든 **합성** recording(nuScenes 아님) 기준. 결과는 검증 기록 V-07/V-08.

## M1 · 프론트 기반·실제 API

- [x] React/TS/Vite, npm lockfile, Router/Query/Zustand, Tailwind/shadcn 구성(`frontend/components.json`, shadcn Button/Dialog를 시안 토큰으로 스타일).
- [x] `.gitignore`, 예제 환경 설정(`frontend/.env.example`), `/api` JSON·이미지·.rrd proxy, npm scripts, README 실행 안내.
- [x] 디자인 토큰·앱 shell·탐색/작업대/비교 route 구현.
- [x] 실제 DTO, HTTP 오류 모델(`{code,message}`와 Spring 기본 오류, 연결 실패 구분), mapper, query keys.
- [x] dataset→scene→samples→sample detail 조회, 직접 링크·dataset 복구·pagination(limit 500 반복).

상태: 코드·단위·fixture e2e 완료, 실제 Spring(fixture 메타데이터) 조회 확인(V-05). 실제 nuScenes mini 목록은 미확인.

## M2 · 6카메라·확대·타임라인

- [x] 6채널 이름 기반 배치, 실제 JPG(blob URL·decode), 원본 width/height, 누락·다운로드 오류(404/다운로드/decode 구분) 상태.
- [x] 6카메라/카메라+LiDAR 모드, 분할 경계 드래그·키보드(←/→/Home/End/Enter·더블클릭 기본값), 우측 패널 접기.
- [x] 확대 모달·카메라 전환·←/→ 프레임·Esc·포커스 복귀.
- [x] sample 이동·timestamp 기반 재생/속도(0.5/1/2×), requested/displayed sample 구분, 끝에서 정지.
- [x] 이미지/박스 프레임 준비 정책(모두 준비되면 함께 전환), 인접 prefetch(앞 1~2·뒤 1), 이전 응답 배제, 숨겨진 탭 정지·blob URL LRU 해제·Viewer stop.

상태: fixture e2e(QA-03/04/13, 재생)와 실제 Spring 응답의 6개 JPG 표시(V-05) 확인. fixture가 sample 1개라 **실제 데이터로 프레임 이동은 미확인** → 첫 구현 묶음의 “실제 씬 이동” 완료 판정은 mini 환경에서 남음.

## M3 · 검색·VESPA 작업·복원

- [x] 자연어 검색·대표 이미지/프레임·빈 결과·오류. 실제 `scenes[]` 계약 사용, score는 “유사도 점수”(확률 아님).
- [x] 실제 sceneToken/datasetId/classMode로 job 생성, 요청 중 버튼 비활성, 실행 receipt(localStorage) 보관.
- [x] 동일 의도 네트워크 재시도는 같은 Idempotency-Key(응답 유실·502~504 자동 2회 + “같은 요청 다시 보내기”), 새 사용자 실행은 새 key.
- [x] status polling(3초, GET 실패 시 5초)·terminal 중단·completedAt 경과 시간·GET 연결 오류 구분.
- [x] 결과 boxes/sampleTokens 연결, 정상 빈 박스, 새 실행 중·실패 시 이전 완료 결과 보존·표시 중인 작업 명시.
- [x] 완료 결과 ‘결과 다시 불러오기’, 알려진 jobId URL 복원, job 소속 검증(서버 문맥 → receipt → 결과 sampleTokens) 또는 ‘작업 대상 확인 필요’, 없는 job 안내·연결 해제.

상태: fixture e2e(QA-06/07/14/15, FR-23/24)와 실제 Spring의 검색 503·job FAILED 표시(V-05) 확인. **실제 CLIP 검색 결과와 실제 VESPA 완료 job 조회는 미확인.**

## M4 · 투영·GT 클래스

- [x] GT annotation categoryToken/categoryName JOIN(dataset 범위)·DTO 보완 및 README_API 갱신. dataset 격리 Spring 테스트 포함.
- [x] 원본 category 보존, 1/3/8 mapping(VESPA upstream `class_mapping/*.yaml` 그대로), 미매핑 ‘비교 분류 없음’, category 없음 ‘클래스 정보 없음’.
- [x] 박스 로컬 축·WLH·WXYZ, 카메라별 world→ego→sensor→pixel 변환·near plane clipping·이미지 clip.
- [x] 원본 이미지 크기·object-fit·resize·확대에 맞는 overlay(SVG viewBox + `xMidYMid meet`).
- [x] GT 점선/예측 실선·레이어·객체 목록/선택/상세(소스·원본/비교 분류·WORLD 위치·W/L/H·회전), 같은 sample 보장.
- [ ] 계산 경계 검증과 실제 이미지/devkit 참고 결과 비교. 단위 기하 검증(수기 계산 픽셀·축·clipping)은 완료, **실제 nuScenes 이미지·devkit `render_sample_data` 비교는 미실행.**

## M5 · Rerun 생성·제공·연결

- [x] recording API 초안을 실제 계약으로 정리하고 metadata/state/timeline/box mapping 명세 갱신([rerun-recording.md](rerun-recording.md)).
- [x] 원본 센서·GT 및 완료 job 예측의 recording exporter, 재사용·실패 재시도 구현(AI `services/recording_exporter.py`, Spring `RecordingService/Worker`, V5 migration).
- [x] 저장소·Compose volume(`rerun_recordings`, backend 읽기 전용)·Spring metadata/content 제공 연결. compose config 검증, **Docker 이미지 빌드·compose up은 미실행**.
- [x] 버전 호환 Rerun Web Viewer, WASM 자산(Vite asset)·로딩·준비/실패 상태·자원 해제 구현. content는 fetch 후 log channel로 전달.
- [ ] 공통 타임라인·sample mapping·이벤트 루프 방지·레이어/객체 연결 검증. 시간 양방향 연결·루프 방지·박스 선택 mapping은 합성 recording으로 확인(V-07/V-08). **GT/예측 레이어 토글은 카메라에만 적용**되고 Viewer entity 표시는 연동하지 않음(0.38.1 JS API에 entity 표시 전환 없음, blueprint 기반 후속 검토).
- [x] recording 실패 복구가 VESPA 재실행 없이 동작하는지 확인(Spring 테스트, fixture e2e QA-16, 실제 Spring 실패→재요청 V-05).
- [ ] 실제 점군·GT·예측을 실제 sample/job과 함께 열고 통합 검증 기록. 실제 Spring→실제 exporter→Viewer 체인은 fixture 메타데이터·합성 LiDAR로 확인(V-06), **nuScenes 실제 점군·완료 job 예측은 미확인.**

## M6 · A/B 비교·최종 검수

- [x] pane별 dataset/scene/sample/job/레이어/재생/선택 분리. Query cache 공유.
- [x] 서로 다른 씬과 동일 씬의 서로 다른 프레임 비교.
- [x] 활성 A/B 표시·우측 작업 대상·패널별 새 탭/공유 URL(`active`, `sync` 포함) 일치.
- [x] timestamp 기반 상대 위치 동기화(동기화로 생긴 변경은 다시 전파하지 않음), off 시 독립, 단일 프레임 예외.
- [x] 비교 6카메라 및 활성 패널 단일 Rerun 구성. 동시 두 Rerun은 후속 성능 범위.
- [ ] 1440/1280/1024/768/375 화면, 키보드·focus·reduced-motion·버튼 대비 확인. 5개 크기 가로 스크롤 없음·주요 요소 표시(e2e + 스크린샷), 모달 focus 복귀, 분할 키보드, 버튼 대비 계산은 완료. **reduced-motion 실제 확인·스크린리더·실기기 375 사용성 검수는 미실행.**
- [ ] typecheck/build/관련 테스트, QA-01~17, 실제 mini 통합 기록. 자동 검사는 모두 통과(검증 기록), **QA의 실제 mini 확인은 미실행.**
- [x] README/API/기획서/체크리스트를 최종 구현과 일치시킴.

## QA 시나리오 대응

| QA | 확인 방법 | 결과 |
|---|---|---|
| QA-01 검색 후 대표 프레임 | e2e `explore` | 통과(fixture). 실제 CLIP 미확인 |
| QA-02 새 탭·새로고침 복원 | e2e `explore` | 통과(fixture) |
| QA-03 빠른 이동·늦은 응답 | e2e `explore`(1.5초 지연 응답) | 통과(fixture) |
| QA-04 카메라 누락·실패 | e2e `explore` | 통과(fixture) |
| QA-05 분할·확대 좌표 | e2e `explore`(정렬 측정) + 단위 `fit` | 통과(fixture). 실제 이미지 미확인 |
| QA-06 POST 유실 재시도 | e2e `jobs` + 단위 `createJob` | 통과(같은 key 2회, job 1개) |
| QA-07 GET 일시 실패 | e2e `jobs` | 통과(FAILED로 표시 안 함) |
| QA-08 박스 없는 프레임 | e2e `jobs` | 통과(‘검출 박스 없음’) |
| QA-09 A/B 같은 씬 | e2e `jobs` + 단위 store | 통과 |
| QA-10 상대 동기화·0분모 | e2e `jobs` + 단위 timeline | 통과 |
| QA-11 Rerun 준비·실패·정상 | e2e `viewer`·`jobs`, live V-06 | 통과(합성 recording·실제 Spring 체인). nuScenes 미확인 |
| QA-12 회전·축·near plane | 단위 geometry | 통과. devkit 비교 미실행 |
| QA-13 키보드·작은 화면·확대 닫기 | e2e `explore`·`layout` | 통과(부분, M6 미실행 항목 참조) |
| QA-14 다른 씬 job 링크 | e2e `jobs` + 단위 verifyJob | 통과 |
| QA-15 결과 GET 실패 후 재조회 | e2e `jobs` | 통과(POST 0회) |
| QA-16 recording 실패 재요청 | e2e `jobs`, Spring `RecordingTests`, live V-05 | 통과 |
| QA-17 GT category·mapping | e2e `explore`, 단위 classes, Spring 테스트, live V-05 | 통과(fixture/합성) |

## 검증 기록

| ID | 날짜·HEAD 또는 작업 상태 | 범위 | 명령/사용자 시나리오 | 결과·증거 | 미검증·제약 |
|---|---|---|---|---|---|
| V-01 | 2026-10-04, `501da08` + 작업 트리 | 프론트 정적 검사·빌드 | `npm run typecheck`, `npm run build` | 통과. 제품 JS 약 380KB(gzip 119KB) + 작업대 lazy chunk, Rerun WASM 51MB(gzip 16MB) 별도 asset | 배포 reverse proxy 미구성 |
| V-02 | 동일 | 프론트 단위(Vitest, jsdom) | `npm test` | 4 files / 48 tests 통과 | 브라우저 렌더링 아님 |
| V-03 | 동일 | 프론트 UI 흐름(Playwright, route fixture, Chromium headless) | `DS2L_RRD=<합성 .rrd> npm run test:e2e` | 43 tests 통과: 1440에서 explore 10·jobs 11·layout 4·viewer 2, 1280/1024/768/375 layout 각 4 | fixture는 실제 DTO 형식이지만 실제 서버 아님. 스크린샷 `frontend/test-results/screens/`(Git 제외) |
| V-04 | 동일 | Spring(실제 PostgreSQL 컨테이너) | `bash scripts/docker-test.sh` | 22 tests 통과(Demo 6·Recording 4·DatasetFiles 1·AutoLabel 4·SceneSearch 7). GT category·dataset 격리, job 문맥 필드, recording 생성/재사용/READY/FAILED/content/경로 거부/job 불변 | fake AI HTTP 서버 사용 |
| V-05 | 동일 | 실제 Spring jar + pgvector 컨테이너 + 브라우저(route mock 없음) | Spring을 test fixture(JPEG 재생성) root로 import, `DS2L_API=… npx playwright test -c playwright.live.config.ts` | 통과: dataset 1/scene 1 표시, 6채널 JPG ready, GT 1개 `vehicle.car`, 검색 503 → ‘검색하지 못했어요’, job POST→worker FAILED(“AI request failed or timed out”) 표시, recording FAILED→재요청 | AI 미기동 상태의 실패 경로. 합성 메타데이터 |
| V-06 | 동일 | 브라우저→Spring→worker→FastAPI `/recordings`→exporter(rerun-sdk 0.38.1)→Spring 검증→Viewer | 위 스택 + 호스트 recording 라우터 하네스(scene 이름 `scene-0001`로 fixture 복사), `DS2L_LIVE_ALLOW_POST=1` | 통과: recording #1 READY(0.7초), 2,000점·GT 1, size/sha256 검증, Viewer 0.38.1 로딩 | nuScenes 실제 점군·예측 없음. Docker AI 이미지 아님 |
| V-07 | 동일 | Rerun Web Viewer 0.38.1(Chromium headless, SwiftShader WebGL2) | e2e `viewer`(합성 6 sample recording) | 통과: recording_open, React 프레임 이동 → Viewer `sample` 시간 1·2 반영, 역전파 루프 없음, 분할 resize 후 캔버스가 영역을 채움, 6카메라 전환 시 stop()·페이지 오류 없음 | 소프트웨어 렌더러 성능은 실제 GPU 브라우저와 다름 |
| V-08 | 동일 | Rerun 선택 이벤트 | e2e `viewer` 박스 클릭 | 통과: `selection_change(world/gt, instance)` → metadata id → 인스펙터 상세·목록 선택 | 합성 recording의 박스 배치 기준 |
| V-09 | 동일 | AI pytest | `ai-server/.venv-recording`: `tests/test_recording.py` 9 통과·1 skip(torch 필요), `.venv-recording-full`(torch 2.10, Python 3.13): `tests` 27 통과 | 실제 rerun-sdk export와 SDK read-back 포함 | Docker(Python 3.12, torch 2.14.1) 빌드 미실행 |
| V-10 | 동일 | 형식 검사 | `git diff --check` | 통과 | — |

기록 시 unit fixture, HTTP/DB 통합, 실제 mini·모델·브라우저 검증을 구분한다. screenshot·recording 등 생성 결과는 Git 제외 경로에 두고 필요한 재현 정보만 문서에 남긴다.

## 계약·설계 결정 기록

| 날짜 | 항목 | 채택한 결정·이유 | 영향 문서/코드 |
|---|---|---|---|
| 2026-10-04 | 디자인 기준 | 작업 폴더 수정본 사용. 소스 검토 완료, 독립 시각 검수는 미완료 | frontend-design/README.md |
| 2026-10-04 | 상태/실제 연동 | 같은 씬 A/B 허용, 실제 DTO mapper, timestamp 재생 | frontend-product-plan.md |
| 2026-10-04 | 이번 필수 범위 | GT category 보완·Rerun 생성/제공 포함 | 기획서 BE-02~04 |
| 2026-10-04 | Rerun 버전 | 0.21.0 Viewer에 시간/선택 API 없음 → SDK·Viewer 0.38.1 동시 고정, exporter는 AI 기본 환경, VESPA venv 0.21.0 유지 | rerun-recording.md, ai-server/requirements.txt, frontend/package.json |
| 2026-10-04 | Viewer 로딩 | 0.38.1이 `.rrd`로 끝나지 않는 URL을 거부 → API 경로는 유지하고 프론트가 fetch 후 `open_channel().send_rrd()` | RerunViewer.tsx, README_API 9장 |
| 2026-10-04 | recording API | 초안 경로 그대로 구현 + `GET /api/scenes/{id}/recordings` 목록 추가(새로고침 복원). 상태 PENDING/RUNNING/READY/FAILED, FAILED가 아닌 동일 설정 재사용 | V5 migration, RecordingController |
| 2026-10-04 | job 문맥 | job status에 sceneToken/sceneId/sceneName/classMode/mappingName 추가(호환). 소속 검증은 서버 → receipt → 결과 순 | AutoLabelDtos, jobLogic.ts |
| 2026-10-04 | GT category | 기존 필드 유지 + nullable categoryToken/categoryName, dataset 범위 LEFT JOIN. 비교 분류는 VESPA upstream mapping 표를 프론트에서 적용 | GtAnnotationView, lib/classes.ts |
| 2026-10-04 | calibration 캐시 | query key를 sensor file id 대신 `datasetId + calibratedSensorToken`으로 두어 카메라당 1회 조회. pose는 파일별 | api/queries.ts |
| 2026-10-04 | 버튼 대비 | 주요 파랑 `#216FE5`(4.70:1), hover `#1D64D6`(5.46:1) | styles/index.css |
| 2026-10-04 | recording timeout | Spring 읽기 timeout 660s > exporter 600s (동시 만료 방지) | application.properties, compose.yml |
| 2026-11-04 | VESPA patch | 고정 commit + `ai-server/vespa-patches`(0001 barrier/traffic_cone, 0002 가려진·너무 깊은 점 제거). Docker·Colab 같은 apply.sh. V13 migration, Spring/AI/프론트 8class 목록 확장. 2026-11-05 Colab GPU로 mini 10개 씬 실행(8class box 7,740→9,128, barrier 1,147·traffic_cone 445), scene-0061 작업대 표시 확인. GT 대비 정확도 비교는 미실행 | ai-server/VESPA.md, docs/superpowers/specs/2026-11-04-vespa-p1-p2-design.md |
| 2026-11-05 | 일치도 재보정·단계 | 100점 기준을 긴 설명 문장(0.259)에서 짧은 검색어 정답 중앙값(0.232)으로 변경. 맞는 짧은 검색어 중앙값 69→100점, 오답 중앙값 37→54점(구분력 AUC 0.81은 그대로). 카드에 단계(80+ 잘 맞음/50+ 관련 있음/약함) 추가. 검색어 template 방식은 점수만 부풀려 제외 | docs/search-match-score.md, scripts/match_score_queries.mini.json |
| 2026-11-04 | 검색 일치도 | 응답에 `matchScore`(0..100) 추가, 기존 score 유지. 기준점은 scene 설명으로 보정해 application.properties에 둠. 카드 "일치도 N점", 툴팁 원래 코사인+확률 아님, % 없음. 신뢰도/변별도 필드는 만들지 않음 | docs/search-match-score.md, MatchScoreCalibration |
| 2026-10-04 | job 실행 제한 | 선택한 job이 PENDING/RUNNING이면 같은 패널의 새 실행 버튼 비활성(Idempotency-Key와 별개 정책) | JobPanel.tsx |

## 알려진 제한·후속

- Viewer의 GT/예측 레이어 표시는 카메라 레이어 토글과 연동되지 않는다(Viewer 패널에서 조작). 0.38.1 JS API에 entity 표시 전환이 없어 blueprint 전송 방식은 후속 검토.
- 예측 박스는 track ID가 없어 프레임 간 같은 객체로 잇지 않는다. (리뉴얼 이후) 선택은 프레임 이동 시 유지되며 GT는 instanceToken으로 같은 객체를 잇고, 예측 선택은 다른 프레임에서 "이어지지 않음"으로 안내한다.
- 결과 전체를 한 번에 받는다(서버 pagination 없음). 큰 trainval scene은 측정 필요.
- Spring `RecordingWorker`가 Jackson 3 `asText()`(deprecated)를 사용한다. 동작 영향 없음.
- AI 스키마는 `scene_name`을 `scene-NNNN` 형식만 허용한다. 실제 nuScenes 이름은 해당되며, 다른 이름의 scene recording은 422로 FAILED가 된다.
- RUNNING 중 Spring 종료 시 recording 자동 복구 없음(job과 동일 제약).
- 성능 수치(프레임 전환 시간, 파일 크기, Viewer 메모리)는 실제 데이터로 측정하지 않았다.

## 다음 재개 지점·환경 제약

1. 실제 nuScenes mini 준비 후 `.env` 설정, `docker compose -f compose.yml -f compose.gpu.yml up --build -d`로 새 AI 이미지(rerun 0.38.1 assert 포함)·Spring(V5 migration)·volume 기동 확인.
2. 이미지 embedding 저장 후 `DS2L_API=http://127.0.0.1:8080 npx playwright test -c playwright.live.config.ts`로 live 검사, 이어서 화면에서 검색→씬→프레임 이동(첫 구현 묶음 완료 판정).
3. 화면에서 VESPA job 1회 실행(GPU, 장시간) 또는 기존 완료 job(`DS2L_LIVE_JOB_ID`)으로 결과 표시·예측 투영 확인.
4. 같은 scene의 GT·예측 투영을 nuScenes devkit `render_sample_data` 결과와 비교(M4 마지막 항목), recording 생성 후 실제 점군·GT·예측·시간/선택 확인(M5 마지막 항목).
5. reduced-motion·스크린리더·실기기 375 검수, 성능 측정 후 M6 마지막 두 항목 판정.

## 2026-11-09 업로드·편집·저장 추가

- [x] 라벨 JSON 업로드, 원본 보존, 버전 저장·재열기·다운로드 UI/API.
- [x] WORLD XY 박스 선택, 클래스·위치·크기·회전 수정, 추가·삭제.
- [x] 완료된 자동 라벨 결과를 별도 편집 문서로 복사. 예측 원본·GT 보존.
- [x] nuScenes ZIP 검증·원본 보관·catalog 등록·GPU 요청 데이터 경로 연결.
- [x] JPA 일반 repository 및 수정 이력, 동시 저장 충돌 처리.
- [x] 선택적 S3 원본 ZIP 저장 및 backend/AI cache 복원.
- [x] PostgreSQL 통합 테스트, frontend unit/build, 브라우저 fixture E2E, AI 업로드 계약 검사.
- [x] 실제 Spring + 임시 PostgreSQL에서 브라우저 업로드·버튼 수정·저장·새로고침·수정본 다운로드·원본 보존 검증.
- [ ] 실제 AWS S3/RDS/ECS 배포·GPU 메모리/추론 검증.
- [ ] 일반 이미지/영상 변환, 업로드 데이터 CLIP indexing 자동화, 업로드 데이터 Rerun.

사용법과 범위: [라벨 편집](label-editing.md), [AWS CI/CD](aws-ecs-cicd.md).

### 2026-11-11 리뉴얼·하이브리드 통합

- [x] `feature/frontend-renewal` b8376e4 통합, 기존 Flyway V7 보존·편집 V12 적용.
- [x] 업로드 전용 `/uploads`, 씬에서 라벨 생성·객체 편집·작업/편집 이력.
- [x] dataset+scene 범위 서버 작업 목록과 최신 완료 결과 복원. 선택한 scene-0103의 40개 키프레임만 실행하는 실제 인자 확인.
- [x] 업로드 데이터셋의 Rerun v3 생성·공개 Viewer 확인. 작업 #3의 라벨 985개를 재추론 없이 사용.
- [x] 실제 공개 업로드/씬 목록/객체/작업 화면 캡처를 README에 반영.
- [x] 관련 프론트 89개, 브라우저 29개, Spring 28개, AI 23개 검사 통과(세부 범위는 트러블슈팅).
- [ ] 운영 라벨을 직접 수정하는 전체 UI 저장 시나리오 재실행(격리 DB·브라우저 계약 검증과 구분).
- [ ] 편집 override를 RRD에 반영하는 재생성 정책, 원본 파일명·업로드 날짜 중심 정렬, 추론 단계 진행률.

### 배포 후 화면 파일 복구

2026-11-12 수동 실행 보완: 업로드 데이터셋의 현재 모델 임베딩이 모두 준비되기 전에는 버튼과 새 작업 API를 차단한다. 완료 후에도 사용자가 선택한 씬의 버튼을 눌러야 생성한다. 동일 요청의 Idempotency-Key 재전송은 보존하며 USER_CANCELLED는 화면에 중단됨, PENDING은 대기 중으로 구분한다. PostgreSQL 관련 23개, 프론트 단위 100개, 해당 브라우저 fixture 2개, 제품 빌드 통과. fixture 검증 때문에 운영 GPU 작업을 생성하지 않았다.

2026-11-12 추가 검증: 업로드 시도별 클라이언트 계측을 추가하고 프론트 100개·fixture 브라우저 흐름 4개 검사를 통과했다. Microsoft 비공개 터널을 거치는 Vercel production에서 사용자가 Cognito 로그인한 뒤 기존 10개 씬, 초기화 뒤 빈 목록을 확인했다. 새 대용량 업로드·씬 추론은 사용자가 직접 수행하며 그 결과는 별도 보고서에 기록한다. 현재 README에 초기화 화면과 운영/미구현 경계를 반영했다.

Spring 정적 리소스는 `Cache-Control: no-cache`로 재검증한다. 이미 열려 있던 페이지가 삭제된 이전 JS 청크를 요청하면 같은 URL에서 한 번 새로고침한다. 60초 동안 추가 자동 새로고침을 막고, 계속 실패하거나 저장소 사용이 차단된 브라우저에는 한국어 복구 버튼을 표시한다. 일반 애플리케이션 오류는 자동 새로고침하지 않는다. 브라우저 테스트는 청크 요청 1회 실패 후 복구와 지속 실패 시 무한 루프 방지를 확인한다. 수정 배포 전에 이미 오류가 난 이전 버전 탭은 사용자가 한 번 새로고침해야 새 복구 코드가 적용된다.

### 비교 작업 박스 겹쳐 보기 (2026-11-12, `feat/vespa-ver2-compare`)

같은 씬의 다른 완료 작업(예: VESPA ver2)을 기존 예측 위에 다른 색으로 겹쳐 본다. 옛 박스는 그대로 두고 비교 박스만 추가한다.

- [x] job status에 `modelVersion` 추가(Spring). 프론트는 접미사(`+ver2-rigid` 등)로 작업을 구분한다.
- [x] 패널별 `compareJobId`와 `cmp` 레이어, URL `cmp` 파라미터. 씬이 바뀌면 비교 선택을 지운다.
- [x] HUD `비교` 드롭다운(현재 결과를 제외한 완료 작업)과 보이기 토글. 비교 박스는 초록 `#19d67a` 점선, 태그 `ver2-rigid · 클래스`. 선택·편집·숨김 대상이 아니다.
- [x] 원본과 같은 비교 박스(같은 클래스, 위치·크기 5 cm, 방향 ~0.9° 이내)는 선만 그리고 태그를 생략한다. HUD에 작업 전체 `같음·달라짐·추가·없어짐` 요약(#26 대비 #35: 987·0·0·0, #23 P1/P2: 872·53·381·62).
- [x] 로컬 Colab shim의 `COLAB_RESULTS_DIR`를 `results`로 되돌림(`results-ver2-base`에는 scene-0061만 있어 다른 씬 라벨 생성이 실패). ai-server shim 이미지 재빌드 후 vespa/recording READY, scene-0061 라벨 생성 job 36 완료(1306개)와 recording 생성 확인.
- [x] 실제 데이터: dataset 1 / scene-0061 / job 26(원본 VESPA, 987) + job 35(ver2 rigid base, 987, trackId 포함). 1600×1000 Chromium 카메라 6대 화면에서 예측 19개와 비교 19개가 함께 그려지는 것을 확인했다. ver2 base는 원본과 바이트 단위로 같은 라벨이라 박스가 정확히 겹친다(차이는 refs 적용 2단계에서 생긴다).
- [x] ver2 2단계(refs `{T3: 18, T1: 0}`)를 저장된 base 라벨·track에 `rigid_tracklet.propagate`와 같은 식으로 적용(p_final `object_filtering: null`이라 1:1). 로컬 job 39: #26 대비 같음 946 · 달라짐 41. 달라진 비교 박스 태그는 겹치거나 30 m 밖이어도 표시.
- [x] 프론트 단위 108개, Spring 71개(Docker), 프론트 build 통과.
- [ ] 3D(Rerun recording)에 비교 박스 레이어 추가: recording `compare_job_id`, exporter `world/prediction_cmp`, 블루프린트 조합 16개.
- [ ] A/B 비교 화면 URL에 `cmpA/cmpB` 보존(현재는 패널 상태로만 유지).
