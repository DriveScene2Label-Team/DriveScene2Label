package com.example.demo;

import org.springframework.boot.test.context.SpringBootTest;

/** Run all existing search/index behavior checks with C2 batch embedding on top of the C1 pending-source path. */
@SpringBootTest(properties={
 "auto-label.worker.enabled=false","recording.worker.enabled=false",
 "embedding.index-prefetch-enabled=true","embedding.index-batch-enabled=true",
 "spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://localhost:55432/drivescene_test}",
 "spring.datasource.username=${TEST_DB_USERNAME:drivescene}",
 "spring.datasource.password=${TEST_DB_PASSWORD:}","nuscenes.import.enabled=false"})
class BatchedSceneSearchTests extends SceneSearchTests {
 @Override protected boolean batched() { return true; }
}
