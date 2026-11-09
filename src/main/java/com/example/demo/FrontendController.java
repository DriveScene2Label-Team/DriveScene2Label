package com.example.demo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/** React routes must also work when opened directly or refreshed in the deployed JAR. */
@Controller
public class FrontendController {
 @GetMapping({"/scenes", "/scenes/{id:[0-9]+}", "/compare", "/labels"})
 public String index() { return "forward:/index.html"; }
}
