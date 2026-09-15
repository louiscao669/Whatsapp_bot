#!/usr/bin/env bash
# Run a campaign once per MCQ option-order rotation, into one output root per rotation.
#
# Why: option order was fixed per item across every model x family x dose cell, so each
# answerer's letter prior was locked onto the same item every time. Measured on gold72,
# an answerer that simply always says its favourite letter scores the SHARE OF KEYS on
# that letter -- 0.194 / 0.278 / 0.222 / 0.306 for A/B/C/D -- with no reading at all.
# Over rotations 0..3 every item's key sits in every position exactly once, so averaging
# the four roots cancels the prior EXACTLY rather than in expectation.
#
# One offset per run, not per cell, on purpose: position is then identical between the
# 0% and 30% cells of an item, so the paired dose contrast carries no position change.
#
#   ROTATIONS="0 1 2 3"                 which offsets to run
#   BASE_OUT=evaluation/outputs/tier1   roots become <BASE_OUT>_rot<K>
#   CAMPAIGN=<path>                     campaign script to run per rotation
# Every other knob is passed straight through to the campaign.
set -euo pipefail

ROTATIONS="${ROTATIONS:-0 1 2 3}"
BASE_OUT="${BASE_OUT:-evaluation/outputs/tier1}"
CAMPAIGN="${CAMPAIGN:-evaluation/scripts/campaigns/current/run_tier1_defect_models.sh}"

[[ -f "$CAMPAIGN" ]] || { echo "no such campaign: $CAMPAIGN" >&2; exit 2; }

# Stale exported knobs have silently wrecked runs in this project before (an exported
# DRY_RUN=1 turned a whole build into a no-op; an exported MODELS broke a later campaign).
# Say what is in force rather than letting it act invisibly.
for v in DRY_RUN FORCE_ANSWER MODELS DEFECTS RATES PASSAGES OUT_ROOT MCQ_ROTATE \
         MCQ_SHUFFLE_SEED; do
  if [[ -n "${!v-}" ]]; then
    echo "  [env] $v=${!v}" >&2
  fi
done
if [[ -n "${OUT_ROOT-}" ]]; then
  echo "  [warn] OUT_ROOT is exported and will be OVERRIDDEN per rotation" >&2
fi
if [[ -n "${MCQ_SHUFFLE_SEED-}" ]]; then
  echo "  [err ] MCQ_SHUFFLE_SEED is exported; it conflicts with rotation. unset it." >&2
  exit 2
fi

roots=()
for K in $ROTATIONS; do
  export MCQ_ROTATE="$K"
  export OUT_ROOT="${BASE_OUT}_rot${K}"
  roots+=("$OUT_ROOT")
  echo
  echo "================ rotation $K -> $OUT_ROOT ================"
  bash "$CAMPAIGN" "$@"
done
unset MCQ_ROTATE

echo
echo "Done. Roots written:"
for r in "${roots[@]}"; do echo "  $r"; done
cat <<'NOTE'

IMPORTANT: analyse the MEAN ACROSS these roots, not any single one. A single root still
carries the answerer's letter prior -- that is the whole reason for the ladder. Item
accuracy is the mean over the rotations; the paired dose contrast may be computed within
a root and then averaged, since position is constant inside a root.
NOTE
