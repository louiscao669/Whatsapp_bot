#!/usr/bin/env bash
# MIXED-DEFECT ADDITIVITY CAMPAIGN (EXPERIMENT_BURDEN_MQM_BRIDGE.md §7.2).
#
# Tests Delta(A+B) ?= Delta(A) + Delta(B) with designed doses and no MQM
# middleman — the clean additivity test that Step 2 could not deliver.
#
# DESIGN
#   Pairs (order: bank-based defect applied FIRST on intact text, then the
#   rule-based one; omission always last since it deletes clauses):
#     P1  grammar        -> omission     (fluency x adequacy)
#     P2  mistranslation -> omission     (adequacy x adequacy)
#     P3  mistranslation -> addition:bad (adequacy x adequacy, insertion)
#   Doses: 2x2 per pair — first defect at {10%, 20%} x second at {10%, 20%}
#   = 12 combos x 8 chapters = 96 mixed cells. Singles at the same doses
#   already exist in the 1.7b defect grid; 0% baselines exist per defect.
#   Seeds: generator defaults (seed+chapter) — matches the single-defect
#   variants' damage instances where the text allows.
#
# STAGES
#   1. generate    — offline, chains the existing create_*_variants.py
#                    (source = the single-defect variant dir). Idempotent.
#                    Output: luke{ch}/1.7b/mixed/<A><dA>_<B>/<level>/
#   2. answer      — Ollama answer + OpenAI judge via
#                    answer_score_subset_in_place.py (run on your machine:
#                    needs Ollama + OPENAI_API_KEY). Resumable.
#
# USAGE (repo root):
#   bash evaluation/scripts/run_mixed_defect_campaign.sh generate
#   bash evaluation/scripts/run_mixed_defect_campaign.sh answer
#   MODELS="qwen1.7b llama1b" bash ... answer     # default qwen1.7b
#   CHAPTERS="1 2" DRY_RUN=1 bash ... answer      # preview
#   MIXES="grammar10_omission" bash ... answer    # restrict answered mixes
#   ANSWER_EXTRA_ARGS="--allow-partial-answers --retries 0" bash ... answer
#
# ANALYSIS (after answering):
#   python3 QA_algorithm/scripts/semireal_validation/additivity_mixed_defects.py

set -euo pipefail
cd "$(dirname "$0")/../.."

STAGE="${1:-generate}"
CHAPTERS="${CHAPTERS:-1 2 3 4 5 6 7 8}"
MODELS="${MODELS:-qwen1.7b}"
SRC_RATES="${SRC_RATES:-10 20}"
SECOND_RATES="${SECOND_RATES:-10% 20%}"
DRY_RUN="${DRY_RUN:-0}"
MIXES="${MIXES:-}"
ANSWER_EXTRA_ARGS="${ANSWER_EXTRA_ARGS:-}"

run() { echo "+ $*"; [ "$DRY_RUN" = "1" ] || "$@"; }

# pair table: name_prefix  first_defect  second_generator  second_extra_args
gen_pair() {  # $1=first_defect $2=src_rate $3=second_name $4=generator $5...=extra
  local FIRST="$1" SR="$2" SECOND="$3" GEN="$4"; shift 4
  # shellcheck disable=SC2086
  run python3 "evaluation/scripts/${GEN}" \
      --source-model-dir 1.7b \
      --source-method "${FIRST}/${SR}%" \
      --output-model-dir "1.7b/mixed/${FIRST}${SR}_${SECOND}" \
      --chapters $CHAPTERS \
      --rates $SECOND_RATES "$@"
}

if [ "$STAGE" = "generate" ]; then
  for SR in $SRC_RATES; do
    gen_pair grammar        "$SR" omission create_omission_variants.py
    gen_pair mistranslation "$SR" omission create_omission_variants.py
    gen_pair mistranslation "$SR" addition create_addition_variants.py --categories bad
  done
  echo "GENERATED. Next: bash evaluation/scripts/run_mixed_defect_campaign.sh answer"
  exit 0
fi

[ "$STAGE" = "answer" ] || { echo "unknown stage: $STAGE (use generate|answer)"; exit 1; }

for M in $MODELS; do
  case "$M" in
    llama1b)  TIER="llama 1b"; OLLAMA_MODEL="llama3.2:1b";  EXTRA="" ;;
    qwen1.5b) TIER="1.5b";     OLLAMA_MODEL="qwen2.5:1.5b"; EXTRA="" ;;
    qwen1.7b|1.7b) TIER="1.7b"; OLLAMA_MODEL="qwen3:1.7b";  EXTRA="--ollama-no-think" ;;
    *) echo "unknown model alias: $M" >&2; exit 1 ;;
  esac
  MIXDIRS="${MIXES:-$(ls "evaluation/outputs/luke1/1.7b/mixed" 2>/dev/null)}"
  for MIXDIRNAME in $MIXDIRS; do
    for CH in $CHAPTERS; do
      SRCD="evaluation/outputs/luke${CH}/1.7b/mixed/${MIXDIRNAME}"
      DSTROOT="evaluation/outputs/luke${CH}/${TIER}/mixed/${MIXDIRNAME}"
      [ -d "$SRCD" ] || { echo "[skip] $SRCD missing"; continue; }
      # copy artifacts for non-1.7b tiers
      if [ "$TIER" != "1.7b" ]; then
        for LEVDIR in "$SRCD"/*%/; do
          LEV="$(basename "$LEVDIR")"
          mkdir -p "$DSTROOT/$LEV"
          for F in passage_target.txt passage_target_decanonicalized.txt \
                   passage_source_decanonicalized.txt qa_target.json \
                   qa_target_decanonicalized.json decanonicalized_metadata.json \
                   passage_translation.json; do
            [ -f "$LEVDIR/$F" ] && [ ! -f "$DSTROOT/$LEV/$F" ] && cp "$LEVDIR/$F" "$DSTROOT/$LEV/$F"
          done
        done
      fi
      LEVELS=""
      for LEVDIR in "$SRCD"/*%/; do
        [ -f "$LEVDIR/passage_target_decanonicalized.txt" ] && LEVELS="$LEVELS $(basename "$LEVDIR")"
      done
      [ -z "$LEVELS" ] && { echo "[skip] luke${CH}/${MIXDIRNAME}: no levels"; continue; }
      N=$(python3 -c "
import json
d = json.load(open('evaluation/datasets/qa_output_luke_ch${CH}_all_formats.json'))
recs = d if isinstance(d, list) else d.get('items', d.get('questions', []))
print(len(recs))")
      echo "== [$M] luke${CH} mixed/${MIXDIRNAME} (N=$N):$LEVELS"
      # shellcheck disable=SC2086
      run python3 evaluation/scripts/answer_score_subset_in_place.py "$N" \
          --allow-fewer \
          --chapters "$CH" \
          --artifact-root-template "evaluation/outputs/luke{chapter}/${TIER}/mixed/${MIXDIRNAME}" \
          --methods $LEVELS \
          --answer-provider ollama \
          --answer-model "$OLLAMA_MODEL" $EXTRA \
          --answer-verse-window 2 \
          $ANSWER_EXTRA_ARGS \
          --summary-json "evaluation/outputs/reports/mixed_runs_${M}_${MIXDIRNAME}_luke${CH}.json"
    done
  done
done
echo "DONE. Analysis: python3 QA_algorithm/scripts/semireal_validation/additivity_mixed_defects.py"
