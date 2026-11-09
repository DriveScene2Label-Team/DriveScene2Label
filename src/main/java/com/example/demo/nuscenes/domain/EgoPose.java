package com.example.demo.nuscenes.domain;
public record EgoPose(
    Long id,
    Long datasetId,
    String token,
    Long timestampUs,
    Double translationX,
    Double translationY,
    Double translationZ,
    Double rotationW,
    Double rotationX,
    Double rotationY,
    Double rotationZ
) {}
