# 2026-11-11 혼합 MVP 기능 보완

구성: Vercel 프론트 → Cloudflare HTTPS → 로컬 Cognito 게이트웨이 → 로컬 Spring/FastAPI/RTX 5060 Ti. S3는 원본 ZIP/TGZ, RDS는 카탈로그·임베딩·작업·라벨을 저장한다. EC2/ECS/EKS를 시작하지 않는다.

## 20시 업로드 장애 수정과 TGZ 지원

아래 초기 배포의 GET healthcheck와 빈 씬 화면 확인은 쓰기 가능 여부를 검증하지 못했다. 실제 업로드에서 별개의 두 문제가 확인됐다.

1. `deployment_control.maintenance=true`가 이전 종료 기록에서 남아 POST 요청을 503 `Environment is stopping…`으로 차단했다. 이 앱 메시지를 처음에 작업 환경 종료로 잘못 해석했다. 해당 플래그만 해제했으며 기존 데이터·계정·S3를 다시 초기화하지 않았다. 재부팅 시작 스크립트는 보호된 로컬 운영 토큰으로 resume를 호출하고, 데이터를 만들지 않는 잘못된 업로드 요청이 400 검증 응답에 도달하는지 확인한다.
2. 사용자가 만든 `v1.0-mini.zip`은 601,354,240바이트이며 ZIP 최종 디렉터리가 없었다. 공개 경로로 수신한 파일과 로컬 원본 모두 같은 문제다. 업로드 `43905fab-9162-496d-8430-9d63ecdb4ba5`를 새 코드로 재검증해 `EXTRACTING` 단계의 `java.util.zip.ZipException: zip END header not found`를 기록했다. 이 실패로 새 데이터셋은 등록되지 않았다.

파일 확장자만 바꾸거나 다시 압축할 필요가 없도록 `.zip`, `.tgz`, `.tar.gz`를 지원한다. 실제 헤더로 형식을 판별하고, ZIP 최종 디렉터리와 gzip footer를 확인한다. TAR 링크·특수 파일·경로 이탈·중복 파일, 100,000개 항목 초과, 8GiB 압축 해제 한도를 차단한다. S3와 원본 다운로드에는 업로드한 압축 바이트를 그대로 보관한다. 기존 ZIP과 새 TAR.GZ 캐시 복원을 모두 지원한다. 서버 로그는 작업 UUID·단계·크기·형식과 원래 예외를 남긴다.

보관 중인 공식 `v1.0-mini.tgz`는 4,168,148,189바이트다. 전체 스트림을 읽어 gzip CRC/footer, TAR 31,253개 항목, 압축 해제 파일 합계 5,374,922,749바이트, 10개 씬 메타데이터를 확인했다. 이는 파일 검사이며 운영 RDS 등록 성공을 뜻하지 않는다. 브라우저 파일 선택 자동화는 확장 기능의 로컬 파일 접근 제한에 이어 Windows에서 현재 URL을 확인하지 못해 중단됐다. **정상 TGZ 전체의 공개 브라우저 전송·씬 등록은 아직 미검증이다.**

수정 후 검증: 백엔드 관련 11개, 프론트 전체 77개 및 제품 빌드, AI 업로드 계약 19개, 운영 스크립트 3개와 PowerShell 구문 검사 통과. TAR FIFO 허용을 잡아낸 회귀 테스트는 일반 파일·폴더 형식만 명시적으로 허용하도록 수정한 뒤 통과했다. 로컬 backend/AI를 새 이미지로 시작했고 maintenance=false와 실제 쓰기 검증 경로를 확인했다. Vercel `dpl_G6drXnnoLmtD4RRXZFoMoBh9xZ6S` READY 및 공개 화면의 TGZ 안내를 확인했다. 아래 초기 배포 기록과 테스트 수는 해당 시점의 이력이다.

## 데이터 초기화

사용자가 앱 데이터 전체 초기화, S3 원본과 DB 백업 보존을 승인했다. 기존 데이터셋 4개, 씬 13개, sample 445개, sensor file 34,183개, GT 23,239개, 라벨 작업 2개, 예측 983개, 라벨 문서 5개/수정 이력 11개를 비웠다. `system_instance`, `deployment_control`, Flyway 이력과 계정을 유지했다. ID 시퀀스를 되돌리지 않아 옛 브라우저 작업 기록이 새 작업과 충돌하지 않는다.

삭제 직전 custom-format PostgreSQL 덤프 10,820,956바이트를 `%LOCALAPPDATA%/DriveScene2Label/hybrid/pre-app-reset-20261111-184231.dump`에 저장하고 `pg_restore --list`로 카탈로그를 확인했다. SHA-256은 `7b3ae16c4ef60b0e457feed93b8b1e9c075d2d4ce3e10e054c62a3c155aa7d56`이다. 이번 덤프의 실제 복원 시험은 하지 않았다. 기존 RDS 스냅샷과 S3 원본 및 로컬 원본 캐시는 보존했다.

## 업로드

기존 단일 요청 업로드는 대용량 ZIP을 프록시에 통째로 통과시켰다. [Cloudflare 요청 크기 제한](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/) 때문에 공개 경로의 4GB 파일은 단일 요청 방식으로 처리할 수 없다.

브라우저는 4MB 초과 파일을 4,000,000바이트 조각으로 Spring에 보낸다. 서버는 UUID 세션별 파일에 순서대로 쓰고, 같은 조각 재전송은 바이트가 같을 때만 허용한다. 전송 완료 후 별도 업로드 작업자가 ZIP 검증·S3 보관·메타데이터 등록을 수행하므로 긴 처리 시간 동안 프록시 요청을 잡아 두지 않는다. 상태와 진행 바이트는 DB에 보존하고, 같은 파일의 브라우저 재선택 시 이어서 전송한다. 브라우저 저장소에는 세션 식별자와 작은 파일 지문만 보관한다.

원본 전송·등록은 로컬 디스크와 네트워크를 사용한다. 파일 합치기, 보관 ZIP, 압축 해제본이 함께 존재할 수 있어 업로드 전에 원본 2배+9GiB의 여유 공간을 검사한다. 실패/중단 세션의 원본 조각은 재시도용으로 남는다. 무기한 서비스 운영을 위한 보관 기한·정리 정책과 S3 직접 multipart 업로드는 후속 범위다. 운영 구성은 로컬 Spring 한 인스턴스와 공유 Docker 볼륨을 전제로 한다.

## 검색

종전 `ImageEmbeddingService`는 `nuscenes` root만 허용하여 업로드 데이터 인덱싱이 막혀 있었다. 이제 서버가 확인한 업로드 UUID와 상대 경로를 내부 AI 요청에 전달한다. AI는 공유 캐시 내부의 실제 파일만 읽으며 경로 이탈·심볼릭 링크 이탈을 차단한다. 데이터셋별 카메라 키프레임을 비동기로 인덱싱하고 현재 모델·전처리로 이미 저장한 벡터는 건너뛴다. 실패 시 진행분을 유지한 채 재시도한다.

GPU 작업은 같은 scheduler에서 검색 인덱싱 8장 단위와 VESPA 작업을 순서대로 처리한다. 인덱싱 중 일부 이미지로 검색할 수 있더라도 화면에 전체 대비 완료 건수를 표시한다. 검색 점수는 확률이 아니며 검색 정확도를 정량 평가한 것은 아니다.

## 객체 기준 후처리

팀이 추가한 `main_pseudo_vlm_scene_ver2.py`와 `src/postprocess/rigid_tracklet.py`를 로컬 web runner에 연결했다. 외부 VESPA checkout 파일은 수정하지 않는다. 기본 실행에서 tracklet을 만든 뒤 yaw/size heuristic까지 적용한 상태를 서버 전용 캐시에 저장한다. 이 캐시는 버전·씬·데이터 경로·버전·클래스 모드·SHA-256을 확인한 뒤만 읽고 업로드 파일을 pickle로 읽지 않는다.

UI는 현재 프레임의 T번호와 sample token을 기준으로 보정을 요청한다. 서버는 해당 원본 작업의 실제 예측 박스에 그 track/frame이 존재하는지 검증한다. 원본과 같은 씬·데이터셋·classMode의 새 작업을 만들고 `source_job_id`, `reference_frames`를 기록한다. Idempotency-Key가 같아도 원본이나 기준이 다르면 409다. 같은 요청의 재전송은 같은 작업을 반환한다.

후처리 실행은 보존된 중간 상태에 같은 `propagate` 및 filtering/label mapping을 적용한다. 단계 01~07과 Grounding DINO/SAM을 다시 실행하지 않는다. 새 보정 상태도 별도 캐시에 보관하므로 다음 보정은 그 결과를 이어서 사용할 수 있다. 원본 geometry·캐시·작업은 바꾸지 않는다. Rerun exporter의 업로드 데이터 지원은 이번 범위에 포함하지 않는다.

## GPU와 검증 범위

Windows 이벤트 153에서 `BusReset TDR occurred on GPUID:2d00`가 16:45와 18:10에 확인됐다. 이는 NVIDIA Xid 153 판정이 아니다. 사용자는 케이블·전원 조작이나 절전 없이 사용 중 발생했다고 설명했다. 18:36 재부팅 후 GPU 인식, 작은 CUDA 연산, 실제 CLIP 이미지 임베딩과 검색을 확인했다. 드라이버 설치·삭제·레지스트리 변경은 하지 않았으며 원인은 아직 미확정이다.

혼합 구성에서 `AI_REQUIRE_GPU=true`를 사용한다. 짧은 NVML 조회가 실패하면 검색/VESPA 준비 상태를 `GPU_UNAVAILABLE`로 반환하고 새 GPU 추론을 막는다. 프로세스 생존과 GPU 연산 가능 여부를 구분한다.

검증: 백엔드 전체 49개, 프론트 75개, AI 계약 42개 및 GPU 감지 검사. AI 체크섬 fixture는 Windows CRLF가 아닌 Git의 LF 복사본에서 실행했다. 실제 VESPA 환경의 작은 CPU fixture로 기준 없는 결과 일치, 기준 크기/yaw 적용, 바닥 중심 보존, 원본 캐시 보존, 검출 단계 재실행 없음을 확인했다. 별도 테스트 DB에서 보존된 실제 카메라 이미지 한 장을 GPU로 임베딩하고 자연어 검색 결과 1건을 확인했다. 운영 앱에 테스트 데이터셋을 다시 등록하지 않았다.

미검증: 4.34GB 전체 파일의 공개 HTTPS 브라우저 전송, 이번 버전의 전체 nuScenes 씬 GPU 추론과 검출 정확도, 장시간 eGPU 안정성. 단위/계약 검증을 전체 씬 성공으로 해석하지 않는다.

## 배포와 브라우저 확인

Vercel 배포 `dpl_K6GMF3QaMQuPEWLAr61Ch9Q8KRSh`가 READY이며 `https://drivescene2label.vercel.app`에 반영됐다. 기존 로그인 세션의 브라우저에서 새 업로드 안내, 등록된 데이터셋 없음, 저장한 라벨 없음 상태를 확인했다. 로컬 backend/AI가 healthy이고 CLIP은 cuda/READY다. 기본 데이터 root는 비어 있으므로 데이터셋 선택 전 VESPA가 UNAVAILABLE인 것은 전체 GPU 실패 판정이 아니다. 업로드 데이터셋별 준비 상태로 판단한다.

별도 로컬 테스트 DB/저장소에서 Playwright 브라우저로 110,011,841바이트 합성 ZIP을 4,000,000바이트 offset 간격의 28개 요청으로 등록했다. 서버 원본 다운로드의 SHA-256 `3d81f3613123decec9e13903ac3f7f98f17599907cd42e75009d59fb058d4990`이 입력과 일치했고 브라우저 오류는 없었다. 이는 실제 브라우저·Spring·PostgreSQL 통합 검증이며 Cloudflare/Vercel 전송 한계나 실제 센서 정확도 검증은 아니다. 운영 RDS와 S3에 테스트 원본/라벨을 다시 쓰지 않았다.

현재 보호된 로컬 환경에서 업로드·이미지 인덱스·자동 라벨 worker를 켰고 recording worker는 꺼 두었다. EC2 조회에 실행/정지 인스턴스가 없음을 재확인했으며 EC2/ECS/EKS 기동 명령은 실행하지 않았다. README에는 재부팅 후 터널 주소 갱신, AWS 로그인 만료, 로컬 공간과 RDS 과금 조건을 기록했다.
