package com.example.demo.nuscenes.domain;
public record Category(
    Long id,
    Long datasetId,
    String token,
    String name,
    String description
) {}
