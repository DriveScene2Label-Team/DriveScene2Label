# upload — 정상 API 전체 사이클 검증

경로: 127.0.0.1 HTTP 클라이언트 → 로컬 backend/GPU → 기존 서울 RDS·S3. 공개 Vercel·브라우저 전송 시험은 아니다. 중첩된 단계 시간을 합산하지 않는다.

dataset 21, 10씬, 이미지 2424/2424장 저장. AI 이벤트 2424개.

| 경계 | 초 |
|---|---:|
| 전송 시작→인덱싱 완료 확인 | 850.547 |
| 클라이언트 전송 | 127.937 |
| 서버 COPYING | 19.626 |
| 서버 EXTRACTING | 68.559 |
| 서버 STORING_ORIGINAL | 362.158 |
| 서버 IMPORTING_METADATA | 12.165 |
| 서버 TOTAL | 462.510 |
| CLIP_INDEX 시작→완료 | 253.359 |

이미지별 Source·exists·AI·저장은 events.jsonl에 분리되어 있다. 전체 소요시간에는 10초 polling 지연이 포함된다. 이 전체 원본 1회는 규모 확대 동작 확인이며 작은 반복용 C1이나 과거 C0와 동일 조건의 전후 비교가 아니다. 저장 벡터·검색 품질은 별도 전체 인덱스 비교 보고서에서 검증한다.

최종 판정: **통과**. 로그 7,106개, 수집 오류 0개, 실패 이벤트 0개.

## 증거와 도구 선택

정상 API는 실제 worker·저장 경로 검증을 위해, 구조화 JSONL과 자원 표본은 단계와 경쟁 조건을 남기기 위해 사용했다. 명령·소스 해시·이미지 digest·클라이언트 출력은 같은 폴더에 보존한다. 비밀번호·쿠키·전체 환경변수는 수집하지 않는다.
[세부 타이밍](report-stage-timings.md) · [구조화 이벤트](events.jsonl) · [자원 표본](resources.jsonl) · [실행 결과](execution-summary.json) · [요약 JSON](cycle-summary.json)
