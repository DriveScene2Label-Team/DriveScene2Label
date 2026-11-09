package com.example.demo.nuscenes.repository;
import com.example.demo.nuscenes.domain.SampleData;
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;
import org.springframework.data.jpa.repository.Query;
public interface SampleDataRepository extends Repository<SampleData, Long> {
 Optional<SampleData> findById(Long id);
 @Query(value="SELECT * FROM sample_data WHERE dataset_id = :datasetId AND sample_token = :sampleToken AND (:keyframesOnly = false OR is_key_frame = true) ORDER BY timestamp_us, token", nativeQuery=true)
 List<SampleData> listBySample(long datasetId, String sampleToken, boolean keyframesOnly);
}
