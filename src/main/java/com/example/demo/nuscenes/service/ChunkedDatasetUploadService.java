package com.example.demo.nuscenes.service;

import com.example.demo.nuscenes.storage.DatasetStorage;
import com.example.demo.nuscenes.storage.DatasetArchive;
import com.example.demo.nuscenes.storage.UploadArchiveStore;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ChunkedDatasetUploadService {
 public static final int CHUNK_BYTES=4_000_000;
 public record Status(UUID id,String status,long sizeBytes,long receivedBytes,int chunkBytes,Long datasetId,Integer sceneCount,String errorMessage,boolean workerEnabled) {}
 public record Row(UUID id,String filename,long sizeBytes,long receivedBytes,String status,UUID executionToken,Long datasetId,String errorMessage) {}
 private final JdbcClient jdbc; private final DatasetUploadService uploads; private final Path incoming; private final TransactionTemplate tx; private final boolean enabled;
 public ChunkedDatasetUploadService(JdbcClient jdbc,DatasetUploadService uploads,DatasetStorage storage,PlatformTransactionManager manager,@Value("${uploads.worker.enabled:true}") boolean enabled) {
  this.jdbc=jdbc;this.uploads=uploads;this.incoming=storage.uploads().resolve("incoming");this.tx=new TransactionTemplate(manager);this.enabled=enabled;
 }
 public Status create(String filename,long size) throws IOException {
  if(filename==null || filename.length()>255 || !DatasetArchive.supported(filename) || size<=0) throw bad("nuScenes ZIP, TGZ 또는 TAR.GZ를 선택해 주세요.");
  if(size>UploadArchiveStore.MAX_ARCHIVE_BYTES) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,"압축 파일은 5GB 이하만 지원합니다.");
  Files.createDirectories(incoming);
  if(Files.getFileStore(incoming).getUsableSpace()<size*2+9L*1024*1024*1024) throw new ResponseStatusException(HttpStatus.INSUFFICIENT_STORAGE,"로컬 서버의 압축 해제·보관 공간이 부족합니다.");
  UUID id=UUID.randomUUID();
  jdbc.sql("INSERT INTO dataset_upload_session(id,filename,size_bytes) VALUES(:id,:n,:s)").param("id",id).param("n",filename).param("s",size).update();
  org.slf4j.LoggerFactory.getLogger(getClass()).info("[UPLOAD_TRANSFER] upload={} event=created bytes={}",id,size);
  return status(id);
 }
 private Row row(UUID id,boolean locked) { return jdbc.sql("SELECT id,filename,size_bytes,received_bytes,status,execution_token,dataset_id,error_message FROM dataset_upload_session WHERE id=:id"+(locked?" FOR UPDATE":"")).param("id",id).query(Row.class).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"업로드 세션을 찾을 수 없습니다.")); }
 public Status status(UUID id) {
  var r=row(id,false);
  Integer scenes=r.datasetId()==null?null:jdbc.sql("SELECT count(*)::integer FROM scene WHERE dataset_id=:d").param("d",r.datasetId()).query(Integer.class).single();
  return new Status(r.id(),r.status(),r.sizeBytes(),r.receivedBytes(),CHUNK_BYTES,r.datasetId(),scenes,r.errorMessage(),enabled);
 }
 private Path file(UUID id) { return incoming.resolve(id.toString()+".zip"); }
 public Status part(UUID id,long offset,InputStream input) throws IOException {
  long started=System.nanoTime();
  // Bound memory even if a client lies about Content-Length.
  byte[] bytes=input.readNBytes(CHUNK_BYTES+1);
  long receivedAt=System.nanoTime();
  if(bytes.length>CHUNK_BYTES) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,"전송 조각이 너무 큽니다.");
  tx.executeWithoutResult(transaction->{
   var r=row(id,true);
   if(!"RECEIVING".equals(r.status())) throw conflict("이미 파일 검증이 시작되었습니다.");
   if(offset<0 || offset%CHUNK_BYTES!=0 || offset>=r.sizeBytes() || bytes.length!=Math.min(CHUNK_BYTES,r.sizeBytes()-offset)) throw bad("전송 위치 또는 조각 크기가 올바르지 않습니다.");
   if(offset>r.receivedBytes()) throw conflict("앞선 파일 조각부터 전송해 주세요.");
   try(FileChannel channel=FileChannel.open(file(id),StandardOpenOption.CREATE,StandardOpenOption.READ,StandardOpenOption.WRITE)) {
    channel.position(offset);
    if(offset<r.receivedBytes()) {
     ByteBuffer previous=ByteBuffer.allocate(bytes.length);
     while(previous.hasRemaining() && channel.read(previous)>0) { }
     if(previous.hasRemaining() || !Arrays.equals(previous.array(),bytes)) throw conflict("이미 전송한 조각과 내용이 다릅니다. 같은 파일을 선택해 주세요.");
     return;
    }
    ByteBuffer data=ByteBuffer.wrap(bytes);while(data.hasRemaining()) channel.write(data);channel.force(true);
   } catch(IOException error) { throw new UncheckedIOException(error); }
   jdbc.sql("UPDATE dataset_upload_session SET received_bytes=:n,updated_at=now() WHERE id=:id").param("n",offset+bytes.length).param("id",id).update();
  });
  var result=status(id);
  org.slf4j.LoggerFactory.getLogger(getClass()).info("[UPLOAD_TRANSFER] upload={} event=part offset={} bytes={} received={} receive_ms={} persist_status_ms={} total_ms={}",id,offset,bytes.length,result.receivedBytes(),(receivedAt-started)/1_000_000,(System.nanoTime()-receivedAt)/1_000_000,(System.nanoTime()-started)/1_000_000);
  return result;
 }
 public Status complete(UUID id) {
  tx.executeWithoutResult(transaction->{
   var r=row(id,true);
   if(r.receivedBytes()!=r.sizeBytes()) throw conflict("파일 전송이 아직 완료되지 않았습니다.");
   if("RECEIVING".equals(r.status()) || "FAILED".equals(r.status())) jdbc.sql("UPDATE dataset_upload_session SET status='QUEUED',error_message=NULL,updated_at=now() WHERE id=:id").param("id",id).update();
  });
  var result=status(id);
  org.slf4j.LoggerFactory.getLogger(getClass()).info("[UPLOAD_TRANSFER] upload={} event=submitted received={} status={}",id,result.receivedBytes(),result.status());
  return result;
 }
 public Optional<Row> claim() {
  return tx.execute(transaction->{
   if(jdbc.sql("SELECT maintenance FROM deployment_control WHERE id=1 FOR SHARE").query(Boolean.class).single()) return Optional.empty();
   var next=jdbc.sql("SELECT id FROM dataset_upload_session WHERE status='QUEUED' OR (status='PROCESSING' AND updated_at<now()-interval '2 minutes') ORDER BY updated_at LIMIT 1 FOR UPDATE SKIP LOCKED").query(UUID.class).optional();
   if(next.isEmpty()) return Optional.empty();
   jdbc.sql("UPDATE dataset_upload_session SET status='PROCESSING',execution_token=:t,updated_at=now() WHERE id=:id").param("t",UUID.randomUUID()).param("id",next.get()).update();
   return Optional.of(row(next.get(),false));
  });
 }
 public void process(Row work) {
  try {
   var result=uploads.upload(new ArchiveFile(file(work.id()),work.filename()),work.id().toString());
   jdbc.sql("UPDATE dataset_upload_session SET status='COMPLETED',dataset_id=:d,updated_at=now() WHERE id=:id AND execution_token=:t AND status='PROCESSING'").param("d",result.datasetId()).param("id",work.id()).param("t",work.executionToken()).update();
   Files.deleteIfExists(file(work.id()));
  } catch(Exception error) {
   String message=error instanceof ResponseStatusException response?response.getReason():"파일 검증·등록에 실패했습니다. 로컬 서버와 S3 연결을 확인한 뒤 다시 시도해 주세요.";
   org.slf4j.LoggerFactory.getLogger(getClass()).error("Chunked upload import failed id={}",work.id(),error);
   jdbc.sql("UPDATE dataset_upload_session SET status='FAILED',error_message=:e,updated_at=now() WHERE id=:id AND execution_token=:t AND status='PROCESSING'").param("e",message).param("id",work.id()).param("t",work.executionToken()).update();
  }
 }
 public void heartbeat(Row work) { jdbc.sql("UPDATE dataset_upload_session SET updated_at=now() WHERE id=:id AND execution_token=:t AND status='PROCESSING'").param("id",work.id()).param("t",work.executionToken()).update(); }
 private record ArchiveFile(Path path,String originalFilename) implements MultipartFile {
  public String getName() { return "file"; } public String getOriginalFilename() { return originalFilename; }
  public String getContentType() { return "application/octet-stream"; }
  public boolean isEmpty() { return getSize()==0; }
  public long getSize() { try { return Files.size(path); } catch(IOException e) { throw new UncheckedIOException(e); } }
  public byte[] getBytes() { throw new UnsupportedOperationException("Use streaming access for archives"); }
  public InputStream getInputStream() throws IOException { return Files.newInputStream(path); }
  public void transferTo(File destination) throws IOException { Files.copy(path,destination.toPath()); }
 }
 private static ResponseStatusException bad(String message) { return new ResponseStatusException(HttpStatus.BAD_REQUEST,message); }
 private static ResponseStatusException conflict(String message) { return new ResponseStatusException(HttpStatus.CONFLICT,message); }
}
