package com.example.demo.nuscenes.repository;
import com.example.demo.nuscenes.dto.AutoLabelDtos.*;
import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
@Repository
public class AutoLabelRepository {
 public record Target(long id,long datasetId,String token,String name,String version,String storageKey) {}
 public record Existing(long id,String mappingName,String sceneToken,Long sourceJobId,String referenceFrames) {}
 private final JdbcClient jdbc;
 public AutoLabelRepository(JdbcClient jdbc) { this.jdbc=jdbc; }
 public List<Target> targets(String token,Long dataset) {
  return jdbc.sql("SELECT s.id,s.dataset_id,s.token,s.name,d.version,d.storage_key FROM scene s JOIN dataset d ON d.id=s.dataset_id WHERE s.token=:t AND (CAST(:d AS bigint) IS NULL OR s.dataset_id=:d)").param("t",token).param("d",dataset).query(Target.class).list();
 }
 public List<String> sceneSamples(Target t) { return jdbc.sql("SELECT token FROM sample WHERE dataset_id=:d AND scene_token=:t ORDER BY timestamp_us,token").param("d",t.datasetId()).param("t",t.token()).query(String.class).list(); }
 public Optional<Long> insert(Target t,String key,int mode,String classes,String version,String config,Long sourceJob,String references) {
  return jdbc.sql("""
   INSERT INTO auto_label_job(dataset_id,request_key,target_type,requested_targets,model_version,config_name,model_config,mapping_name,class_names,source_job_id,reference_frames)
   VALUES(:d,:key,'SCENE',jsonb_build_array(CAST(:scene AS text)),:version,'configs/vlm/p_final.yaml',CAST(:config AS jsonb),:mapping,CAST(:classes AS jsonb),:source,CAST(:refs AS jsonb))
   ON CONFLICT(dataset_id,request_key) DO NOTHING RETURNING id
   """).param("d",t.datasetId()).param("key",key).param("scene",t.token()).param("version",version).param("config",config)
    .param("mapping",mode+"class").param("classes",classes).param("source",sourceJob).param("refs",references).query(Long.class).optional();
 }
 public Optional<Existing> findExisting(long dataset,String key) { return jdbc.sql("SELECT id,mapping_name,requested_targets->>0 AS scene_token,source_job_id,reference_frames::text FROM auto_label_job WHERE dataset_id=:d AND request_key=:k").param("d",dataset).param("k",key).query(Existing.class).optional(); }
 public boolean hasReference(long job,String track,String sample) { return jdbc.sql("SELECT EXISTS(SELECT 1 FROM predicted_annotation WHERE job_id=:j AND sample_token=:s AND raw_payload->>'track_id'=:t)").param("j",job).param("s",sample).param("t",track).query(Boolean.class).single(); }
 public Existing existing(long dataset,String key) { return findExisting(dataset,key).orElseThrow(); }
 public void target(long job,long dataset,String token) { jdbc.sql("INSERT INTO auto_label_job_sample(job_id,dataset_id,sample_token) VALUES(:j,:d,:t)").param("j",job).param("d",dataset).param("t",token).update(); }
 public Optional<Work> claim() {
  if(jdbc.sql("SELECT maintenance FROM deployment_control WHERE id=1 FOR UPDATE").query(Boolean.class).single()) return Optional.empty();
  if(jdbc.sql("SELECT EXISTS(SELECT 1 FROM dataset_search_index WHERE status='RUNNING' AND updated_at>now()-interval '10 minutes')").query(Boolean.class).single()) return Optional.empty();
  var pending=jdbc.sql("""
   SELECT j.id,j.dataset_id,s.name AS scene_name,j.mapping_name,j.execution_token,
    CASE WHEN d.storage_key='uploads' THEN d.root_relative_path END AS dataset_key,
    CASE WHEN d.storage_key='uploads' THEN d.version END AS dataset_version,
    (SELECT relative_path FROM auto_label_artifact a WHERE a.job_id=j.source_job_id AND a.artifact_type='FINAL_JSON' ORDER BY a.id LIMIT 1) AS source_artifact_path,
    j.reference_frames::text
   FROM auto_label_job j JOIN scene s ON s.dataset_id=j.dataset_id AND s.token=j.requested_targets->>0
   JOIN dataset d ON d.id=j.dataset_id
   WHERE j.status='PENDING' AND j.target_type='SCENE' AND jsonb_array_length(j.requested_targets)=1
   ORDER BY j.created_at,j.id LIMIT 1 FOR UPDATE OF j SKIP LOCKED
   """).query(Work.class).optional();
  if(pending.isEmpty()) return Optional.empty();
  Work p=pending.get(); UUID token=UUID.randomUUID();
  jdbc.sql("UPDATE auto_label_job SET status='RUNNING',started_at=now(),execution_token=:t WHERE id=:j AND status='PENDING'").param("t",token).param("j",p.id()).update();
  return Optional.of(new Work(p.id(),p.datasetId(),p.sceneName(),p.mappingName(),token,p.datasetKey(),p.datasetVersion(),p.sourceArtifactPath(),p.referenceFrames()));
 }
 public Optional<Work> lock(long job) { return jdbc.sql("SELECT id,dataset_id,'' AS scene_name,mapping_name,execution_token,NULL AS dataset_key,NULL AS dataset_version,NULL AS source_artifact_path,reference_frames::text FROM auto_label_job WHERE id=:j AND status='RUNNING' FOR UPDATE").param("j",job).query(Work.class).optional(); }
 public Set<String> samples(long job) { return new HashSet<>(jdbc.sql("SELECT sample_token FROM auto_label_job_sample WHERE job_id=:j").param("j",job).query(String.class).list()); }
 public void box(Work job,String token,int index,Box b,String raw) {
  jdbc.sql("""
   INSERT INTO predicted_annotation(job_id,dataset_id,sample_token,box_index,detection_name,center_x,center_y,center_z,size_w,size_l,size_h,
    rotation_w,rotation_x,rotation_y,rotation_z,velocity_x,velocity_y,detection_score,attribute_name,raw_payload)
   VALUES(:j,:d,:t,:i,:name,:x,:y,:z,:w,:l,:h,:rw,:rx,:ry,:rz,:vx,:vy,:score,:attr,CAST(:raw AS jsonb))
   """).param("j",job.id()).param("d",job.datasetId()).param("t",token).param("i",index).param("name",b.detectionName())
    .param("x",b.translation().get(0)).param("y",b.translation().get(1)).param("z",b.translation().get(2))
    .param("w",b.size().get(0)).param("l",b.size().get(1)).param("h",b.size().get(2))
    .param("rw",b.rotation().get(0)).param("rx",b.rotation().get(1)).param("ry",b.rotation().get(2)).param("rz",b.rotation().get(3))
    .param("vx",b.velocity().get(0)).param("vy",b.velocity().get(1)).param("score",b.detectionScore()).param("attr",b.attributeName()==null?"":b.attributeName()).param("raw",raw).update();
 }
 public void complete(Work job,AiResponse result,String storageKey) {
  jdbc.sql("UPDATE auto_label_job_sample SET result_received_at=now() WHERE job_id=:j").param("j",job.id()).update();
  jdbc.sql("INSERT INTO auto_label_artifact(job_id,artifact_type,storage_key,relative_path,checksum,content_type) VALUES(:j,'FINAL_JSON',:s,:p,:c,'application/json')")
   .param("j",job.id()).param("s",storageKey).param("p",result.artifactPath()).param("c",result.resultChecksum()).update();
  jdbc.sql("UPDATE auto_label_job SET status='COMPLETED',completed_at=now(),result_checksum=:c WHERE id=:j").param("j",job.id()).param("c",result.resultChecksum()).update();
 }
 public void fail(Work job,String code,String reason) { jdbc.sql("UPDATE auto_label_job SET status='FAILED',completed_at=now(),failure_reason=:r,error_code=:c WHERE id=:j AND status='RUNNING' AND execution_token=:t").param("r",reason).param("c",code).param("j",job.id()).param("t",job.executionToken()).update(); }
 public Results results(long id,JobStatus status) {
  var header=jdbc.sql("SELECT mapping_name,coordinate_frame,score_type FROM auto_label_job WHERE id=:j").param("j",id).query(Header.class).single();
  var boxes=jdbc.sql("SELECT id,sample_token,box_index,detection_name,center_x,center_y,center_z,size_w,size_l,size_h,rotation_w,rotation_x,rotation_y,rotation_z,velocity_x,velocity_y,detection_score,attribute_name,CAST(raw_payload->>'track_id' AS integer) AS track_id FROM predicted_annotation WHERE job_id=:j ORDER BY sample_token,box_index").param("j",id).query(Prediction.class).list();
  var artifacts=jdbc.sql("SELECT id,artifact_type,storage_key,relative_path,checksum,content_type FROM auto_label_artifact WHERE job_id=:j ORDER BY id").param("j",id).query(Artifact.class).list();
  return new Results(id,status.datasetId(),header.mappingName(),header.coordinateFrame(),header.scoreType(),samples(id).stream().sorted().toList(),boxes,artifacts);
 }
 public Optional<JobStatus> status(long id) {
  return jdbc.sql("""
   SELECT j.id AS job_id,j.dataset_id,j.status,j.failure_reason AS error_message,j.created_at,j.started_at,j.completed_at,
    j.requested_targets->>0 AS scene_token,s.id AS scene_id,s.name AS scene_name,CAST(replace(j.mapping_name,'class','') AS integer) AS class_mode,j.mapping_name,j.error_code
   FROM auto_label_job j LEFT JOIN scene s ON s.dataset_id=j.dataset_id AND s.token=j.requested_targets->>0 WHERE j.id=:j
   """).param("j",id).query(JobStatus.class).optional();
 }
}
