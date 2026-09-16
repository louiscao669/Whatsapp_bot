#!/usr/bin/env bash
# Answer the 0% (undamaged) cells that the grid run skipped.
#
# WHY THIS EXISTS. run_tier1_defect_models.sh with DISCOVER_LEVELS=1 globs
# `! -name '0%'` -- its own doc says "every generated NONZERO level" -- so the
# 2026-09-15 grid answered all six families at 30% and produced no baseline at all.
# 80 cells, 568 observations, nothing to compare them against: no dose effect, no
# paired dz, nothing conditioned on correct-at-0%. The 5/5 verify counted cells and
# checked window binding, both of which passed, so the run reported success.
#
# Re-running the wrapper will not fix it. Discovery has to be OFF and the rate named.
#
# ONE FAMILY IS ENOUGH. At 0% every family is the same undamaged base translation --
# verified identical, passage md5 1532f141c9 and the same QA md5 across all six on
# t1_judg9. Answering six copies of the same 71 items costs 1.5 h to learn nothing.
# Set DEFECTS to all six only if your analysis insists on a per-family 0% cell.
set -uo pipefail

MODEL="${MODEL:-qwen3:1.7b}"
DEFECTS="${DEFECTS:-omission}"
PASSAGES="${PASSAGES:-}"
OUT_ROOT="${OUT_ROOT:-evaluation/outputs/tier1_bsb_unblinded_5opt_think}"
BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

# Mirrors run_gold72_canonical_5opt_think.sh. The inner script defaults to
# OUT_ROOT=evaluation/outputs/tier1 and all three answer models, so every one of
# these must be passed explicitly or the baseline lands in the wrong tree.
export MCQ_CHOICE_LABELS=ABCDE          # five options, one meta-option on E
export QA_FORMATS=mcq
export NO_THINK=0                       # thinking ON, matching the 30% arm
export METHOD=llm_prompt_high
export QA_DIR=evaluation/datasets/qa/tier1_gold72_canonical_5opt
export PASSAGE_DIR=evaluation/datasets/passages/tier1_bsb
export MAP=evaluation/datasets/pseudonym_remap/empty_map_unblinded.json
export WINDOWS=QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json
export OUT_ROOT MODELS="$MODEL" DEFECTS RATES="0%"
export DISCOVER_LEVELS=0 FORCE_ANSWER=1
[ -n "$PASSAGES" ] && export PASSAGES

say() { echo; echo "======== [$(date '+%H:%M:%S')] $*"; }

say "preflight"
curl -sf --max-time 10 "$BASE_URL/api/tags" -o /tmp/_tags.json \
  || { echo "FATAL: ollama unreachable at $BASE_URL" >&2; exit 2; }
grep -q "\"${MODEL%%:*}" /tmp/_tags.json \
  || { echo "FATAL: $MODEL not pulled" >&2; exit 2; }
[ -d "$OUT_ROOT" ] || { echo "FATAL: no run root at $OUT_ROOT" >&2; exit 2; }
n30=$(find -L "$OUT_ROOT" -name generated_answers_target_llama.json \
        ! -path "*/0%/*" | wc -l | tr -d ' ')
[ "$n30" -gt 0 ] || { echo "FATAL: no damaged cells in $OUT_ROOT -- wrong root?" >&2; exit 2; }
echo "  root      $OUT_ROOT  ($n30 damaged cells already answered)"
echo "  answering $DEFECTS at 0%, model=$MODEL, options=$MCQ_CHOICE_LABELS, thinking=on"
for d in $DEFECTS; do
  echo "  staged 0% cells for $d: $(ls -d "$OUT_ROOT"/t1_*/"$d"/0% 2>/dev/null | wc -l | tr -d ' ')/10"
done

say "answering 0%"
bash evaluation/scripts/campaigns/current/run_tier1_defect_models.sh
status=$?

say "verify -- the check the grid run did NOT do"
python3 - "$OUT_ROOT" "$DEFECTS" <<'PY'
import glob, json, os, sys
from collections import Counter
root, defects = sys.argv[1], sys.argv[2].split()
missing, rows = [], []
for d in defects:
    cells = sorted(glob.glob(f"{root}/t1_*/*/{d}/0%/generated_answers_target_llama.json"))
    pids = {c.split("/")[-5] for c in cells}
    staged = {p.split("/")[-3] for p in glob.glob(f"{root}/t1_*/{d}/0%")}
    for p in sorted(staged - pids):
        missing.append(f"{p}/{d}")
    for c in cells:
        rows += json.load(open(c, encoding="utf-8"))
print(f"  0% cells answered : {len(rows)} observation(s)")
if missing:
    print(f"  !! {len(missing)} passage(s) still have NO 0% answers: {missing[:6]}")
    raise SystemExit("FATAL: baseline incomplete")
if not rows:
    raise SystemExit("FATAL: no 0% observations -- DISCOVER_LEVELS still filtering?")
ok = sum(1 for r in rows if r.get("direct_correct") in (1, True))
sel = Counter(str(r.get("selected_choice", "")).strip().upper() for r in rows)
meta = sel.get("E", 0)
print(f"  baseline accuracy : {ok}/{len(rows)} = {ok/len(rows):.1%}")
print(f"  letter spread     : {dict(sorted(sel.items()))}")
print(f"  E (meta-option)   : {meta} = {meta/len(rows):.1%}   <-- on UNDAMAGED text")
print()
print("  Read E first. It is the false-alarm rate of the single hatch on clean text,")
print("  and it is what the five-option collapse has to be judged on. If it is high")
print("  here, the 30% firing rates mean less than they appear to.")
PY
v=$?
say "finished (answer status $status, verify $v)"
exit $(( status || v ))
