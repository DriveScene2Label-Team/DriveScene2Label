package com.example.demo.nuscenes.config;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
/**
 * One dedicated single-thread scheduler per worker: VESPA (long synchronous AI call) and recording export run in
 * parallel, each with at most one execution. DB claim (SKIP LOCKED + execution token) and the AI-side locks still apply.
 */
@Configuration
@EnableScheduling
public class AutoLabelScheduling {
 @Bean(destroyMethod="shutdown") public ThreadPoolTaskScheduler autoLabelScheduler() { return scheduler("vespa-worker-"); }
 @Bean(destroyMethod="shutdown") public ThreadPoolTaskScheduler recordingScheduler() { return scheduler("recording-worker-"); }
 @Bean(destroyMethod="shutdown") public ThreadPoolTaskScheduler uploadScheduler() { return scheduler("upload-worker-"); }
 @Bean(destroyMethod="shutdown") public ThreadPoolTaskScheduler uploadHeartbeatScheduler() { return scheduler("upload-heartbeat-"); }
 private static ThreadPoolTaskScheduler scheduler(String prefix) {
  var s=new ThreadPoolTaskScheduler(); s.setPoolSize(1); s.setThreadNamePrefix(prefix); s.setWaitForTasksToCompleteOnShutdown(false); return s;
 }
}
