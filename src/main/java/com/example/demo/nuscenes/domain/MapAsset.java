package com.example.demo.nuscenes.domain;
public record MapAsset(
    Long id,
    Long datasetId,
    String token,
    String relativePath,
    String category
) {}
