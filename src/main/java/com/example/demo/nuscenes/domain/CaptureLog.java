package com.example.demo.nuscenes.domain;
public record CaptureLog(
    Long id,
    Long datasetId,
    String token,
    String logfile,
    String location,
    String dateCaptured,
    String vehicle
) {}
