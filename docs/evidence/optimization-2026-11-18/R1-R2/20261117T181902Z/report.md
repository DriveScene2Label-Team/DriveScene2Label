# R1 / R2: 실제 Grounding ONNX·추론 엔진 호환성

동일 HF checkpoint의 실제 한 카메라·`car.` 입력으로 수행한 고정 shape probe다. 전처리는 graph 밖이다. production pip 환경과 서빙 모델은 변경하지 않았다.

## 단계별 실행

- {"phase": "export", "exporter": "legacy_bool_or", "exit_code": 0, "remote_directory": "/results/experiments/20261117T181902Z-runtime/legacy_bool_or"}
- {"phase": "ort", "exit_code": 0}
- {"phase": "trt_dependencies", "exit_code": 0}
- {"phase": "trt", "exit_code": 137}

**사용자 요청으로 GPU 컨테이너를 중지했다. TensorRT exit 137은 빌드 중 사용자 중단이며 OOM·엔진 성능 실패의 근거가 아니다. 완성된 엔진·추론 시간·품질 결과는 없다.**

- legacy_bool_or/ort-result.json: median=0.373754초; raw 출력 품질=False. 전체 class·동적 shape·full-scene 검증은 아님.
  실제 profile node 이벤트의 provider 분포: {"CUDAExecutionProvider": 4411, "CPUExecutionProvider": 10}. 개수가 실행시간 비중을 뜻하지 않는다.

- legacy_bool_or PyTorch 기준: 0.438242초, 10회, host tensors -> CUDA forward -> host output arrays.

엔진 export/parse 실패는 배포나 속도 향상으로 계산하지 않는다. 성공하더라도 host→GPU→host raw forward 경계이며 서버 HTTP·SAM·3D 파이프라인과 구분한다. 공식 TAO 경로는 참고 자료이며 다른 checkpoint로 바꾼 수치를 같은 모델의 엔진 개선으로 표현하지 않는다.
