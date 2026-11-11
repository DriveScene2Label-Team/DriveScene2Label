package com.example.demo.nuscenes.client;
import com.example.demo.nuscenes.dto.AutoLabelDtos.*;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
@Component
public class AutoLabelClient {
 private final RestClient client;
 public AutoLabelClient(@Value("${ai-server.base-url}") String url,@Value("${ai-server.connect-timeout:5s}") Duration connect,
   @Value("${auto-label.read-timeout:7300s}") Duration read) {
  var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(connect).build()); factory.setReadTimeout(read);
  client=RestClient.builder().baseUrl(url).requestFactory(factory).build();
 }
 public AiResponse run(Work job) {
  return client.post().uri("/auto-label").contentType(MediaType.APPLICATION_JSON).accept(MediaType.APPLICATION_JSON)
   .body(new AiRequest(job.sceneName(),Integer.parseInt(job.mappingName().replace("class","")),job.id(),job.executionToken(),job.datasetKey(),job.datasetVersion(),job.sourceArtifactPath(),references(job.referenceFrames())))
   .retrieve().body(AiResponse.class);
 }
 private static java.util.Map<String,String> references(String value) {
  var result=new java.util.HashMap<String,String>();
  if(value!=null) { var tree=new tools.jackson.databind.ObjectMapper().readTree(value); tree.properties().forEach(entry->result.put(entry.getKey(),entry.getValue().asString())); }
  return result;
 }
}
