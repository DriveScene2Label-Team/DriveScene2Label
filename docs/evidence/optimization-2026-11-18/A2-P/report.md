# A2 / P1–P3: Grounding Attention·정밀도

동일 6카메라·10클래스·60 forward, seed 42, native 스레드 1. 각 모드 3회 교차 순서의 새 프로세스. 로딩·warmup은 처리 시간에서 제외한다.

| 모드 | 완료 반복 | 검출 중앙값 초 | 최대 할당 VRAM MiB | FP32와 출력 완전 일치 |
|---|---:|---:|---:|---|
| fp32 | 3 | 30.198 | 2207.2 | 기준 |
| fp16 | 0 | 측정 없음 | — | — |
| bf16 | 0 | 측정 없음 | — | — |
| amp_fp16 | 3 | 22.428 | 2595.8 | False |
| amp_bf16 | 3 | 22.481 | 2592.2 | False |
| tf32 | 3 | 24.575 | 2207.2 | False |

## 실제 실패·미지원 시도

- `attention-r0-sdpa`: exit 1; 해당 폴더의 events.jsonl / detector.stderr.log 보존. 성공 실행 시간으로 계산하지 않음.
- `attention-r0-flash_attention_2`: exit 1; 해당 폴더의 events.jsonl / detector.stderr.log 보존. 성공 실행 시간으로 계산하지 않음.
- `precision-r0-fp16`: exit 1; 해당 폴더의 events.jsonl / detector.stderr.log 보존. 성공 실행 시간으로 계산하지 않음.
- `precision-r0-bf16`: exit 1; 해당 폴더의 events.jsonl / detector.stderr.log 보존. 성공 실행 시간으로 계산하지 않음.

## 출력 차이

- amp_fp16 반복 0: exact=False, 클래스별 개수 일치=True, 누락/추가=0/0, 최소 matched IoU=0.9947916666666666, 최대 score 차이=0.008754581212997437.
- amp_bf16 반복 0: exact=False, 클래스별 개수 일치=False, 누락/추가=1/0, 최소 matched IoU=0.9818181818181818, 최대 score 차이=0.019078701734542847.
- tf32 반복 0: exact=False, 클래스별 개수 일치=True, 누락/추가=0/0, 최소 matched IoU=0.9993714644877436, 최대 score 차이=0.003903806209564209.
- tf32 반복 1: exact=False, 클래스별 개수 일치=True, 누락/추가=0/0, 최소 matched IoU=0.9993714644877436, 최대 score 차이=0.003903806209564209.
- amp_bf16 반복 1: exact=False, 클래스별 개수 일치=False, 누락/추가=1/0, 최소 matched IoU=0.9818181818181818, 최대 score 차이=0.019078701734542847.
- amp_fp16 반복 1: exact=False, 클래스별 개수 일치=True, 누락/추가=0/0, 최소 matched IoU=0.9947916666666666, 최대 score 차이=0.008754581212997437.
- amp_fp16 반복 2: exact=False, 클래스별 개수 일치=True, 누락/추가=0/0, 최소 matched IoU=0.9947916666666666, 최대 score 차이=0.008754581212997437.
- tf32 반복 2: exact=False, 클래스별 개수 일치=True, 누락/추가=0/0, 최소 matched IoU=0.9993714644877436, 최대 score 차이=0.003903806209564209.
- amp_bf16 반복 2: exact=False, 클래스별 개수 일치=False, 누락/추가=1/0, 최소 matched IoU=0.9818181818181818, 최대 score 차이=0.019078701734542847.

결정: 운영 dtype/attention 유지. 작은 입력의 속도·greedy IoU는 전체 씬 3D/GT 품질이나 mAP를 대체하지 않는다. 출력이 달라지는 정밀도는 후속 정확도 허용 기준과 다중 씬 검증이 필요하다. INT8/INT4 calibration·양자화는 이 FP16/BF16 시험과 다르며 이번에 실행하지 않았다.
