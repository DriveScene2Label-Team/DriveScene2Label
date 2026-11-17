# R1 / R2: 실제 Grounding ONNX·추론 엔진 호환성

동일 HF checkpoint의 실제 한 카메라·`car.` 입력으로 수행한 고정 shape probe다. 전처리는 graph 밖이다. production pip 환경과 서빙 모델은 변경하지 않았다.

## 단계별 실행

- {"phase": "export", "exporter": "dynamo", "exit_code": 1, "remote_directory": "/results/experiments/20261117T181124Z-runtime/dynamo"}
- {"phase": "export", "exporter": "legacy", "exit_code": 1, "remote_directory": "/results/experiments/20261117T181124Z-runtime/legacy"}
- {"phase": "ort_and_trt", "status": "not_executed_no_valid_exported_graph"}

### dynamo/export-failure.json

`TorchExportError`: Failed to export the model with torch.export. [96mThis is step 1/3[0m of exporting the model to ONNX. Next steps:
- Modify the model code for `torch.export.export` to succeed. Refer to https://pytorch.org/docs/stable/generated/exportdb/index.html for more information.
- Debug `torch.export.export` and submit a PR to PyTorch.
- Create an issue in the PyTorch GitHub repository against the [96m*torch.export*[0m component and attach the full error stack as well as reproduction scripts.

## Exception summary

<class 'torch.fx.experimental.symbolic_shapes.GuardOnDataDependentSymNode'>: Could not extract specialized integer from data-dependent expression u0 (unhinted: u0).  (Size-like symbols: u0)


Caused by: (pt/vespa-env/lib/python3.12/site-packages/transformers/models/grounding_dino/modeling_grounding_dino.py:2046 in generate_masks_with_special_tokens_and_transfer_map)
For more information, run with TORCH_LOGS="dynamic"
For extended logs when we create symbols, also add TORCHDYNAMO_EXTENDED_DEBUG_CREATE_SYMBOL="u0"
If you suspect the guard was triggered from C++, add TORCHDYNAMO_EXTENDED_DEBUG_CPP=1
For more debugging help, see https://docs.google.com/document/d/1HSuTTVvYH1pTew89Rtpeu84Ht3nQEFTYhAX3Ypa_xJs/edit?usp=sharing

For C++ stack trace, run with TORCHDYNAMO_EXTENDED_DEBUG_CPP=1

The error above occurred when calling torch.export.export. If you would like to view some more information about this error, and get a list of all other errors that may occur in your export call, you can replace your `export()` call with `draft_export()`.

(Refer to the full stack trace above for more information.)

### legacy/export-failure.json

`UnsupportedOperatorError`: Exporting the operator 'aten::__ior_' to ONNX opset version 18 is not supported

엔진 export/parse 실패는 배포나 속도 향상으로 계산하지 않는다. 성공하더라도 host→GPU→host raw forward 경계이며 서버 HTTP·SAM·3D 파이프라인과 구분한다. 공식 TAO 경로는 참고 자료이며 다른 checkpoint로 바꾼 수치를 같은 모델의 엔진 개선으로 표현하지 않는다.
