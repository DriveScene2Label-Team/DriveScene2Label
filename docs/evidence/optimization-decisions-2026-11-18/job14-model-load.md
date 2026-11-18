# 모델 로딩 관측

단위: 초. 첫 접근은 로딩 포함 구간이며 디스크 cold 여부와 순수 GPU 전송 시간은 미측정.

## Job 14 / da39e1de-71e0-4ae3-aa7f-20c102fe7a36

| 모델 getter | 첫 접근 | 이후 접근 수 | 이후 중앙값 |
|---|---:|---:|---:|
| detector_model_get | 15.593834 | 1 | 0.000106 |
| sam_model_get | 5.74566 | 1 | 1.3e-05 |
| dinov2_model_get | 미측정 | 0 | 미측정 |

미종료 관측 구간: image_detection_segmentation, grounding_dino_detection

First access is a cold-process candidate, not proof of cold disk/network cache.
Getter timings include construction, cache lookup, I/O and device transfer; CUDA kernels are not separately synchronized.
Missing first access is null, never zero. Missing DINOv2 timing in older runners is unmeasured.
Inclusive stage spans overlap: do not add getters to enclosing detection/feature stages.
Open spans may be running, interrupted or missing their tail; result writing does not prove backend persistence.
