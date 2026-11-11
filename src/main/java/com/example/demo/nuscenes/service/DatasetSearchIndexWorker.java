package com.example.demo.nuscenes.service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
@Component
@ConditionalOnProperty(name="embedding.index-worker.enabled",havingValue="true",matchIfMissing=true)
public class DatasetSearchIndexWorker {
 private final DatasetSearchIndexService service;
 public DatasetSearchIndexWorker(DatasetSearchIndexService service) { this.service=service; }
 @Scheduled(fixedDelayString="${embedding.index-poll-delay-ms:1000}",scheduler="autoLabelScheduler")
 public void tick() {
  try { service.claim().ifPresent(service::process); }
  catch(Exception error) { org.slf4j.LoggerFactory.getLogger(getClass()).error("Search index worker failed",error); }
 }
}
