package com.example.demo.nuscenes.domain;
public record Attribute(
    Long id,
    Long datasetId,
    String token,
    String name,
    String description
) {}
