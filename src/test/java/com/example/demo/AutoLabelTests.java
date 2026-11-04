package com.example.demo;
import com.example.demo.nuscenes.client.AutoLabelClient;
import com.example.demo.nuscenes.dto.AutoLabelDtos.*;
import com.example.demo.nuscenes.service.*;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.context.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.ObjectMapper;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"auto-label.worker.enabled=false","system-status.check-workers=false","recording.worker.enabled=false","auto-label.dataset-version=v1.0-mini",
 "spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://localhost:55432/drivescene_test}",
 "spring.datasource.username=${TEST_DB_USERNAME:drivescene}","spring.datasource.password=${TEST_DB_PASSWORD:}","nuscenes.import.enabled=false"})
@AutoConfigureMockMvc
class AutoLabelTests {
 static final ObjectMapper JSON=new ObjectMapper();
 static final AtomicReference<String> MODE=new AtomicReference<>("ok");
 static final HttpServer AI=start();
 static HttpServer start() {
  try {
   var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
   server.createContext("/auto-label",exchange->{
    var input=JSON.readTree(exchange.getRequestBody().readAllBytes());
    var box=new Box("sample-a",List.of(1.,2.,3.),List.of(2.,4.,1.),List.of(1.,0.,0.,0.),List.of(0.,0.),"car",1.,"");
    Map<String,List<Box>> results=MODE.get().equals("bad")?Map.of("sample-a",List.of(box)):Map.of("sample-a",List.of(box,box),"sample-empty",List.of());
    if(MODE.get().equals("static-classes")) results=Map.of("sample-a",List.of(withName(box,"barrier"),withName(box,"traffic_cone")),"sample-empty",List.of());
    String body=JSON.writeValueAsString(new AiResponse(UUID.randomUUID(),input.path("scene_name").asText(),8,input.path("job_id").asLong(),
     UUID.fromString(input.path("execution_token").asText()),"8class","mini_train","WORLD","VESPA_CONSTANT",Map.of("use_lidar",true),results,"run/result.json","a".repeat(64)));
    if(MODE.get().equals("fail")) body="{\"detail\":\"VESPA failed\"}";
    if(MODE.get().equals("missing-route")) body="{\"detail\":\"Not Found\"}";
    if(MODE.get().equals("vespa-code")) body="{\"detail\":{\"code\":\"VESPA_EXECUTION_FAILED\",\"message\":\"failed\"}}";
    byte[] bytes=body.getBytes(StandardCharsets.UTF_8);exchange.getResponseHeaders().set("Content-Type","application/json");
    exchange.sendResponseHeaders(switch(MODE.get()) { case "fail","vespa-code"->502; case "missing-route"->404; default->200; },bytes.length);
    try(var output=exchange.getResponseBody()) { output.write(bytes); }
   }); FakeAi.install(server); server.start();return server;
  } catch(Exception e) { throw new IllegalStateException(e); }
 }
 static Box withName(Box b,String name) { return new Box(b.sampleToken(),b.translation(),b.size(),b.rotation(),b.velocity(),name,b.detectionScore(),b.attributeName()); }
 @DynamicPropertySource static void properties(DynamicPropertyRegistry r) { r.add("ai-server.base-url",()->"http://127.0.0.1:"+AI.getAddress().getPort()); }
 @AfterAll static void shutdown() { AI.stop(0); }
 @Autowired MockMvc mvc; @Autowired JdbcClient jdbc; @Autowired AutoLabelService jobs; @Autowired AutoLabelClient client; @Autowired SystemStatusService status;
 long dataset;
 @BeforeEach void seed() {
  MODE.set("ok"); FakeAi.CAPS.set("ready"); status.clearCache();
  dataset=jdbc.sql("INSERT INTO dataset(name,version,storage_key,root_relative_path,source_checksum) VALUES(:n,'v1.0-mini','local','.','test') RETURNING id").param("n","auto-test-"+UUID.randomUUID()).query(Long.class).single();
  jdbc.sql("INSERT INTO capture_log(dataset_id,token,logfile,location,date_captured,vehicle,raw_payload) VALUES(:d,'log','x','x','x','x','{}')").param("d",dataset).update();
  jdbc.sql("INSERT INTO scene(dataset_id,token,log_token,name,description,nbr_samples,first_sample_token,last_sample_token,raw_payload) VALUES(:d,'scene-token','log','scene-0061','test',2,'sample-a','sample-empty','{}')").param("d",dataset).update();
  for(String token:List.of("sample-a","sample-empty")) jdbc.sql("INSERT INTO sample(dataset_id,token,scene_token,timestamp_us,raw_payload) VALUES(:d,:t,'scene-token',1,'{}')").param("d",dataset).param("t",token).update();
 }
 @AfterEach void cleanup() {
  jdbc.sql("DELETE FROM label_document WHERE dataset_id=:d").param("d",dataset).update();
  jdbc.sql("DROP TRIGGER IF EXISTS test_reject_completed ON auto_label_job").update();
  jdbc.sql("DROP FUNCTION IF EXISTS test_reject_completed()").update();
  jdbc.sql("DELETE FROM auto_label_job WHERE dataset_id=:d").param("d",dataset).update();
  jdbc.sql("DELETE FROM sample WHERE dataset_id=:d").param("d",dataset).update();
  jdbc.sql("DELETE FROM scene WHERE dataset_id=:d").param("d",dataset).update();
  jdbc.sql("DELETE FROM capture_log WHERE dataset_id=:d").param("d",dataset).update();
  jdbc.sql("DELETE FROM dataset WHERE id=:d").param("d",dataset).update();
 }
 long create(String key) throws Exception {
  var response=mvc.perform(post("/api/auto-label/jobs").header("Idempotency-Key",key).contentType("application/json")
   .content("{\"sceneToken\":\"scene-token\",\"classMode\":8,\"datasetId\":"+dataset+"}"))
   .andExpect(status().isAccepted()).andReturn().getResponse().getContentAsString();
  return JSON.readTree(response).path("jobId").asLong();
 }
 long boxes(long job) { return jdbc.sql("SELECT count(*) FROM predicted_annotation WHERE job_id=:j").param("j",job).query(Long.class).single(); }
 @Test void sceneHistorySurvivesReloadAndSeparatesDatasetsAndTargets() throws Exception {
  long originalDataset=dataset;
  long scene=jdbc.sql("SELECT id FROM scene WHERE dataset_id=:d").param("d",dataset).query(Long.class).single();
  long older=create("history-old"),latest=create("history-new"),otherTarget=create("history-other-target");
  jdbc.sql("UPDATE auto_label_job SET requested_targets='[\"other-scene\"]' WHERE id=:j").param("j",otherTarget).update();
  jdbc.sql("UPDATE auto_label_job SET created_at='2026-01-01T00:00:00Z' WHERE id IN (:a,:b)").param("a",older).param("b",latest).update();
  seed(); // A second upload can contain exactly the same nuScenes scene token.
  try {
   create("history-other-dataset");
   mvc.perform(get("/api/auto-label/jobs").param("sceneId",Long.toString(scene)))
    .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(2))
    .andExpect(jsonPath("$[0].jobId").value(latest)).andExpect(jsonPath("$[1].jobId").value(older))
    .andExpect(jsonPath("$[0].datasetId").value(originalDataset)).andExpect(jsonPath("$[0].sceneId").value(scene));
   mvc.perform(get("/api/auto-label/jobs")).andExpect(status().isBadRequest());
   mvc.perform(get("/api/auto-label/jobs").param("sceneId","0")).andExpect(status().isBadRequest());
   mvc.perform(get("/api/auto-label/jobs").param("sceneId",Long.toString(Long.MAX_VALUE))).andExpect(status().isNotFound());
  } finally { cleanup();dataset=originalDataset; }
 }
 @Test void completedJobBecomesAnEditableCopyWithoutChangingPredictions() throws Exception {
  long job=create("editable");new AutoLabelWorker(jobs,client).runNextJob();
  var response=mvc.perform(post("/api/label-documents/from-job/{id}",job)).andExpect(status().isOk())
   .andExpect(jsonPath("$.data.results.sample-empty").isEmpty()).andReturn().getResponse().getContentAsString();
  var document=JSON.readTree(response);long id=document.path("document").path("id").asLong();
  var data=(tools.jackson.databind.node.ObjectNode)document.path("data").deepCopy();
  ((tools.jackson.databind.node.ObjectNode)data.path("results")).putArray("sample-a");
  mvc.perform(post("/api/label-documents/{id}/revisions",id).contentType("application/json")
   .content(JSON.writeValueAsString(Map.of("expectedVersion",0,"data",data)))).andExpect(status().isCreated());
  assertThat(boxes(job)).isEqualTo(2);
  mvc.perform(post("/api/label-documents/from-job/{id}",job)).andExpect(jsonPath("$.document.id").value(id)).andExpect(jsonPath("$.revision").value(1));
 }
 @Test void postprocessValidatesReferenceAndPreservesSourceAndIdempotency() throws Exception {
  long source=create("rigid-base");new AutoLabelWorker(jobs,client).runNextJob();
  jdbc.sql("UPDATE predicted_annotation SET raw_payload=jsonb_set(raw_payload,'{track_id}',to_jsonb(box_index)) WHERE job_id=:j").param("j",source).update();
  var original=jobs.results(source);
  mvc.perform(get("/api/auto-label/jobs/{id}/results",source)).andExpect(jsonPath("$.boxes[0].trackId").value(0));
  String path="/api/auto-label/jobs/"+source+"/postprocess";
  for(String refs:List.of("{}","{\"99\":\"sample-a\"}","{\"0\":\"sample-empty\"}","{\"-1\":\"sample-a\"}"))
   mvc.perform(post(path).contentType("application/json").content("{\"references\":"+refs+"}")).andExpect(status().isBadRequest());
  String body="{\"references\":{\"0\":\"sample-a\"}}";
  var answer=mvc.perform(post(path).header("Idempotency-Key","rigid-copy").contentType("application/json").content(body)).andExpect(status().isAccepted()).andReturn().getResponse().getContentAsString();
  long copy=JSON.readTree(answer).path("jobId").asLong();
  assertThat(copy).isNotEqualTo(source);
  mvc.perform(post(path).header("Idempotency-Key","rigid-copy").contentType("application/json").content(body)).andExpect(jsonPath("$.jobId").value(copy));
  mvc.perform(post(path).header("Idempotency-Key","rigid-copy").contentType("application/json").content("{\"references\":{\"1\":\"sample-a\"}}")).andExpect(status().isConflict());
  var work=jobs.claim().orElseThrow();
  assertThat(work.id()).isEqualTo(copy);
  assertThat(work.sourceArtifactPath()).isEqualTo("run/result.json");
  assertThat(JSON.readTree(work.referenceFrames()).path("0").asString()).isEqualTo("sample-a");
  jobs.complete(work,client.run(work));
  assertThat(jobs.status(copy).status()).isEqualTo("COMPLETED");
  assertThat(jobs.results(source)).isEqualTo(original);
  assertThat(jdbc.sql("SELECT source_job_id FROM auto_label_job WHERE id=:j").param("j",copy).query(Long.class).single()).isEqualTo(source);
 }
 @Test void pendingThenHttpResultCompletedAndEmptySample() throws Exception {
  long gt=jdbc.sql("SELECT count(*) FROM gt_annotation").query(Long.class).single();
  long job=create("success"); assertThat(jobs.status(job).status()).isEqualTo("PENDING");
  long scene=jdbc.sql("SELECT id FROM scene WHERE dataset_id=:d AND token='scene-token'").param("d",dataset).query(Long.class).single();
  mvc.perform(get("/api/auto-label/jobs/{id}",job)).andExpect(status().isOk()).andExpect(jsonPath("$.jobId").value(job)).andExpect(jsonPath("$.datasetId").value(dataset))
   .andExpect(jsonPath("$.status").value("PENDING")).andExpect(jsonPath("$.errorMessage").isEmpty()).andExpect(jsonPath("$.createdAt").isNotEmpty())
   .andExpect(jsonPath("$.startedAt").isEmpty()).andExpect(jsonPath("$.completedAt").isEmpty())
   .andExpect(jsonPath("$.sceneToken").value("scene-token")).andExpect(jsonPath("$.sceneId").value(scene)).andExpect(jsonPath("$.sceneName").value("scene-0061"))
   .andExpect(jsonPath("$.classMode").value(8)).andExpect(jsonPath("$.mappingName").value("8class"));
  mvc.perform(get("/api/auto-label/jobs/{id}/results",job)).andExpect(status().isConflict());
  new AutoLabelWorker(jobs,client).runNextJob();
  mvc.perform(get("/api/auto-label/jobs/{id}",job)).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("COMPLETED"))
   .andExpect(jsonPath("$.completedAt").isNotEmpty()).andExpect(jsonPath("$.sceneToken").value("scene-token")).andExpect(jsonPath("$.sceneId").value(scene)).andExpect(jsonPath("$.classMode").value(8));
  mvc.perform(get("/api/auto-label/jobs/{id}/results",job)).andExpect(status().isOk())
   .andExpect(jsonPath("$.boxes.length()").value(2)).andExpect(jsonPath("$.sampleTokens.length()").value(2))
   .andExpect(jsonPath("$.coordinateFrame").value("WORLD")).andExpect(jsonPath("$.artifacts.length()").value(1));
  assertThat(boxes(job)).isEqualTo(2);
  assertThat(jdbc.sql("SELECT count(*) FROM auto_label_job_sample WHERE job_id=:j AND result_received_at IS NOT NULL").param("j",job).query(Long.class).single()).isEqualTo(2);
  assertThat(jdbc.sql("SELECT count(*) FROM auto_label_artifact WHERE job_id=:j").param("j",job).query(Long.class).single()).isEqualTo(1);
  assertThat(jdbc.sql("SELECT count(*) FROM predicted_annotation p JOIN sample s ON s.dataset_id=p.dataset_id AND s.token=p.sample_token WHERE job_id=:j").param("j",job).query(Long.class).single()).isEqualTo(2);
  assertThat(jdbc.sql("SELECT count(*) FROM gt_annotation").query(Long.class).single()).isEqualTo(gt);
 }
 @Test void barrierAndTrafficConeFromPatchedVespaAreStored() throws Exception {
  // ai-server/vespa-patches/0001 adds both classes to 8class; V13 extends the detection_name check.
  MODE.set("static-classes"); long job=create("static-classes"); new AutoLabelWorker(jobs,client).runNextJob();
  assertThat(jobs.status(job).status()).isEqualTo("COMPLETED");
  assertThat(jdbc.sql("SELECT detection_name FROM predicted_annotation WHERE job_id=:j ORDER BY box_index").param("j",job).query(String.class).list())
   .containsExactly("barrier","traffic_cone");
 }
 @Test void idempotentCreationAndConflict() throws Exception {
  long job=create("same");assertThat(create("same")).isEqualTo(job);
  mvc.perform(post("/api/auto-label/jobs").header("Idempotency-Key","same").contentType("application/json")
   .content("{\"sceneToken\":\"scene-token\",\"classMode\":3,\"datasetId\":"+dataset+"}")).andExpect(status().isConflict());
 }
 @Test void aiFailureAndInvalidCoverageFailWithoutBoxes() throws Exception {
  for(String mode:List.of("fail","bad")) {
   MODE.set(mode);long job=create(mode);new AutoLabelWorker(jobs,client).runNextJob();
   assertThat(jobs.status(job).status()).isEqualTo("FAILED");assertThat(jobs.status(job).errorMessage()).isNotBlank();assertThat(boxes(job)).isZero();
   assertThat(jobs.status(job).errorCode()).isEqualTo(mode.equals("fail")?"AI_HTTP_ERROR":"RESULT_VALIDATION_FAILED");
  }
 }
 @Test void upstreamRouteMissingIsNotATimeout() throws Exception {
  for(String mode:List.of("missing-route","vespa-code")) {
   MODE.set(mode);long job=create(mode);new AutoLabelWorker(jobs,client).runNextJob();
   var st=jobs.status(job);
   assertThat(st.status()).isEqualTo("FAILED");
   assertThat(st.errorCode()).isEqualTo(mode.equals("missing-route")?"AI_ENDPOINT_UNSUPPORTED":"VESPA_EXECUTION_FAILED");
   assertThat(st.errorMessage()).doesNotContainIgnoringCase("timed out");
  }
  mvc.perform(get("/api/auto-label/jobs/{id}",create("errcode-json-"+UUID.randomUUID()))).andExpect(jsonPath("$.errorCode").isEmpty());
 }
 @Test void newJobNeedsVespaReadinessButKeyReplayDoesNot() throws Exception {
  long job=create("replay");
  // AI down: the same key still returns the existing job (no AI call needed).
  FakeAi.CAPS.set("down"); status.clearCache();
  assertThat(create("replay")).isEqualTo(job);
  long before=jdbc.sql("SELECT count(*) FROM auto_label_job WHERE dataset_id=:d").param("d",dataset).query(Long.class).single();
  for(var c:List.of(new String[]{"down","AI_HTTP_ERROR"},new String[]{"vespa-unconfigured","VESPA_NOT_CONFIGURED"},new String[]{"vespa-configured","VESPA_RUNTIME_NOT_READY"},new String[]{"legacy","VESPA_NOT_CONFIGURED"},new String[]{"missing","AI_ENDPOINT_UNSUPPORTED"})) {
   FakeAi.CAPS.set(c[0]); status.clearCache();
   int refreshes=FakeAi.REFRESHES.get();
   mvc.perform(post("/api/auto-label/jobs").header("Idempotency-Key","new-"+c[0]).contentType("application/json")
     .content("{\"sceneToken\":\"scene-token\",\"classMode\":8,\"datasetId\":"+dataset+"}"))
    .andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.code").value(c[1]));
   if(c[0].equals("vespa-configured")) assertThat(FakeAi.REFRESHES.get()).isGreaterThan(refreshes); // one read-only refresh before rejecting
  }
  assertThat(jdbc.sql("SELECT count(*) FROM auto_label_job WHERE dataset_id=:d").param("d",dataset).query(Long.class).single()).isEqualTo(before);
 }
 @Test void terminalUpdateFailureRollsBackAllResults() throws Exception {
  long job=create("rollback");
  jdbc.sql("CREATE FUNCTION test_reject_completed() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN IF NEW.status = ''COMPLETED'' THEN RAISE EXCEPTION ''test completion failure''; END IF; RETURN NEW; END;'").update();
  jdbc.sql("CREATE TRIGGER test_reject_completed BEFORE UPDATE ON auto_label_job FOR EACH ROW EXECUTE FUNCTION test_reject_completed()").update();
  new AutoLabelWorker(jobs,client).runNextJob();
  assertThat(jobs.status(job).status()).isEqualTo("FAILED"); assertThat(boxes(job)).isZero();
  assertThat(jobs.status(job).errorCode()).isEqualTo("RESULT_STORAGE_FAILED");
  assertThat(jdbc.sql("SELECT count(*) FROM auto_label_artifact WHERE job_id=:j").param("j",job).query(Long.class).single()).isZero();
  assertThat(jdbc.sql("SELECT count(*) FROM auto_label_job_sample WHERE job_id=:j AND result_received_at IS NOT NULL").param("j",job).query(Long.class).single()).isZero();
 }
 @Test void lateResultAfterOperatorFailureIsRejected() throws Exception {
  // IT-18 (controlled): the worker lost contact, an operator marked the RUNNING job FAILED, then the old run answers.
  long job=create("late");
  var work=jobs.claim().orElseThrow();
  assertThat(work.id()).isEqualTo(job);
  var late=client.run(work); // the fake AI answers for the old execution token
  jdbc.sql("UPDATE auto_label_job SET status='FAILED',completed_at=now(),failure_reason='operator: worker lost',error_code='RESULT_STORAGE_FAILED' WHERE id=:j AND status='RUNNING'").param("j",job).update();
  assertThatThrownBy(()->jobs.complete(work,late)).isInstanceOf(IllegalStateException.class);
  assertThat(jobs.status(job).status()).isEqualTo("FAILED"); assertThat(boxes(job)).isZero();
  // a stale fail() from the old execution does not overwrite the operator's record either
  jobs.fail(work,"AI_TIMEOUT","late timeout");
  assertThat(jobs.status(job).errorMessage()).isEqualTo("operator: worker lost");
 }
}
