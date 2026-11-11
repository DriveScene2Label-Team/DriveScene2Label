# DriveScene2Label 개발 지침

이 저장소는 Spring Boot + PostgreSQL/pgvector + 내부 FastAPI/CLIP/VESPA로 구성된다. 현재 프론트 개발 기준과 디자인 자료가 준비되어 있으며, 실제 앱은 `frontend/`에 구현한다. 사용자의 현재 요청이 이 문서의 일반 지침보다 우선한다.

## 먼저 읽을 문서

현재 실제 데이터·프론트 연동 개선 작업의 시작 기준은 [개선 기획서](docs/frontend-integration-plan.md)와 [개선 구현 체크리스트](docs/frontend-integration-checklist.md)다. [근거 분석](docs/frontend-integration-review.md)에서 확인한 문제·미검증 범위를 함께 읽는다. 기존 M1~M6 기록은 아래 문서에 유지하고, 이번 개선 범위의 계약·진행 순서는 개선 기획서를 우선한다. 현재 사용자 요청이 기획 정립이면 구현에 착수하지 않는다.

실제 업데이트를 시작하거나 중단 후 이어갈 때는 [Claude Code 업데이트·재개 프롬프트](docs/claude-code-integration-prompt.md)를 사용한다. 프롬프트 작성 요청 자체는 프로그램 구현 착수와 구분한다.

2026-11-05 UI/UX 리뉴얼(라벨 편집 API 포함)의 디자인 기준은 [리뉴얼 목업](docs/frontend-design/renewal-mockup.html), 범위·의도된 차이·검증은 [프론트 리뉴얼 기록](docs/frontend-renewal.md)이다. 제품 화면을 고칠 때는 이 둘을 먼저 대조한다.

2026-10-06 이후의 현재 재개 기준은 [I1/I2 보완·후속 검증 프롬프트](docs/claude-code-integration-followup-prompt.md)다. [검토 문서](docs/frontend-integration-audit-2026-10-06.md)의 상태 조회 실패 후 이전 READY 사용과 구버전 receipt DB 귀속 문제를 먼저 보완하고 체크리스트 FU-01~08을 따라 진행한다. I0 main 병합과 기존 앱 구현을 반복하지 않는다.

1. [프론트 개발 기획서](docs/frontend-product-plan.md): 화면·기능·상태·개발 범위.
2. [구현 체크리스트](docs/frontend-implementation-checklist.md): 진행 상태·완료 조건·검증 기록.
3. [실제 REST 계약](README_API.md): 기존 Spring 요청/응답·오류.
4. [디자인 결정](docs/frontend-design/README.md), [HTML 원본](docs/frontend-design/index.html): 디자인·상호작용 참고.
5. [환경과 실행](README.md), [Docker 검증](docs/docker-integration.md), [VESPA wrapper](ai-server/VESPA.md).

기획서의 범위, 기존 코드의 실제 계약, 디자인 기준을 함께 확인한다. 불일치는 코드·DTO로 검증하고 문서에 기록한다. `docs/frontend-design/claude-handoff.md`는 전달받은 원문이며 실제 API 계약보다 우선하지 않는다. 디자인 원본은 보존하고 제품 코드는 별도로 작성한다.

## 구현 범위와 작업 방식

- 현재 작업 브랜치에서 진행한다. 다른 작업자의 변경을 초기화하거나 덮어쓰지 않는다.
- 프론트뿐 아니라 GT category 보완, Rerun recording 생성·저장·Spring 제공도 이번 범위다.
- React/TypeScript/Vite, React Router, TanStack Query, Zustand, Tailwind/shadcn/ui, Rerun Web Viewer를 사용한다.
- M1~M6을 작은 검증 가능한 묶음으로 구현하고 체크리스트에 실제 진행·검증을 남긴다. Rerun 기술 검증은 초기에 병행한다.
- 일반적인 구현 선택은 근거를 기록하고 진행한다. 계획을 설명하는 데서 끝내거나 단계마다 사용자 승인을 요구하지 않는다.
- 실제 서버·데이터·GPU가 없으면 가능한 구현과 계산/계약 검증을 계속한다. 없는 파일·jobId·검증 결과를 만들지 말고 통합 미검증 사유와 필요한 환경을 기록한다.
- 완성된 범위를 실제 데이터 검증 범위와 구분한다. 동작하지 않는 자리 표시자로 완료 처리하지 않는다.
- 모델·데이터·DB volume의 대규모 다운로드/재생성·삭제, 원격 push/PR는 현재 사용자가 요청한 범위를 확인한다. 준비 작업만 요청받았다면 실제 앱 구현에 착수하지 않는다.

## 반드시 유지할 계약

- 브라우저는 Spring `/api/*`만 호출한다. FastAPI는 내부 서비스이며 DB 소유자는 Spring이다.
- 성공 응답은 객체 또는 배열이다. 전역 `{data}` envelope를 가정하지 않는다.
- 숫자 DB ID, 원본 token, scene 이름을 구분한다. datasetId를 1로 고정하거나 scene 이름을 전역 키로 사용하지 않는다.
- samples 응답은 `Sample[]`, 상세는 `{sample,sensorFiles,maps}`, 검색은 `scenes[]`, 결과는 `boxes[]`다.
- 카메라는 JPG 키프레임 시퀀스다. 재생·상대 동기화는 `timestampUs` 기반이며 실제 영상/실시간 스트림으로 설명하지 않는다.
- GT/예측은 WORLD 미터, size W/L/H, quaternion W/X/Y/Z다. 박스 로컬 x=L, y=W, z=H를 지킨다.
- 카메라마다 해당 sensor file의 pose와 calibration을 사용한다. 이미지와 박스는 동일 sample이 준비되었을 때 함께 표시한다.
- VESPA detectionScore=1.0은 고정값이다. confidence UI·정확도·진행률을 임의로 만들지 않는다. 검색 score도 확률이 아니다. 보정된 일치도는 허용하며 근거와 기준값을 문서화한다([검색 일치도](docs/search-match-score.md)). %로 표시하지 않는다.
- job 생성은 씬 전체이며 classMode=1/3/8, 상태는 PENDING/RUNNING/COMPLETED/FAILED다. terminal에서 polling을 멈춘다.
- 같은 실행의 네트워크 재시도는 동일 Idempotency-Key를 사용한다. 사용자가 새 작업을 실행하면 새 key를 사용한다.
- status GET 오류는 job FAILED가 아니다. 완료 결과 GET 재시도는 새 VESPA 작업을 만들지 않는다.
- 현재 작업 트리의 job status에는 sceneToken/sceneId/sceneName/classMode/mappingName이 추가되어 있다. 이전 서버에서는 없을 수 있으므로 receipt를 보존하고 서버 문맥과 대조하며, 완료 시간은 `completedAt`을 읽는다.
- A/B는 같은 씬을 열어도 UI 상태가 독립이어야 한다. 서버 캐시는 공유하되 프레임·재생·선택·레이어·job 선택은 패널별로 둔다.
- `artifact.relativePath`는 다운로드 URL이 아니다. recording의 생성/준비 상태와 라벨 job 상태를 구분한다.

## 프론트 구현 규칙

- API DTO와 화면 모델을 분리하고 mapper에 변환을 모은다. mock를 연결하기 위해 기존 Spring 응답을 깨뜨리지 않는다.
- Query는 서버 상태, Zustand는 패널·배치 상태, URL은 공유 문맥, localStorage는 작은 선호/receipt를 담당한다.
- 큰 이미지·점군·전체 결과를 localStorage에 저장하지 않는다. 조회 취소·decode·prefetch·자원 해제를 구현한다.
- Tailwind/shadcn 기본 테마로 시안을 대체하지 않는다. 디자인 토큰을 적용하고 버튼 글자 대비와 센서 면적을 보완한다.
- 제품 화면에서 시안용 API 설명·합성 이미지·가짜 job을 제거한다. 실제 API 실패를 mock로 자동 대체하지 않는다.
- 테스트 fixture는 실제 DTO 형식을 따른다. 개발용 예시 모드는 명시적으로 분리하고 표시한다.
- 프론트 package manager는 npm을 기본으로 하고 lockfile과 scripts를 함께 관리한다. npm·패키지 호환 버전은 설치 시 확인한다.
- `node_modules`, dist, Playwright 출력·로컬 환경 파일 등을 Git에 넣지 않도록 ignore를 함께 구성한다.

## 백엔드·AI 보완 규칙

- GT geometry는 이미 표시 가능하다. 기존 annotation DTO에 원본 categoryToken/categoryName을 추가하고 dataset 범위를 포함한 JOIN을 검증한다.
- 원본 category를 보존하고 classMode별 표시 분류를 분리한다. 미매핑은 명시하고 임의로 vehicle로 바꾸지 않는다.
- Rerun은 실제 점군·GT·완료 job의 예측을 기록하는 exporter와 파일 제공을 연결한다. `visualize=True`나 fake Canvas만으로 완료 처리하지 않는다.
- Python SDK와 웹 Viewer의 호환 버전을 고정하고 시간 제어·entity/box 선택·resize·WASM 자산을 작은 실제 recording으로 확인한다.
- recording API 초안은 기획서에 있다. 실제 코드에 맞게 계약을 정리해 문서를 갱신한 뒤 구현한다. recording 오류는 recording만 재시도한다.
- 기존 migration은 수정하지 않고 새 Flyway migration을 추가한다. 모델, nuScenes 원본, weights, 결과 .rrd/JSON/NPZ, .env를 commit하지 않는다.
- VESPA는 고정 commit + `ai-server/vespa-patches`로만 수정한다(2026-11-04 사용자 결정). patch 밖에서 upstream 파일을 직접 고치지 않고 Docker·Colab이 같은 `apply.sh`를 쓴다. 기존 CLIP 동작은 보존한다. exporter는 프로젝트 코드에 추가한다.
- 결과 저장과 COMPLETED의 기존 transaction 및 Idempotency-Key 의미를 유지한다.

## 검증과 문서 갱신

- 프론트에 typecheck/build/test/test:e2e scripts를 구성하고 변경 범위에 맞는 검증을 수행한다. 기하·DTO 변환·시간·재시도·A/B 독립을 우선 검증한다.
- 백엔드 계약 변경 시 관련 Spring 테스트, AI 변경 시 관련 pytest를 실행한다. 기존 Docker 테스트의 실행 조건은 README와 scripts를 확인한다.
- GPU 전체 추론을 매 테스트에서 실행하지 않는다. 고정 fixture 검사와 실제 mini 통합 검증을 구분한다.
- 실제 검증은 dataset/version, scene/sample/job/recording, browser, 화면 크기, 결과를 기록한다. 미실행 검증을 통과로 쓰지 않는다.
- 기능 구현 후 `docs/frontend-implementation-checklist.md`를 갱신한다. API 변경은 `README_API.md`, 실행/환경 변경은 README와 예제 환경 파일을 함께 갱신한다.
- 기획서의 완료 여부는 해당 요구·QA와 대조한다. `git diff --check`도 수행한다.
- 마지막 보고에는 변경 범위, 실행한 검사, 실제 연동 여부, 남은 항목을 구분해 적는다.
