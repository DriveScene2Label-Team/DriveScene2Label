#!/usr/bin/bash
#SBATCH -J vespa-rigid-front
#SBATCH --gres=gpu:normal:1
#SBATCH --cpus-per-gpu=8
#SBATCH --mem-per-gpu=29G
#SBATCH -w ariel-v6
#SBATCH -p batch_ugrad
#SBATCH -t 0-1
#SBATCH -o logs/slurm-%A.out

# CAM_FRONT + LiDAR BEV only, before (base) and after (ref) the rigid propagation, for sharing.
# Needs the outputs of vis_vespa_direct_check_ver2.sh for both tags. Rendering only, no pipeline run.
#   sbatch render_front_bev_ver2.sh                      (defaults: TAGS="base ref1", FOCUS=3, scene-0061)
# Output: outs/vlm/p_final/#rigid/<tag>/images/8class_front/<scene>.mp4 and <scene>/<keyframe>.jpg
#         outs/vlm/p_final/#rigid/base/images/8class_front_vs_ref1/  (before as usual + changed boxes of ref1 in red)

source /nas2/data/chan12/anaconda3/etc/profile.d/conda.sh
conda activate vespa
export PYTHONUNBUFFERED=1

SCENES="${SCENES:-scene-0061}"
TAGS="${TAGS:-base ref1}"
FOCUS="${FOCUS:-3}"

for TAG in $TAGS; do
  echo "========== [RENDER front+BEV] ${TAG} $(date) =========="
  python scripts/render_boxes_on_images_ver2.py --config configs/vlm/p_final.yaml --tag "$TAG" --mapping 8class \
    --scenes $SCENES --cams CAM_FRONT ${FOCUS:+--focus_tracks $FOCUS} || exit 1
done

set -- $TAGS
if [ $# -eq 2 ]; then
  echo "========== [RENDER front+BEV, $1 + $2 in red] $(date) =========="
  python scripts/render_boxes_on_images_ver2.py --config configs/vlm/p_final.yaml --tag "$1" --compare_tag "$2" \
    --mapping 8class --scenes $SCENES --cams CAM_FRONT ${FOCUS:+--focus_tracks $FOCUS} || exit 1
fi

ls -lh outs/vlm/p_final/#rigid/*/images/
exit 0
