package com.example.demo.nuscenes.service;

import com.example.demo.nuscenes.importer.NuscenesImporter;
import com.example.demo.nuscenes.storage.DatasetFiles;
import com.example.demo.nuscenes.storage.DatasetStorage;
import com.example.demo.nuscenes.storage.DatasetArchive;
import com.example.demo.nuscenes.storage.UploadArchiveStore;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DatasetUploadService {
 private final DatasetStorage storage;
 private final NuscenesImporter importer;
 private final long maxExpanded;
 private final UploadArchiveStore archives;
 private final org.springframework.jdbc.core.simple.JdbcClient jdbc;
 public DatasetUploadService(DatasetStorage storage,NuscenesImporter importer,UploadArchiveStore archives,org.springframework.jdbc.core.simple.JdbcClient jdbc,@Value("${uploads.max-expanded-bytes:8589934592}") long maxExpanded) {
  this.storage=storage;this.importer=importer;this.maxExpanded=maxExpanded;this.archives=archives;this.jdbc=jdbc;
 }
 public record Uploaded(long datasetId,String version,int sceneCount) {}
 public Uploaded upload(MultipartFile file) throws IOException {
  return upload(file,UUID.randomUUID().toString());
 }
 public Uploaded upload(MultipartFile file,String key) throws IOException {
  if(!UUID.fromString(key).toString().equals(key)) throw bad("Invalid upload identifier");
  // A worker retry after import committed must return the same dataset.
  var existing=jdbc.sql("SELECT d.id AS dataset_id,d.version,(SELECT count(*)::integer FROM scene s WHERE s.dataset_id=d.id) AS scene_count FROM dataset d WHERE storage_key='uploads' AND root_relative_path=:k").param("k",key).query(Uploaded.class).optional();
  if(existing.isPresent()) return existing.get();
  if(file.isEmpty() || !DatasetArchive.supported(file.getOriginalFilename())) throw bad("비어 있지 않은 nuScenes ZIP, TGZ 또는 TAR.GZ 파일을 선택해 주세요.");
  if(file.getSize()>UploadArchiveStore.MAX_ARCHIVE_BYTES) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,"nuScenes 압축 파일은 5GB 이하만 지원합니다.");
  Path root=storage.uploads().resolve("datasets").resolve(key), archive=storage.uploads().resolve("archives").resolve(key+".part");
  // Only this upload's UUID paths can be remnants of an interrupted import.
  if(Files.exists(root)) try(var paths=Files.walk(root)) { for(Path path:paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path); }
  Files.deleteIfExists(archive);
  for(var type:DatasetArchive.Format.values()) Files.deleteIfExists(archive.resolveSibling(key+type.extension));
  Files.createDirectories(root); Files.createDirectories(archive.getParent());
  boolean remoteStored=false;DatasetArchive.Format format=null;String stage="COPYING";
  var logger=org.slf4j.LoggerFactory.getLogger(getClass());
  long started=System.nanoTime(),stageStarted=started;
  try {
   logger.info("Dataset upload id={} stage={} event=started bytes={}",key,stage,file.getSize());
   try(var input=file.getInputStream()) { Files.copy(input,archive); }
   format=DatasetArchive.detect(archive);
   archive=Files.move(archive,archive.resolveSibling(key+format.extension));
   logger.info("Dataset upload id={} stage={} event=completed wall_ms={}",key,stage,(System.nanoTime()-stageStarted)/1_000_000);stageStarted=System.nanoTime();
   stage="EXTRACTING";logger.info("Dataset upload id={} stage={} bytes={} format={}",key,stage,file.getSize(),format);
   extract(archive,root,maxExpanded);
   var versions=new ArrayList<String>();
   for(String version:List.of("v1.0-mini","v1.0-trainval")) if(Files.isDirectory(root.resolve(version))) versions.add(version);
   if(versions.size()!=1) throw bad("압축 파일 최상위에 v1.0-mini 또는 v1.0-trainval 폴더와 samples/sweeps 파일을 넣어 주세요.");
   logger.info("Dataset upload id={} stage={} event=completed wall_ms={}",key,stage,(System.nanoTime()-stageStarted)/1_000_000);stageStarted=System.nanoTime();
   stage="STORING_ORIGINAL";logger.info("Dataset upload id={} stage={}",key,stage);
   archives.put(key,archive); remoteStored=archives.enabled();
   logger.info("Dataset upload id={} stage={} event=completed wall_ms={} remote={}",key,stage,(System.nanoTime()-stageStarted)/1_000_000,remoteStored);stageStarted=System.nanoTime();
   stage="IMPORTING_METADATA";logger.info("Dataset upload id={} stage={}",key,stage);
   var imported=importer.importUploaded(new DatasetFiles(root.toString()),key,versions.getFirst());
   logger.info("Dataset upload id={} stage={} event=completed wall_ms={}",key,stage,(System.nanoTime()-stageStarted)/1_000_000);
   logger.info("Dataset upload id={} stage=COMPLETED datasetId={} scenes={}",key,imported.datasetId(),imported.sourceCounts().getOrDefault("scene",0));
   logger.info("Dataset upload id={} stage=TOTAL event=completed wall_ms={}",key,(System.nanoTime()-started)/1_000_000);
   return new Uploaded(imported.datasetId(),versions.getFirst(),imported.sourceCounts().getOrDefault("scene",0));
  } catch(Exception error) {
   logger.error("Dataset upload failed id={} stage={} bytes={} format={} stage_wall_ms={} total_wall_ms={}",key,stage,file.getSize(),format,(System.nanoTime()-stageStarted)/1_000_000,(System.nanoTime()-started)/1_000_000,error);
   if(remoteStored) try { archives.remove(key,format); } catch(RuntimeException cleanup) { error.addSuppressed(cleanup); }
   try {
    // Only the UUID directory allocated by this request can be removed.
    try(var paths=Files.walk(root)) { for(Path path:paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path); }
    Files.deleteIfExists(archive);
   } catch(IOException cleanup) { error.addSuppressed(cleanup); }
   if(error instanceof ResponseStatusException response) throw response;
   if(error instanceof IOException || error instanceof IllegalArgumentException || error instanceof tools.jackson.core.JacksonException || error instanceof org.springframework.dao.DataIntegrityViolationException)
    throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"nuScenes 압축 파일의 메타데이터·센서 파일을 확인해 주세요. 파일이 누락되었거나 관계가 잘못되었습니다. 작업 ID: "+key,error);
   if(error instanceof RuntimeException runtime) throw runtime;
   throw new IOException(error);
  }
 }
 public static void extract(Path archive,Path root,long maxExpanded) throws IOException {
  DatasetArchive.extract(archive,root,maxExpanded);
 }
 private static ResponseStatusException bad(String message) { return new ResponseStatusException(HttpStatus.BAD_REQUEST,message); }
}
