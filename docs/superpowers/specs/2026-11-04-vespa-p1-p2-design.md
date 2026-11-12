# VESPA P1/P2 — barrier·traffic cone, occlusion filter (2026-11-04)

## 목표와 결정

- 목표: 웹에서 눈으로 볼 때 예측 박스 품질 향상(지표 보고가 아니라 시각 품질 우선).
- 사용자 결정: VESPA 소스 수정 허용. 수정본은 우리 레포 `ai-server/vespa-patches/*.patch`에 두고 Docker·Colab 모두 고정 commit `acb2b6e` checkout 후 같은 `apply.sh`로 적용한다.
- 이번 범위: P1(클래스 추가), P2(가려진·너무 깊은 점 제거). P3(가까운 덩어리 선택)는 앞을 가린 물체·지면 잔여·큰 차 분할 위험과 P2와의 중복 때문에 제외, P4(평균 대신 최소 길이로 키우기)도 이번엔 제외.
- "달리는 차는 현재 순간 점만"은 VLM 경로가 이미 프레임마다 sweep 1개만 쓰므로 변경 없음.

## 근거 (scene-0061, 8class, ego 50 m 이내·LiDAR 점 ≥1 GT, 같은 클래스 중심 2 m 매칭)

|클래스|GT|recall|관찰|
|---|---|---|---|
|barrier / traffic_cone|1068 / 458|0 / 0|8class에 클래스 자체가 없음(전체 GT의 52%)|
|truck|108|0.55|21대 근처 예측 없음(점 적은 원거리), 21대 다른 클래스, 12대 2–6 m 어긋남(79%가 ego 반대쪽으로 밀림)|
|construction_vehicle|43|0.28|어긋난 예측의 89%가 먼 쪽, 길이 +3.0 m(평균 길이로 키운 결과 = P4 원인)|

원인 위치: `segmentation_reprojection.py`가 마스크 안 점을 깊이와 무관하게 모두 사용 → 배경·뒤 물체 점이 박스에 섞임.

## P1 — barrier, traffic cone

- `p_final.yaml` 프롬프트 `barrier`, `traffic cone`; `velocity_ref_types` 추가.
- `8class.yaml`: classes·mapping_nuscenes(`movable_object.barrier/trafficcone`)·truckscenes·sam. 1/3class는 null, `get_scene_pseudo_annotations_by_mapping`이 None을 건너뜀.
- `common_obj_infos.yaml`: mini GT p5/중앙값/p95(barrier n=1770: L 1.85/2.05/3.3, W 0.4/0.65/0.75, H 0.9/1.05/1.25; cone n=803: L 0.35/0.45/0.85, W 0.35/0.45/0.55, H 0.65/0.75/1.3). 속도 0.3 m/s(< yaw 임계 0.5).
- 우리 쪽: V13 migration(CHECK 확장), `AutoLabelService.classes(8)`, `vespa_service.CLASSES[8]`, `frontend/src/lib/classes.ts`(목록·색·GT 비교). `classMode=8`/`8class` 이름 유지.

## P2 — visibility filter

- `src/pointcloud/visibility_filter.py`(numpy만): 카메라 깊이 계산, 8 px 칸 z-buffer(가장 가까운 점 + 1.5 m 초과 제거), 깊이 5백분위 기준 `hypot(length_max,width_max)` 초과 제거, 전부 제거 시 원래 마스크 유지.
- `segmentation_reprojection.py`에서 마스크 점 선택 직후 적용. `reprojection.visibility_filter.enabled`가 없거나 false면 upstream 동작.

## 검증

- Mac: `ai-server/tests/test_vespa_patches.py`(patch 안 새 파일을 그대로 실행해 단위 검사 + `VESPA_SRC` 지정 시 깨끗한 checkout 적용), 합성 장면에서 patched `reproject_lidar_to_segmentation` 실행(upstream 박스 20 m → P2 2.4 m 트럭 면만), Spring 테스트(barrier/cone 저장), 프론트 단위 테스트.
- 실행(2026-11-05, Colab GPU): v1.0-mini 10개 씬 전체를 패치 적용 상태로 실행. 결과는 `vespa-labels-ds2l-p1-p2`(Drive)로 분리, 이전 결과는 `.local/colab/results-baseline-upstream`에 보존.
  - 8class box 수(10개 씬): 원본 7,740 → 패치 9,128. barrier 1,147, traffic_cone 445 추가. 기존 클래스는 소폭 감소(car 3,136→3,056, pedestrian 2,854→2,827, truck 714→664), 0002 필터 영향으로 추정.
  - 웹 화면: scene-0061 결과(1,306 box)를 Colab shim으로 받아 작업대에서 표시 확인.
- 미실행: GT 대비 정확도 비교(클래스별 검출 품질, 0002 필터 효과)와 ver2 rigid 후처리를 함께 적용한 실행.
