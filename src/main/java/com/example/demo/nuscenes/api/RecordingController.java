package com.example.demo.nuscenes.api;
import com.example.demo.nuscenes.dto.RecordingDtos.*;
import com.example.demo.nuscenes.service.RecordingService;
import java.io.IOException;
import java.nio.file.Files;
import java.util.List;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
@RestController
@RequestMapping("/api")
public class RecordingController {
 private final RecordingService recordings;
 public RecordingController(RecordingService recordings) { this.recordings=recordings; }
 /** 202 new PENDING recording, 200 when a live (non-FAILED) recording for the same scene/job/export version is reused. */
 @PostMapping("/scenes/{sceneId}/recordings") public ResponseEntity<Created> create(@PathVariable long sceneId,@RequestBody(required=false) CreateRequest body) {
  var created=recordings.create(sceneId,body==null?null:body.jobId(),body==null?null:body.compareJobId());
  return ResponseEntity.status(created.reused()?HttpStatus.OK:HttpStatus.ACCEPTED).body(created);
 }
 @GetMapping("/scenes/{sceneId}/recordings") public List<Recording> list(@PathVariable long sceneId) { return recordings.list(sceneId); }
 @GetMapping("/recordings/{id}") public Recording get(@PathVariable long id) { return recordings.get(id); }
 /** FileSystemResource body: Spring MVC answers Range requests with 206. */
 @GetMapping("/recordings/{id}/content") public ResponseEntity<Resource> content(@PathVariable long id) {
  var file=recordings.content(id);
  try {
   return ResponseEntity.ok().contentType(MediaType.APPLICATION_OCTET_STREAM).contentLength(Files.size(file)).header("X-Content-Type-Options","nosniff").body(new FileSystemResource(file));
  } catch(IOException e) { throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Recording file unavailable"); }
 }
}
