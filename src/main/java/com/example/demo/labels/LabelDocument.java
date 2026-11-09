package com.example.demo.labels;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

@Entity
@Table(name="label_document")
public class LabelDocument {
 @Id @GeneratedValue(strategy=GenerationType.IDENTITY) Long id;
 @Column(nullable=false) String name;
 Long datasetId;
 Long sourceJobId;
 @Column(nullable=false) String sourceType;
 @Column(nullable=false, columnDefinition="text") String originalText;
 int headRevision;
 @Version long version;
 @Column(nullable=false) OffsetDateTime createdAt;
 protected LabelDocument() {}
}
