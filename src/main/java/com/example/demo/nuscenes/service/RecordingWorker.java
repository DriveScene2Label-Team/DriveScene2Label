package com.example.demo.nuscenes.service;
import com.example.demo.nuscenes.client.RecordingClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;
/** Polls PENDING recordings. Claim and READY/FAILED are short DB statements; no transaction is held during the AI export call. */
@Component
@ConditionalOnProperty(name="recording.worker.enabled",havingValue="true",matchIfMissing=true)
public class RecordingWorker {
 private static final Logger log=LoggerFactory.getLogger(RecordingWorker.class);
 private final RecordingService recordings; private final RecordingClient ai;
 public RecordingWorker(RecordingService recordings,RecordingClient ai) { this.recordings=recordings;this.ai=ai; }
 @Scheduled(fixedDelayString="${recording.poll-delay-ms:1000}",scheduler="recordingScheduler")
 public void runNextRecording() {
  try {
   var claimed=recordings.claim(); if(claimed.isEmpty()) return; var work=claimed.get();
   try {
    log.info("[RERUN] recording={} scene={} job={} started",work.id(),work.sceneToken(),work.jobId());
    long started=System.nanoTime();
    var request=recordings.request(work);
    log.info("[RERUN_STAGE] recording={} stage=request_build wall_ms={}",work.id(),(System.nanoTime()-started)/1_000_000);
    started=System.nanoTime();
    var result=ai.export(request);
    log.info("[RERUN_STAGE] recording={} stage=ai_export wall_ms={}",work.id(),(System.nanoTime()-started)/1_000_000);
    started=System.nanoTime();
    recordings.complete(work,request,result);
    log.info("[RERUN_STAGE] recording={} stage=result_storage wall_ms={}",work.id(),(System.nanoTime()-started)/1_000_000);
    log.info("[RERUN] recording={} ready samples={}",work.id(),request.samples().size());
   } catch(Exception e) {
    log.warn("[RERUN] recording={} failed: {}",work.id(),e.toString());
    var f=classify(e);
    recordings.fail(work,f.code(),f.reason());
   }
  } catch(Exception e) { log.error("Recording worker iteration failed",e); }
 }
 public record Failure(String code,String reason) {}
 static Failure classify(Exception e) {
  if(e instanceof RecordingService.Invalid inv) return new Failure(inv.code(),e.getMessage());
  if(e instanceof RestClientException) {
   String code=com.example.demo.nuscenes.client.AiErrors.code(e); int http=com.example.demo.nuscenes.client.AiErrors.httpStatus(e);
   String reason=switch(code) {
    case "AI_ENDPOINT_UNSUPPORTED"->"AI server has no /recordings endpoint (HTTP 404)";
    case "AI_UNREACHABLE"->"AI recording request failed: server unreachable";
    case "AI_TIMEOUT"->"AI recording request timed out";
    case "AI_HTTP_ERROR"->"AI recording export failed (HTTP "+http+")";
    default->"AI recording export failed (HTTP "+http+" "+code+")";
   };
   return new Failure(code,reason);
  }
  return new Failure("RESULT_STORAGE_FAILED","Recording validation or storage failed");
 }
}
