package com.example.demo.nuscenes.storage;

import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Files;
import java.util.Comparator;
import java.util.UUID;
import com.example.demo.nuscenes.service.DatasetUploadService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DatasetStorage {
 private final DatasetFiles original;
 private final Path uploads;
 private final UploadArchiveStore archives;
 private final long maxExpanded;
 public DatasetStorage(DatasetFiles original,@Value("${uploads.root}") String uploads,UploadArchiveStore archives,
   @Value("${uploads.max-expanded-bytes:8589934592}") long maxExpanded) {
  this.original=original; this.uploads=Path.of(uploads).toAbsolutePath().normalize();
  this.archives=archives;this.maxExpanded=maxExpanded;
 }
 public Path uploads() { return uploads; }
 public DatasetFiles files(String storage,String root) throws IOException {
  if("nuscenes".equals(storage) && ".".equals(root)) return original;
  if("uploads".equals(storage)) {
   validateKey(root);
   Path directory=uploads.resolve("datasets").resolve(root);
   if(!Files.isDirectory(directory)) restore(root,directory);
   return new DatasetFiles(directory.toString());
  }
  throw new IOException("Unsupported dataset storage");
 }
 public synchronized Path archive(String key) throws IOException {
  validateKey(key);
  Path target=uploads.resolve("archives").resolve(key+".zip");
  if(Files.isRegularFile(target)) return target;
  Files.createDirectories(target.getParent());
  Path partial=target.resolveSibling(key+"."+UUID.randomUUID()+".part");
  try { archives.fetch(key,partial); Files.move(partial,target); }
  finally { Files.deleteIfExists(partial); }
  return target;
 }
 private synchronized void restore(String key,Path target) throws IOException {
  if(Files.isDirectory(target)) return;
  Files.createDirectories(target.getParent());
  Path staging=Files.createTempDirectory(target.getParent(),".restore-");
  try {
   DatasetUploadService.extract(archive(key),staging,maxExpanded);
   Files.move(staging,target);
  } finally {
   if(Files.exists(staging)) try(var paths=Files.walk(staging)) { for(Path path:paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path); }
  }
 }
 private void validateKey(String key) throws IOException {
  if(key==null || !key.matches("[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")) throw new IOException("Invalid dataset storage key");
 }
}
