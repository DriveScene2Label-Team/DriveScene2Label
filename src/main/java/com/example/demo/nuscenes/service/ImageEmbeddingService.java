package com.example.demo.nuscenes.service;
import com.example.demo.nuscenes.client.TextEmbeddingClient;
import com.example.demo.nuscenes.dto.ImageBatchEmbeddingResponse;
import com.example.demo.nuscenes.dto.TextEmbeddingResponse;
import com.example.demo.nuscenes.repository.ImageEmbeddingRepository;
import com.example.demo.nuscenes.storage.DatasetStorage;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
@Service
public class ImageEmbeddingService {
 public record Result(long sensorFileId,long datasetId,String sampleDataToken,String modelName,String preprocess,int dimension,String status) {}
 /** Matches the AI server's MAX_BATCH_IMAGES (POST /embedding/images). */
 public static final int MAX_BATCH=64;
 private final TextEmbeddingClient ai; private final ImageEmbeddingRepository repo; private final String model,preprocess;
 private final DatasetStorage storage;
 public ImageEmbeddingService(TextEmbeddingClient ai,ImageEmbeddingRepository repo,DatasetStorage storage,@Value("${embedding.model-name}") String model,@Value("${embedding.preprocess}") String preprocess) { this.ai=ai;this.repo=repo;this.storage=storage;this.model=model;this.preprocess=preprocess; }
 public Result embed(long id,boolean overwrite) {
  long started=System.nanoTime();
  var source=repo.source(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Sensor file not found"));
  return embedResolved(id,source,overwrite,false,started,(System.nanoTime()-started)/1_000_000);
 }
 /** A claimed index batch already selected this immutable source and excluded stored embeddings.
  * A concurrent writer is still protected by save(..., overwrite=false)'s atomic ON CONFLICT.
  */
 public Result embedPending(long id,ImageEmbeddingRepository.Source source) {
  return embedResolved(id,source,false,true,System.nanoTime(),0);
 }
 private record Mapped(String datasetKey,long cacheMs) {}
 /** Camera check, upload cache preparation and AI root mapping shared by the single and batch paths. */
 private Mapped map(ImageEmbeddingRepository.Source source) {
  if(!"camera".equals(source.modality())) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Only camera images can be embedded");
  if("uploads".equals(source.storageKey())) {
   long cacheStarted=System.nanoTime();
   try { storage.files(source.storageKey(),source.rootRelativePath()).resolve(source.relativePath()); }
   catch(java.io.IOException e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Uploaded image cache could not be prepared",e); }
   return new Mapped(source.rootRelativePath(),(System.nanoTime()-cacheStarted)/1_000_000);
  }
  if(!"nuscenes".equals(source.storageKey()) || !".".equals(source.rootRelativePath())) throw new ResponseStatusException(HttpStatus.CONFLICT,"Dataset does not map to the configured AI image root");
  return new Mapped(null,0);
 }
 private Result embedResolved(long id,ImageEmbeddingRepository.Source source,boolean overwrite,
   boolean selectedMissing,long started,long sourceMs) {
  long aiMs=0,storageMs=0,existsMs=0;
  var mapped=map(source); String datasetKey=mapped.datasetKey(); long cacheMs=mapped.cacheMs();
  String status="SKIPPED";
  long existsStarted=System.nanoTime();
  boolean needsEmbedding=overwrite || selectedMissing || !repo.exists(source,model,preprocess);
  existsMs=(System.nanoTime()-existsStarted)/1_000_000;
  if(needsEmbedding) {
   long stageStarted=System.nanoTime();
   String vector=EmbeddingValidator.vector(ai.image(source.relativePath(),preprocess,datasetKey),model,preprocess);
   aiMs=(System.nanoTime()-stageStarted)/1_000_000;stageStarted=System.nanoTime();
   // A single atomic upsert follows HTTP inference; no database transaction spans inference.
   if(repo.save(source,model,preprocess,vector,overwrite)>0) status="STORED";
   storageMs=(System.nanoTime()-stageStarted)/1_000_000;
  }
  org.slf4j.LoggerFactory.getLogger(getClass()).info("[CLIP] dataset={} image={} status={} source={} source_ms={} cache_ms={} exists_ms={} ai_ms={} storage_ms={} total_ms={}",source.datasetId(),id,status,selectedMissing?"pending_batch":"per_image",sourceMs,cacheMs,existsMs,aiMs,storageMs,(System.nanoTime()-started)/1_000_000);
  return new Result(id,source.datasetId(),source.token(),model,preprocess,768,status);
 }

 private record Target(long id,ImageEmbeddingRepository.Source source,String datasetKey,boolean selectedMissing) {}
 /**
  * Search indexing: embed many images with one AI call per dataset root (POST /embedding/images, up to 64 per call)
  * instead of one call per image. Vectors, validation and the per-image upsert are the same as embed(id,false).
  * {@code prefetched} holds sources the index batch already selected as missing (see embedPending); other ids are
  * loaded and checked for an existing embedding here. Successful images are stored before the first per-image AI
  * error is raised, so a retry only redoes the rest. An AI server without the batch route falls back to single calls.
  */
 public List<Result> embedBatch(List<Long> ids,Map<Long,ImageEmbeddingRepository.Source> prefetched) {
  long started=System.nanoTime(),aiMs=0,storageMs=0,cacheMs=0;
  var results=new ArrayList<Result>(); var groups=new LinkedHashMap<String,List<Target>>(); long dataset=0;
  for(long id:ids) {
   var known=prefetched.get(id);
   var source=known!=null?known:repo.source(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"Sensor file not found"));
   var mapped=map(source); cacheMs+=mapped.cacheMs(); dataset=source.datasetId();
   var t=new Target(id,source,mapped.datasetKey(),known!=null);
   if(!t.selectedMissing() && repo.exists(source,model,preprocess)) { results.add(result(t,"SKIPPED")); continue; }
   groups.computeIfAbsent(t.datasetKey()==null?"":t.datasetKey(),k->new ArrayList<>()).add(t);
  }
  ResponseStatusException firstError=null; int stored=0,requested=0;
  for(var group:groups.values()) for(int from=0;from<group.size();from+=MAX_BATCH) {
   var chunk=group.subList(from,Math.min(group.size(),from+MAX_BATCH)); requested+=chunk.size();
   long stageStarted=System.nanoTime();
   ImageBatchEmbeddingResponse response;
   try { response=ai.images(chunk.stream().map(t->t.source().relativePath()).toList(),preprocess,chunk.get(0).datasetKey()); }
   catch(TextEmbeddingClient.BatchUnsupportedException e) {
    org.slf4j.LoggerFactory.getLogger(getClass()).warn("[CLIP_BATCH] dataset={} event=fallback images={}",dataset,chunk.size());
    for(var t:chunk) results.add(t.selectedMissing()?embedPending(t.id(),t.source()):embed(t.id(),false));
    continue;
   }
   aiMs+=(System.nanoTime()-stageStarted)/1_000_000;
   if(response==null || !model.equals(response.modelName()) || !preprocess.equals(response.preprocess()) || response.results()==null || response.results().size()!=chunk.size())
    throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI returned incompatible embedding metadata or vector");
   for(int i=0;i<chunk.size();i++) {
    var t=chunk.get(i); var item=response.results().get(i);
    if(item==null || !t.source().relativePath().equals(item.imagePath())) throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI returned incompatible embedding metadata or vector");
    if(item.error()!=null) {
     // Same mapping as the single-image client: 404 stays 404, any other AI-side image error is a bad gateway.
     if(firstError==null) firstError=item.error().status()==404
      ? new ResponseStatusException(HttpStatus.NOT_FOUND,"Image not found on AI server")
      : new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI image embedding request failed");
     continue;
    }
    String vector=EmbeddingValidator.vector(new TextEmbeddingResponse(response.modelName(),response.dimension(),item.embedding(),response.preprocess()),model,preprocess);
    stageStarted=System.nanoTime();
    String status=repo.save(t.source(),model,preprocess,vector,false)>0?"STORED":"SKIPPED";
    storageMs+=(System.nanoTime()-stageStarted)/1_000_000;
    if("STORED".equals(status)) stored++;
    results.add(result(t,status));
   }
  }
  org.slf4j.LoggerFactory.getLogger(getClass()).info("[CLIP_BATCH] dataset={} images={} count={} cache_ms={} ai_ms={} storage_ms={} total_ms={}",dataset,requested,stored,cacheMs,aiMs,storageMs,(System.nanoTime()-started)/1_000_000);
  if(firstError!=null) throw firstError;
  return results;
 }
 public List<Result> embedBatch(List<Long> ids) { return embedBatch(ids,Map.of()); }
 private Result result(Target t,String status) { return new Result(t.id(),t.source().datasetId(),t.source().token(),model,preprocess,768,status); }
}
