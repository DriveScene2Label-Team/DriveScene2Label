package com.example.demo.nuscenes.domain;

import com.fasterxml.jackson.annotation.JsonAutoDetect;
import jakarta.persistence.Entity;
import jakarta.persistence.Column;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.experimental.Accessors;

@Entity
@Table(name="gt_annotation")
@Getter
@Accessors(fluent=true)
@NoArgsConstructor(access=AccessLevel.PROTECTED)
@JsonAutoDetect(fieldVisibility=JsonAutoDetect.Visibility.ANY, getterVisibility=JsonAutoDetect.Visibility.NONE, isGetterVisibility=JsonAutoDetect.Visibility.NONE)
public class GtAnnotation {
 @Id private Long id;
 private Long datasetId;
 private String token;
 private String sampleToken;
 private String instanceToken;
 private String visibilityToken;
 @Column(name="center_x") private Double centerX;
 @Column(name="center_y") private Double centerY;
 @Column(name="center_z") private Double centerZ;
 @Column(name="size_w") private Double sizeW;
 @Column(name="size_l") private Double sizeL;
 @Column(name="size_h") private Double sizeH;
 @Column(name="rotation_w") private Double rotationW;
 @Column(name="rotation_x") private Double rotationX;
 @Column(name="rotation_y") private Double rotationY;
 @Column(name="rotation_z") private Double rotationZ;
 private Integer numLidarPts;
 private Integer numRadarPts;
 private String prevToken;
 private String nextToken;
}
