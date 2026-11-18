# Java S3 검토용 증거

[결론·구현·상황별 선택](../../s3-java-optimization-2026-11-18.md) · [보고서](review/report.md) · [쌍별 비교](review/paired-comparison.json) · [테스트 이력](review/test-history.json)

로컬 원본은 `.local/hybrid/experiments/20261118T072013Z-s3-java/`에 보존했다. `manifest.json`은 각 선택 파일의 원본/내보낸 SHA-256과 변환을 기록한다. 실제 파일 inventory·압축 파일·모델·DB 덤프·자격증명은 포함하지 않는다.

- `review/summary.json`: 완료·중단·단독 관측을 나눈 결과. 재부팅 전 2쌍과 후 1쌍의 합친 중앙값은 기술 통계이며 안정적인 개선 주장이 아니다.
- `pilot`, `faults`, `large`, `post-reboot-pair`, `threshold`: 원래 실행 manifest와 실제 HTTP 시도 JSONL. `large`의 중단 상태는 그대로다.
- `reboot-recovery/result.json`: 실제 재부팅 잔여 73파트의 소유 범위 정리. 주입 SIGKILL과 별도 사건이다.
- `conditions-followup.json`: 재부팅, 배포 준비와 RDS 시작, 부분 자원 수집 경계. 초기 manifest의 “RDS stopped” 문구를 후속 상태 전체로 해석하지 않는다.
- `measured-java-source.json`, `measured-controller-source.json`: 첫 실험에서 실제 사용한 소스. 최종 코드와 달랐던 64MiB 강제 분기 조건을 재현할 수 있다.
- `aws-multipart-setup`: 정책 축소·Access Analyzer·기존 설정/readback. lifecycle의 다음 날 실행을 관측한 증거는 아니다.
- `app-reset`: private dump를 격리 DB에 실제 복원한 33테이블 내용/22시퀀스 비교와 초기화 후 검증. S3 원본 26개 보존. 덤프 파일 자체는 보호된 PC 경로에만 있다.
- `gpu-health.json`, `scoped-capabilities.json`, `local-readiness.json`: 재부팅 후 작은 CUDA 계산, 보존 원본 범위의 VESPA 런타임 점검, 빈 앱 목록과 터널 익명 401. 새 전체 씬 품질 시험이나 로그인한 브라우저의 전체 업로드 성공을 뜻하지 않는다.

multipart는 기본값 false다. 실패 처리와 다운로드 완전성·계측을 적용하고, 병렬 전송은 비교 결과의 편차 때문에 선택 옵션으로 유지한다.
