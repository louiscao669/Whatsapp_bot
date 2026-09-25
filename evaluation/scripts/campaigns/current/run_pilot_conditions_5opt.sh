#!/usr/bin/env bash
# Answer the HUMAN-PILOT conditions of the unblinded 5-option tier-1 corpus with the
# small answer models -- the model-side counterpart of what participants see.
#
# Conditions (exactly the pilot slate, nothing else):
#   omission 0% (the clean anchor), omission 15%, omission 30%,
#   mistranslation 15%, mistranslation 30%, grammar 30%, google_word_by_word
#
# Everything is pinned to the unblinded 5-option arm: canonical (real) names, the
# 5-option QA set with the meta-option on E, the canonical window map, and the ONE
# shared _base QA translation (SHARE_QA) so every model answers the same Chinese items.
#
# The base translations were corrected on 2026-09-16 (fix_unblinded_5opt_translations.py)
# and every variant was rebuilt, so ANY answers already in this tree are stale: this
# script forces answering, back-translation and scoring by default.
#
# Requirements: ollama running with the models pulled, and OPENAI_API_KEY
# (back-translation, judge, MCQ choice mapping).
#
#   bash evaluation/scripts/campaigns/current/run_pilot_conditions_5opt.sh
#   MODELS="qwen3:1.7b" bash ...                 # one model instead of the ladder
#   QA_FORMATS=mcq bash ...                      # skip open items (no judge cost)
#   PASSAGES="t1_judg9" bash ...                 # subset
#   PREVIEW=1 bash ...                           # print the plan, run nothing
#   NO_THINK=1 bash ...                          # thinking OFF (writes qwen317b/, not qwen317b_think/)
set -euo pipefail

# Capture the knobs a caller may legitimately override before clearing leftover exports.
_out_root="${OUT_ROOT:-}"; _qa_dir="${QA_DIR:-}"; _passage_dir="${PASSAGE_DIR:-}"
_windows="${WINDOWS:-}"; _map="${MAP:-}"

unset DRY_RUN STOP_AFTER SKIP_BASE SKIP_BANKS FORCE_TRANSLATE REPLACE_INPUTS \
      DISCOVER_LEVELS SHARE_TRANSLATION ARM_SUFFIX OUT_ROOT QA_DIR PASSAGE_DIR \
      WINDOWS MAP METHOD DEFECTS RATES MCQ_ROTATE MCQ_SHUFFLE_SEED 2>/dev/null || true

export OUT_ROOT="${_out_root:-evaluation/outputs/tier1_bsb_unblinded_5opt_think}"
export QA_DIR="${_qa_dir:-evaluation/datasets/qa/tier1_gold72_canonical_5opt}"
export PASSAGE_DIR="${_passage_dir:-evaluation/datasets/passages/tier1_bsb}"
export MAP="${_map:-evaluation/datasets/pseudonym_remap/empty_map_unblinded.json}"
export WINDOWS="${_windows:-QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json}"
export MCQ_CHOICE_LABELS="${MCQ_CHOICE_LABELS:-ABCDE}"   # five options, meta-option on E
export MCQ_ABSTAIN_LABEL="${MCQ_ABSTAIN_LABEL:-E}"
export QA_FORMATS="${QA_FORMATS:-open,mcq}"              # the pilot delivers both forms
export MODELS="${MODELS:-llama3.2:1b qwen2.5:1.5b qwen3:1.7b}"
export NO_THINK="${NO_THINK:-0}"                         # qwen3 reasons, as in the 5opt_think arm
export SHARE_QA="${SHARE_QA:-1}"
export DISCOVER_LEVELS=0
export FORCE_ANSWER="${FORCE_ANSWER:-1}"
export FORCE_BACKTRANSLATE="${FORCE_BACKTRANSLATE:-1}"
export FORCE_SCORE="${FORCE_SCORE:-1}"
[ -n "${PASSAGES:-}" ] && export PASSAGES

if [ -z "${OPENAI_API_KEY:-}" ] && [ -f .env ]; then set -a; . ./.env; set +a; fi
: "${OPENAI_API_KEY:?export OPENAI_API_KEY (back-translation, judge, MCQ mapping)}"
[ -d "$OUT_ROOT" ] || { echo "missing $OUT_ROOT" >&2; exit 1; }

DEFECT_PLAN="omission:0% 15% 30%|mistranslation:15% 30%|grammar:30%"

if [ "${PREVIEW:-0}" = "1" ]; then
  echo "would answer, per model ($MODELS), thinking=$([ "$NO_THINK" = "0" ] && echo on || echo off):"
  echo "$DEFECT_PLAN" | tr '|' '\n' | sed 's/^/  /'
  echo "  google_word_by_word"
  echo "forms=$QA_FORMATS labels=$MCQ_CHOICE_LABELS out=$OUT_ROOT"
  exit 0
fi

say() { echo; echo "======== [$(date '+%H:%M:%S')] $*"; }

IFS='|' read -r -a plan <<< "$DEFECT_PLAN"
for entry in "${plan[@]}"; do
  export DEFECTS="${entry%%:*}"
  export RATES="${entry#*:}"
  say "$DEFECTS $RATES"
  bash evaluation/scripts/campaigns/current/run_tier1_defect_models.sh
done

say "google_word_by_word"
# The wbw cell sits at <passage>/google_word_by_word in this tree, not under a model dir.
SOURCE_CELL=. bash evaluation/scripts/campaigns/current/run_tier1_wbw_models.sh

say "done -- scores at $OUT_ROOT/<passage>/<model>/<condition>/scores_target_llama.json"
echo "Check window binding: python3 evaluation/scripts/analysis/current/check_window_binding.py $OUT_ROOT"
