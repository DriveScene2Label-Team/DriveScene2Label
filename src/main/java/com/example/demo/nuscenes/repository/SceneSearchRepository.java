package com.example.demo.nuscenes.repository;

import com.example.demo.nuscenes.dto.SceneSearchResult;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class SceneSearchRepository {
 private final JdbcClient jdbc;
 public SceneSearchRepository(JdbcClient jdbc) { this.jdbc=jdbc; }

 /** One SQL row; the service adds matchScore. */
 record Row(long sceneId, long datasetId, String sceneToken, String sceneName, String description, double score,
  double distance, long matchedImages, long contributingImages, long bestImageId, String bestSampleToken,
  String bestImagePath, String contentUrl) {
  SceneSearchResult toResult() {
   return new SceneSearchResult(sceneId,datasetId,sceneToken,sceneName,description,score,distance,matchedImages,
    contributingImages,bestImageId,bestSampleToken,bestImagePath,contentUrl,null);
  }
 }

 /** Exact scene ranking: aggregate eligible images BEFORE limiting scenes. */
 @Transactional(readOnly=true)
 public List<SceneSearchResult> search(String vector, String model, String preprocess, Long datasetId,
   int k, String aggregation, int imageTopK, boolean keyframesOnly) {
  return jdbc.sql("""
   WITH distances AS (
    SELECT sc.id AS scene_id, sc.dataset_id, sc.token AS scene_token, sc.name AS scene_name,
      sc.description, sd.id AS best_image_id, sd.sample_token AS best_sample_token,
      sd.relative_path AS best_image_path, e.embedding <=> CAST(:vector AS vector) AS image_distance
    FROM image_embedding e
    JOIN sample_data sd ON sd.dataset_id=e.dataset_id AND sd.token=e.sample_data_token
    JOIN sample sa ON sa.dataset_id=sd.dataset_id AND sa.token=sd.sample_token
    JOIN scene sc ON sc.dataset_id=sa.dataset_id AND sc.token=sa.scene_token
    JOIN calibrated_sensor cs ON cs.dataset_id=sd.dataset_id AND cs.token=sd.calibrated_sensor_token
    JOIN sensor se ON se.dataset_id=cs.dataset_id AND se.token=cs.sensor_token
    WHERE e.model_name=:model AND e.preprocess=:preprocess AND se.modality='camera'
      AND (CAST(:dataset AS bigint) IS NULL OR e.dataset_id=:dataset)
      AND (:keyframesOnly=false OR sd.is_key_frame)
   ), ranked AS (
    SELECT *, row_number() OVER (PARTITION BY scene_id ORDER BY image_distance, best_image_id) AS image_rank
    FROM distances WHERE image_distance >= 0 AND image_distance <= 2
   ), scores AS (
    SELECT scene_id,
      CASE :aggregation
        WHEN 'MAX' THEN max(1.0-image_distance)
        WHEN 'AVERAGE' THEN avg(1.0-image_distance)
        ELSE avg(1.0-image_distance) FILTER (WHERE image_rank <= :imageTopK)
      END AS score,
      count(*) AS matched_images,
      CASE :aggregation WHEN 'MAX' THEN 1 WHEN 'AVERAGE' THEN count(*)
        ELSE count(*) FILTER (WHERE image_rank <= :imageTopK) END AS contributing_images
    FROM ranked GROUP BY scene_id
   )
   SELECT r.scene_id, r.dataset_id, r.scene_token, r.scene_name, r.description,
      s.score, 1.0-s.score AS distance, s.matched_images, s.contributing_images,
      r.best_image_id, r.best_sample_token, r.best_image_path,
      '/api/sensor-files/' || r.best_image_id || '/content' AS content_url
   FROM scores s JOIN ranked r ON r.scene_id=s.scene_id AND r.image_rank=1
   ORDER BY s.score DESC, r.dataset_id, r.scene_id LIMIT :k
   """).param("vector",vector).param("model",model).param("preprocess",preprocess)
    .param("dataset",datasetId).param("k",k).param("aggregation",aggregation)
    .param("imageTopK",imageTopK).param("keyframesOnly",keyframesOnly)
    .query(Row.class).list().stream().map(Row::toResult).toList();
 }
}
