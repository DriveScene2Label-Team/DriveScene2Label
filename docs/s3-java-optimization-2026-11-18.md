# S3 Java 원본 보관·복원 비교 — 2026-11-18

[검토용 로그·해시](evidence/s3-java-2026-11-18/README.md) · [자동 생성 report.md](evidence/s3-java-2026-11-18/review/report.md)

## 문제와 검증 경계

기존 `UploadArchiveStore.put()`은 최대 5GB 압축 파일을 단일 `PutObject`로 보관한다. Python SDK S2 시험에서 병렬 업로드가 빨랐지만 Java SDK·HTTP 클라이언트·파일 크기가 달라 운영 코드의 개선 근거로 바로 사용할 수 없다. 큰 파일에서 전송 연결을 병렬로 사용하면 빨라지는지, 실패할 때 부분 객체·파트·로컬 파일을 남기지 않는지를 별도로 검증한다.

이번 시험은 **실제 운영 Java 메서드 → 서울 S3 → 새 로컬 캐시 → 압축 해제** 경계다. 브라우저 업로드·Cognito·RDS import·CLIP·3D 모델 실행 시간을 포함하지 않는다. 기존 전체 서비스 사이클 A1과 구분한다. 시험 컨테이너에는 GPU·RDS 접근을 부여하지 않고 원본 볼륨은 읽기 전용으로 연결했다. 재부팅 후 비교 중에는 별도로 사용자가 요청한 배포를 위해 RDS를 시작하고 읽기 전용 DB 초기화 계획을 조회했다. 원본 manifest의 `RDS ... stopped` 문구는 후속 배포 준비 상태를 반영하지 못하므로 이 제한과 부가 기록을 함께 따른다.

앞선 Python S2와 이번 Java는 실행 환경·파일 위치·시각도 다르다. 두 실험의 절대 시간을 언어 교체 효과로 비교하지 않는다. 동일 Java 실행 환경에서 순서를 바꾼 비교만 채택 판단에 사용한다.

## 구현과 도구 선택

- AWS SDK Java **2.57.11**, Java 21과 기존 `UrlConnectionHttpClient`를 유지한다. Netty/CRT/새 서빙 인프라는 추가하지 않는다.
- 후보는 64MiB를 넘는 파일을 16MiB 파트로 나누고 **최대 4개** 요청만 동시에 처리한다. 한 `UploadArchiveStore`에서 압축 파일 하나만 업로드하도록 제한하여 동시 작업 수와 파트 수가 곱해지는 것을 막는다. 이는 프로세스 단위 제한이며 여러 서버 전체의 전역 제한은 아니다.
- 위 64MiB는 비교·장애 시험에서 경로를 강제하기 위한 기준이다. 최종 설정의 기본 크기 기준은 **1GiB 초과**다. 109.7MB의 느려진 multipart 경로를 피하는 보수적인 분리이며, 모든 중간 크기를 측정해 찾은 최적 임계값은 아니다. 측정 당시 Java·컨트롤러 소스와 SHA를 별도로 보존했다. 파트 전송 알고리즘은 유지하고 분기 기준만 설정으로 분리한다.
- 각 파트는 파일의 정해진 구간을 다시 열 수 있는 스트림이다. 파일 전체나 파트 전체를 메모리에 올리지 않는다. SDK 재시도 때 같은 구간을 다시 전송한다. CRC32 파트 checksum과 전체 파일 SHA-256 왕복 검증을 구분한다. multipart ETag를 파일 MD5로 해석하지 않는다.
- 실패하면 이미 제출한 요청들이 실제로 끝날 때까지 기다리고, 정확한 upload ID를 취소한 후 `ListParts` 부재를 확인한다. `Future.cancel()`의 반환만으로 HTTP 종료를 가정하지 않는다. 취소 권한 실패는 성공으로 숨기지 않는다.
- 완료 응답이 유실되면 HEAD의 크기와 이번 시도의 UUID metadata를 모두 확인한다. 같은 key의 이전 객체만 존재하는 경우를 성공으로 인정하지 않는다.
- HEAD까지 실패하면 성공을 추정하지 않고 오류를 반환한다. 이때 이미 완료된 객체가 있을 수 있으므로 운영자가 상태를 확인해야 한다. 미완료 파트 lifecycle은 완료된 객체 버전을 지우지 않는다. 앱의 기존 `DeleteObject`도 versioned bucket에서 영구 버전 삭제와 같지 않다.
- 다운로드는 같은 디렉터리의 임시 `.part`에 쓰고 선언 길이와 실제 길이가 일치한 뒤 최종 경로로 이동한다. 기존 파일은 덮어쓰지 않는다. 중단되면 임시 파일을 제거하고 새 요청으로 재시도할 수 있다.

SDK의 자동 multipart도 검토했다. 설치 버전의 `GenericMultipartHelper`는 실패 후 abort를 비동기로 시작하며 그 완료를 기다리는 정리 보장을 제공하지 않아, 이번에 필요한 **정리 확인과 장애 계측을 명시한 동기 multipart 경로**를 선택했다. 이는 자동 multipart가 항상 느리거나 사용할 수 없다는 결론이 아니다. [AWS 자동 multipart 문서](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/s3-async-client-multipart.html), [2.57.11 소스](https://repo.maven.apache.org/maven2/software/amazon/awssdk/s3/2.57.11/s3-2.57.11-sources.jar).

## AWS 변경과 강제 종료 한계

IAM Policy Autopilot 0.4.0의 정적 분석 결과에서 필요한 `s3:AbortMultipartUpload`, `s3:ListMultipartUploadParts` 두 action만 선택했다. 기존 역할의 동일 `uploads/*` 리소스에 추가했으며 원래 Get/Put/Delete·prefix List 조건을 유지한다. 정적 분석이 제안한 KMS·ACL·retention·version 삭제 권한은 실제 SSE-S3 저장 경로에 필요하지 않아 적용하지 않았다. Access Analyzer validation과 변경 후 readback을 보존한다.

프로세스가 강제 종료되거나 CreateMultipartUpload 응답 자체를 잃으면 애플리케이션의 정리 코드가 실행되지 않을 수 있다. 기존 incomplete upload가 없음을 먼저 확인하고 `uploads/`에 **1일이 지난 미완료 multipart만** 정리하는 lifecycle 규칙을 추가했다. 완료된 원본 객체의 만료 규칙은 추가하지 않았다. lifecycle은 정확히 24시간에 즉시 실행되는 타이머가 아니다. 이번 짧은 시험에서는 설정을 확인하고 강제 종료 잔여 파트를 직접 정리했으며, 다음 날 lifecycle의 실제 삭제 실행까지 관측했다고 주장하지 않는다. [S3 abort와 진행 중 요청 주의사항](https://docs.aws.amazon.com/AmazonS3/latest/API/API_AbortMultipartUpload.html), [미완료 multipart lifecycle](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpu-abort-incomplete-mpu-lifecycle-config.html).

S3 요청과 외부로 내려받은 데이터 전송에는 비용이 발생할 수 있다. 새 상시 컴퓨트는 만들지 않으며 테스트 UUID의 모든 객체 버전과 미완료 파트를 정리한다. S3 원본 저장 비용과 RDS 스토리지 비용은 유지된다. [S3 가격 항목](https://aws.amazon.com/s3/pricing/).

## 재현 코드

| 위치 | 역할 |
|---|---|
| `src/main/java/com/example/demo/nuscenes/storage/UploadArchiveStore.java` | 운영 single/multipart 분기, 업로드 admission, 완전한 다운로드만 게시 |
| `src/main/java/com/example/demo/nuscenes/storage/MultipartArchiveUploader.java` | 제한된 병렬 파트, 재시도 스트림, drain/abort/verify, 완료 응답 복구 |
| `src/main/java/com/example/demo/nuscenes/storage/S3ArchiveExperiment.java` | Spring을 시작하지 않는 CLI, SHA·파일 inventory, 장애 주입·JSONL·자원 계측 |
| `src/test/java/com/example/demo/nuscenes/storage/S3ArchiveTransferTests.java` | 동시성·순서·중단·취소 실패·완료 응답·부분 파일 회귀 |
| `scripts/hybrid/run_s3_java_experiment.py` | pilot/faults/large 순차 실행, 매 case 새 volume/UUID, 정확한 key/version 정리 |
| `scripts/hybrid/configure_s3_multipart.py` | Autopilot 결과 축소·정책 검증·미완료 파트 lifecycle 설정/readback |
| `scripts/hybrid/measurement.py` | 운영 `[S3_TRANSFER]` 로그 수집 |
| `scripts/hybrid/sample_s3_java_resources.py` | 해당 UUID/소유 라벨의 Docker CPU·메모리·네트워크 관측, 완료 후 종료 |
| `scripts/hybrid/summarize_s3_java_experiment.py` | 원본을 보존하며 case 비교·요청 횟수·초기 실패 이력·report.md 생성 |

```powershell
uvx iam-policy-autopilot@latest generate-policies src/main/java/com/example/demo/nuscenes/storage/UploadArchiveStore.java src/main/java/com/example/demo/nuscenes/storage/MultipartArchiveUploader.java --region ap-northeast-2 --account 189750306426 --service-hints s3 --pretty

$envFile = "$env:LOCALAPPDATA\DriveScene2Label\hybrid\compose.env"
# 각 실행은 새 디렉터리를 지정한다. 기존 로그를 덮어쓰지 않는다.
python scripts/hybrid/run_s3_java_experiment.py --directory .local/hybrid/experiments/NEW-pilot --env-file $envFile --phase pilot
python scripts/hybrid/run_s3_java_experiment.py --directory .local/hybrid/experiments/NEW-faults --env-file $envFile --phase faults
python scripts/hybrid/run_s3_java_experiment.py --directory .local/hybrid/experiments/NEW-large --env-file $envFile --phase large
```

실제 실행 명령·source/image hash·시각은 각 실험 manifest와 command 파일을 따른다. 실험용 CLI에만 장애 주입 기능이 있으며 HTTP endpoint나 운영 설정으로 노출하지 않는다. 인증정보·쿠키·서명 URL·전체 HTTP 헤더는 로그에 기록하지 않는다.

## 진행 기록

원본 묶음은 `.local/hybrid/experiments/20261118T072013Z-s3-java/`다. 초기 테스트 fixture에서 SDK builder의 상위 타입 반환 및 metadata 생성 방식을 잘못 사용한 컴파일/모의 응답 오류를 수정했다. CLI도 프로젝트의 Jackson 3에 맞췄다. 실패 기록 `java-pilot-tests`부터 `java-pilot-tests-r7`을 지우지 않았으며 `r8`에서 14개가 통과했다. 이후 1GiB 경계 검사를 추가한 **최종 S3 9개 + 기존 저장/압축 6개, 총 15개 테스트가 통과**했다. 초기 실패를 실제 S3 장애로 분류하지 않는다.

109.7MB pilot 1쌍의 업로드는 single 3.352초, multipart 5.629초였다. 이 표본에서는 병렬이 느렸다.

## 큰 파일 결과와 적용 결정

| 구분 | 순서 | single 업로드 | multipart 업로드 | 감소율 |
|---|---|---:|---:|---:|
| 재부팅 전 1쌍 | single → multipart | 204.320초 | 207.476초 | **-1.54%** |
| 재부팅 전 2쌍 | multipart → single | 202.093초 | 176.827초 | **12.50%** |
| 재부팅 후 새 쌍 | single → multipart | 126.500초 | 121.173초 | **4.21%** |

재부팅 전 다섯 번째 single은 163.912초로 완료됐지만 짝인 여섯 번째 multipart가 호스트 재부팅으로 중단됐다. 이 single도 원본/요약 로그에 유효한 단독 관측으로 남겼고, 재부팅 후 후보와 억지로 묶지 않았다. 재부팅은 사용자가 GPU 문제로 시행한 것이며 이 S3 시험은 GPU를 사용하지 않았다. 원인을 S3 코드나 GPU 드라이버 어느 쪽으로도 단정하지 않는다.

2026-11-18 17:37:53 KST 재부팅 후, 중단 UUID의 실제 파트 **73개 / 1,224,736,768 bytes**를 확인했다. 정확한 upload ID를 취소하고 ListParts 부재, 해당 객체 버전 부재, 시험 컨테이너/볼륨 정리를 검증했다. 원래 중단 manifest를 성공으로 바꾸지 않고 `reboot-recovery` 결과를 별도 보존한다.

완료한 대용량 전송 **7건**의 4,168,148,189바이트 SHA-256이 모두 일치했다. 첫 쌍에서는 압축 해제된 **31,225개 파일**의 경로·크기·SHA가 원본과 모두 같았다. 해제 시간은 52.624/51.888초였다. 이후 다섯 건은 전체 아카이브 SHA를 확인했으며 매번 파일 inventory까지 다시 만들지는 않았다. 다운로드는 242.220~304.285초였고 두 방식 모두 같은 단일 스트림을 사용한다. 이 시간 차이를 multipart 업로드의 개선으로 계산하지 않는다.

**적용:** 다운로드 `.part` 정리/완전성 확인, bounded upload, 운영 계측, 실패·취소 확인 코드를 반영한다. **multipart 기본값은 false**로 유지한다. 정상 전송에서 안정적인 개선을 입증하지 못했으며 작은 파일은 느려졌다. 장애가 잦거나 연결을 병렬화할 여유가 있는 환경에서 선택할 수 있도록 `UPLOAD_S3_MULTIPART_ENABLED=true`, 동시성 최대 4, 1GiB 초과 조건을 남겼다. 1GiB는 보수적 크기 분리이며 최적 임계값 실험의 결론이 아니다.

병렬 옵션을 되돌릴 때는 `UPLOAD_S3_MULTIPART_ENABLED=false`로 backend를 재생성한다. 이 변경은 이미 진행 중인 업로드가 없는 때 적용한다. 전체 신규 저장 코드의 원복은 직전 commit `725c7e3`의 저장 구현을 기준으로 한다. API·DB 스키마·원본 객체 형식은 바꾸지 않았다.

## 장애 시험 결과

109,696,439바이트 실제 원본으로 아래 5종을 수행했다. 여기서 503은 AWS가 자연 발생시킨 장애가 아니다. 실제 S3가 파트를 받은 후 시험 interceptor가 클라이언트가 보는 응답을 503으로 바꿔 SDK의 실제 retry loop를 검증한다.

| 케이스 | 관측 결과 | 검증한 보장 |
|---|---|---|
| 파트 2의 첫 응답만 503 | 해당 파트 HTTP 요청 2회, 최종 다운로드 SHA 일치 | 재시도에서 같은 파일 구간을 다시 읽음 |
| 파트 2 응답을 계속 503 | 해당 파트 3회 후 IOException, Abort 204 → ListParts 404 | 실패를 성공으로 처리하지 않고 다른 요청 종료 후 파트 정리 |
| Complete 성공 응답 유실 | 실제 Complete 후 예외, HEAD metadata/length 확인, SHA 일치 | 성공한 객체를 잘못 실패·삭제 처리하지 않음 |
| 다운로드 1MiB 후 연결 중단 | 미완성 최종 파일·`.part` 없음, 재시도 SHA 일치 | 손상된 캐시가 후속 복원에 사용되지 않음 |
| 첫 실제 파트 수신 후 SIGKILL | exit 137, 미완료 upload 1개·완료 객체 0개 | 강제 종료 한계를 재현; 운영자 exact-ID abort 후 ListParts NoSuchUpload 확인 |

각 시험 뒤 별도 운영자 조회로 해당 UUID의 객체 버전·delete marker·incomplete upload가 모두 없음을 확인했다. 운영자 정리 권한은 앱 컨테이너에 제공하지 않았다. SIGKILL 뒤 자동으로 이어 올리는 기능은 구현하지 않았으며, lifecycle의 다음 날 삭제 실행을 시험했다고 표시하지 않는다. 취소 권한 거부·호출자 스레드 interrupt·잘못된 완료 metadata는 격리된 Java 단위 시험으로 검증한 범위다.

운영 로그 수집에서도 파트·UUID key·mode·대기시간·실패 결과를 보존하고 `unconfirmed` 정리를 실패로 집계한다. 관련 수집기 테스트 12개가 통과했다.

최종 이미지의 자동 선택 시험에서도 109.7MB가 단일 PUT을 선택했고 업로드 3.426초·다운로드 7.357초, SHA 일치를 확인했다. 1GiB 이하/초과 분기는 격리 Java 테스트로 추가 확인했다. hybrid 전체 Python 테스트는 47개 중 45개 통과·게이트웨이 통합 2개는 해당 로컬 실행에서 제외됐고, CI의 통합 실행과 구분한다.

RDS 재개 중 `configuring-enhanced-monitoring`를 시작 실패로 처리하던 운영 스크립트도 수정했다. 실제 상태는 잠시 뒤 `available`로 바뀌었다. 이제 같은 제한 시간 안에서 기다리며 중복 start 요청을 보내지 않는다. 해당 상태 전이 회귀를 기존 시작 테스트에 추가했다. [AWS 인스턴스 상태 정의](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/accessing-monitoring.html).

## 상황별 선택과 다음 후보

| 상황 | 유리한 선택 / 확인할 점 |
|---|---|
| 작은 압축 파일, 안정적인 연결 | 단일 PUT은 multipart 생성·완료·추가 요청 비용이 없다. 109.7MB pilot에서도 단일이 빨랐다. 이 크기 1쌍을 모든 작은 파일에 대한 통계로 일반화하지 않는다. |
| 큰 파일, 충분한 네트워크 여유 | multipart가 여러 연결을 활용할 수 있지만 현재 PC에서의 실측이 우선이다. 4.17GB는 16MiB 기준 249파트이며 단일 PUT보다 요청 수가 늘어난다. |
| 일시적 파트 실패 | multipart는 실패한 16MiB 구간만 다시 보낼 수 있다. 이번 실제 SDK retry loop에서 재현했다. 강제 종료 후 이어 올리기는 별도 기능이다. |
| 같은 데이터셋을 자주 열람 | 기존 압축·해제 캐시 보존이 GET·압축 해제를 건너뛴다. 디스크 공간과 UUID별 격리를 함께 관리한다. CLI 캐시 lookup 시간은 카메라 HTTP 응답 시간이 아니다. |
| 다운로드가 전체 복원의 대부분 | 다음 후보는 대용량 Range GET 병렬화다. 파일의 버전/ETag 고정, 겹침·누락 없는 범위, 전체 SHA와 부분 파일 정리가 필요하다. 이번 다운로드는 동일 단일 스트림이며 병렬 GET을 적용하지 않았다. |
| 다중 연결로도 속도가 같고 CPU가 낮음 | 회선·TCP·전송 경로가 병목일 가능성을 먼저 확인한다. 스레드 수 증가만으로 해결됐다고 판단하지 않는다. 같은 리전의 AWS 컴퓨트와 S3 비교는 별도 비용·데이터 이동 실험이다. |
| multipart 요청 자체의 오버헤드가 큼 | 64MiB 파트 후보는 요청 수를 줄이는 대신 재전송 단위가 커진다. 스트리밍이므로 파트 크기만큼 힙을 예약하는 구현은 아니다. 이번에는 16MiB/동시성 4를 검증했다. |

S3 공식 지침도 CPU·메모리·네트워크를 같이 측정하고 다중 연결·Range GET·동일 리전 배치를 검토하도록 안내한다. 이를 이 프로젝트의 측정 결과 대신 쓰지 않는다. [AWS 성능 지침](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-guidelines.html), [Range/연결 설계 패턴](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html).

현재 TGZ cold restore는 ZIP key의 404를 확인한 뒤 TGZ를 가져온다. 로그의 이 404는 의도된 형식 탐색이다. format metadata를 보존하면 요청 하나를 없앨 수 있지만, 수백 초의 대용량 전송과는 영향 규모가 다르다. Kafka·Spark·검색 엔진 추가는 이 압축 파일 전송 경로를 직접 단축하지 않아 이번 도구로 선택하지 않았다.
