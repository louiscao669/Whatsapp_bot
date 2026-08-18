#!/usr/bin/env bash
# Multi-model answering runs on the existing synthetic defect grid.
# Purpose (2026-07-10 plan): lower the tau=0 noise floor, test lambda's
# ability-dependence on the defect axis (complements V4), fill grid gaps
# (untranslated never answered; local_inconsistency dose levels).
#
# What it does, per answer model x defect x dose level x chapter:
#   1. copies the 1.7b variant artifacts (passage + decanonicalized QA) into
#      a parallel tier dir  evaluation/outputs/luke{ch}/<TIER>/<defect>/<level>/
#      (never touches the 1.7b originals; skips if already copied)
#   2. runs evaluation/scripts/scoring/answer_score_subset_in_place.py to answer all
#      questions with the local Ollama model and score them (OpenAI judge).
#
# REQUIREMENTS (run on your machine, from the repo root):
#   - Ollama running:  ollama pull llama3.2:1b qwen2.5:1.5b
#   - OPENAI_API_KEY exported (back-translation + LLM judge + embeddings)
#
# USAGE:
#   bash evaluation/scripts/campaigns/run_variants_multimodel.sh              # both models, all defects
#   MODELS="1.5b" bash evaluation/scripts/campaigns/run_variants_multimodel.sh
#   DEFECTS="untranslated local_inconsistency" bash evaluation/scripts/campaigns/run_variants_multimodel.sh
#   CHAPTERS="1 2" DRY_RUN=1 bash ...                               # preview commands
#
# Also fills the 1.7b untranslated gap: include TIER "1.7b" in MODELS via
#   MODELS="1.7b" DEFECTS="untranslated" bash ...   (answers in place — the
#   untranslated levels have no scores yet, so nothing is overwritten).

set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

MODELS="${MODELS:-llama1b qwen1.5b}"          # tier aliases (see case below)
DEFECTS="${DEFECTS:-omission mistranslation grammar awkward addition inconsistency local_inconsistency untranslated}"
CHAPTERS="${CHAPTERS:-1 2 3 4 5 6 7 8}"
# question count is computed per chapter (all available records)
VERSE_WINDOW="${VERSE_WINDOW:-2}"
DRY_RUN="${DRY_RUN:-0}"

# --- small-tier (1b / 1.5b) scoping (2026-07-20) ---
# For the smaller answer models we deliberately do NOT run these defects:
#   - untranslated: never answered even at 1.7b (no scores to compare against)
#   - inconsistency: flat / non-responsive proxy signal, not worth the compute
# And for local_inconsistency we answer ONLY the style_* sub-family (plus the
# 0% clean baseline as the dose anchor); the name_* sub-family is skipped.
# These restrictions apply only to non-1.7b tiers — a MODELS="1.7b" gap-fill
# run is unaffected.
SKIP_DEFECTS_SMALL="${SKIP_DEFECTS_SMALL:-untranslated inconsistency}"
LOCAL_INCON_SUBFAMILY_SMALL="${LOCAL_INCON_SUBFAMILY_SMALL:-style}"  # keep style_* (+ 0%)

# Weak small models (1b/1.5b) frequently emit MCQ answers the RULE parser can't
# map to A/B/C/D (non-empty but garbled) -> the cell hard-aborts with
# "MCQ answer must be A, B, C, or D." Use the OpenAI choice mapper (gpt-4.1-mini)
# to map the model's OWN answer text to the closest choice. It fires only when
# the rules parser fails, so parseable answers are untouched. Needs
# OPENAI_API_KEY (already required for back-translation + judge). Full tier
# (1.7b) keeps "rules" — its grid was built that way and it rarely fails.
MCQ_CHOICE_MAPPER_SMALL="${MCQ_CHOICE_MAPPER_SMALL:-openai}"

run() { if [ "$DRY_RUN" = "1" ]; then echo "+ $*"; else echo "+ $*"; "$@"; fi; }

# Whether a given dose-level dir should be run for this defect/tier.
# Returns 0 (include) / 1 (skip). Full-tier (1.7b) always includes everything.
level_included() {
  local defect="$1" tier="$2" lev="$3"
  if [ "$tier" != "1.7b" ] && [ "$defect" = "local_inconsistency" ]; then
    case "$lev" in
      "${LOCAL_INCON_SUBFAMILY_SMALL}"_*|"0%") return 0 ;;
      *) return 1 ;;
    esac
  fi
  return 0
}

for M in $MODELS; do
  case "$M" in
    llama1b)  TIER="llama 1b"; OLLAMA_MODEL="llama3.2:1b";  EXTRA="" ;;
    qwen1.5b) TIER="1.5b";     OLLAMA_MODEL="qwen2.5:1.5b"; EXTRA="" ;;
    qwen1.7b|1.7b) TIER="1.7b"; OLLAMA_MODEL="qwen3:1.7b";  EXTRA="--ollama-no-think" ;;
    *) echo "unknown model alias: $M" >&2; exit 1 ;;
  esac

  for DEFECT in $DEFECTS; do
    # small-tier defect skip (untranslated / inconsistency); full tier unaffected
    if [ "$TIER" != "1.7b" ]; then
      case " $SKIP_DEFECTS_SMALL " in
        *" $DEFECT "*) echo "[skip] $DEFECT not run for tier '$TIER'"; continue ;;
      esac
    fi
    for CH in $CHAPTERS; do
      SRC="evaluation/outputs/luke${CH}/1.7b/${DEFECT}"
      DST="evaluation/outputs/luke${CH}/${TIER}/${DEFECT}"
      [ -d "$SRC" ] || { echo "[skip] $SRC missing"; continue; }
      # ---- stage 1: copy artifacts into the tier dir (inputs only) ----
      if [ "$TIER" != "1.7b" ]; then
        for LEVDIR in "$SRC"/*/; do
          LEV="$(basename "$LEVDIR")"
          [ "$LEV" = "_shared" ] && continue
          level_included "$DEFECT" "$TIER" "$LEV" || continue
          mkdir -p "$DST/$LEV"
          for F in passage_target.txt passage_target_decanonicalized.txt \
                   passage_source_decanonicalized.txt qa_target.json \
                   qa_target_decanonicalized.json decanonicalized_metadata.json \
                   passage_translation.json; do
            [ -f "$LEVDIR/$F" ] && [ ! -f "$DST/$LEV/$F" ] && cp "$LEVDIR/$F" "$DST/$LEV/$F"
          done
        done
      fi
    done

    # ---- stage 2: answer + score, PER CHAPTER (question counts and level
    # availability vary by chapter: e.g. luke3 has only 7 QA records, and
    # untranslated variants exist only for some chapters) ----
    for CH in $CHAPTERS; do
      SRCD="evaluation/outputs/luke${CH}/1.7b/${DEFECT}"
      # levels present IN THIS CHAPTER (need the passage file to answer)
      LEVELS=""
      for LEVDIR in "$SRCD"/*%/; do
        [ -d "$LEVDIR" ] || continue
        [ -f "$LEVDIR/passage_target_decanonicalized.txt" ] || continue
        LEV="$(basename "$LEVDIR")"
        level_included "$DEFECT" "$TIER" "$LEV" || continue
        LEVELS="$LEVELS $LEV"
      done
      [ -z "$LEVELS" ] && { echo "[skip] luke${CH}/${DEFECT}: no usable levels"; continue; }
      # all available questions for this chapter (runner errors if N > avail)
      N=$(python3 -c "
import json
d = json.load(open('evaluation/datasets/qa/qa_output_luke_ch${CH}_all_formats.json'))
recs = d if isinstance(d, list) else d.get('items', d.get('questions', []))
print(len(recs))")
      # weak small models: rescue unparseable MCQ answers via OpenAI mapper
      MAPPER="rules"; [ "$TIER" != "1.7b" ] && MAPPER="$MCQ_CHOICE_MAPPER_SMALL"
      echo "== [$M / $TIER] luke${CH} $DEFECT (N=$N, mcq-mapper=$MAPPER):$LEVELS"
      # shellcheck disable=SC2086
      run python3 evaluation/scripts/scoring/answer_score_subset_in_place.py "$N" \
          --chapters "$CH" \
          --allow-fewer \
          --artifact-root-template "evaluation/outputs/luke{chapter}/${TIER}/${DEFECT}" \
          --methods $LEVELS \
          --answer-provider ollama \
          --answer-model "$OLLAMA_MODEL" $EXTRA \
          --answer-verse-window "$VERSE_WINDOW" \
          --mcq-choice-mapper "$MAPPER" \
          --summary-json "evaluation/outputs/reports/variant_runs_${M}_${DEFECT}_luke${CH}.json"
    done
  done
done
echo "DONE. Then re-fit slopes per model:"
echo "  python3 scripts/fit_item_sensitivity.py --axis defect   (per tier; add lambda_g(model) equality test)"
