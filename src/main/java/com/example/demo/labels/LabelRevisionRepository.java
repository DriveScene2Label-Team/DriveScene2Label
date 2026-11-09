package com.example.demo.labels;

import java.util.*;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LabelRevisionRepository extends JpaRepository<LabelRevision,Long> {
 Optional<LabelRevision> findByDocumentIdAndNumber(long documentId,int number);
 List<LabelDtos.Revision> findByDocumentIdOrderByNumberDesc(long documentId);
}
