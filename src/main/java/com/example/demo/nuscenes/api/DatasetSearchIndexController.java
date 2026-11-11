package com.example.demo.nuscenes.api;
import com.example.demo.nuscenes.service.DatasetSearchIndexService;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/datasets/{id}/search-index")
public class DatasetSearchIndexController {
 private final DatasetSearchIndexService service;
 public DatasetSearchIndexController(DatasetSearchIndexService service) { this.service=service; }
 @GetMapping public DatasetSearchIndexService.Status status(@PathVariable long id) { return service.status(id); }
 @PostMapping public DatasetSearchIndexService.Status create(@PathVariable long id) { return service.enqueue(id); }
}
