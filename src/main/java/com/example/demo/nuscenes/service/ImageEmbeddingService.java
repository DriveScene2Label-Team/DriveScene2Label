package com.example.demo.nuscenes.service;
import com.example.demo.nuscenes.client.TextEmbeddingClient;
import com.example.demo.nuscenes.repository.ImageEmbeddingRepository;
import com.example.demo.nuscenes.storage.DatasetStorage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
@Service
public class ImageEmbeddingService {
 public record Result(long sensorFileId,long datasetId,String sampleDataToken,String modelName,String preprocess,int dimension,String status) {}
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
 private Result embedResolved(long id,ImageEmbeddingRepository.Source source,boolean overwrite,
   boolean selectedMissing,long started,long sourceMs) {
  long aiMs=0,storageMs=0,cacheMs=0,existsMs=0;
  if(!"camera".equals(source.modality())) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Only camera images can be embedded");
  String datasetKey=null;
  if("uploads".equals(source.storageKey())) {
   long cacheStarted=System.nanoTime();
   try { storage.files(source.storageKey(),source.rootRelativePath()).resolve(source.relativePath()); }
   catch(java.io.IOException e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Uploaded image cache could not be prepared",e); }
   datasetKey=source.rootRelativePath();
   cacheMs=(System.nanoTime()-cacheStarted)/1_000_000;
  } else if(!"nuscenes".equals(source.storageKey()) || !".".equals(source.rootRelativePath())) throw new ResponseStatusException(HttpStatus.CONFLICT,"Dataset does not map to the configured AI image root");
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
}
