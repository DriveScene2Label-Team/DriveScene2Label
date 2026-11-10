#!/usr/bin/bash
#SBATCH -J vespa-rigid
#SBATCH --gres=gpu:normal:1
#SBATCH --cpus-per-gpu=8
#SBATCH --mem-per-gpu=29G
#SBATCH -w ariel-v6
#SBATCH -p batch_ugrad
#SBATCH -t 0-4
#SBATCH -o logs/slurm-%A.out

# Rigid tracklet post-processing on mini (based on vis_vespa_direct_check.sh).
# Stages 01-07 load from the cache under outs/vlm/p_final/, so this is CPU work only.
#   Phase 1 (no refs):  sbatch vis_vespa_direct_check_ver2.sh
#     -> tracklets + regression check against main_pseudo_vlm_scene.py + images/report under #rigid/base/
#   Phase 2 (refs):     REFS=refs.json TAG=ref1 sbatch vis_vespa_direct_check_ver2.sh
#     -> propagated labels + images/report under #rigid/ref1/ (compare its report with #rigid/base/)
# Override scenes with e.g. SCENES="scene-0061 scene-0103".

source /nas2/data/chan12/anaconda3/etc/profile.d/conda.sh
conda activate vespa
export PYTHONUNBUFFERED=1

CONFIG=configs/vlm/p_final.yaml
EXP=p_final
SCENES="${SCENES:-scene-0061}"
REFS="${REFS:-}"
TAG="${TAG:-$([ -n "$REFS" ] && echo ref || echo base)}"
OUT="outs/vlm/${EXP}/#rigid/${TAG}"

echo "========== [RIGID] tag=${TAG} refs=${REFS:-none} scenes=${SCENES} $(date) =========="
python main_pseudo_vlm_scene_ver2.py --config "$CONFIG" --scenes $SCENES --tag "$TAG" ${REFS:+--refs "$REFS"} || exit 1

if [ -z "$REFS" ]; then
  echo "========== [REGRESSION] labels without refs must equal main_pseudo_vlm_scene.py =========="
  python main_pseudo_vlm_scene.py --config "$CONFIG" --scenes $SCENES || exit 1
  for SCENE in $SCENES; do
    for MAP in 1class 3class 8class; do
      python - "outs/vlm/${EXP}/#out_labels_scene/${SCENE}/vlm_${EXP}_${SCENE}_${MAP}.json" "${OUT}/labels_${SCENE}_${MAP}.json" <<'EOF' || exit 1
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
ok = a == b
print(('OK   ' if ok else 'DIFF ') + sys.argv[2])
sys.exit(0 if ok else 1)
EOF
    done
  done
fi

echo "========== [RENDER] =========="
# track ids listed in refs.json are reported separately (single-scene runs; ids are per scene)
FOCUS=""
if [ -n "$REFS" ]; then
  FOCUS=$(python -c "import json,sys; r=json.load(open(sys.argv[1])); print(' '.join(t for s in sys.argv[2:] for t in r.get(s, {})))" "$REFS" $SCENES)
fi
python scripts/render_boxes_on_images_ver2.py --config "$CONFIG" --tag "$TAG" --mapping 8class --scenes $SCENES \
  ${FOCUS:+--focus_tracks $FOCUS} || exit 1
if [ -n "$FOCUS" ]; then
  echo "========== [BASE REPORT, same focus tracks] =========="
  python scripts/render_boxes_on_images_ver2.py --config "$CONFIG" --tag base --mapping 8class --scenes $SCENES \
    --no_images --focus_tracks $FOCUS || exit 1
fi

ls -lh "$OUT"
exit 0
