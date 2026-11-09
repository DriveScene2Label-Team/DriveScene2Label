package com.example.demo.nuscenes.storage;

import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.nio.file.*;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.http.urlconnection.UrlConnectionHttpClient;
import software.amazon.awssdk.services.s3.S3Client;

/** Optional durable archive storage. Credentials come from the ECS task role/default SDK chain. */
@Component
public class UploadArchiveStore {
 public static final long MAX_ARCHIVE_BYTES=5_000_000_000L;
 private final String bucket;
 private final S3Client s3;
 public UploadArchiveStore(@Value("${uploads.s3-bucket:}") String bucket) {
  this.bucket=bucket;
  this.s3=bucket.isBlank()?null:S3Client.builder()
   .httpClientBuilder(UrlConnectionHttpClient.builder().connectionTimeout(Duration.ofSeconds(5)).socketTimeout(Duration.ofSeconds(60)))
   .overrideConfiguration(c->c.apiCallTimeout(Duration.ofMinutes(10))).build();
 }
 public boolean enabled() { return s3!=null; }
 private String objectKey(String key) {
  if(!key.matches("[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")) throw new IllegalArgumentException("Invalid upload key");
  return "uploads/"+key+".zip";
 }
 public void put(String key,Path archive) {
  if(s3!=null) s3.putObject(r->r.bucket(bucket).key(objectKey(key)).contentType("application/zip"),RequestBody.fromFile(archive));
 }
 public void remove(String key) { if(s3!=null) s3.deleteObject(r->r.bucket(bucket).key(objectKey(key))); }
 public void fetch(String key,Path target) throws IOException {
  if(s3==null) throw new IOException("Upload archive is not on this server and S3 is not configured");
  try(var input=s3.getObject(r->r.bucket(bucket).key(objectKey(key)));
      var output=Files.newOutputStream(target,StandardOpenOption.CREATE_NEW)) {
   long total=0;byte[] buffer=new byte[65536];int count;
   while((count=input.read(buffer))!=-1) {
    total+=count;if(total>MAX_ARCHIVE_BYTES) throw new IOException("S3 upload archive exceeds 5GB");
    output.write(buffer,0,count);
   }
  }
 }
 @PreDestroy public void close() { if(s3!=null) s3.close(); }
}
