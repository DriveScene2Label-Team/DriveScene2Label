package com.example.demo;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import static org.assertj.core.api.Assertions.*;
import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Label edits: originals untouched, effective state in the REST views, instance scope, history, revert order and conflicts. */
@SpringBootTest(properties={"auto-label.worker.enabled=false","system-status.check-workers=false","recording.worker.enabled=false",
 "spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://localhost:55432/drivescene_test}",
 "spring.datasource.username=${TEST_DB_USERNAME:drivescene}","spring.datasource.password=${TEST_DB_PASSWORD:}","nuscenes.import.enabled=false"})
@AutoConfigureMockMvc
class LabelEditTests {
 static final ObjectMapper JSON=new ObjectMapper();
 @Autowired MockMvc mvc; @Autowired JdbcClient jdbc;
 long dataset,scene,otherScene,sampleA,sampleB,job,pendingJob,carA,carB,pedA,barrierA,pred0,pred1;

 @BeforeEach void seed() {
  dataset=jdbc.sql("INSERT INTO dataset(name,version,storage_key,root_relative_path,source_checksum) VALUES(:n,'v1.0-mini','local','.','test') RETURNING id")
   .param("n","label-edit-"+UUID.randomUUID()).query(Long.class).single();
  jdbc.sql("INSERT INTO capture_log(dataset_id,token,logfile,location,date_captured,vehicle,raw_payload) VALUES(:d,'log','x','x','x','x','{}')").param("d",dataset).update();
  scene=scene("scene-token","scene-0061"); otherScene=scene("scene-other","scene-0103");
  sampleA=sample("sample-a","scene-token",100); sampleB=sample("sample-b","scene-token",200); sample("sample-o","scene-other",1);
  jdbc.sql("INSERT INTO category(dataset_id,token,name,description,raw_payload) VALUES(:d,'cat-car','vehicle.car','x','{}'),(:d,'cat-ped','human.pedestrian.adult','x','{}'),(:d,'cat-bar','movable_object.debris','x','{}')").param("d",dataset).update();
  jdbc.sql("""
   INSERT INTO object_instance(dataset_id,token,category_token,nbr_annotations,first_annotation_token,last_annotation_token,raw_payload) VALUES
   (:d,'inst-car','cat-car',2,'gt-car-a','gt-car-b','{}'),(:d,'inst-ped','cat-ped',1,'gt-ped-a','gt-ped-a','{}'),(:d,'inst-bar','cat-bar',1,'gt-bar-a','gt-bar-a','{}')""").param("d",dataset).update();
  carA=gt("gt-car-a","sample-a","inst-car"); carB=gt("gt-car-b","sample-b","inst-car"); pedA=gt("gt-ped-a","sample-a","inst-ped"); barrierA=gt("gt-bar-a","sample-a","inst-bar");
  job=job("done","COMPLETED"); pendingJob=job("pending","PENDING");
  for(String t:List.of("sample-a","sample-b")) jdbc.sql("INSERT INTO auto_label_job_sample(job_id,dataset_id,sample_token) VALUES(:j,:d,:t)").param("j",job).param("d",dataset).param("t",t).update();
  pred0=prediction(0,"car"); pred1=prediction(1,"truck");
 }
 @AfterEach void cleanup() {
  for(String table:List.of("label_edit","label_override","auto_label_job","gt_annotation","object_instance","category","sample","scene","capture_log"))
   jdbc.sql("DELETE FROM "+table+" WHERE dataset_id=:d").param("d",dataset).update();
  jdbc.sql("DELETE FROM dataset WHERE id=:d").param("d",dataset).update();
 }
 long scene(String token,String name) {
  return jdbc.sql("INSERT INTO scene(dataset_id,token,log_token,name,description,nbr_samples,first_sample_token,last_sample_token,raw_payload) VALUES(:d,:t,'log',:n,'test',2,'x','x','{}') RETURNING id")
   .param("d",dataset).param("t",token).param("n",name).query(Long.class).single();
 }
 long sample(String token,String scene,long ts) {
  return jdbc.sql("INSERT INTO sample(dataset_id,token,scene_token,timestamp_us,raw_payload) VALUES(:d,:t,:s,:ts,'{}') RETURNING id").param("d",dataset).param("t",token).param("s",scene).param("ts",ts).query(Long.class).single();
 }
 long gt(String token,String sample,String instance) {
  return jdbc.sql("""
   INSERT INTO gt_annotation(dataset_id,token,sample_token,instance_token,center_x,center_y,center_z,size_w,size_l,size_h,rotation_w,rotation_x,rotation_y,rotation_z,num_lidar_pts,num_radar_pts,raw_payload)
   VALUES(:d,:t,:s,:i,1,2,3,2,4,1.5,1,0,0,0,5,0,'{}') RETURNING id""").param("d",dataset).param("t",token).param("s",sample).param("i",instance).query(Long.class).single();
 }
 long job(String key,String status) {
  boolean done=status.equals("COMPLETED");
  return jdbc.sql("""
   INSERT INTO auto_label_job(dataset_id,request_key,target_type,requested_targets,model_version,config_name,model_config,mapping_name,class_names,status,execution_token,result_checksum,started_at,completed_at)
   VALUES(:d,:k,'SCENE',jsonb_build_array('scene-token'),'v','c','{}','8class','["car","truck"]',:st,
    CASE WHEN :done THEN gen_random_uuid() END,CASE WHEN :done THEN 'checksum' END,CASE WHEN :done THEN now() END,CASE WHEN :done THEN now() END) RETURNING id
   """).param("d",dataset).param("k",key).param("st",status).param("done",done).query(Long.class).single();
 }
 long prediction(int index,String name) {
  return jdbc.sql("""
   INSERT INTO predicted_annotation(job_id,dataset_id,sample_token,box_index,detection_name,center_x,center_y,center_z,size_w,size_l,size_h,rotation_w,rotation_x,rotation_y,rotation_z,velocity_x,velocity_y,detection_score,raw_payload)
   VALUES(:j,:d,'sample-a',:i,:n,1,2,3,2,4,1.5,1,0,0,0,0,0,1,'{}') RETURNING id""").param("j",job).param("d",dataset).param("i",index).param("n",name).query(Long.class).single();
 }
 JsonNode rename(String path,long id,String body,int status) throws Exception {
  return JSON.readTree(mvc.perform(patch(path,id).contentType("application/json").content(body)).andExpect(status().is(status)).andReturn().getResponse().getContentAsString());
 }
 JsonNode call(org.springframework.test.web.servlet.RequestBuilder request,int status) throws Exception {
  return JSON.readTree(mvc.perform(request).andExpect(status().is(status)).andReturn().getResponse().getContentAsString());
 }
 String originals() {
  return jdbc.sql("SELECT string_agg(id||':'||instance_token||':'||sample_token,',' ORDER BY id) FROM gt_annotation WHERE dataset_id=:d").param("d",dataset).query(String.class).single()
   +jdbc.sql("SELECT string_agg(id||':'||detection_name,',' ORDER BY id) FROM predicted_annotation WHERE dataset_id=:d").param("d",dataset).query(String.class).single()
   +jdbc.sql("SELECT string_agg(token||':'||category_token,',' ORDER BY token) FROM object_instance WHERE dataset_id=:d").param("d",dataset).query(String.class).single();
 }

 @Test void renameGtInstanceAcrossFramesKeepsOriginalCategory() throws Exception {
  String before=originals();
  var r=rename("/api/annotations/{id}",carA,"{\"label\":\"truck\",\"scope\":\"INSTANCE\"}",200).path("edit");
  assertThat(r.path("action").asText()).isEqualTo("RENAME");
  assertThat(r.path("scope").asText()).isEqualTo("INSTANCE");
  assertThat(r.path("fromLabel").asText()).isEqualTo("car");
  assertThat(r.path("toLabel").asText()).isEqualTo("truck");
  assertThat(r.path("sceneId").asLong()).isEqualTo(scene);
  assertThat(r.path("instanceToken").asText()).isEqualTo("inst-car");
  assertThat(r.path("count").asInt()).isEqualTo(2);
  assertThat(r.path("sampleTokens").toString()).contains("sample-a","sample-b");
  assertThat(r.path("revertible").asBoolean()).isTrue();
  mvc.perform(get("/api/samples/{id}/annotations",sampleB)).andExpect(status().isOk())
   .andExpect(jsonPath("$[0].id").value(carB)).andExpect(jsonPath("$[0].labelOverride").value("truck")).andExpect(jsonPath("$[0].categoryName").value("vehicle.car"));
  mvc.perform(get("/api/samples/{id}/annotations",sampleA)).andExpect(jsonPath("$[?(@.id==%d)].labelOverride".formatted(pedA)).value(contains(nullValue())));
  assertThat(originals()).isEqualTo(before);
 }

 @Test void renameBackToOriginalClearsOverrideAndSameLabelIsRejected() throws Exception {
  rename("/api/annotations/{id}",carA,"{\"label\":\"car\"}",400);
  rename("/api/annotations/{id}",carA,"{\"label\":\"bus\"}",200);
  rename("/api/annotations/{id}",carA,"{\"label\":\"car\"}",200);
  assertThat(jdbc.sql("SELECT count(*) FROM label_override WHERE target_type='ANNOTATION' AND target_id=:id").param("id",carA).query(Long.class).single()).isZero();
  var err=rename("/api/annotations/{id}",carA,"{\"label\":\"airplane\"}",400);
  assertThat(err.path("code").asText()).isEqualTo("INVALID_LABEL");
  assertThat(rename("/api/annotations/{id}",carA,"{\"label\":\"car\",\"scope\":\"WORLD\"}",400).path("code").asText()).isEqualTo("INVALID_SCOPE");
  rename("/api/annotations/{id}",999_999_999L,"{\"label\":\"car\"}",404);
 }

 @Test void unmappedCategoryUsesCategoryNameAsOriginalClass() throws Exception {
  var r=rename("/api/annotations/{id}",barrierA,"{\"label\":\"car\"}",200).path("edit");
  assertThat(r.path("fromLabel").asText()).isEqualTo("movable_object.debris");
 }

 @Test void barrierAndTrafficConeAreRenameTargets() throws Exception {
  assertThat(rename("/api/annotations/{id}",carA,"{\"label\":\"traffic_cone\"}",200).path("edit").path("toLabel").asText()).isEqualTo("traffic_cone");
 }

 @Test void deleteSampleScopeHidesOnlyThatFrameAndSceneAnnotations() throws Exception {
  var r=call(delete("/api/annotations/{id}",carA).param("scope","SAMPLE"),200).path("edit");
  assertThat(r.path("count").asInt()).isEqualTo(1);
  mvc.perform(get("/api/samples/{id}/annotations",sampleA)).andExpect(jsonPath("$[*].id",not(hasItem((int)carA))));
  mvc.perform(get("/api/samples/{id}/annotations",sampleA).param("includeDeleted","true")).andExpect(jsonPath("$[?(@.id==%d)].deleted".formatted(carA)).value(contains(true)));
  mvc.perform(get("/api/samples/{id}/annotations",sampleB)).andExpect(jsonPath("$[*].id",hasItem((int)carB)));
  mvc.perform(get("/api/scenes/{id}/annotations",scene)).andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(3)).andExpect(jsonPath("$[*].id",not(hasItem((int)carA))));
  assertThat(call(delete("/api/annotations/{id}",carA),409).path("code").asText()).isEqualTo("TARGET_DELETED");
  assertThat(rename("/api/annotations/{id}",carA,"{\"label\":\"bus\"}",409).path("code").asText()).isEqualTo("TARGET_DELETED");
  // Instance scope skips the already deleted frame.
  assertThat(call(delete("/api/annotations/{id}",carB).param("scope","INSTANCE"),200).path("edit").path("count").asInt()).isEqualTo(1);
 }

 @Test void predictionEditsAreFilteredFromResultsAndScopedToJob() throws Exception {
  String before=originals();
  var r=rename("/api/auto-label/predictions/{id}",pred0,"{\"label\":\"bus\"}",200).path("edit");
  assertThat(r.path("jobId").asLong()).isEqualTo(job);
  assertThat(r.path("targetType").asText()).isEqualTo("PREDICTION");
  assertThat(r.path("fromLabel").asText()).isEqualTo("car");
  rename("/api/auto-label/predictions/{id}",pred0,"{\"label\":\"bus\"}",400);
  rename("/api/auto-label/predictions/{id}",pred0,"{\"label\":\"car\",\"scope\":\"INSTANCE\"}",400);
  call(delete("/api/auto-label/predictions/{id}",pred1),200);
  mvc.perform(get("/api/auto-label/jobs/{id}/results",job)).andExpect(status().isOk()).andExpect(jsonPath("$.boxes.length()").value(1))
   .andExpect(jsonPath("$.boxes[0].id").value(pred0)).andExpect(jsonPath("$.boxes[0].detectionName").value("car")).andExpect(jsonPath("$.boxes[0].labelOverride").value("bus"));
  mvc.perform(get("/api/auto-label/jobs/{id}/results",job).param("includeDeleted","true")).andExpect(jsonPath("$.boxes.length()").value(2))
   .andExpect(jsonPath("$.boxes[1].deleted").value(true));
  // History: GT edits of the scene always, prediction edits only with their jobId.
  rename("/api/annotations/{id}",pedA,"{\"label\":\"bicycle\"}",200);
  mvc.perform(get("/api/scenes/{id}/label-edits",scene)).andExpect(jsonPath("$.length()").value(1)).andExpect(jsonPath("$[0].targetType").value("ANNOTATION"));
  mvc.perform(get("/api/scenes/{id}/label-edits",scene).param("jobId",String.valueOf(job))).andExpect(jsonPath("$.length()").value(3))
   .andExpect(jsonPath("$[0].action").value("RENAME")).andExpect(jsonPath("$[1].action").value("DELETE"));
  mvc.perform(get("/api/scenes/{id}/label-edits",otherScene)).andExpect(jsonPath("$.length()").value(0));
  mvc.perform(get("/api/scenes/{id}/label-edits",999_999_999L)).andExpect(status().isNotFound());
  assertThat(originals()).isEqualTo(before);
 }

 @Test void predictionsOfUnfinishedJobsCannotBeEdited() throws Exception {
  jdbc.sql("INSERT INTO auto_label_job_sample(job_id,dataset_id,sample_token) VALUES(:j,:d,'sample-a')").param("j",pendingJob).param("d",dataset).update();
  long p=jdbc.sql("""
   INSERT INTO predicted_annotation(job_id,dataset_id,sample_token,box_index,detection_name,center_x,center_y,center_z,size_w,size_l,size_h,rotation_w,rotation_x,rotation_y,rotation_z,velocity_x,velocity_y,detection_score,raw_payload)
   VALUES(:j,:d,'sample-a',0,'car',1,2,3,2,4,1.5,1,0,0,0,0,0,1,'{}') RETURNING id""").param("j",pendingJob).param("d",dataset).query(Long.class).single();
  assertThat(rename("/api/auto-label/predictions/{id}",p,"{\"label\":\"bus\"}",409).path("code").asText()).isEqualTo("JOB_NOT_COMPLETED");
 }

 @Test void revertRestoresPreviousStateNewestFirst() throws Exception {
  long first=rename("/api/annotations/{id}",carA,"{\"label\":\"truck\",\"scope\":\"INSTANCE\"}",200).path("edit").path("id").asLong();
  long second=rename("/api/annotations/{id}",carB,"{\"label\":\"bus\"}",200).path("edit").path("id").asLong();
  mvc.perform(get("/api/scenes/{id}/label-edits",scene)).andExpect(jsonPath("$[0].id").value(second)).andExpect(jsonPath("$[0].revertible").value(true))
   .andExpect(jsonPath("$[1].id").value(first)).andExpect(jsonPath("$[1].revertible").value(false));
  assertThat(call(post("/api/label-edits/{id}/revert",first),409).path("code").asText()).isEqualTo("LATER_EDIT_EXISTS");
  var undone=call(post("/api/label-edits/{id}/revert",second),200).path("edit");
  assertThat(undone.path("revertedAt").isNull()).isFalse();
  assertThat(undone.path("revertible").asBoolean()).isFalse();
  mvc.perform(get("/api/samples/{id}/annotations",sampleB)).andExpect(jsonPath("$[0].labelOverride").value("truck"));
  assertThat(call(post("/api/label-edits/{id}/revert",second),409).path("code").asText()).isEqualTo("ALREADY_REVERTED");
  call(post("/api/label-edits/{id}/revert",first),200);
  assertThat(jdbc.sql("SELECT count(*) FROM label_override WHERE dataset_id=:d").param("d",dataset).query(Long.class).single()).isZero();
  call(post("/api/label-edits/{id}/revert",999_999_999L),404);
 }

 @Test void revertDeleteBringsTheBoxBack() throws Exception {
  rename("/api/annotations/{id}",carA,"{\"label\":\"bus\"}",200);
  long del=call(delete("/api/annotations/{id}",carA),200).path("edit").path("id").asLong();
  call(post("/api/label-edits/{id}/revert",del),200);
  mvc.perform(get("/api/samples/{id}/annotations",sampleA)).andExpect(jsonPath("$[?(@.id==%d)].labelOverride".formatted(carA)).value(contains("bus")))
   .andExpect(jsonPath("$[?(@.id==%d)].deleted".formatted(carA)).value(contains(false)));
 }
}
