package com.example.demo.nuscenes.dto;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.OffsetDateTime;
import java.util.*;
/** Rerun recording contract: docs/rerun-recording.md. Browser DTOs are camelCase, AI DTOs snake_case. */
public final class RecordingDtos {
 private RecordingDtos() {}
 public record CreateRequest(Long jobId) {}
 public record Created(long recordingId,String status,boolean reused) {}
 @JsonIgnoreProperties(ignoreUnknown=true)
 public record Entities(String lidar,String ego,String gt,String prediction) {}
 public record SampleMap(int index,String sampleToken,long timestampUs,int lidarPoints,List<Long> gtAnnotationIds,List<Long> predictionIds) {}
 /** Stored in scene_recording.metadata. */
 public record Metadata(String applicationId,String rerunRecordingId,String timeline,String timeTimeline,Entities entities,List<SampleMap> samples) {}
 /** Detail view; list summaries pass samples=null so the field is omitted. Metadata-derived fields are null until READY. */
 public record Recording(long recordingId,long datasetId,long sceneId,String sceneToken,String sceneName,Long jobId,String status,String sdkVersion,String exportVersion,
   String coordinateFrame,String applicationId,String rerunRecordingId,String timeline,String timeTimeline,Entities entities,
   @JsonInclude(JsonInclude.Include.NON_NULL) List<SampleMap> samples,String contentUrl,Long sizeBytes,String errorMessage,String errorCode,
   OffsetDateTime createdAt,OffsetDateTime startedAt,OffsetDateTime completedAt) {}
 public record Row(long recordingId,long datasetId,long sceneId,String sceneToken,String sceneName,Long jobId,String status,String sdkVersion,String exportVersion,
   String metadata,Long sizeBytes,String failureReason,String errorCode,OffsetDateTime createdAt,OffsetDateTime startedAt,OffsetDateTime completedAt) {}
 public record JobTarget(String sceneToken,String targetType,int targets,String status) {}
 public record Work(long id,long datasetId,String sceneToken,Long jobId,String sdkVersion,String exportVersion,UUID executionToken) {}
 public record SceneSample(String token,long timestampUs) {}
 public record LidarRow(String sampleToken,String relativePath,double sensorTx,double sensorTy,double sensorTz,double sensorRw,double sensorRx,double sensorRy,double sensorRz,
   double egoTx,double egoTy,double egoTz,double egoRw,double egoRx,double egoRy,double egoRz) {}
 public record PredictionRow(long id,String sampleToken,String detectionName,double centerX,double centerY,double centerZ,double sizeW,double sizeL,double sizeH,
   double rotationW,double rotationX,double rotationY,double rotationZ) {}

 public record AiRequest(@JsonProperty("recording_id") long recordingId,@JsonProperty("execution_token") UUID executionToken,@JsonProperty("scene_name") String sceneName,
   @JsonProperty("scene_token") String sceneToken,@JsonProperty("job_id") Long jobId,List<AiSample> samples,
   @JsonProperty("dataset_key") String datasetKey,@JsonProperty("dataset_version") String datasetVersion) {}
 public record AiSample(int index,@JsonProperty("sample_token") String sampleToken,@JsonProperty("timestamp_us") long timestampUs,AiLidar lidar,List<AiGt> gt,List<AiPrediction> predictions) {}
 public record AiLidar(@JsonProperty("relative_path") String relativePath,@JsonProperty("sensor_translation") List<Double> sensorTranslation,@JsonProperty("sensor_rotation") List<Double> sensorRotation,
   @JsonProperty("ego_translation") List<Double> egoTranslation,@JsonProperty("ego_rotation") List<Double> egoRotation) {}
 public record AiGt(long id,@JsonProperty("category_name") String categoryName,List<Double> center,@JsonProperty("size_wlh") List<Double> sizeWlh,@JsonProperty("rotation_wxyz") List<Double> rotationWxyz) {}
 public record AiPrediction(long id,@JsonProperty("detection_name") String detectionName,List<Double> center,@JsonProperty("size_wlh") List<Double> sizeWlh,@JsonProperty("rotation_wxyz") List<Double> rotationWxyz) {}
 @JsonIgnoreProperties(ignoreUnknown=true)
 public record AiResponse(@JsonProperty("recording_id") Long recordingId,@JsonProperty("execution_token") UUID executionToken,@JsonProperty("relative_path") String relativePath,
   @JsonProperty("size_bytes") Long sizeBytes,String checksum,@JsonProperty("sdk_version") String sdkVersion,@JsonProperty("export_version") String exportVersion,
   @JsonProperty("application_id") String applicationId,@JsonProperty("rerun_recording_id") String rerunRecordingId,String timeline,@JsonProperty("time_timeline") String timeTimeline,
   Entities entities,List<AiSampleResult> samples) {}
 @JsonIgnoreProperties(ignoreUnknown=true)
 public record AiSampleResult(Integer index,@JsonProperty("sample_token") String sampleToken,@JsonProperty("lidar_points") Integer lidarPoints,
   @JsonProperty("gt_boxes") Integer gtBoxes,@JsonProperty("prediction_boxes") Integer predictionBoxes) {}
}
