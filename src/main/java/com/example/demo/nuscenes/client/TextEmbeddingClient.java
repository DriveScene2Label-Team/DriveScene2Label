package com.example.demo.nuscenes.client;

import com.example.demo.nuscenes.dto.TextEmbeddingRequest;
import com.example.demo.nuscenes.dto.TextEmbeddingResponse;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

@Component
public class TextEmbeddingClient {
 private final RestClient client;
 public TextEmbeddingClient(@Value("${ai-server.base-url}") String baseUrl,
   @Value("${ai-server.connect-timeout:5s}") Duration connectTimeout,
   @Value("${ai-server.read-timeout:30s}") Duration readTimeout) {
  var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(connectTimeout).build());
  factory.setReadTimeout(readTimeout);
  client=RestClient.builder().baseUrl(baseUrl).requestFactory(factory).build();
 }
 public TextEmbeddingResponse image(String path,String preprocess) {
  return image(path,preprocess,null);
 }
 public TextEmbeddingResponse image(String path,String preprocess,String datasetKey) {
  try {
   var body=new java.util.HashMap<String,String>(); body.put("image_path",path); body.put("preprocess",preprocess);
   if(datasetKey!=null) body.put("dataset_key",datasetKey);
   return client.post().uri("/embedding/image").contentType(MediaType.APPLICATION_JSON)
    .body(body).retrieve().body(TextEmbeddingResponse.class);
  } catch(ResourceAccessException e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"AI server unavailable or timed out",e);
  } catch(org.springframework.web.client.HttpClientErrorException e) {
   if(e.getStatusCode().value()==404) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Image not found on AI server",e);
   throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI image embedding request failed",e);
  } catch(RestClientException e) { throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI image embedding request failed",e); }
 }
 public TextEmbeddingResponse embed(String text) {
  try {
   return client.post().uri("/embedding/text").contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON).body(new TextEmbeddingRequest(text))
    .retrieve().body(TextEmbeddingResponse.class);
  } catch(ResourceAccessException e) {
   throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"AI server unavailable or timed out",e);
  } catch(RestClientException e) {
   throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,"AI text embedding request failed",e);
  }
 }
}
