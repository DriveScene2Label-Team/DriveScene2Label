package com.example.demo.nuscenes.repository;
import com.example.demo.nuscenes.dto.RecordingDtos.*;
import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
@Repository
public class RecordingRepository {
 public record Live(long id,String status) {}
 public record Content(String status,String relativePath) {}
 private static final String VIEW="""
  SELECT r.id AS recording_id,r.dataset_id,s.id AS scene_id,r.scene_token,s.name AS scene_name,r.job_id,r.status,r.sdk_version,r.export_version,
   CAST(r.metadata AS text) AS metadata,r.size_bytes,r.failure_reason,r.error_code,r.created_at,r.started_at,r.completed_at
  FROM scene_recording r JOIN scene s ON s.dataset_id=r.dataset_id AND s.token=r.scene_token
  """;
 private final JdbcClient jdbc;
 public RecordingRepository(JdbcClient jdbc) { this.jdbc=jdbc; }
 public Optional<JobTarget> job(long dataset,long job) {
  return jdbc.sql("SELECT requested_targets->>0 AS scene_token,target_type,jsonb_array_length(requested_targets) AS targets,status FROM auto_label_job WHERE dataset_id=:d AND id=:j")
   .param("d",dataset).param("j",job).query(JobTarget.class).optional();
 }
 public Optional<Long> insert(long dataset,String scene,Long job,String exportVersion,String sdkVersion) {
  return jdbc.sql("""
   INSERT INTO scene_recording(dataset_id,scene_token,job_id,export_version,sdk_version) VALUES(:d,:s,CAST(:j AS bigint),:e,:v)
   ON CONFLICT(dataset_id,scene_token,(COALESCE(job_id,0)),export_version) WHERE status<>'FAILED' DO NOTHING RETURNING id
   """).param("d",dataset).param("s",scene).param("j",job).param("e",exportVersion).param("v",sdkVersion).query(Long.class).optional();
 }
 public Optional<Live> live(long dataset,String scene,Long job,String exportVersion) {
  return jdbc.sql("SELECT id,status FROM scene_recording WHERE dataset_id=:d AND scene_token=:s AND COALESCE(job_id,0)=COALESCE(CAST(:j AS bigint),0) AND export_version=:e AND status<>'FAILED'")
   .param("d",dataset).param("s",scene).param("j",job).param("e",exportVersion).query(Live.class).optional();
 }
 public Optional<Row> find(long id) { return jdbc.sql(VIEW+" WHERE r.id=:id").param("id",id).query(Row.class).optional(); }
 public List<Row> byScene(long dataset,String scene) { return jdbc.sql(VIEW+" WHERE r.dataset_id=:d AND r.scene_token=:s ORDER BY r.created_at DESC,r.id DESC").param("d",dataset).param("s",scene).query(Row.class).list(); }
 public Optional<Content> content(long id) { return jdbc.sql("SELECT status,relative_path FROM scene_recording WHERE id=:id").param("id",id).query(Content.class).optional(); }
 /** Call inside a transaction: row lock is held until commit. */
 public Optional<Work> claim() {
  if(jdbc.sql("SELECT maintenance FROM deployment_control WHERE id=1 FOR SHARE").query(Boolean.class).single()) return Optional.empty();
  var pending=jdbc.sql("SELECT id,dataset_id,scene_token,job_id,sdk_version,export_version,execution_token FROM scene_recording WHERE status='PENDING' ORDER BY created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED")
   .query(Work.class).optional();
  if(pending.isEmpty()) return Optional.empty();
  Work p=pending.get(); UUID token=UUID.randomUUID();
  jdbc.sql("UPDATE scene_recording SET status='RUNNING',started_at=now(),execution_token=:t WHERE id=:id AND status='PENDING'").param("t",token).param("id",p.id()).update();
  return Optional.of(new Work(p.id(),p.datasetId(),p.sceneToken(),p.jobId(),p.sdkVersion(),p.exportVersion(),token));
 }
 public Optional<String> sceneName(long dataset,String scene) { return jdbc.sql("SELECT name FROM scene WHERE dataset_id=:d AND token=:s").param("d",dataset).param("s",scene).query(String.class).optional(); }
 public List<SceneSample> samples(long dataset,String scene) {
  return jdbc.sql("SELECT token,timestamp_us FROM sample WHERE dataset_id=:d AND scene_token=:s ORDER BY timestamp_us,token").param("d",dataset).param("s",scene).query(SceneSample.class).list();
 }
 /** Keyframe LIDAR_TOP per sample with its own calibration and ego pose; earliest first if a sample has several. */
 public List<LidarRow> lidar(long dataset,String scene) {
  return jdbc.sql("""
   SELECT sd.sample_token,sd.relative_path,
    cs.translation_x AS sensor_tx,cs.translation_y AS sensor_ty,cs.translation_z AS sensor_tz,cs.rotation_w AS sensor_rw,cs.rotation_x AS sensor_rx,cs.rotation_y AS sensor_ry,cs.rotation_z AS sensor_rz,
    ep.translation_x AS ego_tx,ep.translation_y AS ego_ty,ep.translation_z AS ego_tz,ep.rotation_w AS ego_rw,ep.rotation_x AS ego_rx,ep.rotation_y AS ego_ry,ep.rotation_z AS ego_rz
   FROM sample_data sd
   JOIN sample sa ON sa.dataset_id=sd.dataset_id AND sa.token=sd.sample_token
   JOIN calibrated_sensor cs ON cs.dataset_id=sd.dataset_id AND cs.token=sd.calibrated_sensor_token
   JOIN sensor se ON se.dataset_id=cs.dataset_id AND se.token=cs.sensor_token
   JOIN ego_pose ep ON ep.dataset_id=sd.dataset_id AND ep.token=sd.ego_pose_token
   WHERE sd.dataset_id=:d AND sa.scene_token=:s AND sd.is_key_frame AND se.channel='LIDAR_TOP'
   ORDER BY sd.sample_token,sd.timestamp_us,sd.token
   """).param("d",dataset).param("s",scene).query(LidarRow.class).list();
 }
 /** Same order as /api/auto-label/jobs/{id}/results within a sample: box_index. */
 public List<PredictionRow> predictions(long dataset,long job) {
  return jdbc.sql("""
   SELECT id,sample_token,detection_name,center_x,center_y,center_z,size_w,size_l,size_h,rotation_w,rotation_x,rotation_y,rotation_z
   FROM predicted_annotation WHERE dataset_id=:d AND job_id=:j ORDER BY sample_token,box_index
   """).param("d",dataset).param("j",job).query(PredictionRow.class).list();
 }
 public int ready(Work w,String path,long size,String checksum,String sdkVersion,String metadata) {
  return jdbc.sql("""
   UPDATE scene_recording SET status='READY',completed_at=now(),relative_path=:p,size_bytes=:z,checksum=:c,sdk_version=:v,metadata=CAST(:m AS jsonb)
   WHERE id=:id AND status='RUNNING' AND execution_token=:t
   """).param("p",path).param("z",size).param("c",checksum).param("v",sdkVersion).param("m",metadata).param("id",w.id()).param("t",w.executionToken()).update();
 }
 public int fail(Work w,String code,String reason) {
  return jdbc.sql("UPDATE scene_recording SET status='FAILED',completed_at=now(),failure_reason=:r,error_code=:c WHERE id=:id AND status='RUNNING' AND execution_token=:t")
   .param("r",reason).param("c",code).param("id",w.id()).param("t",w.executionToken()).update();
 }
 /** Conditional: only the same READY row/path. Clears READY-only columns as the FAILED state requires. */
 public int markFileMissing(long id,String path) {
  return jdbc.sql("""
   UPDATE scene_recording SET status='FAILED',completed_at=now(),failure_reason='Recording file missing on server',error_code='RECORDING_FILE_MISSING',
    relative_path=NULL,size_bytes=NULL,checksum=NULL,metadata=NULL WHERE id=:id AND status='READY' AND relative_path=:p
   """).param("id",id).param("p",path).update();
 }
}
