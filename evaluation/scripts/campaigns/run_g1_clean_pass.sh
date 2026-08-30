#!/usr/bin/env bash
# G1 clean-cell pass -- EXPERIMENT_EFFORT_FLUENCY_GUARDRAIL_2026-08-20.md §9.1
#
# Re-answers the CLEAN reference cell (llm_prompt_high) for Luke 1-8 with
# qwen3:1.7b thinking ON, so that per-item token spend exists for Gate G1.
# ~204 generations (102 items x 2 forms). Minutes to an hour, not the 6-14
# hours Phase 1 needs.
#
# THE ONE THING THAT MATTERS HERE: this RE-ANSWERS, it does not RE-TRANSLATE.
# The passage artifacts are copied from the existing 1.7b cells, so the target
# text is byte-identical to the text the anchor IRT was calibrated on. If you
# re-ran the translation instead, llm_prompt_high would come back different
# (it was a single unseeded temperature-1.0 draw; temp 0 still leaves ~5.6%
# text divergence), and G1 would be correlating token spend on ONE text
# against difficulty estimated on ANOTHER.
#
# The thinking switch is an OMISSION: --ollama-no-think is simply not passed.
# Do not "enable" thinking by adding a flag -- there isn't one. Note also that
# the /no_think prompt token is ignored by qwen3:1.7b; the pipeline's
# structured think:false is what actually takes effect, so leaving the flag off
# is what turns reasoning on.
#
# Usage:
#   bash evaluation/scripts/campaigns/run_g1_clean_pass.sh
#   CHAPTERS="1 2 3" bash evaluation/scripts/campaigns/run_g1_clean_pass.sh
#   DRY_RUN=1 bash evaluation/scripts/campaigns/run_g1_clean_pass.sh
#   FORMATS=mcq bash ...      # strictly zero OpenAI spend (see below)
#
# Cost: --skip-llm turns OFF the judge, but back-translation of OPEN answers
# still makes OpenAI calls (it is not gated on skip_llm). That is a few cents
# for ~100 short answers. FORMATS=mcq removes even that, at the price of
# halving n -- and MCQ is judge-free, which is the form G1 can trust most.

set -euo pipefail

cd "$(dirname "$0")/../../.."   # repo root (eten-whatsapp-bot)

CHAPTERS="${CHAPTERS:-1 2 3 4 5 6 7 8}"
TIER="${TIER:-1.7b_think}"
SRC_TIER="${SRC_TIER:-1.7b}"
CELL="${CELL:-llm_prompt_high}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:1.7b}"
VERSE_WINDOW="${VERSE_WINDOW:-2}"
FORMATS="${FORMATS:-both}"
DRY_RUN="${DRY_RUN:-0}"

# Gate G2 protection: an unset num_predict means "no cap", which is what we
# want -- a cap censors output_tokens exactly where spend is highest. num_ctx
# needs headroom for a reasoning trace on top of the prompt.
unset OLLAMA_NUM_PREDICT || true
export OLLAMA_NUM_CTX="${OLLAMA_NUM_CTX:-8192}"

run() {
  echo "+ $*"
  [ "$DRY_RUN" = "1" ] || "$@"
}

command -v ollama >/dev/null 2>&1 || {
  echo "!! ollama not on PATH. Start it with: ollama serve" >&2; exit 1; }
curl -sf "${OLLAMA_BASE_URL:-http://localhost:11434}/api/tags" >/dev/null || {
  echo "!! Ollama is not answering at ${OLLAMA_BASE_URL:-http://localhost:11434}." >&2
  echo "   Start it with: ollama serve" >&2; exit 1; }

echo "== stage 1: copy cached artifacts ${SRC_TIER} -> ${TIER} (NO re-translation)"
for CH in $CHAPTERS; do
  SRC="evaluation/outputs/luke${CH}/${SRC_TIER}/${CELL}"
  DST="evaluation/outputs/luke${CH}/${TIER}/${CELL}"
  if [ ! -d "$SRC" ]; then
    echo "[skip] luke${CH}: $SRC missing"
    continue
  fi
  run mkdir -p "$DST"
  for F in passage_target.txt passage_target_decanonicalized.txt \
           passage_source_decanonicalized.txt qa_target.json \
           qa_target_decanonicalized.json decanonicalized_metadata.json \
           passage_translation.json; do
    if [ -f "$SRC/$F" ] && [ ! -f "$DST/$F" ]; then
      run cp "$SRC/$F" "$DST/$F"
    fi
  done
  # _shared holds the chapter's translated QA; copy if the tier lacks it.
  SRC_SHARED="evaluation/outputs/luke${CH}/${SRC_TIER}/_shared"
  DST_SHARED="evaluation/outputs/luke${CH}/${TIER}/_shared"
  if [ -d "$SRC_SHARED" ] && [ ! -d "$DST_SHARED" ]; then
    run cp -R "$SRC_SHARED" "$DST_SHARED"
  fi
done

echo
echo "== stage 2: answer with thinking ON (no --ollama-no-think)"
for CH in $CHAPTERS; do
  DST="evaluation/outputs/luke${CH}/${TIER}/${CELL}"
  if [ ! -f "$DST/passage_target_decanonicalized.txt" ]; then
    echo "[skip] luke${CH}: no passage in $DST"
    continue
  fi
  # Chapter pools differ (22/12/7/22/13/8/9/9 for ch1-8) and the runner errors
  # if N exceeds what the chapter has, so read it rather than hardcoding.
  N=$(python3 -c "
import json
d = json.load(open('evaluation/datasets/qa/qa_output_luke_ch${CH}_all_formats.json'))
recs = d if isinstance(d, list) else d.get('items', d.get('questions', []))
print(len(recs))")
  echo "-- luke${CH} (N=${N}, formats=${FORMATS})"
  run python3 evaluation/scripts/scoring/answer_score_subset_in_place.py "$N" \
      --chapters "$CH" \
      --allow-fewer \
      --artifact-root-template "evaluation/outputs/luke{chapter}/${TIER}" \
      --methods "$CELL" \
      --formats "$FORMATS" \
      --include-scored \
      --answer-provider ollama \
      --answer-model "$OLLAMA_MODEL" \
      --answer-verse-window "$VERSE_WINDOW" \
      --mcq-choice-mapper rules \
      --skip-llm \
      --summary-json "evaluation/outputs/reports/g1_clean_luke${CH}.json"
done

echo
echo "DONE. Now run the gate:"
echo "  python3 QA_algorithm/scripts/effort/g1_effort_vs_difficulty.py"
