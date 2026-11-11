package com.example.demo.nuscenes.service;
import com.example.demo.nuscenes.api.CodedError;
import com.example.demo.nuscenes.domain.Scene;
import com.example.demo.nuscenes.dto.GtAnnotationView;
import com.example.demo.nuscenes.dto.RecordingDtos.*;
import com.example.demo.nuscenes.repository.*;
import com.example.demo.nuscenes.storage.RecordingFiles;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.Collectors;
import tools.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
/** Recording lifecycle (docs/rerun-recording.md). Never touches auto_label_job rows; the AI call runs outside any DB transaction. */
@Service
public class RecordingService {
 /** Short, user-visible failure reason (stored as failure_reason). */
 public static final class Invalid extends RuntimeException {
  private final String code;
  public Invalid(String message) { this("RECORDING_INVALID_RESULT",message); }
  public Invalid(String code,String message) { super(message); this.code=code; }
  public String code() { return code; }
 }
 private final RecordingRepository repo;
 private final SystemStatusService readiness;
 private final GtAnnotationViewRepository gt;
 private final SceneRepository scenes;
 private final RecordingFiles files;
 private final ObjectMapper json;
 private final TransactionTemplate tx;
 private final String sdkVersion,exportVersion;
 public RecordingService(RecordingRepository repo,SystemStatusService readiness,GtAnnotationViewRepository gt,SceneRepository scenes,RecordingFiles files,ObjectMapper json,PlatformTransactionManager manager,
   @Value("${recording.sdk-version:0.38.1}") String sdkVersion,@Value("${recording.export-version:ds2l-rrd-v3}") String exportVersion) {
  this.repo=repo;this.readiness=readiness;this.gt=gt;this.scenes=scenes;this.files=files;this.json=json;this.tx=new TransactionTemplate(manager);this.sdkVersion=sdkVersion;this.exportVersion=exportVersion;
 }
 public Created create(long sceneId,Long jobId) {
  if(jobId!=null && jobId<=0) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"jobId must be a positive job ID");
  Scene target=scene(sceneId);
  // 1) Reuse a live recording (also while the AI is down). A READY row whose file is confirmed gone is released.
  var reused=tx.execute(status->{
   Scene scene=scene(sceneId);
   if(jobId!=null) {
    var job=repo.job(scene.datasetId(),jobId).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Job not found in this dataset"));
    if(!"SCENE".equals(job.targetType()) || job.targets()!=1 || !scene.token().equals(job.sceneToken())) throw new ResponseStatusException(HttpStatus.CONFLICT,"Job targets another scene");
    if(!"COMPLETED".equals(job.status())) throw new ResponseStatusException(HttpStatus.CONFLICT,"Job has not completed successfully");
   }
   var live=repo.live(scene.datasetId(),scene.token(),jobId,exportVersion);
   if(live.isPresent() && !fileLost(live.get().id())) return new Created(live.get().id(),live.get().status(),true);
   return null;
  });
  if(reused!=null) return reused;
  // 2) New export only: server-side readiness check outside any transaction, then insert.
  readiness.requireRecording(target.datasetId());
  return insert(target,jobId);
 }
 /**
  * True only when the recording root is readable and the READY file is confirmed absent; the row is then moved to
  * FAILED(RECORDING_FILE_MISSING) so the reuse index frees it. An unreadable root (e.g. volume not mounted) is not loss.
  */
 boolean fileLost(long id) {
  var row=repo.content(id).orElse(null);
  if(row==null || !"READY".equals(row.status()) || row.relativePath()==null) return false;
  Path root=files.root();
  if(!Files.isDirectory(root) || !Files.isReadable(root)) return false;
  Path candidate=root.resolve(row.relativePath()).normalize();
  if(!candidate.startsWith(root) || !Files.notExists(candidate)) return false;
  if(repo.markFileMissing(id,row.relativePath())==1) org.slf4j.LoggerFactory.getLogger(getClass()).warn("[RERUN] recording={} READY file {} is missing; marked FAILED",id,row.relativePath());
  return true;
 }
 private Created insert(Scene scene,Long jobId) {
  return tx.execute(status->{
   // A concurrent live row can turn FAILED between the conflict and the lookup; retry the insert in that case.
   for(int attempt=0;attempt<3;attempt++) {
    var inserted=repo.insert(scene.datasetId(),scene.token(),jobId,exportVersion,sdkVersion);
    if(inserted.isPresent()) return new Created(inserted.get(),"PENDING",false);
    var live=repo.live(scene.datasetId(),scene.token(),jobId,exportVersion);
    if(live.isPresent()) return new Created(live.get().id(),live.get().status(),true);
   }
   throw new ResponseStatusException(HttpStatus.CONFLICT,"Recording is changing state; retry");
  });
 }
 public List<Recording> list(long sceneId) {
  Scene scene=scene(sceneId);
  return repo.byScene(scene.datasetId(),scene.token()).stream().map(r->view(r,false)).toList();
 }
 public Recording get(long id) { return view(repo.find(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Recording not found")),true); }
 public Path content(long id) {
  var row=repo.content(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Recording not found"));
  if(!"READY".equals(row.status())) throw new ResponseStatusException(HttpStatus.CONFLICT,"Recording is not ready");
  try { return files.resolve(row.relativePath()); }
  catch(IOException e) {
   if(fileLost(id)) throw new CodedError(HttpStatus.NOT_FOUND,"RECORDING_FILE_MISSING","Recording file is missing; create the recording again");
   Path root=files.root();
   if(!Files.isDirectory(root) || !Files.isReadable(root)) throw new CodedError(HttpStatus.SERVICE_UNAVAILABLE,"RECORDING_STORAGE_UNAVAILABLE","Recording storage is not readable right now");
   throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Recording file unavailable"); // unsafe/invalid path: never served
  }
 }
 private Scene scene(long id) { return scenes.findById(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Scene not found")); }
 private Recording view(Row r,boolean detail) {
  Metadata m=r.metadata()==null?null:json.readValue(r.metadata(),Metadata.class);
  boolean ready="READY".equals(r.status()) && m!=null;
  List<SampleMap> samples=!detail?null:ready && m.samples()!=null?m.samples():List.of();
  return new Recording(r.recordingId(),r.datasetId(),r.sceneId(),r.sceneToken(),r.sceneName(),r.jobId(),r.status(),r.sdkVersion(),r.exportVersion(),"WORLD",
   ready?m.applicationId():null,ready?m.rerunRecordingId():null,ready?m.timeline():null,ready?m.timeTimeline():null,ready?m.entities():null,samples,
   ready?"/api/recordings/"+r.recordingId()+"/content":null,ready?r.sizeBytes():null,r.failureReason(),r.errorCode(),r.createdAt(),r.startedAt(),r.completedAt());
 }

 public Optional<Work> claim() { return tx.execute(s->repo.claim()); }
 /** Builds the AI request from Spring's DB only: keyframe samples by timestamp, per-sample LIDAR_TOP, GT by token, predictions by box_index. */
 public AiRequest request(Work w) {
  String sceneName=repo.sceneName(w.datasetId(),w.sceneToken()).orElseThrow(()->new Invalid("DATA_NOT_READY","Scene no longer exists"));
  var samples=repo.samples(w.datasetId(),w.sceneToken());
  if(samples.isEmpty()) throw new Invalid("DATA_NOT_READY","Scene has no samples");
  Map<String,LidarRow> lidar=new HashMap<>();
  for(var row:repo.lidar(w.datasetId(),w.sceneToken())) lidar.putIfAbsent(row.sampleToken(),row);
  Map<String,List<AiGt>> boxes=gt.byScene(w.datasetId(),w.sceneToken()).stream()
   .collect(Collectors.groupingBy(GtAnnotationView::sampleToken,LinkedHashMap::new,Collectors.mapping(RecordingService::gt,Collectors.toList())));
  Map<String,List<AiPrediction>> predictions=w.jobId()==null?Map.of():repo.predictions(w.datasetId(),w.jobId()).stream()
   .collect(Collectors.groupingBy(PredictionRow::sampleToken,LinkedHashMap::new,Collectors.mapping(RecordingService::prediction,Collectors.toList())));
  List<AiSample> out=new ArrayList<>();
  for(int i=0;i<samples.size();i++) {
   var s=samples.get(i);
   out.add(new AiSample(i,s.token(),s.timestampUs(),lidar(lidar.get(s.token())),boxes.getOrDefault(s.token(),List.of()),predictions.getOrDefault(s.token(),List.of())));
  }
  var dataset=readiness.dataset(w.datasetId()).orElseThrow(()->new Invalid("DATA_NOT_READY","Dataset no longer exists"));
  boolean uploaded="uploads".equals(dataset.storageKey());
  return new AiRequest(w.id(),w.executionToken(),sceneName,w.sceneToken(),w.jobId(),out,
    uploaded?dataset.rootRelativePath():null,uploaded?dataset.version():null);
 }
 /** Validates the AI result against the request and the file on disk, then stores READY only if this execution still owns the row. */
 public void complete(Work w,AiRequest req,AiResponse r) {
  if(r==null || r.recordingId()==null || r.recordingId()!=w.id() || !w.executionToken().equals(r.executionToken())) throw new Invalid("AI response does not match this recording execution");
  if(!w.sdkVersion().equals(r.sdkVersion())) throw new Invalid("Rerun SDK version mismatch (expected "+w.sdkVersion()+")");
  if(!w.exportVersion().equals(r.exportVersion())) throw new Invalid("Export version mismatch (expected "+w.exportVersion()+")");
  if(blank(r.applicationId()) || blank(r.rerunRecordingId()) || blank(r.timeline()) || blank(r.timeTimeline()) || r.entities()==null
    || blank(r.entities().lidar()) || blank(r.entities().ego()) || blank(r.entities().gt()) || (w.jobId()!=null && blank(r.entities().prediction()))) throw new Invalid("AI response is missing timeline/entity metadata");
  if(r.checksum()==null || !r.checksum().matches("[0-9a-f]{64}") || r.sizeBytes()==null || r.sizeBytes()<=0) throw new Invalid("AI response has invalid checksum/size");
  String path=r.relativePath();
  if(path==null || path.isBlank() || path.startsWith("/") || path.contains("..") || path.contains("\\") || path.contains(":") || !path.endsWith(".rrd")) throw new Invalid("AI response has an unsafe recording path");
  if(r.samples()==null || r.samples().size()!=req.samples().size()) throw new Invalid("AI response sample count differs from request");
  List<SampleMap> mapping=new ArrayList<>();
  for(int i=0;i<req.samples().size();i++) {
   AiSample q=req.samples().get(i); AiSampleResult a=r.samples().get(i);
   if(a==null || a.index()==null || a.index()!=i || !q.sampleToken().equals(a.sampleToken())) throw new Invalid("AI response sample order differs at index "+i);
   if(a.gtBoxes()==null || a.gtBoxes()!=q.gt().size() || a.predictionBoxes()==null || a.predictionBoxes()!=q.predictions().size()) throw new Invalid("AI response box count differs at index "+i);
   if(a.lidarPoints()==null || a.lidarPoints()<0 || (q.lidar()==null && a.lidarPoints()!=0)) throw new Invalid("AI response lidar point count is invalid at index "+i);
   mapping.add(new SampleMap(i,q.sampleToken(),q.timestampUs(),a.lidarPoints(),q.gt().stream().map(AiGt::id).toList(),q.predictions().stream().map(AiPrediction::id).toList()));
  }
  Path file;
  try { file=files.resolve(path); } catch(IOException e) { throw new Invalid("RECORDING_FILE_MISSING","Recording file is missing or outside the recording root"); }
  try { if(Files.size(file)!=r.sizeBytes() || !sha256(file).equals(r.checksum())) throw new Invalid("Recording file size/checksum does not match"); }
  catch(IOException e) { throw new Invalid("Recording file cannot be read"); }
  var e=r.entities();
  String metadata=json.writeValueAsString(new Metadata(r.applicationId(),r.rerunRecordingId(),r.timeline(),r.timeTimeline(),
   new Entities(e.lidar(),e.ego(),e.gt(),w.jobId()==null?null:e.prediction()),mapping));
  if(repo.ready(w,path,r.sizeBytes(),r.checksum(),r.sdkVersion(),metadata)!=1) throw new IllegalStateException("Recording is no longer running with this execution");
 }
 public void fail(Work w,String code,String reason) { repo.fail(w,code,reason.length()>300?reason.substring(0,300):reason); }

 private static AiLidar lidar(LidarRow l) {
  if(l==null) return null;
  return new AiLidar(l.relativePath(),List.of(l.sensorTx(),l.sensorTy(),l.sensorTz()),List.of(l.sensorRw(),l.sensorRx(),l.sensorRy(),l.sensorRz()),
   List.of(l.egoTx(),l.egoTy(),l.egoTz()),List.of(l.egoRw(),l.egoRx(),l.egoRy(),l.egoRz()));
 }
 private static AiGt gt(GtAnnotationView g) {
  return new AiGt(g.id(),g.categoryName(),List.of(g.centerX(),g.centerY(),g.centerZ()),List.of(g.sizeW(),g.sizeL(),g.sizeH()),List.of(g.rotationW(),g.rotationX(),g.rotationY(),g.rotationZ()));
 }
 private static AiPrediction prediction(PredictionRow p) {
  return new AiPrediction(p.id(),p.detectionName(),List.of(p.centerX(),p.centerY(),p.centerZ()),List.of(p.sizeW(),p.sizeL(),p.sizeH()),List.of(p.rotationW(),p.rotationX(),p.rotationY(),p.rotationZ()));
 }
 private static boolean blank(String s) { return s==null || s.isBlank(); }
 private static String sha256(Path file) throws IOException {
  try(InputStream in=Files.newInputStream(file)) {
   var digest=MessageDigest.getInstance("SHA-256"); byte[] buffer=new byte[1<<16];
   for(int n;(n=in.read(buffer))>0;) digest.update(buffer,0,n);
   return HexFormat.of().formatHex(digest.digest());
  } catch(java.security.NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
 }
}
