#!/usr/bin/env bash
# Wait for the tier1_strong defect grid to finish, verify it completed, then
# seed and run the google_word_by_word cells with the SAME strong QA.
#
#   caffeinate -dimsu bash evaluation/scripts/campaigns/maintenance/run_wbw_after_grid.sh
set -euo pipefail
cd ~/whatsapp-bot/eten-whatsapp-bot

O=evaluation/outputs
ROOT="$O/tier1_strong"
PIDS="t1_judg9 t1_judg17_18 t1_2kgs6_7 t1_1kgs13 t1_2kgs11
      t1_2chr26 t1_2sam21 t1_acts19 t1_acts20 t1_acts23"

# Fail now, not in six hours.
: "${OPENAI_API_KEY:?export OPENAI_API_KEY before running}"
say() { echo "[$(date '+%H:%M:%S')] $*"; }

# The bracket keeps this pgrep from matching its own command line.
say "waiting for the defect grid to exit..."
while pgrep -f "[r]un_tier1_hard_v3.sh" >/dev/null; do sleep 60; done
say "grid process gone"

n=$(find "$ROOT" -path "*/scores_target_llama.json" -not -path "*google_word_by_word*" | wc -l | tr -d ' ')
say "defect-grid score files: $n (expect 540)"
if [ "$n" -lt 540 ]; then
  say "ABORT: grid incomplete, not starting wbw"; exit 1
fi

say "seeding wbw cells (bsb translation + strong QA)"
for p in $PIDS; do
  mkdir -p "$ROOT/$p/google_word_by_word"
  cp -a "$O/tier1_bsb/$p/qwen317b_think/google_word_by_word/." "$ROOT/$p/google_word_by_word/"
  # overwrite the BSB questions with the strong-66 QA -- the step missed last time
  cp "$ROOT/$p/_base/llm_prompt_high/qa_target.json" \
     "$ROOT/$p/google_word_by_word/qa_target.json"
  cp "$ROOT/$p/_base/llm_prompt_high/qa_target_decanonicalized.json" \
     "$ROOT/$p/google_word_by_word/qa_target_decanonicalized.json"
  rm -f "$ROOT/$p/google_word_by_word/generated_answers_target_llama"*.json \
        "$ROOT/$p/google_word_by_word/scores_target_llama.json"
done

say "launching wbw (30 cells)"
OUT_ROOT="$ROOT" SOURCE_CELL=. \
QA_DIR=evaluation/datasets/pseudonymized/qa/tier1_strong \
PASSAGE_DIR=evaluation/datasets/pseudonymized/passages/tier1_bsb \
WINDOWS="" MODELS="llama3.2:1b qwen2.5:1.5b qwen3:1.7b" \
bash evaluation/scripts/campaigns/current/run_tier1_wbw_models.sh
say "done"
