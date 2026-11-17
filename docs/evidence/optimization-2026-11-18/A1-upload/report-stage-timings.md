# 로컬 계측 결과

수집 시작: 2026-11-17T16:05:26.217600+00:00 · 마지막 수집: 2026-11-17T16:20:02.342070+00:00

중첩된 구간을 합산하지 않습니다. 없는 구간은 미측정입니다. 브라우저 수치는 클라이언트 보고값이며 GPU 커널 시간은 별도 프로파일러가 필요합니다.

관측 이벤트 7106개 · 실패 이벤트 0개 · 수집 오류 0개

| 경계 / 문맥 / 상태 / 지표 | 횟수 | 합계 ms | p50 ms | p95 ms | 최대 ms |
|---|---:|---:|---:|---:|---:|
| CLIP / boundary / 21 / observed / ai_ms | 2424 | 218052.0 | 84.0 | 123.0 | 515.0 |
| CLIP / boundary / 21 / observed / cache_ms | 2424 | 11.0 | 0.0 | 0.0 | 3.0 |
| CLIP / boundary / 21 / observed / exists_ms | 2424 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 21 / observed / source_ms | 2424 | 0.0 | 0.0 | 0.0 | 0.0 |
| CLIP / boundary / 21 / observed / storage_ms | 2424 | 30482.0 | 11.0 | 19.0 | 309.0 |
| CLIP / boundary / 21 / observed / total_ms | 2424 | 249991.0 | 95.0 | 148.0 | 546.0 |
| CLIP_INDEX / batch_loaded / 21 / batch_loaded / jdbc_ms | 39 | 1080.0 | 18.0 | 138.0 | 151.0 |
| CLIP_INDEX / completed / 21 / completed / wall_ms | 1 | 253359.0 | 253359.0 | 253359.0 | 253359.0 |
| CLIP_STAGE / image_embed / all / observed / decode_ms | 2424 | 17074.9 | 6.7 | 11.0 | 23.4 |
| CLIP_STAGE / image_embed / all / observed / gpu_ms | 2424 | 103985.2 | 41.8 | 49.0 | 119.3 |
| CLIP_STAGE / image_embed / all / observed / handler_ms | 2424 | 192023.6 | 76.3 | 101.8 | 199.3 |
| CLIP_STAGE / image_embed / all / observed / lock_wait_ms | 2424 | 2012.2 | 0.6 | 1.9 | 77.4 |
| CLIP_STAGE / image_embed / all / observed / preprocess_ms | 2424 | 67287.2 | 25.3 | 43.9 | 145.0 |
| DB_IMPORT / advisory_lock / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / observed / wall_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / attribute / 21 / observed / jdbc_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / attribute / 21 / observed / wall_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / calibrated_sensor / 21 / observed / jdbc_ms | 1 | 21.0 | 21.0 | 21.0 | 21.0 |
| DB_IMPORT / calibrated_sensor / 21 / observed / wall_ms | 1 | 23.0 | 23.0 | 23.0 | 23.0 |
| DB_IMPORT / capture_log / 21 / observed / jdbc_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / capture_log / 21 / observed / wall_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / category / 21 / observed / jdbc_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / category / 21 / observed / wall_ms | 1 | 9.0 | 9.0 | 9.0 | 9.0 |
| DB_IMPORT / ego_pose / 21 / observed / jdbc_ms | 1 | 2037.0 | 2037.0 | 2037.0 | 2037.0 |
| DB_IMPORT / ego_pose / 21 / observed / wall_ms | 1 | 2169.0 | 2169.0 | 2169.0 | 2169.0 |
| DB_IMPORT / gt_annotation / 21 / observed / jdbc_ms | 1 | 2877.0 | 2877.0 | 2877.0 | 2877.0 |
| DB_IMPORT / gt_annotation / 21 / observed / wall_ms | 1 | 2955.0 | 2955.0 | 2955.0 | 2955.0 |
| DB_IMPORT / map_asset / 21 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / map_asset / 21 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / object_instance / 21 / observed / jdbc_ms | 1 | 77.0 | 77.0 | 77.0 | 77.0 |
| DB_IMPORT / object_instance / 21 / observed / wall_ms | 1 | 78.0 | 78.0 | 78.0 | 78.0 |
| DB_IMPORT / sample / 21 / observed / jdbc_ms | 1 | 36.0 | 36.0 | 36.0 | 36.0 |
| DB_IMPORT / sample / 21 / observed / wall_ms | 1 | 37.0 | 37.0 | 37.0 | 37.0 |
| DB_IMPORT / sample_data / 21 / observed / jdbc_ms | 1 | 4753.0 | 4753.0 | 4753.0 | 4753.0 |
| DB_IMPORT / sample_data / 21 / observed / wall_ms | 1 | 4856.0 | 4856.0 | 4856.0 | 4856.0 |
| DB_IMPORT / scene / 21 / observed / jdbc_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / scene / 21 / observed / wall_ms | 1 | 10.0 | 10.0 | 10.0 | 10.0 |
| DB_IMPORT / sensor / 21 / observed / jdbc_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / sensor / 21 / observed / wall_ms | 1 | 7.0 | 7.0 | 7.0 | 7.0 |
| DB_IMPORT / visibility / 21 / observed / jdbc_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| DB_IMPORT / visibility / 21 / observed / wall_ms | 1 | 8.0 | 8.0 | 8.0 | 8.0 |
| HTTP / /api/dataset-uploads/sessions / all / observed / wall_ms | 1 | 44.0 | 44.0 | 44.0 | 44.0 |
| HTTP / /api/dataset-uploads/sessions/{id} / all / observed / wall_ms | 47 | 775.0 | 15.0 | 38.0 | 67.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/complete / all / observed / wall_ms | 1 | 39.0 | 39.0 | 39.0 | 39.0 |
| HTTP / /api/dataset-uploads/sessions/{id}/parts / all / observed / wall_ms | 1043 | 121297.0 | 106.0 | 195.0 | 357.0 |
| HTTP / /api/datasets / all / observed / wall_ms | 29 | 601.0 | 17.0 | 66.0 | 70.0 |
| HTTP / /api/datasets/{id}/search-index / all / observed / wall_ms | 26 | 1405.0 | 41.0 | 123.0 | 136.0 |
| UPLOAD_STAGE / COPYING / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / completed / wall_ms | 1 | 19626.0 | 19626.0 | 19626.0 | 19626.0 |
| UPLOAD_STAGE / EXTRACTING / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / completed / wall_ms | 1 | 68559.0 | 68559.0 | 68559.0 | 68559.0 |
| UPLOAD_STAGE / IMPORTING_METADATA / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / completed / wall_ms | 1 | 12165.0 | 12165.0 | 12165.0 | 12165.0 |
| UPLOAD_STAGE / STORING_ORIGINAL / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / completed / wall_ms | 1 | 362158.0 | 362158.0 | 362158.0 | 362158.0 |
| UPLOAD_STAGE / TOTAL / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / completed / wall_ms | 1 | 462510.0 | 462510.0 | 462510.0 | 462510.0 |
| UPLOAD_TRANSFER / part / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / part / db_lock_ms | 1043 | 10511.0 | 8.0 | 14.0 | 133.0 |
| UPLOAD_TRANSFER / part / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / part / db_update_ms | 1043 | 8367.0 | 7.0 | 10.0 | 52.0 |
| UPLOAD_TRANSFER / part / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / part / file_ms | 1043 | 12144.0 | 10.0 | 23.0 | 180.0 |
| UPLOAD_TRANSFER / part / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / part / receive_ms | 1043 | 56070.0 | 48.0 | 102.0 | 251.0 |
| UPLOAD_TRANSFER / part / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / part / status_ms | 1043 | 8158.0 | 7.0 | 10.0 | 42.0 |
| UPLOAD_TRANSFER / part / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / part / total_ms | 1043 | 107245.0 | 93.0 | 180.0 | 341.0 |
| UPLOAD_TRANSFER / part / f00cc327-dc93-4e82-a8aa-ef9d18dcc550 / part / transaction_ms | 1043 | 41965.0 | 36.0 | 62.0 | 246.0 |
