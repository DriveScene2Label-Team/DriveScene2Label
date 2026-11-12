package com.example.demo;

import com.example.demo.operations.ApiTimingFilter;
import jakarta.servlet.ServletException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.slf4j.MDC;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.servlet.HandlerMapping;
import static org.assertj.core.api.Assertions.*;

@ExtendWith(OutputCaptureExtension.class)
class ApiTimingFilterTests {
 @Test void failedRequestKeepsTraceButNeverLogsQueryOrCookie(CapturedOutput output) {
  var request=new MockHttpServletRequest("GET","/api/search");
  request.setQueryString("q=private-search");request.addHeader("Cookie","secret-session");request.addHeader("X-Request-ID","user-supplied");
  request.setAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE,"/api/search");
  var response=new MockHttpServletResponse();MDC.put("requestId","outer-context");
  try {
   assertThatThrownBy(()->new ApiTimingFilter().doFilter(request,response,(req,res)->{throw new ServletException("private-error");})).isInstanceOf(ServletException.class);
   assertThat(response.getHeader("X-Request-ID")).isNotBlank().isNotEqualTo("user-supplied");
   assertThat(output.getOut()).contains("status=500","route=/api/search").doesNotContain("private-search","secret-session","private-error");
   assertThat(MDC.get("requestId")).isEqualTo("outer-context");
  } finally { MDC.remove("requestId"); }
 }
}
