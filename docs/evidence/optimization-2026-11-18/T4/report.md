# T4: CPU 스레드 전체 씬 검증

| 항목 | 결과 |
|---|---|
| 과거 1스레드 / 새 2스레드 | 2173.204 / 1907.406초 |
| 234개 검출 완전 일치 | True |
| 최종 3D 완전 일치 | False |
| GT 계산 결과 일치 | True |

결정: 전체 결과 보존 기준 미달로 운영 native 스레드 1 유지. 시간 비교는 과거 기준선이므로 인과적 개선율을 주장하지 않는다.

39프레임·1,308박스 중 한 박스의 9개 수치가 달랐다. 검출·GT 요약 지표가 같아도 모든 3D 필드가 같다는 뜻은 아니다. 스레드 수에 따른 중간 연산 차이의 발생 지점은 추가 분리가 필요하며 원인을 단정하지 않는다.

차이 목록은 `scene-quality-with-gt.json`의 `output_regression.first_differences`, 원본은 `baseline/final-result.json`과 `reuse/final-result.json`에 보존했다.
