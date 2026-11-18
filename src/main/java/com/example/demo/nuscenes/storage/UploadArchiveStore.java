package com.example.demo.nuscenes.storage;

import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.nio.file.*;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.Semaphore;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.http.urlconnection.UrlConnectionHttpClient;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3ClientBuilder;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;
import software.amazon.awssdk.core.interceptor.ExecutionInterceptor;
import software.amazon.awssdk.retries.StandardRetryStrategy;

/** Optional durable archive storage. Credentials come from the ECS task role/default SDK chain. */
@Component
public class UploadArchiveStore implements AutoCloseable {
 public static final long MAX_ARCHIVE_BYTES=5_000_000_000L;
 private final String bucket;
 private final S3Client s3;
 private final MultipartArchiveUploader multipart;
 private final long multipartThreshold;
 private final Semaphore uploadPermit=new Semaphore(1,true);
 @Autowired
 public UploadArchiveStore(@Value("${uploads.s3-bucket:}") String bucket,
   @Value("${uploads.s3-multipart-enabled:false}") boolean multipartEnabled,
   @Value("${uploads.s3-upload-concurrency:4}") int concurrency,
   @Value("${uploads.s3-multipart-threshold-bytes:1073741824}") long multipartThreshold) {
  this(bucket,bucket.isBlank()?null:clientBuilder().build(),multipartEnabled,concurrency,multipartThreshold);
 }
 UploadArchiveStore(String bucket,S3Client client,boolean multipartEnabled,int concurrency,long multipartThreshold) {
  if(multipartThreshold<MultipartArchiveUploader.THRESHOLD_BYTES || multipartThreshold>MAX_ARCHIVE_BYTES)
   throw new IllegalArgumentException("S3 multipart threshold must be 64MiB..5GB");
  this.bucket=bucket;
  this.s3=client;
  this.multipartThreshold=multipartThreshold;
  this.multipart=client!=null && multipartEnabled?new MultipartArchiveUploader(client,concurrency):null;
 }
 static S3ClientBuilder clientBuilder(ExecutionInterceptor... interceptors) {
  return S3Client.builder()
   .httpClientBuilder(UrlConnectionHttpClient.builder().connectionTimeout(Duration.ofSeconds(5)).socketTimeout(Duration.ofSeconds(60)))
   .overrideConfiguration(c->{
    c.apiCallTimeout(Duration.ofMinutes(10)).retryStrategy(StandardRetryStrategy.builder().maxAttempts(3).build());
    for(var interceptor:interceptors)c.addExecutionInterceptor(interceptor);
   });
 }
 public boolean enabled() { return s3!=null; }
 private String objectKey(String key,DatasetArchive.Format format) {
  if(!key.matches("[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")) throw new IllegalArgumentException("Invalid upload key");
  return "uploads/"+key+format.extension;
 }
 public void put(String key,Path archive) throws IOException {
  var format=DatasetArchive.detect(archive);
  if(s3==null)return;
  String object=objectKey(key,format);long size=Files.size(archive),started=System.nanoTime();
  if(size<=0 || size>MAX_ARCHIVE_BYTES)throw new IOException("Archive must be 1 byte..5GB");
  boolean parallel=multipart!=null && size>multipartThreshold;
  try { uploadPermit.acquire(); }catch(InterruptedException interrupted) {
   Thread.currentThread().interrupt();throw new IOException("Interrupted waiting for S3 upload slot",interrupted);
  }
  long admitted=System.nanoTime();
  var log=org.slf4j.LoggerFactory.getLogger(getClass());
  try {
   if(parallel)multipart.upload(bucket,object,archive,format.contentType,size,UUID.randomUUID().toString());
   else s3.putObject(r->r.bucket(bucket).key(object).contentType(format.contentType),RequestBody.fromFile(archive));
   log.info("[S3_TRANSFER] stage=archive_put key={} mode={} bytes={} queue_ms={} transfer_ms={} result=completed",object,
    parallel?"multipart":"single",size,(admitted-started)/1_000_000,(System.nanoTime()-admitted)/1_000_000);
  }catch(IOException|RuntimeException error) {
   log.warn("[S3_TRANSFER] stage=archive_put key={} mode={} bytes={} result=failed error={}",object,parallel?"multipart":"single",size,error.getClass().getSimpleName());
   throw error;
  }finally { uploadPermit.release(); }
 }
 public void remove(String key,DatasetArchive.Format format) { if(s3!=null) s3.deleteObject(r->r.bucket(bucket).key(objectKey(key,format))); }
 public void fetch(String key,Path target) throws IOException {
  if(s3==null) throw new IOException("Upload archive is not on this server and S3 is not configured");
  var log=org.slf4j.LoggerFactory.getLogger(getClass());long started=System.nanoTime();
  log.info("[CACHE] upload={} stage=s3_download event=started",key);
  if(Files.exists(target))throw new FileAlreadyExistsException(target.toString());
  Path staging=Files.createTempFile(target.toAbsolutePath().getParent(),".s3-download-",".part");
  try { for(var format:DatasetArchive.Format.values()) {
  long total=0;
  try {
  try(var input=s3.getObject(r->r.bucket(bucket).key(objectKey(key,format)));
      var output=Files.newOutputStream(staging,StandardOpenOption.TRUNCATE_EXISTING)) {
   Long expected=input.response().contentLength();
   if(expected==null || expected<=0 || expected>MAX_ARCHIVE_BYTES)throw new IOException("Invalid S3 archive length");
   byte[] buffer=new byte[65536];int count;
   while((count=input.read(buffer))!=-1) {
    total+=count;if(total>MAX_ARCHIVE_BYTES) throw new IOException("S3 upload archive exceeds 5GB");
    output.write(buffer,0,count);
   }
   if(total!=expected)throw new IOException("S3 archive response was truncated");
  }
   Files.move(staging,target);
   log.info("[CACHE] upload={} stage=s3_download event=completed bytes={} wall_ms={}",key,total,(System.nanoTime()-started)/1_000_000);
   return;
  } catch(NoSuchKeyException missing) { if(format==DatasetArchive.Format.TGZ) throw missing; }
  } }catch(IOException|RuntimeException error) {
   log.warn("[S3_TRANSFER] stage=archive_fetch key={} result=failed error={}",key,error.getClass().getSimpleName());throw error;
  }finally { Files.deleteIfExists(staging); }
 }
 @Override @PreDestroy public void close() { if(multipart!=null)multipart.close();if(s3!=null)s3.close(); }
}
