package com.example.demo;
import com.example.demo.nuscenes.client.RecordingClient;
import com.example.demo.nuscenes.service.*;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.*;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;
import static org.assertj.core.api.Assertions.*;
import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"auto-label.worker.enabled=false","system-status.check-workers=false","recording.worker.enabled=false",
 "spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://localhost:55432/drivescene_test}",
 "spring.datasource.username=${TEST_DB_USERNAME:drivescene}","spring.datasource.password=${TEST_DB_PASSWORD:}","nuscenes.import.enabled=false"})
@AutoConfigureMockMvc
class RecordingTests {
 static final ObjectMapper JSON=new ObjectMapper();
 static final AtomicReference<String> MODE=new AtomicReference<>("ok");
 static final AtomicReference<JsonNode> LAST=new AtomicReference<>();
 static final Path BASE=temp(), ROOT=BASE.resolve("recordings");
 static final HttpServer AI=start();
 static Path temp() { try { return Files.createTempDirectory("ds2l-recording-test-").toRealPath(); } catch(Exception e) { throw new IllegalStateException(e); } }
 /** Fake AI /recordings: writes a small fake .rrd under ROOT and answers per MODE. */
 static HttpServer start() {
  try {
   Files.createDirectories(ROOT);
   var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
   server.createContext("/recordings",exchange->{
    var input=JSON.readTree(exchange.getRequestBody().readAllBytes()); LAST.set(input);
    String mode=MODE.get(); long id=input.path("recording_id").asLong(); String token=input.path("execution_token").asText();
    String path=id+"-"+token+"/"+input.path("scene_name").asText()+".rrd";
    byte[] rrd=("RRD-fake-recording-"+id).getBytes(StandardCharsets.UTF_8);
    Path file=ROOT.resolve(path); Files.createDirectories(file.getParent()); Files.write(file,rrd);
    ObjectNode body=JSON.createObjectNode();
    body.put("recording_id",id).put("execution_token",token).put("relative_path",mode.equals("traversal")?"../escape.rrd":path).put("size_bytes",rrd.length)
     .put("checksum",mode.equals("checksum")?"b".repeat(64):sha(rrd)).put("sdk_version",mode.equals("sdk")?"0.21.0":"0.38.1").put("export_version","ds2l-rrd-v2")
     .put("application_id","drivescene2label").put("rerun_recording_id","ds2l-recording-"+id).put("timeline","sample").put("time_timeline","timestamp");
    body.putObject("entities").put("lidar","world/lidar").put("ego","world/ego").put("gt","world/gt").put("prediction","world/prediction");
    var samples=body.putArray("samples");
    for(JsonNode s:input.path("samples")) samples.addObject().put("index",s.path("index").asInt()).put("sample_token",s.path("sample_token").asText())
     .put("lidar_points",s.path("lidar").isNull()?0:34688).put("gt_boxes",s.path("gt").size()+(mode.equals("count")?1:0)).put("prediction_boxes",s.path("predictions").size());
    byte[] bytes=(mode.equals("fail")?"{\"detail\":{\"code\":\"RECORDING_EXPORT_FAILED\",\"message\":\"exporter crashed\"}}":JSON.writeValueAsString(body)).getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders().set("Content-Type","application/json"); exchange.sendResponseHeaders(mode.equals("fail")?502:200,bytes.length);
    try(var output=exchange.getResponseBody()) { output.write(bytes); }
   }); FakeAi.install(server); server.start(); return server;
  } catch(Exception e) { throw new IllegalStateException(e); }
 }
 static String sha(byte[] bytes) { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); } catch(Exception e) { throw new IllegalStateException(e); } }
 @DynamicPropertySource static void properties(DynamicPropertyRegistry r) {
  r.add("ai-server.base-url",()->"http://127.0.0.1:"+AI.getAddress().getPort()); r.add("recording.root",ROOT::toString);
 }
 @AfterAll static void shutdown() throws Exception {
  AI.stop(0);
  try(var paths=Files.walk(BASE)) { for(var p:paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(p); }
 }
 @Autowired MockMvc mvc; @Autowired JdbcClient jdbc; @Autowired RecordingService recordings; @Autowired RecordingClient client; @Autowired SystemStatusService status;
 final List<Long> datasets=new ArrayList<>();
 long dataset,scene,otherScene,job,pendingJob,otherSceneJob,gt1,gt2,pred0,pred1;

 long dataset(String name) {
  long d=jdbc.sql("INSERT INTO dataset(name,version,storage_key,root_relative_path,source_checksum) VALUES(:n,'v1.0-mini','local','.','test') RETURNING id").param("n",name+"-"+UUID.randomUUID()).query(Long.class).single();
  datasets.add(d);
  jdbc.sql("INSERT INTO capture_log(dataset_id,token,logfile,location,date_captured,vehicle,raw_payload) VALUES(:d,'log','x','x','x','x','{}')").param("d",d).update();
  return d;
 }
 long scene(long d,String token,String name) {
  return jdbc.sql("INSERT INTO scene(dataset_id,token,log_token,name,description,nbr_samples,first_sample_token,last_sample_token,raw_payload) VALUES(:d,:t,'log',:n,'test',2,'x','x','{}') RETURNING id")
   .param("d",d).param("t",token).param("n",name).query(Long.class).single();
 }
 void sample(long d,String token,String scene,long ts) { jdbc.sql("INSERT INTO sample(dataset_id,token,scene_token,timestamp_us,raw_payload) VALUES(:d,:t,:s,:ts,'{}')").param("d",d).param("t",token).param("s",scene).param("ts",ts).update(); }
 long job(long d,String key,String scene,String status) {
  boolean done=status.equals("COMPLETED");
  return jdbc.sql("""
   INSERT INTO auto_label_job(dataset_id,request_key,target_type,requested_targets,model_version,config_name,model_config,mapping_name,class_names,status,execution_token,result_checksum,started_at,completed_at)
   VALUES(:d,:k,'SCENE',jsonb_build_array(CAST(:s AS text)),'v','c','{}','8class','["car","truck"]',:st,
    CASE WHEN :done THEN gen_random_uuid() END,CASE WHEN :done THEN 'checksum' END,CASE WHEN :done THEN now() END,CASE WHEN :done THEN now() END) RETURNING id
   """).param("d",d).param("k",key).param("s",scene).param("st",status).param("done",done).query(Long.class).single();
 }
 long gt(String token) {
  return jdbc.sql("""
   INSERT INTO gt_annotation(dataset_id,token,sample_token,instance_token,center_x,center_y,center_z,size_w,size_l,size_h,rotation_w,rotation_x,rotation_y,rotation_z,num_lidar_pts,num_radar_pts,raw_payload)
   VALUES(:d,:t,'sample-b','inst-1',1,2,3,2,4,1.5,1,0,0,0,5,0,'{}') RETURNING id""").param("d",dataset).param("t",token).query(Long.class).single();
 }
 long prediction(int index,String name) {
  return jdbc.sql("""
   INSERT INTO predicted_annotation(job_id,dataset_id,sample_token,box_index,detection_name,center_x,center_y,center_z,size_w,size_l,size_h,rotation_w,rotation_x,rotation_y,rotation_z,velocity_x,velocity_y,detection_score,raw_payload)
   VALUES(:j,:d,'sample-a',:i,:n,1,2,3,2,4,1.5,1,0,0,0,0,0,1,'{}') RETURNING id""").param("j",job).param("d",dataset).param("i",index).param("n",name).query(Long.class).single();
 }
 @BeforeEach void seed() {
  MODE.set("ok"); LAST.set(null); FakeAi.CAPS.set("ready"); status.clearCache();
  dataset=dataset("recording-test");
  scene=scene(dataset,"scene-token","scene-rec"); otherScene=scene(dataset,"scene-other","scene-other");
  // Timestamp order (sample-b, sample-a) differs from token order on purpose.
  sample(dataset,"sample-b","scene-token",100); sample(dataset,"sample-a","scene-token",200); sample(dataset,"sample-o","scene-other",1);
  jdbc.sql("INSERT INTO sensor(dataset_id,token,channel,modality,raw_payload) VALUES(:d,'lidar','LIDAR_TOP','lidar','{}'),(:d,'cam','CAM_FRONT','camera','{}')").param("d",dataset).update();
  jdbc.sql("""
   INSERT INTO calibrated_sensor(dataset_id,token,sensor_token,translation_x,translation_y,translation_z,rotation_w,rotation_x,rotation_y,rotation_z,raw_payload)
   VALUES(:d,'cal-lidar','lidar',0.9,0,1.8,0.7071068,0,0,-0.7071068,'{}'),(:d,'cal-cam','cam',1.7,0,1.5,0.5,-0.5,0.5,-0.5,'{}')""").param("d",dataset).update();
  jdbc.sql("""
   INSERT INTO ego_pose(dataset_id,token,timestamp_us,translation_x,translation_y,translation_z,rotation_w,rotation_x,rotation_y,rotation_z,raw_payload)
   VALUES(:d,'pose-b',100,400,1100,0,1,0,0,0,'{}'),(:d,'pose-sweep',150,401,1100,0,1,0,0,0,'{}')""").param("d",dataset).update();
  jdbc.sql("""
   INSERT INTO sample_data(dataset_id,token,sample_token,ego_pose_token,calibrated_sensor_token,relative_path,fileformat,timestamp_us,is_key_frame,width,height,raw_payload) VALUES
   (:d,'lidar-b','sample-b','pose-b','cal-lidar','samples/LIDAR_TOP/b.pcd.bin','bin',100,true,0,0,'{}'),
   (:d,'lidar-sweep','sample-b','pose-sweep','cal-lidar','sweeps/LIDAR_TOP/s.pcd.bin','bin',150,false,0,0,'{}'),
   (:d,'cam-b','sample-b','pose-b','cal-cam','samples/CAM_FRONT/b.jpg','jpg',100,true,1600,900,'{}')""").param("d",dataset).update();
  jdbc.sql("INSERT INTO category(dataset_id,token,name,description,raw_payload) VALUES(:d,'cat-car','vehicle.car','x','{}')").param("d",dataset).update();
  jdbc.sql("INSERT INTO object_instance(dataset_id,token,category_token,nbr_annotations,first_annotation_token,last_annotation_token,raw_payload) VALUES(:d,'inst-1','cat-car',2,'gt-1','gt-2','{}')").param("d",dataset).update();
  gt2=gt("gt-2"); gt1=gt("gt-1"); // ids follow insertion; the REST/recording order is by token
  job=job(dataset,"done","scene-token","COMPLETED"); pendingJob=job(dataset,"pending","scene-token","PENDING"); otherSceneJob=job(dataset,"other","scene-other","COMPLETED");
  for(String token:List.of("sample-b","sample-a")) jdbc.sql("INSERT INTO auto_label_job_sample(job_id,dataset_id,sample_token) VALUES(:j,:d,:t)").param("j",job).param("d",dataset).param("t",token).update();
  pred1=prediction(1,"truck"); pred0=prediction(0,"car");
 }
 @AfterEach void cleanup() {
  for(long d:datasets) for(String table:List.of("scene_recording","auto_label_job","gt_annotation","object_instance","category","sample_data","ego_pose","calibrated_sensor","sensor","sample","scene","capture_log"))
   jdbc.sql("DELETE FROM "+table+" WHERE dataset_id=:d").param("d",d).update();
  for(long d:datasets) jdbc.sql("DELETE FROM dataset WHERE id=:d").param("d",d).update();
 }
 void work() { new RecordingWorker(recordings,client).runNextRecording(); }
 long create(long sceneId,String body,int status,boolean reused) throws Exception {
  var request=post("/api/scenes/{id}/recordings",sceneId); if(body!=null) request=request.contentType("application/json").content(body);
  var response=mvc.perform(request).andExpect(status().is(status)).andExpect(jsonPath("$.reused").value(reused)).andReturn().getResponse().getContentAsString();
  return JSON.readTree(response).path("recordingId").asLong();
 }
 String recordingStatus(long id) { return jdbc.sql("SELECT status FROM scene_recording WHERE id=:id").param("id",id).query(String.class).single(); }
 String jobSnapshot() {
  return jdbc.sql("SELECT CAST(row_to_json(j) AS text) FROM auto_label_job j WHERE id=:j").param("j",job).query(String.class).single()
   +jdbc.sql("SELECT count(*)||':'||string_agg(id::text,',' ORDER BY id) FROM predicted_annotation WHERE job_id=:j").param("j",job).query(String.class).single();
 }

 @Test void createReuseWorkerReadyMappingAndContent() throws Exception {
  long id=create(scene,"{\"jobId\":"+job+"}",202,false);
  assertThat(create(scene,"{\"jobId\":"+job+"}",200,true)).isEqualTo(id);
  mvc.perform(get("/api/recordings/{id}",id)).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("PENDING")).andExpect(jsonPath("$.recordingId").value(id))
   .andExpect(jsonPath("$.datasetId").value(dataset)).andExpect(jsonPath("$.sceneId").value(scene)).andExpect(jsonPath("$.sceneToken").value("scene-token"))
   .andExpect(jsonPath("$.sceneName").value("scene-rec")).andExpect(jsonPath("$.jobId").value(job)).andExpect(jsonPath("$.sdkVersion").value("0.38.1"))
   .andExpect(jsonPath("$.exportVersion").value("ds2l-rrd-v2")).andExpect(jsonPath("$.coordinateFrame").value("WORLD")).andExpect(jsonPath("$.samples.length()").value(0))
   .andExpect(jsonPath("$.contentUrl").isEmpty()).andExpect(jsonPath("$.entities").isEmpty());
  mvc.perform(get("/api/recordings/{id}/content",id)).andExpect(status().isConflict());
  work();
  assertThat(recordingStatus(id)).isEqualTo("READY");
  // Request built from Spring's DB: timestamp order, keyframe LIDAR_TOP only, GT by token with category, predictions by box_index.
  JsonNode request=LAST.get();
  assertThat(request.path("recording_id").asLong()).isEqualTo(id);
  assertThat(request.path("execution_token").asText()).isEqualTo(jdbc.sql("SELECT CAST(execution_token AS text) FROM scene_recording WHERE id=:id").param("id",id).query(String.class).single());
  assertThat(request.path("scene_name").asText()).isEqualTo("scene-rec"); assertThat(request.path("scene_token").asText()).isEqualTo("scene-token"); assertThat(request.path("job_id").asLong()).isEqualTo(job);
  var s0=request.path("samples").get(0); var s1=request.path("samples").get(1);
  assertThat(request.path("samples").size()).isEqualTo(2);
  assertThat(s0.path("index").asInt()).isZero(); assertThat(s0.path("sample_token").asText()).isEqualTo("sample-b"); assertThat(s0.path("timestamp_us").asLong()).isEqualTo(100);
  assertThat(s0.path("lidar").path("relative_path").asText()).isEqualTo("samples/LIDAR_TOP/b.pcd.bin");
  assertThat(s0.path("lidar").path("sensor_translation").toString()).isEqualTo("[0.9,0.0,1.8]");
  assertThat(s0.path("lidar").path("sensor_rotation").toString()).isEqualTo("[0.7071068,0.0,0.0,-0.7071068]");
  assertThat(s0.path("lidar").path("ego_translation").toString()).isEqualTo("[400.0,1100.0,0.0]");
  assertThat(s0.path("gt").size()).isEqualTo(2); assertThat(s0.path("gt").get(0).path("id").asLong()).isEqualTo(gt1); assertThat(s0.path("gt").get(1).path("id").asLong()).isEqualTo(gt2);
  assertThat(s0.path("gt").get(0).path("category_name").asText()).isEqualTo("vehicle.car");
  assertThat(s0.path("gt").get(0).path("size_wlh").toString()).isEqualTo("[2.0,4.0,1.5]"); assertThat(s0.path("gt").get(0).path("rotation_wxyz").toString()).isEqualTo("[1.0,0.0,0.0,0.0]");
  assertThat(s0.path("predictions").size()).isZero();
  assertThat(s1.path("sample_token").asText()).isEqualTo("sample-a"); assertThat(s1.path("lidar").isNull()).isTrue(); assertThat(s1.path("gt").size()).isZero();
  assertThat(s1.path("predictions").get(0).path("id").asLong()).isEqualTo(pred0); assertThat(s1.path("predictions").get(0).path("detection_name").asText()).isEqualTo("car");
  assertThat(s1.path("predictions").get(1).path("id").asLong()).isEqualTo(pred1);
  mvc.perform(get("/api/recordings/{id}",id)).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("READY"))
   .andExpect(jsonPath("$.contentUrl").value("/api/recordings/"+id+"/content")).andExpect(jsonPath("$.applicationId").value("drivescene2label"))
   .andExpect(jsonPath("$.rerunRecordingId").value("ds2l-recording-"+id)).andExpect(jsonPath("$.timeline").value("sample")).andExpect(jsonPath("$.timeTimeline").value("timestamp"))
   .andExpect(jsonPath("$.entities.lidar").value("world/lidar")).andExpect(jsonPath("$.entities.gt").value("world/gt")).andExpect(jsonPath("$.entities.prediction").value("world/prediction"))
   .andExpect(jsonPath("$.samples.length()").value(2)).andExpect(jsonPath("$.samples[0].index").value(0)).andExpect(jsonPath("$.samples[0].sampleToken").value("sample-b"))
   .andExpect(jsonPath("$.samples[0].timestampUs").value(100)).andExpect(jsonPath("$.samples[0].lidarPoints").value(34688))
   .andExpect(jsonPath("$.samples[0].gtAnnotationIds[0]").value(gt1)).andExpect(jsonPath("$.samples[0].gtAnnotationIds[1]").value(gt2)).andExpect(jsonPath("$.samples[0].predictionIds.length()").value(0))
   .andExpect(jsonPath("$.samples[1].lidarPoints").value(0)).andExpect(jsonPath("$.samples[1].gtAnnotationIds.length()").value(0))
   .andExpect(jsonPath("$.samples[1].predictionIds[0]").value(pred0)).andExpect(jsonPath("$.samples[1].predictionIds[1]").value(pred1))
   .andExpect(jsonPath("$.errorMessage").isEmpty()).andExpect(jsonPath("$.completedAt").isNotEmpty());
  byte[] rrd=("RRD-fake-recording-"+id).getBytes(StandardCharsets.UTF_8);
  mvc.perform(get("/api/recordings/{id}/content",id)).andExpect(status().isOk()).andExpect(content().contentType("application/octet-stream"))
   .andExpect(header().longValue("Content-Length",rrd.length)).andExpect(header().string("X-Content-Type-Options","nosniff")).andExpect(content().bytes(rrd));
  mvc.perform(get("/api/recordings/{id}/content",id).header("Range","bytes=0-3")).andExpect(status().isPartialContent()).andExpect(content().bytes(Arrays.copyOf(rrd,4)));
  assertThat(create(scene,"{\"jobId\":"+job+"}",200,true)).isEqualTo(id);
  // Without jobId: separate recording, empty predictions, prediction entity null.
  long gtOnly=create(scene,null,202,false); assertThat(gtOnly).isNotEqualTo(id);
  assertThat(create(scene,"{}",200,true)).isEqualTo(gtOnly);
  work();
  assertThat(LAST.get().path("job_id").isNull()).isTrue(); assertThat(LAST.get().path("samples").get(1).path("predictions").size()).isZero();
  mvc.perform(get("/api/recordings/{id}",gtOnly)).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("READY")).andExpect(jsonPath("$.jobId").isEmpty())
   .andExpect(jsonPath("$.entities.prediction").isEmpty()).andExpect(jsonPath("$.samples[1].predictionIds.length()").value(0));
  mvc.perform(get("/api/scenes/{id}/recordings",scene)).andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(2))
   .andExpect(jsonPath("$[0].recordingId").value(gtOnly)).andExpect(jsonPath("$[1].recordingId").value(id)).andExpect(jsonPath("$[0].samples").doesNotExist())
   .andExpect(jsonPath("$[1].contentUrl").value("/api/recordings/"+id+"/content"));
  mvc.perform(get("/api/scenes/{id}/recordings",otherScene)).andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(0));
 }
 @Test void invalidAiResultFailsOnlyTheRecordingAndANewPostRecreatesIt() throws Exception {
  String before=jobSnapshot(); long gtRows=jdbc.sql("SELECT count(*) FROM gt_annotation").query(Long.class).single();
  Map<String,String> reasons=Map.of("count","box count","fail","HTTP 502 RECORDING_EXPORT_FAILED","sdk","SDK version","checksum","checksum","traversal","unsafe recording path");
  Set<Long> failed=new HashSet<>();
  for(var mode:reasons.entrySet()) {
   MODE.set(mode.getKey());
   long id=create(scene,"{\"jobId\":"+job+"}",202,false); assertThat(failed.add(id)).isTrue();
   work();
   assertThat(recordingStatus(id)).isEqualTo("FAILED");
   mvc.perform(get("/api/recordings/{id}",id)).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("FAILED"))
    .andExpect(jsonPath("$.errorMessage").value(containsString(mode.getValue()))).andExpect(jsonPath("$.errorCode").value(mode.getKey().equals("fail")?"RECORDING_EXPORT_FAILED":"RECORDING_INVALID_RESULT")).andExpect(jsonPath("$.contentUrl").isEmpty()).andExpect(jsonPath("$.samples.length()").value(0));
   mvc.perform(get("/api/recordings/{id}/content",id)).andExpect(status().isConflict());
  }
  assertThat(jobSnapshot()).isEqualTo(before);
  assertThat(jdbc.sql("SELECT count(*) FROM gt_annotation").query(Long.class).single()).isEqualTo(gtRows);
  MODE.set("ok");
  long retry=create(scene,"{\"jobId\":"+job+"}",202,false); assertThat(failed).doesNotContain(retry);
  work();
  assertThat(recordingStatus(retry)).isEqualTo("READY"); assertThat(jobSnapshot()).isEqualTo(before);
  mvc.perform(get("/api/scenes/{id}/recordings",scene)).andExpect(jsonPath("$.length()").value(reasons.size()+1)).andExpect(jsonPath("$[0].recordingId").value(retry));
 }
 @Test void jobAndSceneValidation() throws Exception {
  mvc.perform(post("/api/scenes/{id}/recordings",Long.MAX_VALUE)).andExpect(status().isNotFound());
  mvc.perform(post("/api/scenes/{id}/recordings",scene).contentType("application/json").content("{\"jobId\":"+Long.MAX_VALUE+"}")).andExpect(status().isNotFound());
  mvc.perform(post("/api/scenes/{id}/recordings",scene).contentType("application/json").content("{\"jobId\":"+pendingJob+"}")).andExpect(status().isConflict());
  mvc.perform(post("/api/scenes/{id}/recordings",scene).contentType("application/json").content("{\"jobId\":"+otherSceneJob+"}")).andExpect(status().isConflict());
  mvc.perform(post("/api/scenes/{id}/recordings",scene).contentType("application/json").content("{\"jobId\":0}")).andExpect(status().isBadRequest());
  mvc.perform(post("/api/scenes/{id}/recordings",scene).contentType("application/json").content("{\"jobId\":\"abc\"}")).andExpect(status().isBadRequest());
  // A COMPLETED job of the same scene token in another dataset is not visible from this dataset's scene.
  long other=dataset("recording-other"); scene(other,"scene-token","scene-rec"); long foreign=job(other,"done","scene-token","COMPLETED");
  mvc.perform(post("/api/scenes/{id}/recordings",scene).contentType("application/json").content("{\"jobId\":"+foreign+"}")).andExpect(status().isNotFound());
  assertThat(jdbc.sql("SELECT count(*) FROM scene_recording WHERE dataset_id IN (:d,:o)").param("d",dataset).param("o",other).query(Long.class).single()).isZero();
  mvc.perform(get("/api/recordings/{id}",Long.MAX_VALUE)).andExpect(status().isNotFound());
  mvc.perform(get("/api/recordings/{id}/content",Long.MAX_VALUE)).andExpect(status().isNotFound());
  mvc.perform(get("/api/scenes/{id}/recordings",Long.MAX_VALUE)).andExpect(status().isNotFound());
 }
 @Test void contentRejectsPathsOutsideRecordingRoot() throws Exception {
  Path outside=Files.writeString(BASE.resolve("outside.rrd"),"outside");
  Files.createSymbolicLink(ROOT.resolve("escape-"+dataset+".rrd"),outside);
  String inside="inside-"+dataset+".rrd"; Files.writeString(ROOT.resolve(inside),"inside");
  int n=0;
  for(String path:List.of("../outside.rrd",outside.toString(),"escape-"+dataset+".rrd","missing-"+dataset+".rrd",inside)) {
   long id=jdbc.sql("""
    INSERT INTO scene_recording(dataset_id,scene_token,export_version,sdk_version,status,execution_token,relative_path,size_bytes,checksum,metadata,started_at,completed_at)
    VALUES(:d,'scene-token',:e,'0.38.1','READY',gen_random_uuid(),:p,1,repeat('a',64),'{}',now(),now()) RETURNING id""").param("d",dataset).param("e","path-"+(n++)).param("p",path).query(Long.class).single();
   mvc.perform(get("/api/recordings/{id}/content",id)).andExpect(path.equals(inside)?status().isOk():status().isNotFound());
  }
 }
 @Test void lostReadyFileIsReleasedAndOnlyTheRecordingIsRecreated() throws Exception {
  String before=jobSnapshot();
  long id=create(scene,"{\"jobId\":"+job+"}",202,false); work(); assertThat(recordingStatus(id)).isEqualTo("READY");
  String rel=jdbc.sql("SELECT relative_path FROM scene_recording WHERE id=:id").param("id",id).query(String.class).single();
  Files.delete(ROOT.resolve(rel));
  mvc.perform(get("/api/recordings/{id}/content",id)).andExpect(status().isNotFound()).andExpect(jsonPath("$.code").value("RECORDING_FILE_MISSING"));
  mvc.perform(get("/api/recordings/{id}",id)).andExpect(jsonPath("$.status").value("FAILED")).andExpect(jsonPath("$.errorCode").value("RECORDING_FILE_MISSING"));
  long again=create(scene,"{\"jobId\":"+job+"}",202,false); assertThat(again).isNotEqualTo(id);
  work(); assertThat(recordingStatus(again)).isEqualTo("READY"); assertThat(jobSnapshot()).isEqualTo(before);
  // reuse path also notices a lost file without a content GET
  rel=jdbc.sql("SELECT relative_path FROM scene_recording WHERE id=:id").param("id",again).query(String.class).single();
  Files.delete(ROOT.resolve(rel));
  long third=create(scene,"{\"jobId\":"+job+"}",202,false); assertThat(third).isNotIn(id,again);
 }
 @Test void newRecordingNeedsReadinessButReuseDoesNot() throws Exception {
  long id=create(scene,null,202,false);
  FakeAi.CAPS.set("down"); status.clearCache();
  assertThat(create(scene,null,200,true)).isEqualTo(id); // live recording reused while the AI is down
  for(var c:List.of(new String[]{"legacy","LEGACY_NOT_VERIFIED"},new String[]{"missing","AI_ENDPOINT_UNSUPPORTED"},new String[]{"down","AI_HTTP_ERROR"})) {
   FakeAi.CAPS.set(c[0]); status.clearCache();
   mvc.perform(post("/api/scenes/{id}/recordings",scene).contentType("application/json").content("{\"jobId\":"+job+"}"))
    .andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.code").value(c[1]));
  }
  assertThat(jdbc.sql("SELECT count(*) FROM scene_recording WHERE dataset_id=:d").param("d",dataset).query(Long.class).single()).isEqualTo(1);
 }
}
