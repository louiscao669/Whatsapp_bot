#!/usr/bin/env bash
set -u

ROOT="evaluation/outputs"
LOG_PREFIX="[resume-synthetic]"
FAILED=0

run_group() {
  local chapter="$1"
  local category="$2"
  shift 2
  local methods=("$@")
  local missing=()
  local method

  for method in "${methods[@]}"; do
    if [[ ! -f "${ROOT}/luke${chapter}/${category}/${method}/scores_target_llama.json" ]]; then
      missing+=("$method")
    fi
  done

  if [[ "${#missing[@]}" -eq 0 ]]; then
    echo "${LOG_PREFIX} skip Luke ${chapter} ${category}: all scores present"
    return 0
  fi

  echo "${LOG_PREFIX} run Luke ${chapter} ${category}: ${missing[*]}"
  python evaluation/main.py \
    "evaluation/datasets/test_passage_luke${chapter}.txt" \
    "evaluation/datasets/qa_output_luke_ch${chapter}_all_formats.json" \
    --output-dir "${ROOT}/luke${chapter}/${category}" \
    --run-name "luke_ch${chapter}_all_formats" \
    --methods "${missing[@]}" \
    --answer-provider ollama \
    --answer-model qwen3:1.7b \
    --ollama-no-think \
    --allow-partial-answers \
    --expanded-answer-format \
    --continue-on-method-error
  local status=$?
  if [[ "$status" -ne 0 ]]; then
    echo "${LOG_PREFIX} failed Luke ${chapter} ${category}: exit ${status}" >&2
    FAILED=1
  fi
}

grammar_methods=("0%" "5%" "10%" "15%" "20%" "30%")
awkward_methods=("0%" "5%" "10%" "15%" "20%" "30%")
omission_methods=("0%" "5%" "10%" "15%" "20%" "30%")
inconsistency_methods=(
  "0%"
  "name_5%" "style_5%"
  "name_10%" "style_10%"
  "name_15%" "style_15%"
  "name_20%" "style_20%"
)
addition_methods=(
  "0%"
  "neutral_5%" "bad_5%" "adversarial_5%"
  "neutral_10%" "bad_10%" "adversarial_10%"
  "neutral_15%" "bad_15%" "adversarial_15%"
  "neutral_20%" "bad_20%" "adversarial_20%"
  "neutral_30%" "bad_30%" "adversarial_30%"
)

echo "${LOG_PREFIX} started $(date)"

for chapter in 1 2 3 4 5 6 7 8; do
  run_group "$chapter" "grammar" "${grammar_methods[@]}"
  run_group "$chapter" "inconsistency" "${inconsistency_methods[@]}"
  run_group "$chapter" "awkward" "${awkward_methods[@]}"
  run_group "$chapter" "addition" "${addition_methods[@]}"
  run_group "$chapter" "omission" "${omission_methods[@]}"
done

echo "${LOG_PREFIX} finished $(date) status=${FAILED}"
exit "$FAILED"
