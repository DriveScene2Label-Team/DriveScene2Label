package com.example.demo.operations;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Set;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class MaintenanceFilter extends OncePerRequestFilter {
 private final OperationsService operations;
 public MaintenanceFilter(OperationsService operations) { this.operations=operations; }
 @Override protected boolean shouldNotFilter(HttpServletRequest request) {
  return !request.getRequestURI().startsWith("/api/") || Set.of("GET","HEAD","OPTIONS").contains(request.getMethod());
 }
 @Override protected void doFilterInternal(HttpServletRequest request,HttpServletResponse response,FilterChain chain) throws ServletException,IOException {
  // Count before checking the shared gate so a drain never misses an admitted request.
  operations.enterWrite();
  try {
   if(operations.maintenance()) {
    response.setStatus(503); response.setContentType("application/json"); response.setHeader("Retry-After","60");
    response.getWriter().write("{\"message\":\"Environment is stopping. Saving is temporarily unavailable.\"}"); return;
   }
   chain.doFilter(request,response);
  } finally { operations.leaveWrite(); }
 }
}
