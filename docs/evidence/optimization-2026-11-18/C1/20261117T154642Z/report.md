# 로컬 계측 결과

수집 시작: 2026-11-17T15:46:43.044132+00:00 · 마지막 수집: 2026-11-17T15:48:19.023283+00:00

중첩된 구간을 합산하지 않습니다. 없는 구간은 미측정입니다. 브라우저 수치는 클라이언트 보고값이며 GPU 커널 시간은 별도 프로파일러가 필요합니다.

관측 이벤트 1055개 · 실패 이벤트 0개 · 수집 오류 0개

| 경계 / 문맥 / 상태 / 지표 | 횟수 | 합계 ms | p50 ms | p95 ms | 최대 ms |
|---|---:|---:|---:|---:|---:|
| CLIP / boundary / 15 / observed / ai_ms | 474 | 36293.0 | 71.0 | 94.0 | 374.0 |
| CLIP / boundary / 15 / observed / cache_ms | 474 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 15 / observed / exists_ms | 474 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 15 / observed / source_ms | 474 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 15 / observed / storage_ms | 474 | 5519.0 | 11.0 | 15.0 | 107.0 |
| CLIP / boundary / 15 / observed / total_ms | 474 | 42101.0 | 83.0 | 107.0 | 387.0 |
| CLIP_INDEX / batch_loaded / 15 / batch_loaded / jdbc_ms | 9 | 338.0 | 35.0 | 58.0 | 58.0 |
| CLIP_INDEX / completed / 15 / completed / wall_ms | 1 | 42948.0 | 42948.0 | 42948.0 | 42948.0 |
| CLIP_STAGE / image_embed / all / observed / decode_ms | 474 | 2172.7 | 4.3 | 6.0 | 16.2 |
| CLIP_STAGE / image_embed / all / observed / gpu_ms | 474 | 19873.6 | 40.5 | 48.0 | 87.3 |
| CLIP_STAGE / image_embed / all / observed / handler_ms | 474 | 31838.9 | 65.0 | 81.6 | 113.8 |
| CLIP_STAGE / image_embed / all / observed / lock_wait_ms | 474 | 62.2 | 0.1 | 0.2 | 1.1 |
| CLIP_STAGE / image_embed / all / observed / preprocess_ms | 474 | 9484.6 | 18.3 | 33.3 | 45.4 |
| DB_IMPORT / advisory_lock / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / attribute / 15 / observed / jdbc_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / attribute / 15 / observed / wall_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / calibrated_sensor / 15 / observed / jdbc_ms | 1 | 13.0 | 13.0 | 13.0 | 13.0 |
| DB_IMPORT / calibrated_sensor / 15 / observed / wall_ms | 1 | 19.0 | 19.0 | 19.0 | 19.0 |
| DB_IMPORT / capture_log / 15 / observed / jdbc_ms | 1 | 13.0 | 13.0 | 13.0 | 13.0 |
| DB_IMPORT / capture_log / 15 / observed / wall_ms | 1 | 19.0 | 19.0 | 19.0 | 19.0 |
| DB_IMPORT / category / 15 / observed / jdbc_ms | 1 | 12.0 | 12.0 | 12.0 | 12.0 |
| DB_IMPORT / category / 15 / observed / wall_ms | 1 | 12.0 | 12.0 | 12.0 | 12.0 |
| DB_IMPORT / ego_pose / 15 / observed / jdbc_ms | 1 | 89.0 | 89.0 | 89.0 | 89.0 |
| DB_IMPORT / ego_pose / 15 / observed / wall_ms | 1 | 129.0 | 129.0 | 129.0 | 129.0 |
| DB_IMPORT / gt_annotation / 15 / observed / jdbc_ms | 1 | 881.0 | 881.0 | 881.0 | 881.0 |
| DB_IMPORT / gt_annotation / 15 / observed / wall_ms | 1 | 987.0 | 987.0 | 987.0 | 987.0 |
| DB_IMPORT / map_asset / 15 / observed / jdbc_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / map_asset / 15 / observed / wall_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / object_instance / 15 / observed / jdbc_ms | 1 | 32.0 | 32.0 | 32.0 | 32.0 |
| DB_IMPORT / object_instance / 15 / observed / wall_ms | 1 | 36.0 | 36.0 | 36.0 | 36.0 |
| DB_IMPORT / sample / 15 / observed / jdbc_ms | 1 | 21.0 | 21.0 | 21.0 | 21.0 |
| DB_IMPORT / sample / 15 / observed / wall_ms | 1 | 27.0 | 27.0 | 27.0 | 27.0 |
| DB_IMPORT / sample_data / 15 / observed / jdbc_ms | 1 | 125.0 | 125.0 | 125.0 | 125.0 |
| DB_IMPORT / sample_data / 15 / observed / wall_ms | 1 | 142.0 | 142.0 | 142.0 | 142.0 |
| DB_IMPORT / scene / 15 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / scene / 15 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / sensor / 15 / observed / jdbc_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / sensor / 15 / observed / wall_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / visibility / 15 / observed / jdbc_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / visibility / 15 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| HTTP / /api/dataset-uploads/sessions / all / observed / wall_ms | 1 | 167.0 | 167.0 | 167.0 | 167.0 |
| HTTP / /api/dataset-uploads/sessions/{id} / all / observed / wall_ms | 1 | 23.0 | 23.0 | 23.0 | 23.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/complete / all / observed / wall_ms | 1 | 44.0 | 44.0 | 44.0 | 44.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/parts / all / observed / wall_ms | 28 | 4384.0 | 133.0 | 294.0 | 408.0 |
| HTTP / /api/datasets / all / observed / wall_ms | 4 | 71.0 | 19.0 | 21.0 | 21.0 |
| HTTP / /api/datasets/{id}/search-index / all / observed / wall_ms | 6 | 350.0 | 59.0 | 69.0 | 69.0 |
| UPLOAD_STAGE / COPYING / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / completed / wall_ms | 1 | 104.0 | 104.0 | 104.0 | 104.0 |
| UPLOAD_STAGE / EXTRACTING / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / completed / wall_ms | 1 | 1436.0 | 1436.0 | 1436.0 | 1436.0 |
| UPLOAD_STAGE / IMPORTING_METADATA / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / completed / wall_ms | 1 | 1899.0 | 1899.0 | 1899.0 | 1899.0 |
| UPLOAD_STAGE / STORING_ORIGINAL / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / completed / wall_ms | 1 | 3464.0 | 3464.0 | 3464.0 | 3464.0 |
| UPLOAD_STAGE / TOTAL / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / completed / wall_ms | 1 | 6906.0 | 6906.0 | 6906.0 | 6906.0 |
| UPLOAD_TRANSFER / part / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / part / db_lock_ms | 28 | 316.0 | 9.0 | 16.0 | 46.0 |
| UPLOAD_TRANSFER / part / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / part / db_update_ms | 28 | 279.0 | 9.0 | 12.0 | 47.0 |
| UPLOAD_TRANSFER / part / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / part / file_ms | 28 | 377.0 | 10.0 | 28.0 | 57.0 |
| UPLOAD_TRANSFER / part / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / part / receive_ms | 28 | 2286.0 | 68.0 | 166.0 | 308.0 |
| UPLOAD_TRANSFER / part / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / part / status_ms | 28 | 265.0 | 8.0 | 15.0 | 19.0 |
| UPLOAD_TRANSFER / part / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / part / total_ms | 28 | 3947.0 | 118.0 | 281.0 | 387.0 |
| UPLOAD_TRANSFER / part / f1698cde-7ee9-453b-b0b5-ba19e9811f63 / part / transaction_ms | 28 | 1366.0 | 39.0 | 68.0 | 207.0 |
