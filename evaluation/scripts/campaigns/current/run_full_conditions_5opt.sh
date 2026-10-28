#!/usr/bin/env bash
# Full unblinded Gold-72 grid: clean + WBW + 3 families × 6 positive rates.
# CHECK_ONLY=1 checks all shared inputs without model calls or corpus writes.
# PREVIEW=1 prints the plan only. Missing/duplicate/off-target inputs fail closed.
set -euo pipefail

export OUT_ROOT="${OUT_ROOT:-evaluation/outputs/tier1_bsb_unblinded_5opt_think}"
export QA_DIR="${QA_DIR:-evaluation/datasets/qa/tier1_gold72_canonical_5opt}"
export PASSAGE_DIR="${PASSAGE_DIR:-evaluation/datasets/passages/tier1_bsb}"
export MAP="${MAP:-evaluation/datasets/pseudonym_remap/empty_map_unblinded.json}"
export WINDOWS="${WINDOWS:-QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json}"
export MODELS="${MODELS:-llama3.2:1b qwen2.5:1.5b qwen3:1.7b}"
export PASSAGES="${PASSAGES:-t1_judg9 t1_judg17_18 t1_2kgs6_7 t1_1kgs13 t1_2kgs11 t1_2chr26 t1_2sam21 t1_acts19 t1_acts20 t1_acts23}"
export PYTHON_BIN="${PYTHON_BIN:-python3}"
export QA_FORMATS="${QA_FORMATS:-open,mcq}"
export MCQ_CHOICE_LABELS=ABCDE MCQ_ABSTAIN_LABEL=E
export NO_THINK="${NO_THINK:-0}"
export SHARE_QA=1 DISCOVER_LEVELS=0 REPLACE_INPUTS=1
export FORCE_ANSWER=1 FORCE_BACKTRANSLATE=1 FORCE_SCORE=1
unset STOP_AFTER
read -r -a selected_passages <<< "$PASSAGES"
read -r -a selected_models <<< "$MODELS"
echo "${#selected_passages[@]} passages × 20 conditions × ${#selected_models[@]} models = $((${#selected_passages[@]} * 20 * ${#selected_models[@]})) cells"
echo "Models: $MODELS"
echo "Conditions: clean once; WBW once; omission, mistranslation, grammar each at 5% 10% 15% 20% 25% 30%"
echo "QA: $QA_DIR ($QA_FORMATS); NO_THINK=$NO_THINK; output: $OUT_ROOT"
[[ "${PREVIEW:-0}" == "1" ]] && exit 0

"$PYTHON_BIN" evaluation/scripts/analysis/current/check_full_conditions_5opt.py \
  --root "$OUT_ROOT" --passages "${selected_passages[@]}" \
  --qa-dir "$QA_DIR" --passage-dir "$PASSAGE_DIR" \
  --coverage-tolerance-pp "${COVERAGE_TOLERANCE_PP:-2}"
[[ -s "$MAP" && -s "$WINDOWS" && -d "$PASSAGE_DIR" ]] || { echo "Missing map, verse windows, or passage directory" >&2; exit 1; }
[[ "${CHECK_ONLY:-0}" == "1" || "${DRY_RUN:-0}" == "1" ]] && exit 0

if [[ -z "${OPENAI_API_KEY:-}" && -f .env ]]; then set -a; . ./.env; set +a; fi
: "${OPENAI_API_KEY:?export OPENAI_API_KEY (back-translation, judge, MCQ mapping)}"
installed=$(ollama list)
for model in "${selected_models[@]}"; do
  if ! printf '%s\n' "$installed" | awk 'NR>1 {print $1}' | grep -Fxq -- "$model"; then
    echo "Missing Ollama model: $model" >&2; exit 1
  fi
done
code=$(curl --connect-timeout 10 --max-time 30 -s -o /dev/null -w '%{http_code}' \
  https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY")
[[ "$code" == "200" ]] || { echo "OpenAI authentication failed (HTTP $code)" >&2; exit 1; }
export SKIP_PREFLIGHT=1

DEFECTS=omission RATES="0% 5% 10% 15% 20% 25% 30%" \
  bash evaluation/scripts/campaigns/current/run_tier1_defect_models.sh
DEFECTS="mistranslation grammar" RATES="5% 10% 15% 20% 25% 30%" \
  bash evaluation/scripts/campaigns/current/run_tier1_defect_models.sh
SOURCE_CELL=. bash evaluation/scripts/campaigns/current/run_tier1_wbw_models.sh
echo "Campaign finished; inspect answer completeness and scores before analysis."
