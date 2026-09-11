#!/usr/bin/env bash
# Answer the staged Luke naming-condition arms (blinding diagnostic).
#
# Run stage_luke_naming_arms.py FIRST. The three arms differ only in which
# passage/QA the answerer reads; everything else is held identical, so all
# three MUST be run in one session with the same settings.
#
#   decanon    人物丙 / 角色02      historical eval condition
#   pseudonym  珂温 / 哈丽 / 米珥    pilot delivery form
#   canonical  撒迦利亚 / 以利沙伯   UNBLINDED
#
# Requirements: Ollama with the three models pulled; OPENAI_API_KEY exported
# (back-translation, judge, MCQ choice mapping). No translation happens here.
#
# Knobs:
#   ARMS="decanon pseudonym canonical"
#   CHAPTERS="1 2 3 4 5 6 7 8"
#   MODELS="llama1b qwen1.5b qwen1.7b"
#   RATES="0% 30%"
#   DRY_RUN=1
set -euo pipefail
unset OUT_ROOT QA_DIR PASSAGE_DIR WINDOWS MAP METHOD DEFECTS 2>/dev/null || true
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

ARMS="${ARMS:-decanon pseudonym canonical}"
CHAPTERS="${CHAPTERS:-1 2 3 4 5 6 7 8}"
MODELS="${MODELS:-llama1b qwen1.5b qwen1.7b}"
RATES="${RATES:-0% 30%}"
VERSE_WINDOW="${VERSE_WINDOW:-2}"
DEFECT=omission
ARM_SUFFIX="${ARM_SUFFIX:-}"
DRY_RUN="${DRY_RUN:-0}"

: "${OPENAI_API_KEY:?export OPENAI_API_KEY before running}"
run() { if [ "$DRY_RUN" = "1" ]; then printf '  %q' "$@"; echo; else "$@"; fi; }
say() { echo "[$(date '+%H:%M:%S')] $*"; }

for ARM in $ARMS; do
  for M in $MODELS; do
    case "$M" in
      llama1b|llama3.2:1b|"llama 1b"|1b)
        TIER="llama 1b"; OLLAMA_MODEL="llama3.2:1b";  EXTRA=""; MAPPER=openai ;;
      qwen1.5b|qwen2.5:1.5b|1.5b)
        TIER="1.5b";     OLLAMA_MODEL="qwen2.5:1.5b"; EXTRA=""; MAPPER=openai ;;
      qwen1.7b|qwen3:1.7b|1.7b)
        TIER="1.7b";     OLLAMA_MODEL="qwen3:1.7b";   EXTRA="--ollama-no-think"; MAPPER=rules ;;
      *)
        echo "unknown model alias: $M" >&2
        echo "accepted: llama1b|llama3.2:1b  qwen1.5b|qwen2.5:1.5b  qwen1.7b|qwen3:1.7b" >&2
        echo "NOTE: a stale exported MODELS from an earlier campaign is the usual cause." >&2
        exit 1 ;;
    esac
    for CH in $CHAPTERS; do
      ROOT="evaluation/outputs/naming_${ARM}${ARM_SUFFIX}/luke${CH}/${TIER}/${DEFECT}"
      LEVELS=""
      for LEV in $RATES; do [ -d "$ROOT/$LEV" ] && LEVELS="$LEVELS $LEV"; done
      [ -z "$LEVELS" ] && { echo "[skip] $ARM luke${CH}/${TIER}: nothing staged"; continue; }
      FIRST_LEV="$(echo $LEVELS | awk '{print $1}')"
      N=$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(len(d if isinstance(d,list) else d.get('items',d.get('questions',[]))))" \
        "$ROOT/$FIRST_LEV/qa_target_decanonicalized.json")
      say "[$ARM / $TIER] luke${CH} (N=$N, mapper=$MAPPER):$LEVELS"
      # shellcheck disable=SC2086
      run python3 evaluation/scripts/scoring/legacy_luke/answer_score_subset_in_place.py "$N" \
          --chapters "$CH" \
          --allow-fewer \
          --artifact-root-template "evaluation/outputs/naming_${ARM}${ARM_SUFFIX}/luke{chapter}/${TIER}/${DEFECT}" \
          --methods $LEVELS \
          --answer-provider ollama \
          --answer-model "$OLLAMA_MODEL" $EXTRA \
          --answer-verse-window "$VERSE_WINDOW" \
          --mcq-choice-mapper "$MAPPER" \
          --summary-json "evaluation/outputs/reports/naming_${ARM}${ARM_SUFFIX}_${M}_luke${CH}.json"
    done
  done
done
say "done. analyse with: python3 evaluation/scripts/analysis/current/compare_luke_naming_arms.py"
