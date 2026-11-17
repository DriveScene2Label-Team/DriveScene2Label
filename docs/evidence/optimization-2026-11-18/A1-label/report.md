# label — 정상 API 전체 사이클 검증

경로: 127.0.0.1 HTTP 클라이언트 → 로컬 backend/GPU → 기존 서울 RDS·S3. 공개 Vercel·브라우저 전송 시험은 아니다. 중첩된 단계 시간을 합산하지 않는다.

dataset 21, job 13, recording 13.
전체 39키프레임·1,308박스를 RDS에서 다시 읽었다. 위치·크기·회전·속도·클래스·점수·attribute·track ID와 프레임별 box 순서를 원본 모델 artifact와 대조했다.
RDS 왕복 품질 판정: `True`. 최종 artifact의 정규화 SHA256도 비교했다. track_frames 등 결과 API가 직접 노출하지 않는 최상위 필드는 이 artifact checksum에 포함된다.
Rerun 전체 파일 17,202,643바이트·SHA256 `f7eca2ecb5e9f67aa80d96f865e6885f483977216a9e58b4f8e4bb6d0ecb332b`. 크기 일치와 HTTP 206 Range 데이터 비교 통과. 모든 sample/예측 ID가 recording에 연결된다.
이는 정상 API·DB·파일 전송 검증이며 브라우저의 시각적 렌더링 확인을 대신하지 않는다. 고정 seed G2의 최적화 전후 3D 품질 검증과도 측정 목적이 다르다.

최종 판정: **통과**. 로그 2,335개, 수집 오류 0개, 실패 이벤트 0개.

## 증거와 도구 선택

정상 API는 실제 worker·저장 경로 검증을 위해, 구조화 JSONL과 자원 표본은 단계와 경쟁 조건을 남기기 위해 사용했다. 명령·소스 해시·이미지 digest·클라이언트 출력은 같은 폴더에 보존한다. 비밀번호·쿠키·전체 환경변수는 수집하지 않는다.
[세부 타이밍](report-stage-timings.md) · [구조화 이벤트](events.jsonl) · [자원 표본](resources.jsonl) · [실행 결과](execution-summary.json) · [요약 JSON](cycle-summary.json)
