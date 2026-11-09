package com.example.demo.nuscenes.service;

import com.example.demo.nuscenes.importer.NuscenesImporter;
import com.example.demo.nuscenes.storage.DatasetFiles;
import com.example.demo.nuscenes.storage.DatasetStorage;
import com.example.demo.nuscenes.storage.UploadArchiveStore;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.ZipInputStream;
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
 public DatasetUploadService(DatasetStorage storage,NuscenesImporter importer,UploadArchiveStore archives,@Value("${uploads.max-expanded-bytes:8589934592}") long maxExpanded) {
  this.storage=storage;this.importer=importer;this.maxExpanded=maxExpanded;this.archives=archives;
 }
 public record Uploaded(long datasetId,String version,int sceneCount) {}
 public Uploaded upload(MultipartFile file) throws IOException {
  if(file.isEmpty()) throw bad("비어 있지 않은 nuScenes ZIP 파일을 선택해 주세요.");
  if(file.getSize()>UploadArchiveStore.MAX_ARCHIVE_BYTES) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,"nuScenes ZIP은 5GB 이하만 지원합니다.");
  String key=UUID.randomUUID().toString();
  Path root=storage.uploads().resolve("datasets").resolve(key), archive=storage.uploads().resolve("archives").resolve(key+".zip");
  Files.createDirectories(root); Files.createDirectories(archive.getParent());
  boolean remoteStored=false;
  try {
   try(var input=file.getInputStream()) { Files.copy(input,archive); }
   extract(archive,root,maxExpanded);
   var versions=new ArrayList<String>();
   for(String version:List.of("v1.0-mini","v1.0-trainval")) if(Files.isDirectory(root.resolve(version))) versions.add(version);
   if(versions.size()!=1) throw bad("ZIP 최상위에 v1.0-mini 또는 v1.0-trainval 폴더와 samples/sweeps 파일을 넣어 주세요.");
   archives.put(key,archive); remoteStored=archives.enabled();
   var imported=importer.importUploaded(new DatasetFiles(root.toString()),key,versions.getFirst());
   return new Uploaded(imported.datasetId(),versions.getFirst(),imported.sourceCounts().getOrDefault("scene",0));
  } catch(Exception error) {
   if(remoteStored) try { archives.remove(key); } catch(RuntimeException cleanup) { error.addSuppressed(cleanup); }
   try {
    // Only the UUID directory allocated by this request can be removed.
    try(var paths=Files.walk(root)) { for(Path path:paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path); }
    Files.deleteIfExists(archive);
   } catch(IOException cleanup) { error.addSuppressed(cleanup); }
   if(error instanceof ResponseStatusException response) throw response;
   if(error instanceof IOException || error instanceof IllegalArgumentException || error instanceof tools.jackson.core.JacksonException || error instanceof org.springframework.dao.DataIntegrityViolationException)
    throw bad("nuScenes ZIP의 메타데이터·파일 경로·관계를 확인해 주세요. 파일이 누락되었거나 형식이 잘못되었습니다.");
   if(error instanceof RuntimeException runtime) throw runtime;
   throw new IOException(error);
  }
 }
 public static void extract(Path archive,Path root,long maxExpanded) throws IOException {
  long expanded=0;int entries=0; byte[] buffer=new byte[65536];
  try(var zip=new ZipInputStream(Files.newInputStream(archive))) {
   for(var entry=zip.getNextEntry();entry!=null;entry=zip.getNextEntry()) {
    String name=entry.getName();
    if(++entries>100000 || name.isBlank() || name.startsWith("/") || name.contains("\\") || name.contains(":") || Arrays.asList(name.split("/")).contains("..")) throw bad("ZIP 파일 경로 또는 항목 수가 올바르지 않습니다.");
    Path target=root.resolve(name).normalize();
    if(!target.startsWith(root) || target.equals(root)) throw bad("ZIP에 허용되지 않는 경로가 있습니다.");
    if(entry.isDirectory()) { Files.createDirectories(target);continue; }
    Files.createDirectories(target.getParent());
    try(var output=Files.newOutputStream(target,StandardOpenOption.CREATE_NEW)) {
     int count;while((count=zip.read(buffer))!=-1) {
      expanded+=count;if(expanded>maxExpanded) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,"ZIP 압축 해제 용량 제한을 초과했습니다.");
      output.write(buffer,0,count);
     }
    }
   }
  }
  if(entries==0) throw bad("유효한 ZIP 파일이 아닙니다.");
 }
 private static ResponseStatusException bad(String message) { return new ResponseStatusException(HttpStatus.BAD_REQUEST,message); }
}
