# 로컬 계측 결과

수집 시작: 2026-11-17T15:58:50.879836+00:00 · 마지막 수집: 2026-11-17T16:00:26.753717+00:00

중첩된 구간을 합산하지 않습니다. 없는 구간은 미측정입니다. 브라우저 수치는 클라이언트 보고값이며 GPU 커널 시간은 별도 프로파일러가 필요합니다.

관측 이벤트 1055개 · 실패 이벤트 0개 · 수집 오류 0개

| 경계 / 문맥 / 상태 / 지표 | 횟수 | 합계 ms | p50 ms | p95 ms | 최대 ms |
|---|---:|---:|---:|---:|---:|
| CLIP / boundary / 18 / observed / ai_ms | 474 | 36200.0 | 72.0 | 93.0 | 303.0 |
| CLIP / boundary / 18 / observed / cache_ms | 474 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 18 / observed / exists_ms | 474 | 3743.0 | 7.0 | 11.0 | 38.0 |
| CLIP / boundary / 18 / observed / source_ms | 474 | 3832.0 | 8.0 | 11.0 | 25.0 |
| CLIP / boundary / 18 / observed / storage_ms | 474 | 5156.0 | 10.0 | 15.0 | 30.0 |
| CLIP / boundary / 18 / observed / total_ms | 474 | 49739.0 | 100.0 | 125.0 | 349.0 |
| CLIP_INDEX / batch_loaded / 18 / batch_loaded / jdbc_ms | 9 | 356.0 | 33.0 | 67.0 | 67.0 |
| CLIP_INDEX / completed / 18 / completed / wall_ms | 1 | 50598.0 | 50598.0 | 50598.0 | 50598.0 |
| CLIP_STAGE / image_embed / all / observed / decode_ms | 474 | 2135.1 | 4.3 | 5.9 | 11.4 |
| CLIP_STAGE / image_embed / all / observed / gpu_ms | 474 | 20007.7 | 41.2 | 47.0 | 52.2 |
| CLIP_STAGE / image_embed / all / observed / handler_ms | 474 | 31955.1 | 66.0 | 79.2 | 94.3 |
| CLIP_STAGE / image_embed / all / observed / lock_wait_ms | 474 | 61.2 | 0.1 | 0.2 | 1.0 |
| CLIP_STAGE / image_embed / all / observed / preprocess_ms | 474 | 9499.5 | 18.6 | 30.9 | 44.2 |
| DB_IMPORT / advisory_lock / 4111d978-1b91-4b8d-bff5-dd3986276035 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / attribute / 18 / observed / jdbc_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / attribute / 18 / observed / wall_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / calibrated_sensor / 18 / observed / jdbc_ms | 1 | 14.0 | 14.0 | 14.0 | 14.0 |
| DB_IMPORT / calibrated_sensor / 18 / observed / wall_ms | 1 | 20.0 | 20.0 | 20.0 | 20.0 |
| DB_IMPORT / capture_log / 18 / observed / jdbc_ms | 1 | 14.0 | 14.0 | 14.0 | 14.0 |
| DB_IMPORT / capture_log / 18 / observed / wall_ms | 1 | 23.0 | 23.0 | 23.0 | 23.0 |
| DB_IMPORT / category / 18 / observed / jdbc_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / category / 18 / observed / wall_ms | 1 | 11.0 | 11.0 | 11.0 | 11.0 |
| DB_IMPORT / ego_pose / 18 / observed / jdbc_ms | 1 | 83.0 | 83.0 | 83.0 | 83.0 |
| DB_IMPORT / ego_pose / 18 / observed / wall_ms | 1 | 125.0 | 125.0 | 125.0 | 125.0 |
| DB_IMPORT / gt_annotation / 18 / observed / jdbc_ms | 1 | 856.0 | 856.0 | 856.0 | 856.0 |
| DB_IMPORT / gt_annotation / 18 / observed / wall_ms | 1 | 913.0 | 913.0 | 913.0 | 913.0 |
| DB_IMPORT / map_asset / 18 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / map_asset / 18 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / object_instance / 18 / observed / jdbc_ms | 1 | 30.0 | 30.0 | 30.0 | 30.0 |
| DB_IMPORT / object_instance / 18 / observed / wall_ms | 1 | 33.0 | 33.0 | 33.0 | 33.0 |
| DB_IMPORT / sample / 18 / observed / jdbc_ms | 1 | 20.0 | 20.0 | 20.0 | 20.0 |
| DB_IMPORT / sample / 18 / observed / wall_ms | 1 | 25.0 | 25.0 | 25.0 | 25.0 |
| DB_IMPORT / sample_data / 18 / observed / jdbc_ms | 1 | 126.0 | 126.0 | 126.0 | 126.0 |
| DB_IMPORT / sample_data / 18 / observed / wall_ms | 1 | 137.0 | 137.0 | 137.0 | 137.0 |
| DB_IMPORT / scene / 18 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / scene / 18 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / sensor / 18 / observed / jdbc_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / sensor / 18 / observed / wall_ms | 1 | 11.0 | 11.0 | 11.0 | 11.0 |
| DB_IMPORT / visibility / 18 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / visibility / 18 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| HTTP / /api/dataset-uploads/sessions / all / observed / wall_ms | 1 | 193.0 | 193.0 | 193.0 | 193.0 |
| HTTP / /api/dataset-uploads/sessions/{id} / all / observed / wall_ms | 1 | 28.0 | 28.0 | 28.0 | 28.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/complete / all / observed / wall_ms | 1 | 45.0 | 45.0 | 45.0 | 45.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/parts / all / observed / wall_ms | 28 | 3537.0 | 110.0 | 280.0 | 359.0 |
| HTTP / /api/datasets / all / observed / wall_ms | 4 | 92.0 | 20.0 | 35.0 | 35.0 |
| HTTP / /api/datasets/{id}/search-index / all / observed / wall_ms | 6 | 381.0 | 58.0 | 81.0 | 81.0 |
| UPLOAD_STAGE / COPYING / 4111d978-1b91-4b8d-bff5-dd3986276035 / completed / wall_ms | 1 | 182.0 | 182.0 | 182.0 | 182.0 |
| UPLOAD_STAGE / EXTRACTING / 4111d978-1b91-4b8d-bff5-dd3986276035 / completed / wall_ms | 1 | 1851.0 | 1851.0 | 1851.0 | 1851.0 |
| UPLOAD_STAGE / IMPORTING_METADATA / 4111d978-1b91-4b8d-bff5-dd3986276035 / completed / wall_ms | 1 | 1861.0 | 1861.0 | 1861.0 | 1861.0 |
| UPLOAD_STAGE / STORING_ORIGINAL / 4111d978-1b91-4b8d-bff5-dd3986276035 / completed / wall_ms | 1 | 3548.0 | 3548.0 | 3548.0 | 3548.0 |
| UPLOAD_STAGE / TOTAL / 4111d978-1b91-4b8d-bff5-dd3986276035 / completed / wall_ms | 1 | 7446.0 | 7446.0 | 7446.0 | 7446.0 |
| UPLOAD_TRANSFER / part / 4111d978-1b91-4b8d-bff5-dd3986276035 / part / db_lock_ms | 28 | 249.0 | 9.0 | 11.0 | 12.0 |
| UPLOAD_TRANSFER / part / 4111d978-1b91-4b8d-bff5-dd3986276035 / part / db_update_ms | 28 | 244.0 | 8.0 | 12.0 | 16.0 |
| UPLOAD_TRANSFER / part / 4111d978-1b91-4b8d-bff5-dd3986276035 / part / file_ms | 28 | 307.0 | 9.0 | 28.0 | 44.0 |
| UPLOAD_TRANSFER / part / 4111d978-1b91-4b8d-bff5-dd3986276035 / part / receive_ms | 28 | 1771.0 | 53.0 | 192.0 | 208.0 |
| UPLOAD_TRANSFER / part / 4111d978-1b91-4b8d-bff5-dd3986276035 / part / status_ms | 28 | 232.0 | 8.0 | 10.0 | 10.0 |
| UPLOAD_TRANSFER / part / 4111d978-1b91-4b8d-bff5-dd3986276035 / part / total_ms | 28 | 3129.0 | 99.0 | 262.0 | 314.0 |
| UPLOAD_TRANSFER / part / 4111d978-1b91-4b8d-bff5-dd3986276035 / part / transaction_ms | 28 | 1101.0 | 36.0 | 59.0 | 95.0 |
