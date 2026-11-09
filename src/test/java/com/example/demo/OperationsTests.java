package com.example.demo;

import com.example.demo.operations.OperationsService;
import com.example.demo.nuscenes.service.AutoLabelService;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"operations.token=test-only-operations-token","auto-label.worker.enabled=false","recording.worker.enabled=false","nuscenes.import.enabled=false",
 "spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://localhost:55432/drivescene_test}",
 "spring.datasource.username=${TEST_DB_USERNAME:drivescene}","spring.datasource.password=${TEST_DB_PASSWORD:}"})
@AutoConfigureMockMvc
class OperationsTests {
 @Autowired MockMvc mvc;
 @Autowired OperationsService operations;
 @Autowired AutoLabelService jobs;
 @AfterEach void cleanup() { operations.maintenance(false); }
 @Test void requiresOperationsTokenAndNeverReturnsIt() throws Exception {
  mvc.perform(post("/internal/operations/quiesce")).andExpect(status().isForbidden());
  mvc.perform(post("/internal/operations/quiesce").header("X-Operations-Token","wrong")).andExpect(status().isForbidden());
  assertThat(operations.maintenance()).isFalse();
  mvc.perform(get("/internal/operations").header("X-Operations-Token","test-only-operations-token"))
   .andExpect(status().isOk()).andExpect(jsonPath("$.maintenance").value(false)).andExpect(jsonPath("$.token").doesNotExist());
 }
 @Test void drainBlocksUploadsAndClaimsButAllowsReadsAndResume() throws Exception {
  mvc.perform(post("/internal/operations/quiesce").header("X-Operations-Token","test-only-operations-token"))
   .andExpect(status().isOk()).andExpect(jsonPath("$.maintenance").value(true));
  mvc.perform(multipart("/api/label-documents/upload").file(new MockMultipartFile("file","labels.json","application/json","{}".getBytes(StandardCharsets.UTF_8))))
   .andExpect(status().isServiceUnavailable());
  mvc.perform(get("/api/label-documents")).andExpect(status().isOk());
  assertThat(jobs.claim()).isEmpty(); assertThat(operations.state().activeWrites()).isZero();
  mvc.perform(post("/internal/operations/resume").header("X-Operations-Token","test-only-operations-token"))
   .andExpect(status().isOk()).andExpect(jsonPath("$.maintenance").value(false));
  mvc.perform(post("/api/label-documents/999999999/revisions").contentType("application/json").content("{}"))
   .andExpect(result->assertThat(result.getResponse().getStatus()).isNotEqualTo(503));
  assertThat(operations.state().activeWrites()).isZero();
 }
}
