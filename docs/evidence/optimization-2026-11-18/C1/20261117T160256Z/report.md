# 로컬 계측 결과

수집 시작: 2026-11-17T16:02:57.081509+00:00 · 마지막 수집: 2026-11-17T16:04:33.362645+00:00

중첩된 구간을 합산하지 않습니다. 없는 구간은 미측정입니다. 브라우저 수치는 클라이언트 보고값이며 GPU 커널 시간은 별도 프로파일러가 필요합니다.

관측 이벤트 1055개 · 실패 이벤트 0개 · 수집 오류 0개

| 경계 / 문맥 / 상태 / 지표 | 횟수 | 합계 ms | p50 ms | p95 ms | 최대 ms |
|---|---:|---:|---:|---:|---:|
| CLIP / boundary / 20 / observed / ai_ms | 474 | 36810.0 | 73.0 | 103.0 | 206.0 |
| CLIP / boundary / 20 / observed / cache_ms | 474 | 5.0 | 0.0 | 0.0 | 2.0 |
| CLIP / boundary / 20 / observed / exists_ms | 474 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 20 / observed / source_ms | 474 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 20 / observed / storage_ms | 474 | 5492.0 | 11.0 | 16.0 | 93.0 |
| CLIP / boundary / 20 / observed / total_ms | 474 | 42599.0 | 85.0 | 116.0 | 217.0 |
| CLIP_INDEX / batch_loaded / 20 / batch_loaded / jdbc_ms | 9 | 498.0 | 66.0 | 72.0 | 72.0 |
| CLIP_INDEX / completed / 20 / completed / wall_ms | 1 | 43609.0 | 43609.0 | 43609.0 | 43609.0 |
| CLIP_STAGE / image_embed / all / observed / decode_ms | 474 | 2297.7 | 4.6 | 6.4 | 10.6 |
| CLIP_STAGE / image_embed / all / observed / gpu_ms | 474 | 19881.6 | 40.7 | 47.3 | 59.4 |
| CLIP_STAGE / image_embed / all / observed / handler_ms | 474 | 32716.7 | 66.9 | 87.8 | 105.2 |
| CLIP_STAGE / image_embed / all / observed / lock_wait_ms | 474 | 69.2 | 0.1 | 0.2 | 3.4 |
| CLIP_STAGE / image_embed / all / observed / preprocess_ms | 474 | 10176.9 | 19.9 | 36.7 | 48.0 |
| DB_IMPORT / advisory_lock / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / observed / wall_ms | 1 | 23.0 | 23.0 | 23.0 | 23.0 |
| DB_IMPORT / attribute / 20 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / attribute / 20 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / calibrated_sensor / 20 / observed / jdbc_ms | 1 | 14.0 | 14.0 | 14.0 | 14.0 |
| DB_IMPORT / calibrated_sensor / 20 / observed / wall_ms | 1 | 20.0 | 20.0 | 20.0 | 20.0 |
| DB_IMPORT / capture_log / 20 / observed / jdbc_ms | 1 | 11.0 | 11.0 | 11.0 | 11.0 |
| DB_IMPORT / capture_log / 20 / observed / wall_ms | 1 | 20.0 | 20.0 | 20.0 | 20.0 |
| DB_IMPORT / category / 20 / observed / jdbc_ms | 1 | 12.0 | 12.0 | 12.0 | 12.0 |
| DB_IMPORT / category / 20 / observed / wall_ms | 1 | 13.0 | 13.0 | 13.0 | 13.0 |
| DB_IMPORT / ego_pose / 20 / observed / jdbc_ms | 1 | 80.0 | 80.0 | 80.0 | 80.0 |
| DB_IMPORT / ego_pose / 20 / observed / wall_ms | 1 | 117.0 | 117.0 | 117.0 | 117.0 |
| DB_IMPORT / gt_annotation / 20 / observed / jdbc_ms | 1 | 891.0 | 891.0 | 891.0 | 891.0 |
| DB_IMPORT / gt_annotation / 20 / observed / wall_ms | 1 | 957.0 | 957.0 | 957.0 | 957.0 |
| DB_IMPORT / map_asset / 20 / observed / jdbc_ms | 1 | 11.0 | 11.0 | 11.0 | 11.0 |
| DB_IMPORT / map_asset / 20 / observed / wall_ms | 1 | 12.0 | 12.0 | 12.0 | 12.0 |
| DB_IMPORT / object_instance / 20 / observed / jdbc_ms | 1 | 34.0 | 34.0 | 34.0 | 34.0 |
| DB_IMPORT / object_instance / 20 / observed / wall_ms | 1 | 36.0 | 36.0 | 36.0 | 36.0 |
| DB_IMPORT / sample / 20 / observed / jdbc_ms | 1 | 22.0 | 22.0 | 22.0 | 22.0 |
| DB_IMPORT / sample / 20 / observed / wall_ms | 1 | 28.0 | 28.0 | 28.0 | 28.0 |
| DB_IMPORT / sample_data / 20 / observed / jdbc_ms | 1 | 129.0 | 129.0 | 129.0 | 129.0 |
| DB_IMPORT / sample_data / 20 / observed / wall_ms | 1 | 139.0 | 139.0 | 139.0 | 139.0 |
| DB_IMPORT / scene / 20 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / scene / 20 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / sensor / 20 / observed / jdbc_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / sensor / 20 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / visibility / 20 / observed / jdbc_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / visibility / 20 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| HTTP / /api/dataset-uploads/sessions / all / observed / wall_ms | 1 | 104.0 | 104.0 | 104.0 | 104.0 |
| HTTP / /api/dataset-uploads/sessions/{id} / all / observed / wall_ms | 1 | 20.0 | 20.0 | 20.0 | 20.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/complete / all / observed / wall_ms | 1 | 44.0 | 44.0 | 44.0 | 44.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/parts / all / observed / wall_ms | 28 | 3177.0 | 103.0 | 193.0 | 288.0 |
| HTTP / /api/datasets / all / observed / wall_ms | 4 | 66.0 | 16.0 | 20.0 | 20.0 |
| HTTP / /api/datasets/{id}/search-index / all / observed / wall_ms | 6 | 443.0 | 71.0 | 95.0 | 95.0 |
| UPLOAD_STAGE / COPYING / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / completed / wall_ms | 1 | 108.0 | 108.0 | 108.0 | 108.0 |
| UPLOAD_STAGE / EXTRACTING / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / completed / wall_ms | 1 | 1198.0 | 1198.0 | 1198.0 | 1198.0 |
| UPLOAD_STAGE / IMPORTING_METADATA / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / completed / wall_ms | 1 | 1910.0 | 1910.0 | 1910.0 | 1910.0 |
| UPLOAD_STAGE / STORING_ORIGINAL / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / completed / wall_ms | 1 | 2970.0 | 2970.0 | 2970.0 | 2970.0 |
| UPLOAD_STAGE / TOTAL / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / completed / wall_ms | 1 | 6188.0 | 6188.0 | 6188.0 | 6188.0 |
| UPLOAD_TRANSFER / part / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / part / db_lock_ms | 28 | 245.0 | 8.0 | 12.0 | 16.0 |
| UPLOAD_TRANSFER / part / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / part / db_update_ms | 28 | 220.0 | 8.0 | 10.0 | 10.0 |
| UPLOAD_TRANSFER / part / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / part / file_ms | 28 | 247.0 | 7.0 | 20.0 | 25.0 |
| UPLOAD_TRANSFER / part / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / part / receive_ms | 28 | 1545.0 | 47.0 | 127.0 | 188.0 |
| UPLOAD_TRANSFER / part / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / part / status_ms | 28 | 241.0 | 8.0 | 11.0 | 20.0 |
| UPLOAD_TRANSFER / part / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / part / total_ms | 28 | 2836.0 | 91.0 | 176.0 | 269.0 |
| UPLOAD_TRANSFER / part / 1311ffd1-17fb-48f3-8681-d70cb0d730b5 / part / transaction_ms | 28 | 1021.0 | 35.0 | 50.0 | 60.0 |
