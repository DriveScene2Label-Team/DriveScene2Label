package com.example.demo.nuscenes.service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
@Component
@ConditionalOnProperty(name="uploads.worker.enabled",havingValue="true",matchIfMissing=true)
public class ChunkedDatasetUploadWorker {
 private final ChunkedDatasetUploadService service;
 private volatile ChunkedDatasetUploadService.Row active;
 public ChunkedDatasetUploadWorker(ChunkedDatasetUploadService service) { this.service=service; }
 @Scheduled(fixedDelay=1000,scheduler="uploadScheduler") public void tick() {
  try { service.claim().ifPresent(work->{ active=work; try { service.process(work); } finally { active=null; } }); }
  catch(Exception error) { org.slf4j.LoggerFactory.getLogger(getClass()).error("Upload worker iteration failed",error); }
 }
 @Scheduled(fixedDelay=15000,scheduler="uploadHeartbeatScheduler") public void heartbeat() {
  var current=active;
  if(current!=null) try { service.heartbeat(current); } catch(Exception error) { org.slf4j.LoggerFactory.getLogger(getClass()).error("Upload heartbeat failed",error); }
 }
}
