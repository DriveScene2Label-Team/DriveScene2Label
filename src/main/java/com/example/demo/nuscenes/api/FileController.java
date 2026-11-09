package com.example.demo.nuscenes.api;

import com.example.demo.nuscenes.storage.DatasetStorage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class FileController {
 private final JdbcClient jdbc;
 private final DatasetStorage files;
 public FileController(JdbcClient jdbc, DatasetStorage files) { this.jdbc=jdbc; this.files=files; }
 @GetMapping("/sensor-files/{id}/content") public ResponseEntity<Resource> sensor(@PathVariable long id) { return content("sample_data", id); }
 @GetMapping("/maps/{id}/content") public ResponseEntity<Resource> map(@PathVariable long id) { return content("map_asset", id); }
 private ResponseEntity<Resource> content(String table, long id) {
  // table is an internal constant from the two handlers, never request input.
  var source=jdbc.sql("SELECT a.relative_path,d.storage_key,d.root_relative_path FROM " + table + " a JOIN dataset d ON d.id=a.dataset_id WHERE a.id=:id")
   .param("id",id).query(Source.class).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"File not found"));
  String path=source.relativePath();
  try {
   Path file=files.files(source.storageKey(),source.rootRelativePath()).resolve(path);
   MediaType type=path.endsWith(".jpg") ? MediaType.IMAGE_JPEG : path.endsWith(".png") ? MediaType.IMAGE_PNG : MediaType.APPLICATION_OCTET_STREAM;
   return ResponseEntity.ok().contentType(type).contentLength(Files.size(file)).header("X-Content-Type-Options","nosniff").body(new FileSystemResource(file));
  } catch(IOException e) { throw new ResponseStatusException(HttpStatus.NOT_FOUND,"Dataset file unavailable"); }
 }
 private record Source(String relativePath,String storageKey,String rootRelativePath) {}
}
