# 수동 시험을 위한 hybrid 재배포 — 2026-11-18

[배포·HTTP·실행 설정 증거](evidence/hybrid-ready-2026-11-18/release-summary.json) · [CI 실패/재실행 단계](evidence/hybrid-ready-2026-11-18/ci-retry-jobs.json)

사용자가 선택한 **로컬 GPU·백엔드 + AWS RDS·S3 + Vercel** 구조를 유지한다. 이전 “시험 후 AWS 중지” 요청 이후 사용자가 직접 전체 사이클을 시험하도록 재배포를 요청했으므로, 이번에는 서비스가 준비되면 켜둔다. EC2/ECS/EKS는 시작하지 않았다.

## 적용한 코드와 판단

프론트·AI 기준 커밋은 `132669a1f78237c9c87c6c3905d1baa121d1ed4c`다. 이후 CI에서 발견한 S3 취소 경합을 수정해 **18:56 KST 백엔드만 교체**했다. 검증한 이미지와 실행 이미지가 `sha256:2a7480b0eef5f25bba7f5845f2036745b92a1798209eee2e0e121155019a12db`로 일치한다. [후속 코드 스냅샷·65개 회귀·실제 S3 7케이스·배포 증거](evidence/s3-interruption-2026-11-18/README.md). AI 시작 시각은 그대로이고 앱 데이터를 다시 초기화하지 않았다.

| 영역 | 적용 | 보류·이유 |
|---|---|---|
| Grounding DINO | G2 이미지 전처리 재사용 | 클래스 forward 자체의 병합·새 모델은 적용하지 않음. 앞선 전체 씬의 234검출/1,308박스 일치가 근거 |
| CPU·정밀도·엔진 | 기존 스레드 1, FP32/PyTorch | 스레드 2·AMP/TF32는 출력 차이, Flash/SDPA는 현재 attention 미지원, TRT는 전체 클래스/3D 회귀 미검증 |
| CLIP/RDS | C1 Source prefetch, Q2 exact SQL/custom plan, Q3 동일 문장 LRU/single-flight | approximate HNSW, Q4 카메라 metadata 묶음·Q5 라벨 batch는 별도 품질/트랜잭션 검증 필요 |
| Java S3 | 완전한 다운로드만 게시, 실패/취소 확인, 제한된 업로드·계측 | multipart는 편차가 있어 false. 활성화하더라도 최대 4파트·1GiB 초과. 작은 파일에는 단일 PUT |
| 인프라 | 기존 S3/RDS, 검증된 캐시 보존, 미완료 파트 lifecycle | Spark/Kafka/Elasticsearch는 해당 압축 파일 전송·모델 forward를 직접 줄이지 않아 추가하지 않음 |

각 원인·코드·전후 로그는 [기존 통합 결과](optimization-results-2026-11-18.md), [쿼리/서빙 후속](optimization-resume-2026-11-18.md), [Java S3](s3-java-optimization-2026-11-18.md)를 따른다. 이전과 같은 GPU 품질 비교를 이번 재부팅 후 다시 실행한 것으로 표시하지 않는다.

## 앱 초기화와 복구 경로

실행 도구는 [reset_app_data.py](../scripts/hybrid/reset_app_data.py)다. 기본 실행은 읽기 전용 계획이며 `--apply`에서도 백업/복원 검증이 통과해야 초기화한다. 기존 backend·AI를 중지하고 maintenance=true 상태에서 실행했다.

- private custom-format dump **91,953,796 bytes**, SHA-256 `dc708602c4f4680e964ded3e8da07c346aca2d4cab2d0a441b40f4fe79ca7f72`.
- 보호된 PC 경로: `%LOCALAPPDATA%/DriveScene2Label/hybrid/pre-app-reset-20261118T090813Z.dump`. Git이나 공개 S3로 올리지 않았다.
- 외부 네트워크/포트가 없는 임시 PostgreSQL에 `pg_restore --exit-on-error --no-owner --no-acl`로 실제 복원했다. **33테이블의 행 수·정렬된 행 내용 digest와 22시퀀스 값이 일치**했다. dump 파일 자체는 저장 후 SHA-256 재검증했다.
- 허용 목록의 앱 테이블 **30개**만 명시하여 `TRUNCATE ... CONTINUE IDENTITY RESTRICT`를 사용했다. system_instance·deployment_control·Flyway 이력 3개를 보존한다. 미검토 테이블이나 외부 FK가 생기면 실행을 거절한다.
- dataset **16→0**, scene **56→0**, embedding **13,434→0**, 작업 **7→0**, 예측 **2,616→0**, recording **6→0**. 다른 앱 테이블도 0을 확인했다.
- **S3 원본 26개 key·size·ETag가 전후 동일**하다. Cognito 계정·모델·로컬 원본/해제 캐시·기존 결과 볼륨은 보존했다. 과거 결과 파일은 복구 자료로 남지만 DB에서 제거되어 새 앱 목록에 표시되지 않는다. ID 시퀀스를 되돌리지 않아 과거 job/dataset ID와 새 작업이 충돌하지 않는다.

[초기화 결과](evidence/s3-java-2026-11-18/app-reset/report.json), [실제 복원 검증](evidence/s3-java-2026-11-18/app-reset/restore-validation.json). 복구가 필요하면 먼저 쓰기를 멈추고 이 dump를 별도 DB에 복원해 검증한 뒤 선택적으로 가져온다. 새 사용자 데이터가 생긴 DB에 무조건 덮어쓰는 복원 명령은 실행하지 않았다. [PostgreSQL pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html).

## 재부팅 이후 검증

backend·AI 이미지를 재빌드하고 인증 컨테이너와 함께 재생성했다. RDS available, maintenance=false, 모든 작업 worker 활성 상태에서 데이터 목록 `[]`, 실행 작업 0을 확인했다. 작은 CUDA 행렬 계산이 성공했고 CLIP은 CUDA READY였다. 보존된 실제 업로드를 **읽기만 하는** capability refresh에서 VESPA runtime·recording READY를 확인했다.

고정 `/data/nuscenes` 볼륨에는 기본 데이터셋이 없어 일반 `/health`의 VESPA 필드가 `not_configured`로 표시될 수 있다. 업로드 데이터셋 범위로 점검하면 READY이며, 초기화 후 임의의 데이터셋을 다시 등록해 상태를 꾸미지 않았다. 이 점검은 전체 모델 inference/3D 품질 재검증과 다르다.

## 직접 시험과 로그

[서비스](https://drivescene2label.vercel.app)에서 기존 팀 계정으로 로그인 → `/uploads`에서 nuScenes `.tgz`/`.zip` 업로드 → CLIP 완료 확인 → 검색 → 씬 선택 → **라벨 생성하기**를 누른다. 업로드 자체로 라벨링을 자동 실행하지 않는다. 새 사용자 시험은 아직 시작하지 않았다.

새 수집기 폴더는 `.local/hybrid/measurements/20261118T091728Z/`이며 `report.md`, `report.json`, `events.jsonl`을 30초마다 갱신한다. 최대 48시간 또는 stop marker까지 동작한다. PC 재부팅으로 종료되면 다시 시작해야 한다. 공개 Vercel 주소/127.0.0.1 중 어느 경로로 올렸는지와 다른 동시 작업 여부도 기록한다. GPU·S3·DB의 중첩 구간을 더해 전체 시간으로 계산하지 않는다.

수집 시작 뒤 백엔드 이미지 변경 시각은 같은 폴더의 `deployment-transitions.jsonl`에 별도 기록했다. 초기 manifest의 git_revision을 덮어쓰지 않았다. 18:56 KST 재시작 구간의 관측은 사용자 업로드 성능 측정과 구분한다.

이번 S3 전후 보고서는 `.local/hybrid/experiments/20261118T072013Z-s3-java/review/report.md`, Git 검토용은 [report.md](evidence/s3-java-2026-11-18/review/report.md)다. 새 사용자 시험 로그와 과거 비교 실험을 섞지 않는다.

최종 해시 검토에서 검토용 원본 manifest와 내보내기 인덱스의 이름 충돌을 발견해 복구했다. 실험 원본은 그대로이며 85개 파일의 원래 export hash가 모두 일치한다. 같은 실수를 예방하는 예약 이름·중복 경로 검사를 추가했고, 로컬 hybrid 테스트는 최종 **49개 중 47개 통과·게이트웨이 통합 2개 제외**다. 제외된 통합은 Linux CI 실행으로 따로 확인한다.

## 공개 배포 검증 기록

**2026-11-18 18:34 KST 공개 HTTP 확인 완료.** Vercel API/CLI의 첫 배포가 `BLOCKED`였던 이유는 기존 프로젝트 pause였다. 첫 CI는 backend·frontend 테스트 후 Docker 의존성 다운로드에서 Maven Central HTTP 429로 실패했고, 실패한 job 재실행에서 **전체 성공**했다. 실패 로그도 보존한다.

| 확인 | 결과 |
|---|---|
| 코드 CI | [44274257190](https://github.com/DriveScene2Label-Team/DriveScene2Label/actions/runs/44274257190), attempt 2 success |
| production 배포 | `dpl_EJu2CKzqfcF81W3x3ETmJfPbZLBk`, **READY**, Vite, 빌드 약 30.3초 |
| 배포 코드 | `132669a1f78237c9c87c6c3905d1baa121d1ed4c`, 공개 도메인의 배포 ID와 일치 |
| 공개 페이지/스크립트 | `/`, `/uploads`, HTML의 script asset HTTP 200 |
| 공개 API | `/api/datasets`, `/api/system/status` 익명 HTTP 401 `{}`, private/no-store |
| 로그인 진입 | `/oauth2/start` HTTP 302, 기존 서울 Cognito 도메인으로 이동 |
| 운영 상태 | 프로젝트 `paused=false`, RDS available, backend·AI·인증 서비스 실행, maintenance=false, 실행 작업 0 |
| 새 사용자 데이터 | backend 목록 `[]`; 사용자 업로드/임베딩/검색/라벨링은 아직 시작하지 않음 |

프로젝트의 `live=false` 필드는 pause 상태 판정에 사용하지 않는다. CLI의 실제 `paused=false`와 공개 HTTP/배포 ID로 확인했다. Git 자동 배포는 false를 유지하며, 다음 Start가 같은 터널에 대해 불필요한 재배포를 하지 않도록 연결 기록을 갱신했다.

위 표는 최초 18:34 배포의 기록이다. 후속 문서 커밋 `11cde64`의 CI에서는 S3 취소 테스트 실패를 발견했고, 소스가 같다는 이유로 무시하지 않고 동시성 경계를 수정했다. 수정 이미지의 정상 2건·장애 5건 및 65개 Java 회귀가 통과한 후, maintenance에서 업로드·임베딩·라벨·recording·활성 쓰기 0을 확인해 백엔드만 교체했다. **18:57 KST** 공개 200/401/302, 내부 인증 프록시의 backend 목록 조회 200·데이터셋 0, maintenance=false를 재확인했다. [HTTP 재검증](evidence/s3-interruption-2026-11-18/public-http-verification.json). 후속 소스의 전체 CI 상태는 [release-version CI](https://github.com/DriveScene2Label-Team/DriveScene2Label/actions/workflows/ci.yml?query=branch%3Arelease-version)에서 커밋별로 확인할 수 있다.

**실제 로그인한 브라우저 화면은 이번에 검증하지 못했다.** Computer Use가 현재 Windows 브라우저 URL을 확인할 수 없다고 자동 조작을 중단했고 이후 브라우저 입력을 하지 않았다. CI의 fixture 브라우저 흐름 성공과 실제 공개 로그인 후 전체 사이클을 구분한다. 사용자가 직접 위 순서로 수행하면 새 수집기 폴더에 로그가 쌓인다.

로컬/GPU/RDS와 공개 연결은 **켜둔 상태**다. 시험 UUID 객체·버전·미완료 파트와 전용 컨테이너/볼륨은 정리했다. Windows 호스트의 남은 C: 공간은 약 29.6GiB였으며, Docker 내부 가상 디스크 표시만으로 실제 호스트 여유를 판단하지 않았다. 기존 로컬 캐시/결과를 임의로 지우지 않았다.
