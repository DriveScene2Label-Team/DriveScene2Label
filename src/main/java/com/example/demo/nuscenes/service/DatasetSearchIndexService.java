package com.example.demo.nuscenes.service;

import java.util.*;
import com.example.demo.nuscenes.repository.ImageEmbeddingRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DatasetSearchIndexService {
 public record Status(long datasetId,String status,long indexedImages,long totalImages,String errorMessage,boolean workerEnabled) {}
 public record Work(long datasetId,UUID executionToken) {}
 private record Row(String status,String errorMessage) {}
 private record Pending(long id,ImageEmbeddingRepository.Source source) {}
 private final JdbcClient jdbc; private final ImageEmbeddingService images; private final TransactionTemplate tx;
 private final String model,preprocess; private final boolean enabled,prefetchEnabled,batchEnabled;
 /** Images per heartbeat/yield check. With embedding.index-batch-enabled this is also one AI batch call (C2);
  *  otherwise images are still embedded one request at a time. */
 public static final int BATCH_SIZE=64;
 private static final String CAMERA_FROM="""
  FROM sample_data sd JOIN calibrated_sensor cs ON cs.dataset_id=sd.dataset_id AND cs.token=sd.calibrated_sensor_token
  JOIN sensor s ON s.dataset_id=cs.dataset_id AND s.token=cs.sensor_token
  LEFT JOIN image_embedding e ON e.dataset_id=sd.dataset_id AND e.sample_data_token=sd.token AND e.model_name=:m AND e.preprocess=:p
  WHERE sd.dataset_id=:d AND sd.is_key_frame=true AND s.modality='camera'
  """;
 public DatasetSearchIndexService(JdbcClient jdbc,ImageEmbeddingService images,PlatformTransactionManager manager,
   @Value("${embedding.model-name}") String model,@Value("${embedding.preprocess}") String preprocess,
   @Value("${embedding.index-worker.enabled:true}") boolean enabled,
   @Value("${embedding.index-prefetch-enabled:false}") boolean prefetchEnabled,
   @Value("${embedding.index-batch-enabled:false}") boolean batchEnabled) {
  this.jdbc=jdbc;this.images=images;this.tx=new TransactionTemplate(manager);this.model=model;this.preprocess=preprocess;this.enabled=enabled;this.prefetchEnabled=prefetchEnabled;this.batchEnabled=batchEnabled;
 }
 public Status status(long dataset) {
  if(!jdbc.sql("SELECT EXISTS(SELECT 1 FROM dataset WHERE id=:d)").param("d",dataset).query(Boolean.class).single()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Dataset not found");
  var counts=jdbc.sql("SELECT count(*) AS total,count(e.sample_data_token) AS indexed "+CAMERA_FROM).param("d",dataset).param("m",model).param("p",preprocess).query((rs,n)->new long[]{rs.getLong("total"),rs.getLong("indexed")}).single();
  var row=jdbc.sql("SELECT status,error_message FROM dataset_search_index WHERE dataset_id=:d").param("d",dataset).query(Row.class).optional().orElse(new Row("NOT_STARTED",null));
  String state=counts[0]==0?"EMPTY":counts[0]==counts[1]?"COMPLETED":row.status();
  // A changed model/preprocess needs a new index even if an older index finished.
  if("COMPLETED".equals(state) && counts[0]!=counts[1]) state="NOT_STARTED";
  return new Status(dataset,state,counts[1],counts[0],row.errorMessage(),enabled);
 }
 public Status enqueue(long dataset) {
  var current=status(dataset); if(current.totalImages()==0 || "COMPLETED".equals(current.status())) return current;
  jdbc.sql("""
   INSERT INTO dataset_search_index(dataset_id,status) VALUES(:d,'PENDING')
   ON CONFLICT(dataset_id) DO UPDATE SET status='PENDING',error_message=NULL,updated_at=now()
   WHERE dataset_search_index.status IN ('FAILED','COMPLETED')
    OR (dataset_search_index.status='RUNNING' AND dataset_search_index.updated_at < now()-interval '10 minutes')
   """).param("d",dataset).update();
  return status(dataset);
 }
 public Optional<Work> claim() {
  return tx.execute(transaction->{
   if(jdbc.sql("SELECT maintenance FROM deployment_control WHERE id=1 FOR UPDATE").query(Boolean.class).single()) return Optional.empty();
   if(jdbc.sql("SELECT EXISTS(SELECT 1 FROM auto_label_job WHERE status='RUNNING')").query(Boolean.class).single()) return Optional.empty();
   // Import and upload transactions finish before their new rows become visible here.
   jdbc.sql("INSERT INTO dataset_search_index(dataset_id,status) SELECT id,'PENDING' FROM dataset WHERE storage_key='uploads' ON CONFLICT DO NOTHING").update();
   UUID token=UUID.randomUUID();
   return jdbc.sql("""
    UPDATE dataset_search_index SET status='RUNNING',execution_token=:t,updated_at=now(),error_message=NULL
    WHERE dataset_id=(SELECT dataset_id FROM dataset_search_index WHERE status='PENDING'
     OR (status='RUNNING' AND updated_at < now()-interval '10 minutes') ORDER BY updated_at LIMIT 1 FOR UPDATE SKIP LOCKED)
    RETURNING dataset_id,execution_token
    """).param("t",token).query(Work.class).optional();
  });
 }
 public void process(Work work) {
  long started=System.nanoTime();
  int processed=0;
  String outcome="failed";
  org.slf4j.LoggerFactory.getLogger(getClass()).info("[CLIP_INDEX] dataset={} event=started",work.datasetId());
  try {
   // Keep one claim until the index is done instead of releasing it every batch and waiting for the next tick
   // (2026-11-12 measurement: ~1s scheduler delay x 303 batches). VESPA and indexing share one scheduler thread,
   // so yield only when a label job is actually waiting.
   List<Long> previous=List.of();
   while(true) {
    long queryStarted=System.nanoTime();
    var pending=pending(work.datasetId());
    var ids=pending.stream().map(Pending::id).toList();
    org.slf4j.LoggerFactory.getLogger(getClass()).info("[CLIP_INDEX] dataset={} event=batch_loaded source={} ai={} images={} jdbc_ms={}",work.datasetId(),prefetchEnabled?"pending_batch":"per_image",batchEnabled?"batch":"per_image",pending.size(),(System.nanoTime()-queryStarted)/1_000_000);
    if(pending.isEmpty()) { finish(work,"COMPLETED",null); outcome="completed"; return; }
    // A batch that stored nothing would repeat forever; release it to the normal retry path instead.
    if(ids.equals(previous)) { finish(work,"PENDING",null); outcome="no_progress"; return; }
    // One batch takes seconds, far below the 10-minute stale-claim window.
    if(!heartbeat(work)) { outcome="claim_lost"; return; }
    if(batchEnabled) {
     // C2 (2026-11-18): one AI call per batch (POST /embedding/images) instead of one per image. 5060 Ti 11-17:
     // a 2-crop forward pass ~40.8 ms and HTTP + JSON ~6.0 ms per image. Uses the C1 prefetched sources when on.
     var prefetched=new HashMap<Long,ImageEmbeddingRepository.Source>();
     for(var item:pending) if(item.source()!=null) prefetched.put(item.id(),item.source());
     images.embedBatch(ids,prefetched);
     processed+=pending.size();
    } else for(var item:pending) {
     if(prefetchEnabled) images.embedPending(item.id(),item.source());
     else images.embed(item.id(),false);
     processed++;
    }
    if(labelJobWaiting()) { finish(work,"PENDING",null); outcome="yielded"; return; }
    previous=ids;
   }
  } catch(Exception error) {
   org.slf4j.LoggerFactory.getLogger(getClass()).error("Search indexing failed for dataset {}",work.datasetId(),error);
   finish(work,"FAILED","이미지 검색 준비에 실패했습니다. GPU·AI 서버와 원본 파일 상태를 확인한 뒤 다시 시도해 주세요.");
  } finally {
   org.slf4j.LoggerFactory.getLogger(getClass()).info("[CLIP_INDEX] dataset={} event={} images={} wall_ms={}",work.datasetId(),outcome,processed,(System.nanoTime()-started)/1_000_000);
  }
 }
 private List<Pending> pending(long dataset) {
  String from=CAMERA_FROM;
  String columns="sd.id";
  if(prefetchEnabled) {
   columns+=",sd.dataset_id,sd.token,sd.relative_path,s.modality,d.storage_key,d.root_relative_path";
   from=from.replace("FROM sample_data sd ","FROM sample_data sd JOIN dataset d ON d.id=sd.dataset_id ");
  }
  return jdbc.sql("SELECT "+columns+" "+from+" AND e.sample_data_token IS NULL ORDER BY sd.timestamp_us,sd.id LIMIT "+BATCH_SIZE)
   .param("d",dataset).param("m",model).param("p",preprocess).query((rs,n)->new Pending(rs.getLong("id"),prefetchEnabled?
    new ImageEmbeddingRepository.Source(rs.getLong("dataset_id"),rs.getString("token"),rs.getString("relative_path"),rs.getString("modality"),rs.getString("storage_key"),rs.getString("root_relative_path")):null)).list();
 }
 private boolean labelJobWaiting() { return jdbc.sql("SELECT EXISTS(SELECT 1 FROM auto_label_job WHERE status IN ('PENDING','RUNNING'))").query(Boolean.class).single(); }
 private boolean heartbeat(Work w) { return jdbc.sql("UPDATE dataset_search_index SET updated_at=now() WHERE dataset_id=:d AND execution_token=:t AND status='RUNNING'").param("d",w.datasetId()).param("t",w.executionToken()).update()==1; }
 private void finish(Work w,String state,String error) { jdbc.sql("UPDATE dataset_search_index SET status=:s,error_message=:e,updated_at=now() WHERE dataset_id=:d AND execution_token=:t AND status='RUNNING'").param("s",state).param("e",error).param("d",w.datasetId()).param("t",w.executionToken()).update(); }
}
