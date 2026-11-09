package com.example.demo.labels;

import java.util.*;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LabelDocumentRepository extends JpaRepository<LabelDocument,Long> {
 List<LabelDtos.Summary> findAllByOrderByCreatedAtDescIdDesc(Pageable page);
 Optional<LabelDocument> findBySourceJobId(long jobId);
}
