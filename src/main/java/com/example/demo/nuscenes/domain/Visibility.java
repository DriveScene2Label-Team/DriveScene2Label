package com.example.demo.nuscenes.domain;
public record Visibility(
    Long id,
    Long datasetId,
    String token,
    String level,
    String description
) {}
