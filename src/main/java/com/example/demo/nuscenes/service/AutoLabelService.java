package com.example.demo.nuscenes.service;
import com.example.demo.nuscenes.dto.AutoLabelDtos.*;
import com.example.demo.nuscenes.repository.AutoLabelRepository;
import java.util.*;
import tools.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.web.server.ResponseStatusException;
@Service
public class AutoLabelService {
 private final AutoLabelRepository repo;
 private final SystemStatusService readiness;
 private final ObjectMapper json;
 private final TransactionTemplate tx;
 private final String version,modelVersion,storage;
 public AutoLabelService(AutoLabelRepository repo,SystemStatusService readiness,ObjectMapper json,PlatformTransactionManager manager,
  @Value("${auto-label.dataset-version:v1.0-trainval}") String version,
  @Value("${auto-label.model-version:acb2b6e8683363795528f049fe0444ef9f3efdb9}") String modelVersion,
  @Value("${auto-label.artifact-storage-key:vespa-results}") String storage) {
  this.repo=repo;this.readiness=readiness;this.json=json;this.tx=new TransactionTemplate(manager);this.version=version;this.modelVersion=modelVersion;this.storage=storage;
 }
 public Created create(CreateRequest request,String key) {
  return create(request,key,null,Map.of());
 }
 public Created postprocess(long sourceJob,PostprocessRequest request,String key) {
  var source=status(sourceJob);
  if(!"COMPLETED".equals(source.status())) throw new ResponseStatusException(HttpStatus.CONFLICT,"Source job must be completed");
  if(request.references()==null || request.references().isEmpty() || request.references().size()>1000) throw bad("Select at least one reference box");
  for(var reference:request.references().entrySet()) {
   if(reference.getKey()==null || !reference.getKey().matches("0|[1-9][0-9]{0,8}") || !repo.hasReference(sourceJob,reference.getKey(),reference.getValue())) throw bad("Reference track/frame is not in the source result");
  }
  return create(new CreateRequest(source.sceneToken(),source.datasetId(),source.classMode()),key,sourceJob,request.references());
 }
 private Created create(CreateRequest request,String key,Long sourceJob,Map<String,String> references) {
  if(!Set.of(1,3,8).contains(request.classMode()) || (request.datasetId()!=null && request.datasetId()<=0)) throw bad("Invalid classMode/datasetId");
  String requestKey=key==null?UUID.randomUUID().toString():key.strip();
  if(requestKey.isEmpty() || requestKey.length()>200) throw bad("Idempotency-Key must be 1..200 characters");
  // 1) Resolve the target and replay an existing job for this key first: works even while the AI is down.
  var target=tx.execute(status->{
   var targets=repo.targets(request.sceneToken(),request.datasetId());
   if(targets.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Scene not found");
   if(targets.size()!=1) throw new ResponseStatusException(HttpStatus.CONFLICT,"Specify datasetId for this scene token");
   return targets.getFirst();
  });
  var replay=tx.execute(status->repo.findExisting(target.datasetId(),requestKey).map(old->replay(old,target,request,sourceJob,references)));
  if(replay!=null && replay.isPresent()) return replay.get();
  if(!"uploads".equals(target.storageKey()) && !version.equals(target.version())) throw bad("Dataset version must match the configured VESPA dataset");
  // 2) New job only: the server checks VESPA readiness itself, outside any DB transaction.
  readiness.requireVespa(target.datasetId());
  // 3) Insert; a concurrent request with the same key falls back to replay.
  return tx.execute(status->{
   var samples=repo.sceneSamples(target); if(samples.isEmpty()) throw bad("Scene has no samples");
   var inserted=repo.insert(target,requestKey,request.classMode(),json.writeValueAsString(classes(request.classMode())),modelVersion,
      json.writeValueAsString(Map.of("dataset_version",target.version(),"config_name","configs/vlm/p_final.yaml")),sourceJob,json.writeValueAsString(references));
   if(inserted.isEmpty()) return replay(repo.existing(target.datasetId(),requestKey),target,request,sourceJob,references);
   long job=inserted.get(); for(String token:samples) repo.target(job,target.datasetId(),token);
   return new Created(job,"PENDING");
  });
 }
 private Created replay(AutoLabelRepository.Existing old,AutoLabelRepository.Target target,CreateRequest request,Long sourceJob,Map<String,String> references) {
  if(!old.sceneToken().equals(target.token()) || !old.mappingName().equals(request.classMode()+"class") || !Objects.equals(old.sourceJobId(),sourceJob)
    || !json.readTree(old.referenceFrames()).equals(json.valueToTree(references))) throw new ResponseStatusException(HttpStatus.CONFLICT,"Idempotency key refers to another request");
  return new Created(old.id(),repo.status(old.id()).orElseThrow().status());
 }
 public Optional<Work> claim() { return tx.execute(s->repo.claim()); }
 public JobStatus status(long id) { return repo.status(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Job not found")); }
 public Results results(long id) {
  var status=status(id);
  if(!"COMPLETED".equals(status.status())) throw new ResponseStatusException(HttpStatus.CONFLICT,"Job has not completed successfully");
  return repo.results(id,status);
 }
 public void complete(Work job,AiResponse result) {
  tx.executeWithoutResult(status->{
   Work locked=repo.lock(job.id()).orElseThrow(()->new IllegalStateException("Job is no longer running"));
   if(!job.executionToken().equals(locked.executionToken())) throw new IllegalStateException("Stale execution token");
   validate(job,result,repo.samples(job.id()));
   for(var entry:result.results().entrySet()) {
    int index=0; for(Box box:entry.getValue()) repo.box(job,entry.getKey(),index++,box,json.writeValueAsString(box));
   }
   repo.complete(job,result,storage);
  });
 }
 public void fail(Work job,String code,String reason) { tx.executeWithoutResult(s->repo.fail(job,code,reason)); }
 private void validate(Work job,AiResponse r,Set<String> samples) {
  if(r==null || r.jobId()==null || r.jobId()!=job.id() || !job.executionToken().equals(r.executionToken())
    || !job.sceneName().equals(r.sceneName()) || !job.mappingName().equals(r.mappingName()) || r.classMode()!=Integer.parseInt(job.mappingName().replace("class",""))
    || !"WORLD".equals(r.coordinateFrame()) || !"VESPA_CONSTANT".equals(r.scoreType()) || r.runId()==null || r.meta()==null || r.split()==null
    || r.resultChecksum()==null || !r.resultChecksum().matches("[0-9a-f]{64}") || r.artifactPath()==null
    || r.artifactPath().startsWith("/") || r.artifactPath().contains("..") || r.artifactPath().contains(":") || r.artifactPath().contains("\\") || r.artifactPath().isBlank()
    || r.results()==null || !r.results().keySet().equals(samples)) throw new IllegalArgumentException("VESPA response identity/coverage is invalid");
  for(var e:r.results().entrySet()) {
   if(e.getValue()==null) throw new IllegalArgumentException("Missing sample result");
   for(Box b:e.getValue()) {
    if(b==null || !e.getKey().equals(b.sampleToken()) || !classes(r.classMode()).contains(b.detectionName()) || b.detectionScore()==null || b.detectionScore()!=1.0 || (b.trackId()!=null && b.trackId()<0)) throw new IllegalArgumentException("Invalid predicted box metadata");
    numbers(b.translation(),3); numbers(b.size(),3); numbers(b.rotation(),4); numbers(b.velocity(),2);
    if(b.size().stream().anyMatch(v->v<=0) || Math.abs(b.rotation().stream().mapToDouble(v->v*v).sum()-1)>0.001) throw new IllegalArgumentException("Invalid predicted geometry");
   }
  }
 }
 private static void numbers(List<Double> values,int count) { if(values==null || values.size()!=count || values.stream().anyMatch(v->v==null || !Double.isFinite(v))) throw new IllegalArgumentException("Invalid box numeric fields"); }
 private static List<String> classes(int mode) { return switch(mode) { case 1->List.of("vehicle"); case 3->List.of("vehicle","pedestrian","bicycle"); default->List.of("car","truck","bus","trailer","construction_vehicle","pedestrian","motorcycle","bicycle"); }; }
 private static ResponseStatusException bad(String reason) { return new ResponseStatusException(HttpStatus.BAD_REQUEST,reason); }
}
