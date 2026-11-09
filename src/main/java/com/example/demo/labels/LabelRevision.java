package com.example.demo.labels;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

@Entity
@Table(name="label_revision")
public class LabelRevision {
 @Id @GeneratedValue(strategy=GenerationType.IDENTITY) Long id;
 @ManyToOne(fetch=FetchType.LAZY, optional=false)
 @JoinColumn(name="document_id") LabelDocument document;
 int number;
 @Column(nullable=false, columnDefinition="text") String payload;
 @Column(nullable=false, length=500) String note;
 @Column(nullable=false) OffsetDateTime createdAt;
 protected LabelRevision() {}
}
