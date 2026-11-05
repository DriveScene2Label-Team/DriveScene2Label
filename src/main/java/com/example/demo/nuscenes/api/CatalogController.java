package com.example.demo.nuscenes.api;

import com.example.demo.nuscenes.domain.*;
import com.example.demo.nuscenes.dto.GtAnnotationView;
import com.example.demo.nuscenes.repository.*;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class CatalogController {
 private final DatasetRepository datasets;
 private final SceneRepository scenes;
 private final SampleRepository samples;
 private final GtAnnotationViewRepository annotations;
 private final JdbcClient jdbc;
 public CatalogController(DatasetRepository datasets, SceneRepository scenes, SampleRepository samples,
   GtAnnotationViewRepository annotations, JdbcClient jdbc) {
  this.datasets=datasets; this.scenes=scenes; this.samples=samples; this.annotations=annotations; this.jdbc=jdbc;
 }
 @GetMapping("/datasets") public List<Dataset> datasets() { return datasets.listAll(); }
 @GetMapping("/datasets/{id}/scenes") public List<Scene> scenes(@PathVariable long id) {
  datasets.findById(id).orElseThrow(CatalogController::notFound); return scenes.findByDatasetId(id);
 }
 public record Counts(long scenes, long samples, long sensorFiles, long keyframeFiles, long gtBoxes, long maps) {}
 @GetMapping("/datasets/{id}/stats") public Counts stats(@PathVariable long id) {
  datasets.findById(id).orElseThrow(CatalogController::notFound);
  return jdbc.sql("""
   SELECT (SELECT count(*) FROM scene WHERE dataset_id=:id) AS scenes,
     (SELECT count(*) FROM sample WHERE dataset_id=:id) AS samples,
     (SELECT count(*) FROM sample_data WHERE dataset_id=:id) AS sensor_files,
     (SELECT count(*) FROM sample_data WHERE dataset_id=:id AND is_key_frame) AS keyframe_files,
     (SELECT count(*) FROM gt_annotation WHERE dataset_id=:id) AS gt_boxes,
     (SELECT count(*) FROM map_asset WHERE dataset_id=:id) AS maps
   """).param("id", id).query(Counts.class).single();
 }
 @GetMapping("/scenes/{id}/samples") public List<Sample> samples(@PathVariable long id,
   @RequestParam(defaultValue="100") int limit, @RequestParam(defaultValue="0") int offset) {
  if(limit<1 || limit>500 || offset<0) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"limit must be 1..500 and offset >= 0");
  Scene scene=scenes.findById(id).orElseThrow(CatalogController::notFound);
  return samples.listByScene(scene.datasetId(), scene.token(), limit, offset);
 }
 public record SensorFile(long id, String token, String channel, String modality, String relativePath,
   long timestampUs, boolean isKeyFrame, int width, int height, String egoPoseToken, String calibratedSensorToken,
   double vehicleX, double vehicleY, double vehicleZ, String contentUrl) {}
 public record MapView(long id, String token, String relativePath, String location, String contentUrl) {}
 public record SampleDetail(Sample sample, List<SensorFile> sensorFiles, List<MapView> maps) {}
 @GetMapping("/samples/{id}") public SampleDetail sample(@PathVariable long id,
   @RequestParam(defaultValue="true") boolean keyframesOnly) {
  Sample sample=samples.findById(id).orElseThrow(CatalogController::notFound);
  List<SensorFile> files=jdbc.sql("""
   SELECT sd.id, sd.token, s.channel, s.modality, sd.relative_path, sd.timestamp_us, sd.is_key_frame,
     sd.width, sd.height, sd.ego_pose_token, sd.calibrated_sensor_token,
     ep.translation_x AS vehicle_x, ep.translation_y AS vehicle_y, ep.translation_z AS vehicle_z,
     '/api/sensor-files/' || sd.id || '/content' AS content_url
   FROM sample_data sd
   JOIN calibrated_sensor cs ON cs.dataset_id=sd.dataset_id AND cs.token=sd.calibrated_sensor_token
   JOIN sensor s ON s.dataset_id=cs.dataset_id AND s.token=cs.sensor_token
   JOIN ego_pose ep ON ep.dataset_id=sd.dataset_id AND ep.token=sd.ego_pose_token
   WHERE sd.dataset_id=:dataset AND sd.sample_token=:token AND (:keyframes=false OR sd.is_key_frame=true)
   ORDER BY s.channel, sd.timestamp_us
   """).param("dataset",sample.datasetId()).param("token",sample.token()).param("keyframes",keyframesOnly).query(SensorFile.class).list();
  List<MapView> maps=jdbc.sql("""
   SELECT m.id, m.token, m.relative_path, l.location, '/api/maps/' || m.id || '/content' AS content_url
   FROM scene sc
   JOIN capture_log l ON l.dataset_id=sc.dataset_id AND l.token=sc.log_token
   JOIN map_log ml ON ml.dataset_id=l.dataset_id AND ml.log_token=l.token
   JOIN map_asset m ON m.dataset_id=ml.dataset_id AND m.token=ml.map_token
   WHERE sc.dataset_id=:dataset AND sc.token=:scene ORDER BY m.token
   """).param("dataset",sample.datasetId()).param("scene",sample.sceneToken()).query(MapView.class).list();
  return new SampleDetail(sample,files,maps);
 }
 @GetMapping("/samples/{id}/annotations") public List<GtAnnotationView> annotations(@PathVariable long id,@RequestParam(defaultValue="false") boolean includeDeleted) {
  Sample sample=samples.findById(id).orElseThrow(CatalogController::notFound);
  return annotations.bySample(sample.datasetId(),sample.token(),includeDeleted);
 }
 /** All not-deleted GT of a scene (every sample). Lets the UI count an instance's frames and mark them on the timeline. */
 @GetMapping("/scenes/{id}/annotations") public List<GtAnnotationView> sceneAnnotations(@PathVariable long id) {
  Scene scene=scenes.findById(id).orElseThrow(CatalogController::notFound);
  return annotations.visibleByScene(scene.datasetId(),scene.token());
 }
 @GetMapping("/datasets/{id}/categories") public List<Category> categories(@PathVariable long id) {
  datasets.findById(id).orElseThrow(CatalogController::notFound);
  return jdbc.sql("SELECT * FROM category WHERE dataset_id=:id ORDER BY name").param("id",id).query(Category.class).list();
 }
 @GetMapping("/sensor-files/{id}/calibration") public CalibratedSensor calibration(@PathVariable long id) {
  return jdbc.sql("SELECT cs.* FROM calibrated_sensor cs JOIN sample_data sd ON sd.dataset_id=cs.dataset_id AND sd.calibrated_sensor_token=cs.token WHERE sd.id=:id")
   .param("id",id).query(CalibratedSensor.class).optional().orElseThrow(CatalogController::notFound);
 }
 @GetMapping("/sensor-files/{id}/pose") public EgoPose pose(@PathVariable long id) {
  return jdbc.sql("SELECT ep.* FROM ego_pose ep JOIN sample_data sd ON sd.dataset_id=ep.dataset_id AND sd.ego_pose_token=ep.token WHERE sd.id=:id")
   .param("id",id).query(EgoPose.class).optional().orElseThrow(CatalogController::notFound);
 }
 private static ResponseStatusException notFound() { return new ResponseStatusException(HttpStatus.NOT_FOUND,"Record not found"); }
}
