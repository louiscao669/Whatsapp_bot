#!/usr/bin/env bash
# Answer the Tier 1 defect-variant cells with the small answer models.
#
# The variants live at            tier1/<pid>/<defect>/<rate>/
# and each model needs its own    tier1/<pid>/<model>/<defect>/<rate>/
# because the answer and score files would otherwise collide between models.
#
# So each cell is seeded (copied) from the shared variant, then answered.
# Crucially the variants all derive from ONE base translation per passage, so
# every model and every dose level sees the same Chinese text apart from the
# injected defect -- which is the whole point of the design. Nothing here
# re-translates.
#
# main.py treats a variant directory as an "external artifact" method: it skips
# translate/decanonicalize when the folder already contains
# passage_translation.json, passage_target.txt, passage_target_decanonicalized.txt
# and qa_target_decanonicalized.json. The method name carries the subpath, so
# --methods "mistranslation/15%" resolves to <output-dir>/mistranslation/15%.
#
# Requirements: Ollama running with each model pulled; OPENAI_API_KEY exported
# (back-translation, judge, MCQ choice mapping).
#
# Knobs:
#   MODELS="llama3.2:1b qwen2.5:1.5b qwen3:1.7b"
#   DEFECTS="mistranslation grammar"
#   RATES="15% 30%"
#   DISCOVER_LEVELS=1           run every generated nonzero level per family
#   PASSAGES="t1_judg9"        default: every passage that has the variants
#   PASSAGE_DIR=...             pseudonymized source passages
#   QA_DIR=...                  pseudonymized QA set used for scoring
#   REPLACE_INPUTS=1            refresh cached model-cell variant inputs
#   FORCE_ANSWER=1              overwrite answers and all downstream outputs
#   DRY_RUN=1
set -euo pipefail

OUT_ROOT="${OUT_ROOT:-evaluation/outputs/tier1}"
MODELS="${MODELS:-llama3.2:1b qwen2.5:1.5b qwen3:1.7b}"
DEFECTS="${DEFECTS:-mistranslation grammar}"
RATES="${RATES:-15% 30%}"
DISCOVER_LEVELS="${DISCOVER_LEVELS:-0}"
MAP="${MAP:-evaluation/datasets/pseudonym_remap/name_map_tier1_reconciled.json}"
WINDOWS="${WINDOWS-QA_algorithm/inputs/tier1_qa_verse_windows.json}"
PASSAGE_DIR="${PASSAGE_DIR:-evaluation/datasets/pseudonymized/passages/tier1}"
QA_DIR="${QA_DIR:-evaluation/datasets/pseudonymized/qa/tier1}"
DRY_RUN="${DRY_RUN:-0}"
REPLACE_INPUTS="${REPLACE_INPUTS:-0}"
FORCE_ANSWER="${FORCE_ANSWER:-0}"
FORCE_BACKTRANSLATE="${FORCE_BACKTRANSLATE:-0}"
FORCE_SCORE="${FORCE_SCORE:-0}"
STOP_AFTER="${STOP_AFTER:-}"
MCQ_CHOICE_MAPPER="${MCQ_CHOICE_MAPPER:-openai}"
# NO_THINK=0 lets qwen3 reason. /no_think alone is ignored by qwen3:1.7b, so the
# pipeline sends Ollama's structured think:false -- omitting the flag is what
# actually enables reasoning.
NO_THINK="${NO_THINK:-1}"
# Appended to the model dir name. Thinking on/off are different conditions and
# must not share an output cell; with NO_THINK=0 this defaults to "_think".
if [[ -z "${SLUG_SUFFIX+x}" ]]; then
  [[ "$NO_THINK" == "0" ]] && SLUG_SUFFIX="_think" || SLUG_SUFFIX=""
fi

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

# Files that define the cell. Deliberately excludes generated_answers* and
# scores*, so re-seeding never overwrites results already produced.
ARTIFACTS=(passage_source_decanonicalized.txt passage_target.txt
           passage_target_decanonicalized.txt passage_translation.json
           qa_target.json qa_target_decanonicalized.json)

ran=0; skipped=0
for pair in "${PAIRS[@]}"; do
  pid="${pair%%:*}"; name="${pair#*:}"
  [[ -n "${PASSAGES:-}" && " $PASSAGES " != *" $pid "* ]] && continue

  for defect in $DEFECTS; do
    levels=()
    if [[ "$DISCOVER_LEVELS" == "1" ]]; then
      defect_root="$OUT_ROOT/$pid/$defect"
      if [[ -d "$defect_root" ]]; then
        while IFS= read -r level; do
          [[ -n "$level" ]] && levels+=("$level")
        done < <(
          find "$defect_root" -mindepth 1 -maxdepth 1 -type d \
            ! -name '0%' ! -name '_*' -exec basename {} \; | LC_ALL=C sort
        )
      fi
    else
      read -r -a levels <<< "$RATES"
    fi
    if (( ${#levels[@]} == 0 )); then
      echo "  skip $pid/$defect: no selected variant levels" >&2
      skipped=$((skipped+1))
      continue
    fi

    for rate in "${levels[@]}"; do
      src="$OUT_ROOT/$pid/$defect/$rate"
      if [[ ! -f "$src/passage_target_decanonicalized.txt" ]]; then
        echo "  skip $pid/$defect/$rate: variant not generated" >&2
        skipped=$((skipped+1)); continue
      fi

      for model in $MODELS; do
        base_slug="${model//[:.]/}"
        slug="${base_slug}${SLUG_SUFFIX}"
        dst="$OUT_ROOT/$pid/$slug/$defect/$rate"
        if [[ "$DRY_RUN" != "1" ]]; then
          mkdir -p "$dst"
          # Reuse the base slug's translated QA rather than re-translating into
          # the new cell: the thinking condition must differ ONLY in inference,
          # not in the Chinese text the model reads.
          if [[ -n "$SLUG_SUFFIX" && -d "$OUT_ROOT/$pid/$base_slug/_shared" ]]; then
            mkdir -p "$OUT_ROOT/$pid/$slug/_shared"
            for f in "$OUT_ROOT/$pid/$base_slug"/_shared/"${pid}_${base_slug}"_*; do
              [[ -e "$f" ]] || continue
              t="$(basename "$f" | sed "s/^${pid}_${base_slug}_/${pid}_${slug}_/")"
              cp -n "$f" "$OUT_ROOT/$pid/$slug/_shared/$t" 2>/dev/null || true
            done
          fi
          for f in "${ARTIFACTS[@]}"; do
            if [[ -f "$src/$f" ]]; then
              if [[ "$REPLACE_INPUTS" == "1" ]]; then
                cp -f "$src/$f" "$dst/$f"
              else
                cp -n "$src/$f" "$dst/$f" 2>/dev/null || true
              fi
            fi
          done
        fi

        cmd=(python evaluation/main.py
             "$PASSAGE_DIR/$name" "$QA_DIR/${pid}_all_formats.json"
             --output-dir "$OUT_ROOT/$pid/$slug"
             --run-name "${pid}_${slug}"
             --methods "$defect/$rate"
             --answer-provider ollama --answer-model "$model"
             --mcq-choice-mapper "$MCQ_CHOICE_MAPPER"
             --skip-entity-discovery --pre-blinded
             --pseudonym-map "$MAP"
             --answer-verse-window 2 --temperature 0.0
             --allow-partial-answers --continue-on-method-error)
        [[ -n "$WINDOWS" ]] && cmd+=(--answer-verse-windows-json "$WINDOWS")
        [[ "$model" == qwen3* && "$NO_THINK" == "1" ]] && cmd+=(--ollama-no-think)
        [[ "$FORCE_ANSWER" == "1" ]] && cmd+=(--force-answer)
        [[ "$FORCE_BACKTRANSLATE" == "1" ]] && cmd+=(--force-backtranslate)
        [[ "$FORCE_SCORE" == "1" ]] && cmd+=(--force-score)
        [[ -n "$STOP_AFTER" ]] && cmd+=(--stop-after "$STOP_AFTER")

        echo "=== $pid / $defect $rate / $model"
        if [[ "$DRY_RUN" == "1" ]]; then printf '  '; printf '%q ' "${cmd[@]}"; echo
        else "${cmd[@]}"; fi
        ran=$((ran+1))
      done
    done
  done
done

echo
echo "$ran cell(s) run, $skipped variant(s) missing"
echo "Scores: $OUT_ROOT/<passage>/<model>/<defect>/<rate>/scores_target_llama.json"
