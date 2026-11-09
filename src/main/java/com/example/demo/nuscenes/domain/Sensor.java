package com.example.demo.nuscenes.domain;
public record Sensor(
    Long id,
    Long datasetId,
    String token,
    String channel,
    String modality
) {}
