# DriveScene2Label 프론트엔드 개발 기획서

> 2026-10-05 후속 기준: [실제 데이터·연동 개선 기획서](frontend-integration-plan.md)와 [개선 체크리스트](frontend-integration-checklist.md)를 함께 따른다. 이 문서의 제품·화면·디자인 요구는 유지하며, 개선 범위의 환경·준비 상태·오류·비동기 처리·실제 성공 판정은 후속 기획서가 보완한다. 기존 v1.2 구현 기록을 실제 데이터 연동 완료로 취급하지 않는다.

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.2 · 구현 반영(2026-10-04) |
| 작성일 | 2026-10-04 |
| 대상 | 프론트 개발자, 백엔드·AI 담당자, 시안 제작자, 검토자 |
| 기준 소스 | 저장소 main `88847a9` |
| API 기준 | [README_API.md](../README_API.md) |
| 기준 시안 | 2026-10-04 작업 폴더 수정본. [HTML](frontend-design/index.html), [Claude 핸드오프](frontend-design/claude-handoff.md), [인수 결정](frontend-design/README.md) |
| 검토 범위 | HTML·핸드오프 소스 비교, JS 문법 검사, 색상 대비 계산. 브라우저 시각·동작 검수는 구현 단계에서 수행 |
| 사용 시점 | 프론트 및 필요한 백엔드·AI 보완 작업 착수 기준 |
| 구현 추적 | [단계별 체크리스트](frontend-implementation-checklist.md), [Claude Code 시작 프롬프트](claude-code-frontend-prompt.md), [저장소 지침](../CLAUDE.md) |

이 문서는 기존 Spring·CLIP 검색·VESPA·nuScenes 센서 데이터 위에 프론트를 연결하는 개발 기준이다. 수정 시안의 디자인과 화면 구조를 참고하되, 실제 기능·상태·데이터 계약은 이 문서와 현재 백엔드 코드를 따른다. ‘추가 계약’으로 표시한 API는 구현 제안이며 현재 제공되는 기능이 아니다.

### 이번 개발의 결정

| 항목 | 기준 |
|---|---|
| 제품 형태 | 데스크톱 우선의 주행 장면 탐색·자동 라벨 검토 도구 |
| 화면 | 씬 탐색, 씬 작업대, 두 씬 비교. 작업 실행·상태는 작업대의 우측 패널에 통합 |
| 디자인 | 수정 HTML의 다크 테마, 파랑 행동 색, 노랑 GT 점선, 민트 예측 실선 |
| 데이터 | 실제 Spring `/api/*`와 실제 nuScenes JPG·LiDAR·GT·VESPA 결과 |
| 비교 | 서로 다른 씬과 동일 씬의 서로 다른 프레임 모두 지원 |
| 3D | Rerun Web Viewer. recording 생성·제공도 이번 범위에 포함 |
| GT | 현재 박스 geometry 사용, category 필드와 classMode mapping 보완도 이번 범위에 포함 |
| 확장 | 평가·학습·수동 편집·취소·팀 전체 작업 이력은 후속 |

### 기술 스택

| 역할 | 기술 | 적용 기준 |
|---|---|---|
| 앱 | React + TypeScript + Vite | `frontend/`에서 별도 빌드 |
| 라우팅 | React Router | 공유 가능한 씬·비교 URL |
| 서버 상태 | TanStack Query | 실제 API 조회, 캐시, polling, 재시도 |
| 화면 상태 | Zustand | 패널별 프레임·재생·레이어·객체·배치 |
| UI | Tailwind CSS + shadcn/ui | 기준 시안의 토큰과 스타일을 적용 |
| 3D | Rerun Web Viewer | Python SDK·웹 Viewer 0.38.1로 고정(기술 검증 결과, 9장) |
| API 타입 | 수동 DTO + mapper, 이후 Spring OpenAPI 생성 타입 | mock 형식을 서버 계약으로 사용하지 않음 |
| 검증 | Vitest + Playwright | 기하·상태 경계와 실제 사용자 흐름 |
| 후속 차트 | Apache ECharts | 평가 API 구현 시 도입 |

패키지 버전은 설치 단계에서 호환성을 확인하고 lockfile로 고정한다. 이 기획서 작성 과정에서는 의존성을 설치하거나 기존 백엔드를 변경하지 않는다.

## 1. 제품 목적과 성공 기준

DriveScene2Label은 nuScenes 주행 장면을 검색하고, 카메라·LiDAR 데이터를 탐색하며, VESPA가 생성한 3D 라벨을 정답 GT와 비교하는 작업 도구다.

프론트의 첫 목표는 다음 흐름을 실제 데이터로 완성하는 것이다.

```text
데이터셋 선택 → 자연어 검색 또는 씬 목록 → 씬 작업대
 → 6개 카메라와 프레임 탐색 → VESPA 실행 → 완료 결과 확인
 → 이미지 위 라벨 및 LiDAR 3D 비교 → 다른 씬과 나란히 확인
```

핵심 발표·사용 경험은 다음 세 가지다.

1. 한 씬의 6개 카메라를 동시에 보며 프레임을 이동한다.
2. 주행 이미지를 재생할 때 해당 프레임의 객체 라벨이 함께 바뀐다.
3. 카메라와 LiDAR를 분할하거나 두 씬을 나란히 열어 결과를 비교한다.

‘이미지 위 라벨’은 WORLD 좌표의 3D 박스를 카메라에 투영한 표시다. ‘재생’은 JPG 키프레임 시퀀스 재생이다. 실시간 영상 입력이나 라벨 편집을 의미하지 않는다.

### 완료 판정

- 사용자가 검색부터 예측 결과 비교까지 설명 없이 이어갈 수 있다.
- 선택한 씬·프레임·작업이 화면과 URL에서 일관되게 유지된다.
- 다른 프레임 또는 다른 씬의 이미지와 박스가 섞여 표시되지 않는다.
- 실제 데이터와 예시 데이터, 미지원 기능을 구분할 수 있다.
- GT와 예측의 시각적 비교가 가능하되, 자동 매칭·정량 평가 결과를 임의로 만들지 않는다.

## 2. 범위와 우선순위

| 구분 | 기능 | 완료 범위 |
|---|---|---|
| 필수·기존 API 기반 | 데이터셋·씬 탐색, 자연어 검색 | 실제 Spring 연결 |
| 필수·기존 API 기반 | 6개 카메라, 확대, 프레임 이동·재생 | 실제 JPG 파일 표시 |
| 필수·프론트 구현 | 패널 분할·크기 조절, 씬별 새 탭, 두 씬 비교 | 독립 상태와 선택적 상대 시간 동기화 |
| 필수·기존 API 기반 | VESPA 실행, 상태 조회, 결과 확인 | 씬 단위 생성과 polling |
| 필수·프론트 구현 | 이미지 위 예측/GT 박스 | 실제 캘리브레이션·pose를 이용한 투영 |
| 필수·추가 계약 필요 | GT 클래스명·클래스 기준 비교 | annotation 클래스 보완 및 mapping 합의 |
| 필수·추가 계약 필요 | Rerun LiDAR·3D 박스 | recording 생성·제공·시간/객체 연결 검증 |
| 필수·프론트 구현 | 알려진 jobId 복원·결과 다시 조회 | URL·생성 receipt 기반. 네트워크 실패와 작업 실패 구분 |
| 후속 | 팀 전체 작업 이력·취소·서버 worker 자동 복구 | 서버 기능 마련 후 |
| 후속 | 박스 직접 편집·저장·내보내기 | 별도 API와 상호작용 설계 후 |
| 후속 | 평가·학습·실험 관리 | 평가 API 마련 후 ECharts 활용 |

카메라·검색·작업 조회를 먼저 완료할 수 있다. Rerun 연결이 남아 있으면 ‘카메라 MVP 완료’로 구분하고, 필수 3D 요구까지 모두 완료한 것으로 표기하지 않는다.

## 3. HTML 시안에서 실제 앱으로 넘어가는 절차

HTML은 시각·상호작용 참고 자료다. 실제 앱에서는 데이터와 상태를 React 구조로 다시 구성한다.

### 시안 인수 자료

- 선택한 `index.html`, 필요한 assets, 화면 캡처와 뷰포트 크기.
- 검토한 시안 버전 또는 파일 해시와 선택한 디자인 방향.
- 색상·서체·간격·반경·아이콘·레이어 스타일 토큰.
- 세 가지 보기 모드, 검색 화면, 확대 모달, 객체 패널의 동작.
- 로딩·빈 결과·카메라 누락·작업 실패 상태.
- 예시 데이터·하드코딩 값·실제 연동이 필요한 영역 목록.
- 사용한 이미지·폰트·아이콘의 출처와 교체 위치.

### 인수 체크

| 확인 항목 | 처리 |
|---|---|
| 기존 필수 기능이 누락됨 | React 이식 전 시안 또는 설계에 반영 |
| 지원하지 않는 confidence/진행률/편집 버튼이 있음 | 현재 계약에 맞춰 표시·동작 수정 |
| 모바일·작은 화면에서 주요 동작이 잘림 | 반응형 규칙 확정 |
| 카메라 방향·씬·프레임 관계가 불명확함 | 기능 명세 우선 적용 |
| 그림은 있으나 버튼이 동작하지 않음 | 동작 설계를 별도로 기록 |
| 시안과 실제 센서 이미지 비율이 다름 | 실제 데이터 비율과 overlay 좌표 검증 |

기준 시안 원본과 결정 이유는 `docs/frontend-design/`에 보관한다. 핸드오프는 Claude의 참고 자료이며 실제 API 계약 문서가 아니다. 실제 구현은 `frontend/`에서 진행한다. 이후 변경은 기능 요구·데이터 제약·사용성 문제와 연결해 변경 기록을 남긴다.

### 인수한 시안에서 그대로 유지할 부분과 교체할 부분

| 영역 | 적용 |
|---|---|
| 다크 색상, 카드, 버튼, 상태 배지, 해요체 | 디자인 기준으로 사용. 버튼 대비와 작업 공간은 구현 검수에서 조정 |
| 검색→작업대, 6카메라, 카메라+LiDAR, A/B 비교, 확대 | 제품 화면 구조로 사용 |
| `store.views[scene]`, 동일 씬 A/B 금지 | 패널별 Zustand 상태로 교체 |
| `MockBackend`, 합성 카메라·점군, 시간 기반 job | 실제 API와 센서 데이터로 교체 |
| `DemoProjection`, 고정 500ms 재생, 프레임 인덱스 비율 동기화 | 실제 좌표 변환·timestamp 기반 재생/동기화로 교체 |
| 요청 body, SDK/API 설명, 시안 상태 메뉴 | 일반 제품 화면에서 제거하고 필요 시 개발 진단 메뉴로 이동 |

시안의 `camlidar/cams` 해시 경로는 최종 앱의 `split/six` 경로로 변환한다. 합성 생성 코드와 단일 파일의 DOM 조작 코드를 React 제품 코드로 복사하지 않는다.

## 4. 화면과 라우팅

| 화면 | 제안 URL | 주요 책임 |
|---|---|---|
| 씬 탐색 | `/scenes?dataset=1&q=...` | 데이터셋·목록·검색·비교 씬 선택 |
| 씬 작업대 | `/scenes/7?dataset=1&sample=TOKEN&job=12&view=split` | 현재 씬의 센서·프레임·라벨·작업 |
| 두 씬 비교 | `/compare?datasetA=1&sceneA=7&datasetB=1&sceneB=12` | A/B별 작업대와 독립 타임라인 |

작업대 `view`는 `six`, `split`을 사용한다. 두 씬 비교는 별도 route를 사용하되 보기 모드 버튼으로 이동할 수 있게 한다. 비교 화면은 필요 시 `sampleA/B`, `jobA/B`, `sync=relative`를 추가한다. 기본은 독립 탐색이다.

숫자 ID는 API 식별자, token은 원본 식별자다. URL의 숫자·token을 서로 대체하지 않는다. 유효한 `sample`이 없으면 해당 씬의 첫 프레임으로 이동하고, 유효하지 않은 `job`은 오류 안내 후 연결을 해제한다.

현재 `GET /api/scenes/{id}` 단건 API는 없다. 작업대의 씬 이름·token·프레임 수는 `dataset`의 씬 목록에서 sceneId로 찾는다. 공유 링크에 dataset을 포함하고, 빠진 경우 데이터셋 선택을 통해 복구한다. 배열 인덱스나 DB ID 1을 기본값으로 고정하지 않는다.

새 탭은 현재 씬의 실제 앱 URL로 연다. 배포 서버는 BrowserRouter 하위 경로 요청에 앱의 `index.html`을 반환하도록 구성한다.

## 5. 화면별 기능 명세

### 5.1 씬 탐색

| ID | 요구 | 동작·완료 기준 |
|---|---|---|
| FR-01 | 데이터셋 선택 | API의 실제 dataset 목록 사용. 변경 시 이전 선택 씬·검색 결과를 새 dataset과 섞지 않음 |
| FR-02 | 전체 씬 목록 | 이름·설명·프레임 수 표시. 전체 목록 API에는 thumbnail·작업 상태가 없음을 고려 |
| FR-03 | 자연어 검색 | 제출 시 요청. 기본 k=10, TOP_K_AVERAGE, imageTopK=3, keyframesOnly=true |
| FR-04 | 결과 카드 | 검색 응답의 대표 이미지·이름·설명·유사도 표시. score를 정확도 %로 바꾸지 않음 |
| FR-05 | 씬 이동 | sceneId/datasetId를 URL에 넣고 대표 sampleToken이 있으면 해당 프레임 선택 |
| FR-06 | 비교 씬 선택 | A/B 2개 선택 후 비교 화면. 서로 다른 dataset도 각 문맥을 보존 |

전체 씬 카드의 이미지가 필요하면 화면에 보이는 카드에 한해 `/scenes/{id}/samples?limit=1&offset=0` → `/samples/{sampleId}`의 카메라 contentUrl을 사용한다. 조회 전에는 이미지 영역의 로딩 상태를 표시한다. 검색 대표 이미지와 일반 목록 첫 프레임 이미지는 구분한다.

검색의 `scenes:[]`는 오류가 아닌 정상 빈 결과다. 임베딩이 없어서 결과가 비어도 프론트만으로 원인을 확정하지 않는다. dataset embedding 개수를 확인하는 운영 자료가 마련되면 준비 상태를 별도로 안내한다. 임베딩 대량 생성은 사용자의 검색 동작마다 자동 실행하지 않는다.

한국어 입력은 허용하지만 현재 CLIP의 한국어 품질 검증은 되어 있지 않다. 예시 검색어는 영문을 제공한다. 검색 조건으로 제공되지 않는 날씨·시간·장소 필터를 실제 필터처럼 노출하지 않는다.

### 5.2 씬 작업대와 6개 카메라

데스크톱 기본 구성은 다음이다. 처음 진입하면 카메라+LiDAR 모드이며, 데이터가 없거나 recording이 준비되지 않았으면 해당 영역에 준비 상태를 표시한다.

```text
상단: 씬 목록으로 / 씬 이름 / 보기 모드 / 새 탭·링크
┌──────────────────────────────────────┬───────────────────┐
│ 6개 카메라      ↔      LiDAR / 3D     │ 씬 전체 라벨 생성 │
│ 채널별 이미지 위 GT·예측 박스         │ 작업 상태·결과    │
│ 카메라 확대 / GT·예측 토글            │ 객체 목록·상세    │
├──────────────────────────────────────┴───────────────────┤
│ 이전·재생·다음 / 프레임 / 타임라인 / 속도                 │
└──────────────────────────────────────────────────────────┘
```

6카메라 모드는 LiDAR 영역을 닫아 카메라에 더 넓은 공간을 준다. 우측 패널은 접을 수 있고, 확대는 별도 모달에서 수행한다. 단위·좌표 정보는 객체 상세에, 주된 버튼과 작업 상태는 우측 위쪽에 배치한다.

| ID | 요구 | 동작·완료 기준 |
|---|---|---|
| FR-07 | 센서 그리드 | keyframe camera를 channel 이름으로 배치. API 배열 순서에 의존하지 않음 |
| FR-08 | 보기 모드 | 6카메라 중심 또는 카메라+LiDAR. 전환해도 프레임·job·객체 선택 보존 |
| FR-09 | 확대 | 현재 카메라·이미지·overlay 확대. Esc·닫기·포커스 복귀 지원 |
| FR-10 | 분할 | 패널 경계 드래그, 최소 폭, 키보드 조절, 기본 배치 복원 |
| FR-11 | 프레임 탐색 | 이전·다음·슬라이더·재생·일시정지·속도 선택. 끝에서 정지 |
| FR-12 | 레이어 | GT/예측 표시 토글. 점선/실선과 텍스트로도 소스 구분 |
| FR-13 | 객체 정보 | 박스 또는 목록 선택 시 소스·클래스·위치·W/L/H·회전 표시 |

카메라 기본 배치는 다음이다.

```text
CAM_FRONT_LEFT | CAM_FRONT | CAM_FRONT_RIGHT
CAM_BACK_LEFT  | CAM_BACK  | CAM_BACK_RIGHT
```

큰 화면의 6카메라 모드는 3열×2행, 분할 모드의 좁은 카메라 패널은 2열×3행을 허용한다. 채널 이름과 방향은 항상 표시한다. 처음부터 프레임 목록과 파일을 모두 다운로드하지 않는다.

GT 클래스가 없으면 ‘GT · 클래스 정보 없음’으로 표시하고 위치·크기 비교는 허용한다. 이름을 예측 박스에서 복사하지 않는다. 예측과 GT의 일대일 객체 대응·tracking을 추정하지 않는다. 프레임 변경 시 선택 객체는 해제하고, 같은 박스 ID를 다음 프레임의 동일 객체로 간주하지 않는다.

카메라 파일 누락, 파일 다운로드 오류, calibration/pose 누락은 구분한다. 이미지는 있지만 calibration이 없으면 이미지는 표시하되 해당 채널의 overlay가 준비되지 않았음을 안내한다.

### 5.3 두 씬 비교

| ID | 요구 | 동작·완료 기준 |
|---|---|---|
| FR-14 | 독립 문맥 | A/B별 dataset·scene·sample·job·객체·레이어 상태 관리 |
| FR-15 | 독립 시간 | A 이동 시 B 프레임 유지. 같은 씬을 양쪽에 열어도 상태 분리 |
| FR-16 | 상대 시간 동기화 | 옵션 활성화 시 재생 범위의 상대 위치로 B를 이동. 동일 촬영 시각을 의미하지 않음 |
| FR-17 | 실행 대상 | 현재 활성 패널 A/B를 분명히 표시하고 해당 씬에만 생성 요청 |
| FR-18 | 별도 탭 | A/B 씬을 각각 공유 가능한 작업대 URL로 열기 |

상대 시간 매핑은 sample timestamp를 사용한다.

```text
progress = (tA - startA) / (endA - startA)
targetB = startB + progress × (endB - startB)
```

B에서는 targetB에 가장 가까운 sample을 선택한다. 단일 프레임 또는 시간 범위 0인 씬은 예외 처리한다. frame index 비율은 시안 예시에만 허용하고 실제 데이터는 시간을 기준으로 한다.

동기화가 꺼져 있을 때 다른 패널의 씬은 같은 타임라인을 강제로 따르지 않는다. 실제 AI가 한 번에 여러 씬을 처리할 수 있다는 UI를 만들지 않는다. MVP 비교 화면은 양쪽 6카메라와 독립 타임라인을 필수로 제공한다. LiDAR 비교는 활성 패널 한 곳에 단일 Rerun 뷰어를 연결하는 구성을 시작 기준으로 삼고, 두 Rerun 인스턴스 동시 표시는 후속 성능 검증 후 확대한다.

A/B를 누르면 우측 작업·객체 패널도 해당 패널을 따른다. 같은 씬을 A/B에 열어도 조회 캐시는 공유하되 프레임과 선택은 독립이다. 같은 씬에 진행 중인 작업이 있으면 어느 패널에서도 그 작업을 확인할 수 있도록 생성 receipt를 공유하고, 새로운 사용자 실행과 네트워크 재시도를 구분한다.

### 5.4 VESPA 작업

| ID | 요구 | 동작·완료 기준 |
|---|---|---|
| FR-19 | 생성 | datasetId/sceneToken/classMode를 보내고 202의 jobId 보관 |
| FR-20 | 중복 방지 | 요청 중 버튼 비활성. 요청 의도가 같으면 Idempotency-Key 유지 |
| FR-21 | 상태 조회 | 2~5초 polling. COMPLETED/FAILED에서 중단 |
| FR-22 | 결과 표시 | COMPLETED 이후 results 조회. datasetId+sampleToken으로 현재 프레임에 연결 |
| FR-23 | 실패·재실행 | FAILED 이유 표시. 사용자 새 실행은 새 key로 새 job 생성 |
| FR-24 | 복원 | URL과 로컬 receipt의 jobId로 다시 조회. 저장된 상태 문자열을 서버 사실로 사용하지 않음 |

classMode는 1/3/8이다. 1종은 vehicle, 3종은 vehicle/pedestrian/bicycle, 8종은 car/truck/bus/trailer/construction_vehicle/pedestrian/motorcycle/bicycle에 barrier/traffic_cone을 더한 10개다(VESPA patch 0001, 2026-11-04). GT 비교 분류는 VESPA `assets/class_mapping/{1,3,8}class.yaml`(commit acb2b6e + patch)의 `mapping_nuscenes`를 그대로 따른다. upstream 기준으로 3종에서 motorcycle은 bicycle, 1종에서는 pedestrian도 vehicle이며, 8종에서는 barrier·trafficcone이 같은 이름으로 비교되고, 1/3종의 barrier·trafficcone과 emergency 등은 비교 분류가 없다(`frontend/src/lib/classes.ts`).

상태의 표시 문구는 다음으로 통일한다.

| 상태 | 문구·동작 |
|---|---|
| 프론트에서 생성 전 | 실행 전. 서버 status enum으로 추가하지 않음 |
| PENDING | 대기 중 |
| RUNNING | 라벨 생성 중 · 시작 시각/경과 시간 표시 |
| COMPLETED | 생성 완료 · 결과 로딩/표시 |
| FAILED | 생성 실패 · 이유와 다시 실행 |
| 상태 요청 실패 | 연결을 확인할 수 없음 · 마지막 확인 시각 및 다시 조회 |

일시적인 GET 실패를 job FAILED로 바꾸지 않는다. POST 응답이 유실된 경우 같은 요청·같은 key로 재요청한다. status의 장시간 RUNNING을 프론트에서 임의 FAILED로 변경하거나 새 실행을 자동 생성하지 않는다.

결과 `boxes:[]` 또는 현재 sample의 박스가 없는 것은 정상적인 ‘검출 박스 없음’이다. 결과 준비 전, 프레임에 박스 없음, 실패를 서로 다른 화면 상태로 관리한다. 생성 실패 시 이미 선택한 과거 완료 job의 결과는 유지하고 어떤 job을 보고 있는지 명시한다.

`COMPLETED` 뒤 results GET이 실패하면 ‘결과 다시 불러오기’로 해당 조회만 재시도한다. 결과를 읽는 데 실패했다는 이유로 새 VESPA job을 만들지 않는다. 경과 시간은 서버 `completedAt`에서 멈추며, job의 sceneToken/classMode는 현재 status에 없으므로 receipt로 연결한다.

## 6. 데이터·상태 설계

### 상태 책임

| 위치 | 저장 내용 | 규칙 |
|---|---|---|
| TanStack Query | dataset, scene 목록, samples, sample detail, GT, calibration, pose, job status/results | 서버의 원본 상태. 조회 키에 식별자·조건 포함 |
| Zustand | pane별 프레임·선택 카메라·객체·레이어·재생·배치 | 서버 응답 배열을 다시 복사해 저장하지 않음 |
| URL | dataset/scene/sample/job/view 및 비교 문맥 | 공유·새로고침 복원용 |
| localStorage | 배치 설정, 사용자 표시 선호, 생성 요청 receipt | 큰 이미지·점군·results 전체 저장 금지 |
| 컴포넌트 내부 | 모달 열림, hover, 드래그 중 임시 크기 | 공유가 필요 없는 단기 상태 |

URL을 먼저 읽고 식별자를 검증한 뒤 사용자 표시 선호를 적용한다. 저장 구조에 버전을 두고 잘못된 데이터는 기본값으로 복구한다. 재생 중 매 프레임마다 브라우저 history를 쌓지 않는다. 슬라이더 탐색 중 URL 갱신은 제한하고 정지·탐색 완료 시 replace한다.

패널 키는 `paneId + datasetId + sceneId`로 구분한다. 같은 씬을 A/B에 열면 서버 query cache는 공유할 수 있지만 UI 상태는 별개다.

### 대표 query key 제안

```ts
['datasets']
['scenes', datasetId]
['sceneSamples', sceneId, { limit, offset }]
['sampleDetail', sampleId, { keyframesOnly: true }]
['annotations', sampleId]
['calibration', sensorFileId]
['pose', sensorFileId]
['sceneSearch', { datasetId, q, k, aggregation, imageTopK, keyframesOnly }]
['jobStatus', jobId]
['jobResults', jobId]
```

원본 센서·calibration은 변경이 드문 데이터로 캐시하고, job 상태는 별도 짧은 조회 주기를 둔다. 쿼리 함수가 지원하는 취소 신호를 사용해 오래된 응답을 배제한다. 파일 다운로드·이미지 decode 실패는 query JSON 오류와 별도 처리한다.

### 프론트 표시 모델 제안

```ts
type PaneId = 'single' | 'A' | 'B';
type BoxSource = 'GT' | 'VESPA';

interface BoxView {
  key: string; // source + dataset + sample + annotation id (+ job id)
  datasetId: number;
  sampleToken: string;
  source: BoxSource;
  jobId?: number;
  className: string | null; // 현재 GT에는 없음
  center: [number, number, number];
  sizeWLH: [number, number, number];
  quaternionWXYZ: [number, number, number, number];
  coordinateFrame: 'WORLD';
}
```

이 모델은 API DTO를 대체하는 서버 계약이 아니다. 별도 mapper에서 GT/Prediction DTO를 동일 표시 모델로 변환한다. calibrated confidence 필드를 만들어 1.0을 표시하지 않는다. BIGINT 숫자가 JS 안전 정수 범위를 벗어나는 데이터까지 확대할 때는 서버와 문자열 ID 정책을 먼저 합의한다.

## 7. 실제 API 연결과 예외 처리

| 기능 | 현재 API | 주의 |
|---|---|---|
| dataset·scene | `/api/datasets`, `/api/datasets/{id}/scenes` | 숫자 ID로 조회 |
| sample 목록 | `/api/scenes/{id}/samples` | limit 1~500, offset≥0. 순서와 pagination 유지 |
| 센서 파일 | `/api/samples/{id}` | 기본 keyframesOnly=true. contentUrl은 Spring 상대 URL |
| GT | `/api/samples/{id}/annotations` | 원본 categoryToken/categoryName 포함(v1.2 추가, nullable) |
| 카메라 투영 | `/api/sensor-files/{id}/calibration`, `/pose` | 각 카메라 파일의 pose 사용 |
| 이미지/점군 파일 | `/api/sensor-files/{id}/content` | LiDAR/Radar는 binary. Rerun recording URL이 아님 |
| 검색 | `/api/search/scenes` | query를 안전하게 인코딩. 빈 결과 정상 |
| job 생성 | `POST /api/auto-label/jobs` | body와 Idempotency-Key |
| job 상태/결과 | `/api/auto-label/jobs/{id}`, `/{id}/results` | 결과는 완료 전 409 가능 |

### 시안과 실제 DTO의 차이

| 대상 | 실제 계약 | 화면 연결 |
|---|---|---|
| Scene | `token`, `id`, `datasetId`, `nbrSamples` | 숫자 id로 조회하고 token으로 job 생성 |
| samples | `Sample[]` | `{items,total}`을 가정하지 않음. 전체 수는 Scene의 nbrSamples 참고 |
| sample detail | `{sample,sensorFiles,maps}` | `sample.token`, `sample.timestampUs`를 읽음 |
| GT·pose·calibration | 평탄한 center/translation/rotation/intrinsic 필드 | mapper에서 벡터·행렬로 변환 |
| search | `scenes[]`, `sceneName`, `bestSampleToken` | 결과 목록과 대표 프레임으로 변환 |
| create job | `{jobId,status}` | 생성 요청 정보를 receipt에 함께 저장 |
| job status | `completedAt`, datasetId, v1.2부터 sceneToken/sceneId/sceneName/classMode/mappingName 추가 | 서버 문맥 → receipt → 결과 sampleTokens 순으로 소속 검증 |
| job results | `boxes[]`, `detectionName`, 최상위 datasetId | dataset+sampleToken으로 연결 |
| SensorFile | `width`, `height`, `contentUrl` 제공 | 실제 원본 비율로 표시·투영 |

`Scene`에는 location이 없으므로 카드의 필수 항목에서 위치를 제외한다. 위치를 추가하면 sample detail의 map 정보 또는 별도 서버 확장을 사용한다. 썸네일 API가 없어도 기존 JPG로 목록을 구현하며, 축소본 제공은 성능 개선 항목으로 둔다.

성공 응답은 envelope 없는 객체/배열, Spring JSON은 camelCase다. 비즈니스 오류의 `{code,message}`와 Spring 기본 오류 형식을 모두 받아 사용자 오류 모델로 정규화한다.

| 응답 | 프론트 처리 |
|---|---|
| 400 | 입력 또는 설정을 수정하도록 안내. 자동 반복 요청 안 함 |
| 404 | 없어진/잘못된 대상 또는 파일 상태 표시. 링크 복구 제공 |
| 409 | 결과 준비 전, key 충돌 등 호출 문맥과 code/message에 따라 안내 |
| 502/503 | 서비스 연결 또는 처리 오류 안내. GET 재시도는 제한적으로 수행 |
| 500/형식 불일치 | 일반 오류와 다시 조회. mock 결과로 조용히 대체하지 않음 |

개발 서버는 `/api`를 백엔드 주소로 proxy한다. 배포는 같은 origin의 reverse proxy를 기본으로 하고 JSON과 이미지 contentUrl을 함께 전달한다. 다른 PC의 백엔드 사용 시 루프백 바인딩을 포함한 접속 경로를 팀에서 확정한다. FastAPI 주소·DB 접속정보를 프론트에 넣지 않는다.

예시 모드가 필요한 경우 명시적인 설정으로 선택하고 항상 표시한다. 실제 API 실패 시 예시 모드로 자동 전환하지 않는다.

## 8. 프레임 재생과 이미지 라벨

### 재생 정책

- sample 목록은 시간 순으로 읽고 `sampleToken → sampleId` 인덱스를 만든다.
- 긴 씬은 페이지를 추가 로딩한다. 처음 100프레임만으로 전체 씬 타임라인을 완료했다고 표시하지 않는다.
- `timestampUs` 차이를 시간으로 변환해 재생 간격을 정한다. 0.5×/1×/2×를 기본 제안으로 한다.
- `requestedSampleToken`과 실제 표시 중인 `displayedSampleToken`을 분리한다.
- 새 프레임의 이미지/박스가 준비되면 함께 전환한다. 준비 전에는 이전 프레임을 유지하거나 로딩 표시를 하고 이전 박스를 새 이미지에 겹치지 않는다.
- 실패한 카메라는 새 프레임의 누락/오류 상태로 처리하고 이전 이미지로 채우지 않는다.
- 필요한 파일을 기다리는 동안 buffering을 표시한다. 기본 재생은 프레임을 보존하고 늦으면 기다린다.
- 인접 프레임 prefetch는 우선 1~2개로 시작하고 실제 파일 크기·메모리 측정 후 조절한다.
- 작업대 이탈·숨겨진 탭에서는 재생을 멈추고 timer, 이미지 blob URL, viewer 자원을 정리한다.

### 투영 규칙

박스의 로컬 꼭짓점을 회전하고 중심을 더한 뒤 카메라 좌표로 변환한다.

```text
p_world = R_box × p_local + center_world
p_camera = inverse(T_ego_sensor) × inverse(T_world_ego) × p_world
pixel = K × p_camera → depth로 나누어 u,v 계산
```

nuScenes 박스는 size 입력 W/L/H와 로컬 축 길이를 구분한다. 로컬 x는 L, y는 W, z는 H에 대응하며 꼭짓점은 ±L/2, ±W/2, ±H/2에서 만든다. [nuScenes devkit Box 구현](https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuscenes/utils/data_classes.py)

API quaternion W/X/Y/Z와 사용하는 수학 라이브러리의 입력 순서를 명시적으로 변환한다. 모든 카메라에 같은 ego pose를 공유하지 않는다. 스윕 누적과 시간 보간은 초기 MVP에서 제외하고 keyframe 기본 조회를 유지한다.

카메라 뒤 박스, near plane을 통과하는 선분, 화면 밖 박스, intrinsic null, 유효하지 않은 숫자를 처리한다. 박스 일부가 카메라 뒤에 있다고 전체 꼭짓점을 무조건 나누면 잘못된 선이 생기므로 선분 clipping 정책을 구현한다.

image와 overlay는 원본 width/height를 같은 기준으로 사용한다. SVG viewBox 또는 Canvas 스케일을 이미지 표시 크기와 맞추고 object-fit 여백을 반영한다. 분할 드래그·확대·창 크기 변경 후에도 일치해야 한다. 수학 검증에 더해 실제 프레임과 devkit 참고 이미지로 위치·축 방향을 비교한다.

정답과 예측은 같은 sample의 world 공간에서 표시한다. 시각적 겹침을 IoU·정확도·tracking 일치로 설명하지 않는다. category 비교는 후속 합의한 mapping을 적용한다.

## 9. Rerun 연결 설계

VESPA 환경에는 `rerun-sdk==0.21.0`이 있지만 실행 wrapper는 `visualize=False`다. v1.2 기술 검증에서 `@rerun-io/web-viewer@0.21.0`은 `ready`/`fullscreen` 이벤트만 있고 시간 읽기·설정과 선택 이벤트가 없음을 확인했다. 그래서 recording exporter는 AI 기본 환경의 `rerun-sdk==0.38.1`, 웹은 `@rerun-io/web-viewer@0.38.1`로 함께 고정했다(VESPA venv의 0.21.0은 유지). 0.38.1은 `time_update`, `selection_change`(entity_path + instance_id), `set_current_time` 등을 제공한다. 실제 계약·검증은 [Rerun recording 계약](rerun-recording.md)과 체크리스트를 따른다.

웹 뷰어는 호환되는 recording 또는 지원되는 스트림이 필요하고 Python SDK·웹 패키지 버전을 맞춰야 한다. React 패키지 연결과 선택 이벤트는 공식 문서를 참고하되, 프로젝트에서 고정할 버전의 API를 따로 확인한다. [Rerun 웹 임베딩 문서](https://rerun.io/docs/howto/integrations/embed-web)

### 선행 기술 검증

1. 현재 pin과 호환되는 작은 실제 `.rrd`를 생성하고 React/Vite에서 연다.
2. WASM 로딩·배포 자산 경로·뷰어 resize·자원 해제가 되는지 확인한다.
3. 목표 버전에서 시간 읽기/설정과 선택 이벤트가 가능한지 확인한다.
4. GT/예측 레이어 토글, 개별 box 선택 식별자 전달 방법을 확인한다.
5. 단일 뷰어의 메모리·로딩 시간을 측정하고 기록한다.

선택 API가 entity 단위만 제공한다면 박스 인스턴스별 식별 전략을 별도로 마련한다. 목록의 annotation ID가 모든 프레임의 같은 객체 ID라고 가정하지 않는다. 필요한 기능을 목표 버전에서 지원하지 않으면 SDK/웹 버전의 동시 변경 또는 MVP 상호작용 범위 변경을 명시적으로 결정한다.

### recording 데이터 계약 — v1.2 구현됨

recording은 별도 exporter가 원본 점군·GT·필요한 job의 예측을 묶어 생성하는 방식을 우선 검토한다. `visualize=True`만 바꾸는 것으로 웹 파일 생성·제공이 완료된다고 보지 않는다. SDK 호환성과 실제 데이터 검증을 통과한 경로를 선택한다.

- sceneId, datasetId, jobId와 recording을 연결한다.
- keyframe sampleToken, timestampUs, viewer timeline 값의 대응표를 제공한다.
- WORLD 좌표 LiDAR/GT/예측 또는 명확한 센서 transform 계층을 기록한다.
- point cloud, ego, GT, prediction의 entity 경로와 box key mapping을 정의한다.
- 원본 센서·GT만 있는 recording과 특정 job 예측을 포함한 recording의 준비 여부를 구분한다.
- 파일 URL·SDK 버전·좌표계·범위·준비 상태·생성 실패 이유를 조회할 수 있게 한다.

### recording API — v1.2 구현됨 ([계약](rerun-recording.md))

| 호출 | 제안 동작 |
|---|---|
| `POST /api/scenes/{sceneId}/recordings` | body `{jobId?: number}`. GT·센서만 또는 완료 job 예측을 포함한 생성 요청. `202 {recordingId,status}` |
| `GET /api/recordings/{recordingId}` | 대상 문맥, 준비 상태, 버전, 좌표계, timeline/sample mapping, 준비된 contentUrl 또는 실패 이유 |
| `GET /api/recordings/{recordingId}/content` | READY recording의 `.rrd` bytes. Spring 상대 URL. 필요한 Range 지원은 목표 Viewer로 검증 |

새 계약의 준비 상태는 `PENDING/RUNNING/READY/FAILED`로 제안하고 라벨 job enum과 분리한다. metadata에는 최소한 datasetId, sceneId, sceneToken, 선택적 jobId, sdkVersion, coordinateFrame, timeline 이름·단위, sampleToken별 timeline 값이 필요하다. 박스 선택 연동용 entity/box mapping도 함께 정의한다. timeline이 sample index를 사용하더라도 외부 sampleToken 대응표를 제공한다.

jobId가 있으면 씬 소속과 COMPLETED를 서버에서 검증한다. 같은 원본·job·export 설정의 recording은 재사용하고, 생성 실패 재시도는 recording만 다시 생성한다. recording 오류로 VESPA를 다시 실행하지 않는다. v1.2에서 위 경로로 구현했고 `GET /api/scenes/{sceneId}/recordings` 목록을 추가했다. 0.38.1 Viewer는 `.rrd`로 끝나지 않는 HTTP URL을 열지 않으므로 프론트는 content를 fetch해 log channel로 전달한다.

Spring은 AI `/results` 볼륨을 공유하지 않는다. recording은 별도 `rerun_recordings` volume(AI 쓰기, Spring 읽기 전용)에 저장하고 Spring content API로만 제공한다. artifact metadata의 relativePath를 브라우저 파일 URL로 직접 연결하지 않는다. `COMPLETED`인 라벨 job과 recording 생성 완료는 별개일 수 있다.

React 공통 타임라인을 프레임 상태의 기준으로 사용한다. Rerun에서 시간을 이동할 경우 해당 sample에 매핑하고, 출처와 변경 여부를 확인해 React↔Viewer 이벤트 반복을 막는다. 원하는 프레임 데이터가 아직 로딩 중이면 동기화 완료로 표시하지 않는다.

뷰어 부재·미준비·로드 실패는 각각 안내하되 카메라·작업 조회는 유지한다. recording을 기다리는 화면은 실제 점군처럼 보이는 예시 그림으로 대체하지 않는다.

## 10. 백엔드·AI 협의 목록

GT category와 Rerun 생성·제공은 이번 작업에 포함한다. 다음 표는 구현 역할과 계약 항목이며 담당자의 실명·일정은 아직 지정하지 않았다.

| ID | 역할 | 합의할 내용 | 완료 조건 |
|---|---|---|---|
| BE-01 | 백엔드 | API 주소·프록시·실제 dataset/embedding 준비 | 브라우저에서 JSON·JPG 조회와 검색 가능 |
| BE-02 | 백엔드+프론트 | GT annotation category token/name 및 mapping | 원본 category와 classMode별 비교 기준 구분. 이번 필수 범위 |
| BE-03 | AI+백엔드 | Rerun recording 생성·저장·제공 | 실제 씬·job의 recording을 웹에서 열 수 있음. 이번 필수 범위 |
| BE-04 | AI+프론트 | recording sample/timeline·entity·객체 mapping | 같은 프레임과 선택 객체를 연결 |
| BE-05 | 백엔드 | job status에 대상 scene/classMode 정보 보완 | 공유 링크의 job 소속을 서버 응답으로 검증 |
| BE-06 | 백엔드 | Spring OpenAPI | 실제 프론트 계약 기반 타입 자동 생성 |
| BE-07 | 백엔드 | 선택적 scene 단건/thumbnail 조회 | 목록 보완 조회 수·직접 링크 복구 개선 |
| BE-08 | 백엔드·AI | 작업 이력·취소·복구·결과 pagination | MVP 이후 범위와 정책 확정 |

BE-05 전에는 생성 성공 시 datasetId/sceneToken/classMode/jobId의 receipt를 로컬에 저장한다. 외부 링크의 임의 jobId는 datasetId가 같다는 이유만으로 현재 씬의 작업이라고 확정하지 않는다. 완료 결과의 sampleTokens로 씬 소속을 검증할 수 있지만, PENDING/RUNNING의 대상은 현재 status 응답만으로 검증할 수 없다. 검증 전 상태는 ‘작업 대상 확인 필요’로 표시한다.

BE-01이 준비되면 카메라 개발을 시작할 수 있다. BE-02는 GT 클래스 비교, BE-03/04는 Rerun 완료 기준의 선행 조건이다. BE-06/07을 기다리느라 기본 UI 개발을 중단하지 않는다.

GT 보완은 기존 annotation 응답에 nullable `categoryToken/categoryName`을 추가하는 호환 가능한 방식을 제안한다. 원본 nuScenes category를 보존하고 별도 mapper로 1/3/8종 표시 기준에 연결한다. 매핑할 수 없는 GT는 ‘비교 분류 없음’으로 표시하며 임의의 vehicle로 바꾸지 않는다. 예측 track ID는 이번 MVP의 필수 서버 확장으로 두지 않는다.

## 11. 코드와 컴포넌트 구조

저장소에 `frontend/`를 추가하는 것을 제안한다. 구현 단계에서 기존 Gradle·AI 코드와 독립적으로 프론트 의존성과 빌드 경로를 관리한다.

```text
frontend/
  src/
    app/                  router, providers, app shell
    api/                  HTTP client, DTOs, mappers, query hooks
    pages/                SceneSearch, SceneWorkspace, SceneCompare
    features/
      scenes/             dataset picker, scene cards, comparison selection
      cameras/            CameraGrid, CameraTile, CameraOverlay, CameraDialog
      timeline/           FrameTimeline, playback, frame readiness
      viewer/             RerunPanel, ViewerTimeBridge, RecordingStatus
      labeling/           JobControls, JobStatus, ObjectInspector
    stores/               pane workspace, layout preferences
    lib/geometry/         box corners, transforms, projection, clipping
    components/ui/        shadcn/ui 기반 공통 UI
    styles/               design tokens
  tests/                  실제 사용자 흐름·기하 검증
```

선택한 HTML·핸드오프·디자인 결정 기록은 `docs/frontend-design/`를 사용한다. 뷰어와 6카메라 영역은 필요한 화면에서 로드한다. React 버전과 관련 패키지는 구현 시작 시 호환 조합을 확인해 lockfile에 고정한다. Query와 Zustand는 각각 서버 상태와 화면 상태를 맡는다. ECharts는 평가 기능 단계까지 초기 의존성 설치를 미룬다.

API 타입은 우선 현재 Spring 문서·DTO를 기준으로 작성하고, OpenAPI가 생기면 생성 타입과 검증한다. 내부 FastAPI OpenAPI를 Spring 프론트 타입으로 사용하지 않는다.

## 12. 디자인·접근성·화면 크기

- 기본 방향은 수정 HTML의 다크 테마. 배경 `#111215`, 카드 `#1C1D22`, 입력 면 `#26272D`, 주요 글자 `#F2F4F6`, 보조 글자 `#B0B8C1`을 기준으로 한다.
- GT `#FFCC4D` 점선, 예측 `#4FE0D5` 실선, A `#9B8CFF`, B `#FF7AA2`. 색상 외에도 범례·선 형태·패널 이름을 제공한다.
- 파랑 `#2272EB`와 hover `#3182F6`는 기준 시안의 값이다. 흰 글자 대비가 각각 약 4.49:1/3.71:1이므로 제품 버튼은 대비를 확보하도록 조정한다. 예를 들어 기본 `#216FE5`, hover `#1D64D6`를 후보로 검수한다.
- Pretendard와 시스템 한글 폰트 fallback, 기본 글자 14px, 주요 실행 버튼 52px, 반경 6/10/12/16/22px를 시작 기준으로 한다. 일반 진단 문구를 제품 설명으로 노출하지 않는다.
- 한국어 UI, 영문 제품명·센서 채널·클래스. 단위와 좌표계 표기를 통일한다.
- 센서 화면을 크게 유지하고 앱 통계 카드나 내부 모델 설치 정보를 메인 화면에 배치하지 않는다.
- 정상·hover·선택·focus·비활성·로딩·오류의 대비를 확인한다.
- modal은 이름·초기 포커스·포커스 가두기·Esc·닫힌 후 복귀를 제공한다.
- slider와 분할 경계는 키보드 조절 가능하고 현재 값·대상을 알 수 있게 한다.
- 객체 박스를 직접 누르기 어려운 사용자는 같은 객체 목록에서 선택할 수 있다.
- 재생 상태·job 상태는 알리되 매 프레임을 스크린리더로 반복 낭독하지 않는다.
- reduced-motion을 반영하고 실제 데이터 재생과 장식 효과를 구분한다.

| 폭 | 배치 제안 |
|---|---|
| 1280px 이상 | 센서 작업 영역 + 우측 객체/작업 패널. 6카메라는 3열 기본 |
| 1024px | 분할 최소 폭 보장. 보조 패널 접기 지원 |
| 768px 전후 | 센서 패널 세로 배치 또는 탭. 비교 씬의 선택 문맥 명시 |
| 375px | 주요 카메라 탐색·프레임·job 조회 유지. 3D 사용 가능성은 실제 장치 확인 |

breakpoint는 고정 요구가 아닌 시작안이다. 기본 인스펙터 340px는 접기와 폭 축소를 지원하고 1280/1440px에서 센서 정보가 읽히는지 확인한다. 실제 HTML과 센서 비율을 기준으로 최종 조정한다. 좁은 화면에서 필수 동작을 단순히 숨기지 않는다. 휴대폰에서 6개 카메라를 동시에 크게 보는 경험까지 데스크톱과 동일하게 보장하지는 않으며, 세로 스크롤과 카메라 확대를 제공한다.

## 13. 개발 단계와 산출물

개발 인원·가용 시간·백엔드 준비일이 정해지지 않아 날짜를 확정하지 않는다. 각 단계는 완료 조건으로 다음 단계에 넘긴다.

| 단계 | 작업 | 산출물·완료 조건 | 선행 조건 |
|---|---|---|---|
| M0 | 기준 시안 인수 완료, Rerun 기술 검증 | 기준 파일·디자인 결정은 본 문서에 반영. 실제 작은 recording의 웹 로딩·시간 제어 검증은 착수 시 진행 | 실제 sensor 자료 및 exporter |
| M1 | frontend 기반, router/query/store/proxy | 실제 dataset·scene·sample 조회 | API 접속과 데이터 준비 |
| M2 | 카메라·확대·분할·재생 | 실제 6카메라가 같은 프레임으로 이동 | M1 |
| M3 | 검색·job 생성·polling·URL 복원 | 검색→실행→결과 확인 | embedding 및 실행 가능한 VESPA |
| M4 | 카메라 박스 투영·GT 비교 | 실제 이미지에서 좌표 일치 검증 | calibration/pose/GT/예측, 클래스 비교는 BE-02 |
| M5 | Rerun recording 및 시간/객체 연결 | 실제 점군·박스를 같은 프레임으로 확인 | BE-03/04 및 기술 검증 |
| M6 | 두 씬 비교·완료 검수 | 동일/다른 씬 A/B 독립 및 상대 동기화, 반응형·실제 흐름 검증 | 카메라/타임라인 기반; 동시 두 3D는 후속 |

두 씬 카메라 비교의 UI·상태 분리는 M2 이후 병행 가능하다. Rerun 기술 검증은 초기에 하되 전체 연결 완료는 recording 계약 준비 후 진행한다.

### 첫 구현 묶음

1. `frontend/`에 React/TS/Vite와 공통 provider, 실제 API proxy를 구성한다.
2. 디자인 tokens·앱 shell·세 화면 route를 만든다. 패널 상태와 URL 구조를 처음부터 A/B 분리 기준으로 작성한다.
3. DTO·mapper와 dataset→scene→samples→sample detail 조회를 연결한다.
4. 첫 실제 씬의 6개 JPG, 채널명, 누락 상태, 확대·프레임 이동을 완성한다.
5. 이 흐름을 확인한 뒤 재생·검색·job·overlay를 순차 연결한다.

이와 병행해 BE-02의 GT category join과 BE-03/04의 recording exporter·제공 경로를 구현한다. 첫 구현 완료 판정은 ‘실제 씬을 열고 6개 카메라를 한 프레임씩 이동할 수 있음’이며 합성 이미지 표시로 대체하지 않는다.

### 역할 제안

- 프론트: HTML 인수, 화면·상태·투영·뷰어 연결, 사용자 흐름 검증.
- 백엔드: API 계약·접속·GT 클래스·job 문맥·recording 제공.
- AI: VESPA 실행 환경·결과·recording 생성과 시간/좌표 규칙.
- 팀 공동: 시안 선택, class mapping, 실제 씬 기준 비교, 단계 완료 판정.

## 14. 검증과 성능 기준

### 필수 검증 시나리오

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| QA-01 | 검색 후 대표 프레임 열기 | 올바른 dataset·scene·sample |
| QA-02 | 일반 목록에서 새 탭 열기·새로고침 | 이름·센서·선택 프레임 복원 |
| QA-03 | 프레임 빠르게 이동 | 늦은 응답으로 이전 이미지/박스가 덮이지 않음 |
| QA-04 | 카메라 하나 누락·실패 | 해당 채널만 오류, 다른 채널과 탐색 유지 |
| QA-05 | 분할 크기 변경·확대 | 박스와 이미지 좌표 일치 |
| QA-06 | 생성 POST 응답 유실 후 재시도 | 같은 key로 같은 job, 불필요한 새 job 없음 |
| QA-07 | GET 일시 실패·복구 | job 자체 FAILED로 잘못 표시하지 않음 |
| QA-08 | 완료했지만 박스 없는 프레임 | 검출 없음과 오류 구분 |
| QA-09 | A/B에 같은 씬 열기 | 서버 cache 공유와 UI 상태 독립 |
| QA-10 | 상대 동기화 on/off·단일 프레임 | 올바른 시간 매핑, 0분모 예외 없음 |
| QA-11 | Rerun 준비 중·실패·정상 | 상태 구분, 카메라 UI 유지, 실제 프레임 일치 |
| QA-12 | 회전·축·near plane·카메라 뒤 박스 | 기하 단위검증과 실제 devkit 비교 |
| QA-13 | 키보드·작은 화면·확대 닫기 | 주요 동작 접근 가능, 포커스 복원 |
| QA-14 | 다른 씬 job 링크 연결 | 대상 검증 또는 확인 필요 안내 |
| QA-15 | 완료 job 결과 GET 실패 후 다시 조회 | 기존 job 유지, 새 생성 POST 없이 복구 |
| QA-16 | recording 생성 실패·다시 요청 | recording만 복구, VESPA 재실행 없음 |
| QA-17 | GT category와 1/3/8 mapping | 원본 분류 보존, 미매핑 표시, 예측에서 GT 이름을 복사하지 않음 |

Vitest는 좌표 변환·투영·시간 mapping·정상/오류 응답 변환처럼 계산과 경계 조건에 사용한다. Playwright는 탐색·확대·비교·재생·job 복원 등 핵심 흐름에 사용한다. 실제 GPU 작업을 매 테스트에서 실행하지 않고, UI 검증용 고정 응답과 실제 통합 검증을 구분한다.

최종 통합에서는 실제 mini 씬과 완료 job으로 카메라 6채널, 예측/GT, 실제 점군을 확인한다. 실행한 commit, dataset/version, jobId, browser, 화면 크기, 캡처를 기록한다. 캡처만으로 좌표나 모든 동작을 검증했다고 하지 않는다.

### 성능 목표 — 제안, 측정 전

- 캐시된 레이어 토글·선택·레이아웃 조작은 목표 환경에서 200ms 이내 반응을 목표로 한다.
- 같은 씬 반복 진입 시 metadata·calibration·pose를 불필요하게 다시 받지 않는다.
- 프레임 이동 요청·파일 용량·decode 시간·Rerun 메모리를 실제로 측정한다.
- 두 씬 비교에서 이미지 prefetch와 viewer 사용량을 제한한다.
- 최초 화면/첫 3D 표시 시간은 네트워크·GPU·파일 크기와 함께 기록하고, 측정 후 합의한 기준을 적용한다.

측정 전 ‘실시간’, ‘30fps’, ‘즉시 완료’를 성능 보장 문구로 사용하지 않는다. 키프레임의 원본 간격을 실제 재생의 기준으로 삼는다.

## 15. 착수 전 결정·추적 항목

| ID | 현재 상태 | 다음 결정 |
|---|---|---|
| D-01 | 수정 시안을 디자인 기준으로 기록 | 실제 렌더링·버튼 대비·센서 면적은 구현 시 검수 |
| D-02 | React/TS/Vite 및 기존 스택 적용 | 구현 시 패키지 호환 버전·lockfile 확정 |
| D-03 | 접속 주소 미확인 | 실제 API 접근 방법과 데이터 준비 담당 확인 |
| D-04 | GT 클래스 추가는 이번 필수 범위 | 원본 category와 1/3/8 mapping 계약 확인 후 구현 |
| D-05 | Rerun 생성·제공은 이번 필수 범위 | SDK 호환 검증·exporter·저장소·timeline 계약 확인 후 구현 |
| D-06 | job 문맥 일부 부족 | 공유 링크에서 작업 대상 검증 방식 |
| D-07 | 시간·인력 미확정 | M0~M6의 팀별 일정과 완료 확인자 지정 |

기준 시안은 인수했고 기능·상태·개발 순서는 이 문서로 정리했다. API 접속과 실제 데이터 준비를 확인하면 M1과 M2를 진행한다. 현재 카메라·검색·job API를 이용하는 개발과 recording/GT 클래스 보완을 병행한다. 담당자·일정과 새 API의 세부 계약이 미정이라는 이유로 화면·DTO·패널 구조 작업까지 중단하지 않는다.

### 단계별 완료 표기

- **카메라 기반 완료:** 실제 탐색·6카메라·재생·확대·검색·job·이미지 overlay가 동작한다. Rerun이 남아 있으면 이 상태로만 표기한다.
- **이번 범위 완료:** GT category/mapping, 실제 Rerun·시간/객체 연결, 동일/다른 씬 A/B 비교, 오류 복구와 QA-01~17을 충족한다.
- **사용 가능한 빌드:** 타입 검사·제품 빌드와 관련 테스트를 통과하고, 실제 데이터 통합 기록·API proxy·SPA 경로·Rerun 자산 로딩을 확인한다. 미검증 브라우저·환경은 별도로 기록한다.

인증·권한·인터넷 공개 운영은 이번 기능 구현 완료에 포함하지 않는다. 실제 공개 출시를 결정하면 별도의 배포·운영 범위를 정한다.

## 16. 참고와 문서 우선순위

- 실제 요청/응답과 오류는 [README_API.md](../README_API.md)를 기준으로 한다.
- 현재 환경은 [README.md](../README.md), [Docker 검증 기록](docker-integration.md)을 참고한다.
- 최종 시안의 시각 규칙은 확정 HTML과 디자인 결정 기록을 기준으로 한다.
- 기능 범위·사용자 동작·완료 기준은 이 기획서를 기준으로 한다.
- 과거 프론트 구성안의 가상 API, confidence 필터, 진행률·평가 화면은 현재 구현 사실로 취급하지 않는다.
- [Rerun 웹 임베딩](https://rerun.io/docs/howto/integrations/embed-web), [nuScenes Box 구현](https://github.com/nutonomy/nuscenes-devkit/blob/master/python-sdk/nuscenes/utils/data_classes.py)은 호환·기하 검증 참고이며 프로젝트 고정 버전과 대조한다.

문서와 코드가 달라지면 변경한 계약과 UI 영향을 함께 기록한다. 이 문서 작성으로 프론트 설치·구현·배포 또는 실제 서버 검증이 완료된 것은 아니다.

### 변경 이력

| 버전 | 내용 |
|---|---|
| v1.0 | 기존 API·화면 요구 기반 개발 초안 |
| v1.1 | 수정 시안 인수, 기존 스택 명시, 동일 씬 비교, DTO 차이·결과 재조회, GT/Rerun 필수 범위와 recording 계약 초안, 첫 구현 묶음·QA 추가 |
| v1.2 | 구현 반영: GT category·job 문맥 필드, Rerun 0.38.1 고정과 recording API/exporter, VESPA class mapping 근거, Viewer 로딩 방식. 진행·검증은 체크리스트 |
