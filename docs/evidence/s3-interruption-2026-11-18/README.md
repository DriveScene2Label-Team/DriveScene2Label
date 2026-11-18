# S3 완료/취소 경쟁 조건 후속 검증

이 폴더는 최초 대용량 성능 실험과 구분되는 안전성 수정 증거다. [문제·원인·수정 경계](../../s3-java-optimization-2026-11-18.md#후속-ci에서-발견한-취소-경쟁-조건).

- [CI 실패 진단](diagnosis.json): 11cde64 / run 44277650231, 원본 실패 아티팩트 SHA 보존.
- [수정 소스 스냅샷](source-snapshot.json), [Java 65개 통과](tests-summary.json): 50회 경합 반복 포함. 첫 실행의 잘못된 클래스명으로 누락된 3개는 별도 실행했다.
- [정상 왕복 2케이스](pilot/manifest.json), [장애 5케이스](faults/manifest.json): 실제 S3, 109,696,439바이트, 성공한 5회 다운로드 SHA 일치. 케이스별 `events.jsonl`에 실제 HTTP와 주입 장애를 구분했다.
- [7개 시험 UUID 정리 검증](cleanup-verification.json): 원본 조회 로그의 해시·응답을 함께 기록. S3 원본 키에 대한 삭제는 하지 않았다.
- [백엔드 교체](backend-deployment.json): 검증 이미지와 실행 이미지 일치, 유지보수 중 모든 작업 0 확인, GPU 재시작·앱 재초기화 없음, 정상 운영 재개.
- [18:57 공개 HTTP 확인](public-http-verification.json): 페이지 200·익명 API 401·Cognito 진입 302. 실제 로그인 후 브라우저 전체 사이클은 미검증이다.

[manifest.json](manifest.json)은 명시적으로 선정한 31개 파일의 원본/내보내기 SHA-256을 기록한다. 원본 경로는 `.local/hybrid/experiments/20261118T072013Z-s3-java/ci-interruption/`이다. 전체 실패 ZIP·Gradle XML·명령 stdout/stderr·Docker 빌드 로그도 로컬에 남겼다. 정리 조회의 `raw_sha256`은 가공 전 원본 로그 해시다.

이 변경은 취소 경계를 보강한다. 이미 전송된 Complete를 원격에서 되돌린다는 보장은 없고, 완료 응답 유실은 기존 attempt/size HEAD 대조로 처리한다. **multipart 기본 false**를 유지하며 기존 4.17GB 측정값을 새 소스의 성능 결과로 재사용하지 않는다.
