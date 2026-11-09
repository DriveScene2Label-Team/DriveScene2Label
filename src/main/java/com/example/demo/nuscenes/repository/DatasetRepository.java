package com.example.demo.nuscenes.repository;
import com.example.demo.nuscenes.domain.Dataset;
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;
import org.springframework.data.jpa.repository.Query;
public interface DatasetRepository extends Repository<Dataset, Long> {
 Optional<Dataset> findById(Long id);
 @Query(value="SELECT * FROM dataset ORDER BY id", nativeQuery=true)
 List<Dataset> listAll();
}
