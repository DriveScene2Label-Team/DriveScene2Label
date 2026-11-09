package com.example.demo.nuscenes.dto;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.*;
import java.time.OffsetDateTime;
import jakarta.validation.constraints.*;
public final class AutoLabelDtos {
 private AutoLabelDtos() {}
 public record CreateRequest(@NotBlank String sceneToken, Long datasetId, @NotNull Integer classMode) {}
 public record Created(long jobId,String status) {}
 /** sceneToken is requested_targets[0]; sceneId/sceneName are null if that scene row no longer resolves. classMode is parsed from mappingName. */
 public record JobStatus(long jobId,long datasetId,String status,String errorMessage,OffsetDateTime createdAt,OffsetDateTime startedAt,OffsetDateTime completedAt,
   String sceneToken,Long sceneId,String sceneName,int classMode,String mappingName,String errorCode) {}
 public record Results(long jobId,long datasetId,String mappingName,String coordinateFrame,String scoreType,List<String> sampleTokens,List<Prediction> boxes,List<Artifact> artifacts) {}
 public record Prediction(long id,String sampleToken,int boxIndex,String detectionName,double centerX,double centerY,double centerZ,double sizeW,double sizeL,double sizeH,double rotationW,double rotationX,double rotationY,double rotationZ,double velocityX,double velocityY,double detectionScore,String attributeName) {}
 public record Artifact(long id,String artifactType,String storageKey,String relativePath,String checksum,String contentType) {}
 public record Header(String mappingName,String coordinateFrame,String scoreType) {}
 public record Work(long id,long datasetId,String sceneName,String mappingName,UUID executionToken,String datasetKey,String datasetVersion) {
  public Work(long id,long datasetId,String sceneName,String mappingName,UUID executionToken) { this(id,datasetId,sceneName,mappingName,executionToken,null,null); }
 }
 public record AiRequest(@JsonProperty("scene_name") String sceneName,@JsonProperty("class_mode") int classMode,
   @JsonProperty("job_id") long jobId,@JsonProperty("execution_token") UUID executionToken,
   @JsonProperty("dataset_key") String datasetKey,@JsonProperty("dataset_version") String datasetVersion) {}
 public record Box(@JsonProperty("sample_token") String sampleToken,List<Double> translation,List<Double> size,List<Double> rotation,List<Double> velocity,
   @JsonProperty("detection_name") String detectionName,@JsonProperty("detection_score") Double detectionScore,@JsonProperty("attribute_name") String attributeName) {}
 public record AiResponse(@JsonProperty("run_id") UUID runId,@JsonProperty("scene_name") String sceneName,@JsonProperty("class_mode") int classMode,
   @JsonProperty("job_id") Long jobId,@JsonProperty("execution_token") UUID executionToken,@JsonProperty("mapping_name") String mappingName,
   String split,@JsonProperty("coordinate_frame") String coordinateFrame,@JsonProperty("score_type") String scoreType,Map<String,Boolean> meta,
   Map<String,List<Box>> results,@JsonProperty("artifact_path") String artifactPath,@JsonProperty("result_checksum") String resultChecksum) {}
}
