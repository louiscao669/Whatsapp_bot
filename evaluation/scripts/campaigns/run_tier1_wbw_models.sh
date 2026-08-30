#!/usr/bin/env bash
# Answer the Tier-1 BSB google_word_by_word (wbw) condition with the three
# small answer models.
#
# The wbw translation already exists for all 10 passages under the
# qwen317b_think cell. Every model is SEEDED from that one translation rather
# than re-translating: deep_translator would issue live Google requests whose
# per-token fallbacks vary run to run, and a per-model retranslation would put
# translation noise on top of the ability axis this is meant to measure. Same
# principle as the defect grid's single shared base.
#
# wbw is the canary condition (H-T6) and the known-terrible method: on the Luke
# grid it scored worst at 0.543, with the damage concentrated in OPEN questions
# (MCQ lets a respondent reconstruct meaning from the options). Expect a large
# mcq-open gap here; that gap is the wbw signature, not an artifact.
#
# Knobs:
#   MODELS="llama3.2:1b qwen2.5:1.5b qwen3:1.7b"
#   PASSAGES="t1_judg9"        default: all 10
#   SOURCE_CELL=qwen317b_think  where the existing wbw translation lives
#   FORCE_ANSWER=1  DRY_RUN=1
set -euo pipefail

OUT_ROOT="${OUT_ROOT:-evaluation/outputs/tier1_bsb}"
METHOD="google_word_by_word"
SOURCE_CELL="${SOURCE_CELL:-qwen317b_think}"
MODELS="${MODELS:-llama3.2:1b qwen2.5:1.5b qwen3:1.7b}"
MAP="${MAP:-evaluation/datasets/pseudonym_remap/name_map_tier1_reconciled.json}"
WINDOWS="${WINDOWS-QA_algorithm/inputs/tier1_qa_verse_windows.json}"
PASSAGE_DIR="${PASSAGE_DIR:-evaluation/datasets/pseudonymized/passages/tier1_bsb}"
QA_DIR="${QA_DIR:-evaluation/datasets/pseudonymized/qa/tier1_bsb}"
DRY_RUN="${DRY_RUN:-0}"
FORCE_ANSWER="${FORCE_ANSWER:-0}"
NO_THINK="${NO_THINK:-1}"

PIDS="t1_judg9 t1_judg17_18 t1_2kgs6_7 t1_1kgs13 t1_2kgs11 t1_2chr26 t1_2sam21 t1_acts19 t1_acts20 t1_acts23"

passage_file() {
  case "$1" in
    t1_judg9)     echo judg_9_1-57.txt ;;      t1_judg17_18) echo judg_17_1-18_31.txt ;;
    t1_2kgs6_7)   echo 2kgs_6_24-7_20.txt ;;   t1_1kgs13)    echo 1kgs_13_1-34.txt ;;
    t1_2kgs11)    echo 2kgs_11_1-21.txt ;;     t1_2chr26)    echo 2chr_26_1-23.txt ;;
    t1_2sam21)    echo 2sam_21_15-22.txt ;;    t1_acts19)    echo acts_19_11-20.txt ;;
    t1_acts20)    echo acts_20_7-12.txt ;;     t1_acts23)    echo acts_23_12-35.txt ;;
    *) echo "unknown passage id: $1" >&2; return 1 ;;
  esac
}

# Cell-defining inputs. Excludes generated_answers*/scores* so seeding never
# overwrites results already produced.
ARTIFACTS="passage_source_decanonicalized.txt passage_target.txt
           passage_target_decanonicalized.txt passage_translation.json
           qa_target.json qa_target_decanonicalized.json"

say() { echo "[$(date '+%H:%M:%S')] $*"; }

# Preflight. Ollama answering runs BEFORE the first OpenAI call, so an unset or
# placeholder key is not discovered until a full answering pass has been spent.
# Verify the key actually authenticates first.
: "${OPENAI_API_KEY:?export OPENAI_API_KEY (back-translation, judge, MCQ mapping)}"
case "$OPENAI_API_KEY" in
  ""|...|"<your-key>"|"sk-...") echo "OPENAI_API_KEY is a placeholder: '$OPENAI_API_KEY'" >&2; exit 1 ;;
esac
if [ "${SKIP_PREFLIGHT:-0}" != "1" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' https://api.openai.com/v1/models \
         -H "Authorization: Bearer $OPENAI_API_KEY" || echo 000)
  if [ "$code" != "200" ]; then
    echo "OPENAI_API_KEY did not authenticate (HTTP $code). Fix it before running." >&2
    exit 1
  fi
  say "preflight: OpenAI key OK"
fi
ran=0; skipped=0

for pid in $PIDS; do
  [ -n "${PASSAGES:-}" ] && case " $PASSAGES " in *" $pid "*) ;; *) continue ;; esac
  src="$OUT_ROOT/$pid/$SOURCE_CELL/$METHOD"
  if [ ! -s "$src/passage_target_decanonicalized.txt" ]; then
    echo "  skip $pid: no wbw translation at $src" >&2; skipped=$((skipped+1)); continue
  fi
  for model in $MODELS; do
    slug=$(echo "$model" | tr -d ':.')
    dst="$OUT_ROOT/$pid/$slug/$METHOD"
    if [ "$DRY_RUN" != "1" ]; then
      mkdir -p "$dst"
      for f in $ARTIFACTS; do
        [ -f "$src/$f" ] && cp -n "$src/$f" "$dst/$f" 2>/dev/null || true
      done
    fi
    cmd="python -u evaluation/main.py \"$PASSAGE_DIR/$(passage_file "$pid")\" \"$QA_DIR/${pid}_all_formats.json\" \
      --output-dir \"$OUT_ROOT/$pid/$slug\" --run-name \"${pid}_${slug}\" \
      --methods $METHOD --answer-provider ollama --answer-model \"$model\" \
      --mcq-choice-mapper openai --skip-entity-discovery --pre-blinded \
      --pseudonym-map \"$MAP\" --answer-verse-window 2 --temperature 0.0 \
      --allow-partial-answers --continue-on-method-error"
    [ -n "$WINDOWS" ] && cmd="$cmd --answer-verse-windows-json \"$WINDOWS\""
    case "$model" in qwen3*) [ "$NO_THINK" = "1" ] && cmd="$cmd --ollama-no-think" ;; esac
    [ "$FORCE_ANSWER" = "1" ] && cmd="$cmd --force-answer"

    say "=== $pid / $METHOD / $model"
    if [ "$DRY_RUN" = "1" ]; then echo "  $cmd"; else eval "$cmd"; fi
    ran=$((ran+1))
  done
done

say "$ran cell(s) run, $skipped passage(s) missing a wbw translation"
say "scores: $OUT_ROOT/<passage>/<model>/$METHOD/scores_target_llama.json"
