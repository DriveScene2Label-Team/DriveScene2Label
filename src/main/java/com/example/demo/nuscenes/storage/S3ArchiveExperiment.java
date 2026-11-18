package com.example.demo.nuscenes.storage;

import tools.jackson.databind.json.JsonMapper;
import java.io.*;
import java.lang.management.ManagementFactory;
import java.lang.reflect.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.*;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.core.interceptor.*;
import software.amazon.awssdk.http.SdkHttpResponse;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.*;

/** Opt-in offline CLI, never a Spring bean or HTTP route. Uses the production storage path. */
public final class S3ArchiveExperiment {
 private static final JsonMapper JSON=JsonMapper.builder().build();
 private S3ArchiveExperiment() {}

 public static void main(String[] args) throws Exception {
  if(args.length!=8)throw new IllegalArgumentException("bucket source UUID work evidence single|multipart|automatic fault original-tree|none");
  String bucket=args[0],key=args[2],mode=args[5],fault=args[6];
  if(!Set.of("single","multipart","automatic").contains(mode) || !Set.of("none","transient503","permanent503","complete-lost","download-cut","crash").contains(fault))
   throw new IllegalArgumentException("Unknown experiment case");
  UUID.fromString(key);
  Path source=Path.of(args[1]),work=Path.of(args[3]),evidence=Path.of(args[4]);
  if(Files.exists(work))throw new FileAlreadyExistsException("Experiment workspace must be fresh: "+work);
  Files.createDirectories(work);Files.createDirectories(evidence);
  // Explicit modes reproduce the measured paths, including small fault fixtures.
  // Automatic exercises the conservative production size guard with multipart enabled.
  long threshold=mode.equals("automatic")?1073741824L:MultipartArchiveUploader.THRESHOLD_BYTES;
  boolean multipartEnabled=!mode.equals("single");
  var result=new LinkedHashMap<String,Object>();
  result.put("started_at",Instant.now().toString());result.put("requested_mode",mode);
  result.put("mode",multipartEnabled && Files.size(source)>threshold?"multipart":"single");result.put("fault",fault);
  result.put("multipart_threshold_bytes",threshold);
  result.put("key","uploads/"+key+DatasetArchive.detect(source).extension);result.put("bytes",Files.size(source));
  result.put("java",System.getProperty("java.version"));result.put("processors",Runtime.getRuntime().availableProcessors());
  result.put("scope","Java production UploadArchiveStore + DatasetStorage; no HTTP/browser/RDS/model execution");
  String expected=sha256(source);result.put("source_sha256",expected);
  var process=(com.sun.management.OperatingSystemMXBean)ManagementFactory.getOperatingSystemMXBean();
  long cpu=process.getProcessCpuTime();
  AtomicBoolean stop=new AtomicBoolean();AtomicLong peakHeap=new AtomicLong(),peakRss=new AtomicLong();
  try(var events=new Events(evidence.resolve("events.jsonl"),fault)) {
   Thread sampler=new Thread(()->{
    while(!stop.get()) {
     peakHeap.accumulateAndGet(ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed(),Math::max);
     try {
      for(String line:Files.readAllLines(Path.of("/proc/self/status")))if(line.startsWith("VmRSS:"))
       peakRss.accumulateAndGet(Long.parseLong(line.split("\\s+")[1])*1024,Math::max);
      Thread.sleep(200);
     }catch(IOException ignored) {}catch(InterruptedException end) { return; }
    }
   },"s3-experiment-metrics");sampler.setDaemon(true);sampler.start();
   try(var real=UploadArchiveStore.clientBuilder(events).build();
       var store=new UploadArchiveStore(bucket,wrap(real,fault,evidence,events),multipartEnabled,4,threshold)) {
    long started=System.nanoTime();
    try {
     store.put(key,source);result.put("upload_s",seconds(started));
     if(fault.equals("permanent503"))throw new AssertionError("Permanent error unexpectedly succeeded");
    }catch(IOException|RuntimeException failure) {
     result.put("upload_s",seconds(started));result.put("upload_error",failure.getClass().getSimpleName());
     if(!fault.equals("permanent503") || events.injected.get()<1)throw failure;
     result.put("expected_failure",true);result.put("pass",true);return;
    }
    var storage=new DatasetStorage(new DatasetFiles("/unused"),work.toString(),store,8L*1024*1024*1024);
    if(fault.equals("download-cut")) {
     try { storage.archive(key);throw new AssertionError("Interrupted download unexpectedly succeeded"); }
     catch(IOException expectedFailure) {
      try(var paths=Files.walk(work)) {
       if(paths.anyMatch(Files::isRegularFile))throw new AssertionError("Partial download was published/left behind");
      }
      result.put("download_failure_clean",true);
     }
    }
    started=System.nanoTime();Path downloaded=storage.archive(key);result.put("download_s",seconds(started));
    String actual=sha256(downloaded);result.put("download_sha256",actual);
    if(!expected.equals(actual))throw new AssertionError("Full file SHA-256 differs");
    if(!args[7].equals("none")) {
     Path original=Path.of(args[7]);
     started=System.nanoTime();Path restored=storage.files("uploads",key).root();result.put("restore_s",seconds(started));
     var before=inventory(original);var after=inventory(restored);
     Files.writeString(evidence.resolve("original-files.json"),JSON.writeValueAsString(before));
     Files.writeString(evidence.resolve("restored-files.json"),JSON.writeValueAsString(after));
     result.put("restored_files",after.size());result.put("all_file_hashes_equal",before.equals(after));
     if(!before.equals(after))throw new AssertionError("Restored file inventory/content differs");
     started=System.nanoTime();
     if(!storage.archive(key).equals(downloaded) || !storage.files("uploads",key).root().equals(restored))throw new AssertionError("Cache path changed");
     result.put("local_cache_hit_s",seconds(started));
    }
    if(fault.equals("transient503") && events.injected.get()!=1)throw new AssertionError("Retry injection did not execute once");
    result.put("pass",true);
   }catch(Throwable error) {
    result.put("pass",false);result.put("error_type",error.getClass().getSimpleName());throw error;
   }finally {
    stop.set(true);sampler.interrupt();sampler.join(2000);
    result.put("process_cpu_s",(process.getProcessCpuTime()-cpu)/1e9);
    result.put("peak_heap_bytes",peakHeap.get());result.put("peak_rss_bytes",peakRss.get());
    result.put("injected_http_503",events.injected.get());result.put("finished_at",Instant.now().toString());
    Files.writeString(evidence.resolve("result.json"),JSON.writerWithDefaultPrettyPrinter().writeValueAsString(result));
    System.out.println(JSON.writeValueAsString(result));
   }
  }
 }

 private static S3Client wrap(S3Client client,String fault,Path evidence,Events events) {
  AtomicBoolean cut=new AtomicBoolean(),lost=new AtomicBoolean();
  return (S3Client)Proxy.newProxyInstance(S3Client.class.getClassLoader(),new Class<?>[]{S3Client.class},(proxy,method,args)->{
   if(method.getName().equals("close"))return null; // outer owner closes the real client once
   Object response;
   try { response=method.invoke(client,args); }catch(InvocationTargetException e) { throw e.getCause(); }
   if(fault.equals("complete-lost") && method.getName().equals("completeMultipartUpload") && lost.compareAndSet(false,true)) {
    events.write(Map.of("event","injected_lost_complete_ack"));throw SdkClientException.create("Injected lost Complete acknowledgement after real S3 success");
   }
   if(fault.equals("crash") && method.getName().equals("uploadPart")) {
    Files.writeString(evidence.resolve("crash-ready.json"),"{\"real_part_accepted\":true}");
    while(true)Thread.sleep(1000); // orchestrator kills only this labelled experiment container
   }
   if(fault.equals("download-cut") && method.getName().equals("getObject") && response instanceof ResponseInputStream<?> stream && cut.compareAndSet(false,true)) {
    events.write(Map.of("event","injected_download_cut","after_bytes",1048576));
    return new ResponseInputStream<>((GetObjectResponse)stream.response(),new FilterInputStream(stream) {
     long remaining=1048576;
     @Override public int read(byte[] b,int off,int len) throws IOException {
      if(remaining<=0) { stream.abort();throw new IOException("Injected download connection loss"); }
      int count=super.read(b,off,(int)Math.min(len,remaining));if(count>0)remaining-=count;return count;
     }
     @Override public void close() throws IOException { stream.abort();super.close(); }
    });
   }
   return response;
  });
 }

 static String sha256(Path path) throws Exception {
  var digest=MessageDigest.getInstance("SHA-256");byte[] buffer=new byte[1024*1024];
  try(var in=Files.newInputStream(path)) { int count;while((count=in.read(buffer))!=-1)digest.update(buffer,0,count); }
  return HexFormat.of().formatHex(digest.digest());
 }
 private static Map<String,Object> inventory(Path root) throws Exception {
  var result=new TreeMap<String,Object>();
  try(var paths=Files.walk(root)) {
   for(Path path:paths.filter(Files::isRegularFile).sorted().toList())
    result.put(root.relativize(path).toString().replace('\\','/'),Map.of("bytes",Files.size(path),"sha256",sha256(path)));
  }
  return result;
 }
 private static double seconds(long start) { return (System.nanoTime()-start)/1e9; }

 private static final class Events implements ExecutionInterceptor,AutoCloseable {
  private final BufferedWriter output;private final String fault;final AtomicInteger injected=new AtomicInteger();
  Events(Path path,String fault) throws IOException { output=Files.newBufferedWriter(path,StandardOpenOption.CREATE_NEW);this.fault=fault; }
  synchronized void write(Map<String,?> fields) {
   var row=new LinkedHashMap<String,Object>(fields);row.put("utc",Instant.now().toString());
   try { output.write(JSON.writeValueAsString(row));output.newLine();output.flush(); }
   catch(IOException error) { throw new UncheckedIOException(error); }
  }
  @Override public void afterTransmission(Context.AfterTransmission context,ExecutionAttributes attributes) {
   var row=new LinkedHashMap<String,Object>();row.put("event","http_attempt");
   row.put("operation",context.request().getClass().getSimpleName());row.put("status",context.httpResponse().statusCode());
   context.httpResponse().firstMatchingHeader("x-amz-request-id").ifPresent(v->row.put("request_id",v));
   if(context.request() instanceof UploadPartRequest part) { row.put("part",part.partNumber());row.put("upload_id",part.uploadId());row.put("bytes",part.contentLength()); }
   write(row);
  }
  @Override public SdkHttpResponse modifyHttpResponse(Context.ModifyHttpResponse context,ExecutionAttributes attributes) {
   if(context.request() instanceof UploadPartRequest part && part.partNumber()==2 &&
      (fault.equals("permanent503") || (fault.equals("transient503") && injected.get()==0))) {
    int count=injected.incrementAndGet();write(Map.of("event","injected_http_response","status",503,"part",2,"attempt",count));
    return context.httpResponse().toBuilder().statusCode(503).statusText("Service Unavailable").build();
   }
   return context.httpResponse();
  }
  @Override public void close() throws IOException { output.close(); }
 }
}
