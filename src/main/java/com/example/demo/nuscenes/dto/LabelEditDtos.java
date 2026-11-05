package com.example.demo.nuscenes.dto;
import jakarta.validation.constraints.NotBlank;
import java.time.OffsetDateTime;
import java.util.List;
public final class LabelEditDtos {
 private LabelEditDtos() {}
 /** scope: SAMPLE (this frame only, default) or INSTANCE (every frame of the GT instance). Predictions accept SAMPLE only. */
 public record RenameRequest(@NotBlank String label,String scope) {}
 /**
  * One history entry. targetIds are gt_annotation ids (ANNOTATION) or predicted_annotation ids (PREDICTION);
  * sampleTokens are the original sample tokens of those targets in the same order. revertible is false once reverted
  * or while a later, not reverted edit touches one of the same targets (revert the newest first).
  */
 public record LabelEdit(long id,long datasetId,long sceneId,Long jobId,String targetType,String action,String scope,String instanceToken,
   String fromLabel,String toLabel,List<Long> targetIds,List<String> sampleTokens,int count,OffsetDateTime createdAt,OffsetDateTime revertedAt,boolean revertible) {}
 public record EditResult(LabelEdit edit) {}
}
