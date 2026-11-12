# 혼합 배포 실행 준비

## 2026-11-12 Microsoft 비공개 터널

현재 운영 경로는 `Vercel → Microsoft Dev Tunnel → 127.0.0.1:4180 oauth2-proxy → Spring`이다. Cloudflare 발급 timeout/429가 반복되어 연결 방식을 변경했다. 기존 Cognito 팀 로그인은 유지하고 터널에는 익명 접근 권한을 주지 않는다.

- 공식 [Dev Tunnels CLI](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/get-started?tabs=windows) 1.0.2115를 `.local/tools/devtunnel.exe`에 설치하고 Microsoft Authenticode 서명을 확인했다. GitHub 로그인은 사용자가 직접 Authorize했다.
- 이미 만든 `ds2l-mvp.jpe1`과 HTTP 포트 4180을 재사용한다. `host-header`·`origin-header`는 unchanged, request timeout은 600초다. 터널 리소스의 만료 설정은 30일이며 없어진 터널을 스크립트가 자동 생성하지 않는다.
- `%LOCALAPPDATA%/DriveScene2Label/hybrid/tunnel.json`에는 provider·tunnelId·관찰한 origin만 둔다. 실제 값은 아래 형식이며 이 설정이 있는 PC에서 `scripts/hybrid.ps1`은 Microsoft 경로를 선택한다.

```json
{"provider":"microsoft","tunnelId":"<existing-id.region>","origin":"https://<assigned-host>-4180.<region>.devtunnels.ms"}
```

`scripts/hybrid/dev_tunnel.py`는 **connect 범위만** 가진 토큰을 발급한다. 보호된 `tunnel-token.json`과 Vercel production의 `BACKEND_TUNNEL_TOKEN` secret에 저장하고, CLI stdin으로 전달해 명령줄·로그에 값을 넣지 않는다. `frontend/vercel.json`의 **request.headers transform**이 업스트림 요청에만 `X-Tunnel-Authorization`을 설정한다. 응답 헤더·VITE 변수·정적 JS에 넣지 않는다. `env`는 transform에도 지정해야 한다.

토큰은 약 24시간 유효하다. 시작 시 잔여 6시간 미만이면 갱신하고 기존 production 소스를 재배포한다. 하루 이상 연속 실행할 때 자동으로 영구 갱신되는 구성은 아니다. 장시간 시험 전 `start`를 재실행한다. 터널·Vercel·AWS 공식 로그인 자체가 만료되면 해당 CLI 로그인을 갱신해야 한다. [Microsoft 토큰·보안 설명](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/security).

실제 검증: 터널 직접 익명 요청은 Microsoft 인증으로 이동, connect 토큰을 보낸 API는 기존 게이트웨이 JSON 401, Vercel API도 같은 JSON 401, `/oauth2/start`는 Cognito 302, 사용자 로그인 후 기존 10개 씬 표시 확인. 빈 401만으로 앱 로그인까지 도달했다고 판단하지 않는다. 초기화 뒤 공개 빈 씬 목록도 확인했다.

한 번의 `start`로 RDS available·Docker/GPU·S3 세션·쓰기 재개·Vercel READY까지 확인했다. 두 번째 연결 검사는 `already connected`로 재배포를 생략했다. EC2/ECS/EKS는 시작하지 않았다. 아래 11월 11일 Cloudflare·설치 준비 설명은 과거 단계의 기록이다.

기준: `release-version`, 2026-11-11. 구성은 **Vercel 프론트 + 로컬 Spring/FastAPI/GPU + S3 원본 + RDS DB**다. 최신 기능·검증 범위는 [11월 11일 MVP 갱신 기록](hybrid-mvp-update-2026-11-11.md)과 저장소 README를 기준으로 한다. 아래 초기 준비와 과거 연결 기록은 당시 상태를 보존한 것이다.

## 명령 하나로 기존 환경 시작

보호된 runtime 설정이 준비된 PC에서 `powershell -ExecutionPolicy Bypass -File scripts/hybrid.ps1 -Action start`를 실행한다. 기존 RDS 상태 확인·필요 시 시작, Docker Desktop 준비, GPU 확인, 컨테이너 재사용, 인증된 maintenance 해제, S3 세션 갱신, 터널 시작, Vercel 연결을 순서대로 처리한다. EC2·ECS·EKS나 새 RDS를 생성하지 않는다. 이미 실행 중인 컨테이너는 `--no-recreate`로 보존하므로 이미지·환경 변경 적용은 별도의 배포 절차로 수행한다.

Vercel 자동 연결에는 CLI 65.14.0과 최초 공식 로그인이 필요하다. Node가 PATH에 있는 셸에서 저장소 루트 기준으로 한 번 준비한다.

```powershell
npm install --prefix .local/tools/vercel-cli --no-audit --no-fund --ignore-scripts vercel@65.14.0
python scripts/hybrid/cloud.py vercel-login
```

AWS 세션 만료 시 `aws login --profile ds2l-seoul --region ap-northeast-2`를 실행한다. 비밀은 공식 CLI 사용자 저장소에 두고 토큰을 명령 인자나 Git에 넣지 않는다. Vercel 로그인 전에는 `-SkipVercel`로 로컬 기동까지만 실행할 수 있다. 대상은 기존 `leehyeoksu1/drivescene2label`, RDS `ds2l-hybrid-database`이며 계정·프로젝트가 다르면 변경을 중단한다.

Vercel 연결은 익명 API 401을 확인한 터널만 사용한다. 기존 production 소스를 새 주소로 재배포하며 작업 트리의 미검증 소스는 올리지 않는다. `.local/hybrid/vercel-connection.json`에 확인한 주소·배포 ID 또는 진행 중 배포 ID를 저장한다. 재시도는 진행 중 배포 확인을 이어가고, 확인된 연결이 그대로면 재배포하지 않는다. 로그인을 기다리는 동안 로컬 서비스는 계속 실행된다.

실제 RDS `available` 재사용과 로컬 시작을 확인했으며 세 컨테이너의 ID가 그대로 유지됐다. 운영 Python 검사 13개 통과. Vercel CLI 로그인 후 터널 연결 갱신→production READY→익명 API 401을 확인했고, 같은 명령의 두 번째 실행은 `already connected`로 재배포를 생략했다. CLI의 owner/배포 응답 구조를 검증하며 암호화된 환경 값을 URL로 비교하지 않고 메타데이터 fingerprint를 기록한다. 실제 RDS 중지→시작 시험은 사용자 데이터 이용을 중단하지 않도록 수행하지 않았다. S3는 켜고 끄는 인스턴스가 없고, 기존 `stop` 명령은 로컬 서비스만 중지한다.

## 최신 운영 설정

`scripts/hybrid.ps1 -Action start`는 보호된 `compose.env`에 로컬 운영 토큰을 준비하고 backend 기동 후 인증된 resume API를 호출한다. DB 스냅샷에 남은 `deployment_control.maintenance=true`를 명시적으로 해제하며, 실제 업로드 쓰기 경로가 검증 단계에 도달하는지 확인한다. `status`도 maintenance 상태를 출력한다. 일반 GET healthcheck만으로 쓰기 가능 상태를 판정하지 않는다. 현재 파일 형식은 ZIP·TGZ·TAR.GZ이며 공식 mini.tgz 재압축은 필요 없다.

앱 데이터 초기화와 백업 보존을 완료한 뒤 사용자의 새 업로드와 결과를 유지하고 있다. 현재 `UPLOAD_WORKER_ENABLED=true`, `EMBEDDING_INDEX_WORKER_ENABLED=true`, `AUTO_LABEL_WORKER_ENABLED=true`, `RECORDING_WORKER_ENABLED=true`로 운영한다. 업로드 dataset key/version에 맞는 RRD 생성을 지원하며 CLIP 실패만으로 recording을 차단하지 않는다. 예제 파일의 기본값은 복원 직후 기존 작업을 검토하도록 모두 false다.

업로드 ZIP·TGZ·TAR.GZ는 4MB 조각으로 전송하고 서버에서 비동기로 검증·등록한다. 원본 등록 후 검색 임베딩을 자동 생성하며, 진행률과 재시도를 씬 화면에서 제공한다. 자동 라벨 작업과 인덱스 생성은 같은 GPU 작업자를 공유해 동시에 실행하지 않는다. 완료된 신규 VESPA 작업에는 객체별 기준 프레임 후처리를 사용할 수 있다. 이전 캐시 없는 작업은 기본 라벨 생성부터 다시 수행해야 한다.

2026-11-11 20:37 KST 사용자가 공개 Vercel에서 전송한 `v1.0-mini.tgz` 4,168,148,189바이트가 S3 보관과 DB 등록까지 완료됐다. 데이터셋 #5, 10개 씬이며 카메라·GT 조회를 확인했다. 서버 로그 기준 압축 해제·검증 약 47.8초, S3 보관 약 358.1초, DB 등록 약 13.0초다. 전송과 등록, 검색 인덱싱, VESPA 라벨 생성은 서로 다른 단계다.

기존 모델 캐시는 `MODEL_CACHE_VOLUME=demo_model_cache`, `MODEL_CACHE_EXTERNAL=true`로 연결했다. 새 PC는 기본값 false로 자체 캐시를 만들면 된다. 재부팅 후 `scripts/hybrid.ps1 -Action start`를 실행하고 터널 주소가 바뀌면 Vercel의 `BACKEND_URL` 갱신과 재배포가 필요하다. `stop`은 로컬만 정지하며 RDS 과금은 계속된다.

## 준비한 파일

대용량 원본이 백엔드 PC에 있으면 `http://127.0.0.1:8080/uploads`에서 직접 업로드할 수 있다. 현재 Docker backend 이미지가 React 화면도 포함하며, 공개 Vercel과 같은 Spring·S3·RDS를 사용한다. 공개 프록시를 거치는 파일 전송만 생략한다. `compose.hybrid.yml`의 loopback 바인딩을 유지한다. 두 origin의 브라우저 업로드 기록은 공유되지 않으므로 이미 전송 중인 파일을 다른 주소에서 중복 업로드하지 않는다.

- `compose.hybrid.yml`: 로컬 backend·ai-server만 정의한 독립 Compose. DB 서비스·EC2·ECS·EKS를 생성하지 않는다.
- `.env.hybrid.example`: RDS·S3 설정 예제. 실제 `.env.hybrid`는 Git에서 제외한다. 필수 연결 값은 비워 두어 설정 전 기동을 막는다.
- `frontend/vercel.json`: `/api` 외부 전달, 정적 파일 우선 처리, SPA 새로고침 경로, API 응답 캐시 비활성화.
- `frontend/scripts/check-vercel-env.mjs`: 공개 HTTPS backend origin이 없는 Vercel 빌드를 실패시킨다. 인증과 실제 접속 가능 여부는 별도 검증해야 한다.
- `scripts/frontend.ps1`: Windows에서 프로젝트 전용 Node가 있으면 사용하고, 시스템 PATH 변경 없이 프론트 개발·검사를 실행한다.

기존 `compose.yml`은 전체 로컬 비교군으로 유지한다. 혼합 파일과 합쳐 실행하지 않는다. GPU 설정만 기존 `compose.gpu.yml`을 덧붙인다.

## 지금 실행할 수 있는 프론트

Node 기준 버전은 `frontend/.node-version`의 24.22.2다. 기존 일부 잠금 의존성(jsdom 등)은 Node 24.15.0 이상을 요구하므로 기존 시스템 Node 24.11.0으로 설치·테스트하지 않는다. 앱 의존성 버전은 바꾸지 않고 `engines` 표시만 실제 요구 범위에 맞췄다.

이번 PC에는 공식 배포본을 SHA-256 검증 후 `.local/tools/node-v24.22.2-win-x64`에 설치했다. 전역 Node 설치는 변경하지 않았다. 다른 PC에서는 같은 버전을 설치하거나 기존 버전 관리 도구를 사용한다.

저장소 루트의 PowerShell에서:

```powershell
powershell -NoProfile -File scripts/frontend.ps1 -Action dev
# http://localhost:5173

powershell -NoProfile -File scripts/frontend.ps1 -Action build
powershell -NoProfile -File scripts/frontend.ps1 -Action typecheck
```

처음 의존성을 설치하는 PC는 해당 Node가 PATH에 잡힌 터미널에서 `cd frontend; npm ci`를 먼저 실행한다. `frontend/.env.local`의 `API_PROXY_TARGET` 기본값은 `http://127.0.0.1:8080`이다. backend가 꺼져 있으면 화면은 열리지만 데이터 API는 실패하며, 가짜 데이터로 성공 처리하지 않는다.

## AWS 재개 전후의 경계

아래는 초기 준비 절차다. 2026-11-11 후속 승인으로 RDS·S3 연결과 Vercel 배포까지 진행했으며 최신 실행 상태와 재부팅 절차는 저장소 README의 **현재 MVP와 재부팅 후 재개**를 기준으로 한다. 기존 전체 AWS 시작 스크립트는 실행하지 않았다.

1. 기존 보존 원본과 DB 스냅샷을 확인하고 RDS 복원·접속 방식을 결정한다. 사설 RDS는 PC에서 닿는 VPN 등의 경로가 필요하다.
2. `.env.hybrid.example`을 `.env.hybrid`로 복사하고 실제 값을 편집한다. 이미 있는 환경 파일은 덮어쓰지 않는다.
3. JDBC URL에 `sslmode=verify-full&sslrootcert=/app/rds-ca.pem`을 유지한다. `/app/rds-ca.pem`은 기존 backend 이미지에 포함된다. `reWriteBatchedInserts=true`는 기존 batch 호출에만 영향을 주며 박스별 INSERT를 자동 배치화하지 않는다.
4. S3 전용 shared-credentials 파일의 절대 경로를 `AWS_SHARED_CREDENTIALS_HOST_PATH`로 지정한다. 컨테이너에는 읽기 전용 파일로 주입하며, 소스·프론트·이미지에 키를 넣지 않는다. 임시 자격 증명은 session token과 만료 후 갱신이 필요하다. SSO config만 마운트하는 방식은 이 설정에서 지원하지 않는다.
5. 아래 명령으로 구문과 기동 상태를 확인한다. `config` 원문에는 비밀번호가 포함되므로 `--quiet`을 사용한다.

```powershell
docker compose --env-file .env.hybrid -f compose.hybrid.yml -f compose.gpu.yml config --quiet

# 처음 빌드는 큰 PyTorch/CUDA 이미지와 라이브러리를 받을 수 있다.
# 실제 RDS/S3에 접속하고 앱을 시작한다. AWS 자원 자체를 생성하지는 않는다.
docker compose --env-file .env.hybrid -f compose.hybrid.yml -f compose.gpu.yml up --build -d
docker compose --env-file .env.hybrid -f compose.hybrid.yml -f compose.gpu.yml ps

# 컨테이너를 내려도 캐시는 보존한다. down -v를 사용하지 않는다.
docker compose --env-file .env.hybrid -f compose.hybrid.yml -f compose.gpu.yml down
```

복원 직후에는 두 worker가 기본 비활성 상태다. 기존 PENDING/RUNNING 작업을 검토하고 의도한 작업만 처리할 준비가 되면 `AUTO_LABEL_WORKER_ENABLED=true`, `RECORDING_WORKER_ENABLED=true`로 변경해 backend를 다시 적용한다. importer는 자동 실행하지 않지만 기존 Spring 설정대로 시작 시 Flyway migration은 실행되므로 검증용 복원 DB에서 먼저 확인한다.

S3 권한은 이 앱의 `uploads/` 경로에 필요한 읽기·쓰기·실패 업로드 정리 범위로 제한한다. 실제 정책과 버킷 암호화 키 권한은 AWS 재개 단계에서 확인한다.

## 캐시와 저장 공간

Compose 프로젝트 이름은 기본 `drivescene-hybrid`다. 업로드 데이터·모델·VESPA 결과·recording을 각각 Docker named volume에 보관한다. OneDrive 소스 폴더에 원본과 모델을 쌓지 않는다. 물리적 저장 위치·여유 공간은 Docker Desktop의 disk image 위치를 확인한다. WSL의 가상 최대 용량과 Windows 호스트의 실제 여유 공간은 다르다.

backend만 `/uploads`를 쓰고 AI는 읽는다. AI의 S3 복원은 비활성화해 읽기 전용 볼륨에 쓰려고 하지 않게 했다. 복원한 dataset의 첫 파일/상태 요청에서 backend가 ZIP 전체를 복원할 수 있으므로, 작은 상태 요청도 오래 걸릴 수 있다. 준비 작업을 별도 API로 분리하는 개선은 아직 미구현이다. 캐시가 준비된 뒤 상태를 다시 조회한다.

이 구성의 `nuscenes_data`는 빈 기본 데이터 볼륨이다. S3 업로드 방식(`storage_key=uploads`)의 데이터셋은 공유 업로드 캐시를 사용한다. 기존 DB에서 `storage_key=nuscenes`인 데이터셋을 쓰려면 실제 원본 root를 두 서비스의 `/data/nuscenes`에 읽기 전용으로 연결하는 별도 override가 필요하다. 빈 볼륨만으로 과거 모든 데이터셋이 복원됐다고 판단하지 않는다.

현재 S3 보관은 원본 ZIP 중심이다. `/results`와 `/recordings`는 로컬 보관이며 산출물 S3 업로드·캐시 자동 정리·씬 단위 다운로드·DB batch 저장 개선은 별도 작업으로 남아 있다.

## Vercel 연결

실제 배포 시 프로젝트 Root Directory를 `frontend`, Node.js major를 24.x로 지정한다. 환경변수 `BACKEND_URL`에는 로그인 보호가 있는 공개 HTTPS origin을 넣는다. 끝 `/`, `/api` 경로, query, 계정·비밀번호를 포함하지 않는다. Vercel build가 이 형식을 검사한다. 값은 `VITE_` 환경변수로 만들지 않는다.

Vercel의 `/api` 요청은 `${BACKEND_URL}/api`로 전달한다. 공개 주소는 localhost가 아니며 로컬 backend로 연결되는 HTTPS 터널/게이트웨이가 필요하다. 기존 AWS 로그인 보호는 자동 이전되지 않는다. 브라우저 로그인 callback·cookie·logout과 터널 직접 접근의 인증까지 확인한 뒤 공개한다. 단순 서비스 공통 키만으로 사용자 로그인을 대체하지 않는다.

API는 캐시하지 않고 기존 상태 polling을 유지한다. 정적 WASM/JS 파일은 filesystem 단계에서 제공한 뒤 `/scenes/...`, `/labels` 등의 SPA 경로를 index로 전달한다. 실제 배포에서 API 실패가 HTML 200으로 바뀌지 않는지, Rerun WASM 응답과 새로고침을 확인해야 한다. [Vercel routing 설정](https://vercel.com/docs/project-configuration/vercel-json), [외부 rewrite 캐시](https://vercel.com/docs/routing/rewrites)

4MB 조각 전송·진행 저장·같은 파일 재선택 시 재개·비동기 등록을 구현했고, 실제 공개 경로에서 정상 TGZ 약 4.17GB 등록을 확인했다. S3 직접 multipart 방식은 아니다. 과거 4.34GB ZIP의 관리자 터널 경로 검증과 이번 TGZ 공개 경로 검증은 파일과 경로가 다르다.

## 이번 검증 기록

- `git pull --ff-only origin release-version`: 이미 최신, `a022707`.
- Windows 호스트: RTX 5060 Ti 16GB, WSL2 확인. C드라이브 여유 약 146GiB(확인 시점).
- Docker Desktop 엔진 28.5.1 시작·연결 확인.
- 이미 설치돼 있던 `drivescene2label-ai-server:latest`에서 네트워크 없이 PyTorch 2.14.1 / CUDA 13.0의 작은 GPU 연산 통과. 새 commit 이미지 빌드나 실제 VESPA scene 성능 검증은 아니다.
- Node 24.22.2에서 `npm ci`: 잠금 파일 기준 의존성 설치 완료.
- `scripts/frontend.ps1 -Action build`: TypeScript 검사 + Vite 제품 빌드 통과. Rerun WASM 자산 생성 확인.
- `scripts/frontend.ps1 -Action test`: 기존 8개 파일, 67개 테스트 통과. 실제 AWS·브라우저 통합 시험은 아니다.
- 혼합 Compose + GPU override: 가상 연결 값으로 구성 검사 통과. backend·AI 2개 서비스만 존재하고 DB 서비스 없음, backend loopback bind, AI 호스트 포트 비공개 확인. 실제 credentials 내용은 사용하지 않았다.
- 기존 전체 로컬 Compose + GPU override도 구성 검사 통과.
- Vercel 공식 JSON schema의 구성 필드 검증 통과, HTTPS origin 검사 8개 사례 통과. 공개 배포에서의 라우팅·인증은 아직 미검증이다.
- `.env.hybrid`, `frontend/.env.local` 생성 및 Git 제외 확인. 실제 RDS·S3 자격 증명은 비워 두었다.
- 로컬 Vite 개발 서버 `http://localhost:5173/` 시작, `/`와 `/scenes/1`의 앱 HTML 응답 HTTP 200 확인. backend 데이터 연결 확인과는 구분한다.

위 목록은 초기 준비 시점의 검증이다. 후속 실행 결과는 아래와 같다.

## 2026-11-11 실제 연결·배포와 재개 지점

- Vercel 팀 `leehyeoksu1`, 프로젝트 `drivescene2label`, 공개 주소 https://drivescene2label.vercel.app. 배포 `dpl_HBed5yfqkoFjFo7di87sG5LLxWKa`가 READY다. 소스 파일로 배포했고 Git 자동 배포는 연결하지 않았다.
- AWS 계정 `189750306426`, 서울. `ds2l-20261109-143942-4b42e21f`에서 `ds2l-hybrid-database`를 PostgreSQL 16.15 / db.t4g.small / 20GiB gp3 / Single-AZ로 복원했다. 7일 백업·삭제 보호를 설정했다.
- 공개 RDS endpoint를 사용하지만 전용 SG `ds2l-hybrid-local-db`는 승인된 현재 PC IPv4 /32 TCP 5432만 허용한다. 기존 `rds.force_ssl=1` parameter group과 JDBC `verify-full`을 적용했다.
- Spring 기동에서 RDS 연결, Flyway 기존 v8 검증·변경 없음, `/api/datasets`의 4개 데이터셋 응답을 확인했다. 실제 mini는 #4다. 원본 S3 ZIP 다운로드·카메라 검증은 아직 남아 있다.
- S3 역할 `ds2l-hybrid-storage`는 기존 버킷 `uploads/*` Get/Put/Delete와 해당 prefix List만 허용한다. 로컬 로그인 역할만 assume할 수 있다. `scripts/hybrid/refresh-s3-session.py`가 1시간 STS 세션을 40분마다 갱신하고 Java SDK는 `credential_process`로 읽는다. 로그인 만료 시 `aws login --profile ds2l-seoul`을 다시 실행해야 한다.
- 비밀 설정은 `%LOCALAPPDATA%/DriveScene2Label/hybrid`의 `compose.env`, `auth.env`, `aws/`에 저장하고 현재 Windows 사용자·SYSTEM으로 접근을 제한했다. 해당 파일을 Git/OneDrive/로그에 복사하지 않는다. 최초 DB 비밀 해석에는 AWS Secrets Manager skill의 `asm-exec` 동적 참조를 사용했다. 구형 MCP 도구명을 보정하는 로컬 어댑터는 `.local/hybrid/asm-exec-current.py`에 보존했다.
- `compose.hybrid-auth.yml`의 oauth2-proxy가 기존 Cognito `team` 그룹을 검사한다. 새 앱 클라이언트에 managed login branding도 설정했다. [AWS 공식 동작 설명](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-managed-login.html).
- 공개 홈페이지 200, Vercel `/oauth2/auth`와 터널 직접 `/api/datasets`의 비로그인 401을 확인했다. 사용자 계정 로그인·callback·실데이터 화면 검증은 아직 남아 있다.
- 모델 캐시 `demo_model_cache` 약 8.1GB를 재사용한다. 새 로컬 GPU 이미지 빌드는 끝났지만 Windows `nvidia-smi`가 `GPU is lost`를 반환해 GPU 컨테이너 시작이 실패했다. 사용자 요청으로 재부팅 후 재개한다. GPU 추론 성공으로 보고하지 않는다.
- 새로운 로그인 gate를 포함한 프론트 빌드와 71개 테스트가 통과했다. 기존 결과 저장·편집 통합 테스트를 이번 배포에서 재실행한 것은 아니다.
- `scripts/hybrid.ps1`은 이미 준비된 PC에서 start/status/stop을 지원한다. GPU 장애 중 `-WebOnly`는 backend·auth만 시작한다. 스크립트는 AWS 컴퓨팅 자원을 생성하거나 켜지 않는다. 로컬 stop으로 RDS가 정지되지는 않는다.
- Cloudflare Quick Tunnel은 재시작 시 주소가 바뀔 수 있다. 새 주소로 Vercel `BACKEND_URL`을 수정하고 재배포해야 한다. `VITE_AUTH_REQUIRED=true`를 유지한다. named tunnel·고정 도메인·자동 갱신은 후속 개선이다.
- release-version push는 CI만 실행하고 기존 ECS/EKS 배포 workflow는 수동으로만 실행한다. 원격 push는 사용자가 별도로 승인했다.

재개 순서: GPU 정상 인식 → Docker·AWS 로그인 확인 → 로컬 start → 터널 주소 갱신·Vercel 재배포 → 팀 로그인 → S3 원본 준비·기존 결과/수정본 검증 → 복원 중인 작업 상태를 검토한 후 필요한 worker 활성화. 현재 worker는 모두 꺼져 있다.
