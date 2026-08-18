#!/usr/bin/env bash
# Run the small answer models over the 10 tier-1 passages.
#
# Consumes the PSEUDONYMIZED inputs written by build_tier1_pseudonymized.sh --
# run that first. The passage and its QA are blinded with one shared table, so
# the expected answers live in the same namespace as the passage the model
# reads. Pointing this at the raw datasets/ files instead reproduces the
# 2026-08-04 failure: the judge compares placeholder answers against canonical
# expected answers and marks correct answers partial.
#
# --skip-entity-discovery is therefore required, not an optimization: the inputs
# are already blind, and a second in-pipeline pass would pseudonymize the
# pseudonyms.
#
# Requirements (run from the repo root, on your local machine):
#   - Ollama running with each MODELS entry pulled
#   - OPENAI_API_KEY exported (QA translation, passage translation,
#     back-translation, judge)
#
# Knobs:
#   MODELS="llama3.2:1b qwen2.5:1.5b qwen3:1.7b"
#   METHODS="llm_prompt_high"        # passage translation methods
#   OUT_ROOT="evaluation/outputs/tier1"
#   PASSAGE_DIR="evaluation/datasets/pseudonymized/passages/tier1"
#   QA_DIR="evaluation/datasets/pseudonymized/qa/tier1"
#   STOP_AFTER=""                    # e.g. answer, to skip backtranslate+score
#   RAW=1                            # use un-pseudonymized inputs (not advised)
#   WINDOWS=path|""                  # curated verse windows; "" for +/-N instead
#   FORCE_TRANSLATE=1                # rebuild translated QA (keeps passage translation)
#   REPLACE_INPUTS=1                 # replace cached per-model QA with shared refreshed QA
#   FORCE_ANSWER=1                   # overwrite generated answer files
#   NO_THINK=1                       # pass --ollama-no-think to qwen3 models
#   MCQ_CHOICE_MAPPER=openai         # normalize textual MCQ replies to A-D
#   DRY_RUN=1                        # print commands only
set -euo pipefail

MODELS="${MODELS:-llama3.2:1b qwen2.5:1.5b qwen3:1.7b}"
METHODS="${METHODS:-llm_prompt_high}"
OUT_ROOT="${OUT_ROOT:-evaluation/outputs/tier1}"
STOP_AFTER="${STOP_AFTER:-}"
DRY_RUN="${DRY_RUN:-0}"
RAW="${RAW:-0}"
# Translate once per passage and share it across answer models. Set to 0 only
# if you deliberately want an independent translation draw per model.
SHARE_TRANSLATION="${SHARE_TRANSLATION:-1}"
FORCE_TRANSLATE="${FORCE_TRANSLATE:-0}"
REPLACE_INPUTS="${REPLACE_INPUTS:-$FORCE_TRANSLATE}"
FORCE_ANSWER="${FORCE_ANSWER:-0}"
NO_THINK="${NO_THINK:-1}"
MCQ_CHOICE_MAPPER="${MCQ_CHOICE_MAPPER:-openai}"
# Curated 3-verse windows, hand-checked to contain the answer-bearing verse.
# Set WINDOWS="" to fall back to the mechanical --answer-verse-window span.
MAP="${MAP:-evaluation/datasets/pseudonym_remap/name_map_tier1_reconciled.json}"
QA_TRANSLATION_CORRECTIONS="${QA_TRANSLATION_CORRECTIONS:-evaluation/datasets/qa/tier1_qa_translation_corrections_zh.json}"
WINDOWS="${WINDOWS-QA_algorithm/inputs/tier1_qa_verse_windows.json}"
if [[ -n "$WINDOWS" && ! -f "$WINDOWS" ]]; then
  echo "error: verse windows file not found: $WINDOWS" >&2
  echo 'Set WINDOWS="" to use the mechanical --answer-verse-window instead.' >&2
  exit 1
fi

if [[ "$RAW" == "1" ]]; then
  PASSAGE_DIR="${PASSAGE_DIR:-evaluation/datasets/passages/tier1}"
  QA_DIR="${QA_DIR:-evaluation/datasets/qa/tier1_QAs_easy}"
  echo "WARNING: RAW=1 -- expected answers will keep canonical names and the" >&2
  echo "judge will under-score every name-bearing item." >&2
else
  PASSAGE_DIR="${PASSAGE_DIR:-evaluation/datasets/pseudonymized/passages/tier1}"
  QA_DIR="${QA_DIR:-evaluation/datasets/pseudonymized/qa/tier1}"
  if [[ ! -d "$PASSAGE_DIR" ]]; then
    echo "error: $PASSAGE_DIR not found." >&2
    echo "Run: bash evaluation/scripts/campaigns/build_tier1_pseudonymized.sh" >&2
    exit 1
  fi
fi

# passage_id : passage filename  (filenames come from the tier-1 CSV references)
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

# Translate each passage ONCE, into <pid>/_base, and seed every answer-model
# cell from it.
#
# Without this each model triggered its own QA and passage translation, because
# _shared lives under --output-dir and --output-dir is per model. Temperature 0
# is not bit-reproducible on the Responses API (~5.6% residual divergence), so
# the three models were being asked differently-worded questions about a
# differently-worded passage -- variance landing directly on top of the
# respondent-ability axis the design exists to measure. Two runs of one
# identical cell differed on three items for exactly this reason.
#
# Reuse is existence-based, so seeding the files is enough to make the pipeline
# skip translation. This is also the layout the defect-variant scripts expect:
# they derive perturbed passages from one base translation.
seed_from_base() {
  local pid="$1" base_dir="$2" model_dir="$3" base_name="$4" run_name="$5"
  mkdir -p "$model_dir/_shared" "$model_dir/$METHOD_DIR"
  local f target
  for f in "$base_dir"/_shared/"$base_name"_*; do
    [[ -e "$f" ]] || continue
    target="$(basename "$f" | sed "s/^${base_name}_/${run_name}_/")"
    if [[ "$REPLACE_INPUTS" == "1" ]]; then
      cp -f "$f" "$model_dir/_shared/$target"
    else
      cp -n "$f" "$model_dir/_shared/$target" 2>/dev/null || true
    fi
  done
  for f in passage_source_decanonicalized.txt passage_target.txt \
           passage_target_decanonicalized.txt passage_translation.json \
           qa_target.json qa_target_decanonicalized.json decanonicalized_metadata.json; do
    if [[ -e "$base_dir/$METHOD_DIR/$f" ]]; then
      if [[ "$REPLACE_INPUTS" == "1" ]]; then
        cp -f "$base_dir/$METHOD_DIR/$f" "$model_dir/$METHOD_DIR/$f"
      else
        cp -n "$base_dir/$METHOD_DIR/$f" "$model_dir/$METHOD_DIR/$f" 2>/dev/null || true
      fi
    fi
  done
}

METHOD_DIR="${METHODS%% *}"

for pair in "${PAIRS[@]}"; do
  pid="${pair%%:*}"
  passage="$PASSAGE_DIR/${pair#*:}"
  qa="$QA_DIR/${pid}_all_formats.json"

  [[ -f "$passage" ]] || { echo "missing passage: $passage" >&2; exit 1; }
  [[ -f "$qa" ]]      || { echo "missing qa: $qa" >&2; exit 1; }

  base_dir="$OUT_ROOT/$pid/_base"
  base_name="${pid}_base"
  if [[ "$SHARE_TRANSLATION" == "1" && ( "$FORCE_TRANSLATE" == "1" || ! -f "$base_dir/$METHOD_DIR/passage_target_decanonicalized.txt" ) ]]; then
    echo "=== $pid / base translation (shared by all models)"
    base_cmd=(python evaluation/main.py "$passage" "$qa"
              --output-dir "$base_dir" --run-name "$base_name"
              --methods $METHODS --stop-after decanonicalize
              --temperature 0.0 --continue-on-method-error)
    [[ "$RAW" == "1" ]] || base_cmd+=(--skip-entity-discovery --pre-blinded --pseudonym-map "$MAP")
    [[ "$FORCE_TRANSLATE" == "1" ]] && base_cmd+=(--force-translate)
    if [[ "$DRY_RUN" == "1" ]]; then printf '%q ' "${base_cmd[@]}"; echo; else "${base_cmd[@]}"; fi
  fi

  # Apply human-reviewed, content-ID-keyed QA fixes after translation and
  # before the shared base is copied into answer-model cells.
  if [[ "$SHARE_TRANSLATION" == "1" && "$DRY_RUN" != "1" && -f "$QA_TRANSLATION_CORRECTIONS" ]]; then
    python evaluation/scripts/data_prep/apply_qa_translation_corrections.py \
      "$base_dir" --corrections "$QA_TRANSLATION_CORRECTIONS"
  fi

  for model in $MODELS; do
    slug="${model//[:.]/}"
    if [[ "$SHARE_TRANSLATION" == "1" && "$DRY_RUN" != "1" ]]; then
      seed_from_base "$pid" "$base_dir" "$OUT_ROOT/$pid/$slug" "$base_name" "${pid}_${slug}"
    fi
    cmd=(python evaluation/main.py "$passage" "$qa"
         --output-dir "$OUT_ROOT/$pid/$slug"
         --run-name "${pid}_${slug}"
         --methods $METHODS
         --answer-provider ollama
         --answer-model "$model"
         --mcq-choice-mapper "$MCQ_CHOICE_MAPPER"
         --answer-verse-window 2
         --temperature 0.0
         --allow-partial-answers
         --continue-on-method-error)
    [[ "$RAW" == "1" ]] || cmd+=(--skip-entity-discovery --pre-blinded)
    [[ -n "$WINDOWS" ]] && cmd+=(--answer-verse-windows-json "$WINDOWS")
    [[ "$RAW" == "1" ]] || cmd+=(--pseudonym-map "$MAP")
    [[ "$model" == qwen3* && "$NO_THINK" == "1" ]] && cmd+=(--ollama-no-think)
    [[ "$FORCE_ANSWER" == "1" ]] && cmd+=(--force-answer)
    [[ -n "$STOP_AFTER" ]] && cmd+=(--stop-after "$STOP_AFTER")

    echo "=== $pid / $model"
    if [[ "$DRY_RUN" == "1" ]]; then
      printf '%q ' "${cmd[@]}"; echo
    else
      "${cmd[@]}"
    fi
  done
done
