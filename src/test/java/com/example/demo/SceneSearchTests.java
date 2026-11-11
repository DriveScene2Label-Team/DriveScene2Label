package com.example.demo;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={
 "auto-label.worker.enabled=false","recording.worker.enabled=false",
 "spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://localhost:55432/drivescene_test}",
 "spring.datasource.username=${TEST_DB_USERNAME:drivescene}",
 "spring.datasource.password=${TEST_DB_PASSWORD:}", "nuscenes.import.enabled=false"})
@AutoConfigureMockMvc
@Transactional
class SceneSearchTests {
 private static final String MODEL="ViT-L-14-quickgelu/openai", PREPROCESS="lr-square-crop-mean";
 private static final AtomicReference<String> RESPONSE=new AtomicReference<>();
 private static final AtomicReference<String> REQUEST=new AtomicReference<>();
 private static final AtomicInteger STATUS=new AtomicInteger(200), CALLS=new AtomicInteger();
 private static final HttpServer AI=startAi();
 private static HttpServer startAi() {
  try {
   var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
   server.createContext("/embedding/",exchange->{
    CALLS.incrementAndGet();
    REQUEST.set(exchange.getRequestMethod()+" "+new String(exchange.getRequestBody().readAllBytes(),StandardCharsets.UTF_8));
    byte[] body=RESPONSE.get().getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders().set("Content-Type","application/json");
    exchange.sendResponseHeaders(STATUS.get(),body.length);
    try(var output=exchange.getResponseBody()) { output.write(body); }
   });
   server.start(); return server;
  } catch(Exception e) { throw new IllegalStateException(e); }
 }
 @DynamicPropertySource static void aiProperties(DynamicPropertyRegistry registry) {
  registry.add("ai-server.base-url",()->"http://127.0.0.1:"+AI.getAddress().getPort());
 }
 @AfterAll static void stopAi() { AI.stop(0); }
 @BeforeEach void resetAi() { STATUS.set(200); RESPONSE.set(aiResponse()); CALLS.set(0); }
 @Autowired JdbcClient jdbc;
 @Autowired MockMvc mvc;
 @Autowired com.example.demo.nuscenes.service.DatasetSearchIndexService indexes;
 @Autowired com.example.demo.nuscenes.storage.DatasetStorage storage;

 private static String vector(double cosine) {
  var b=new StringBuilder("[").append(cosine).append(',').append(Math.sqrt(1-cosine*cosine));
  for(int i=2;i<768;i++) b.append(",0");
  return b.append(']').toString();
 }
 private static String aiResponse() { return "{\"model_name\":\""+MODEL+"\",\"dimension\":768,\"preprocess\":\"clip-text-tokenizer\",\"embedding\":"+vector(1)+"}"; }
 private long dataset(String version) {
  long id=jdbc.sql("INSERT INTO dataset(name,version,storage_key,root_relative_path,source_checksum) VALUES('search-test',:v,'test','.','test') RETURNING id")
    .param("v",version).query(Long.class).single();
  jdbc.sql("INSERT INTO capture_log(dataset_id,token,logfile,location,date_captured,vehicle,raw_payload) VALUES(:d,'log','test','test','test','test','{}')").param("d",id).update();
  jdbc.sql("INSERT INTO sensor(dataset_id,token,channel,modality,raw_payload) VALUES(:d,'sensor','CAM_FRONT','camera','{}')").param("d",id).update();
  jdbc.sql("INSERT INTO calibrated_sensor(dataset_id,token,sensor_token,translation_x,translation_y,translation_z,rotation_w,rotation_x,rotation_y,rotation_z,raw_payload) VALUES(:d,'cal','sensor',0,0,0,1,0,0,0,'{}')").param("d",id).update();
  jdbc.sql("INSERT INTO ego_pose(dataset_id,token,timestamp_us,translation_x,translation_y,translation_z,rotation_w,rotation_x,rotation_y,rotation_z,raw_payload) VALUES(:d,'pose',1,0,0,0,1,0,0,0,'{}')").param("d",id).update();
  return id;
 }
 private void scene(long dataset,String token,String name,double... similarities) {
  jdbc.sql("INSERT INTO scene(dataset_id,token,log_token,name,description,nbr_samples,first_sample_token,last_sample_token,raw_payload) VALUES(:d,:t,'log',:n,'test scene',1,:s,:s,'{}')")
    .param("d",dataset).param("t",token).param("n",name).param("s","sample-"+token).update();
  jdbc.sql("INSERT INTO sample(dataset_id,token,scene_token,timestamp_us,raw_payload) VALUES(:d,:s,:t,1,'{}')")
    .param("d",dataset).param("s","sample-"+token).param("t",token).update();
  for(int i=0;i<similarities.length;i++) image(dataset,token,i,similarities[i],true,MODEL,PREPROCESS);
 }
 private void image(long dataset,String scene,int number,double similarity,boolean keyframe,String model,String preprocess) {
  String token=scene+"-file-"+number;
  jdbc.sql("INSERT INTO sample_data(dataset_id,token,sample_token,ego_pose_token,calibrated_sensor_token,relative_path,fileformat,timestamp_us,is_key_frame,width,height,raw_payload) VALUES(:d,:t,:s,'pose','cal',:p,'jpg',1,:key,1600,900,'{}')")
    .param("d",dataset).param("t",token).param("s","sample-"+scene).param("p","samples/"+token+".jpg").param("key",keyframe).update();
  jdbc.sql("INSERT INTO image_embedding(dataset_id,sample_data_token,model_name,preprocess,embedding) VALUES(:d,:t,:m,:p,CAST(:v AS vector))")
    .param("d",dataset).param("t",token).param("m",model).param("p",preprocess).param("v",vector(similarity)).update();
 }
 @Test void imageStoreSkipOverwriteAndValidation() throws Exception {
  long d=dataset("image-write"); scene(d,"a","A",1);
  jdbc.sql("UPDATE dataset SET storage_key='nuscenes' WHERE id=:d").param("d",d).update();
  long id=jdbc.sql("SELECT id FROM sample_data WHERE dataset_id=:d").param("d",d).query(Long.class).single();
  jdbc.sql("DELETE FROM image_embedding WHERE dataset_id=:d").param("d",d).update();
  RESPONSE.set(aiResponse().replace("clip-text-tokenizer",PREPROCESS));
  mvc.perform(post("/api/sensor-files/{id}/embedding",id)).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("STORED"));
  assertThat(REQUEST.get()).contains("image_path","samples/a-file-0.jpg",PREPROCESS);
  mvc.perform(post("/api/sensor-files/{id}/embedding",id)).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("SKIPPED"));
  assertThat(CALLS.get()).isEqualTo(1);
  RESPONSE.set(aiResponse().replace("clip-text-tokenizer",PREPROCESS).replace(vector(1),vector(.5)));
  mvc.perform(post("/api/sensor-files/{id}/embedding",id).param("overwrite","true")).andExpect(status().isOk());
  assertThat(jdbc.sql("SELECT count(*) FROM image_embedding WHERE dataset_id=:d").param("d",d).query(Long.class).single()).isEqualTo(1);
  assertThat(jdbc.sql("SELECT embedding <=> CAST(:v AS vector) FROM image_embedding WHERE dataset_id=:d").param("v",vector(.5)).param("d",d).query(Double.class).single()).isCloseTo(0,within(1e-6));
  RESPONSE.set(aiResponse());
  mvc.perform(post("/api/sensor-files/{id}/embedding",id).param("overwrite","true")).andExpect(status().isBadGateway());
  STATUS.set(404);
  mvc.perform(post("/api/sensor-files/{id}/embedding",id).param("overwrite","true")).andExpect(status().isNotFound());
 }
 @Test void emptySceneSearchAndMissingRequest() throws Exception {
  mvc.perform(get("/api/search/scenes").param("q","road")).andExpect(status().isOk()).andExpect(jsonPath("$.scenes.length()").value(0));
  mvc.perform(get("/api/search/scenes")).andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
 }
 @Test void uploadedSearchIndexRetriesOnlyMissingKeyframes() throws Exception {
  long d=dataset("uploaded-index"); scene(d,"a","A",1,.8);
  String key=java.util.UUID.randomUUID().toString();
  jdbc.sql("UPDATE dataset SET storage_key='uploads',root_relative_path=:k WHERE id=:d").param("k",key).param("d",d).update();
  var file=storage.uploads().resolve("datasets").resolve(key).resolve("samples/a-file-1.jpg");
  java.nio.file.Files.createDirectories(file.getParent());java.nio.file.Files.writeString(file,"AI is stubbed; backend validates the scoped path");
  jdbc.sql("DELETE FROM image_embedding WHERE dataset_id=:d AND sample_data_token='a-file-1'").param("d",d).update();
  image(d,"a",10,.5,false,MODEL,PREPROCESS);
  try {
   mvc.perform(get("/api/datasets/{id}/search-index",d)).andExpect(status().isOk()).andExpect(jsonPath("$.totalImages").value(2)).andExpect(jsonPath("$.indexedImages").value(1));
   indexes.enqueue(d); STATUS.set(503);
   indexes.process(indexes.claim().orElseThrow());
   assertThat(indexes.status(d).status()).isEqualTo("FAILED");
   assertThat(indexes.status(d).indexedImages()).isEqualTo(1);
   STATUS.set(200); RESPONSE.set(aiResponse().replace("clip-text-tokenizer",PREPROCESS));
   indexes.enqueue(d); indexes.process(indexes.claim().orElseThrow());
   assertThat(indexes.status(d).status()).isEqualTo("COMPLETED");
   assertThat(indexes.status(d).indexedImages()).isEqualTo(2);
   assertThat(REQUEST.get()).contains("dataset_key",key,"samples/a-file-1.jpg");
   assertThat(CALLS.get()).isEqualTo(2);
   indexes.enqueue(d); assertThat(indexes.claim()).isEmpty();
   mvc.perform(get("/api/datasets/999999/search-index")).andExpect(status().isNotFound());
  } finally {
   java.nio.file.Files.deleteIfExists(file); java.nio.file.Files.deleteIfExists(file.getParent()); java.nio.file.Files.deleteIfExists(file.getParent().getParent());
  }
 }
 @Test void unavailableAiReturnsServiceUnavailable() throws Exception {
  int unused;
  try(var socket=new java.net.ServerSocket(0)) { unused=socket.getLocalPort(); }
  var client=new com.example.demo.nuscenes.client.TextEmbeddingClient("http://127.0.0.1:"+unused,java.time.Duration.ofMillis(200),java.time.Duration.ofMillis(200));
  assertThatThrownBy(()->client.embed("road")).isInstanceOfSatisfying(org.springframework.web.server.ResponseStatusException.class,e->assertThat(e.getStatusCode().value()).isEqualTo(503));
 }
 @Test void realHttpDtoAndSceneAggregation() throws Exception {
  long d=dataset("ranking");
  scene(d,"a","A",1,.2,.1); scene(d,"b","B",.8,.8,.8); scene(d,"c","C",.7,.7); scene(d,"empty","Empty");
  image(d,"c",10,1,true,"other-model",PREPROCESS);
  image(d,"c",11,1,true,MODEL,"other-preprocess");
  image(d,"b",12,.99,false,MODEL,PREPROCESS);
  mvc.perform(get("/api/search/scenes").param("q"," rainy night road ").param("datasetId",String.valueOf(d)).param("k","1"))
    .andExpect(status().isOk()).andExpect(jsonPath("$.query").value("rainy night road"))
    .andExpect(jsonPath("$.scenes.length()").value(1)).andExpect(jsonPath("$.scenes[0].sceneName").value("B"))
    .andExpect(jsonPath("$.scenes[0].matchedImages").value(3)).andExpect(jsonPath("$.scenes[0].contributingImages").value(3))
    .andExpect(jsonPath("$.scenes[0].score").value(org.hamcrest.Matchers.closeTo(.8,1e-6)))
    .andExpect(jsonPath("$.scenes[0].matchScore").value(100))  // above the calibrated upper anchor
    .andExpect(jsonPath("$.scenes[0].contentUrl").exists());
  assertThat(REQUEST.get()).isEqualTo("POST {\"text\":\"rainy night road\"}");
  mvc.perform(get("/api/search/scenes").param("q","road").param("datasetId",String.valueOf(d)).param("aggregation","MAX"))
    .andExpect(status().isOk()).andExpect(jsonPath("$.scenes.length()").value(3))
    .andExpect(jsonPath("$.scenes[0].sceneName").value("A")).andExpect(jsonPath("$.scenes[0].score").value(1.0))
    .andExpect(jsonPath("$.scenes[0].contributingImages").value(1));
  mvc.perform(get("/api/search/scenes").param("q","road").param("datasetId",String.valueOf(d)).param("aggregation","average"))
    .andExpect(status().isOk()).andExpect(jsonPath("$.scenes[0].sceneName").value("B"));
  mvc.perform(get("/api/search/scenes").param("q","road").param("datasetId",String.valueOf(d)).param("imageTopK","2"))
    .andExpect(status().isOk()).andExpect(jsonPath("$.scenes[0].contributingImages").value(2));
  mvc.perform(get("/api/search/scenes").param("q","road").param("datasetId",String.valueOf(d)).param("keyframesOnly","false"))
    .andExpect(status().isOk()).andExpect(jsonPath("$.scenes[0].matchedImages").value(4));
 }
 @Test void datasetScopeAndIdenticalTokensStaySeparate() throws Exception {
  long first=dataset("one"), second=dataset("two");
  scene(first,"a","First",.6); scene(second,"a","Second",.95);
  mvc.perform(get("/api/search/scenes").param("q","road"))
    .andExpect(status().isOk()).andExpect(jsonPath("$.scenes.length()").value(2)).andExpect(jsonPath("$.scenes[0].sceneName").value("Second"));
  mvc.perform(get("/api/search/scenes").param("q","road").param("datasetId",String.valueOf(first)))
    .andExpect(status().isOk()).andExpect(jsonPath("$.scenes.length()").value(1)).andExpect(jsonPath("$.scenes[0].sceneName").value("First"));
 }
 @Test void invalidInputsNeverCallAi() throws Exception {
  mvc.perform(get("/api/search/scenes").param("q","   ")).andExpect(status().isBadRequest());
  for(String query:new String[]{"q=road&k=0","q=road&k=101","q=road&datasetId=-1","q=road&imageTopK=0","q=road&aggregation=unknown"}) {
   mvc.perform(get("/api/search/scenes?"+query)).andExpect(status().isBadRequest());
  }
  assertThat(CALLS.get()).isZero();
 }
 @Test void invalidUpstreamAndHttpFailureAreRejected() throws Exception {
  for(String body:new String[]{"{}", aiResponse().replace("768","767"), aiResponse().replace(MODEL,"wrong-model"), aiResponse().replace(vector(1),"[1,0]"), aiResponse().replace(vector(1),vector(0).replace("1.0","2.0")), "not json"}) {
   RESPONSE.set(body);
   mvc.perform(get("/api/search/scenes").param("q","road")).andExpect(status().isBadGateway());
  }
  STATUS.set(503); RESPONSE.set("{\"detail\":\"not ready\"}");
  mvc.perform(get("/api/search/scenes").param("q","road")).andExpect(status().isBadGateway());
 }
}
