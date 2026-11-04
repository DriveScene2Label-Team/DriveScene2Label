#!/usr/bin/env bash
# Apply DriveScene2Label's VESPA patches to a clean checkout of the pinned upstream commit.
# Used by ai-server/Dockerfile and the Colab notebook so both run the same modified VESPA.
#   usage: apply.sh <vespa_dir> <expected_commit>
set -euo pipefail
if [[ $# -ne 2 ]]; then echo "usage: $0 <vespa_dir> <expected_commit>" >&2; exit 2; fi
vespa_dir=$1 expected=$2
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

head=$(git -C "$vespa_dir" rev-parse HEAD)
if [[ $head != "$expected"* ]]; then
  echo "VESPA is at $head, expected $expected. The patches are made for that commit only." >&2; exit 1
fi
if [[ -n $(git -C "$vespa_dir" status --porcelain) ]]; then
  echo "VESPA checkout is not clean (patches already applied?). Start from a fresh checkout." >&2; exit 1
fi
shopt -s nullglob
patches=("$here"/[0-9][0-9][0-9][0-9]-*.patch)
if [[ ${#patches[@]} -eq 0 ]]; then echo "no patches found in $here" >&2; exit 1; fi
for p in "${patches[@]}"; do
  git -C "$vespa_dir" apply --check "$p"
  git -C "$vespa_dir" apply "$p"
  echo "applied $(basename "$p")"
done
