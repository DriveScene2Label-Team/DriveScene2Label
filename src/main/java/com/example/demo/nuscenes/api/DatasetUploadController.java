package com.example.demo.nuscenes.api;

import com.example.demo.nuscenes.service.DatasetUploadService;
import com.example.demo.nuscenes.storage.DatasetStorage;
import com.example.demo.nuscenes.storage.DatasetArchive;
import java.io.IOException;
import java.nio.file.Files;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/dataset-uploads")
public class DatasetUploadController {
 private final DatasetUploadService uploads;
 private final DatasetStorage storage;
 private final JdbcClient jdbc;
 public DatasetUploadController(DatasetUploadService uploads,DatasetStorage storage,JdbcClient jdbc) { this.uploads=uploads;this.storage=storage;this.jdbc=jdbc; }
 @PostMapping(consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
 @ResponseStatus(HttpStatus.CREATED)
 public DatasetUploadService.Uploaded upload(@RequestParam MultipartFile file) throws IOException { return uploads.upload(file); }
 @GetMapping("/{datasetId}/original")
 public ResponseEntity<FileSystemResource> original(@PathVariable long datasetId) throws IOException {
  String key=jdbc.sql("SELECT root_relative_path FROM dataset WHERE id=:id AND storage_key='uploads'").param("id",datasetId).query(String.class).optional()
   .orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"업로드 데이터셋을 찾을 수 없습니다."));
  var file=storage.archive(key);
  if(!Files.isRegularFile(file)) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"원본 압축 파일이 없습니다.");
  return ResponseEntity.ok().contentType(MediaType.APPLICATION_OCTET_STREAM).contentLength(Files.size(file))
   .header(HttpHeaders.CONTENT_DISPOSITION,"attachment; filename=\"dataset-"+datasetId+DatasetArchive.detect(file).extension+"\"").header("X-Content-Type-Options","nosniff").body(new FileSystemResource(file));
 }
}
