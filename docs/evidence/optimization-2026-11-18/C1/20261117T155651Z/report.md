# 로컬 계측 결과

수집 시작: 2026-11-17T15:56:51.334805+00:00 · 마지막 수집: 2026-11-17T15:58:27.711173+00:00

중첩된 구간을 합산하지 않습니다. 없는 구간은 미측정입니다. 브라우저 수치는 클라이언트 보고값이며 GPU 커널 시간은 별도 프로파일러가 필요합니다.

관측 이벤트 1055개 · 실패 이벤트 0개 · 수집 오류 0개

| 경계 / 문맥 / 상태 / 지표 | 횟수 | 합계 ms | p50 ms | p95 ms | 최대 ms |
|---|---:|---:|---:|---:|---:|
| CLIP / boundary / 17 / observed / ai_ms | 474 | 36227.0 | 72.0 | 88.0 | 328.0 |
| CLIP / boundary / 17 / observed / cache_ms | 474 | 1.0 | 0.0 | 0.0 | 1.0 |
| CLIP / boundary / 17 / observed / exists_ms | 474 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 17 / observed / source_ms | 474 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 17 / observed / storage_ms | 474 | 5073.0 | 10.0 | 15.0 | 59.0 |
| CLIP / boundary / 17 / observed / total_ms | 474 | 41621.0 | 84.0 | 102.0 | 350.0 |
| CLIP_INDEX / batch_loaded / 17 / batch_loaded / jdbc_ms | 9 | 324.0 | 33.0 | 53.0 | 53.0 |
| CLIP_INDEX / completed / 17 / completed / wall_ms | 1 | 42436.0 | 42436.0 | 42436.0 | 42436.0 |
| CLIP_STAGE / image_embed / all / observed / decode_ms | 474 | 2147.3 | 4.4 | 5.5 | 10.2 |
| CLIP_STAGE / image_embed / all / observed / gpu_ms | 474 | 19763.6 | 40.7 | 46.1 | 53.1 |
| CLIP_STAGE / image_embed / all / observed / handler_ms | 474 | 31819.7 | 65.8 | 77.4 | 101.6 |
| CLIP_STAGE / image_embed / all / observed / lock_wait_ms | 474 | 60.2 | 0.1 | 0.2 | 1.1 |
| CLIP_STAGE / image_embed / all / observed / preprocess_ms | 474 | 9593.1 | 19.0 | 27.9 | 57.0 |
| DB_IMPORT / advisory_lock / c2d527af-f0d5-48d2-96f7-2966839a0c13 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / attribute / 17 / observed / jdbc_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / attribute / 17 / observed / wall_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / calibrated_sensor / 17 / observed / jdbc_ms | 1 | 13.0 | 13.0 | 13.0 | 13.0 |
| DB_IMPORT / calibrated_sensor / 17 / observed / wall_ms | 1 | 19.0 | 19.0 | 19.0 | 19.0 |
| DB_IMPORT / capture_log / 17 / observed / jdbc_ms | 1 | 14.0 | 14.0 | 14.0 | 14.0 |
| DB_IMPORT / capture_log / 17 / observed / wall_ms | 1 | 23.0 | 23.0 | 23.0 | 23.0 |
| DB_IMPORT / category / 17 / observed / jdbc_ms | 1 | 11.0 | 11.0 | 11.0 | 11.0 |
| DB_IMPORT / category / 17 / observed / wall_ms | 1 | 12.0 | 12.0 | 12.0 | 12.0 |
| DB_IMPORT / ego_pose / 17 / observed / jdbc_ms | 1 | 97.0 | 97.0 | 97.0 | 97.0 |
| DB_IMPORT / ego_pose / 17 / observed / wall_ms | 1 | 148.0 | 148.0 | 148.0 | 148.0 |
| DB_IMPORT / gt_annotation / 17 / observed / jdbc_ms | 1 | 905.0 | 905.0 | 905.0 | 905.0 |
| DB_IMPORT / gt_annotation / 17 / observed / wall_ms | 1 | 1000.0 | 1000.0 | 1000.0 | 1000.0 |
| DB_IMPORT / map_asset / 17 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / map_asset / 17 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / object_instance / 17 / observed / jdbc_ms | 1 | 28.0 | 28.0 | 28.0 | 28.0 |
| DB_IMPORT / object_instance / 17 / observed / wall_ms | 1 | 31.0 | 31.0 | 31.0 | 31.0 |
| DB_IMPORT / sample / 17 / observed / jdbc_ms | 1 | 25.0 | 25.0 | 25.0 | 25.0 |
| DB_IMPORT / sample / 17 / observed / wall_ms | 1 | 33.0 | 33.0 | 33.0 | 33.0 |
| DB_IMPORT / sample_data / 17 / observed / jdbc_ms | 1 | 128.0 | 128.0 | 128.0 | 128.0 |
| DB_IMPORT / sample_data / 17 / observed / wall_ms | 1 | 144.0 | 144.0 | 144.0 | 144.0 |
| DB_IMPORT / scene / 17 / observed / jdbc_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / scene / 17 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / sensor / 17 / observed / jdbc_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / sensor / 17 / observed / wall_ms | 1 | 11.0 | 11.0 | 11.0 | 11.0 |
| DB_IMPORT / visibility / 17 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / visibility / 17 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| HTTP / /api/dataset-uploads/sessions / all / observed / wall_ms | 1 | 223.0 | 223.0 | 223.0 | 223.0 |
| HTTP / /api/dataset-uploads/sessions/{id} / all / observed / wall_ms | 1 | 25.0 | 25.0 | 25.0 | 25.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/complete / all / observed / wall_ms | 1 | 44.0 | 44.0 | 44.0 | 44.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/parts / all / observed / wall_ms | 28 | 3503.0 | 115.0 | 183.0 | 262.0 |
| HTTP / /api/datasets / all / observed / wall_ms | 4 | 82.0 | 17.0 | 28.0 | 28.0 |
| HTTP / /api/datasets/{id}/search-index / all / observed / wall_ms | 6 | 350.0 | 55.0 | 75.0 | 75.0 |
| UPLOAD_STAGE / COPYING / c2d527af-f0d5-48d2-96f7-2966839a0c13 / completed / wall_ms | 1 | 102.0 | 102.0 | 102.0 | 102.0 |
| UPLOAD_STAGE / EXTRACTING / c2d527af-f0d5-48d2-96f7-2966839a0c13 / completed / wall_ms | 1 | 1330.0 | 1330.0 | 1330.0 | 1330.0 |
| UPLOAD_STAGE / IMPORTING_METADATA / c2d527af-f0d5-48d2-96f7-2966839a0c13 / completed / wall_ms | 1 | 2007.0 | 2007.0 | 2007.0 | 2007.0 |
| UPLOAD_STAGE / STORING_ORIGINAL / c2d527af-f0d5-48d2-96f7-2966839a0c13 / completed / wall_ms | 1 | 3878.0 | 3878.0 | 3878.0 | 3878.0 |
| UPLOAD_STAGE / TOTAL / c2d527af-f0d5-48d2-96f7-2966839a0c13 / completed / wall_ms | 1 | 7321.0 | 7321.0 | 7321.0 | 7321.0 |
| UPLOAD_TRANSFER / part / c2d527af-f0d5-48d2-96f7-2966839a0c13 / part / db_lock_ms | 28 | 255.0 | 9.0 | 11.0 | 14.0 |
| UPLOAD_TRANSFER / part / c2d527af-f0d5-48d2-96f7-2966839a0c13 / part / db_update_ms | 28 | 229.0 | 8.0 | 11.0 | 14.0 |
| UPLOAD_TRANSFER / part / c2d527af-f0d5-48d2-96f7-2966839a0c13 / part / file_ms | 28 | 267.0 | 9.0 | 16.0 | 18.0 |
| UPLOAD_TRANSFER / part / c2d527af-f0d5-48d2-96f7-2966839a0c13 / part / receive_ms | 28 | 1752.0 | 56.0 | 126.0 | 154.0 |
| UPLOAD_TRANSFER / part / c2d527af-f0d5-48d2-96f7-2966839a0c13 / part / status_ms | 28 | 241.0 | 8.0 | 16.0 | 17.0 |
| UPLOAD_TRANSFER / part / c2d527af-f0d5-48d2-96f7-2966839a0c13 / part / total_ms | 28 | 3054.0 | 102.0 | 172.0 | 226.0 |
| UPLOAD_TRANSFER / part / c2d527af-f0d5-48d2-96f7-2966839a0c13 / part / transaction_ms | 28 | 1035.0 | 36.0 | 48.0 | 56.0 |
