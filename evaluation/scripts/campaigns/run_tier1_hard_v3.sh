#!/usr/bin/env bash
# End-to-end tier1_hard_v3 run: QA translation -> verify -> refresh -> answer.
#
# The verify gate is the point. Step 2 has silently left stale QA in the base
# cell before (main.py's shared->method copy is gated on --force, not
# --force-translate, so an existing qa_target.json wins). Answering against
# that produces a full grid scored on questions the QA set no longer contains,
# and nothing downstream notices. So the answer phase runs only if every
# passage has 2x its item count in rows and every item id is present.
#
# Usage:
#   bash evaluation/scripts/campaigns/run_tier1_hard_v3.sh
#   DEFECTS="mistranslation grammar" bash .../run_tier1_hard_v3.sh
#   SKIP_TRANSLATE=1 bash .../run_tier1_hard_v3.sh    # QA already verified
set -euo pipefail

SRC="${SRC:-evaluation/outputs/tier1_bsb}"
DST="${DST:-evaluation/outputs/tier1_hard_v3}"
QA_DIR="${QA_DIR:-evaluation/datasets/pseudonymized/qa/tier1_hard_v3}"
PDIR="${PDIR:-evaluation/datasets/pseudonymized/passages/tier1_bsb}"
MAP="${MAP:-evaluation/datasets/pseudonym_remap/name_map_tier1_reconciled.json}"
DEFECTS="${DEFECTS:-mistranslation grammar omission}"
RATES="${RATES:-0% 5% 10% 15% 20% 30%}"
MODELS="${MODELS:-llama3.2:1b qwen2.5:1.5b qwen3:1.7b}"
SKIP_TRANSLATE="${SKIP_TRANSLATE:-0}"

PIDS=(t1_judg9 t1_judg17_18 t1_2kgs6_7 t1_1kgs13 t1_2kgs11
      t1_2chr26 t1_2sam21 t1_acts19 t1_acts20 t1_acts23)

# macOS ships bash 3.2, which has no associative arrays: `declare -A m=([k]=v)`
# is parsed as an indexed array with an arithmetic subscript, so the key is
# evaluated as a variable name and `set -u` aborts the script. A case function
# is portable to both.
passage_file() {
  case "$1" in
    t1_judg9)      echo judg_9_1-57.txt ;;
    t1_judg17_18)  echo judg_17_1-18_31.txt ;;
    t1_2kgs6_7)    echo 2kgs_6_24-7_20.txt ;;
    t1_1kgs13)     echo 1kgs_13_1-34.txt ;;
    t1_2kgs11)     echo 2kgs_11_1-21.txt ;;
    t1_2chr26)     echo 2chr_26_1-23.txt ;;
    t1_2sam21)     echo 2sam_21_15-22.txt ;;
    t1_acts19)     echo acts_19_11-20.txt ;;
    t1_acts20)     echo acts_20_7-12.txt ;;
    t1_acts23)     echo acts_23_12-35.txt ;;
    *)             echo "unknown passage id: $1" >&2; return 1 ;;
  esac
}

say() { echo "[$(date '+%H:%M:%S')] $*"; }

say "=== 0/5  clone missing defect families + clear stale model cells"
for p in "${PIDS[@]}"; do
  mkdir -p "$DST/$p"
  for d in $DEFECTS; do
    [[ -d "$DST/$p/$d" ]] || { say "  clone $p/$d"; cp -a "$SRC/$p/$d" "$DST/$p/"; }
  done
  # Model cells are seeded with cp -n, so a cell created before the QA was
  # fixed would keep its stale inputs. Drop any that carry no scores.
  # Match answer-model slugs only (llama321b, qwen2515b, qwen317b, *_think).
  # Everything else under a passage is _base or a defect family.
  for cell in "$DST/$p"/*/; do
    name="$(basename "$cell")"
    if [[ "$name" != llama* && "$name" != qwen* ]]; then
      continue
    fi
    if [ -z "$(find "$cell" -name 'scores_target_llama.json' 2>/dev/null | head -1)" ]; then
      say "  drop unanswered model cell $p/$name"
      rm -rf "$cell"
    fi
  done
done

if [[ "$SKIP_TRANSLATE" != "1" ]]; then
  say "=== 1/5  QA translation into each base (passage translation reused)"
  : "${OPENAI_API_KEY:?export OPENAI_API_KEY}"
  for p in "${PIDS[@]}"; do
    # Deleting is what actually forces a rebuild; the force flags do not reach
    # the shared->method copy.
    rm -f "$DST/$p/_base/llm_prompt_high/qa_target"*.json
    rm -f "$DST/$p/_base/_shared/"*_qa_zh*.json
    say "  $p"
    python -u evaluation/main.py "$PDIR/$(passage_file "$p")" "$QA_DIR/${p}_all_formats.json" \
      --output-dir "$DST/$p/_base" --run-name "${p}_base" \
      --methods llm_prompt_high --stop-after decanonicalize \
      --skip-entity-discovery --pre-blinded --pseudonym-map "$MAP" \
      --temperature 0.0
  done
fi

say "=== 2/5  verify every base carries the new QA"
python3 - "$QA_DIR" "$DST" <<'PY'
import json, os, sys
qa_dir, out = sys.argv[1], sys.argv[2]
bad = 0
for name in sorted(os.listdir(qa_dir)):
    if not name.endswith("_all_formats.json"):
        continue
    pid = name[:-len("_all_formats.json")]
    src = json.load(open(os.path.join(qa_dir, name), encoding="utf-8"))
    path = os.path.join(out, pid, "_base", "llm_prompt_high", "qa_target.json")
    rows = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    have = {str(r.get("passage_id", "")).split(":")[1].rsplit("-", 1)[0]
            for r in rows if ":" in str(r.get("passage_id", ""))}
    miss = [i["id"] for i in src if i["id"] not in have]
    ok = len(rows) == 2 * len(src) and not miss
    bad += not ok
    print(f"  {pid:14s} {len(rows):3d}/{2*len(src):3d} rows  "
          + ("OK" if ok else f"BAD ({len(miss)} items missing)"))
if bad:
    sys.exit(f"{bad} passage(s) bad - refusing to start the answer phase")
print("  all passages carry the new QA")
PY

say "=== 3/5  push QA into the nonzero variants"
python evaluation/scripts/data_prep/refresh_tier1_defect_variant_qa.py \
  --root "$DST" --defects $DEFECTS --apply

say "=== 4/5  seed the 0% cells (refresh skips them by design)"
for p in "${PIDS[@]}"; do
  for d in $DEFECTS; do
    cp "$DST/$p/_base/llm_prompt_high/qa_target.json" "$DST/$p/$d/0%/qa_target.json"
    cp "$DST/$p/_base/llm_prompt_high/qa_target_decanonicalized.json" \
       "$DST/$p/$d/0%/qa_target_decanonicalized.json"
  done
done

say "=== 5/5  answer + score"
OUT_ROOT="$DST" QA_DIR="$QA_DIR" PASSAGE_DIR="$PDIR" \
DEFECTS="$DEFECTS" RATES="$RATES" WINDOWS="" MODELS="$MODELS" \
REPLACE_INPUTS=1 \
bash evaluation/scripts/campaigns/run_tier1_defect_models.sh

say "done. scores: $DST/<passage>/<model>/<defect>/<rate>/scores_target_llama.json"
