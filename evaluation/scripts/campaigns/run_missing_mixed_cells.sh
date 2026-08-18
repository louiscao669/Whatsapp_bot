#!/usr/bin/env bash
# Fill in all missing / errored cells of the MIXED-DEFECT campaign
# (EXPERIMENT_BURDEN_MQM_BRIDGE.md §7.2).
#
# Does three things, in order:
#   1. Scans evaluation/outputs/luke{1..8}/<tier>/mixed/<mix>/<level>/ for
#      cells that have generated variants but NO scores_target_llama.json,
#      and runs the campaign answer stage for exactly those (mix, chapter)
#      pairs. (As of 2026-07-16: grammar20_omission, all 8 chapters, 1.7b.)
#   2. Retries, in place, every item whose generated_answer came back empty
#      (generation_error set) across ALL mixed cells — 39 such items in 24
#      cells as of 2026-07-16. Cells without empties are a no-op.
#   3. Reruns the additivity analysis.
#
# Requirements (run on your local machine):
#   - Ollama running, with the tier's model pulled (default qwen3:1.7b)
#   - OPENAI_API_KEY exported (judge + backtranslation)
#
# Usage:
#   bash evaluation/scripts/campaigns/run_missing_mixed_cells.sh          # qwen1.7b
#   MODELS="llama1b qwen1.5b" bash evaluation/scripts/campaigns/run_missing_mixed_cells.sh
#   DRY_RUN=1 bash evaluation/scripts/campaigns/run_missing_mixed_cells.sh  # preview
set -euo pipefail
cd "$(dirname "$0")/../.."

MODELS="${MODELS:-qwen1.7b}"
DRY_RUN="${DRY_RUN:-0}"
CAMPAIGN=evaluation/scripts/campaigns/run_mixed_defect_campaign.sh

for M in $MODELS; do
  case "$M" in
    llama1b)       TIER="llama 1b" ;;
    qwen1.5b)      TIER="1.5b" ;;
    qwen1.7b|1.7b) TIER="1.7b" ;;
    *) echo "unknown model alias: $M" >&2; exit 1 ;;
  esac

  echo "### [$M] pass 1: answer cells with no scores yet"
  PAIRS=$(python3 - "$TIER" <<'PY'
import sys
from pathlib import Path

tier = sys.argv[1]
root = Path("evaluation/outputs")
missing = {}
for ch in range(1, 9):
    mixroot = root / f"luke{ch}" / "1.7b" / "mixed"  # variants live under 1.7b
    if not mixroot.is_dir():
        continue
    for mixdir in sorted(p for p in mixroot.iterdir() if p.is_dir()):
        for lev in sorted(mixdir.glob("*%")):
            if not (lev / "passage_target_decanonicalized.txt").exists():
                continue
            score = (root / f"luke{ch}" / tier / "mixed" / mixdir.name
                     / lev.name / "scores_target_llama.json")
            if not score.exists():
                missing.setdefault(mixdir.name, set()).add(ch)
for mix, chs in sorted(missing.items()):
    print(mix + ":" + " ".join(str(c) for c in sorted(chs)))
PY
)
  if [ -z "$PAIRS" ]; then
    echo "  (no missing cells for $M)"
  else
    while IFS=: read -r MIX CHS; do
      [ -z "$MIX" ] && continue
      echo "  -> $MIX  chapters: $CHS"
      MODELS="$M" MIXES="$MIX" CHAPTERS="$CHS" DRY_RUN="$DRY_RUN" \
        bash "$CAMPAIGN" answer
    done <<< "$PAIRS"
  fi

  echo "### [$M] pass 2: retry empty-generation-error items (in place)"
  MODELS="$M" DRY_RUN="$DRY_RUN" \
    ANSWER_EXTRA_ARGS="--only-empty-generation-errors" \
    bash "$CAMPAIGN" answer
done

echo "### rerun additivity analysis"
[ "$DRY_RUN" = "1" ] || \
  python3 QA_algorithm/scripts/semireal_validation/additivity_mixed_defects.py
echo "ALL DONE."
