# 로컬 계측 결과

수집 시작: 2026-11-17T15:44:42.635154+00:00 · 마지막 수집: 2026-11-17T15:46:18.527738+00:00

중첩된 구간을 합산하지 않습니다. 없는 구간은 미측정입니다. 브라우저 수치는 클라이언트 보고값이며 GPU 커널 시간은 별도 프로파일러가 필요합니다.

관측 이벤트 1055개 · 실패 이벤트 0개 · 수집 오류 0개

| 경계 / 문맥 / 상태 / 지표 | 횟수 | 합계 ms | p50 ms | p95 ms | 최대 ms |
|---|---:|---:|---:|---:|---:|
| CLIP / boundary / 14 / observed / ai_ms | 474 | 34913.0 | 70.0 | 88.0 | 448.0 |
| CLIP / boundary / 14 / observed / cache_ms | 474 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 14 / observed / exists_ms | 474 | 3634.0 | 7.0 | 10.0 | 78.0 |
| CLIP / boundary / 14 / observed / source_ms | 474 | 3733.0 | 7.0 | 11.0 | 43.0 |
| CLIP / boundary / 14 / observed / storage_ms | 474 | 5114.0 | 10.0 | 16.0 | 50.0 |
| CLIP / boundary / 14 / observed / total_ms | 474 | 48162.0 | 98.0 | 119.0 | 485.0 |
| CLIP_INDEX / batch_loaded / 14 / batch_loaded / jdbc_ms | 9 | 550.0 | 68.0 | 80.0 | 80.0 |
| CLIP_INDEX / completed / 14 / completed / wall_ms | 1 | 49192.0 | 49192.0 | 49192.0 | 49192.0 |
| CLIP_STAGE / image_embed / all / observed / decode_ms | 474 | 2031.3 | 4.1 | 5.4 | 9.5 |
| CLIP_STAGE / image_embed / all / observed / gpu_ms | 474 | 19759.4 | 40.4 | 45.6 | 210.0 |
| CLIP_STAGE / image_embed / all / observed / handler_ms | 474 | 31072.6 | 64.0 | 74.7 | 238.9 |
| CLIP_STAGE / image_embed / all / observed / lock_wait_ms | 474 | 58.6 | 0.1 | 0.2 | 0.9 |
| CLIP_STAGE / image_embed / all / observed / preprocess_ms | 474 | 8966.1 | 17.8 | 25.8 | 35.4 |
| DB_IMPORT / advisory_lock / a83f46d1-868e-4bea-968b-79dae0d56bb2 / observed / wall_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / attribute / 14 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / attribute / 14 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / calibrated_sensor / 14 / observed / jdbc_ms | 1 | 14.0 | 14.0 | 14.0 | 14.0 |
| DB_IMPORT / calibrated_sensor / 14 / observed / wall_ms | 1 | 21.0 | 21.0 | 21.0 | 21.0 |
| DB_IMPORT / capture_log / 14 / observed / jdbc_ms | 1 | 12.0 | 12.0 | 12.0 | 12.0 |
| DB_IMPORT / capture_log / 14 / observed / wall_ms | 1 | 18.0 | 18.0 | 18.0 | 18.0 |
| DB_IMPORT / category / 14 / observed / jdbc_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / category / 14 / observed / wall_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / ego_pose / 14 / observed / jdbc_ms | 1 | 93.0 | 93.0 | 93.0 | 93.0 |
| DB_IMPORT / ego_pose / 14 / observed / wall_ms | 1 | 131.0 | 131.0 | 131.0 | 131.0 |
| DB_IMPORT / gt_annotation / 14 / observed / jdbc_ms | 1 | 831.0 | 831.0 | 831.0 | 831.0 |
| DB_IMPORT / gt_annotation / 14 / observed / wall_ms | 1 | 921.0 | 921.0 | 921.0 | 921.0 |
| DB_IMPORT / map_asset / 14 / observed / jdbc_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / map_asset / 14 / observed / wall_ms | 1 | 11.0 | 11.0 | 11.0 | 11.0 |
| DB_IMPORT / object_instance / 14 / observed / jdbc_ms | 1 | 28.0 | 28.0 | 28.0 | 28.0 |
| DB_IMPORT / object_instance / 14 / observed / wall_ms | 1 | 30.0 | 30.0 | 30.0 | 30.0 |
| DB_IMPORT / sample / 14 / observed / jdbc_ms | 1 | 18.0 | 18.0 | 18.0 | 18.0 |
| DB_IMPORT / sample / 14 / observed / wall_ms | 1 | 25.0 | 25.0 | 25.0 | 25.0 |
| DB_IMPORT / sample_data / 14 / observed / jdbc_ms | 1 | 125.0 | 125.0 | 125.0 | 125.0 |
| DB_IMPORT / sample_data / 14 / observed / wall_ms | 1 | 135.0 | 135.0 | 135.0 | 135.0 |
| DB_IMPORT / scene / 14 / observed / jdbc_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / scene / 14 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / sensor / 14 / observed / jdbc_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / sensor / 14 / observed / wall_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / visibility / 14 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / visibility / 14 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| HTTP / /api/dataset-uploads/sessions / all / observed / wall_ms | 1 | 131.0 | 131.0 | 131.0 | 131.0 |
| HTTP / /api/dataset-uploads/sessions/{id} / all / observed / wall_ms | 1 | 19.0 | 19.0 | 19.0 | 19.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/complete / all / observed / wall_ms | 1 | 50.0 | 50.0 | 50.0 | 50.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/parts / all / observed / wall_ms | 28 | 3734.0 | 109.0 | 330.0 | 365.0 |
| HTTP / /api/datasets / all / observed / wall_ms | 4 | 51.0 | 11.0 | 15.0 | 15.0 |
| HTTP / /api/datasets/{id}/search-index / all / observed / wall_ms | 6 | 465.0 | 67.0 | 97.0 | 97.0 |
| UPLOAD_STAGE / COPYING / a83f46d1-868e-4bea-968b-79dae0d56bb2 / completed / wall_ms | 1 | 133.0 | 133.0 | 133.0 | 133.0 |
| UPLOAD_STAGE / EXTRACTING / a83f46d1-868e-4bea-968b-79dae0d56bb2 / completed / wall_ms | 1 | 1438.0 | 1438.0 | 1438.0 | 1438.0 |
| UPLOAD_STAGE / IMPORTING_METADATA / a83f46d1-868e-4bea-968b-79dae0d56bb2 / completed / wall_ms | 1 | 1861.0 | 1861.0 | 1861.0 | 1861.0 |
| UPLOAD_STAGE / STORING_ORIGINAL / a83f46d1-868e-4bea-968b-79dae0d56bb2 / completed / wall_ms | 1 | 3708.0 | 3708.0 | 3708.0 | 3708.0 |
| UPLOAD_STAGE / TOTAL / a83f46d1-868e-4bea-968b-79dae0d56bb2 / completed / wall_ms | 1 | 7143.0 | 7143.0 | 7143.0 | 7143.0 |
| UPLOAD_TRANSFER / part / a83f46d1-868e-4bea-968b-79dae0d56bb2 / part / db_lock_ms | 28 | 293.0 | 10.0 | 15.0 | 20.0 |
| UPLOAD_TRANSFER / part / a83f46d1-868e-4bea-968b-79dae0d56bb2 / part / db_update_ms | 28 | 477.0 | 8.0 | 11.0 | 244.0 |
| UPLOAD_TRANSFER / part / a83f46d1-868e-4bea-968b-79dae0d56bb2 / part / file_ms | 28 | 287.0 | 10.0 | 14.0 | 15.0 |
| UPLOAD_TRANSFER / part / a83f46d1-868e-4bea-968b-79dae0d56bb2 / part / receive_ms | 28 | 1670.0 | 50.0 | 83.0 | 230.0 |
| UPLOAD_TRANSFER / part / a83f46d1-868e-4bea-968b-79dae0d56bb2 / part / status_ms | 28 | 249.0 | 9.0 | 13.0 | 14.0 |
| UPLOAD_TRANSFER / part / a83f46d1-868e-4bea-968b-79dae0d56bb2 / part / total_ms | 28 | 3337.0 | 97.0 | 299.0 | 353.0 |
| UPLOAD_TRANSFER / part / a83f46d1-868e-4bea-968b-79dae0d56bb2 / part / transaction_ms | 28 | 1389.0 | 38.0 | 59.0 | 279.0 |
