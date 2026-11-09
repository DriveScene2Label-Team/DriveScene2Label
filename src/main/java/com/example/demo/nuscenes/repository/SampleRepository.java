package com.example.demo.nuscenes.repository;
import com.example.demo.nuscenes.domain.Sample;
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;
import org.springframework.data.jpa.repository.Query;
public interface SampleRepository extends Repository<Sample, Long> {
 Optional<Sample> findById(Long id);
 @Query(value="SELECT * FROM sample WHERE dataset_id = :datasetId AND scene_token = :sceneToken ORDER BY timestamp_us LIMIT :limit OFFSET :offset", nativeQuery=true)
 List<Sample> listByScene(long datasetId, String sceneToken, int limit, int offset);
}
