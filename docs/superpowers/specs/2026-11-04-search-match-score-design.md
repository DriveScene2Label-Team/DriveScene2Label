# 검색 일치도 matchScore (2026-11-04)

- 요청: CLIP 유사도 0.2~0.3이 사용자에게 신뢰를 떨어뜨리므로 0~100 일치도로 보여 준다. 기존 score 유지, 새 필드 `matchScore`.
- 기준점: nuScenes scene 설명으로 보정(상한 = 자기 설명 점수 중앙값, 하한 = 관련 없는 문장 p90), aggregation별, `application.properties`(`search.match-score.*`). 재현은 `scripts/calibrate_match_score.py`.
- 화면: 카드 "일치도 65점", 툴팁에 원래 코사인 값과 "확률이 아님". % 금지. matchScore가 없으면 기존 "유사도 점수 0.xxx".
- 범위 밖(사용자 지시): 신뢰도·변별도·z-score·confidence 필드.
- 규칙 문구: CLAUDE.md와 FR-04에 "보정된 일치도는 허용하며 근거와 기준값을 문서화한다".
- 검증: Spring(`MatchScoreCalibrationTests`, `SceneSearchTests` matchScore), 프론트 단위(mapper·tooltip·% 없음), Playwright e2e(desktop-1440). 실제 서버 화면 확인은 이 브랜치로 backend 재빌드 후.
- 상세 근거·측정값: [docs/search-match-score.md](../../search-match-score.md).
