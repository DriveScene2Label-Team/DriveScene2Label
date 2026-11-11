package com.example.demo.nuscenes.dto;
/**
 * score = 1 - cosine distance (not a probability). matchScore = score rescaled to 0..100 with the calibrated
 * anchors in application.properties (search.match-score.*); null when no calibration matches the model/preprocess.
 */
public record SceneSearchResult(long sceneId, long datasetId, String sceneToken, String sceneName,
 String description, double score, double distance, long matchedImages, long contributingImages,
 long bestImageId, String bestSampleToken, String bestImagePath, String contentUrl, Integer matchScore) {
 public SceneSearchResult withMatchScore(Integer value) {
  return new SceneSearchResult(sceneId,datasetId,sceneToken,sceneName,description,score,distance,matchedImages,
   contributingImages,bestImageId,bestSampleToken,bestImagePath,contentUrl,value);
 }
}
