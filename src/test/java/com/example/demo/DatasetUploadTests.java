package com.example.demo;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.*;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.ObjectMapper;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"auto-label.worker.enabled=false","recording.worker.enabled=false","nuscenes.import.enabled=false","uploads.max-expanded-bytes=1048576",
 "spring.datasource.url=${TEST_DB_URL:jdbc:postgresql://localhost:55432/drivescene_test}",
 "spring.datasource.username=${TEST_DB_USERNAME:drivescene}","spring.datasource.password=${TEST_DB_PASSWORD:}"})
@AutoConfigureMockMvc
@org.junit.jupiter.api.extension.ExtendWith(org.springframework.boot.test.system.OutputCaptureExtension.class)
@org.springframework.transaction.annotation.Transactional
class DatasetUploadTests {
 static final Path ROOT=tempRoot();
 static Path tempRoot() { try { return Files.createTempDirectory("dataset-upload-test-"); } catch(IOException e) { throw new UncheckedIOException(e); } }
 @DynamicPropertySource static void properties(DynamicPropertyRegistry registry) { registry.add("uploads.root",ROOT::toString); }
 @Autowired MockMvc mvc;
 @Autowired JdbcClient jdbc;
 @Autowired ObjectMapper json;
 @Autowired com.example.demo.nuscenes.service.ChunkedDatasetUploadService chunks;
 @Autowired com.example.demo.nuscenes.service.DatasetUploadService uploads;
 @AfterAll static void files() throws IOException { try(var paths=Files.walk(ROOT)) { for(Path path:paths.sorted(Comparator.reverseOrder()).toList()) Files.delete(path); } }
 byte[] zip(Map<String,byte[]> entries) throws IOException {
  var bytes=new ByteArrayOutputStream();
  try(var zip=new ZipOutputStream(bytes)) { for(var entry:entries.entrySet()) { zip.putNextEntry(new ZipEntry(entry.getKey()));zip.write(entry.getValue());zip.closeEntry(); } }
  return bytes.toByteArray();
 }
 Map<String,byte[]> fixture() throws Exception {
  var entries=new LinkedHashMap<String,byte[]>();
  Path metadata=Path.of(getClass().getResource("/nuscenes/v1.0-mini").toURI());
  try(var paths=Files.list(metadata)) { for(Path path:paths.toList()) entries.put("v1.0-mini/"+path.getFileName(),Files.readAllBytes(path)); }
  for(String table:List.of("sample_data","map")) for(var row:json.readTree(entries.get("v1.0-mini/"+table+".json"))) entries.put(row.path("filename").asText(),"synthetic-media".getBytes());
  return entries;
 }
 byte[] tgz(Map<String,byte[]> entries) throws IOException {
  var bytes=new ByteArrayOutputStream();
  try(var gzip=new GZIPOutputStream(bytes);var tar=new org.apache.commons.compress.archivers.tar.TarArchiveOutputStream(gzip)) {
   for(var item:entries.entrySet()) {
    var entry=new org.apache.commons.compress.archivers.tar.TarArchiveEntry("./"+item.getKey());entry.setSize(item.getValue().length);
    tar.putArchiveEntry(entry);tar.write(item.getValue());tar.closeArchiveEntry();
   }
  }
  return bytes.toByteArray();
 }
 @Test void tgzUploadAndChunkRetryPreserveOriginalFormat() throws Exception {
  byte[] archive=tgz(fixture());
  for(String filename:List.of("mini.tgz","mini.tar.gz")) {
   var session=chunks.create(filename,archive.length);
   chunks.part(session.id(),0,new ByteArrayInputStream(archive));chunks.complete(session.id());
   chunks.process(chunks.claim().orElseThrow());
   var done=chunks.status(session.id());assertThat(done.status()).isEqualTo("COMPLETED");assertThat(done.sceneCount()).isEqualTo(1);
   mvc.perform(get("/api/dataset-uploads/{id}/original",done.datasetId())).andExpect(status().isOk())
    .andExpect(header().string("Content-Disposition","attachment; filename=\"dataset-"+done.datasetId()+".tar.gz\""))
    .andExpect(content().bytes(archive));
  }
 }
 @Test void uploadCatalogMediaAndDownloadOriginal() throws Exception {
  byte[] archive=zip(fixture());
  var large=new MockMultipartFile("file","data.zip","application/zip",archive) {
   @Override public long getSize() { return 600L*1024*1024; }
  };
  var response=mvc.perform(multipart("/api/dataset-uploads").file(large))
   .andExpect(status().isCreated()).andExpect(jsonPath("$.sceneCount").value(1)).andReturn().getResponse().getContentAsString();
  long id=json.readTree(response).path("datasetId").asLong();
  mvc.perform(get("/api/datasets/{id}/scenes",id)).andExpect(status().isOk());
  long file=jdbc.sql("SELECT min(id) FROM sample_data WHERE dataset_id=:id").param("id",id).query(Long.class).single();
  mvc.perform(get("/api/sensor-files/{id}/content",file)).andExpect(status().isOk()).andExpect(content().string("synthetic-media"));
  mvc.perform(get("/api/dataset-uploads/{id}/original",id)).andExpect(status().isOk()).andExpect(content().bytes(archive));
 }
 @Test void traversalMissingFilesAndExpandedLimitLeaveNoDataset() throws Exception {
  long before=jdbc.sql("SELECT count(*) FROM dataset").query(Long.class).single();
  var oversized=new MockMultipartFile("file","large.zip","application/zip",new byte[]{1}) {
   @Override public long getSize() { return 5_000_000_001L; }
  };
  mvc.perform(multipart("/api/dataset-uploads").file(oversized)).andExpect(status().isPayloadTooLarge());
  Files.createDirectories(ROOT.resolve("datasets"));
  long directories;try(var paths=Files.list(ROOT.resolve("datasets"))) { directories=paths.count(); }
  mvc.perform(multipart("/api/dataset-uploads").file(new MockMultipartFile("file","bad.zip","application/zip",zip(Map.of("../escaped",new byte[]{1})))))
   .andExpect(status().isBadRequest());
  assertThat(Files.exists(ROOT.resolve("datasets/escaped"))).isFalse();
  var incomplete=fixture(); incomplete.keySet().removeIf(key->key.startsWith("samples/"));
  mvc.perform(multipart("/api/dataset-uploads").file(new MockMultipartFile("file","missing.zip","application/zip",zip(incomplete))))
   .andExpect(status().isBadRequest());
  mvc.perform(multipart("/api/dataset-uploads").file(new MockMultipartFile("file","large.zip","application/zip",zip(Map.of("large.bin",new byte[1048577])))))
   .andExpect(status().isPayloadTooLarge());
  assertThat(jdbc.sql("SELECT count(*) FROM dataset").query(Long.class).single()).isEqualTo(before);
  try(var paths=Files.list(ROOT.resolve("datasets"))) { assertThat(paths.count()).isEqualTo(directories); }
 }
 @Test void chunkedUploadRetriesAndCompletesWithoutDuplicatingDataset(org.springframework.boot.test.system.CapturedOutput output) throws Exception {
  byte[] archive=zip(fixture());
  String created=mvc.perform(post("/api/dataset-uploads/sessions").contentType("application/json").content(json.writeValueAsString(Map.of("filename","mini.zip","sizeBytes",archive.length))))
   .andExpect(status().isCreated()).andExpect(header().exists("X-Request-ID")).andReturn().getResponse().getContentAsString();
  UUID id=UUID.fromString(json.readTree(created).path("id").asString());String path="/api/dataset-uploads/sessions/"+id;
  mvc.perform(post(path+"/complete")).andExpect(status().isConflict());
  for(int retry=0;retry<2;retry++) mvc.perform(post(path+"/parts").param("offset","0").contentType("application/octet-stream").content(archive)).andExpect(status().isOk()).andExpect(jsonPath("$.receivedBytes").value(archive.length));
  var changed=archive.clone();changed[0]^=1;
  mvc.perform(post(path+"/parts").param("offset","0").contentType("application/octet-stream").content(changed)).andExpect(status().isConflict());
  for(int retry=0;retry<2;retry++) mvc.perform(post(path+"/complete")).andExpect(status().isAccepted()).andExpect(jsonPath("$.status").value("QUEUED"));
  chunks.process(chunks.claim().orElseThrow());
  var done=chunks.status(id);assertThat(done.status()).isEqualTo("COMPLETED");assertThat(done.sceneCount()).isEqualTo(1);
  mvc.perform(get("/api/dataset-uploads/{id}/original",done.datasetId())).andExpect(content().bytes(archive));
  var replay=uploads.upload(new MockMultipartFile("file","mini.zip","application/zip",archive),id.toString());
  assertThat(replay.datasetId()).isEqualTo(done.datasetId());
  assertThat(chunks.claim()).isEmpty();
  mvc.perform(post(path+"/metrics").contentType("application/json").content("{\"transferMs\":120,\"processingMs\":80,\"totalMs\":200,\"sentBytes\":"+archive.length+",\"resumedBytes\":0,\"outcome\":\"completed\"}"))
   .andExpect(status().isNoContent());
  assertThat(output.getAll()).contains("[HTTP] request=", "db_lock_ms=", "file_ms=", "db_update_ms=", "transaction_ms=", "[UPLOAD_CLIENT] upload="+id,
   "Dataset upload id="+id+" stage=STORING_ORIGINAL event=completed", "Dataset upload id="+id+" stage=IMPORTING_METADATA event=completed");
  mvc.perform(post(path+"/metrics").contentType("application/json").content("{\"transferMs\":-1,\"outcome\":\"completed\"}"))
   .andExpect(status().isBadRequest());
 }
 @Test void chunkSizeOrderAndResumeOffsetAreEnforced() throws Exception {
  int size=com.example.demo.nuscenes.service.ChunkedDatasetUploadService.CHUNK_BYTES;
  var session=chunks.create("large.zip",size+3L);
  assertThatThrownBy(()->chunks.part(session.id(),size,new ByteArrayInputStream(new byte[3]))).isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
  chunks.part(session.id(),0,new ByteArrayInputStream(new byte[size]));
  assertThat(chunks.status(session.id()).receivedBytes()).isEqualTo(size);
  assertThatThrownBy(()->chunks.part(session.id(),size,new ByteArrayInputStream(new byte[4]))).isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
  chunks.part(session.id(),size,new ByteArrayInputStream(new byte[3]));
  assertThat(chunks.status(session.id()).receivedBytes()).isEqualTo(size+3L);
 }
}
