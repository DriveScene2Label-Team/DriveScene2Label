package com.example.demo;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
/** Fake AI /capabilities and /health for Spring tests. MODE selects the answer; REFRESHES counts refresh=true calls. */
final class FakeAi {
 private FakeAi() {}
 /** ready | vespa-unconfigured | vespa-configured | legacy | missing (404 everywhere) | down (500) */
 static final AtomicReference<String> CAPS=new AtomicReference<>("ready");
 static final AtomicInteger REFRESHES=new AtomicInteger();
 static void install(HttpServer server) {
  server.createContext("/capabilities",ex->{
   if(ex.getRequestURI().getQuery()!=null && ex.getRequestURI().getQuery().contains("refresh=true")) REFRESHES.incrementAndGet();
   String mode=CAPS.get();
   if(mode.equals("legacy") || mode.equals("missing")) { send(ex,404,"{\"detail\":\"Not Found\"}"); return; }
   if(mode.equals("down")) { send(ex,500,"Internal Server Error"); return; }
   boolean refreshed=ex.getRequestURI().getQuery()!=null && ex.getRequestURI().getQuery().contains("refresh=true");
   String vespa=switch(mode) {
    case "vespa-unconfigured"->"\"state\":\"UNAVAILABLE\",\"reasonCode\":\"VESPA_NOT_CONFIGURED\"";
    case "vespa-configured"->refreshed?"\"state\":\"UNAVAILABLE\",\"reasonCode\":\"VESPA_RUNTIME_NOT_READY\"":"\"state\":\"CONFIGURED\",\"reasonCode\":\"EXECUTOR_NOT_CHECKED\"";
    default->"\"state\":\"READY\",\"reasonCode\":null";
   };
   String now=OffsetDateTime.now().toString(), later=OffsetDateTime.now().plusMinutes(10).toString();
   send(ex,200,"{\"schemaVersion\":1,\"service\":\"drivescene-ai\",\"checkedAt\":\""+now+"\","
    +"\"clip\":{\"state\":\"READY\",\"reasonCode\":null,\"modelName\":\"ViT-L-14-quickgelu/openai\",\"imagePreprocess\":[\"lr-square-crop-mean\",\"openclip-eval-224-centercrop\"],\"dimension\":768},"
    +"\"vespa\":{"+vespa+",\"executor\":\"local\",\"datasetVersion\":\"v1.0-mini\",\"metadataChecksum\":null,\"checkedAt\":\""+now+"\",\"expiresAt\":\""+later+"\"},"
    +"\"recording\":{\"state\":\"READY\",\"reasonCode\":null,\"sdkVersion\":\"0.38.1\",\"expectedSdkVersion\":\"0.38.1\",\"exportVersion\":\"ds2l-rrd-v3\",\"checkedAt\":\""+now+"\",\"expiresAt\":\""+later+"\"}}");
  });
  server.createContext("/health",ex->{
   if(CAPS.get().equals("missing")) { send(ex,404,"{\"detail\":\"Not Found\"}"); return; }
   send(ex,200,"{\"status\":\"ok\",\"service\":\"recording-harness\",\"inference\":{\"clip\":\"not_loaded\",\"vespa\":\"not_configured\",\"recording\":\"configured\"}}");
  });
 }
 static void send(HttpExchange ex,int status,String body) throws IOException {
  byte[] bytes=body.getBytes(StandardCharsets.UTF_8);
  ex.getResponseHeaders().set("Content-Type","application/json"); ex.sendResponseHeaders(status,bytes.length);
  try(var out=ex.getResponseBody()) { out.write(bytes); }
 }
}
