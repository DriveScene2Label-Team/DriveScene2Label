package com.example.demo;

import java.nio.charset.StandardCharsets;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"auto-label.worker.enabled=false","recording.worker.enabled=false","nuscenes.import.enabled=false",
 "spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://localhost:55432/drivescene_test}",
 "spring.datasource.username=${TEST_DB_USERNAME:drivescene}","spring.datasource.password=${TEST_DB_PASSWORD:}"})
@AutoConfigureMockMvc
class LabelTests {
 static final String ORIGINAL="""
  {"meta":{"use_camera":true},"coordinate_frame":"WORLD","results":{"frame-1":[{"sample_token":"frame-1","translation":[1,2,3],"size":[2,4,1.5],"rotation":[1,0,0,0],"velocity":[0,0],"detection_name":"car","detection_score":1,"attribute_name":""}],"frame-empty":[]}}
  """;
 @Autowired MockMvc mvc;
 @Autowired ObjectMapper json;
 @Autowired JdbcClient jdbc;
 final List<Long> created=new ArrayList<>();
 @AfterEach void cleanup() { for(long id:created) jdbc.sql("DELETE FROM label_document WHERE id=:id").param("id",id).update(); }
 JsonNode upload(byte[] bytes) throws Exception {
  var response=mvc.perform(multipart("/api/label-documents/upload").file(new MockMultipartFile("file","labels.json","application/json",bytes)))
   .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
  var result=json.readTree(response); created.add(result.path("document").path("id").asLong()); return result;
 }
 JsonNode upload() throws Exception { return upload(ORIGINAL.getBytes(StandardCharsets.UTF_8)); }
 @Test void uploadEditSaveReloadDownloadAndReimportPreserveOriginal() throws Exception {
  var first=upload(); long id=first.path("document").path("id").asLong();
  var data=(ObjectNode)first.path("data").deepCopy();
  var box=(ObjectNode)data.path("results").path("frame-1").get(0); box.put("detection_name","truck");
  box.putArray("translation").add(9).add(2).add(3);
  String body=json.writeValueAsString(Map.of("expectedVersion",0,"data",data,"note","class and position"));
  mvc.perform(post("/api/label-documents/{id}/revisions",id).contentType("application/json").content(body))
   .andExpect(status().isCreated()).andExpect(jsonPath("$.revision").value(1)).andExpect(jsonPath("$.document.version").value(1));
  mvc.perform(get("/api/label-documents/{id}",id)).andExpect(jsonPath("$.data.results.frame-1[0].detection_name").value("truck"));
  mvc.perform(get("/api/label-documents/{id}",id).param("revision","0")).andExpect(jsonPath("$.data.results.frame-1[0].detection_name").value("car"));
  mvc.perform(get("/api/label-documents/{id}/original",id)).andExpect(content().bytes(ORIGINAL.getBytes(StandardCharsets.UTF_8)));
  var download=mvc.perform(get("/api/label-documents/{id}/download",id).param("revision","1"))
   .andExpect(header().string("Content-Disposition","attachment; filename=\"labels-"+id+"-v1.json\""))
   .andExpect(jsonPath("$.meta.use_camera").value(true)).andExpect(jsonPath("$.results.frame-empty").isEmpty())
   .andReturn().getResponse().getContentAsByteArray();
  assertThat(upload(download).path("data")).isEqualTo(json.readTree(download));
  mvc.perform(get("/api/label-documents/{id}/revisions",id)).andExpect(jsonPath("$[0].number").value(1)).andExpect(jsonPath("$[1].number").value(0));
 }
 @Test void staleSaveDoesNotOverwriteAnotherRevision() throws Exception {
  var first=upload(); long id=first.path("document").path("id").asLong();
  String body=json.writeValueAsString(Map.of("expectedVersion",0,"data",first.path("data")));
  mvc.perform(post("/api/label-documents/{id}/revisions",id).contentType("application/json").content(body)).andExpect(status().isCreated());
  mvc.perform(post("/api/label-documents/{id}/revisions",id).contentType("application/json").content(body)).andExpect(status().isConflict());
  mvc.perform(get("/api/label-documents/{id}/revisions",id)).andExpect(jsonPath("$.length()").value(2));
 }
 @Test void invalidGeometryAndLostFrameAreRejectedWithoutSaving() throws Exception {
  var first=upload(); long id=first.path("document").path("id").asLong();
  var data=(ObjectNode)first.path("data").deepCopy();
  ((ObjectNode)data.path("results").path("frame-1").get(0)).putArray("size").add(-1).add(2).add(3);
  mvc.perform(post("/api/label-documents/{id}/revisions",id).contentType("application/json")
   .content(json.writeValueAsString(Map.of("expectedVersion",0,"data",data)))).andExpect(status().isBadRequest());
  data=(ObjectNode)first.path("data").deepCopy(); ((ObjectNode)data.path("results")).remove("frame-empty");
  mvc.perform(post("/api/label-documents/{id}/revisions",id).contentType("application/json")
   .content(json.writeValueAsString(Map.of("expectedVersion",0,"data",data)))).andExpect(status().isBadRequest());
  mvc.perform(get("/api/label-documents/{id}",id)).andExpect(jsonPath("$.document.headRevision").value(0));
 }
 @Test void lastBoxCanBeDeletedWhileKeepingTheFrame() throws Exception {
  var first=upload(); long id=first.path("document").path("id").asLong();
  var data=(ObjectNode)first.path("data").deepCopy(); ((ObjectNode)data.path("results")).putArray("frame-1");
  mvc.perform(post("/api/label-documents/{id}/revisions",id).contentType("application/json")
   .content(json.writeValueAsString(Map.of("expectedVersion",0,"data",data))))
   .andExpect(status().isCreated()).andExpect(jsonPath("$.data.results.frame-1").isEmpty());
 }
 @Test void malformedAndOtherCoordinateFramesAreRejected() throws Exception {
  for(String input:List.of("invalid",ORIGINAL.replace("WORLD","CAMERA")))
   mvc.perform(multipart("/api/label-documents/upload").file(new MockMultipartFile("file","bad.json","application/json",input.getBytes(StandardCharsets.UTF_8)))).andExpect(status().isBadRequest());
 }
}
