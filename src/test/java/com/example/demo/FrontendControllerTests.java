package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class FrontendControllerTests {
 @Test void browserRoutesSurviveReloadWithoutCapturingApiRequests() throws Exception {
  var mvc=MockMvcBuilders.standaloneSetup(new FrontendController()).build();
  for(String path:new String[]{"/scenes", "/scenes/42?dataset=1", "/compare", "/labels?id=1"}) {
   mvc.perform(get(path)).andExpect(status().isOk()).andExpect(forwardedUrl("/index.html"));
  }
  mvc.perform(get("/api/missing")).andExpect(status().isNotFound());
 }
}
