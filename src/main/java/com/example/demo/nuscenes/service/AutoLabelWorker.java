package com.example.demo.nuscenes.service;
import com.example.demo.nuscenes.client.AiErrors;
import com.example.demo.nuscenes.client.AutoLabelClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.TransactionException;
import org.springframework.web.client.RestClientException;
/** Polls PENDING jobs on its own single-thread scheduler, so a long VESPA call never blocks the recording worker. */
@Component
@ConditionalOnProperty(name="auto-label.worker.enabled",havingValue="true",matchIfMissing=true)
public class AutoLabelWorker {
 private static final Logger log=LoggerFactory.getLogger(AutoLabelWorker.class);
 private final AutoLabelService jobs; private final AutoLabelClient ai;
 public AutoLabelWorker(AutoLabelService jobs,AutoLabelClient ai) { this.jobs=jobs;this.ai=ai; }
 @Scheduled(fixedDelayString="${auto-label.poll-delay-ms:1000}",scheduler="autoLabelScheduler")
 public void runNextJob() {
  try {
   var pending=jobs.claim(); if(pending.isEmpty()) return; var job=pending.get();
   try {
    log.info("[VESPA] job={} scene={} started",job.id(),job.sceneName());
    long aiStarted=System.nanoTime();
    var result=ai.run(job);
    log.info("[VESPA_STAGE] job={} scene={} stage=ai_request event=completed wall_ms={}",job.id(),job.sceneName(),(System.nanoTime()-aiStarted)/1_000_000);
    long storageStarted=System.nanoTime();
    log.info("[VESPA_STAGE] job={} scene={} stage=result_storage event=started",job.id(),job.sceneName());
    jobs.complete(job,result);
    log.info("[VESPA_STAGE] job={} scene={} stage=result_storage event=completed wall_ms={}",job.id(),job.sceneName(),(System.nanoTime()-storageStarted)/1_000_000);
    log.info("[VESPA] job={} completed boxes={}",job.id(),result.results().values().stream().mapToInt(java.util.List::size).sum());
   }
   catch(Exception e) {
    var f=classify(e);
    log.error("Auto-label job {} failed code={} http={}",job.id(),f.code(),AiErrors.httpStatus(e),e);
    jobs.fail(job,f.code(),f.reason());
   }
  } catch(Exception e) { log.error("Auto-label worker iteration failed",e); }
 }
 public record Failure(String code,String reason) {}
 /** Keeps where it failed: AI route missing, connection, timeout, AI-reported VESPA failure, result validation or storage. */
 static Failure classify(Exception e) {
  if(e instanceof RestClientException) {
   String code=AiErrors.code(e); int http=AiErrors.httpStatus(e);
   String reason=switch(code) {
    case "AI_ENDPOINT_UNSUPPORTED"->"AI server has no /auto-label endpoint (HTTP 404)";
    case "AI_UNREACHABLE"->"AI server unreachable";
    case "AI_TIMEOUT"->"AI request timed out";
    case "AI_HTTP_ERROR"->"AI request failed (HTTP "+http+")";
    default->"AI reported "+code+(http>0?" (HTTP "+http+")":"");
   };
   return new Failure(code,reason);
  }
  if(e instanceof DataAccessException || e instanceof TransactionException) return new Failure("RESULT_STORAGE_FAILED","Result storage failed");
  if(e instanceof IllegalArgumentException) return new Failure("RESULT_VALIDATION_FAILED","AI result validation failed");
  return new Failure("RESULT_STORAGE_FAILED","Result validation or storage failed");
 }
}
