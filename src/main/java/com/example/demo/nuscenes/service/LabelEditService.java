package com.example.demo.nuscenes.service;
import com.example.demo.nuscenes.api.CodedError;
import com.example.demo.nuscenes.dto.LabelEditDtos.*;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
/**
 * Rename / delete / revert for GT annotations and VESPA predictions.
 * Original rows are never changed: the effective state lives in label_override and every edit keeps the previous
 * state of each target in label_edit_target. The original rows of the targets are locked (ordered by id) for the
 * whole transaction, so concurrent edits and reverts of the same boxes are serialized.
 */
@Service
public class LabelEditService {
 private static final String ANN="ANNOTATION", PRED="PREDICTION";
 private final JdbcClient jdbc;
 private final TransactionTemplate tx;
 public LabelEditService(JdbcClient jdbc,PlatformTransactionManager manager) { this.jdbc=jdbc; this.tx=new TransactionTemplate(manager); }

 /** A box with its current effective state. base = original class (GT display class or detectionName). */
 record Target(long id,long datasetId,String sampleToken,String instanceToken,String base,String override,boolean deleted) {
  String label() { return override!=null?override:base; }
 }
 record GtRow(long id,long datasetId,String sampleToken,String instanceToken,String categoryName,String overrideLabel,boolean deleted) {
  Target target() { return new Target(id,datasetId,sampleToken,instanceToken,LabelClasses.gtBase(categoryName),overrideLabel,deleted); }
 }
 record PredRow(long id,long datasetId,String sampleToken,String detectionName,String overrideLabel,boolean deleted) {
  Target target() { return new Target(id,datasetId,sampleToken,null,detectionName,overrideLabel,deleted); }
 }
 record GtContext(long sceneId,String sceneToken,long datasetId,String instanceToken) {}
 record PredContext(long jobId,String status,Long sceneId) {}
 record EditRow(long id,long datasetId,long sceneId,Long jobId,String targetType,String action,String scope,String instanceToken,String fromLabel,String toLabel,
   OffsetDateTime createdAt,OffsetDateTime revertedAt,boolean revertible) {}
 record TargetRow(long editId,long targetId,String sampleToken) {}
 record PrevRow(long targetId,String targetType,long datasetId,String prevLabel,boolean prevDeleted) {}

 public EditResult renameAnnotation(long id,String label,String scope) {
  String to=validLabel(label); String sc=validScope(scope,true);
  return tx.execute(s->{
   var ctx=gtContext(id);
   var selected=lockGt(sc.equals("INSTANCE")?instanceIds(ctx):List.of(id)).stream().filter(t->!t.deleted() || t.id()==id).toList();
   var self=selected.stream().filter(t->t.id()==id).findFirst().orElseThrow(()->notFound("Annotation not found"));
   if(self.deleted()) throw new CodedError(HttpStatus.CONFLICT,"TARGET_DELETED","A deleted annotation cannot be renamed");
   var changed=selected.stream().filter(t->!t.label().equals(to)).toList();
   if(changed.isEmpty()) throw new CodedError(HttpStatus.BAD_REQUEST,"SAME_LABEL","The annotation already has this class");
   return new EditResult(apply(ANN,ctx.sceneId(),null,"RENAME",sc,ctx.instanceToken(),self.label(),to,changed));
  });
 }
 public EditResult deleteAnnotation(long id,String scope) {
  String sc=validScope(scope,true);
  return tx.execute(s->{
   var ctx=gtContext(id);
   var selected=lockGt(sc.equals("INSTANCE")?instanceIds(ctx):List.of(id));
   var self=selected.stream().filter(t->t.id()==id).findFirst().orElseThrow(()->notFound("Annotation not found"));
   if(self.deleted()) throw new CodedError(HttpStatus.CONFLICT,"TARGET_DELETED","The annotation is already deleted");
   var live=selected.stream().filter(t->!t.deleted()).toList();
   return new EditResult(apply(ANN,ctx.sceneId(),null,"DELETE",sc,ctx.instanceToken(),self.label(),null,live));
  });
 }
 public EditResult renamePrediction(long id,String label,String scope) {
  String to=validLabel(label); validScope(scope,false);
  return tx.execute(s->{
   var ctx=predContext(id);
   var self=lockPred(id);
   if(self.deleted()) throw new CodedError(HttpStatus.CONFLICT,"TARGET_DELETED","A deleted prediction cannot be renamed");
   if(self.label().equals(to)) throw new CodedError(HttpStatus.BAD_REQUEST,"SAME_LABEL","The prediction already has this class");
   return new EditResult(apply(PRED,ctx.sceneId(),ctx.jobId(),"RENAME","SAMPLE",null,self.label(),to,List.of(self)));
  });
 }
 public EditResult deletePrediction(long id) {
  return tx.execute(s->{
   var ctx=predContext(id);
   var self=lockPred(id);
   if(self.deleted()) throw new CodedError(HttpStatus.CONFLICT,"TARGET_DELETED","The prediction is already deleted");
   return new EditResult(apply(PRED,ctx.sceneId(),ctx.jobId(),"DELETE","SAMPLE",null,self.label(),null,List.of(self)));
  });
 }

 /** GT edits of the scene plus prediction edits of jobId (when given), newest first. */
 public List<LabelEdit> list(long sceneId,Long jobId) {
  if(jdbc.sql("SELECT count(*) FROM scene WHERE id=:s").param("s",sceneId).query(Long.class).single()==0) throw notFound("Scene not found");
  return edits("e.scene_id=:s AND (e.target_type='ANNOTATION' OR e.job_id=CAST(:j AS bigint)) ORDER BY e.id DESC LIMIT 200",Map.of("s",sceneId),jobId);
 }

 public EditResult revert(long editId) {
  return tx.execute(s->{
   var row=jdbc.sql("SELECT id,target_type,reverted_at IS NOT NULL AS reverted FROM label_edit WHERE id=:e FOR UPDATE").param("e",editId)
    .query((rs,i)->new Object[]{rs.getString("target_type"),rs.getBoolean("reverted")}).optional().orElseThrow(()->notFound("Edit not found"));
   String type=(String)row[0];
   if((Boolean)row[1]) throw new CodedError(HttpStatus.CONFLICT,"ALREADY_REVERTED","The edit has already been reverted");
   var prev=jdbc.sql("""
    SELECT t.target_id,t.target_type,e.dataset_id,t.prev_label,t.prev_deleted FROM label_edit_target t JOIN label_edit e ON e.id=t.edit_id
    WHERE t.edit_id=:e ORDER BY t.target_id""").param("e",editId).query(PrevRow.class).list();
   lockOriginals(type,prev.stream().map(PrevRow::targetId).toList());
   boolean later=jdbc.sql("""
    SELECT EXISTS(SELECT 1 FROM label_edit_target t1 JOIN label_edit_target t2 ON t2.target_type=t1.target_type AND t2.target_id=t1.target_id AND t2.edit_id>t1.edit_id
     JOIN label_edit e2 ON e2.id=t2.edit_id AND e2.reverted_at IS NULL WHERE t1.edit_id=:e)""").param("e",editId).query(Boolean.class).single();
   if(later) throw new CodedError(HttpStatus.CONFLICT,"LATER_EDIT_EXISTS","A later edit changed the same box; revert the newest edit first");
   for(var p:prev) write(p.targetType(),p.targetId(),p.datasetId(),p.prevLabel(),p.prevDeleted());
   jdbc.sql("UPDATE label_edit SET reverted_at=now() WHERE id=:e").param("e",editId).update();
   return new EditResult(edit(editId));
  });
 }

 private LabelEdit apply(String type,long sceneId,Long jobId,String action,String scope,String instance,String from,String to,List<Target> targets) {
  long datasetId=targets.getFirst().datasetId();
  long editId=jdbc.sql("""
   INSERT INTO label_edit(dataset_id,scene_id,job_id,target_type,action,scope,instance_token,from_label,to_label)
   VALUES(:d,:s,:j,:t,:a,:sc,:inst,:from,:to) RETURNING id""").param("d",datasetId).param("s",sceneId).param("j",jobId).param("t",type)
   .param("a",action).param("sc",scope).param("inst",instance).param("from",from).param("to",to).query(Long.class).single();
  for(var t:targets) {
   jdbc.sql("INSERT INTO label_edit_target(edit_id,target_type,target_id,sample_token,prev_label,prev_deleted) VALUES(:e,:t,:id,:sample,:pl,:pd)")
    .param("e",editId).param("t",type).param("id",t.id()).param("sample",t.sampleToken()).param("pl",t.override()).param("pd",t.deleted()).update();
   if(action.equals("RENAME")) write(type,t.id(),t.datasetId(),to.equals(t.base())?null:to,false);
   else write(type,t.id(),t.datasetId(),t.override(),true);
  }
  return edit(editId);
 }
 /** Sets the effective state; "no label, not deleted" removes the override row (box back to its original state). */
 private void write(String type,long id,long datasetId,String label,boolean deleted) {
  if(label==null && !deleted) {
   jdbc.sql("DELETE FROM label_override WHERE target_type=:t AND target_id=:id").param("t",type).param("id",id).update();
   return;
  }
  jdbc.sql("""
   INSERT INTO label_override(target_type,target_id,dataset_id,label,deleted) VALUES(:t,:id,:d,:l,:del)
   ON CONFLICT(target_type,target_id) DO UPDATE SET label=EXCLUDED.label,deleted=EXCLUDED.deleted,updated_at=now()""")
   .param("t",type).param("id",id).param("d",datasetId).param("l",label).param("del",deleted).update();
 }

 private GtContext gtContext(long id) {
  return jdbc.sql("""
   SELECT sc.id AS scene_id,sc.token AS scene_token,g.dataset_id,g.instance_token FROM gt_annotation g
   JOIN sample s ON s.dataset_id=g.dataset_id AND s.token=g.sample_token
   JOIN scene sc ON sc.dataset_id=s.dataset_id AND sc.token=s.scene_token WHERE g.id=:id""").param("id",id).query(GtContext.class).optional()
   .orElseThrow(()->notFound("Annotation not found"));
 }
 /** Every annotation of the same instance in the same scene (a nuScenes instance belongs to one scene). */
 private List<Long> instanceIds(GtContext c) {
  return jdbc.sql("""
   SELECT g.id FROM gt_annotation g JOIN sample s ON s.dataset_id=g.dataset_id AND s.token=g.sample_token
   WHERE g.dataset_id=:d AND g.instance_token=:i AND s.scene_token=:sc ORDER BY g.id""").param("d",c.datasetId()).param("i",c.instanceToken())
   .param("sc",c.sceneToken()).query(Long.class).list();
 }
 private List<Target> lockGt(List<Long> ids) {
  lockOriginals(ANN,ids);
  return jdbc.sql("""
   SELECT g.id,g.dataset_id,g.sample_token,g.instance_token,c.name AS category_name,o.label AS override_label,COALESCE(o.deleted,false) AS deleted
   FROM gt_annotation g
   LEFT JOIN object_instance i ON i.dataset_id=g.dataset_id AND i.token=g.instance_token
   LEFT JOIN category c ON c.dataset_id=i.dataset_id AND c.token=i.category_token
   LEFT JOIN label_override o ON o.target_type='ANNOTATION' AND o.target_id=g.id
   WHERE g.id IN (:ids) ORDER BY g.id""").param("ids",ids).query(GtRow.class).list().stream().map(GtRow::target).toList();
 }
 private PredContext predContext(long id) {
  var ctx=jdbc.sql("""
   SELECT j.id AS job_id,j.status,sc.id AS scene_id FROM predicted_annotation p JOIN auto_label_job j ON j.id=p.job_id
   LEFT JOIN scene sc ON sc.dataset_id=j.dataset_id AND sc.token=j.requested_targets->>0 WHERE p.id=:id""").param("id",id).query(PredContext.class).optional()
   .orElseThrow(()->notFound("Prediction not found"));
  if(!"COMPLETED".equals(ctx.status())) throw new CodedError(HttpStatus.CONFLICT,"JOB_NOT_COMPLETED","Only predictions of a completed job can be edited");
  if(ctx.sceneId()==null) throw new CodedError(HttpStatus.CONFLICT,"SCENE_NOT_FOUND","The job's scene no longer exists");
  return ctx;
 }
 private Target lockPred(long id) {
  lockOriginals(PRED,List.of(id));
  return jdbc.sql("""
   SELECT p.id,p.dataset_id,p.sample_token,p.detection_name,o.label AS override_label,COALESCE(o.deleted,false) AS deleted
   FROM predicted_annotation p LEFT JOIN label_override o ON o.target_type='PREDICTION' AND o.target_id=p.id WHERE p.id=:id""")
   .param("id",id).query(PredRow.class).optional().orElseThrow(()->notFound("Prediction not found")).target();
 }
 private void lockOriginals(String type,List<Long> ids) {
  if(ids.isEmpty()) return;
  String table=type.equals(ANN)?"gt_annotation":"predicted_annotation";
  jdbc.sql("SELECT id FROM "+table+" WHERE id IN (:ids) ORDER BY id FOR UPDATE").param("ids",ids).query(Long.class).list();
 }

 private LabelEdit edit(long id) { return edits("e.id=:s",Map.of("s",id),null).getFirst(); }
 private List<LabelEdit> edits(String where,Map<String,Object> params,Long jobId) {
  var rows=jdbc.sql(("""
   SELECT e.id,e.dataset_id,e.scene_id,e.job_id,e.target_type,e.action,e.scope,e.instance_token,e.from_label,e.to_label,e.created_at,e.reverted_at,
    (e.reverted_at IS NULL AND NOT EXISTS(SELECT 1 FROM label_edit_target t1 JOIN label_edit_target t2 ON t2.target_type=t1.target_type AND t2.target_id=t1.target_id
     AND t2.edit_id>t1.edit_id JOIN label_edit e2 ON e2.id=t2.edit_id AND e2.reverted_at IS NULL WHERE t1.edit_id=e.id)) AS revertible
   FROM label_edit e WHERE""")+" "+where).params(params).param("j",jobId).query(EditRow.class).list();
  if(rows.isEmpty()) return List.of();
  Map<Long,List<TargetRow>> targets=new HashMap<>();
  for(var t:jdbc.sql("SELECT edit_id,target_id,sample_token FROM label_edit_target WHERE edit_id IN (:ids) ORDER BY edit_id,target_id")
   .param("ids",rows.stream().map(EditRow::id).toList()).query(TargetRow.class).list()) targets.computeIfAbsent(t.editId(),k->new ArrayList<>()).add(t);
  return rows.stream().map(r->{
   var ts=targets.getOrDefault(r.id(),List.of());
   return new LabelEdit(r.id(),r.datasetId(),r.sceneId(),r.jobId(),r.targetType(),r.action(),r.scope(),r.instanceToken(),r.fromLabel(),r.toLabel(),
    ts.stream().map(TargetRow::targetId).toList(),ts.stream().map(TargetRow::sampleToken).toList(),ts.size(),r.createdAt(),r.revertedAt(),r.revertible());
  }).toList();
 }

 private static String validLabel(String label) {
  if(label==null || !LabelClasses.LABELS.contains(label)) throw new CodedError(HttpStatus.BAD_REQUEST,"INVALID_LABEL","label must be one of "+String.join(", ",LabelClasses.LABELS));
  return label;
 }
 private static String validScope(String scope,boolean instanceAllowed) {
  String s=scope==null || scope.isBlank()?"SAMPLE":scope;
  if(s.equals("SAMPLE") || (instanceAllowed && s.equals("INSTANCE"))) return s;
  throw new CodedError(HttpStatus.BAD_REQUEST,"INVALID_SCOPE",instanceAllowed?"scope must be SAMPLE or INSTANCE":"Predictions are edited per box (scope SAMPLE)");
 }
 private static ResponseStatusException notFound(String m) { return new ResponseStatusException(HttpStatus.NOT_FOUND,m); }
}
