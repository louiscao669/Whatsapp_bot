#!/usr/bin/env bash
# Tier-1 gold72, CANONICAL (unblinded) names, 5-option MCQs with an abstention
# option E (根据这段文字无法判断). Omission 0% and 30%, three answer models.
#
# Self-contained on purpose. Campaign scripts read ~20 environment knobs, and a
# leftover export from an earlier command silently changes what runs -- a stale
# DRY_RUN makes every stage print instead of execute, which looks exactly like
# "it skipped everything". This script clears every control flag it knows about
# and sets the rest explicitly, so shell state cannot reach it.
#
#   bash evaluation/scripts/campaigns/current/run_gold72_canonical_5opt.sh
#   PREVIEW=1 bash ...current/run_gold72_canonical_5opt.sh    # print, run nothing
set -euo pipefail

unset DRY_RUN STOP_AFTER SKIP_BASE SKIP_BANKS PASSAGES FORCE_ANSWER FORCE_TRANSLATE \
      FORCE_PASSAGE_TRANSLATE FORCE_BACKTRANSLATE FORCE_SCORE REPLACE_INPUTS \
      DISCOVER_LEVELS RAW SHARE_TRANSLATION NO_THINK VERSE_WINDOW ARM_SUFFIX ARMS \
      CHAPTERS OUT_ROOT QA_DIR PASSAGE_DIR WINDOWS MAP METHOD DEFECTS RATES MODELS 2>/dev/null || true

export MCQ_CHOICE_LABELS=ABCDE
export OUT_ROOT=evaluation/outputs/tier1_bsb_unblinded_5opt
export QA_DIR=evaluation/datasets/qa/tier1_gold72_canonical_5opt
export PASSAGE_DIR=evaluation/datasets/passages/tier1_bsb
export MAP=evaluation/datasets/pseudonym_remap/empty_map_unblinded.json
export WINDOWS=QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json
export METHOD=llm_prompt_high
export DEFECTS=omission
export RATES="0% 30%"
export MODELS="llama3.2:1b qwen2.5:1.5b qwen3:1.7b"

: "${OPENAI_API_KEY:?export OPENAI_API_KEY (set -a; source .env; set +a)}"
[ -d "$QA_DIR" ] || { echo "missing $QA_DIR -- run add_abstention_option.py first" >&2; exit 1; }
[ -f "$WINDOWS" ] || { echo "missing $WINDOWS" >&2; exit 1; }

say() { echo; echo "======== [$(date '+%H:%M:%S')] $*"; }
PREVIEW="${PREVIEW:-0}"
if [ "$PREVIEW" = "1" ]; then
  echo "PREVIEW -- would run, in order:"
  echo "  1 build variants        OUT_ROOT=$OUT_ROOT QA_DIR=$QA_DIR MAP=$MAP"
  echo "  2 translate only        STOP_AFTER=translate"
  echo "  3 pin option E          dry run, then --apply"
  echo "  4 answer                FORCE_ANSWER=1"
  echo "  5 verify                window binding + abstention analysis"
  exit 0
fi

say "1/5 build base translation + omission variants"
bash evaluation/scripts/campaigns/current/build_tier1_defect_variants.sh

say "2/5 translate QA per model (no answering yet)"
STOP_AFTER=translate bash evaluation/scripts/campaigns/current/run_tier1_defect_models.sh

say "3/5 option E: how did the translator render it?"
python3 evaluation/scripts/mcq/preparation/pin_abstention_option.py "$OUT_ROOT"
say "3/5 pinning it to one string"
python3 evaluation/scripts/mcq/preparation/pin_abstention_option.py "$OUT_ROOT" --apply

say "4/5 answer + back-translate + judge"
FORCE_ANSWER=1 bash evaluation/scripts/campaigns/current/run_tier1_defect_models.sh

say "5/5 verify"
python3 evaluation/scripts/analysis/current/check_window_binding.py "$OUT_ROOT"
python3 evaluation/scripts/analysis/current/compare_5opt_abstention.py
