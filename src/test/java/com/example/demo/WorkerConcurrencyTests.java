package com.example.demo;
import com.example.demo.nuscenes.service.SystemStatusService;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Supplier;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.*;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * IT-08: with the real schedulers running, a VESPA call blocked inside the AI (latch) must not stop a GT-only
 * recording from being exported and becoming READY. Each worker still runs at most one task at a time.
 */
@SpringBootTest(properties={"auto-label.worker.enabled=true","recording.worker.enabled=true","auto-label.poll-delay-ms=100","recording.poll-delay-ms=100",
 "auto-label.dataset-version=v1.0-mini","nuscenes.import.enabled=false","system-status.ai-cache=0s",
 "spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://localhost:55432/drivescene_test}",
 "spring.datasource.username=${TEST_DB_USERNAME:drivescene}","spring.datasource.password=${TEST_DB_PASSWORD:}"})
@AutoConfigureMockMvc
@DirtiesContext(classMode=DirtiesContext.ClassMode.AFTER_CLASS) // stop the live schedulers before other test classes run
class WorkerConcurrencyTests {
 static final ObjectMapper JSON=new ObjectMapper();
 static final CountDownLatch RELEASE=new CountDownLatch(1);
 static final Set<String> CONCURRENT_VESPA=ConcurrentHashMap.newKeySet();
 static volatile int maxVespa=0;
 static final Path ROOT=temp();
 static final HttpServer AI=start();
 static Path temp() { try { return Files.createTempDirectory("ds2l-workers-").toRealPath(); } catch(Exception e) { throw new IllegalStateException(e); } }
 static HttpServer start() {
  try {
   var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
   server.setExecutor(Executors.newCachedThreadPool()); // the blocked /auto-label must not block /recordings
   FakeAi.install(server);
   server.createContext("/auto-label",ex->{
    var in=JSON.readTree(ex.getRequestBody().readAllBytes());
    String token=in.path("execution_token").asString(); CONCURRENT_VESPA.add(token); maxVespa=Math.max(maxVespa,CONCURRENT_VESPA.size());
    try { RELEASE.await(60,TimeUnit.SECONDS); } catch(InterruptedException e) { Thread.currentThread().interrupt(); }
    ObjectNode body=JSON.createObjectNode();
    body.put("run_id",UUID.randomUUID().toString()).put("scene_name",in.path("scene_name").asString()).put("class_mode",8).put("job_id",in.path("job_id").asLong())
     .put("execution_token",token).put("mapping_name","8class").put("split","mini_train").put("coordinate_frame","WORLD").put("score_type","VESPA_CONSTANT")
     .put("artifact_path","run/result.json").put("result_checksum","a".repeat(64));
    body.putObject("meta").put("use_lidar",true);
    var results=body.putObject("results"); results.putArray("sample-a"); results.putArray("sample-b");
    CONCURRENT_VESPA.remove(token);
    FakeAi.send(ex,200,JSON.writeValueAsString(body));
   });
   server.createContext("/recordings",ex->{
    var in=JSON.readTree(ex.getRequestBody().readAllBytes());
    long id=in.path("recording_id").asLong(); String token=in.path("execution_token").asString();
    String path=id+"-"+token+"/"+in.path("scene_name").asString()+".rrd"; byte[] rrd=("rrd-"+id).getBytes(StandardCharsets.UTF_8);
    Path file=ROOT.resolve(path); Files.createDirectories(file.getParent()); Files.write(file,rrd);
    ObjectNode body=JSON.createObjectNode();
    body.put("recording_id",id).put("execution_token",token).put("relative_path",path).put("size_bytes",rrd.length).put("checksum",sha(rrd))
     .put("sdk_version","0.38.1").put("export_version","ds2l-rrd-v3").put("application_id","drivescene2label").put("rerun_recording_id","ds2l-recording-"+id)
     .put("timeline","sample").put("time_timeline","timestamp");
    body.putObject("entities").put("lidar","world/lidar").put("ego","world/ego").put("gt","world/gt").putNull("prediction");
    var samples=body.putArray("samples");
    for(var s:in.path("samples")) samples.addObject().put("index",s.path("index").asInt()).put("sample_token",s.path("sample_token").asString()).put("lidar_points",0).put("gt_boxes",0).put("prediction_boxes",0);
    FakeAi.send(ex,200,JSON.writeValueAsString(body));
   });
   server.start(); return server;
  } catch(Exception e) { throw new IllegalStateException(e); }
 }
 static String sha(byte[] b) { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(b)); } catch(Exception e) { throw new IllegalStateException(e); } }
 @DynamicPropertySource static void props(DynamicPropertyRegistry r) {
  r.add("ai-server.base-url",()->"http://127.0.0.1:"+AI.getAddress().getPort()); r.add("recording.root",ROOT::toString);
 }
 @AfterAll static void stop() throws Exception {
  RELEASE.countDown(); AI.stop(0);
  try(var paths=Files.walk(ROOT)) { for(var p:paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(p); }
 }
 @Autowired MockMvc mvc; @Autowired JdbcClient jdbc; @Autowired SystemStatusService status;
 long dataset,scene;
 @BeforeEach void seed() {
  FakeAi.CAPS.set("ready"); status.clearCache();
  dataset=jdbc.sql("INSERT INTO dataset(name,version,storage_key,root_relative_path,source_checksum) VALUES(:n,'v1.0-mini','local','.','test') RETURNING id").param("n","workers-"+UUID.randomUUID()).query(Long.class).single();
  jdbc.sql("INSERT INTO capture_log(dataset_id,token,logfile,location,date_captured,vehicle,raw_payload) VALUES(:d,'log','x','x','x','x','{}')").param("d",dataset).update();
  scene=jdbc.sql("INSERT INTO scene(dataset_id,token,log_token,name,description,nbr_samples,first_sample_token,last_sample_token,raw_payload) VALUES(:d,'scene-w','log','scene-0061','t',2,'sample-a','sample-b','{}') RETURNING id").param("d",dataset).query(Long.class).single();
  for(String t:List.of("sample-a","sample-b")) jdbc.sql("INSERT INTO sample(dataset_id,token,scene_token,timestamp_us,raw_payload) VALUES(:d,:t,'scene-w',:ts,'{}')").param("d",dataset).param("t",t).param("ts",t.endsWith("a")?1:2).update();
 }
 @AfterEach void cleanup() {
  for(String table:List.of("scene_recording","auto_label_job","sample","scene","capture_log")) jdbc.sql("DELETE FROM "+table+" WHERE dataset_id=:d").param("d",dataset).update();
  jdbc.sql("DELETE FROM dataset WHERE id=:d").param("d",dataset).update();
 }
 String jobStatus() { return jdbc.sql("SELECT status FROM auto_label_job WHERE dataset_id=:d").param("d",dataset).query(String.class).single(); }
 String recordingStatus() { return jdbc.sql("SELECT status FROM scene_recording WHERE dataset_id=:d").param("d",dataset).query(String.class).single(); }
 static void await(Supplier<Boolean> condition,Duration limit,String what) throws InterruptedException {
  Instant end=Instant.now().plus(limit);
  while(!condition.get()) { if(Instant.now().isAfter(end)) fail("timed out waiting for "+what); Thread.sleep(50); }
 }
 @Test void recordingCompletesWhileAVespaCallIsBlocked() throws Exception {
  mvc.perform(post("/api/auto-label/jobs").header("Idempotency-Key","it-08").contentType("application/json")
   .content("{\"sceneToken\":\"scene-w\",\"classMode\":8,\"datasetId\":"+dataset+"}")).andExpect(status().isAccepted());
  await(()->"RUNNING".equals(jobStatus()) && !CONCURRENT_VESPA.isEmpty(),Duration.ofSeconds(15),"VESPA call to start");
  mvc.perform(post("/api/scenes/{id}/recordings",scene)).andExpect(status().isAccepted());
  await(()->"READY".equals(recordingStatus()),Duration.ofSeconds(15),"recording READY during the VESPA call");
  assertThat(jobStatus()).isEqualTo("RUNNING");
  RELEASE.countDown();
  await(()->"COMPLETED".equals(jobStatus()),Duration.ofSeconds(15),"job completion");
  assertThat(maxVespa).isEqualTo(1);
 }
}
