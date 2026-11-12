# Claude에 전달할 현재 인프라 설계·병목 분석 프롬프트

아래 본문을 복사한다. 저장소를 읽을 수 있는 Claude Code라면 먼저 실제 파일을 확인하게 한다. 일반 대화라면 README와 상세 문서를 함께 제공한다. 로그는 원문 전체 대신 비밀정보를 제거한 계측 보고서를 첨부한다.

---

DriveScene2Label 프로젝트의 **현재 인프라를 설명하는 구조도와 설계 문서**를 만들어 줘. 대상 독자는 대학생 4학년 Cloud/Backend Engineer 지원자와 면접관이야. 기술을 많이 사용했다는 인상보다, 요구사항에 맞춘 선택·대가·실측에 근거한 개선 판단을 명확히 보여줘.

## 자료와 우선순위

- 저장소: https://github.com/DriveScene2Label-Team/DriveScene2Label
- 기준 브랜치: `release-version`. 현재 README와 실제 코드를 먼저 확인해.
- `README.md`: 현재 구성·사용 흐름·실측·검증 범위
- `docs/architecture-and-measurement-2026-11-12.md`: 인증·JPA/JDBC·작업/저장·계측의 코드 근거
- `docs/upload-measurement-2026-11-12.md`: 이번 사용자 업로드·임베딩 실측, 라벨 작업 개입으로 발생한 대기
- 발표 자료는 `docs/presentation-prompt-2026-11-12.md`의 10장 구성을 사용해.
- `docs/hybrid-setup.md`: 현재 Cloudflare 터널과 실행 설정. Microsoft 임시 복구·11월 11일 초기 구성은 이력임
- `docs/troubleshooting-2026-11-11.md`: 이전 실행의 병목·수정·검증
- `docs/work-checkpoint-2026-11-12.md`: 배포·백업·초기화 증거
- `compose.hybrid.yml`, `compose.gpu.yml`, `compose.hybrid-auth.yml`, `frontend/vercel.json`, `scripts/hybrid/`: 구현 설정
- 새로운 시험은 `.local/hybrid/measurements/<시각>/report.json`, `report.md`, `events.jsonl`, `manifest.json`을 확인해. 접근할 수 없으면 미측정으로 표시하고 수치를 만들지 마.
- `docs/aws-deployment-history-2026-11-09.md`의 ECS/EKS/GPU EC2 구성은 **종료한 과거 검증 환경**이야. 현재 구조에 섞지 마.

## 현재 운영 사실

1. 프론트는 Vercel React/Vite. 브라우저는 같은 Vercel 출처의 `/api/*`, `/oauth2/*`를 호출해.
2. Vercel이 **Cloudflare Quick Tunnel**을 통해 로컬 `127.0.0.1:4180` oauth2-proxy에 연결해. 기존 Cognito `team` 그룹 로그인을 검사한 뒤 Spring에 전달해. 이전 Microsoft 연결 토큰은 Cloudflare로 전달하지 않아. 11월 12일 업로드 계측은 전환 전 Microsoft 경로이므로 Cloudflare 성능 수치로 사용하지 마.
3. Spring과 FastAPI는 로컬 PC의 Docker/WSL2에서 실행해. GPU는 보유 RTX 5060 Ti 16GB eGPU야. FastAPI를 외부에 직접 공개하지 않고 DB 조회·저장 책임은 Spring에 있어.
4. AWS 서울 S3는 원본 ZIP/TGZ, RDS PostgreSQL/pgvector는 메타데이터·GT·검색 벡터·작업·예측·편집 이력을 보관해. 기존 Cognito와 IAM/STS도 쓰므로 AWS를 문자 그대로 두 서비스만 쓴다고 적지 마.
5. 해제 데이터·모델·후처리 캐시·RRD는 로컬 Docker 볼륨이야. 모든 결과가 S3에 백업되는 것은 아니고 DB 백업만으로 로컬 파일까지 복구되지는 않아.
6. EC2·ECS·EKS는 현재 사용하지 않아. 클라우드 자원을 만들거나 켜지 말고 문서·다이어그램만 작성해. 도메인 구매·외부 메시지 발송·인증 변경·재배포도 하지 마.

## 반드시 설명할 흐름

- 업로드: 브라우저 → 4,000,000바이트 분할 전송 → Spring 압축 검증·해제 → S3 원본 보관 → RDS 등록 → CLIP 인덱싱. 브라우저에서 S3로 직접 multipart 업로드하는 구조는 아직 아니야.
- 같은 PC의 `http://127.0.0.1:8080/uploads`는 첫 전송 구간의 Vercel/터널 왕복만 생략하고 이후 S3·RDS 경로는 같아.
- 씬 목록은 등록 후 열 수 있고 검색은 임베딩 준비 상태에 따라 사용해. 임베딩과 VESPA 자동 라벨링은 별도 작업이야.
- 사용자가 `scene-0103`을 선택하면 그 씬의 40키프레임을 추론해. 전체 데이터셋 또는 현재 한 장으로 그리지 마. 데이터 캐시가 비었을 때 ZIP 전체를 복원하는 준비 범위와 실제 추론 범위는 구분해.
- 완료 결과는 RDS에 저장되고 씬을 다시 열 때 조회해. 결과 조회가 새 GPU 추론을 의미하지 않아. RRD 생성·편집 override 반영의 현재 지원 범위도 구분해.

## 분석할 설계 선택

- 왜 전체 AWS가 더 단순한 운영 선택일 수 있는데도 현재 혼합 구성을 택했는가? 보유 GPU·시연 시간·원격 보관 조건과 PC/집 회선/터널 의존성의 대가를 함께 설명해.
- ECS와 EKS를 동시에 유지하던 과거 구성은 배포 비교 검증 목적이었어. 현재 작은 단일 GPU MVP에서 그 중복을 유지하지 않는 이유를 설명해. 전체 AWS가 반드시 ECS+EKS 모두를 요구한다고 가정하지 마.
- 전체 AWS / 현재 혼합 / 전체 로컬을 비용 항목·가용성·운영 복잡도·DB 왕복·캐시·확장·백업으로 비교해. 실제 청구 없이 월 절감액이나 성능 우위를 만들지 마.
- JWT/OIDC/세션/쿠키를 구분해. 자체 Spring JWT 필터나 Redis 세션을 구현했다고 쓰지 마. JPA 일반 조회/문서 저장, JDBC batch import, 작업·검색·예측의 명시 SQL을 코드로 확인해.
- PC가 꺼지면 API/GPU는 중단돼. RDS는 로컬 stop과 독립적이야. Cloudflare Quick Tunnel은 재시작 시 주소가 바뀔 수 있어 시작 명령이 Vercel 연결을 갱신해. 고정 도메인이나 상시 무중단 운영을 달성했다고 쓰지 마.

## 로그와 병목 판단 규칙

이전 실행에서 TGZ 압축 검증 약 47.8초, S3 보관 약 358.1초, DB 등록 약 13.0초가 관찰됐고, scene-0103 한 씬은 약 28분 16초 중 이미지 검출·분할이 약 21분 7초였어. 이 수치는 **이전 실행의 기록**이며 새 시험의 결과로 재사용하지 마.

이번 로그는 HTTP request → upload UUID → dataset → job → VESPA run/scene으로 연결해. 브라우저 관찰, 조각 수신/DB 잠금/파일 fsync/transaction, 압축·S3·DB import, CLIP, VESPA 내부, 결과 저장·3D를 나눠. 중첩 span을 더하거나 서로 다른 컴퓨터 시계를 빼서 순수 네트워크 시간으로 만들지 마. `transaction_ms`에는 하위 구간이 포함되고 JDBC 시간에는 네트워크·DB 대기가 섞여 있어.

1회 시험의 평균·호출별 p95를 서비스 SLA로 일반화하지 마. CPU 시간은 GPU 커널 시간이 아니야. `LogCursorMismatch`나 수집 오류가 있으면 누락 가능성을 표시해. 실행 중인 단계는 완료 시간으로 쓰지 마. 모델/데이터 캐시, 파일 크기/형식, 공개/loopback 경로, 클래스 설정, 코드 버전을 함께 적어.

## 원하는 산출물

1. **현재 배포 구조도**: 브라우저 / Vercel / Cloudflare 경유 구간 / 로컬 PC / AWS 경계를 표시한 Mermaid. 인증과 데이터 저장·GPU 연산을 연결선에 명시해.
2. **업로드→검색 준비, 씬 추론→결과 저장** 시퀀스 다이어그램 두 개. 원본 이동과 작은 작업 요청을 구분해.
3. **설계 결정 표**: 요구사항 → 선택 → 이점 → 대가 → 다른 선택으로 바꿀 조건.
4. **병목 근거 표**: 시험 조건, 단계, 측정값, 관련 로그 ID, 관측/추정/미측정, 다음 검증. 긴 단계와 개선 가능한 원인을 구분해.
5. **개선 우선순위**: 결과 재사용·캐시·SQL batch·S3 전송 순서·모델 중복 연산 등을 근거별로 평가해. 스레드 증가·GPU 교체를 먼저 정답으로 놓지 마. 구현된 것과 후보를 분리해.
6. **면접 설명**: 1분 요약과 예상 질문 5개. 무엇을 직접 구현·검증했고 무엇을 아직 못 했는지 솔직하게 써.

먼저 확인한 사실과 모르는 사항을 짧게 정리한 뒤 산출물을 만들어 줘. 기존 파일을 고치는 경우 현재 시험·배포를 건드리지 말고 문서 변경만 제시해. 키·쿠키·비밀번호·DB 덤프·원본 센서 파일을 출력하거나 외부에 올리지 마.
