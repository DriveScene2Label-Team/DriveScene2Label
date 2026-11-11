package com.example.demo.nuscenes.dto;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.*;
import java.time.OffsetDateTime;
import jakarta.validation.constraints.*;
public final class AutoLabelDtos {
 private AutoLabelDtos() {}
 public record CreateRequest(@NotBlank String sceneToken, Long datasetId, @NotNull Integer classMode) {}
 public record Created(long jobId,String status) {}
 public record PostprocessRequest(@NotEmpty @Size(max=1000) Map<@Pattern(regexp="0|[1-9][0-9]{0,8}") String,@NotBlank String> references) {}
 /** sceneToken is requested_targets[0]; sceneId/sceneName are null if that scene row no longer resolves. classMode is parsed from mappingName. */
 public record JobStatus(long jobId,long datasetId,String status,String errorMessage,OffsetDateTime createdAt,OffsetDateTime startedAt,OffsetDateTime completedAt,
   String sceneToken,Long sceneId,String sceneName,int classMode,String mappingName,String errorCode) {}
 public record Results(long jobId,long datasetId,String mappingName,String coordinateFrame,String scoreType,List<String> sampleTokens,List<Prediction> boxes,List<Artifact> artifacts) {}
 /** labelOverride: class set by a label edit (null = detectionName unchanged). deleted is true only when deleted boxes were requested. */
 public record Prediction(long id,String sampleToken,int boxIndex,String detectionName,double centerX,double centerY,double centerZ,double sizeW,double sizeL,double sizeH,double rotationW,double rotationX,double rotationY,double rotationZ,double velocityX,double velocityY,double detectionScore,String attributeName,
   Integer trackId,String labelOverride,boolean deleted) {}
 public record Artifact(long id,String artifactType,String storageKey,String relativePath,String checksum,String contentType) {}
 public record Header(String mappingName,String coordinateFrame,String scoreType) {}
 public record Work(long id,long datasetId,String sceneName,String mappingName,UUID executionToken,String datasetKey,String datasetVersion,String sourceArtifactPath,String referenceFrames) {
  public Work(long id,long datasetId,String sceneName,String mappingName,UUID executionToken,String datasetKey,String datasetVersion) { this(id,datasetId,sceneName,mappingName,executionToken,datasetKey,datasetVersion,null,"{}"); }
  public Work(long id,long datasetId,String sceneName,String mappingName,UUID executionToken) { this(id,datasetId,sceneName,mappingName,executionToken,null,null); }
 }
 public record AiRequest(@JsonProperty("scene_name") String sceneName,@JsonProperty("class_mode") int classMode,
   @JsonProperty("job_id") long jobId,@JsonProperty("execution_token") UUID executionToken,
   @JsonProperty("dataset_key") String datasetKey,@JsonProperty("dataset_version") String datasetVersion,
   @JsonProperty("source_artifact_path") String sourceArtifactPath,Map<String,String> references) {}
 public record Box(@JsonProperty("sample_token") String sampleToken,List<Double> translation,List<Double> size,List<Double> rotation,List<Double> velocity,
   @JsonProperty("detection_name") String detectionName,@JsonProperty("detection_score") Double detectionScore,@JsonProperty("attribute_name") String attributeName,
   @JsonProperty("track_id") Integer trackId) {
  public Box(String sampleToken,List<Double> translation,List<Double> size,List<Double> rotation,List<Double> velocity,String detectionName,Double detectionScore,String attributeName) { this(sampleToken,translation,size,rotation,velocity,detectionName,detectionScore,attributeName,null); }
 }
 public record AiResponse(@JsonProperty("run_id") UUID runId,@JsonProperty("scene_name") String sceneName,@JsonProperty("class_mode") int classMode,
   @JsonProperty("job_id") Long jobId,@JsonProperty("execution_token") UUID executionToken,@JsonProperty("mapping_name") String mappingName,
   String split,@JsonProperty("coordinate_frame") String coordinateFrame,@JsonProperty("score_type") String scoreType,Map<String,Boolean> meta,
   Map<String,List<Box>> results,@JsonProperty("artifact_path") String artifactPath,@JsonProperty("result_checksum") String resultChecksum) {}
}
