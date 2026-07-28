#!/usr/bin/env bash
set -euo pipefail

export OPENAI_JUDGE_MODEL="${OPENAI_JUDGE_MODEL:-gpt-5.4-mini}"
export OPENAI_TRANSLATION_MODEL="${OPENAI_TRANSLATION_MODEL:-gpt-5.4-mini}"

OUTPUT_NAME="${OUTPUT_NAME:-scores_target_llama_core_claim.json}"
JUDGE_BATCH_SIZE="${JUDGE_BATCH_SIZE:-20}"
LIMIT="${LIMIT:-0}"
DRY_RUN="${DRY_RUN:-0}"
SKIP_EXISTING="${SKIP_EXISTING:-1}"

count=0
scored=0
skipped=0

while IFS= read -r -d '' generated_answers; do
  dir="$(dirname "$generated_answers")"
  qa_json="$dir/qa_target_decanonicalized.json"

  if [[ ! -f "$qa_json" ]]; then
    qa_json="$dir/qa_target.json"
  fi

  if [[ ! -f "$qa_json" ]]; then
    echo "skip: no qa_target JSON for $dir" >&2
    continue
  fi

  output_json="$dir/$OUTPUT_NAME"

  if [[ "$SKIP_EXISTING" == "1" && -f "$output_json" ]]; then
    skipped=$((skipped + 1))
    echo "skip existing: $output_json"
    continue
  fi

  count=$((count + 1))

  echo "[$count] $generated_answers -> $output_json"

  if [[ "$DRY_RUN" == "1" ]]; then
    if [[ "$LIMIT" != "0" && "$count" -ge "$LIMIT" ]]; then
      echo "limit reached: $LIMIT"
      break
    fi
    continue
  fi

  python evaluation/scripts/score_generated_answers.py \
    "$generated_answers" \
    "$qa_json" \
    "$output_json" \
    --judge-model "$OPENAI_JUDGE_MODEL" \
    --translation-model "$OPENAI_TRANSLATION_MODEL" \
    --judge-batch-size "$JUDGE_BATCH_SIZE" \
    --placeholder-standard-answers

  scored=$((scored + 1))

  if [[ "$LIMIT" != "0" && "$count" -ge "$LIMIT" ]]; then
    echo "limit reached: $LIMIT"
    break
  fi
done < <(find evaluation/outputs/luke* -path '*/generated_answers_target_llama.json' -print0)

echo "done: scored=$scored skipped_existing=$skipped"
