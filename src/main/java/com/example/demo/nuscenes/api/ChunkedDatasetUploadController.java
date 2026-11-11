package com.example.demo.nuscenes.api;
import com.example.demo.nuscenes.service.ChunkedDatasetUploadService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.io.IOException;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/dataset-uploads/sessions")
public class ChunkedDatasetUploadController {
 public record Create(@NotBlank @Size(max=255) String filename,@Positive long sizeBytes) {}
 private final ChunkedDatasetUploadService service;
 public ChunkedDatasetUploadController(ChunkedDatasetUploadService service) { this.service=service; }
 @PostMapping @ResponseStatus(HttpStatus.CREATED) public ChunkedDatasetUploadService.Status create(@Valid @RequestBody Create body) throws IOException { return service.create(body.filename(),body.sizeBytes()); }
 @GetMapping("/{id}") public ChunkedDatasetUploadService.Status status(@PathVariable UUID id) { return service.status(id); }
 @PostMapping(value="/{id}/parts",consumes=MediaType.APPLICATION_OCTET_STREAM_VALUE)
 public ChunkedDatasetUploadService.Status part(@PathVariable UUID id,@RequestParam long offset,HttpServletRequest request) throws IOException { return service.part(id,offset,request.getInputStream()); }
 @PostMapping("/{id}/complete") @ResponseStatus(HttpStatus.ACCEPTED)
 public ChunkedDatasetUploadService.Status complete(@PathVariable UUID id) { return service.complete(id); }
}
