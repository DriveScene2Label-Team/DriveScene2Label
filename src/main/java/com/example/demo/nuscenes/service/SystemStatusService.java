package com.example.demo.nuscenes.service;
import com.example.demo.nuscenes.api.CodedError;
import com.example.demo.nuscenes.client.AiCapabilitiesClient;
import com.example.demo.nuscenes.client.AiCapabilitiesClient.Snapshot;
import com.example.demo.nuscenes.dto.SystemDtos.*;
import com.example.demo.nuscenes.storage.DatasetFiles;
import com.example.demo.nuscenes.storage.DatasetStorage;
import com.example.demo.nuscenes.storage.RecordingFiles;
import java.io.IOException;
import java.nio.file.Files;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.locks.ReentrantLock;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;
/**
 * GET /api/system/status (docs/frontend-integration-plan.md §7). Light read-only checks: DB catalog, a sample of media
 * files, CLIP model/preprocess vs stored embeddings, VESPA/recording readiness from the AI server. A refresh asks the
 * AI to re-check its runtime; it never starts inference, sbatch, embedding generation or imports.
 * configured is never promoted to READY; an unreachable/older AI yields UNKNOWN/UNAVAILABLE, never a mock.
 */
@Service
public class SystemStatusService {
 private static final int SCHEMA_VERSION=1;
 private static final Duration LOCAL_TTL=Duration.ofSeconds(30);
 private final JdbcClient jdbc;
 private final AiCapabilitiesClient ai;
 private final DatasetStorage media;
 private final RecordingFiles recordingFiles;
 private final String modelName,preprocess,vespaVersion,recordingSdk;
 private final boolean jobWorker,recordingWorker;
 private final Duration aiTtl;
 private final ReentrantLock aiLock=new ReentrantLock();
 private volatile Snapshot cached;
 public SystemStatusService(JdbcClient jdbc,AiCapabilitiesClient ai,DatasetStorage media,RecordingFiles recordingFiles,
   @Value("${embedding.model-name}") String modelName,@Value("${embedding.preprocess}") String preprocess,
   @Value("${auto-label.dataset-version:v1.0-trainval}") String vespaVersion,@Value("${recording.sdk-version:0.38.1}") String recordingSdk,
   @Value("${auto-label.worker.enabled:true}") boolean jobWorker,@Value("${recording.worker.enabled:true}") boolean recordingWorker,
   @Value("${system-status.ai-cache:15s}") Duration aiTtl,@Value("${system-status.check-workers:true}") boolean checkWorkers) {
  this.jdbc=jdbc;this.ai=ai;this.media=media;this.recordingFiles=recordingFiles;this.modelName=modelName;this.preprocess=preprocess;
  this.vespaVersion=vespaVersion;this.recordingSdk=recordingSdk;this.jobWorker=jobWorker||!checkWorkers;this.recordingWorker=recordingWorker||!checkWorkers;this.aiTtl=aiTtl;
 }

 public UUID instanceId() { return jdbc.sql("SELECT instance_id FROM system_instance").query(UUID.class).single(); }

 public SystemStatus status(Long datasetId,boolean refresh) {
  if(datasetId!=null && datasetId<=0) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"datasetId must be positive");
  var now=OffsetDateTime.now();
  DatasetRow ds=datasetId==null?null:dataset(datasetId).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Dataset not found"));
  Snapshot snap=datasetSnapshot(ds,refresh);
  Map<String,Capability> caps=new LinkedHashMap<>();
  caps.put("catalog",new Capability("READY",true,null,null,now,now.plus(LOCAL_TTL),null));
  caps.put("media",media(ds,now));
  caps.put("search",search(ds,snap,now));
  caps.put("vespa",vespa(ds,snap,now));
  caps.put("recording",recording(snap,now));
  DatasetStatus dataset=ds==null?null:new DatasetStatus(ds.id(),ds.version(),ds.origin(),ds.sourceChecksum(),ds.mediaValidation());
  return new SystemStatus(SCHEMA_VERSION,instanceId(),now,dataset,caps);
 }

 /** Server-side guard for a new VESPA job (POST). A CONFIGURED state gets one bounded refresh before rejecting. */
 public void requireVespa(long datasetId) { require(datasetId,"vespa"); }
 public void requireRecording(long datasetId) { require(datasetId,"recording"); }
 private void require(long datasetId,String key) {
  var ds=dataset(datasetId).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Dataset not found"));
  var now=OffsetDateTime.now();
  Capability c=evaluate(key,ds,datasetSnapshot(ds,false),now);
  if(!c.canExecute() && ("CONFIGURED".equals(c.state()) || "UNKNOWN".equals(c.state()))) c=evaluate(key,ds,datasetSnapshot(ds,true),now);
  if(!c.canExecute()) throw new CodedError(HttpStatus.SERVICE_UNAVAILABLE,c.reasonCode()==null?"CAPABILITY_NOT_READY":c.reasonCode(),c.message()==null?"Feature is not ready":c.message());
 }
 private Capability evaluate(String key,DatasetRow ds,Snapshot snap,OffsetDateTime now) {
  return "vespa".equals(key)?vespa(ds,snap,now):recording(snap,now);
 }
 private Snapshot datasetSnapshot(DatasetRow ds,boolean refresh) {
  // Uploaded datasets must be checked against their own metadata; never reuse the default dataset's readiness.
  return ds!=null && "uploads".equals(ds.storageKey())?ai.fetch(refresh,ds.rootRelativePath(),ds.version()):aiSnapshot(refresh);
 }

 // ---------------- AI snapshot cache (single flight) ----------------
 Snapshot aiSnapshot(boolean refresh) {
  var c=cached;
  if(!refresh && fresh(c)) return c;
  if(!refresh && c!=null && aiLock.isLocked()) return c; // a check is running: serve the last known answer
  var requested=OffsetDateTime.now();
  aiLock.lock();
  try {
   c=cached;
   if(!refresh && fresh(c)) return c;
   if(refresh && c!=null && c.refreshed() && !c.fetchedAt().isBefore(requested)) return c; // another refresh just finished
   c=ai.fetch(refresh);
   cached=c; // a failed refresh replaces an older READY: expired readiness is never reused
   return c;
  } finally { aiLock.unlock(); }
 }
 private boolean fresh(Snapshot c) { return c!=null && c.fetchedAt().plus(aiTtl).isAfter(OffsetDateTime.now()); }
 /** Test hook. */
 public void clearCache() { cached=null; }

 // ---------------- capabilities ----------------
 private Capability media(DatasetRow ds,OffsetDateTime now) {
  if(ds==null) return cap("UNKNOWN",false,"DATASET_NOT_SELECTED",now,LOCAL_TTL);
  DatasetFiles source;
  try { source=media.files(ds.storageKey(),ds.rootRelativePath()); }
  catch(IOException e) { return cap("UNAVAILABLE",false,"MEDIA_NOT_SERVED",now,LOCAL_TTL); }
  if(!Files.isDirectory(source.root())) return cap("UNAVAILABLE",false,"MEDIA_ROOT_UNAVAILABLE",now,LOCAL_TTL);
  // Spot check: the first keyframe sample's files (cameras + lidar). Not a full validation.
  var paths=jdbc.sql("""
   SELECT sd.relative_path FROM sample_data sd JOIN sample s ON s.dataset_id=sd.dataset_id AND s.token=sd.sample_token
   WHERE sd.dataset_id=:d AND sd.is_key_frame AND s.id=(SELECT min(id) FROM sample WHERE dataset_id=:d)
   """).param("d",ds.id()).query(String.class).list();
  if(paths.isEmpty()) return cap("UNAVAILABLE",false,"DATA_NOT_READY",now,LOCAL_TTL);
  long missing=paths.stream().filter(p->{ try { source.resolve(p); return false; } catch(IOException e) { return true; } }).count();
  if(missing==paths.size()) return cap("UNAVAILABLE",false,"MEDIA_FILES_MISSING",now,LOCAL_TTL);
  if(missing>0) return cap("CONFIGURED",true,"MEDIA_FILES_MISSING",now,LOCAL_TTL);
  if("VERIFIED".equals(ds.mediaValidation())) return cap("READY",true,null,now,LOCAL_TTL);
  return cap("CONFIGURED",true,"MEDIA_NOT_FULLY_VALIDATED",now,LOCAL_TTL);
 }

 private Capability search(DatasetRow ds,Snapshot snap,OffsetDateTime now) {
  var unreach=unreachable(snap,now); if(unreach!=null) return unreach;
  JsonNode clip=snap.legacy()?null:snap.body().path("clip");
  if(snap.legacy()) {
   boolean ready="ready".equals(snap.body().path("inference").path("clip").asString(""));
   if(!ready) return cap("UNAVAILABLE",false,"MODEL_NOT_READY",snap.fetchedAt(),aiTtl);
  } else {
   if(!"READY".equals(clip.path("state").asString(""))) return cap("UNAVAILABLE",false,text(clip,"reasonCode","MODEL_NOT_READY"),snap.fetchedAt(),aiTtl);
   boolean preprocessOk=false; for(var p:clip.path("imagePreprocess")) preprocessOk|=preprocess.equals(p.asString(""));
   if(!modelName.equals(clip.path("modelName").asString("")) || !preprocessOk) return cap("UNAVAILABLE",false,"MODEL_MISMATCH",snap.fetchedAt(),aiTtl);
  }
  if(ds==null) return cap("CONFIGURED",true,"DATASET_NOT_SELECTED",snap.fetchedAt(),aiTtl);
  long images=jdbc.sql("SELECT count(*) FROM image_embedding WHERE dataset_id=:d AND model_name=:m AND preprocess=:p")
   .param("d",ds.id()).param("m",modelName).param("p",preprocess).query(Long.class).single();
  if(images==0) return cap("UNAVAILABLE",false,"EMBEDDINGS_NOT_READY",snap.fetchedAt(),aiTtl);
  // images>0 is not full coverage; the message says how many images are indexed.
  return new Capability(snap.legacy()?"CONFIGURED":"READY",true,snap.legacy()?"LEGACY_NOT_VERIFIED":null,
   "검색 인덱스 이미지 "+images+"개 (전체 카메라 이미지 대비 범위는 확인하지 않아요)",snap.fetchedAt(),snap.fetchedAt().plus(aiTtl),null);
 }

 private Capability vespa(DatasetRow ds,Snapshot snap,OffsetDateTime now) {
  if(!jobWorker) return cap("UNAVAILABLE",false,"VESPA_WORKER_DISABLED",now,LOCAL_TTL);
  if(ds!=null && "SYNTHETIC".equals(ds.origin())) return cap("UNAVAILABLE",false,"SYNTHETIC_DATASET",now,LOCAL_TTL);
  if(ds!=null && !"uploads".equals(ds.storageKey()) && !vespaVersion.equals(ds.version())) return cap("UNAVAILABLE",false,"DATASET_MISMATCH",now,LOCAL_TTL);
  var unreach=unreachable(snap,now); if(unreach!=null) return unreach;
  if(snap.legacy()) {
   JsonNode inf=snap.body().path("inference");
   String executor=inf.path("vespa_executor").asString("local");
   if(!"configured".equals(inf.path("vespa").asString(""))) return withExecutor(cap("UNAVAILABLE",false,"VESPA_NOT_CONFIGURED",snap.fetchedAt(),aiTtl),executor);
   return withExecutor(cap("CONFIGURED",false,"LEGACY_NOT_VERIFIED",snap.fetchedAt(),aiTtl),executor);
  }
  JsonNode v=snap.body().path("vespa");
  String executor=v.path("executor").isNull()?null:v.path("executor").asString(null);
  String state=v.path("state").asString("UNKNOWN");
  String reason=text(v,"reasonCode",null);
  OffsetDateTime checked=time(v,"checkedAt",snap.fetchedAt()), expires=time(v,"expiresAt",snap.fetchedAt().plus(aiTtl));
  if(ds!=null) {
   String aiVersion=text(v,"datasetVersion",null), aiChecksum=text(v,"metadataChecksum",null);
   if("uploads".equals(ds.storageKey()) && (!ds.rootRelativePath().equals(text(v,"datasetKey",null)) || aiChecksum==null && "READY".equals(state)))
    return withExecutor(cap("UNAVAILABLE",false,"DATASET_MISMATCH",snap.fetchedAt(),aiTtl),executor);
   if(aiVersion!=null && !aiVersion.equals(ds.version())) return withExecutor(cap("UNAVAILABLE",false,"DATASET_MISMATCH",snap.fetchedAt(),aiTtl),executor);
   if(aiChecksum!=null && !aiChecksum.equals(ds.sourceChecksum())) return withExecutor(cap("UNAVAILABLE",false,"DATASET_MISMATCH",snap.fetchedAt(),aiTtl),executor);
  }
  boolean ready="READY".equals(state) && expires.isAfter(now);
  if("READY".equals(state) && !ready) { state="CONFIGURED"; reason="EXECUTOR_NOT_CHECKED"; }
  return new Capability(state,ready,reason,message(reason),checked,expires,executor);
 }

 private Capability recording(Snapshot snap,OffsetDateTime now) {
  if(!recordingWorker) return cap("UNAVAILABLE",false,"RECORDING_WORKER_DISABLED",now,LOCAL_TTL);
  if(!Files.isDirectory(recordingFiles.root())) return cap("UNAVAILABLE",false,"RECORDING_STORAGE_UNAVAILABLE",now,LOCAL_TTL);
  var unreach=unreachable(snap,now); if(unreach!=null) return unreach;
  if(snap.legacy()) {
   boolean configured="configured".equals(snap.body().path("inference").path("recording").asString(""));
   return cap(configured?"CONFIGURED":"UNAVAILABLE",false,configured?"LEGACY_NOT_VERIFIED":"RECORDING_NOT_CONFIGURED",snap.fetchedAt(),aiTtl);
  }
  JsonNode r=snap.body().path("recording");
  String state=r.path("state").asString("UNKNOWN"), reason=text(r,"reasonCode",null);
  if("READY".equals(state) && !recordingSdk.equals(text(r,"sdkVersion",""))) { state="UNAVAILABLE"; reason="RECORDING_SDK_MISMATCH"; }
  OffsetDateTime expires=time(r,"expiresAt",snap.fetchedAt().plus(aiTtl));
  boolean ready="READY".equals(state) && expires.isAfter(now);
  return new Capability(state,ready,reason,message(reason),time(r,"checkedAt",snap.fetchedAt()),expires,null);
 }

 private Capability unreachable(Snapshot snap,OffsetDateTime now) {
  if(snap.reachable()) return null;
  String code=snap.errorCode()==null?"AI_UNREACHABLE":snap.errorCode();
  // Unsupported route = definite; connection/timeout = we do not know the feature state.
  return cap("AI_ENDPOINT_UNSUPPORTED".equals(code)?"UNAVAILABLE":"UNKNOWN",false,code,snap.fetchedAt(),Duration.ofSeconds(5));
 }

 // ---------------- helpers ----------------
 public record DatasetRow(long id,String version,String storageKey,String rootRelativePath,String sourceChecksum,String origin,String mediaValidation) {}
 public Optional<DatasetRow> dataset(long id) {
  // Provenance counts only for the checksum it was recorded with.
  return jdbc.sql("""
   SELECT d.id,d.version,d.storage_key,d.root_relative_path,d.source_checksum,
    CASE WHEN p.metadata_checksum=d.source_checksum THEN p.origin ELSE 'UNKNOWN' END AS origin,
    CASE WHEN p.metadata_checksum=d.source_checksum THEN p.media_validation ELSE 'NOT_CHECKED' END AS media_validation
   FROM dataset d LEFT JOIN dataset_provenance p ON p.dataset_id=d.id WHERE d.id=:id
   """).param("id",id).query(DatasetRow.class).optional();
 }
 private static String text(JsonNode n,String field,String fallback) { var v=n.path(field); return v.isMissingNode()||v.isNull()?fallback:v.asString(fallback); }
 private static OffsetDateTime time(JsonNode n,String field,OffsetDateTime fallback) {
  String s=text(n,field,null);
  try { return s==null?fallback:OffsetDateTime.parse(s); } catch(RuntimeException e) { return fallback; }
 }
 private static Capability cap(String state,boolean can,String reason,OffsetDateTime at,Duration ttl) {
  return new Capability(state,can,reason,message(reason),at,at.plus(ttl),null);
 }
 private static Capability withExecutor(Capability c,String executor) {
  return new Capability(c.state(),c.canExecute(),c.reasonCode(),c.message(),c.checkedAt(),c.expiresAt(),executor);
 }
 static String message(String reason) { return reason==null?null:ReasonMessages.ko(reason); }
}
