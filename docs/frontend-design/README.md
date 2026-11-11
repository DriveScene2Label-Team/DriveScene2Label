# 프론트 디자인 기준 자료

> **2026-11-05 리뉴얼:** 현재 제품 화면의 디자인 기준은 [renewal-mockup.html](renewal-mockup.html)(Apple×Toss, 밝게/어둡게 테마)이다. 적용 범위·의도된 차이·검증은 [프론트 리뉴얼 기록](../frontend-renewal.md)에 있다. 아래 2026-10-04 다크 시안 자료는 이력으로 보존한다.

| 파일 | 역할 | SHA-256 |
|---|---|---|
| [renewal-mockup.html](renewal-mockup.html) | 리뉴얼 목업(단일 HTML, 합성 예시 데이터·mock 백엔드 포함). 원본 그대로 보관 | `bd2cc3e6d49e8c4a44d38cf0defd9b590dc06243a17e1e84da882d503e57f215` |

2026-10-04 작업 폴더에 제공된 수정 HTML과 핸드오프를 원본 그대로 보관했다. 기능 범위와 구현 기준은 [프론트 개발 기획서 v1.1](../frontend-product-plan.md)을 따른다.

| 파일 | 역할 | SHA-256 |
|---|---|---|
| [index.html](index.html) | 디자인·화면 구조·조작 참고용 합성 프로토타입 | `bb153a8618675c1636cbe6bd609bc4063091f49a96f85fefa9953b4b967afeac` |
| [claude-handoff.md](claude-handoff.md) | Claude가 작성한 인계 원문 | `7bfae38b7b7a423f529935939bb8fbc806b7e0e57ece2dc6138a2c8db70a352b` |

## 적용하는 디자인

- 다크 배경과 단계별 회색 면, 한국어 해요체, Pretendard와 시스템 폰트 fallback.
- 주요 행동은 파랑, GT는 노랑 점선, 예측은 민트 실선, A/B는 보라·분홍.
- 씬 탐색, 6카메라, 카메라+LiDAR, 두 씬 비교, 확대 모달, 우측 작업·객체 패널.
- 상단 56px, 주요 실행 버튼 52px, 기본 글자 14px, 카드 반경 6/10/12/16/22px를 시작 기준으로 사용.

## 구현에서 보완하는 사항

1. 흰 글자 버튼의 기본/hover 대비를 조정한다. 시안 값의 대비는 각각 약 4.49:1/3.71:1이다.
2. 기본 340px 우측 패널에 접기·폭 조정 규칙을 적용하고 실제 센서 화면 면적을 확인한다.
3. 동일 씬 A/B 비교를 허용하도록 패널별 상태를 구성한다.
4. 실제 DTO 변환, timestamp 재생, 카메라별 투영, job 생성 재시도·결과 재조회, 실제 Rerun 연결을 구현한다.
5. 합성 생성기·예시 job·일반 화면의 API/SDK 진단 설명을 제품 코드에서 교체한다.

## 핸드오프 원문의 해석

원문을 고쳐서 전달받은 자료와 혼동하지 않도록, 보정 사항은 여기에 기록한다.

- 현재 GT API로 박스 geometry는 표시할 수 있다. 클래스 이름 연결이 부족하다.
- 현재 SensorFile은 width/height를 제공한다. 썸네일·축소본 API는 별도 성능 개선이다.
- Scene 목록에 location이 없으므로 목록 join만으로 위치를 얻을 수 없다.
- HttpAdapter 교체 외에도 실제 DTO→화면 모델 변환과 상태 재구성이 필요하다.
- 알려진 jobId는 현재 status/results API로 조회 가능하다. 팀 전체 작업 이력 탐색 API는 후속이다.
- Idempotency-Key 재사용과 같은 씬의 실행 제한은 서로 다른 문제다.
- 핸드오프의 Playwright 검증·22ms 성능은 Claude의 보고다. 여기서 독립 검증된 수치가 아니다.

## 검토 기록

소스 비교, JS `node --check`, 색상 대비 계산을 수행했다. 직접 브라우저 렌더링·반응형·클릭 검수는 미완료다. 최종 UI 검수는 실제 JPG·GT·job·recording으로 진행한다. 이 파일을 보관한 것은 앱 구현·배포 완료를 의미하지 않는다.
