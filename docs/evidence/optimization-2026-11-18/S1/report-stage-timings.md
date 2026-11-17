# 로컬 계측 결과

수집 시작: 2026-11-17T16:23:17.740312+00:00 · 마지막 수집: 2026-11-17T16:32:38.353156+00:00

중첩된 구간을 합산하지 않습니다. 없는 구간은 미측정입니다. 브라우저 수치는 클라이언트 보고값이며 GPU 커널 시간은 별도 프로파일러가 필요합니다.

관측 이벤트 73개 · 실패 이벤트 0개 · 수집 오류 0개

| 경계 / 문맥 / 상태 / 지표 | 횟수 | 합계 ms | p50 ms | p95 ms | 최대 ms |
|---|---:|---:|---:|---:|---:|
| CACHE / archive_prepare / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / observed / wall_ms | 2 | 369105.0 | 4.0 | 369101.0 | 369101.0 |
| CACHE / extract / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / completed / wall_ms | 2 | 133134.0 | 62330.0 | 70804.0 | 70804.0 |
| CACHE / s3_download / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / completed / wall_ms | 1 | 369100.0 | 369100.0 | 369100.0 | 369100.0 |
| HTTP / /api/datasets / all / observed / wall_ms | 20 | 457.0 | 19.0 | 49.0 | 54.0 |
| HTTP / /api/datasets/{id}/scenes / all / observed / wall_ms | 1 | 28.0 | 28.0 | 28.0 | 28.0 |
| HTTP / /api/datasets/{id}/search-index / all / observed / wall_ms | 1 | 29.0 | 29.0 | 29.0 | 29.0 |
| HTTP / /api/datasets/{id}/stats / all / observed / wall_ms | 2 | 70.0 | 32.0 | 38.0 | 38.0 |
| HTTP / /api/maps/{id}/content / all / observed / wall_ms | 3 | 52.0 | 13.0 | 27.0 | 27.0 |
| HTTP / /api/samples/{id} / all / observed / wall_ms | 1 | 30.0 | 30.0 | 30.0 | 30.0 |
| HTTP / /api/scenes/{id}/samples / all / observed / wall_ms | 1 | 30.0 | 30.0 | 30.0 | 30.0 |
| HTTP / /api/sensor-files/{id}/content / all / observed / wall_ms | 36 | 502696.0 | 11.0 | 70838.0 | 431452.0 |
