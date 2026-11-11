package com.example.demo.nuscenes.service;

import java.util.*;
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
 private final JdbcClient jdbc; private final ImageEmbeddingService images; private final TransactionTemplate tx;
 private final String model,preprocess; private final boolean enabled;
 private static final String CAMERA_FROM="""
  FROM sample_data sd JOIN calibrated_sensor cs ON cs.dataset_id=sd.dataset_id AND cs.token=sd.calibrated_sensor_token
  JOIN sensor s ON s.dataset_id=cs.dataset_id AND s.token=cs.sensor_token
  LEFT JOIN image_embedding e ON e.dataset_id=sd.dataset_id AND e.sample_data_token=sd.token AND e.model_name=:m AND e.preprocess=:p
  WHERE sd.dataset_id=:d AND sd.is_key_frame=true AND s.modality='camera'
  """;
 public DatasetSearchIndexService(JdbcClient jdbc,ImageEmbeddingService images,PlatformTransactionManager manager,
   @Value("${embedding.model-name}") String model,@Value("${embedding.preprocess}") String preprocess,
   @Value("${embedding.index-worker.enabled:true}") boolean enabled) {
  this.jdbc=jdbc;this.images=images;this.tx=new TransactionTemplate(manager);this.model=model;this.preprocess=preprocess;this.enabled=enabled;
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
  try {
   // Yield between small batches; VESPA and indexing share the same scheduler in this local deployment.
   var pending=jdbc.sql("SELECT sd.id "+CAMERA_FROM+" AND e.sample_data_token IS NULL ORDER BY sd.timestamp_us,sd.id LIMIT 8")
    .param("d",work.datasetId()).param("m",model).param("p",preprocess).query(Long.class).list();
   for(long id:pending) {
    if(!heartbeat(work)) return;
    images.embed(id,false);
   }
   var done=status(work.datasetId());
   finish(work,done.indexedImages()==done.totalImages()?"COMPLETED":"PENDING",null);
  } catch(Exception error) {
   org.slf4j.LoggerFactory.getLogger(getClass()).error("Search indexing failed for dataset {}",work.datasetId(),error);
   finish(work,"FAILED","이미지 검색 준비에 실패했습니다. GPU·AI 서버와 원본 파일 상태를 확인한 뒤 다시 시도해 주세요.");
  }
 }
 private boolean heartbeat(Work w) { return jdbc.sql("UPDATE dataset_search_index SET updated_at=now() WHERE dataset_id=:d AND execution_token=:t AND status='RUNNING'").param("d",w.datasetId()).param("t",w.executionToken()).update()==1; }
 private void finish(Work w,String state,String error) { jdbc.sql("UPDATE dataset_search_index SET status=:s,error_message=:e,updated_at=now() WHERE dataset_id=:d AND execution_token=:t AND status='RUNNING'").param("s",state).param("e",error).param("d",w.datasetId()).param("t",w.executionToken()).update(); }
}
