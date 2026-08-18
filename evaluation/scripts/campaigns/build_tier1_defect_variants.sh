#!/usr/bin/env bash
# Generate the defect-variant grid for the Tier 1 passages.
#
# Order matters and the first step is the point:
#
#   1. ONE base translation per passage -> tier1/<pid>/_base/llm_prompt_high/
#      Every defect variant is a perturbation of that single Chinese passage,
#      and every answer-model cell is seeded from it. This is what keeps the
#      defect axis and the ability axis clean: a per-model or per-defect
#      re-translation would put translation sampling noise (temperature 0 is not
#      bit-reproducible on the Responses API, ~5.6% divergence) on top of the
#      effect being measured.
#
#   2. Passage-specific banks for the two defects that need them.
#      mistranslation and awkward substitute real phrases, so their banks are
#      built per passage from the base translation. Without this they fall back
#      to global banks written against Luke, splicing Luke vocabulary into
#      Judges -- a defect the answer model can spot as alien text rather than
#      as degraded meaning.
#
#      addition and inconsistency keep their built-in banks: addition injects
#      generic filler and inconsistency's style pass rewrites in place, so
#      neither depends on passage vocabulary. omission and grammar are purely
#      algorithmic.
#
#   3. Six defect families x six dose rates, derived from that base.
#      Layout mirrors the Luke grid, so the existing analysis scripts read it:
#         tier1/<pid>/<defect>/<rate>/
#      The variant scripts perturb the TRANSLATED Chinese and copy the QA
#      across unchanged, so no re-translation happens here.
#
# Requirements: steps 1 and 2 need OPENAI_API_KEY. Step 3 is offline except
# inconsistency (--types style).
#
# Knobs:
#   DEFECTS="omission mistranslation grammar awkward addition inconsistency"
#   RATES="0% 5% 10% 15% 20% 30%"
#   PASSAGES="t1_judg9 ..."      restrict to a subset
#   OUT_ROOT="evaluation/outputs/tier1"
#   PASSAGE_DIR="evaluation/datasets/pseudonymized/passages/tier1"
#   QA_DIR="evaluation/datasets/pseudonymized/qa/tier1"
#   SKIP_BASE=1                  base translations already exist
#   SKIP_BANKS=1                 use the global Luke-derived banks instead
#   DRY_RUN=1
set -euo pipefail

OUT_ROOT="${OUT_ROOT:-evaluation/outputs/tier1}"
OUT_ROOT="${OUT_ROOT%/}"
OUTPUTS_ROOT="${OUT_ROOT%/*}"
OUTPUT_NAMESPACE="${OUT_ROOT##*/}"
METHOD="${METHOD:-llm_prompt_high}"
MAP="${MAP:-evaluation/datasets/pseudonym_remap/name_map_tier1_reconciled.json}"
PASSAGE_DIR="${PASSAGE_DIR:-evaluation/datasets/pseudonymized/passages/tier1}"
QA_DIR="${QA_DIR:-evaluation/datasets/pseudonymized/qa/tier1}"
DEFECTS="${DEFECTS:-omission mistranslation grammar awkward addition inconsistency}"
RATES="${RATES:-0% 5% 10% 15% 20% 30%}"
SKIP_BASE="${SKIP_BASE:-0}"
SKIP_BANKS="${SKIP_BANKS:-0}"
DRY_RUN="${DRY_RUN:-0}"

PAIRS=(
  "t1_judg9:judg_9_1-57.txt"
  "t1_judg17_18:judg_17_1-18_31.txt"
  "t1_2kgs6_7:2kgs_6_24-7_20.txt"
  "t1_1kgs13:1kgs_13_1-34.txt"
  "t1_2kgs11:2kgs_11_1-21.txt"
  "t1_2chr26:2chr_26_1-23.txt"
  "t1_2sam21:2sam_21_15-22.txt"
  "t1_acts19:acts_19_11-20.txt"
  "t1_acts20:acts_20_7-12.txt"
  "t1_acts23:acts_23_12-35.txt"
)

run() {
  if [[ "$DRY_RUN" == "1" ]]; then printf '  '; printf '%q ' "$@"; echo; else "$@"; fi
}

selected_pairs=()
for pair in "${PAIRS[@]}"; do
  pid="${pair%%:*}"
  if [[ -n "${PASSAGES:-}" ]]; then
    [[ " $PASSAGES " == *" $pid "* ]] || continue
  fi
  selected_pairs+=("$pair")
done

echo "=== 1/3  base translation (one per passage, shared by every defect and model)"
for pair in "${selected_pairs[@]}"; do
  pid="${pair%%:*}"; name="${pair#*:}"
  base="$OUT_ROOT/$pid/_base"
  if [[ "$SKIP_BASE" == "1" || -f "$base/$METHOD/passage_target_decanonicalized.txt" ]]; then
    echo "  reuse $base"
    continue
  fi
  : "${OPENAI_API_KEY:?export OPENAI_API_KEY for the base translation}"
  echo "  $pid"
  run python evaluation/main.py \
    "$PASSAGE_DIR/$name" "$QA_DIR/${pid}_all_formats.json" \
    --output-dir "$base" --run-name "${pid}_base" \
    --methods "$METHOD" --stop-after decanonicalize \
    --skip-entity-discovery --pre-blinded --pseudonym-map "$MAP" \
    --temperature 0.0 --continue-on-method-error
done

# Every defect script warns-and-continues when a base translation is missing,
# and exits 0. So a base that failed in step 1 would silently yield no variants
# for that passage while the run still reports success. Check explicitly.
if [[ "$DRY_RUN" != "1" ]]; then
  missing_base=0
  for pair in "${selected_pairs[@]}"; do
    pid="${pair%%:*}"
    f="$OUT_ROOT/$pid/_base/$METHOD/passage_target_decanonicalized.txt"
    [[ -s "$f" ]] || { echo "  MISSING base translation: $f" >&2; missing_base=$((missing_base+1)); }
  done
  if (( missing_base )); then
    echo "  $missing_base passage(s) have no base translation; stopping." >&2
    exit 1
  fi
fi

# Variant scripts append each passage dir to --root. Derive both pieces from
# OUT_ROOT so a staging namespace such as tier1_bsb can never fall through to
# the production tier1 tree.
passage_dirs=()
for pair in "${selected_pairs[@]}"; do
  passage_dirs+=("$OUTPUT_NAMESPACE/${pair%%:*}")
done

echo
echo "=== 2/3  passage-specific defect banks"
# mistranslation and awkward read a per-cell bank and silently fall back to a
# global one written against Luke. That still yields a dose gradient, but the
# injected material is drawn from the wrong text -- Luke vocabulary spliced into
# Judges. Generating banks per passage keeps the defect plausible for the
# passage it perturbs, which matters because the proxy is meant to measure
# adequacy loss rather than detect obviously alien text.
if [[ "$SKIP_BANKS" == "1" ]]; then
  echo "  skipped (SKIP_BANKS=1); variants will use the global Luke-derived banks"
else
  : "${OPENAI_API_KEY:?export OPENAI_API_KEY for bank generation}"
  if [[ "$DEFECTS" == *mistranslation* ]]; then
    echo "  --- mistranslation banks -> <passage>/_base/_shared/"
    run python evaluation/scripts/variants/generate_mistranslation_banks.py \
      --root "$OUTPUTS_ROOT" --passage-dirs "${passage_dirs[@]}" \
      --source-model-dir _base --source-method "$METHOD"
  fi
  if [[ "$DEFECTS" == *awkward* ]]; then
    echo "  --- awkward style banks -> datasets/perturbations/awkward_style/"
    run python evaluation/scripts/variants/generate_chapter_awkward_style_banks.py \
      --root "$OUTPUTS_ROOT" --passage-dirs "${passage_dirs[@]}" \
      --source-model-dir _base --source-method "$METHOD"
  fi
  # Positive check. Exit codes are necessary but not sufficient: a bank can be
  # skipped as "reuse" or written empty, and the variant scripts fall back
  # rather than fail. Assert the files are actually on disk.
  if [[ "$DRY_RUN" != "1" ]]; then
    missing=0
    for pair in "${selected_pairs[@]}"; do
      pid="${pair%%:*}"
      if [[ "$DEFECTS" == *mistranslation* ]]; then
        f="$OUT_ROOT/$pid/_base/_shared/mistranslation_bank_zh.json"
        [[ -s "$f" ]] || { echo "  MISSING $f" >&2; missing=$((missing+1)); }
      fi
      if [[ "$DEFECTS" == *awkward* ]]; then
        f="evaluation/datasets/perturbations/awkward_style/${OUTPUT_NAMESPACE}_${pid}_awkward_style_bank.json"
        [[ -s "$f" ]] || { echo "  MISSING $f" >&2; missing=$((missing+1)); }
      fi
    done
    if (( missing )); then
      echo "  $missing bank file(s) missing; not building variants on fallback banks." >&2
      echo "  Re-run bank generation, or pass SKIP_BANKS=1 to accept the global banks." >&2
      exit 1
    fi
    echo "  all expected bank files present"
  fi
fi

echo
echo "=== 3/3  defect variants"
# --require-bank turns the silent fallback into an error for the two defects
# that substitute passage vocabulary. Omitted when SKIP_BANKS=1, which is the
# explicit opt-in to the global banks.
require_bank=()
[[ "$SKIP_BANKS" == "1" ]] || require_bank=(--require-bank)

for defect in $DEFECTS; do
  case "$defect" in
    awkward) script=create_awkward_style_variants.py ;;
    *)       script="create_${defect}_variants.py" ;;
  esac
  path="evaluation/scripts/variants/$script"
  if [[ ! -f "$path" ]]; then
    echo "  skip $defect: $path not found" >&2
    continue
  fi
  echo "  --- $defect"
  strict=()
  case "$defect" in
    mistranslation|awkward) strict=("${require_bank[@]}") ;;
  esac
  run python "$path" \
    --root "$OUTPUTS_ROOT" \
    --passage-dirs "${passage_dirs[@]}" \
    --source-model-dir _base \
    --source-method "$METHOD" \
    --output-model-dir "$defect" \
    --rates $RATES ${strict+"${strict[@]}"}
done

echo
echo "done. Grid layout: $OUT_ROOT/<passage>/<defect>/<rate>/"
echo "Next: answer them with the small models."
