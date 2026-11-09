# release-version: 서울 AWS 환경

대상 계정은 `189750306426`, 리전은 **서울 `ap-northeast-2`**다. 관리 계정에는 애플리케이션을 배포하지 않는다. GitHub 기본 브랜치, PR 검사 대상, push 배포 및 수동 실행 브랜치는 `release-version`이다.

## 구성과 보관

`infra/aws/templates.py`가 일반 CloudFormation JSON 6개를 생성한다. CDK, Terraform, Kafka, Redis, Elasticsearch, SQS는 필요하지 않다. 작업 큐는 기존 PostgreSQL claim/locking을 사용한다.

| 스택 | 역할 | stop 이후 |
|---|---|---|
| ds2l-foundation | VPC, 비공개 S3, ECR, Secrets Manager, IAM/OIDC, 빈 ECS 클러스터, 내부 DNS | 유지 |
| ds2l-database | 사설 PostgreSQL 16 + pgvector, db.t4g.small | 검증한 수동 스냅샷·복구 기록 보존 후 인스턴스 삭제 |
| ds2l-eks | EKS 클러스터와 CPU EC2 t3.large 1대 | 노드·클러스터 삭제 |
| ds2l-app | 프런트엔드와 Spring API, ECS Fargate 1 vCPU / 2 GiB | 서비스·태스크 삭제 |
| ds2l-gpu | ECS용 EC2 g6.2xlarge 1대, VESPA + CLIP | EC2·캐시 디스크·서비스 삭제 |
| ds2l-web | AWS 제공 HTTPS 주소, ALB, 0.25 vCPU / 512 MiB 로그인 프록시 | ALB·프록시 제거, Cognito 사용자와 세션 키는 foundation에 보존 |

EKS와 Fargate는 같은 앱 이미지 digest, RDS, S3, GPU를 사용한다. 자동 라벨 worker는 **ECS만** 실행한다. EKS는 업로드·수정·다운로드 API를 제공한다. GPU EC2는 EKS 노드가 아니다.

GPU를 끌 때 ECS worker도 비활성화하고, GPU 준비 확인 후 다시 활성화한다. 대기 중 작업은 GPU가 꺼진 동안 DB에 남으며 연결 실패로 소비하지 않는다.

원본 ZIP은 S3 버전 관리 버킷에, 원본 라벨 JSON과 수정 이력은 DB에 저장한다. 환경 종료 시 DB는 스냅샷으로 보존한다. S3, 스냅샷, ECR 이미지에는 자동 삭제 정책이 없다. 최소 한 달 보관하며 30일 이후에도 자동 삭제하지 않는다. 저장된 데이터·이미지·스냅샷·비밀·DNS에는 서버 종료 후에도 요금이 발생할 수 있다. CloudWatch 진단 로그만 30일 보관한다.

EKS 제어 영역은 실행 중 시간당 요금이 발생한다. RDS 단순 정지는 7일 뒤 자동 시작되므로 `stop`은 보존·삭제 방식이다. 재시작에는 DB 복원, EKS 생성, 이미지 다운로드 및 GPU 모델 로딩 시간이 걸린다. GPU 캐시 디스크는 종료 시 제거되므로 다시 다운로드한다.

## 최초 준비

프로젝트 계정의 서울 CloudShell에서 실행한다. `bootstrap`은 영구 저장소와 배포 권한만 생성하며 GPU/DB/웹 서버를 켜지 않는다.

```bash
git clone --branch release-version https://github.com/DriveScene2Label-Team/DriveScene2Label.git
cd DriveScene2Label
python3 -m venv .venv-aws
source .venv-aws/bin/activate
pip install -r scripts/aws/requirements.txt
export AWS_REGION=ap-northeast-2
python scripts/aws/environment.py bootstrap
```

GitHub의 `production` Environment는 `release-version` 배포만 허용한다. Repository Variables:

| 이름 | 값 |
|---|---|
| AWS_ROLE_ARN | bootstrap 출력의 role |
| AWS_DEPLOY_ENABLED | true |
| AI_BUILD_RUNNER | 선택: 모델 이미지 빌드용 충분한 디스크를 갖춘 runner label |

장기 AWS access key를 GitHub Secrets에 넣지 않는다. OIDC subject는 이 저장소의 immutable owner/repo ID와 `production` environment에 정확히 제한된다. 해당 저장소가 재생성되면 OIDC subject를 다시 확인해야 한다.

`Release images and deploy ECS + EKS`를 앱으로 한 번 실행해 ECR에 앱 이미지를 준비한다. AI 이미지는 같은 workflow에서 `component=ai`로 **수동** 실행한다. AI 빌드는 모델 라이브러리와 VESPA 의존성 때문에 CPU 빌드보다 오래 걸리고 디스크 공간을 더 사용한다.

서울 `Running On-Demand G and VT instances` quota(`L-DB2E81BA`)가 **8 vCPU 이상**이어야 GPU를 켤 수 있다. 인스턴스 유형 제공 여부와 실제 용량은 다르므로 용량 부족 오류는 별도로 처리해야 한다.

## 켜기·끄기

GitHub Actions → **AWS environment** → Run workflow → `release-version`:

| action | 동작 |
|---|---|
| status | 리소스·스택·복구 스냅샷·GPU 한도 조회 |
| start | 마지막 검증 이미지로 DB 복원, EKS/ECS 생성, GPU 및 앱 준비 확인 |
| stop | 쓰기 차단, 실행 작업 종료 대기, 스냅샷 확인, 런타임 전체 제거 |
| gpu-start | 공유 GPU만 생성하고 CLIP 로딩 확인 |
| gpu-stop | 작업 종료 대기 후 GPU 제거, 앱 쓰기 재허용 |
| web-start | 실행 중인 ECS 앞에 팀 로그인 필수 HTTPS 주소 생성. 이후 start에서 함께 복원 |
| verify | 두 환경에서 실제 브라우저 라벨 업로드·수정·저장·다운로드 및 ZIP 업로드/API 다운로드 검사. restore_check=true면 이전 문서와 ZIP의 복구 여부만 확인 |

GPU 승인 전에는 `start`에서 `gpu=false`를 선택해 업로드·수정·저장·다운로드를 검증할 수 있다. 자동 라벨과 임베딩은 GPU가 준비된 뒤 검증한다. `/health`는 CLIP 로딩 상태다. VESPA 실제 추론 성공 여부는 유효한 업로드 데이터셋으로 작업을 실행해 별도 확인해야 한다.

push는 테스트·Docker 빌드·ECR 업로드 후 **이미 실행 중인** 환경만 배포한다. 환경이 꺼져 있으면 이미지 digest만 S3 control manifest에 기록한다. push로 누락된 서버를 생성하지 않는다. 한쪽만 실행 중인 불완전 상태면 자동 복구 대신 오류를 내며 수동 start/stop으로 복구한다.

전체 종료는 다음 순서를 지킨다.

1. 토큰으로 보호된 내부 운영 API가 DB 공통 maintenance gate를 켠다. 신규 업로드·수정·작업 생성을 막고 다운로드는 유지한다.
2. 모든 앱 프로세스의 진행 중 쓰기와 DB의 RUNNING 작업이 0이 될 때까지 기다린다. 시간 초과나 확인 실패면 DB를 삭제하지 않는다.
3. 공개 게이트웨이와 ALB, ECS/EKS 앱과 GPU를 제거하고 암호화 수동 DB 스냅샷을 생성한다.
4. 스냅샷이 `available`이고 이 DB에서 생성됐는지 확인한다. S3의 버전 관리되는 복구 기록을 저장하고 다시 읽어 확인한다.
5. 검증이 모두 성공한 경우에만 DB를 삭제한다. 이어 EKS 노드·클러스터를 제거하고 남은 실행 리소스를 검사한다.

스냅샷 생성·검증·S3 기록 중 하나라도 실패하면 DB 삭제를 호출하지 않는다. 실패 시 쓰기가 차단된 상태가 유지될 수 있으므로 원인을 해결한 뒤 start/stop을 다시 실행한다. `foundation` 삭제는 lifecycle 도구가 거부한다. DB CloudFormation 리소스도 `Retain`이므로 실수로 스택만 지워도 DB가 자동 삭제되지 않는다.

GitHub 배포와 lifecycle은 같은 concurrency group과 `queue: max`를 써서 대기 중인 수동 작업이 새 push로 취소되지 않게 하며, S3 조건부 쓰기 lock도 공유한다. 실행이 강제로 중단되면 lock이 남을 수 있다. 자동으로 만료시키지 않는다. 기존 실행이 종료됐고 스냅샷·스택 상태를 검토한 관리자가 `control/lock.json`의 현재 버전을 보존한 채 조건부 갱신으로 `{"owner":null}`로 복구해야 한다. 실행 중인 작업의 lock을 해제하지 않는다.

## 팀 로그인과 외부 HTTPS 주소

2026-11-09 생성한 서울 주소: **https://ds-0b9e41d7414848af9d6a29b538031aa6.ecs.ap-northeast-2.on.aws**. `/scenes?dataset=3`에 실제 nuScenes `scene-0061` 39개 프레임을 업로드했습니다. `/labels`는 라벨 JSON 편집 화면입니다. 공개 주소와 로그인 리디렉션·최초 비밀번호 변경 화면을 확인했으며, 인증 후 전체 흐름 검증과 구분합니다. 환경 재생성 시 아래 `status` 결과가 최신 주소입니다.

최초 관리자가 갱신된 `bootstrap`을 적용한 뒤 `AWS environment → web-start`를 실행한다. `status`의 `recovery.public_url`이 실제 외부 접속 주소다. Express Mode가 AWS 도메인과 TLS 인증서를 제공하므로 도메인 구매와 로컬 터널이 필요 없다. `/scenes`에서 씬을 탐색하고 `/labels`에서 파일 업로드·편집·수정본 저장·다운로드를 사용한다. 새 방문은 최신 업로드 데이터셋을 선택하고 기존 dataset 링크는 보존한다.

Cognito는 관리자 생성 계정만 허용하며 `team` 그룹 회원만 프록시를 통과한다. 코드 교환에는 PKCE와 nonce를 사용하고, 로그인 쿠키는 Secure·HttpOnly·SameSite=Lax다. DB·S3·GPU는 공개하지 않는다. `/ping`은 앱 데이터가 없는 상태 확인 경로다. 그룹에서 제거한 사용자의 기존 세션은 갱신/만료 시 차단되므로 긴급 접근 회수 시 Cognito 계정 비활성화와 프록시 세션 키 교체를 함께 검토한다.

프로젝트 관리자 자격 증명으로 팀 계정을 만든다. 아래 명령은 이메일을 보내지 않으며 임시 비밀번호를 터미널에 출력하지 않는다. 파일은 저장소 밖에 생성하고 본인에게만 전달한다. 첫 로그인에서 사용자가 비밀번호를 변경한다.

```bash
python scripts/aws/team_user.py TEAM_USERNAME --credentials-file /secure/local/path/team-login.txt
```

인증 프록시는 `oauth2-proxy v7.15.5`의 검증한 이미지 digest를 고정한다. 앱 자체에 비밀번호 처리 코드를 추가하지 않기 위해 사용한다. 인증 client secret과 쿠키 키는 Secrets Manager에서 주입한다. `stop` 뒤 `start` 시 OAuth client/callback을 다시 구성하며, 재생성된 서비스의 URL은 `status`에서 확인한다. 코드 push는 꺼진 공개 게이트웨이를 켜지 않는다. 실행 중 ALB와 프록시 비용이 추가된다.

`cfn-lint` 및 `infra/aws/security.guard`로 비공개 S3·암호화 DB·관리자 초대 전용 계정을 검사했다. 이는 전체 보안 감사가 아니다. 현재 계정에 별도 CloudTrail trail은 없으며 장기 감사 로그 보관은 별도 구성 사항이다.

## 관리자 PC에서 직접 접속

앱·DB·GPU의 직접 인터넷 인바운드 포트는 열지 않는다. 공개 접속은 로그인 게이트웨이를 사용한다. 아래 터널은 관리자의 진단용이며 팀원에게 배포 주소로 안내하지 않는다. NAT Gateway는 생성하지 않는다. EKS API는 IAM 인증을 요구한다.

PC에 AWS CLI, Session Manager plugin, kubectl을 설치하고 bootstrap에 사용한 프로젝트 관리자 역할의 단기 자격 증명으로 로그인한다. 해당 실제 IAM 역할 ARN을 확인해 EKS 운영자 Access Entry로 등록한다. 사람의 역할을 GitHub OIDC 역할로 가장하지 않는다. 다른 팀원은 별도 EKS Access Entry와 SSM 권한이 필요하다.

ECS 접속은 실행 중 EKS CPU 노드 ID를 대상으로 SSM remote-host 포트 전달:

```bash
aws ssm start-session --region ap-northeast-2 --target i-CPU_NODE_ID \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["app.ds2l.internal"],"portNumber":["8080"],"localPortNumber":["18080"]}'
```

브라우저에서 `http://127.0.0.1:18080/labels`를 연다. EKS는 허가된 역할로:

```bash
aws eks update-kubeconfig --region ap-northeast-2 --name ds2l-eks
kubectl -n drivescene port-forward service/backend 18081:8080 --address=127.0.0.1
```

`http://127.0.0.1:18081/labels`에서 같은 문서·수정 이력이 보이는지 확인한다. Secrets Manager는 앱 DB 자격 증명과 운영 토큰을 제공한다. EKS는 Pod Identity + CSI로 파일 마운트하며 일반 Kubernetes Secret에 비밀번호를 복사하지 않는다. DB 연결은 CA 인증서와 `sslmode=verify-full`로 검증한다.

## 검증과 현재 기능 범위

2026-11-09 서울에서 [CPU 환경 start](https://github.com/DriveScene2Label-Team/DriveScene2Label/actions/runs/42595122060)와 [ECS/EKS 실제 UI·원본 ZIP 검증](https://github.com/DriveScene2Label-Team/DriveScene2Label/actions/runs/42595393497)이 성공했다. 같은 이미지 digest를 확인하고 양쪽 브라우저에서 라벨 수정본 저장·재조회·다운로드를 검사했으며, 두 환경에서 원본 라벨과 ZIP 해시가 일치했다. [공개 게이트웨이 추가 릴리스](https://github.com/DriveScene2Label-Team/DriveScene2Label/actions/runs/42603725024)의 검사·이미지 발행·앱 배포도 성공했다. GPU 한도는 8 vCPU로 승인됐으며 실제 추론과 전체 stop/start 스냅샷 복원은 별도 검증해야 한다. 사용 종료 시 `stop`을 실행한다.

GPU의 `ai.ds2l.internal`은 Cloud Map 서비스와 `AWS::ServiceDiscovery::Instance`로 관리한다. Cloud Map이 소유한 DNS 영역에 Route 53 레코드를 직접 쓰면 거부되므로 해당 방식은 사용하지 않는다. GPU 생성 시 현재 사설 IP를 등록하고 제거 시 등록도 해제한다. 배포 역할은 이 AI 서비스에 대한 등록·해제 권한만 갖는다. 공개 게이트웨이는 ECS가 반환하는 보안 그룹 ARN에서 그룹 ID를 추출하고, secret 갱신 후 시작한 새 배포가 성공했는지 확인한다.

```bash
python -m unittest discover -s scripts/aws/tests -v
python infra/aws/templates.py
cfn-lint build/cloudformation/*.json
bash gradlew test
```

CI는 백엔드, 프런트엔드, 업로드/라벨 브라우저 흐름, AI 업로드 계약, Docker 빌드 및 종료 안전장치를 검사한다. 실제 AWS 확인은 ECS와 EKS 양쪽에서 업로드 → 수정 → 수정본 저장 → 다운로드, stop/start 후 동일 원본·수정 이력 유지, off 상태 push 후 리소스 미생성을 검증한다.

`verify`는 저장소의 테스트 metadata와 합성 미디어로 작은 nuScenes ZIP을 만들고 양쪽 앱에 올린다. 다운로드 SHA-256과 라벨 원문·revision을 S3 `control/verification.json`에 기록해 재생성 뒤 대조한다. 이 합성 ZIP은 저장·복구 검사용이며 GPU 추론 검사용 데이터가 아니다. 검사 문서는 실제 DB에 남는다.

업로드 지원은 라벨 JSON과 유효한 nuScenes ZIP이다. 임의 이미지·MP4를 nuScenes로 변환하는 기능은 포함하지 않는다. 업로드 ZIP 최대 5,000,000,000바이트, 압축 해제 최대 8GiB이며 필요한 메타데이터와 참조 미디어를 포함해야 한다. 전체 mini를 위해 Spring·S3 복원·GPU 캐시 한도를 일치시키고, Fargate 임시 공간을 40GiB로 지정했다. ALB idle timeout은 배포 및 web-start 시 로그인 프록시와 같은 600초로 설정해 압축 해제·S3 보존·DB 등록 중 응답을 기다릴 수 있게 한다. S3 단일 PUT 한도 안에서 처리하며 중단된 업로드의 이어받기는 지원하지 않는다. 현재 업로드 데이터셋의 자동 CLIP 인덱싱과 Rerun 생성은 별도 후속 작업이다. 라벨 JSON 업로드·UI 수정·수정본 저장/다운로드에는 GPU가 필요 없다. 자세한 JSON 형식은 [라벨 편집 문서](label-editing.md)를 참조한다.

참고: [EKS 요금](https://aws.amazon.com/eks/pricing/), [RDS 정지 후 재시작](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html), [Secrets Manager Pod Identity](https://docs.aws.amazon.com/secretsmanager/latest/userguide/ascp-pod-identity-integration.html), [GitHub OIDC](https://docs.github.com/en/actions/reference/security/oidc).
