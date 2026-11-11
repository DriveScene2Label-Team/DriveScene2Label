# Rerun recording exporter

## 구조

`POST /recordings` -> routers/recording.py -> RecordingService -> 별도 Python subprocess -> services/recording_exporter.py (rerun-sdk 0.38.1) -> `.rrd` + summary.json -> 검증 -> Spring 응답.

AI는 DB에 접근하지 않습니다. Spring이 보낸 sample/pose/calibration/GT/예측 값과 dataset root 아래 LIDAR_TOP `.pcd.bin`만 읽습니다. 전체 계약과 Spring/브라우저 흐름은 [Rerun recording 계약](../docs/rerun-recording.md) 4~6장을 따릅니다.

## 버전

| 환경 | rerun-sdk | 비고 |
|---|---|---|
| AI 기본 환경 (`requirements.txt`) | 0.38.1 | exporter 전용. `@rerun-io/web-viewer@0.38.1`과 같아야 함 |
| VESPA venv (`requirements-vespa.txt`) | 0.21.0 | 변경 없음. `visualize=False` |

VESPA venv는 `--system-site-packages`지만 venv 패키지가 먼저 import됩니다. Docker build에서 두 Python의 `rerun.__version__`을 assert합니다. 응답 `sdk_version`은 exporter가 실제로 import한 버전이며 0.38.1이 아니면 503 `RECORDING_SDK_MISMATCH`입니다. 버전을 올릴 때 `SDK_VERSION`, `export_version`, npm 패키지를 함께 바꿉니다.

## 환경 변수

| 변수 | 기본 | 의미 |
|---|---|---|
| NUSCENES_ROOT (없으면 VESPA_DATA_ROOT) | /data/nuscenes | `lidar.relative_path`의 기준 root |
| RECORDING_OUTPUT_ROOT | `<project>/.local/recordings`, Docker `/recordings` | 결과 root. 응답 `relative_path`의 기준 |
| RECORDING_PYTHON | 현재 Python | exporter 실행 Python 절대 경로 |
| RECORDING_TIMEOUT_SECONDS | 600 | subprocess 상한. 초과 시 프로세스 그룹 종료, 504 |

## entity와 timeline

| entity | 내용 |
|---|---|
| `world` | `ViewCoordinates.RIGHT_HAND_Z_UP` static. 모든 값은 WORLD 미터 |
| `world/lidar` | `.pcd.bin` float32×5의 x,y,z를 sensor→ego(calibration), ego→world(pose) 변환한 `Points3D`. ego z 기준 높이 색(남색→밝은 회색). lidar null이면 빈 batch |
| `world/ego` | ego pose `Transform3D`(sample마다) + static 차량 상자(근사 Renault Zoe 4.08×1.74×1.56 m). lidar null sample은 직전 pose 유지 |
| `world/gt` | `Boxes3D`. half_sizes=[L/2,W/2,H/2] (size_wlh=[W,L,H]), quaternion W,X,Y,Z→x,y,z,w, 노랑 #FFCC4D, label=category_name 또는 `GT` |
| `world/prediction` | `Boxes3D`, 민트 #4FE0D5, label=detection_name. `job_id`가 없으면 기록하지 않고 응답 `entities.prediction=null` |
| `world/labels/{gt,pred,both}` (v3) | 이름표 전용 `Points3D`(labels, show_labels). 출처별로 나눠 앱의 GT/예측 토글이 해당 이름표도 숨긴다(`both`=같은 클래스 GT·예측이 겹친 이름표, 둘 다 꺼질 때만 숨김). GT·예측 `Boxes3D`는 `show_labels=False`로 기록하고 이름은 데이터로만 남긴다(선택·hover용). ego 기준 30 m 안만, 같은 클래스의 GT·예측이 1.5 m 안이면 이름표 하나(흰색), 같은 클래스가 4 m 안에 모이면 `pedestrian ×3`처럼 한 번, 무리의 가장 높은 박스 윗면 0.6 m 위. GT는 8class 비교 분류(미매핑은 category 그대로). lidar가 없는 sample은 ego 위치를 몰라 이름표를 쓰지 않는다. 응답 entities에는 넣지 않는다 |

- timeline: `sample`(sequence=index), `timestamp`(`timestamp_us` 마이크로초 정밀 timestamp). `log_time`은 끕니다.
- 박스가 0개인 sample도 모든 component를 빈 batch로 기록해 latest-at으로 이전 박스가 남지 않습니다.
- instance 순서 = 요청 배열 순서. Spring은 같은 순서로 `gtAnnotationIds`/`predictionIds`를 저장합니다.
- `application_id=drivescene2label`, `recording_id=ds2l-recording-<recording_id>`, recording 이름=scene_name.

## 준비 상태 (/capabilities, 2026-10-05)

`GET /capabilities`의 recording은 exporter Python에서 `import rerun` 버전(0.38.1)과 `RECORDING_OUTPUT_ROOT` 쓰기 가능 여부를 확인해 READY/UNAVAILABLE(`RECORDING_SDK_UNAVAILABLE`, `RECORDING_SDK_MISMATCH`, `RECORDING_OUTPUT_NOT_WRITABLE`, `RECORDING_NOT_CONFIGURED`)을 돌려준다. 결과는 기본 600초 유지된다. CLIP 로딩 실패는 exporter를 막지 않는다.

## 입력 검증과 오류

pydantic(extra=forbid)이 finite 값, size>0, 단위 quaternion(±1e-3), index=0..n-1, 고유 sample_token, timestamp 비감소, job_id 없는 예측 금지를 검사합니다. lidar 경로는 절대경로·`..`·`\`·`:`·root 밖 symlink를 거부합니다. exporter도 같은 기하 검증을 반복합니다.

| 상태 | code |
|---|---|
| 422 | RECORDING_INVALID_REQUEST, RECORDING_INVALID_PATH |
| 404 | RECORDING_LIDAR_NOT_FOUND |
| 503 | RECORDING_NOT_CONFIGURED, RECORDING_SDK_UNAVAILABLE, RECORDING_SDK_MISMATCH, RECORDING_LAUNCH_FAILED |
| 502 | RECORDING_EXPORT_FAILED (손상된 `.pcd.bin` 포함), RECORDING_INVALID_RESULT |
| 504 | RECORDING_TIMEOUT |

오류 body는 `{"detail":{"code","message"}}`이며 이 router의 422도 같은 형식입니다(입력값·stack trace 미노출). 로그는 run 폴더의 `execution.log`에 남습니다.

## 파일

```text
RECORDING_OUTPUT_ROOT/<recording_id>-<execution_token>/
  request.json  summary.json  execution.log  <scene_name>.rrd
```

`.rrd`는 같은 폴더의 임시 파일에 쓴 뒤 `os.replace`로 교체합니다. 같은 execution_token 재요청은 새로 export해 덮어씁니다. `checksum`은 파일 bytes의 SHA-256입니다. `relative_path`는 다운로드 URL이 아니며 Spring content API로만 제공합니다.

## 검증

```bash
python3 -m venv .venv-recording
.venv-recording/bin/pip install fastapi uvicorn pydantic httpx pytest numpy rerun-sdk==0.38.1
.venv-recording/bin/python -m pytest -q tests/test_recording.py
# 브라우저 확인용 합성 recording (nuScenes 아님)
.venv-recording/bin/python tests/recording_fixtures.py --out /tmp/sample-recording
```

테스트는 합성 `.pcd.bin`으로 실제 rerun-sdk export를 실행하고 `rerun.chunk.RrdReader`로 다시 읽어 entity, `sample`/`timestamp` timeline, sample별 GT/예측 instance 수, 빈 sample, half_sizes/quaternion 변환, sensor→ego→world 점 변환을 확인합니다. 경로 거부, lidar 누락 404, 손상 파일 502, timeout 504, SDK 없음 503도 확인합니다. torch가 있으면 `main.py` 연결과 `/health`의 `recording`도 확인합니다.

macOS Python 3.13은 hidden flag가 붙은 `.pth`를 건너뜁니다. 이 저장소 위치에서는 `.venv*` 안의 `rerun_sdk.pth`에 flag가 다시 붙어 `import rerun`이 실패할 수 있으므로 `PYTHONPATH=$PWD/.venv-recording/lib/python3.13/site-packages/rerun_sdk`를 지정해 실행합니다. 테스트는 SDK가 없으면 skip하지 않고 실패합니다. Docker는 Python 3.12입니다.

실제 nuScenes scene recording과 Web Viewer 시간/선택 이벤트는 별도 통합 검증 대상입니다. 결과는 [구현 체크리스트](../docs/frontend-implementation-checklist.md)에 기록합니다.
