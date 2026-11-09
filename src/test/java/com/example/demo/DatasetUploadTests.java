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
@org.springframework.transaction.annotation.Transactional
class DatasetUploadTests {
 static final Path ROOT=tempRoot();
 static Path tempRoot() { try { return Files.createTempDirectory("dataset-upload-test-"); } catch(IOException e) { throw new UncheckedIOException(e); } }
 @DynamicPropertySource static void properties(DynamicPropertyRegistry registry) { registry.add("uploads.root",ROOT::toString); }
 @Autowired MockMvc mvc;
 @Autowired JdbcClient jdbc;
 @Autowired ObjectMapper json;
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
 @Test void uploadCatalogMediaAndDownloadOriginal() throws Exception {
  byte[] archive=zip(fixture());
  var response=mvc.perform(multipart("/api/dataset-uploads").file(new MockMultipartFile("file","data.zip","application/zip",archive)))
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
   @Override public long getSize() { return 512L*1024*1024+1; }
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
}
