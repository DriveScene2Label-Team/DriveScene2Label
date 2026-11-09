package com.example.demo.operations;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/internal/operations")
public class OperationsController {
 private final OperationsService operations;
 private final byte[] token;
 public OperationsController(OperationsService operations,@Value("${operations.token:}") String token) {
  this.operations=operations;this.token=token.getBytes(StandardCharsets.UTF_8);
 }
 private void authorize(String provided) {
  if(token.length==0) throw new ResponseStatusException(HttpStatus.NOT_FOUND);
  if(provided==null || !MessageDigest.isEqual(token,provided.getBytes(StandardCharsets.UTF_8))) throw new ResponseStatusException(HttpStatus.FORBIDDEN);
 }
 @GetMapping public OperationsService.State state(@RequestHeader(value="X-Operations-Token",required=false) String provided) {
  authorize(provided); return operations.state();
 }
 @PostMapping("/quiesce") public OperationsService.State quiesce(@RequestHeader(value="X-Operations-Token",required=false) String provided) {
  authorize(provided); operations.maintenance(true); return operations.state();
 }
 @PostMapping("/resume") public OperationsService.State resume(@RequestHeader(value="X-Operations-Token",required=false) String provided) {
  authorize(provided); operations.maintenance(false); return operations.state();
 }
}
