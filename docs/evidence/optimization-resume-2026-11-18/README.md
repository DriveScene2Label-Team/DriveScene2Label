# 후속 최적화 검토용 증거

원본에서 선택한 **229개 파일, 2,632,451바이트**다. [manifest.json](manifest.json)은 원본/공개본 SHA256, 원래 위치와 공개 위치를 연결한다. JSON 정렬·절대 저장소 경로 치환·LF 변환 외에 측정값을 바꾸지 않았다. 기존 첫 실행 증거 폴더는 그대로 보존했다.

[해석·문제 정의·선택 이유·적용/보류](../../optimization-resume-2026-11-18.md)를 먼저 읽는다. 원본 로그의 UTC 시각과 문서의 KST를 구분한다. 단계별 기본 report에 이벤트 0이 있어도 별도 프로세스 결과 JSON까지 미실행이었다는 뜻은 아니다.

| 케이스 | 확인할 기록 | 해석 범위 |
|---|---|---|
| R1 빈 검출 | [CUDA 진단](measurements/20261118T053436Z/cuda/diagnostic.json) | 빈 검출의 일치는 품질 통과가 아님 |
| R1 6카메라 | [대응 결과](measurements/20261118T053854Z/detections/comparison.json) | 자동차 6개. 전체 클래스/3D 아님 |
| R2 | [빌드](measurements/20261118T053959Z/trt/trt-build.json), [시간·raw 비교](measurements/20261118T053959Z/trt/trt-result.json), [6카메라](measurements/20261118T054437Z/detections/comparison.json) | TRT 실행 성공, 수치 차이로 운영 교체 보류 |
| S2 실패 | [client 계약](measurements/20261118T054546Z/failure-analysis.json), [StreamingBody 계약](measurements/20261118T054724Z/failure-analysis.json) | 예전 running 상태는 실패 기록 누락 버그. 원본을 고치지 않고 sidecar 추가 |
| S2 성공 | [실험·SHA·정리](measurements/20261118T054854Z/s3-transfer-experiment.json), [요청/재시도](measurements/20261118T054854Z/s3-requests.jsonl) | 109.7MB Python SDK 전송. Java 4GB 서비스 결과 아님 |
| Q2 단계 비교 | [auto/custom/generic/최종 요약](operations/query-cases-summary.json), [최종 비교·정제한 plan](measurements/20261118T060849Z/query-comparison.json), [준비문 카운터](measurements/20261118T060849Z/query-output/q2-global-TOP_K_AVERAGE-prepared-statements.json) | 4회×54쌍 SQL 결과 일치. raw plan의 벡터 literal은 공개 제외 |
| Q3 pilot/보강 | [pilot](measurements/20261118T061354Z/clip-serving/comparison.json), [보강](measurements/20261118T062125Z/clip-serving/comparison.json), [요청별 값·출력 해시](measurements/20261118T062125Z/clip-serving/events.jsonl), [자원](measurements/20261118T062125Z/resources.jsonl) | 288+1,152쌍. no-hit 시간 차이는 캐시 효과로 해석하지 않음 |
| 실제 검색 HTTP | [기준](measurements/20261118T061542Z/baseline/summary.json), [후보·54쌍 품질](measurements/20261118T061542Z/optimized/summary.json), [447개 단계 이벤트](measurements/20261118T061542Z/events.jsonl) | loopback/warm/repeated, 공개 인증·p95 아님 |
| 회귀 | [테스트 요약](operations/test-summary.json) | mock/실제 GPU/임시 DB 시험 구분 |
| 종료 | [RDS](operations/rds-final-state.json), [로컬](operations/local-final-state.json), [유휴 상태](operations/operations-quiesced.json) | 원본 보존, 새 임시 자원만 정리 |

stdout/stderr·전체 SQL/HTTP 응답·raw 벡터/plan·이미지·가중치·엔진은 로컬 측정/결과 볼륨에 남긴다. credential·cookie·서명 URL은 공개하지 않는다. [operations/manifest.json](operations/manifest.json)의 Git pending 항목은 증거를 내보낸 당시의 상태이며 이후 push/CI 상태와 구분한다. Vercel 공유 링크 생성 가능성이 있는 URL 도구는 자동 검토에서 거절되어 [프로젝트 메타데이터](operations/vercel-project-state.json)만 확인했다.
