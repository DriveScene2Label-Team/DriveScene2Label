package com.example.demo.labels;

import jakarta.validation.Valid;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import static com.example.demo.labels.LabelDtos.*;

@RestController
@RequestMapping("/api/label-documents")
public class LabelController {
 private final LabelService labels;
 public LabelController(LabelService labels) { this.labels=labels; }
 @GetMapping public List<Summary> list(@RequestParam(defaultValue="0") int page) { return labels.list(page); }
 @PostMapping(value="/upload",consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
 @ResponseStatus(HttpStatus.CREATED)
 public Detail upload(@RequestParam MultipartFile file,@RequestParam(required=false) Long datasetId) throws IOException {
  if(file.getSize()>20L*1024*1024) throw new org.springframework.web.server.ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,"라벨 JSON은 20MB 이하만 지원합니다.");
  return labels.upload(file.getOriginalFilename(),file.getBytes(),datasetId);
 }
 @PostMapping("/from-job/{jobId}") public Detail fromJob(@PathVariable long jobId) { return labels.fromJob(jobId); }
 @GetMapping("/{id}") public Detail get(@PathVariable long id,@RequestParam(required=false) Integer revision) { return labels.get(id,revision); }
 @GetMapping("/{id}/revisions") public List<Revision> history(@PathVariable long id) { return labels.history(id); }
 @PostMapping("/{id}/revisions") @ResponseStatus(HttpStatus.CREATED)
 public Detail save(@PathVariable long id,@Valid @RequestBody Save body) { return labels.save(id,body); }
 @GetMapping("/{id}/download") public ResponseEntity<Object> download(@PathVariable long id,@RequestParam(required=false) Integer revision) {
  var detail=labels.get(id,revision);
  return ResponseEntity.ok().headers(downloadHeaders("labels-"+id+"-v"+detail.revision()+".json")).body(detail.data());
 }
 @GetMapping("/{id}/original") public ResponseEntity<byte[]> original(@PathVariable long id) {
  return ResponseEntity.ok().headers(downloadHeaders("labels-"+id+"-original.json")).body(labels.original(id).getBytes(StandardCharsets.UTF_8));
 }
 private HttpHeaders downloadHeaders(String filename) {
  var headers=new HttpHeaders(); headers.setContentType(MediaType.APPLICATION_JSON);
  headers.setContentDisposition(ContentDisposition.attachment().filename(filename).build());
  headers.set("X-Content-Type-Options","nosniff"); headers.setCacheControl("no-store");
  return headers;
 }
 @ExceptionHandler(org.springframework.orm.ObjectOptimisticLockingFailureException.class)
 public ResponseEntity<com.example.demo.nuscenes.api.ApiErrors.Error> conflict() {
  return ResponseEntity.status(409).body(new com.example.demo.nuscenes.api.ApiErrors.Error("REVISION_CONFLICT","다른 창에서 저장했습니다. 최신 버전을 다시 열어 주세요."));
 }
}
