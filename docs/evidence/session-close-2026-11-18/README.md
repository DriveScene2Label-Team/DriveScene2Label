# 2026-11-18 마감 증거

[마감 report.md](../../reports/2026-11-18/report.md) · [해시 manifest](manifest.json) · [요약](summary.json).

사용자 job 14 완료, RDS 전체 결과 왕복, 모델 로딩, 계측 마감, G3 사용자 요청 중단을 구분한다. 13개 파일을 명시적 목록으로 내보냈고 원본/내보낸 파일 SHA256을 보존했다. 경로·JSON 표시 형식·LF 변환 외에 측정 값은 바꾸지 않았다.

`interrupted-ground/host.json`의 exit 143은 사용자 종료 요청에 따른 SIGTERM이다. 해당 실험의 속도·품질 판정은 없다. 신규 GPU 상주 비교도 실행하지 않았다. 원본 execution.log, 전체 라벨, 센서 데이터, 자격 증명은 공개하지 않는다.

[종료 확인·중단 부분 로그·테스트 증거](shutdown/manifest.json)를 별도 manifest로 보존했다.
