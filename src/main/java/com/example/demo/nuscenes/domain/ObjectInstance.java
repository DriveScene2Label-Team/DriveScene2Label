package com.example.demo.nuscenes.domain;
public record ObjectInstance(
    Long id,
    Long datasetId,
    String token,
    String categoryToken,
    Integer nbrAnnotations,
    String firstAnnotationToken,
    String lastAnnotationToken
) {}
