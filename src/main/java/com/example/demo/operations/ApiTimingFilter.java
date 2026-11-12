package com.example.demo.operations;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

/** Server boundary only: excludes time spent before arrival at Spring. Never logs query/body/cookies. */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class ApiTimingFilter extends OncePerRequestFilter {
 @Override protected boolean shouldNotFilter(HttpServletRequest request) { return !request.getRequestURI().startsWith("/api/"); }
 @Override protected void doFilterInternal(HttpServletRequest request,HttpServletResponse response,FilterChain chain) throws IOException,ServletException {
  String id=UUID.randomUUID().toString(),previous=MDC.get("requestId");
  MDC.put("requestId",id);response.setHeader("X-Request-ID",id);
  long started=System.nanoTime();boolean failed=false;
  try { chain.doFilter(request,response); }
  catch(IOException|ServletException|RuntimeException error) { failed=true;throw error; }
  finally {
   Object route=request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
   LoggerFactory.getLogger(getClass()).info("[HTTP] request={} method={} route={} status={} wall_ms={}",id,request.getMethod(),route==null?"unmatched":route,failed?500:response.getStatus(),(System.nanoTime()-started)/1_000_000);
   if(previous==null) MDC.remove("requestId");else MDC.put("requestId",previous);
  }
 }
}
