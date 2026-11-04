# VESPA wrapper (MVP)

## 2026-11-11 로컬 rigid 후처리 연결

로컬 executor는 기본적으로 팀의 `vespa-remote/main_pseudo_vlm_scene_ver2.py`를 사용한다. 최초 작업은 기존 검출·추적 단계를 실행한 뒤 필터 전 scene/tracklet/config를 작업별 `rigid-cache`에 보관하고, 최종 박스에 `track_id`를 연결한다. upstream checkout 자체는 수정하지 않는다. `VESPA_RIGID_ENABLED=false`는 기존 경로를 선택한다.

Spring의 후처리 작업이 `source_artifact_path`와 `references`(track 번호 → sample token)를 함께 전달하면 새 run에서 기준 크기·yaw 보정을 수행한다. 이미 계산한 detector/segmentation/backbone을 재실행하지 않는다. 입력 artifact는 결과 root 안의 UUID 작업에 한정하고, 버전·dataset root·scene·class mode·SHA-256 manifest를 검사한 서버 생성 캐시만 역직렬화한다. 캐시 파일은 외부 업로드 형식이 아니다. 원본 결과/캐시는 변경하지 않으며 새 작업에도 보정 후 필터 전 상태를 남겨 후속 보정을 이어갈 수 있다.

T1/frame0, T3/frame18은 팀의 특정 씬 예시이며 기본값으로 강제하지 않는다. 실제 프레임에 존재하는 객체만 선택한다. 캐시가 없는 이전 작업은 최초 생성이 필요하다. SSH executor의 후처리는 이번 범위에 포함하지 않는다.

혼합 Compose는 `AI_REQUIRE_GPU=true`다. NVML 조회에 실패하면 capability와 새 GPU 연산 요청을 `GPU_UNAVAILABLE`로 표시한다. 이 검사는 드라이버 장애를 수리하거나 긴 작업의 안정성을 보장하지 않는다. 후처리 알고리즘/캐시 재실행은 실제 VESPA 클래스 기반 fixture에서 확인했고, 신규 전체 씬의 검출 정확도·성능은 별도로 검증해야 한다.

## 구조

`POST /auto-label` -> router -> VespaService -> 별도 VESPA Python subprocess -> vespa_runner.py -> upstream process_scene() -> upstream _get_annotation_dict() -> 최종 JSON -> schema 검증 -> Spring 응답.

VESPA 원본 소스는 수정하지 않습니다. 공식 main_pseudo_vlm.py의 옵션은 `--scenes`이며 `--scene`이 아닙니다. 공식 CLI는 전체 scene 처리가 아닌 경우 submission을 쓰지 않고, writer도 단일 scene export를 제한합니다. 따라서 단순 CLI 호출 후 기존 all JSON을 읽으면 요청 결과를 얻을 수 없습니다.

adapter는 공식 process_scene()로 단일 scene을 계산하고 공식 serializer로 동일한 박스 형식을 내보냅니다. get_out_dir의 출력 base만 subprocess 메모리에서 변경하여 job별 캐시/결과를 격리합니다. 원본 파일은 아래 [patch](#drivescene2label-patch)로만 바꾸며 이전 all JSON 재사용은 없습니다. 사용 중인 upstream 커밋은 acb2b6e8683363795528f049fe0444ef9f3efdb9이며 upstream 함수 API가 바뀌면 adapter 호환성을 다시 확인해야 합니다.

## 서버 설정 (WSL/Ubuntu)

VESPA의 환경은 FastAPI 환경과 별도로 공식 Dockerfile/설치 절차에 따라 준비하세요. API를 추가했다고 Grounding DINO/SAM/DINOv2 및 VESPA의 모든 패키지가 설치되는 것은 아닙니다.

```bash
cd ai-server
source .venv/bin/activate
export VESPA_ROOT="$(pwd)/../.local/VESPA"
# VESPA 패키지를 설치한 환경의 실제 Python 절대 경로로 변경
export VESPA_PYTHON=/path/to/vespa-venv/bin/python
export VESPA_DATA_ROOT=/home/hyuksu/Cap_Project_Data/v1.0-mini
export VESPA_DATASET_VERSION=v1.0-mini
export VESPA_OUTPUT_ROOT="$(pwd)/../.local/vespa-runs"
export VESPA_TIMEOUT_SECONDS=7200
export HF_HOME="$(pwd)/../.local/clip-model-cache"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

VESPA_ROOT는 main_pseudo_vlm.py가 있는 디렉터리입니다. VESPA_PYTHON은 실행 파일 경로이며 activate 명령이 아닙니다. 지정하지 않으면 현재 FastAPI Python을 사용하므로 해당 환경에 VESPA 의존성이 없으면 실행 실패합니다. Python venv symlink 경로를 보존합니다.

VESPA_DATA_ROOT 아래에 dataset version의 scene/sample 등 nuScenes JSON 및 samples/sweeps 센서 파일이 있어야 합니다. dataset version 기본값은 p_final.yaml과 같은 v1.0-trainval입니다. 서버는 고정 configs/vlm/p_final.yaml을 사용하고 데이터 root/version만 서버 환경값으로 override합니다. 요청에서 임의 shell 명령/config/file 경로를 받지 않습니다.

`/health`의 vespa=configured는 repo/config/Python/scene.json/sample.json 파일 확인만 의미하며 GPU·모델·모든 의존성의 실행 성공을 보장하지 않습니다. CLIP은 기존대로 lifespan에서 실제 로딩하며 로딩 실패 시 서버 startup이 실패합니다.

## 요청/응답

```bash
curl --max-time 7300 -X POST http://127.0.0.1:8000/auto-label \
  -H 'Content-Type: application/json' \
  -d '{"scene_name":"scene-0061","class_mode":8}'
```

class_mode는 1/3/8 (기본 8)입니다. 내부 VLM 클래스 설정은 그대로이며 최종 매핑을 선택합니다. 이 API는 기존 sample_tokens 기반 초안 계약을 scene_name/class_mode 계약으로 교체했습니다. Spring이 job을 연결할 때는 job_id와 execution_token을 둘 다 전달하세요. 이 값은 검증 후 그대로 응답하며 AI는 DB를 조회하거나 job 상태를 저장하지 않습니다.

```json
{
  "scene_name":"scene-0061",
  "class_mode":8,
  "job_id":7,
  "execution_token":"00000000-0000-0000-0000-000000000001"
}
```

성공 응답은 run_id, scene_name, class_mode, job_id/execution_token, mapping_name, split, coordinate_frame=WORLD, score_type=VESPA_CONSTANT, meta, results[sample_token], artifact_path, result_checksum을 포함합니다. 빈 sample도 []로 포함합니다. 최종 JSON의 박스 translation=world XYZ 중심(m), size=WLH(m), rotation=WXYZ, velocity=world XY(m/s)이며 detection_score=1.0은 실제 confidence가 아닙니다.

파일 위치:

```text
VESPA_OUTPUT_ROOT/<run_id>/execution.log
VESPA_OUTPUT_ROOT/<run_id>/outs/vlm/p_final/#out_labels/
  vlm_p_final_scene-0061_8class.json
```

artifact_path는 VESPA_OUTPUT_ROOT 기준 상대 경로입니다. Spring의 artifact storage_key와 함께 사용해야 하며 다운로드 URL은 아닙니다. result_checksum은 최종 JSON 전체를 key 정렬/고정 구분자/UTF-8로 정규화한 SHA-256입니다. Spring에서도 같은 규칙을 쓰거나 반환값을 보관해야 합니다.

중간 01_*~07_* 파일은 VESPA의 계산용으로 run 폴더에 남지만 응답/DB 저장 대상이 아닙니다. 결과 파일과 로그는 실패 시에도 보존해 진단할 수 있습니다. 반복 요청은 새로운 run을 생성하므로 재전송 방지는 Spring job 계약에서 처리합니다.

## 오류와 장시간 실행

422=입력 오류, 404=없는 scene, 409=같은 worker의 VESPA 실행 중, 503=설정/metadata/실행 환경 오류, 502=자식 프로세스 실패 또는 최종 JSON 검증 실패, 504=VESPA 실행 제한 초과.

subprocess에는 shell=False 기본값과 인자 배열을 사용합니다. 로그는 파일로 보내고 응답에 stack trace를 노출하지 않습니다. Linux/WSL timeout은 프로세스 그룹을 종료해 자식 실행도 중단합니다. worker 내 lock은 성공/실패/timeout 모두 해제합니다.

MVP는 동기 HTTP입니다. FastAPI의 `def` route가 thread pool에서 대기하므로 event loop를 직접 막지는 않지만 요청 연결과 worker thread는 종료까지 유지됩니다. reverse proxy와 Spring의 auto-label 전용 timeout을 맞춰야 합니다. 기존 text 검색 client의 30초 timeout을 VESPA 호출에 그대로 쓰면 안 됩니다. 클라이언트 연결 종료가 계산 취소를 의미하지 않으며 서버 timeout까지 작업이 계속될 수 있습니다.

workers=1에서 VESPA 동시 실행은 1개로 제한됩니다. 이 lock은 다른 프로세스/서버와 공유되지 않습니다. 기존 CLIP은 GPU에 상주하고 요청 시 VESPA와 GPU를 공유하므로 총 VRAM도 고려해야 합니다.

## subprocess vs import

| 방식 | 장점 | 한계 |
|---|---|---|
| FastAPI 프로세스에서 직접 Python import | 객체 전달 간단, 모델 재사용 가능 | GPU/라이브러리 상태 공유, 의존성 충돌, 실패 격리·강제 timeout 어려움 |
| 별도 subprocess 안에서 Python adapter import | VESPA 환경 분리, 로그/종료 코드, timeout, 원본 무수정 | 실행마다 모델 로딩, 긴 HTTP 대기, 함수 API에 대한 호환성 의존 |

초기 MVP는 현재 구현한 subprocess adapter를 권장합니다. 운영은 Spring에서 PENDING/RUNNING job을 관리하고 queue에 dispatch한 뒤 AI worker가 계산하며 Spring이 결과를 저장하는 구조가 적합합니다. 202 응답과 job 조회/결과 수신 계약 및 durable queue가 필요합니다. FastAPI BackgroundTasks만으로는 서버 재시작에 견디는 작업 큐가 되지 않습니다. 현재 Spring VESPA client, DB 기반 PENDING polling worker, job 상태/결과 조회 API가 구현되어 있습니다. 별도 메시지 큐와 RUNNING crash recovery는 아직 없습니다. [최신 REST 계약](../README_API.md)을 참조하세요.

## 검증

`python -m pytest tests -q`: 기존 CLIP 회귀와 wrapper 테스트. wrapper 테스트는 실제 subprocess를 실행하되 테스트용 VESPA 함수 모듈을 사용합니다. 1/3/8class, 빈 sample, 요청별 결과 분리, coverage/token 검증, 실행 실패, timeout, lock 해제, 409/404/503, HTTP schema 계약을 검증합니다. 실제 VESPA 모델/nuScenes end-to-end 추론 성공과는 별도입니다.

## Docker 실행

컨테이너에는 `/opt/vespa` source와 `/opt/vespa-env/bin/python` 환경이 포함됩니다. 실행 및 모델 다운로드 링크는 [메인 README](../README.md), 실제 검증 결과는 [Docker 통합](../docs/docker-integration.md)을 참조하세요. `VESPA_NUM_THREADS` 기본1로 subprocess BLAS/OMP 스레드 수를 제한하며 CLIP에는 적용하지 않습니다.

## DriveScene2Label patch

2026-11-04부터 VESPA는 고정 commit에 `ai-server/vespa-patches/*.patch`를 번호 순서로 적용해 실행합니다. Docker(`ai-server/Dockerfile`)와 Colab 노트북이 같은 `apply.sh <vespa_dir> <commit>`을 사용하고, commit이 다르거나 checkout이 깨끗하지 않으면 실패합니다. Spring에 저장되는 model_version 기본값은 `acb2b6e…+ds2l-p1-p2`입니다.

|patch|변경|설정|
|---|---|---|
|0001-classes-barrier-cone|GroundingDINO 프롬프트에 `barrier`, `traffic cone` 추가. 8class 출력·nuScenes/truckScenes/SAM 매핑에 `barrier`, `traffic_cone` 추가(1/3class는 null → 출력에서 제외, `assign_labels`가 None을 건너뜀). 크기 사전값은 mini GT(LiDAR 점 있는 barrier 1770, cone 803개)의 p5/중앙값/p95. 정지 클래스라 속도 상한 0.3 m/s(yaw 추정 임계 0.5 m/s 미만)|`grounding_sam.class_names`, `velocity_ref_types`|
|0002-visibility-filter|마스크에 투영된 LiDAR 점 중 ①8px 칸마다 가장 가까운 점보다 1.5 m 이상 뒤의 점(가려진 점) ②물체 앞면(깊이 5백분위)에서 클래스 `hypot(length_max,width_max)`보다 깊은 점을 box fit 전에 제거. 전부 제거되면 원래 마스크 유지. 로직은 numpy만 쓰는 `src/pointcloud/visibility_filter.py`|`reprojection.visibility_filter.{enabled,cell_px,occlusion_margin_m,near_percentile}`; 키가 없으면 upstream 동작|

patch를 바꿀 때는 VESPA clone에서 commit을 만든 뒤 `git format-patch --no-signature --zero-commit acb2b6e..HEAD`로 다시 내보내고 `tests/test_vespa_patches.py`를 실행합니다(`VESPA_SRC=<clone>`이면 깨끗한 checkout 적용까지 확인). reprojection 단계 결과는 npz로 캐시되므로 patch를 바꾼 뒤에는 이전 work/output 폴더를 재사용하지 않습니다.
