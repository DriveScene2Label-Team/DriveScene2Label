package com.example.demo.nuscenes.storage;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.Consumer;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.http.SdkHttpResponse;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class S3ArchiveTransferTests {
 @TempDir Path root;
 private static final String BUCKET="fixture-bucket",KEY="uploads/"+UUID.randomUUID()+".tar.gz";
 private S3Client client;
 @BeforeEach void setup() {
  client=mock(S3Client.class);
  when(client.createMultipartUpload(any(CreateMultipartUploadRequest.class))).thenReturn(CreateMultipartUploadResponse.builder().uploadId("owned-upload").build());
  when(client.headObject(any(HeadObjectRequest.class))).thenThrow(NoSuchKeyException.builder().statusCode(404).build());
  when(client.listParts(any(ListPartsRequest.class))).thenThrow(S3Exception.builder().statusCode(404).build());
 }
 private UploadPartResponse part(int number) {
  UploadPartResponse.Builder response=UploadPartResponse.builder().eTag("etag-"+number).checksumCRC32("AAAAAA==");
  response.responseMetadata(S3ResponseMetadata.create(null));
  response.sdkHttpResponse(SdkHttpResponse.builder().statusCode(200).build());return response.build();
 }
 private Path archive(long size) throws IOException {
  Path p=root.resolve(UUID.randomUUID()+".tgz");
  try(var f=new RandomAccessFile(p.toFile(),"rw")) { f.setLength(size);f.write(new byte[]{31,(byte)139,0,0}); }
  return p;
 }
 @Test void retryStreamReopensSameRangeAndRejectsTruncation() throws Exception {
  Path p=root.resolve("bytes");Files.write(p,new byte[]{0,1,2,3,4,5});
  try(var provider=new MultipartArchiveUploader.FileSlice(p,2,3)) {
   assertThat(provider.newStream().readAllBytes()).containsExactly(2,3,4);
   assertThat(provider.newStream().readAllBytes()).containsExactly(2,3,4);
  }
  try(var provider=new MultipartArchiveUploader.FileSlice(p,4,4)) {
   assertThatThrownBy(()->provider.newStream().readAllBytes()).isInstanceOf(EOFException.class);
  }
 }
 @Test void boundedConcurrencyAndOrderedCompletionWithShortLastPart() throws Exception {
  AtomicInteger active=new AtomicInteger(),peak=new AtomicInteger();
  CountDownLatch firstWave=new CountDownLatch(4);
  List<Long> lengths=Collections.synchronizedList(new ArrayList<>());
  when(client.uploadPart(any(UploadPartRequest.class),any(RequestBody.class))).thenAnswer(call->{
   UploadPartRequest request=call.getArgument(0);RequestBody body=call.getArgument(1);
   peak.accumulateAndGet(active.incrementAndGet(),Math::max);firstWave.countDown();
   try {
    assertThat(firstWave.await(5,TimeUnit.SECONDS)).isTrue();
    assertThat(body.optionalContentLength().orElseThrow()).isEqualTo(request.contentLength());
    lengths.add(request.contentLength());return part(request.partNumber());
   }finally { active.decrementAndGet(); }
  });
  long size=MultipartArchiveUploader.PART_BYTES*4+123;
  try(var uploader=new MultipartArchiveUploader(client,4)) { uploader.upload(BUCKET,KEY,archive(size),"application/gzip",size,"attempt"); }
  assertThat(peak.get()).isEqualTo(4);assertThat(lengths).hasSize(5).contains(123L);
  var completion=org.mockito.ArgumentCaptor.forClass(CompleteMultipartUploadRequest.class);
  verify(client).completeMultipartUpload(completion.capture());
  assertThat(completion.getValue().multipartUpload().parts()).extracting(CompletedPart::partNumber).containsExactly(1,2,3,4,5);
  verify(client,never()).abortMultipartUpload(any(AbortMultipartUploadRequest.class));
 }
 @Test void failureDrainsOtherRequestsBeforeAbortAndDoesNotComplete() throws Exception {
  CountDownLatch otherStarted=new CountDownLatch(1),releaseOther=new CountDownLatch(1);
  AtomicBoolean drained=new AtomicBoolean();
  when(client.uploadPart(any(UploadPartRequest.class),any(RequestBody.class))).thenAnswer(call->{
   UploadPartRequest request=call.getArgument(0);
   if(request.partNumber()==1) { assertThat(otherStarted.await(5,TimeUnit.SECONDS)).isTrue();releaseOther.countDown();throw S3Exception.builder().statusCode(503).build(); }
   otherStarted.countDown();assertThat(releaseOther.await(5,TimeUnit.SECONDS)).isTrue();drained.set(true);return part(request.partNumber());
  });
  when(client.abortMultipartUpload(any(AbortMultipartUploadRequest.class))).thenAnswer(call->{assertThat(drained.get()).isTrue();return AbortMultipartUploadResponse.builder().build();});
  try(var uploader=new MultipartArchiveUploader(client,2)) {
   assertThatThrownBy(()->uploader.upload(BUCKET,KEY,archive(40_000_000),"application/gzip",40_000_000,"attempt")).isInstanceOf(IOException.class);
  }
  verify(client).abortMultipartUpload(any(AbortMultipartUploadRequest.class));
  verify(client,never()).completeMultipartUpload(any(CompleteMultipartUploadRequest.class));
 }
 @Test void lostCompletionAcknowledgementAcceptsOnlyMatchingAttemptAndLength() throws Exception {
  when(client.uploadPart(any(UploadPartRequest.class),any(RequestBody.class))).thenReturn(part(1));
  when(client.completeMultipartUpload(any(CompleteMultipartUploadRequest.class))).thenThrow(new RuntimeException("lost response"));
  when(client.headObject(any(HeadObjectRequest.class))).thenReturn(HeadObjectResponse.builder().contentLength(32L).metadata(Map.of("ds2l-upload-attempt","mine")).build());
  try(var uploader=new MultipartArchiveUploader(client,1)) { uploader.upload(BUCKET,KEY,archive(32),"application/gzip",32,"mine"); }
  verify(client,never()).abortMultipartUpload(any(AbortMultipartUploadRequest.class));
  try(var uploader=new MultipartArchiveUploader(client,1)) {
   assertThatThrownBy(()->uploader.upload(BUCKET,KEY,archive(32),"application/gzip",32,"other")).isInstanceOf(RuntimeException.class);
  }
  verify(client).abortMultipartUpload(any(AbortMultipartUploadRequest.class));
 }
 @Test void cleanupPermissionFailureIsNotReportedAsSuccess() throws Exception {
  when(client.uploadPart(any(UploadPartRequest.class),any(RequestBody.class))).thenThrow(new RuntimeException("part failure"));
  when(client.abortMultipartUpload(any(AbortMultipartUploadRequest.class))).thenThrow(S3Exception.builder().statusCode(403).build());
  try(var uploader=new MultipartArchiveUploader(client,1)) {
   assertThatThrownBy(()->uploader.upload(BUCKET,KEY,archive(32),"application/gzip",32,"mine"))
    .isInstanceOf(IOException.class).satisfies(error->assertThat(error.getCause().getSuppressed()).hasSize(1));
  }
 }
 @Test void callerInterruptionWaitsForPartAndPreservesInterruptAfterCleanup() throws Exception {
  CountDownLatch started=new CountDownLatch(1),release=new CountDownLatch(1);
  AtomicBoolean restored=new AtomicBoolean();AtomicReference<Throwable> error=new AtomicReference<>();
  when(client.uploadPart(any(UploadPartRequest.class),any(RequestBody.class))).thenAnswer(call->{
   started.countDown();assertThat(release.await(5,TimeUnit.SECONDS)).isTrue();return part(1);
  });
  Path source=archive(32);
  try(var uploader=new MultipartArchiveUploader(client,1)) {
   Thread caller=new Thread(()->{
    try { uploader.upload(BUCKET,KEY,source,"application/gzip",32,"mine"); }
    catch(Throwable failure) { error.set(failure);restored.set(Thread.currentThread().isInterrupted()); }
   });
   caller.start();assertThat(started.await(5,TimeUnit.SECONDS)).isTrue();caller.interrupt();release.countDown();caller.join(5000);
   assertThat(caller.isAlive()).isFalse();assertThat(error.get()).isInstanceOf(IOException.class);assertThat(restored.get()).isTrue();
  }
  verify(client).abortMultipartUpload(any(AbortMultipartUploadRequest.class));
  verify(client,never()).completeMultipartUpload(any(CompleteMultipartUploadRequest.class));
 }
 @Test void smallArchivesUseSinglePutAndExistingDownloadTargetIsPreserved() throws Exception {
  String key=UUID.randomUUID().toString();Path target=root.resolve("existing");Files.writeString(target,"preserve");
  try(var store=new UploadArchiveStore(BUCKET,client,true,4,1073741824L)) {
   store.put(key,archive(64));
   assertThatThrownBy(()->store.fetch(key,target)).isInstanceOf(FileAlreadyExistsException.class);
  }
  verify(client).putObject(any(Consumer.class),any(RequestBody.class));
  verify(client,never()).createMultipartUpload(any(CreateMultipartUploadRequest.class));
  assertThat(Files.readString(target)).isEqualTo("preserve");
 }
 @Test void truncatedDownloadNeverPublishesAndCanRetryWithoutPartialFiles() throws Exception {
  String key=UUID.randomUUID().toString();Path target=root.resolve("download");
  when(client.getObject(any(Consumer.class))).thenAnswer(call->new ResponseInputStream<>(GetObjectResponse.builder().contentLength(100L).build(),new ByteArrayInputStream(new byte[]{1,2,3})));
  try(var store=new UploadArchiveStore(BUCKET,client,false,4,1073741824L)) {
   assertThatThrownBy(()->store.fetch(key,target)).isInstanceOf(IOException.class);
   assertThat(target).doesNotExist();
   try(var paths=Files.list(root)) { assertThat(paths.toList()).isEmpty(); }
   when(client.getObject(any(Consumer.class))).thenAnswer(call->new ResponseInputStream<>(GetObjectResponse.builder().contentLength(3L).build(),new ByteArrayInputStream(new byte[]{1,2,3})));
   store.fetch(key,target);assertThat(Files.readAllBytes(target)).containsExactly(1,2,3);
  }
 }
 @Test void conservativeSizeGuardKeepsSmallFilesSingleAndAllowsLargeMultipart() throws Exception {
  when(client.uploadPart(any(UploadPartRequest.class),any(RequestBody.class))).thenAnswer(call->part(((UploadPartRequest)call.getArgument(0)).partNumber()));
  try(var store=new UploadArchiveStore(BUCKET,client,true,4,1073741824L)) {
   store.put(UUID.randomUUID().toString(),archive(109696439));
   store.put(UUID.randomUUID().toString(),archive(1073741824L));
   verify(client,times(2)).putObject(any(Consumer.class),any(RequestBody.class));
   verify(client,never()).createMultipartUpload(any(CreateMultipartUploadRequest.class));
   store.put(UUID.randomUUID().toString(),archive(1073741825L));
   verify(client).createMultipartUpload(any(CreateMultipartUploadRequest.class));
   verify(client).completeMultipartUpload(any(CompleteMultipartUploadRequest.class));
  }
 }
}
