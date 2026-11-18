package com.example.demo.nuscenes.storage;

import java.io.*;
import java.nio.channels.Channels;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.http.ContentStreamProvider;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.*;

/** One archive at a time is admitted by UploadArchiveStore; at most concurrency parts are in flight. */
final class MultipartArchiveUploader implements AutoCloseable {
 static final long PART_BYTES=16L*1024*1024, THRESHOLD_BYTES=64L*1024*1024;
 private static final Logger LOG=LoggerFactory.getLogger(MultipartArchiveUploader.class);
 private final S3Client s3;
 private final int concurrency;
 private final ExecutorService workers;

 MultipartArchiveUploader(S3Client s3,int concurrency) {
  if(concurrency<1 || concurrency>4)throw new IllegalArgumentException("S3 upload concurrency must be 1..4");
  this.s3=s3;this.concurrency=concurrency;
  workers=Executors.newFixedThreadPool(concurrency,r->{var t=new Thread(r,"s3-archive-part");t.setDaemon(true);return t;});
 }

 void upload(String bucket,String key,Path source,String contentType,long size,String attempt) throws IOException {
  String uploadId=s3.createMultipartUpload(CreateMultipartUploadRequest.builder().bucket(bucket).key(key)
   .contentType(contentType).metadata(Map.of("ds2l-upload-attempt",attempt))
   .checksumAlgorithm(ChecksumAlgorithm.CRC32).checksumType(ChecksumType.COMPOSITE)
   .overrideConfiguration(c->c.apiCallTimeout(Duration.ofSeconds(30))).build()).uploadId();
  LOG.info("[S3_TRANSFER] stage=multipart_create key={} upload_id={} concurrency={}",key,uploadId,concurrency);
  var completion=new ExecutorCompletionService<CompletedPart>(workers);
  var inFlight=new HashSet<Future<CompletedPart>>();
  var parts=new ArrayList<CompletedPart>();
  boolean interrupted=false;
  try {
   int count=Math.toIntExact((size+PART_BYTES-1)/PART_BYTES),next=1;
   while(next<=count || !inFlight.isEmpty()) {
    while(next<=count && inFlight.size()<concurrency) {
     int number=next++;
     inFlight.add(completion.submit(()->part(bucket,key,uploadId,source,number,Math.min(PART_BYTES,size-(number-1)*PART_BYTES))));
    }
    Future<CompletedPart> finished=completion.take();
    inFlight.remove(finished);parts.add(finished.get());
   }
   parts.sort(Comparator.comparingInt(CompletedPart::partNumber));
   s3.completeMultipartUpload(CompleteMultipartUploadRequest.builder().bucket(bucket).key(key).uploadId(uploadId)
    .multipartUpload(CompletedMultipartUpload.builder().parts(parts).build())
    .overrideConfiguration(c->c.apiCallTimeout(Duration.ofSeconds(60))).build());
  } catch(Exception failure) {
   interrupted=failure instanceof InterruptedException || Thread.interrupted();
   // Future.cancel reports completion before blocking HTTP has stopped. Drain the actual
   // calls before aborting so a late UploadPart cannot recreate stored parts after cleanup.
   for(Future<CompletedPart> future:inFlight) {
    boolean done=false;
    while(!done)try { future.get();done=true; }
    catch(InterruptedException again) { interrupted=true; }
    catch(ExecutionException|CancellationException ignored) { done=true; }
   }
   // A successful Complete response may have been lost. Match this attempt only;
   // never delete or accept an older object at the same key.
   if(committed(bucket,key,size,attempt)) {
    LOG.info("[S3_TRANSFER] stage=multipart_reconcile key={} result=committed",key);
    return;
   }
   try { abortAndVerify(bucket,key,uploadId); }
   catch(RuntimeException cleanup) {
    failure.addSuppressed(cleanup);
    LOG.error("[S3_TRANSFER] stage=multipart_abort key={} upload_id={} result=unconfirmed error={}",key,uploadId,cleanup.getClass().getSimpleName());
   }
   if(failure instanceof RuntimeException runtime)throw runtime;
   throw new IOException(interrupted?"S3 archive upload interrupted":"S3 multipart upload failed",failure);
  } finally {
   if(interrupted)Thread.currentThread().interrupt();
  }
 }

 private CompletedPart part(String bucket,String key,String uploadId,Path source,int number,long bytes) throws IOException {
  long start=System.nanoTime();
  try(var slice=new FileSlice(source,(number-1)*PART_BYTES,bytes)) {
   var response=s3.uploadPart(UploadPartRequest.builder().bucket(bucket).key(key).uploadId(uploadId).partNumber(number)
    .contentLength(bytes).checksumAlgorithm(ChecksumAlgorithm.CRC32)
    .overrideConfiguration(c->c.apiCallTimeout(Duration.ofSeconds(120)).apiCallAttemptTimeout(Duration.ofSeconds(60))).build(),
    RequestBody.fromContentProvider(slice,bytes,"application/octet-stream"));
   LOG.info("[S3_TRANSFER] stage=upload_part key={} part={} bytes={} wall_ms={} status={} request_id={}",
    key,number,bytes,(System.nanoTime()-start)/1_000_000,response.sdkHttpResponse().statusCode(),response.responseMetadata().requestId());
   return CompletedPart.builder().partNumber(number).eTag(response.eTag()).checksumCRC32(response.checksumCRC32()).build();
  }
 }

 private boolean committed(String bucket,String key,long size,String attempt) {
  try {
   var head=s3.headObject(HeadObjectRequest.builder().bucket(bucket).key(key)
    .overrideConfiguration(c->c.apiCallTimeout(Duration.ofSeconds(30))).build());
   return Objects.equals(head.contentLength(),size) && attempt.equals(head.metadata().get("ds2l-upload-attempt"));
  } catch(RuntimeException unavailable) { return false; }
 }

 private void abortAndVerify(String bucket,String key,String uploadId) {
  for(int retry=0;retry<3;retry++) {
   try { s3.abortMultipartUpload(AbortMultipartUploadRequest.builder().bucket(bucket).key(key).uploadId(uploadId)
     .overrideConfiguration(c->c.apiCallTimeout(Duration.ofSeconds(30))).build()); }
   catch(S3Exception missing) { if(missing.statusCode()!=404)throw missing; }
   try { s3.listParts(ListPartsRequest.builder().bucket(bucket).key(key).uploadId(uploadId).maxParts(1)
     .overrideConfiguration(c->c.apiCallTimeout(Duration.ofSeconds(30))).build()); }
   catch(S3Exception missing) {
    if(missing.statusCode()!=404)throw missing;
    LOG.info("[S3_TRANSFER] stage=multipart_abort key={} upload_id={} result=verified_absent",key,uploadId);
    return;
   }
  }
  throw new IllegalStateException("Multipart cleanup could not be confirmed");
 }

 @Override public void close() { workers.shutdown(); }

 /** Reopens exactly the same file range for SDK retries; never buffers a whole part/file. */
 static final class FileSlice implements ContentStreamProvider,AutoCloseable {
  private final Path path;private final long offset,length;private InputStream current;
  FileSlice(Path path,long offset,long length) { this.path=path;this.offset=offset;this.length=length; }
  @Override public InputStream newStream() {
   try {
    close();var channel=Files.newByteChannel(path,StandardOpenOption.READ);
    try { channel.position(offset); }catch(IOException error) { channel.close();throw error; }
    current=new FilterInputStream(Channels.newInputStream(channel)) {
     private long remaining=length;
     @Override public int read() throws IOException { byte[] one=new byte[1];return read(one,0,1)<0?-1:one[0]&255; }
     @Override public int read(byte[] b,int off,int len) throws IOException {
      if(len==0)return 0;if(remaining==0)return -1;
      int count=in.read(b,off,(int)Math.min(len,remaining));
      if(count<0)throw new EOFException("Archive changed or was truncated during upload");
      remaining-=count;return count;
     }
     @Override public long skip(long n) throws IOException { long skipped=in.skip(Math.min(Math.max(n,0),remaining));remaining-=skipped;return skipped; }
     @Override public int available() throws IOException { return (int)Math.min(in.available(),remaining); }
    };
    return current;
   }catch(IOException failure) { throw new UncheckedIOException(failure); }
  }
  @Override public void close() throws IOException { if(current!=null) { current.close();current=null; } }
 }
}
