package com.example.demo.labels;

import java.time.OffsetDateTime;
import tools.jackson.databind.JsonNode;
import jakarta.validation.constraints.*;

public final class LabelDtos {
 private LabelDtos() {}
 public record Summary(long id,String name,Long datasetId,Long sourceJobId,String sourceType,int headRevision,long version,OffsetDateTime createdAt) {}
 public record Revision(int number,String note,OffsetDateTime createdAt) {}
 public record Detail(Summary document,int revision,JsonNode data) {}
 public record Save(@NotNull @Min(0) Long expectedVersion,@NotNull JsonNode data,@Size(max=500) String note) {}
}
