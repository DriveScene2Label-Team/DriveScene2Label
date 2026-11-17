# R1 / R2: 실제 Grounding ONNX·추론 엔진 호환성

동일 HF checkpoint의 실제 한 카메라·`car.` 입력으로 수행한 고정 shape probe다. 전처리는 graph 밖이다. production pip 환경과 서빙 모델은 변경하지 않았다.

## 단계별 실행

- {"phase": "export", "exporter": "legacy_bool_or", "exit_code": 1, "remote_directory": "/results/experiments/20261117T181435Z-runtime/legacy_bool_or"}
- {"phase": "ort_and_trt", "status": "not_executed_no_valid_exported_graph"}

### legacy_bool_or/export-failure.json

`ImportError`: cannot import name '_type_utils' from 'torch.onnx' (/usr/local/lib/python3.12/site-packages/torch/onnx/__init__.py)

엔진 export/parse 실패는 배포나 속도 향상으로 계산하지 않는다. 성공하더라도 host→GPU→host raw forward 경계이며 서버 HTTP·SAM·3D 파이프라인과 구분한다. 공식 TAO 경로는 참고 자료이며 다른 checkpoint로 바꾼 수치를 같은 모델의 엔진 개선으로 표현하지 않는다.
