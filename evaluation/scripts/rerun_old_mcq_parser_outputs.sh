#!/usr/bin/env bash
set -euo pipefail

run_main() {
  local ch="$1"
  local output_dir="$2"
  local answer_model="$3"
  shift 3

  if [[ "$answer_model" == qwen3:* ]]; then
    python3 evaluation/main.py \
      "evaluation/datasets/test_passage_luke${ch}.txt" \
      "evaluation/datasets/qa_output_luke_ch${ch}_all_formats.json" \
      --output-dir "$output_dir" \
      --run-name "luke_ch${ch}_all_formats" \
      --methods "$@" \
      --answer-provider ollama \
      --answer-model "$answer_model" \
      --ollama-no-think \
      --allow-partial-answers \
      --continue-on-method-error \
      --force-answer \
      --force-backtranslate \
      --force-score
  else
    python3 evaluation/main.py \
      "evaluation/datasets/test_passage_luke${ch}.txt" \
      "evaluation/datasets/qa_output_luke_ch${ch}_all_formats.json" \
      --output-dir "$output_dir" \
      --run-name "luke_ch${ch}_all_formats" \
      --methods "$@" \
      --answer-provider ollama \
      --answer-model "$answer_model" \
      --allow-partial-answers \
      --continue-on-method-error \
      --force-answer \
      --force-backtranslate \
      --force-score
  fi
}

run_main 1 "evaluation/outputs/luke1/llama 1b" "llama3.2:1b" \
  llm_prompt_low helsinki nllb-200-1.3B llm_prompt_high llm_prompt_medium \
  nllb-200-distilled-600M mBART-50 google_word_by_word

run_main 2 "evaluation/outputs/luke2/llama 1b" "llama3.2:1b" \
  llm_prompt_low helsinki nllb-200-1.3B llm_prompt_high llm_prompt_medium \
  nllb-200-distilled-600M

run_main 3 "evaluation/outputs/luke3/llama 1b" "llama3.2:1b" \
  llm_prompt_low helsinki nllb-200-1.3B llm_prompt_high llm_prompt_medium \
  nllb-200-distilled-600M mBART-50 google_word_by_word

run_main 4 "evaluation/outputs/luke4/llama 1b" "llama3.2:1b" \
  llm_prompt_low helsinki nllb-200-1.3B llm_prompt_high llm_prompt_medium \
  nllb-200-distilled-600M mBART-50 google_word_by_word

run_main 5 "evaluation/outputs/luke5/llama 1b" "llama3.2:1b" \
  llm_prompt_low helsinki nllb-200-1.3B llm_prompt_high llm_prompt_medium \
  nllb-200-distilled-600M mBART-50 google_word_by_word

run_main 6 "evaluation/outputs/luke6/llama 1b" "llama3.2:1b" \
  llm_prompt_low helsinki nllb-200-1.3B llm_prompt_high llm_prompt_medium \
  nllb-200-distilled-600M mBART-50 google_word_by_word

run_main 7 "evaluation/outputs/luke7/llama 1b" "llama3.2:1b" \
  llm_prompt_medium nllb-200-distilled-600M

run_main 8 "evaluation/outputs/luke8/llama 1b" "llama3.2:1b" \
  nllb-200-1.3B llm_prompt_high

run_main 2 "evaluation/outputs/luke2/1.5b" "qwen2.5:1.5b" \
  llm_prompt_low helsinki nllb-200-1.3B llm_prompt_high \
  nllb-200-distilled-600M mBART-50 google_word_by_word

run_main 3 "evaluation/outputs/luke3/1.5b" "qwen2.5:1.5b" \
  nllb-200-distilled-600M mBART-50

run_main 4 "evaluation/outputs/luke4/1.5b" "qwen2.5:1.5b" \
  llm_prompt_low nllb-200-1.3B llm_prompt_high llm_prompt_medium mBART-50

run_main 5 "evaluation/outputs/luke5/1.5b" "qwen2.5:1.5b" \
  llm_prompt_low nllb-200-1.3B llm_prompt_high mBART-50 google_word_by_word

run_main 7 "evaluation/outputs/luke7/1.5b" "qwen2.5:1.5b" \
  llm_prompt_low

run_main 8 "evaluation/outputs/luke8/1.5b" "qwen2.5:1.5b" \
  nllb-200-1.3B llm_prompt_medium

run_main 1 "evaluation/outputs/luke1/nllb_dropout" "qwen3:1.7b" \
  nllb-200-1.3B-dropout-0.15

run_main 8 "evaluation/outputs/luke8/omission" "qwen3:1.7b" \
  "0%"
