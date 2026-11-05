package com.example.demo.nuscenes.api;
import com.example.demo.nuscenes.dto.LabelEditDtos.*;
import com.example.demo.nuscenes.service.LabelEditService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.web.bind.annotation.*;
/** Label edits (rename / delete / history / revert). Originals stay unchanged; see LabelEditService. */
@RestController
@RequestMapping("/api")
public class LabelEditController {
 private final LabelEditService edits;
 public LabelEditController(LabelEditService edits) { this.edits=edits; }
 @PatchMapping("/annotations/{id}") public EditResult renameAnnotation(@PathVariable long id,@Valid @RequestBody RenameRequest body) { return edits.renameAnnotation(id,body.label(),body.scope()); }
 @DeleteMapping("/annotations/{id}") public EditResult deleteAnnotation(@PathVariable long id,@RequestParam(required=false) String scope) { return edits.deleteAnnotation(id,scope); }
 @PatchMapping("/auto-label/predictions/{id}") public EditResult renamePrediction(@PathVariable long id,@Valid @RequestBody RenameRequest body) { return edits.renamePrediction(id,body.label(),body.scope()); }
 @DeleteMapping("/auto-label/predictions/{id}") public EditResult deletePrediction(@PathVariable long id) { return edits.deletePrediction(id); }
 @GetMapping("/scenes/{sceneId}/label-edits") public List<LabelEdit> list(@PathVariable long sceneId,@RequestParam(required=false) Long jobId) { return edits.list(sceneId,jobId); }
 @PostMapping("/label-edits/{id}/revert") public EditResult revert(@PathVariable long id) { return edits.revert(id); }
}
