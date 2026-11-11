package com.example.demo.nuscenes.api;
import com.example.demo.nuscenes.dto.AutoLabelDtos.*;
import com.example.demo.nuscenes.service.AutoLabelService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/auto-label/jobs")
public class AutoLabelController {
 private final AutoLabelService jobs;
 public AutoLabelController(AutoLabelService jobs) { this.jobs=jobs; }
 @PostMapping @ResponseStatus(HttpStatus.ACCEPTED)
 public Created create(@Valid @RequestBody CreateRequest body,@RequestHeader(value="Idempotency-Key",required=false) String key) { var result=jobs.create(body,key); org.slf4j.LoggerFactory.getLogger(getClass()).info("[VESPA] job={} status={} accepted",result.jobId(),result.status()); return result; }
 @GetMapping("/{id}/results") public Results results(@PathVariable long id) { return jobs.results(id); }
 @PostMapping("/{id}/postprocess") @ResponseStatus(HttpStatus.ACCEPTED)
 public Created postprocess(@PathVariable long id,@Valid @RequestBody PostprocessRequest body,@RequestHeader(value="Idempotency-Key",required=false) String key) { return jobs.postprocess(id,body,key); }
 @GetMapping("/{id}") public JobStatus status(@PathVariable long id) { return jobs.status(id); }
}
