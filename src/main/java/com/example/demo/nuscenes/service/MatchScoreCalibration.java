package com.example.demo.nuscenes.service;

import java.util.Locale;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Rescales a CLIP scene score (cosine similarity, typically 0.1..0.3) to a 0..100 match score.
 *
 * Per aggregation, lower = 0 points and upper = 100 points, linear in between and clamped. The anchors come from
 * scripts/calibrate_match_score.py (lower = p90 of unrelated-text scores, upper = median score of short queries on
 * their matching scenes, scripts/match_score_queries.mini.json); see docs/search-match-score.md. They only hold for the model/preprocess they were
 * measured with, so any other embedding gets null rather than a misleading number. Not a probability.
 */
@Component
public class MatchScoreCalibration {
 record Anchors(double lower, double upper) {
  Anchors {
   if(!(Double.isFinite(lower) && Double.isFinite(upper) && upper>lower))
    throw new IllegalStateException("search.match-score: upper must be greater than lower, got "+lower+".."+upper);
  }
 }
 private final String model, preprocess;
 private final Map<String,Anchors> anchors;

 public MatchScoreCalibration(
   @Value("${search.match-score.model-name}") String model, @Value("${search.match-score.preprocess}") String preprocess,
   @Value("${search.match-score.top-k-average.lower}") double topKLower, @Value("${search.match-score.top-k-average.upper}") double topKUpper,
   @Value("${search.match-score.max.lower}") double maxLower, @Value("${search.match-score.max.upper}") double maxUpper,
   @Value("${search.match-score.average.lower}") double avgLower, @Value("${search.match-score.average.upper}") double avgUpper) {
  this.model=model; this.preprocess=preprocess;
  this.anchors=Map.of("TOP_K_AVERAGE",new Anchors(topKLower,topKUpper),"MAX",new Anchors(maxLower,maxUpper),
   "AVERAGE",new Anchors(avgLower,avgUpper));
 }

 /** 0..100, or null if the embedding model/preprocess differs from the calibrated one. */
 public Integer matchScore(String embeddingModel, String embeddingPreprocess, String aggregation, double score) {
  if(!model.equals(embeddingModel) || !preprocess.equals(embeddingPreprocess) || !Double.isFinite(score)) return null;
  Anchors a=anchors.get(aggregation==null ? null : aggregation.toUpperCase(Locale.ROOT));
  if(a==null) return null;
  double scaled=100.0*(score-a.lower())/(a.upper()-a.lower());
  return (int)Math.round(Math.max(0.0,Math.min(100.0,scaled)));
 }
}
