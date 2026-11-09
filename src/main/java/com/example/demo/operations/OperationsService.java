package com.example.demo.operations;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

@Service
public class OperationsService {
 private final JdbcClient jdbc;
 private final AtomicInteger activeWrites=new AtomicInteger();
 public OperationsService(JdbcClient jdbc) { this.jdbc=jdbc; }
 public void enterWrite() { activeWrites.incrementAndGet(); }
 public void leaveWrite() { activeWrites.decrementAndGet(); }
 public boolean maintenance() { return jdbc.sql("SELECT maintenance FROM deployment_control WHERE id=1").query(Boolean.class).single(); }
 public void maintenance(boolean value) {
  // UPDATE waits for claim transactions holding FOR SHARE; a prior claim is then visible as RUNNING.
  jdbc.sql("UPDATE deployment_control SET maintenance=:value WHERE id=1").param("value",value).update();
 }
 public State state() {
  return new State(maintenance(),activeWrites.get(),
   jdbc.sql("SELECT count(*) FROM auto_label_job WHERE status='RUNNING'").query(Long.class).single(),
   jdbc.sql("SELECT count(*) FROM scene_recording WHERE status='RUNNING'").query(Long.class).single());
 }
 public record State(boolean maintenance,int activeWrites,long runningLabels,long runningRecordings) {}
}
