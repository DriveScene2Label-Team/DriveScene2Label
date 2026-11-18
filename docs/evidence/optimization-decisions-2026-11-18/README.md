# 사용자 시험·운영 설정·비용·모델 첫 로딩 증거

2026-11-18 KST. [의사결정 문서](../../optimization-decisions-and-costs-2026-11-18.md)의 근거다. `manifest.json`은 선택한 원본과 Git용 파일의 SHA256을 기록한다. 원본은 `.local/hybrid/experiments/20261118T101633Z-cost-and-parallel/`에 보존한다. 계정 전체 청구액, 인증 정보, 원본 데이터/모델은 내보내지 않았다.

| 파일 | 범위 |
|---|---|
| [user-upload-baseline.json](user-upload-baseline.json) | 4.168GB single PUT 완료·dataset 22/10씬·CLIP 2,424장 완료 API. 인덱싱 마지막 타이머 누락 명시 |
| [browser-route-proof.json](browser-route-proof.json) | 인증 upstream/backend 조각 요청 1,043개 상관관계. 정확한 브라우저 주소/화면 검증 아님 |
| [parallel-activation.json](parallel-activation.json) | 유휴 상태 확인, backend만 재생성, multipart opt-in true. AI 시작 시각 보존 |
| [job14-model-load.md](job14-model-load.md) · [JSON](job14-model-load.json) | job 14의 첫 모델 접근과 이후 접근. **19:43 중간 관측**, 완료 성능/3D 품질 증거 아님 |
| [job14-stage-snapshot.jsonl](job14-stage-snapshot.jsonl) | 해당 시점까지의 allowlist runner 원본 이벤트. DINOv2 getter는 구버전에서 미측정 |
| [resource-snapshot.json](resource-snapshot.json) | GPU/WSL 메모리 단일 관측. host RAM 원인·swap thrashing 입증 아님 |
| [post-activation-http.json](post-activation-http.json) | 공개 200/익명 API 401. host 8000 연결 실패와 AI 내부 health 200 후속 확인을 함께 보존 |
| [local-validation.json](local-validation.json) | hybrid 52개 중 50 통과·2 gateway 제외, 컴파일·diff 확인. host pytest 미설치로 stage 테스트는 CI에서 실행 |
| [cost-inputs/selected-prices.json](cost-inputs/selected-prices.json) | AWS Price List의 선택 SKU·단위·tier·유효일. 계정 실제 할인 가격 아님 |
| [cost-inputs/cost-scenarios.json](cost-inputs/cost-scenarios.json) | Decimal 산술·730시간·GB/GiB·multipart 요청/전송 가정·제외 비용 |
| [RDS 사양](cost-inputs/rds-configuration.json) · [S3 current](cost-inputs/s3-current-objects.json) · [S3 versions](cost-inputs/s3-all-versions.json) | 19:17 가격 산정 시점의 실제 사양/용량. 이후 새 사용자 원본 저장 증가분 제외 |

동작 중 수집기는 `.local/hybrid/measurements/20261118T091728Z/`의 report/events를 계속 갱신한다. 이 폴더는 고정 스냅샷이며 완료했다고 꾸미지 않는다. 다음 비교는 새 증거 폴더에서 저장한다. 상주 모델 worker는 아직 구현·배포하지 않았고, 새 DINOv2 getter 타이머도 진행 중 AI 컨테이너에는 적용하지 않았다.
