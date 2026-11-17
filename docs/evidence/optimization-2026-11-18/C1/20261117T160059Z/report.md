# 로컬 계측 결과

수집 시작: 2026-11-17T16:00:59.288906+00:00 · 마지막 수집: 2026-11-17T16:02:35.251130+00:00

중첩된 구간을 합산하지 않습니다. 없는 구간은 미측정입니다. 브라우저 수치는 클라이언트 보고값이며 GPU 커널 시간은 별도 프로파일러가 필요합니다.

관측 이벤트 1055개 · 실패 이벤트 0개 · 수집 오류 0개

| 경계 / 문맥 / 상태 / 지표 | 횟수 | 합계 ms | p50 ms | p95 ms | 최대 ms |
|---|---:|---:|---:|---:|---:|
| CLIP / boundary / 19 / observed / ai_ms | 474 | 35225.0 | 71.0 | 87.0 | 301.0 |
| CLIP / boundary / 19 / observed / cache_ms | 474 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 19 / observed / exists_ms | 474 | 3283.0 | 7.0 | 9.0 | 28.0 |
| CLIP / boundary / 19 / observed / source_ms | 474 | 3450.0 | 7.0 | 10.0 | 18.0 |
| CLIP / boundary / 19 / observed / storage_ms | 474 | 4922.0 | 10.0 | 15.0 | 91.0 |
| CLIP / boundary / 19 / observed / total_ms | 474 | 47653.0 | 97.0 | 117.0 | 343.0 |
| CLIP_INDEX / batch_loaded / 19 / batch_loaded / jdbc_ms | 9 | 525.0 | 65.0 | 80.0 | 80.0 |
| CLIP_INDEX / completed / 19 / completed / wall_ms | 1 | 48657.0 | 48657.0 | 48657.0 | 48657.0 |
| CLIP_STAGE / image_embed / all / observed / decode_ms | 474 | 2076.5 | 4.2 | 5.8 | 9.4 |
| CLIP_STAGE / image_embed / all / observed / gpu_ms | 474 | 19939.9 | 40.9 | 46.5 | 58.3 |
| CLIP_STAGE / image_embed / all / observed / handler_ms | 474 | 31344.2 | 65.0 | 77.0 | 90.6 |
| CLIP_STAGE / image_embed / all / observed / lock_wait_ms | 474 | 63.1 | 0.1 | 0.2 | 1.2 |
| CLIP_STAGE / image_embed / all / observed / preprocess_ms | 474 | 9016.6 | 17.8 | 26.6 | 44.4 |
| DB_IMPORT / advisory_lock / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / observed / wall_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / attribute / 19 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / attribute / 19 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / calibrated_sensor / 19 / observed / jdbc_ms | 1 | 14.0 | 14.0 | 14.0 | 14.0 |
| DB_IMPORT / calibrated_sensor / 19 / observed / wall_ms | 1 | 19.0 | 19.0 | 19.0 | 19.0 |
| DB_IMPORT / capture_log / 19 / observed / jdbc_ms | 1 | 13.0 | 13.0 | 13.0 | 13.0 |
| DB_IMPORT / capture_log / 19 / observed / wall_ms | 1 | 18.0 | 18.0 | 18.0 | 18.0 |
| DB_IMPORT / category / 19 / observed / jdbc_ms | 1 | 11.0 | 11.0 | 11.0 | 11.0 |
| DB_IMPORT / category / 19 / observed / wall_ms | 1 | 11.0 | 11.0 | 11.0 | 11.0 |
| DB_IMPORT / ego_pose / 19 / observed / jdbc_ms | 1 | 84.0 | 84.0 | 84.0 | 84.0 |
| DB_IMPORT / ego_pose / 19 / observed / wall_ms | 1 | 131.0 | 131.0 | 131.0 | 131.0 |
| DB_IMPORT / gt_annotation / 19 / observed / jdbc_ms | 1 | 812.0 | 812.0 | 812.0 | 812.0 |
| DB_IMPORT / gt_annotation / 19 / observed / wall_ms | 1 | 870.0 | 870.0 | 870.0 | 870.0 |
| DB_IMPORT / map_asset / 19 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / map_asset / 19 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / object_instance / 19 / observed / jdbc_ms | 1 | 28.0 | 28.0 | 28.0 | 28.0 |
| DB_IMPORT / object_instance / 19 / observed / wall_ms | 1 | 31.0 | 31.0 | 31.0 | 31.0 |
| DB_IMPORT / sample / 19 / observed / jdbc_ms | 1 | 20.0 | 20.0 | 20.0 | 20.0 |
| DB_IMPORT / sample / 19 / observed / wall_ms | 1 | 26.0 | 26.0 | 26.0 | 26.0 |
| DB_IMPORT / sample_data / 19 / observed / jdbc_ms | 1 | 140.0 | 140.0 | 140.0 | 140.0 |
| DB_IMPORT / sample_data / 19 / observed / wall_ms | 1 | 162.0 | 162.0 | 162.0 | 162.0 |
| DB_IMPORT / scene / 19 / observed / jdbc_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / scene / 19 / observed / wall_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / sensor / 19 / observed / jdbc_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / sensor / 19 / observed / wall_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / visibility / 19 / observed / jdbc_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / visibility / 19 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| HTTP / /api/dataset-uploads/sessions / all / observed / wall_ms | 1 | 156.0 | 156.0 | 156.0 | 156.0 |
| HTTP / /api/dataset-uploads/sessions/{id} / all / observed / wall_ms | 1 | 23.0 | 23.0 | 23.0 | 23.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/complete / all / observed / wall_ms | 1 | 42.0 | 42.0 | 42.0 | 42.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/parts / all / observed / wall_ms | 28 | 3164.0 | 104.0 | 181.0 | 264.0 |
| HTTP / /api/datasets / all / observed / wall_ms | 4 | 60.0 | 14.0 | 20.0 | 20.0 |
| HTTP / /api/datasets/{id}/search-index / all / observed / wall_ms | 6 | 271.0 | 42.0 | 53.0 | 53.0 |
| UPLOAD_STAGE / COPYING / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / completed / wall_ms | 1 | 104.0 | 104.0 | 104.0 | 104.0 |
| UPLOAD_STAGE / EXTRACTING / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / completed / wall_ms | 1 | 1334.0 | 1334.0 | 1334.0 | 1334.0 |
| UPLOAD_STAGE / IMPORTING_METADATA / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / completed / wall_ms | 1 | 1854.0 | 1854.0 | 1854.0 | 1854.0 |
| UPLOAD_STAGE / STORING_ORIGINAL / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / completed / wall_ms | 1 | 2574.0 | 2574.0 | 2574.0 | 2574.0 |
| UPLOAD_STAGE / TOTAL / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / completed / wall_ms | 1 | 5870.0 | 5870.0 | 5870.0 | 5870.0 |
| UPLOAD_TRANSFER / part / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / part / db_lock_ms | 28 | 241.0 | 8.0 | 11.0 | 13.0 |
| UPLOAD_TRANSFER / part / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / part / db_update_ms | 28 | 211.0 | 7.0 | 10.0 | 10.0 |
| UPLOAD_TRANSFER / part / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / part / file_ms | 28 | 246.0 | 9.0 | 12.0 | 20.0 |
| UPLOAD_TRANSFER / part / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / part / receive_ms | 28 | 1570.0 | 51.0 | 117.0 | 176.0 |
| UPLOAD_TRANSFER / part / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / part / status_ms | 28 | 221.0 | 8.0 | 10.0 | 10.0 |
| UPLOAD_TRANSFER / part / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / part / total_ms | 28 | 2802.0 | 92.0 | 168.0 | 240.0 |
| UPLOAD_TRANSFER / part / 33bfeac8-1b61-4683-bb2c-f0777319c5ba / part / transaction_ms | 28 | 984.0 | 34.0 | 42.0 | 53.0 |
