# Post-processing: Tracklet 기반 Rigid Box 전파

VESPA-Direct 결과에서 객체가 잘 잡힌 keyframe을 기준으로 정합니다. 그 box의 크기와 yaw offset을 같은 track의 모든 keyframe에 전파합니다. 객체는 rigid로 가정합니다.

- **크기 (L, W, H)**: 기준 box의 값을 그대로 복사합니다.
- **중심**: 각 프레임의 VESPA box bottom center를 그대로 씁니다.
- **yaw**: 앞뒤 프레임 속도의 중앙 차분으로 heading을 구하고, 여기에 `(기준 yaw − 기준 heading)`을 더합니다. 속도가 threshold 미만이면 이전 yaw를 유지합니다.
- **track 간 관계**: 모든 track은 서로 독립적으로 처리됩니다.

원본 코드는 수정하지 않았습니다. 모든 변경은 새 파일과 `_ver2` 파일에 있습니다.

## 추가 파일

| 파일 | 설명 |
|---|---|
| `src/postprocess/rigid_tracklet.py` | tracklet 생성(`build_tracklets`)과 rigid 전파(`propagate`). 실행: `python -m src.postprocess.rigid_tracklet` (self-check) |
| `main_pseudo_vlm_scene_ver2.py` | 실행 진입점. VESPA 01~07 단계 → tracklet → yaw/inflation → 전파 → filter → 라벨 저장 |
| `scripts/render_boxes_on_images_ver2.py` | track 리포트(순도, ID switch, 파편화, GT 오차, track 끊김 표)와 카메라/BEV 렌더링, 전후 비교 |
| `vis_vespa_direct_check_ver2.sh` | sbatch: 파이프라인 실행 → (refs가 없으면) 회귀 검사 → 리포트와 렌더링 |
| `render_front_bev_ver2.sh` | sbatch: CAM_FRONT와 LiDAR BEV만 렌더링. 전후 비교 포함 |
| `refs_scene-0061.json` | 기준 프레임 예시 (T3) |
| `refs_scene-0061_t3_t1.json` | 기준 프레임 예시 (T3 + T1) |
| `Post_processing.md` | 이 문서 |

`_ver2` 파일이 의존하는 파일입니다. 아래 파일은 이번에 함께 올립니다.

| 파일 | 사용처 |
|---|---|
| `main_pseudo_vlm_scene.py` | `vis_vespa_direct_check_ver2.sh`의 회귀 검사 |
| `scripts/render_boxes_on_images.py` | `render_boxes_on_images_ver2.py`가 import |
| `scripts/scene_error_analysis.py` | `render_boxes_on_images_ver2.py`가 import (`yaw_error`) |

## 사용 방법

### 1. JSON에 씬과 기준 프레임 지정

```json
{"scene-0061": {"3": 18, "1": 0}}
```

- 바깥 key는 씬 이름입니다.
- 안쪽 key는 track ID입니다. 리포트와 이미지의 `T3`에서 숫자 `3`만 씁니다.
- 안쪽 value는 기준 keyframe 번호입니다. 이미지 파일 `018.jpg`의 18에 해당합니다.
- JSON에 적지 않은 track은 변경되지 않습니다.

track ID와 keyframe 번호는 refs 없이 실행한 `base` 결과를 보고 고릅니다. `images/8class/<scene>/<keyframe>.jpg`에서 확인할 수 있습니다.

### 2. 실행

#### sh 버전 (SLURM)

```bash
# (1) refs 없이 실행: tracklet + 회귀 검사 + 리포트/이미지. 출력은 outs/vlm/p_final/#rigid/base/
sbatch vis_vespa_direct_check_ver2.sh

# (2) refs를 적용해서 전파. 출력은 outs/vlm/p_final/#rigid/<TAG>/
REFS=refs_scene-0061_t3_t1.json TAG=ref2 sbatch vis_vespa_direct_check_ver2.sh

# (3) 공유용: CAM_FRONT + LiDAR BEV, 전후 비교(빨간 box = 바뀐 box)
TAGS="base ref2" FOCUS="3 1" sbatch render_front_bev_ver2.sh

# 다른 씬: SCENES="scene-0103" ... (환경 변수)
```

#### py 버전

```bash
# 파이프라인 + 전파 (--refs를 생략하면 tracklet만 만들고 box는 원본 그대로)
python main_pseudo_vlm_scene_ver2.py --config configs/vlm/p_final.yaml --scenes scene-0061 \
    --refs refs_scene-0061_t3_t1.json --tag ref2

# 리포트 + 전체 카메라 렌더링
python scripts/render_boxes_on_images_ver2.py --config configs/vlm/p_final.yaml --tag ref2 \
    --mapping 8class --scenes scene-0061 --focus_tracks 3 1

# 리포트만 출력 (track 끊김 표 포함)
python scripts/render_boxes_on_images_ver2.py --config configs/vlm/p_final.yaml --tag base \
    --mapping 8class --scenes scene-0061 --no_images --focus_tracks 3

# CAM_FRONT + BEV, base 위에 ref2의 바뀐 box를 빨간색으로 표시
python scripts/render_boxes_on_images_ver2.py --config configs/vlm/p_final.yaml --tag base \
    --compare_tag ref2 --mapping 8class --scenes scene-0061 --cams CAM_FRONT --focus_tracks 3 1
```

### 출력 파일

`outs/vlm/<exp>/#rigid/<tag>/` 아래에 생성됩니다.

- `labels_<scene>_<mapping>.json`: 라벨 (1class, 3class, 8class)
- `tracks_<scene>.json`: keyframe마다 box 순서대로 나열한 track ID
- `images/<mapping>[_<cams>][_vs_<tag>]/<scene>.mp4`, `<scene>/<keyframe>.jpg`

### 이미지 색상
- **회색**: GT
- **track별 색 (`T<id>`)**: 전파 전 pseudo box. 빨간색은 쓰지 않습니다.
- **빨간색 (`T<id> after`)**: 전파 후 바뀐 box. `--compare_tag`를 줄 때만 표시됩니다.


