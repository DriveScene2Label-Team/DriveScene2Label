# 프론트 UI/UX 리뉴얼 (2026-11-05)

브랜치 `feature/frontend-renewal` (시작: `origin/main` `97818c9`). 기준 디자인은 [리뉴얼 목업](frontend-design/renewal-mockup.html)이다. 목업의 화면 구성·토큰·상호작용을 실제 Spring 데이터 위에 그대로 옮기고, 목업에만 있던 라벨 편집 기능은 백엔드 API까지 구현했다. 기존 계약([CLAUDE.md](../CLAUDE.md) "반드시 유지할 계약")은 바꾸지 않았다.

## 1. 범위

| 영역 | 내용 | 주요 파일 |
|---|---|---|
| 디자인 토큰·기본 스타일 | 목업 CSS를 그대로 이식(밝게/어둡게/시스템 테마, Apple×Toss 토큰, 시스템 글꼴). 실제 데이터 상태만 같은 토큰으로 보완. Tailwind는 theme/utilities만 쓰고 preflight는 제외(목업 base와 충돌) | `frontend/src/styles/index.css`, `index.html` |
| 라이브러리 | 히어로·검색창·예시 토큰·정렬·카드 그리드·비교할 씬 고르기(하단 실행 막대) | `pages/SceneSearchPage.tsx`, `features/scenes/SceneCard.tsx` |
| 작업 화면 | 툴바(뒤로·제목·보기 방식·링크 복사·인스펙터·더 보기), 어두운 센서 카드(HUD·카메라·3D·재생 막대), 흰 인스펙터 카드 | `pages/SceneWorkspacePage.tsx`, `features/workspace/*` |
| 카메라 | 3×2/2×3 자동 배치, 이름표·확대 버튼, GT 노랑 점선·예측 파랑 실선, 알약형 클래스 이름표, 선택 강조·나머지 흐리게, 박스 영역 클릭 | `features/cameras/*` |
| 분할 | 세로(3D 아래)/가로(3D 오른쪽) 배치, 카메라 6장이 빈틈없이 들어가는 자동 비율, 키보드 조절 | `features/layout/Split.tsx` |
| 재생 막대 | 이전/재생/다음, 예측이 있는 프레임(파랑)·선택한 GT가 나오는 프레임(노랑) 띠, 0.5–4× | `features/timeline/FrameTimeline.tsx` |
| 인스펙터 | 탭 객체/자동 라벨링/기록, 객체 편집기, 거르기·표, 작업 패널, 수정 기록 | `features/inspector/*` |
| 겹침 창 | 카메라 크게 보기, 삭제 확인(범위 선택), 단축키 | `features/workspace/Overlays.tsx` |
| 단축키 | Space, ←/→, G, P, H, Delete, ⌘/Ctrl+Z, Esc, \, ? | `features/workspace/hooks.ts` |
| 백엔드 | 라벨 편집 API + V7 migration + GT/결과 조회의 `labelOverride`/`deleted` + scene GT 조회 | `LabelEdit*`, `V7__label_edits.sql`, [README_API 8-1장](../README_API.md) |

## 2. 목업과 다르게 구현한 부분과 이유

| 목업 | 구현 | 이유 |
|---|---|---|
| 표시 막대(HUD)가 비교 화면 전체에 하나 | 같은 막대가 **작업 대상 패널**에 적용되고 왼쪽에 A/B 표를 붙임 | 레이어·선택은 패널별 독립이 계약. 같은 씬을 A/B로 열어도 독립 |
| 3D 합성 점군·시점 버튼(뒤에서/위에서)·축 범례 | Rerun Web Viewer(실제 recording). 시점 버튼·축 범례 없음 | 0.38.1 JS API로 카메라 시점을 바꿀 수 없고, WORLD 좌표 recording에 ego 축 범례는 틀린 정보 |
| 3D 패널 머리글 | 준비 전 상태 안내만. READY 뒤 어떤 recording인지(GT·센서 / 작업 #n 예측 포함)는 화면에 그리지 않고 스크린리더용 status로만 둔다 | Rerun 자체 패널·재생 컨트롤을 가리지 않기 위해 |
| 작업 기록 = 서버 목록(`listJobs`) | 이 브라우저의 실행 receipt 목록 | 서버에 scene별 job 목록 API가 없음(기존 receipt·서버 귀속 규칙 유지) |
| 실행 환경 "사용 가능 · 다시 확인" | 같음 + "실제 추론 성공을 보장하는 확인은 아니에요" 한 줄, 상태 조회 실패/만료 안내 | I1/I2 준비 상태 계약(이전 READY 미사용) 유지 |
| 데이터셋 1개 고정, 위치·날씨 메타 | 서버 데이터셋 목록, 카드 메타는 프레임 수·설명의 밤/비 키워드만 | Scene DTO에 location 없음. 날씨는 DB의 is_night/is_rain과 같은 키워드 규칙 |
| 데이터 출처 표시 없음 | 라이브러리 eyebrow·작업 툴바에 출처 배지(nuScenes/합성/미확인) | I1/I2 요구(합성 데이터를 실제 검증으로 오인 방지) |
| GT 라벨 = 합성 클래스 | 원본 category의 8class 비교 분류, 미매핑은 category 그대로, 원본 category는 "좌표와 ID"에 표시 | 원본 category 보존·임의 vehicle 변환 금지 |
| 같은 씬 비교 불가(선택 비활성) | 라이브러리 고르기는 두 씬, 패널 선택에서는 같은 씬도 허용 | 같은 씬 A/B 독립 계약 |
| 예측 박스 미보유 시 목록 문구 | 예측 0개 프레임은 일반 빈 상태, 결과 조회 오류는 별도 경고 | 빈 결과와 오류 구분 |
| 목업 확인용 메뉴(느린 로딩 등) | 제거 | 제품 화면에서 시안용 기능 제거 |

선택은 이제 프레임이 바뀌어도 유지된다(GT는 instanceToken으로 같은 객체를 잇고, 예측은 track ID가 없어 이어지지 않음을 편집기가 안내). 숨긴 객체·레이어·선택은 패널별 상태이며 서버로 보내지 않는다.

## 3. 라벨 편집 설계 요약

- 원본(`gt_annotation`, category, `predicted_annotation`)은 바꾸지 않고 `label_override`에 현재 상태, `label_edit(_target)`에 이력과 대상별 이전 상태를 저장한다.
- GT의 원래 클래스는 VESPA 8class 비교 분류(서버 `LabelClasses`, 프론트 `lib/classes.ts`가 같은 표). 이름 변경 후보는 8class + vehicle.
- GT는 "모든 프레임에 적용"(INSTANCE)이 기본이다. 삭제도 확인 창에서 모든 프레임/지금 프레임을 고른다. 예측은 박스 단위.
- 되돌리기는 최신 편집부터(같은 박스의 나중 편집이 있으면 409). 기록 탭·토스트·⌘/Ctrl+Z가 같은 API를 쓴다.
- 편집 후에는 영향받는 조회만 무효화한다(GT annotations·scene instances 또는 해당 job results, 기록). 결과 재조회는 새 VESPA 작업을 만들지 않는다.
- Rerun recording은 원본 박스를 기록한다(편집 미반영). 인스펙터 기록 탭 안내 문구에 표시했다.

## 3-1. 3D 이름표 정리와 표시 토글 연동 (export `ds2l-rrd-v3`, 2026-11-05)

Rerun 3D에서 모든 GT·예측 박스에 이름이 붙어 확대해도 읽기 어려웠다. 이름표는 끄지 않고 exporter에서 정리한다([Rerun recording 계약](rerun-recording.md)의 `world/labels`).

- GT·예측 `Boxes3D`는 `show_labels=False`(이름은 데이터로 남아 선택·hover에 표시).
- 이름표 전용 `world/labels`(`Points3D`): ego 기준 30 m 안만, 같은 클래스 GT·예측이 1.5 m 안이면 하나(흰색), 같은 클래스가 4 m 안이면 `pedestrian ×3`, 무리 윗면 0.6 m 위. GT는 8class 비교 분류(미매핑은 category 그대로). Viewer 엔티티 목록에서 이 레이어만 끌 수 있다.
- 이름표 레이어는 출처별 `world/labels/gt|pred|both`로 나눈다(v3).
- GT / 예측 / 클래스 이름 토글이 3D에도 적용된다: 토글 조합별 blueprint 8개(`scripts/generate_rerun_blueprints.py` → `frontend/public/rerun-blueprints`)를 뷰어에 보내고, 적용 직후 recording·타임라인·프레임·일시정지를 복원한다. **0.38.1 제약으로 토글할 때 3D 카메라가 기본 시점으로 돌아간다.**
- export 버전을 v3로 올려 기존 recording은 재사용하지 않는다(씬마다 새로 만들어야 반영). 응답 entities·선택 매핑은 그대로.
- 함께 고친 기존 버그: 개발 모드(StrictMode)에서 `bindQueryClient`가 버려진 QueryClient에 묶여, job/recording 생성 뒤 목록 재조회가 일어나지 않았다(“3D recording 만들기” 후 화면 그대로). 커밋 후 effect에서 묶도록 변경. production 빌드(e2e)에서는 드러나지 않았다.

## 4. 검증 기록

| ID | 범위 | 명령 | 결과 | 미검증·제약 |
|---|---|---|---|---|
| R-01 | 프론트 정적 검사·빌드 | `npm run typecheck`, `npm run build` | 통과 | — |
| R-02 | 프론트 단위(Vitest) | `npm test` | 6 files / 70 tests 통과(신규 `lib/renewal.test.ts`: override 변환·삭제 제외·instance 색인·객체 키·배치/자동 비율·조사) | jsdom |
| R-03 | 프론트 UI 흐름(Playwright, route fixture, Chromium/WebKit headless) | `npm run test:e2e` | 84 통과, 3 skip(Rerun 파일 필요). 신규 `renewal.spec.ts` 9개: GT 모든 프레임 이름 변경·토스트 되돌리기, 삭제 범위·기록 최신순 되돌리기, ⌘Z·예측 이름 변경, 편집 API 없는 서버, H/G/?·모두 보이기, 테마 유지, 3D 배치 전환, 비교할 씬 고르기·비교 닫기, 작업 화면 비교 모드 | fixture는 실제 DTO 형식이지만 실제 서버 아님. 6개 프로젝트 병렬 실행이 느린 환경에서 assertion timeout을 10초로 상향 |
| R-04 | Rerun Viewer 0.38.1 | `DS2L_RRD=<합성 .rrd> npx playwright test --project=desktop-1440 tests/e2e/viewer.spec.ts` (`ai-server/tests/recording_fixtures.py`로 생성) | 3 통과: 타임라인 동기화, 분할 resize, Viewer 선택 → 인스펙터 객체(객체 키 변환), 다운로드 실패 재열기 | 합성 점군, SwiftShader |
| R-05 | Spring(PostgreSQL 컨테이너) | `bash scripts/docker-test.sh` | 40 tests 통과(신규 LabelEditTests 8: instance 이름 변경·원본 불변, 원래 클래스로 되돌림·검증 오류, 미매핑 category, 프레임/모든 프레임 삭제·scene GT, 예측 편집·결과 필터·기록 범위, 미완료 job 거부, 최신순 되돌리기·충돌, 삭제 되돌리기) | fake AI |
| R-06 | 목업 대조 | 같은 크기(1440×900, 1024, 768, 375)로 목업과 앱(route fixture) 화면 캡처 비교: 라이브러리·검색·작업 화면·선택·작업 탭·카메라·비교·삭제 확인·크게 보기·토스트·어두운 테마 | 배치·간격·색·글자 크기 일치. 차이는 2장 표의 의도된 항목과 fixture 이미지 | 실제 JPG·실제 GT 밀도로는 미확인 |
| R-07 | 형식 | `git diff --check` | 통과 | — |
| R-08 | 3D 이름표(exporter) | `ai-server/.venv-recording`: `pytest tests/test_recording.py` (`PYTHONPATH=…/rerun_sdk`) | 11 통과·1 skip(torch 필요). 실제 .rrd read-back: 박스 `show_labels=False`, `world/labels` 이름표(GT·예측 쌍 합침), 빈 sample·lidar 없는 sample은 빈 batch. 정리 규칙 단위 테스트 2개 | 전체 AI pytest(`.venv-recording-full`)의 `test_vespa_ssh.py` 6개 실패는 변경 전 코드에서도 같은 실패(이번 변경과 무관) |
| R-09 | Spring | `bash scripts/docker-test.sh` | 40 통과(export 버전 v2 반영) | — |
| R-10 | 로컬 실제 스택 | 합성 nuScenes 형식 데이터(씬 2·sample 24·GT 142, SYNTHETIC) + Spring jar·pgvector 컨테이너 + recording 전용 AI 하네스(CLIP 실패 주입, 제품 AI 컨테이너 아님) + `npm run dev` | 브라우저에서 GT 이름 변경·되돌리기·기록(실제 PostgreSQL), 3D recording 생성 → READY 자동 열림(StrictMode 수정 후), 이름표가 박스 위 별도 레이어로 표시 | 실제 nuScenes·실제 예측 밀도에서의 이름표 겹침은 미확인 |
| R-11 | Rerun Viewer(v2 .rrd, 이후 v3로 재확인) + 전체 e2e(desktop) | `DS2L_RRD=<v2 .rrd> npx playwright test --project=desktop-1440` | 65 통과(Viewer 3 포함: 박스 선택 → 인스펙터 매핑 유지) | 합성 recording |
| R-12 | 표시 토글 → 3D | v3 .rrd로 `DS2L_RRD=… npm run test:e2e`(viewer: GT·클래스 이름 토글 시 blueprint 전송, 프레임 동기 유지) + 로컬 실제 스택 브라우저 확인 | e2e 84 통과·3 viewer 통과. 실제 스택: GT 끔 → GT 박스·이름표 숨김, 클래스 이름 끔 → 이름표만 숨김, 토글 뒤 앱 프레임 4→5와 3D 시간 3→4 일치 | 토글 시 3D 카메라 초기화(0.38.1 제약). 실제 nuScenes·실제 예측 미확인 |

**실제 연동은 하지 않았다.** 실제 nuScenes mini, 실제 Spring 서버에서의 라벨 편집 API(브라우저→Spring→PostgreSQL), 실제 CLIP 검색, 실제 VESPA job, 실제 GPU 브라우저 성능은 이 환경(로컬 JDK·데이터·GPU 없음)에서 확인하지 못했다.

## 5. 남은 항목

1. 실제 Spring + mini 데이터로 라벨 편집 흐름(이름 변경·삭제·되돌리기·기록)과 V7 migration 적용을 live로 확인(`playwright.live.config.ts`에 편집 시나리오 추가 필요).
2. 실제 JPG에서 박스 이름표 밀도·겹침 회피 확인(목업 규칙: 선택 없음일 때 30m 이내만 표시).
3. Rerun recording에 편집 반영 여부 결정(현재 원본 기록). 반영하려면 exporter 입력에 override를 넣고 recording 재생성 정책이 필요.
4. 서버 job 목록 API가 생기면 작업 기록을 서버 목록으로 교체.
5. 사용하지 않게 된 의존성(`@radix-ui/react-slot`, `class-variance-authority`) 정리 여부.
