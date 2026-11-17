package com.example.demo;

import org.springframework.boot.test.context.SpringBootTest;

/** Run all existing search/index behavior checks with the optimized pending-source path. */
@SpringBootTest(properties={
 "auto-label.worker.enabled=false","recording.worker.enabled=false",
 "embedding.index-prefetch-enabled=true",
 "spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://localhost:55432/drivescene_test}",
 "spring.datasource.username=${TEST_DB_USERNAME:drivescene}",
 "spring.datasource.password=${TEST_DB_PASSWORD:}","nuscenes.import.enabled=false"})
class PrefetchedSceneSearchTests extends SceneSearchTests {}
