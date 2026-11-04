# VESPA를 원격 Slurm 클러스터에서 실행 (`VESPA_EXECUTOR=ssh`)

로컬(컨테이너 안) 실행은 [VESPA.md](VESPA.md)를 참고하세요. 이 문서는 VESPA를 Seraph(Slurm 기반 GPU서버)에서 돌리는 설정입니다.

기본값 `VESPA_EXECUTOR=local`은 컨테이너 안에서 VESPA를 실행합니다. `ssh`로 바꾸면 같은 `POST /auto-label`이 클러스터에 SSH로 Slurm job을 제출하고, 끝나면 결과 JSON을 가져와 local과 **같은 검증·응답 코드**로 반환합니다. Spring, DB, REST 계약은 바뀌지 않습니다.

```text
Spring backend → ai-server POST /auto-label → (ssh) 클러스터 sbatch → GPU 노드에서 VESPA
                         ↑ 결과 JSON 복사 · 검증 ←────────────────────┘
```

흐름: `sbatch --parsable <script>`(EXP/SCENES 환경변수) 제출 → 받은 job ID로 `squeue -j` 대기(`VESPA_SSH_POLL_SECONDS` 간격) → 큐에서 빠지면 `sacct` 상태와 Slurm 로그 tail을 run 로그에 저장 → 출력 파일의 수정 시각이 제출 전과 달라졌는지 확인 → `cat`으로 복사 → coverage/클래스/score 검증.

## 0. 내 PC에서 seraph 접속 설정 (처음 한 번)

아래 명령은 WSL/Ubuntu 터미널에서 실행합니다(Windows가 아니라 Ubuntu의 `~/.ssh/`에 저장됨).

|자리표시자|의미|
|---|---|---|
|`<seraph 계정>`|seraph 로그인 계정 이름|
|`<서버 주소>`|seraph 로그인 노드 주소 (ex. ariel@khu.ac.kr)|
|`<포트>`|SSH 포트. 기본값 22가 아닐 수 있음 (Ex. 30080)|
|`<키 메모>`|키를 구분하는 메모. 접속에는 쓰이지 않으며 아무 값이나 됨(예: PC 이름)|

**1) 개인 키 만들기**

```bash
ssh-keygen -t ed25519 -C "<키 메모>"
```

- 저장 위치를 물으면 Enter를 눌러 기본 위치(`~/.ssh/id_ed25519`)에 저장합니다. 이미 그 파일이 있으면 덮어쓰지 말고 이 단계를 건너뜁니다.
- passphrase(키 비밀번호)를 비워 두면 비밀번호 없이 접속됩니다. 이때는 개인 키 파일이 곧 접속 권한이므로 복사하거나 레포에 넣지 마세요.
- 결과로 두 파일이 생깁니다. `id_ed25519`는 개인 키로 내 PC에만 두고, `id_ed25519.pub`는 공개 키로 서버에 등록합니다.

**2) 공개 키를 seraph에 등록하기**

```bash
ssh-copy-id -p <포트> <seraph 계정>@<서버 주소>
```

- 1)의 공개 키를 seraph의 `~/.ssh/authorized_keys`에 추가합니다. 이때 처음이자 마지막으로 seraph 비밀번호를 입력합니다.
- `Number of key(s) added: 1`이 나오면 성공입니다. 이후에는 비밀번호 없이 키로 접속됩니다.

**3) 접속 별칭 등록하기**

`~/.ssh/config`에 아래 블록을 추가하면 긴 주소 대신 `ssh seraph`로 접속됩니다. 파일이 없으면 새로 만들고 `chmod 600 ~/.ssh/config`로 권한을 맞춥니다.

```text
Host seraph
    HostName <서버 주소>
    User <seraph 계정>
    Port <포트>
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
```

|줄|의미|
|---|---|
|`Host seraph`|별칭 이름. 자유롭게 정할 수 있으며 `ssh <별칭>`으로 씀|
|`HostName` / `User` / `Port`|실제 서버 주소, 계정, 포트|
|`IdentityFile`|1)에서 만든 개인 키 경로|
|`ServerAliveInterval 30`|30초마다 신호를 보내 오래 켜 둔 연결이 끊기지 않게 함|

**4) 확인하기**

```bash
ssh seraph "hostname; which sbatch squeue sacct"
```

비밀번호를 묻지 않고 로그인 노드 이름과 세 명령의 경로가 출력되면 완료입니다. 서버 SSH 버전에 따라 `post-quantum key exchange` 경고가 함께 나올 수 있으며 동작에는 영향이 없습니다.

이 별칭은 내 PC에서 직접 접속할 때만 쓰입니다. AI server 컨테이너는 2장의 전용 키와 `.env` 값으로 따로 접속합니다.

**예시**

계정 `student01`, 서버 주소 `seraph.example.ac.kr`, 포트 `2222`, 키 메모 `my-laptop`이라고 가정한 예시입니다. 실제 값이 아니므로 자기 값으로 바꿔 입력하세요.

```bash
ssh-keygen -t ed25519 -C "my-laptop"
ssh-copy-id -p 2222 student01@seraph.example.ac.kr
ssh seraph "hostname; which sbatch squeue sacct"   # ~/.ssh/config 등록 후
```

```text
# ~/.ssh/config
Host seraph
    HostName seraph.example.ac.kr
    User student01
    Port 2222
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
```

## 1. 원격(Slurm 클러스터) 준비

ssh 모드는 클러스터에 있는 VESPA 레포에서 job을 실행합니다. **원본 [TUMFTM/VESPA](https://github.com/TUMFTM/VESPA)에는 scene별 결과를 쓰는 스크립트가 없으므로**, 이 레포의 [`vespa-remote/`](vespa-remote/)에 있는 두 파일을 VESPA 레포 최상위에 복사해서 씁니다.

|파일|역할|
|---|---|
|`main_pseudo_vlm_scene.py`|원본 `main_pseudo_vlm.py`와 같은 파이프라인. 요청한 scene마다 최종 JSON을 따로 저장|
|`pseudo_scenes_lowmem.sh`|위 스크립트를 실행하는 sbatch 스크립트. `EXP`, `SCENES` 환경변수를 받음|

### 1-1. 원격 폴더 구성

```text
<VESPA_ROOT>/                          ← .env의 VESPA_SSH_REMOTE_ROOT
├─ main_pseudo_vlm.py 등               (원본 VESPA)
├─ main_pseudo_vlm_scene.py            ← vespa-remote/에서 복사
├─ pseudo_scenes_lowmem.sh             ← vespa-remote/에서 복사
├─ configs/vlm/p_final.yaml            ← 데이터셋 경로 지정 (1-2)
├─ logs/                               (제출 시 자동 생성, Slurm 로그)
└─ outs/vlm/p_final/#out_labels_scene/<scene>/vlm_p_final_<scene>_{1,3,8}class.json
```

```bash
# 클러스터에서: 원본 VESPA clone 후 원본 설치 절차대로 환경 준비 (예: conda env "vespa")
git clone https://github.com/TUMFTM/VESPA.git <VESPA_ROOT> && git -C <VESPA_ROOT> checkout acb2b6e8683363795528f049fe0444ef9f3efdb9
# Docker·Colab과 같은 결과를 원하면 이 레포의 patch도 적용 (apply.sh와 patch 파일을 함께 복사)
scp -r ai-server/vespa-patches seraph:<VESPA_ROOT>/../vespa-patches && ssh seraph 'bash <VESPA_ROOT>/../vespa-patches/apply.sh <VESPA_ROOT> acb2b6e8683363795528f049fe0444ef9f3efdb9'
# 로컬(이 레포)에서: 두 파일 복사. scp는 SSH로 파일을 보냅니다(0장의 seraph 별칭 사용)
scp ai-server/vespa-remote/* seraph:<VESPA_ROOT>/
```

### 1-2. 데이터셋 위치와 설정

nuScenes는 클러스터 안 어디에 둬도 되지만, **job이 실행되는 계산 노드에서도 보이는 경로**(공유 스토리지)여야 합니다. 폴더 구조는 로컬 `NUSCENES_HOST_PATH`와 같습니다.

```text
<DATA_ROOT>/                 예: /<공유 스토리지>/<계정>/datasets/nuscenes
├─ samples/  sweeps/  maps/
└─ v1.0-mini/                (scene.json, sample.json 등)
```

위치는 원격 VESPA의 config 파일에 지정합니다. ssh 모드는 이 config를 **그대로** 쓰고, local 모드처럼 경로를 덮어쓰지 않습니다.

```yaml
# <VESPA_ROOT>/configs/vlm/p_final.yaml
data:
  root_path: <DATA_ROOT>
  dataset_version: v1.0-mini
```

- 원격 데이터는 로컬 `NUSCENES_HOST_PATH`와 **같은 버전**이어야 합니다. AI server가 로컬 metadata로 sample token을 검사합니다.
- `.env`의 `VESPA_SSH_EXP`는 config 파일 이름입니다. mini는 `p_final`, trainval은 그 데이터용 config 이름(예: `p_final_trainval`)을 씁니다.

### 1-3. 스크립트를 계정에 맞게 수정

`pseudo_scenes_lowmem.sh` 맨 위의 `#SBATCH` 줄(파티션 `-p`, 노드 `-w`, GPU·메모리·시간)과 `CONDA_SH`, `CONDA_ENV` 기본값을 자기 계정과 클러스터에 맞게 고칩니다. `#SBATCH` 줄에는 환경변수를 쓸 수 없어서 직접 수정해야 합니다. 스크립트는 항상 `exit 0`이며, AI server는 종료 코드가 아니라 **새 출력 파일**로 성공을 판단합니다.

### 1-4. 원격에서 먼저 단독 실행

```bash
cd <VESPA_ROOT>
EXP=p_final SCENES=scene-0061 sbatch pseudo_scenes_lowmem.sh
ls "outs/vlm/p_final/#out_labels_scene/scene-0061/"     # job이 끝난 뒤 3개 JSON 확인
```

## 2. AI server 연결 (Docker)

1. 컨테이너 전용 키를 만들고 seraph에 등록합니다. 0장의 개인 키(`~/.ssh/id_ed25519`)를 컨테이너에 넣지 않기 위해서입니다. `secrets/`는 Git에서 제외됩니다. `-C drivescene-ai-server`는 0장과 같은 키 메모입니다.

```bash
mkdir -p secrets/vespa-ssh && chmod 700 secrets/vespa-ssh
ssh-keygen -t ed25519 -N "" -C drivescene-ai-server -f secrets/vespa-ssh/id_ed25519
ssh-copy-id -f -i secrets/vespa-ssh/id_ed25519.pub seraph
ssh-keyscan -p <포트> <서버 주소> > secrets/vespa-ssh/known_hosts   # 서버 신원 저장 (예: -p 2222 seraph.example.ac.kr)
ssh -i secrets/vespa-ssh/id_ed25519 -o IdentitiesOnly=yes seraph hostname   # 새 키만으로 접속 확인
```

`-f`가 없으면 기존 개인 키로 시험 접속이 성공해서 `ssh-copy-id`가 새 키 등록을 건너뛸 수 있습니다(`All keys were skipped`).

2. `.env`에 추가합니다. 컨테이너에는 `~/.ssh/config`가 없으므로 별칭이 아니라 실제 계정, 주소, 포트를 씁니다. `.env`는 커밋하지 않습니다.

```bash
COMPOSE_FILE=compose.yml:compose.seraph.yml
VESPA_SSH_TARGET=<seraph 계정>@<서버 주소>   # 예: student01@seraph.example.ac.kr
VESPA_SSH_PORT=<포트>                        # 예: 2222
VESPA_SSH_REMOTE_ROOT=<VESPA_ROOT>            # 1장의 원격 VESPA 폴더 절대 경로
VESPA_SSH_EXP=p_final
```

3. 재빌드 후 연결을 확인합니다. `openssh-client` 레이어만 새로 빌드됩니다.

```bash
docker compose up -d --build
curl http://127.0.0.1:8000/health          # inference.vespa_executor = "ssh", vespa = "configured"
docker compose exec ai-server sh -c 'ssh -i "$VESPA_SSH_KEY" -p "$VESPA_SSH_PORT" -o BatchMode=yes \
  -o UserKnownHostsFile="$VESPA_SSH_KNOWN_HOSTS" "$VESPA_SSH_TARGET" "hostname; which sbatch squeue sacct"'
```

`/health`와 SSH 확인이 끝나면 3장으로 실제 job을 실행합니다.

Docker 없이 WSL에서 FastAPI를 직접 띄울 때는 `VESPA_EXECUTOR=ssh VESPA_SSH_TARGET=<~/.ssh/config의 Host 별칭> VESPA_SSH_REMOTE_ROOT=...`만 주면 기존 `~/.ssh/config`(포트·키)를 그대로 사용합니다.

## 3. 실행하기

평소에는 **Backend API**로 실행합니다. Backend가 job을 DB에 저장하고, worker가 ai-server를 호출하고, 결과를 DB에 저장합니다. 3-2의 ai-server 직접 호출은 연결 확인용이며 결과가 DB에 저장되지 않습니다.

### 3-1. Backend로 실행

**1) scene token 확인**

Backend는 scene 이름(`scene-0061`)이 아니라 nuScenes의 scene **token**을 받습니다. dataset ID는 `GET /api/datasets`로 확인합니다.

```bash
curl -s http://127.0.0.1:8080/api/datasets/<datasetId>/scenes \
  | python3 -c "import json,sys; [print(s['name'], s['token']) for s in json.load(sys.stdin)]"
```

**2) job 생성**

```bash
curl -X POST http://127.0.0.1:8080/api/auto-label/jobs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: <요청 키>' \
  -d '{"sceneToken":"<scene token>","datasetId":<datasetId>,"classMode":8}'
```

- 응답은 `{"jobId":<번호>,"status":"PENDING"}`이며 바로 돌아옵니다. 실제 실행은 Backend worker가 이어서 처리합니다.
- `classMode`는 1(vehicle), 3(vehicle·pedestrian·bicycle), 8(nuScenes 8개 클래스) 중 하나입니다.
- `Idempotency-Key`는 요청을 구분하는 임의의 문자열입니다. 같은 키로 다시 보내면 새 job을 만들지 않고 기존 job을 돌려주므로, 네트워크 재시도에는 같은 키를, **새로 실행할 때는 새 키**를 씁니다.

**3) 진행 확인**

```bash
curl http://127.0.0.1:8080/api/auto-label/jobs/<jobId>          # PENDING → RUNNING → COMPLETED 또는 FAILED
docker compose logs -f ai-server                                # Slurm job ID와 상태 변화
ssh seraph "squeue -j <Slurm job ID> -o '%T %N %M'"             # seraph에서 상태, 노드, 경과 시간
```

`FAILED`이면 `errorMessage`에는 짧은 분류만 담깁니다. 자세한 원인은 ai-server 로그와 `/results/<run_id>/execution.log`에서 확인합니다(5장).

```bash
docker compose exec ai-server sh -c 'cat /results/$(ls -t /results | head -1)/execution.log'
```

**4) 결과 조회**

`COMPLETED`가 되면 결과를 조회합니다. 응답에는 처리한 sample 목록(`sampleTokens`), 박스(`boxes`: world 좌표 중심, 크기 WLH, quaternion WXYZ, 클래스), 결과 파일 정보(`artifacts`)가 들어 있습니다.

```bash
curl http://127.0.0.1:8080/api/auto-label/jobs/<jobId>/results
# 요약만 보기: sample 수, 박스 수, 클래스별 개수
curl -s http://127.0.0.1:8080/api/auto-label/jobs/<jobId>/results | python3 -c "import json,sys,collections;d=json.load(sys.stdin);print(d['mappingName'],'samples',len(d['sampleTokens']),'boxes',len(d['boxes']));print(collections.Counter(b['detectionName'] for b in d['boxes']))"
```

**예시**

nuScenes mini의 scene-0061(token `cc8c0bf57f984915a77078b10eb33198`), dataset ID 1, 8class로 실행하는 예시입니다. dataset ID와 jobId는 DB마다 다를 수 있으므로 1)과 2)의 응답에서 확인한 값을 쓰세요.

```bash
curl -X POST http://127.0.0.1:8080/api/auto-label/jobs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: scene-0061-8class-run-1' \
  -d '{"sceneToken":"cc8c0bf57f984915a77078b10eb33198","datasetId":1,"classMode":8}'
# → {"jobId":1,"status":"PENDING"}
curl http://127.0.0.1:8080/api/auto-label/jobs/1
curl http://127.0.0.1:8080/api/auto-label/jobs/1/results
```

### 3-2. ai-server 직접 호출 (연결 확인용)

Backend 없이 ai-server만 확인할 때 씁니다. 이 경로는 scene **이름**을 받고, 결과를 응답으로만 돌려주며 DB에 저장하지 않습니다. 실제 Slurm job을 제출하므로 GPU 노드가 비어 있을 때 실행하세요.

```bash
curl --max-time 7300 -X POST http://127.0.0.1:8000/auto-label \
  -H 'Content-Type: application/json' \
  -d '{"scene_name":"<scene 이름>","class_mode":8}'
# 예: -d '{"scene_name":"scene-0061","class_mode":8}'
```

## 4. 환경변수

|변수|기본|의미|
|---|---|---|
|VESPA_EXECUTOR|local|`local` 또는 `ssh`|
|VESPA_SSH_TARGET|(필수)|`user@host` 또는 ssh config 별칭|
|VESPA_SSH_PORT|22 (overlay)|비우면 ssh 기본/config 사용|
|VESPA_SSH_KEY / VESPA_SSH_KNOWN_HOSTS|overlay가 `/run/secrets/vespa-ssh/*`로 설정|비우면 ssh 기본값|
|VESPA_SSH_REMOTE_ROOT|(필수)|원격 VESPA 레포 절대 경로|
|VESPA_SSH_EXP|p_final|`configs/vlm/<EXP>.yaml`, 출력 경로의 exp 이름|
|VESPA_SSH_SBATCH_SCRIPT|pseudo_scenes_lowmem.sh|원격 루트 기준 sbatch 스크립트|
|VESPA_SSH_POLL_SECONDS|30|`squeue` 조회 간격|
|VESPA_SSH_COMMAND_TIMEOUT|120|SSH 명령 1회 상한(초)|
|VESPA_TIMEOUT_SECONDS|7200|큐 대기를 포함한 전체 상한. 넘으면 `scancel`|

## 5. 오류와 한계

- 503 `VESPA_LAUNCH_FAILED`: SSH 접속/`sbatch` 실패. 503 `VESPA_REMOTE_UNREACHABLE`: 실행 중 SSH 또는 Slurm 조회가 5회 연속 실패(원격 job은 계속될 수 있음). 502 `VESPA_EXECUTION_FAILED`: job이 끝났지만 새 출력이 없음(취소 포함) → run 로그의 Slurm 로그 tail 확인. 504 `VESPA_TIMEOUT`: 큐 대기를 포함해 `VESPA_TIMEOUT_SECONDS` 초과 시 `scancel` 후 반환.
- 여전히 동기 HTTP입니다. GPU 노드가 바쁘면 큐 대기도 timeout에 포함되므로 `AUTO_LABEL_READ_TIMEOUT`을 `VESPA_TIMEOUT_SECONDS`보다 길게 유지하세요.
- 출력 경로가 scene별로 고정이라, 이 서버 밖에서 같은 scene/EXP를 동시에 실행하면 결과를 구분할 수 없습니다. 이 서버 안에서는 lock으로 한 번에 하나만 실행합니다.
- 결과 사본과 `execution.log`(명령, Slurm 상태, 로그 tail)는 `/results/<run_id>/`에 남습니다.
- `kex_exchange_identification: Connection reset by peer`는 인증 전에 서버가 연결을 끊은 것입니다. 짧은 시간에 여러 번 접속하면 일시적으로 막힐 수 있으니 1~2분 뒤 다시 시도하세요. 실행 중 자주 나면 `VESPA_SSH_POLL_SECONDS`를 늘리세요.

## 6. 검증

- Spring `POST /api/auto-label/jobs`(scene-0061, 8class) → ai-server → seraph Slurm job → 결과 복사·검증 → DB 저장 → `COMPLETED` 확인. 39 sample 전부, 박스 985개(pedestrian 552, car 196, truck 113, motorcycle 37, construction_vehicle 31, bus 26, bicycle 22, trailer 8), `GET /api/auto-label/jobs/{id}/results`로 조회. [Docker 통합 기록](../docs/docker-integration.md)의 local 실행 결과와 총 박스 수가 같고 car/truck 1개만 다름.
- 이 실행은 seraph에 남은 이전 VESPA 중간 결과를 재사용해 약 65초 걸렸습니다. 캐시 없는 scene의 전체 처리 시간은 별도 확인이 필요합니다.
