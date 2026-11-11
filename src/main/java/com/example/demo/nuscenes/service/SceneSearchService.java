package com.example.demo.nuscenes.service;

import com.example.demo.nuscenes.client.TextEmbeddingClient;
import com.example.demo.nuscenes.dto.*;
import com.example.demo.nuscenes.repository.SceneSearchRepository;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class SceneSearchService {
 private final TextEmbeddingClient ai;
 private final SceneSearchRepository repository;
 private final MatchScoreCalibration calibration;
 private final String model, preprocess;
 public SceneSearchService(TextEmbeddingClient ai, SceneSearchRepository repository, MatchScoreCalibration calibration,
   @Value("${embedding.model-name}") String model, @Value("${embedding.preprocess}") String preprocess) {
  this.ai=ai; this.repository=repository; this.calibration=calibration; this.model=model; this.preprocess=preprocess;
 }
 public SceneSearchResponse search(String query, int k, Long datasetId, String aggregation,
   int imageTopK, boolean keyframesOnly) {
  if(query==null || query.isBlank() || query.strip().length()>10000) throw badRequest("q must contain 1..10000 characters");
  if(k<1 || k>100) throw badRequest("k must be 1..100");
  if(datasetId!=null && datasetId<=0) throw badRequest("datasetId must be positive");
  if(imageTopK<1 || imageTopK>100) throw badRequest("imageTopK must be 1..100");
  String mode=aggregation==null ? "TOP_K_AVERAGE" : aggregation.toUpperCase(Locale.ROOT);
  if(!Set.of("MAX","AVERAGE","TOP_K_AVERAGE").contains(mode)) throw badRequest("aggregation must be MAX, AVERAGE or TOP_K_AVERAGE");
  String text=query.strip();
  var encoded=ai.embed(text);
  String vector=EmbeddingValidator.vector(encoded,model,"clip-text-tokenizer");
  // HTTP inference occurs before the repository's read-only DB transaction.
  var results=repository.search(vector,model,preprocess,datasetId,k,mode,imageTopK,keyframesOnly).stream()
   .map(r->r.withMatchScore(calibration.matchScore(model,preprocess,mode,r.score()))).toList();
  org.slf4j.LoggerFactory.getLogger(getClass()).info("[SEARCH] topK={} scenes={} aggregation={}",k,results.size(),mode);
  return new SceneSearchResponse(text,model,preprocess,mode,imageTopK,keyframesOnly,results);
 }
 private static ResponseStatusException badRequest(String message) { return new ResponseStatusException(HttpStatus.BAD_REQUEST,message); }
 private static ResponseStatusException invalidEmbedding() { return new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI returned an incompatible or invalid text embedding"); }
}
