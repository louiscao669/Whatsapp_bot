#!/usr/bin/env bash
# Build the google_word_by_word (wbw) pilot condition for the UNBLINDED 5-option
# tier-1 corpus (evaluation/outputs/tier1_bsb_unblinded_5opt_think).
#
# Why this exists: that corpus was built for the MCQ defect grid and has no wbw
# cell, but the human pilot's Latin square needs one. Everything else the pilot
# needs (clean, omission 15/30, mistranslation 15/30, grammar 30) is already there.
#
# What it does, per passage:
#   1. seeds <pid>/_wbw/_shared/ with the corpus's already-translated QA, so
#      main.py REUSES it -- no OpenAI QA translation, and no second translation
#      that could differ from the one every other condition uses;
#   2. runs main.py for google_word_by_word only, stopping after decanonicalize
#      (live Google requests, so run it on a machine that can reach Google);
#   3. publishes <pid>/_wbw/google_word_by_word -> <pid>/google_word_by_word, the
#      root-level layout human_pilot/pilot_import.py reads;
#   4. overwrites that cell's QA with the clean cell's QA (meta-option E pinned),
#      so the wbw cell carries byte-identical questions.
#
# Run from the repo root:
#   bash evaluation/scripts/campaigns/current/build_unblinded_5opt_wbw.sh
#   PASSAGES="t1_judg9" bash ...     # subset
#   FORCE=1 bash ...                 # rebuild cells that already exist
set -euo pipefail

OUT_ROOT="${OUT_ROOT:-evaluation/outputs/tier1_bsb_unblinded_5opt_think}"
QA_DIR="${QA_DIR:-evaluation/datasets/qa/tier1_gold72_canonical_5opt}"
PASSAGE_DIR="${PASSAGE_DIR:-evaluation/datasets/passages/tier1_bsb}"
MAP="${MAP:-evaluation/datasets/pseudonym_remap/empty_map_unblinded.json}"
METHOD=google_word_by_word
FORCE="${FORCE:-0}"
# Largest share of word tokens allowed to stay English. Only lookups that FAIL stay
# English (proper names are translated too), so a high share means Google refused
# the requests -- rate limiting or a blocked network -- not a property of the text.
MAX_ENGLISH_PCT="${MAX_ENGLISH_PCT:-5}"
# Seconds between live Google requests (see translation_quality.google_word_by_word).
export WBW_REQUEST_GAP="${WBW_REQUEST_GAP:-0.5}"
# On a refusal, back off 5, 10, 20, 40, 80 s before giving up on a word.
export WBW_TOKEN_RETRIES="${WBW_TOKEN_RETRIES:-6}"
export WBW_RETRY_BASE_DELAY="${WBW_RETRY_BASE_DELAY:-5}"
PIDS="${PASSAGES:-t1_judg9 t1_judg17_18 t1_2kgs6_7 t1_1kgs13 t1_2kgs11 t1_2chr26 t1_2sam21 t1_acts19 t1_acts20 t1_acts23}"

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

# main.py insists on OPENAI_API_KEY even though this run makes no OpenAI calls
# (QA translation is reused and the empty name map skips canonicalization).
if [ -z "${OPENAI_API_KEY:-}" ] && [ -f .env ]; then set -a; . ./.env; set +a; fi
: "${OPENAI_API_KEY:?set OPENAI_API_KEY or run from the repo root with .env present}"
# Skip the live-Google check when every word is already in the token cache
# (e.g. filled with fill_wbw_cache.py or the Cloud Translation API): the build
# then makes no requests at all.
missing=$(python3 - <<'PY3'
import glob, json, sys
sys.path.insert(0, "evaluation/scripts/scoring/current")
from translation_quality import is_protected_token
try:
    cache = json.load(open("evaluation/datasets/perturbations/.wbw_cache_en_zh-CN.json", encoding="utf-8"))
except FileNotFoundError:
    cache = {}
keys = {w.lower() for f in glob.glob("evaluation/datasets/passages/tier1_bsb/*.txt")
        for w in open(f, encoding="utf-8").read().split(" ") if w and not is_protected_token(w)}
print(len(keys - set(cache)))
PY3
)
if [ "$missing" = "0" ]; then
  echo "token cache complete -- no Google requests needed"
  export WBW_REQUEST_GAP=0
elif [ "${WBW_SKIP_CHECK:-0}" != "1" ]; then
  echo "$missing word(s) not cached yet; checking Google is reachable"
  python3 - <<'PY3' || { echo "Google is still refusing requests (TooManyRequests). Wait and retry, or switch network." >&2; exit 1; }
from deep_translator import GoogleTranslator
GoogleTranslator(source="en", target="zh-CN").translate("mother")
PY3
fi
[ -d "$OUT_ROOT" ] || { echo "missing $OUT_ROOT" >&2; exit 1; }
python3 -c "import deep_translator" 2>/dev/null \
  || { echo "deep_translator is not installed: pip install deep-translator" >&2; exit 1; }

built=0
for pid in $PIDS; do
  cell="$OUT_ROOT/$pid/$METHOD"
  clean="$OUT_ROOT/$pid/omission/0%"
  if [ -s "$cell/passage_target_decanonicalized.txt" ] && [ "$FORCE" != "1" ]; then
    echo "== $pid: reuse $cell"
    continue
  fi
  [ -s "$clean/qa_target_decanonicalized.json" ] || { echo "missing $clean" >&2; exit 1; }
  echo "== $pid"
  work="$OUT_ROOT/$pid/_wbw"
  mkdir -p "$work/_shared"
  cp "$OUT_ROOT/$pid/_base/_shared/${pid}_base_qa_zh.json" "$work/_shared/"
  cp "$OUT_ROOT/$pid/_base/_shared/${pid}_base_qa_zh_decanonicalized.json" "$work/_shared/"

  # Never let main.py "reuse" a translation left by an earlier failed attempt.
  rm -rf "$work/$METHOD"

  python3 -u evaluation/main.py \
    "$PASSAGE_DIR/$(passage_file "$pid")" "$QA_DIR/${pid}_all_formats.json" \
    --output-dir "$work" --run-name "${pid}_base" \
    --methods "$METHOD" --stop-after decanonicalize \
    --skip-entity-discovery --pre-blinded --pseudonym-map "$MAP" \
    --temperature 0.0

  src="$work/$METHOD"
  [ -s "$src/passage_target_decanonicalized.txt" ] \
    || { echo "no wbw passage produced for $pid" >&2; exit 1; }
  pct=$(python3 - "$src/passage_target_decanonicalized.txt" <<'PY2'
import re, sys
words = [w for w in open(sys.argv[1], encoding="utf-8").read().split() if not w.isdigit()]
eng = sum(1 for w in words if re.search(r"[A-Za-z]{2,}", w))
print(round(100 * eng / max(len(words), 1), 1))
PY2
)
  echo "  English tokens left in $pid: ${pct}%"
  if python3 -c "import sys; sys.exit(0 if float('$pct') <= float('$MAX_ENGLISH_PCT') else 1)"; then :; else
    rm -rf "$src"
    echo "FATAL: $pid is ${pct}% untranslated (limit ${MAX_ENGLISH_PCT}%). Google is refusing" >&2
    echo "  requests. Not published. Wait a while (or switch network) and re-run." >&2
    exit 1
  fi
  rm -rf "$cell"
  cp -R "$src" "$cell"
  cp "$clean/qa_target_decanonicalized.json" "$cell/qa_target_decanonicalized.json"
  cp "$clean/qa_target.json" "$cell/qa_target.json"
  built=$((built + 1))
done

echo
echo "built $built wbw cell(s). Check:"
for pid in $PIDS; do
  f="$OUT_ROOT/$pid/$METHOD/passage_target_decanonicalized.txt"
  if [ -s "$f" ]; then echo "  ok      $pid  ($(wc -c < "$f" | tr -d ' ') bytes)"; else echo "  MISSING $pid"; fi
done
