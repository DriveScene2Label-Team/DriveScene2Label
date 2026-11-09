package com.example.demo.nuscenes.domain;

import com.fasterxml.jackson.annotation.JsonAutoDetect;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.experimental.Accessors;

@Entity
@Table(name="scene")
@Getter
@Accessors(fluent=true)
@NoArgsConstructor(access=AccessLevel.PROTECTED)
@JsonAutoDetect(fieldVisibility=JsonAutoDetect.Visibility.ANY, getterVisibility=JsonAutoDetect.Visibility.NONE, isGetterVisibility=JsonAutoDetect.Visibility.NONE)
public class Scene {
 @Id private Long id;
 private Long datasetId;
 private String token;
 private String logToken;
 private String name;
 private String description;
 private Integer nbrSamples;
 private String firstSampleToken;
 private String lastSampleToken;
}
