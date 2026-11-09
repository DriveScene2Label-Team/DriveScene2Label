package com.example.demo.labels;

import com.example.demo.nuscenes.service.AutoLabelService;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;
import static com.example.demo.labels.LabelDtos.*;

@Service
@Transactional(readOnly=true)
public class LabelService {
 private static final Set<String> CLASSES=Set.of("vehicle","car","truck","bus","trailer","construction_vehicle","pedestrian","motorcycle","bicycle");
 private static final int MAX_BYTES=20*1024*1024;
 private final LabelDocumentRepository documents;
 private final LabelRevisionRepository revisions;
 private final AutoLabelService jobs;
 private final ObjectMapper json;
 private final JdbcClient jdbc;
 public LabelService(LabelDocumentRepository documents,LabelRevisionRepository revisions,AutoLabelService jobs,ObjectMapper json,JdbcClient jdbc) {
  this.documents=documents;this.revisions=revisions;this.jobs=jobs;this.json=json;this.jdbc=jdbc;
 }
 public List<Summary> list(int page) {
  if(page<0) throw bad("page must be non-negative");
  return documents.findAllByOrderByCreatedAtDescIdDesc(PageRequest.of(page,50));
 }
 public Detail get(long id,Integer number) {
  var document=document(id);
  return detail(document,number==null?document.headRevision:number);
 }
 public List<Revision> history(long id) {
  document(id);
  return revisions.findByDocumentIdOrderByNumberDesc(id);
 }
 public String original(long id) { return document(id).originalText; }
 @Transactional
 public Detail upload(String filename,byte[] bytes,Long datasetId) {
  if(bytes.length==0 || bytes.length>MAX_BYTES) throw bad("라벨 JSON은 20MB 이하의 비어 있지 않은 파일이어야 합니다.");
  String original;
  try { original=StandardCharsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(bytes)).toString(); }
  catch(java.nio.charset.CharacterCodingException e) { throw bad("UTF-8로 저장한 라벨 JSON 파일을 선택해 주세요."); }
  JsonNode data;
  try { data=json.readTree(original); }
  catch(RuntimeException e) { throw bad("올바른 UTF-8 라벨 JSON 파일을 선택해 주세요."); }
  var normalized=validate(data,datasetId);
  return create(safeName(filename),datasetId,null,"UPLOAD",original,normalized);
 }
 @Transactional
 public Detail fromJob(long jobId) {
  jdbc.sql("SELECT id FROM auto_label_job WHERE id=:id FOR UPDATE").param("id",jobId).query(Long.class).optional()
   .orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"자동 라벨 작업을 찾을 수 없습니다."));
  var existing=documents.findBySourceJobId(jobId);
  if(existing.isPresent()) return detail(existing.get(),existing.get().headRevision);
  var result=jobs.results(jobId);
  var root=json.createObjectNode();
  root.put("coordinate_frame","WORLD"); root.put("mapping_name",result.mappingName()); root.put("score_type",result.scoreType());
  var results=root.putObject("results");
  for(String token:result.sampleTokens()) results.putArray(token);
  for(var box:result.boxes()) {
   var item=((tools.jackson.databind.node.ArrayNode)results.get(box.sampleToken())).addObject();
   item.put("sample_token",box.sampleToken()); item.put("detection_name",box.detectionName()); item.put("detection_score",box.detectionScore()); item.put("attribute_name",box.attributeName());
   item.putArray("translation").add(box.centerX()).add(box.centerY()).add(box.centerZ());
   item.putArray("size").add(box.sizeW()).add(box.sizeL()).add(box.sizeH());
   item.putArray("rotation").add(box.rotationW()).add(box.rotationX()).add(box.rotationY()).add(box.rotationZ());
   item.putArray("velocity").add(box.velocityX()).add(box.velocityY());
  }
  return create("auto-label-"+jobId+".json",result.datasetId(),jobId,"AUTO_LABEL",json.writeValueAsString(root),root);
 }
 @Transactional
 public Detail save(long id,Save request) {
  var document=document(id);
  if(document.version!=request.expectedVersion()) throw conflict();
  var data=validate(request.data(),document.datasetId);
  // Keep every frame, including frames whose last box was removed.
  var baseline=json.readTree(revision(id,0).payload);
  if(!data.path("results").propertyNames().equals(baseline.path("results").propertyNames())) throw bad("프레임 목록은 원본과 같아야 합니다. 박스를 모두 지울 때에도 빈 배열을 유지해 주세요.");
  document.headRevision++;
  documents.saveAndFlush(document); // @Version rejects simultaneous saves; the whole transaction rolls back.
  append(document,data,request.note()==null?"":request.note().strip());
  return detail(document,document.headRevision);
 }
 private Detail create(String name,Long datasetId,Long jobId,String source,String original,ObjectNode data) {
  var document=new LabelDocument();
  document.name=name; document.datasetId=datasetId; document.sourceJobId=jobId; document.sourceType=source;
  document.originalText=original; document.createdAt=OffsetDateTime.now();
  documents.saveAndFlush(document);
  append(document,data,"원본");
  return detail(document,0);
 }
 private void append(LabelDocument document,JsonNode data,String note) {
  var revision=new LabelRevision(); revision.document=document; revision.number=document.headRevision;
  revision.payload=json.writeValueAsString(data); revision.note=note; revision.createdAt=OffsetDateTime.now();
  revisions.saveAndFlush(revision);
 }
 private ObjectNode validate(JsonNode input,Long datasetId) {
  if(input==null || !input.isObject() || !input.path("results").isObject() || input.path("results").isEmpty()) throw bad("nuScenes/VESPA 형식의 results 객체가 필요합니다.");
  if(json.writeValueAsBytes(input).length>MAX_BYTES) throw bad("라벨 데이터가 20MB를 초과했습니다.");
  var root=(ObjectNode)input.deepCopy();
  if(root.has("coordinate_frame") && !"WORLD".equals(root.path("coordinate_frame").asText())) throw bad("WORLD 좌표계의 3D 라벨만 지원합니다.");
  root.put("coordinate_frame","WORLD");
  Set<String> samples=null;
  if(datasetId!=null) {
   if(!jdbc.sql("SELECT EXISTS(SELECT 1 FROM dataset WHERE id=:id)").param("id",datasetId).query(Boolean.class).single()) throw bad("데이터셋을 찾을 수 없습니다.");
   samples=new HashSet<>(jdbc.sql("SELECT token FROM sample WHERE dataset_id=:id").param("id",datasetId).query(String.class).list());
  }
  int count=0;
  for(String token:root.path("results").propertyNames()) {
   if(token.isBlank() || token.length()>128 || samples!=null && !samples.contains(token)) throw bad("라벨의 sample_token이 선택한 데이터셋과 맞지 않습니다.");
   var boxes=root.path("results").get(token);
   if(!boxes.isArray()) throw bad("각 프레임의 라벨은 배열이어야 합니다.");
   for(var value:boxes) {
    if(++count>100000 || !value.isObject()) throw bad("잘못된 박스 또는 너무 많은 박스입니다.");
    var box=(ObjectNode)value;
    if(box.has("sample_token") && !token.equals(box.path("sample_token").asText())) throw bad("박스와 프레임의 sample_token이 다릅니다.");
    box.put("sample_token",token);
    if(!CLASSES.contains(box.path("detection_name").asText())) throw bad("지원하지 않는 라벨 클래스입니다.");
    numbers(box.path("translation"),3,"translation"); numbers(box.path("size"),3,"size"); numbers(box.path("rotation"),4,"rotation");
    for(var size:box.path("size")) if(size.asDouble()<=0) throw bad("박스 크기는 0보다 커야 합니다.");
    double norm=0; for(var component:box.path("rotation")) norm+=component.asDouble()*component.asDouble();
    if(Math.abs(norm-1)>0.001) throw bad("회전 quaternion은 정규화되어야 합니다.");
    if(!box.has("velocity")) box.putArray("velocity").add(0).add(0);
    numbers(box.path("velocity"),2,"velocity");
    if(!box.has("detection_score")) box.put("detection_score",1.0);
    var score=box.path("detection_score");
    if(!score.isNumber() || !Double.isFinite(score.asDouble()) || score.asDouble()<0 || score.asDouble()>1) throw bad("detection_score는 0부터 1 사이여야 합니다.");
    if(!box.has("attribute_name")) box.put("attribute_name","");
    if(!box.path("attribute_name").isTextual() || box.path("attribute_name").asText().length()>255) throw bad("attribute_name을 확인해 주세요.");
   }
  }
  return root;
 }
 private static void numbers(JsonNode values,int length,String field) {
  if(!values.isArray() || values.size()!=length) throw bad(field+" 배열 길이가 올바르지 않습니다.");
  for(var value:values) if(!value.isNumber() || !Double.isFinite(value.asDouble())) throw bad(field+"에는 유한한 숫자만 입력할 수 있습니다.");
 }
 private Detail detail(LabelDocument document,int number) { return new Detail(summary(document),number,json.readTree(revision(document.id,number).payload)); }
 private Summary summary(LabelDocument d) { return new Summary(d.id,d.name,d.datasetId,d.sourceJobId,d.sourceType,d.headRevision,d.version,d.createdAt); }
 private LabelDocument document(long id) { return documents.findById(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"라벨 문서를 찾을 수 없습니다.")); }
 private LabelRevision revision(long id,int number) { return revisions.findByDocumentIdAndNumber(id,number).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"저장 버전을 찾을 수 없습니다.")); }
 private static String safeName(String filename) {
  String name=filename==null?"labels.json":filename.replace('\\','/');
  name=name.substring(name.lastIndexOf('/')+1).replaceAll("[\\p{Cntrl}]","").strip();
  return name.isBlank()?"labels.json":name.substring(0,Math.min(255,name.length()));
 }
 private static ResponseStatusException bad(String text) { return new ResponseStatusException(HttpStatus.BAD_REQUEST,text); }
 private static ResponseStatusException conflict() { return new ResponseStatusException(HttpStatus.CONFLICT,"다른 창에서 수정본이 저장되었습니다. 최신 버전을 다시 열어 주세요."); }
}
