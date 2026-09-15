#!/usr/bin/env bash
# Validate the ONE collapsed meta-option before committing it to a full grid.
#
# 2026-09-14 replaced the two meta-options with a single hatch:
#     E  经文不支持以上任何一个选项      the passage supports none of A-D
# (EXPERIMENT_META_OPTION_COLLAPSE_2026-09-14.md). That decision rests on a negative
# result -- two hatches track which LETTER a role sits on, not what the label says --
# and NOT on a single generation using the new string. This measures it.
#
# NO DATASET IS BUILT OR REBUILT HERE. The probe appends the meta-option at run time
# from META_LABELS, so the 5-option format is produced on the fly against the existing
# run root. Pinning the new string into a QA dataset is a step of the FULL grid run,
# not of this validation -- and it must happen in a FRESH output root, because
# pin_meta_options.py refuses a root whose cells already hold answers (retro-pinning
# would make qa_target.json misrepresent what earlier models were shown).
#
# A 2x2, NOT a two-arm comparison. The collapsed design changes TWO things at once,
# and they are separate knobs in separate code paths:
#
#     LABEL        the pinned option text  -- 根据这段文字无法判断 (a claim about the
#                  READER, true whenever the answer is merely unlisted) vs
#                  经文不支持以上任何一个选项 (a claim about the EVIDENCE)
#     INSTRUCTION  _meta_hint() -- "if the passage does not give enough information to
#                  answer" vs "if the passage supports none of A-D"
#
# Moving both and reporting one number would repeat the 2026-09-13 mistake: the label
# rewrite was predicted to carry that experiment and in fact did nothing, while the
# untested variable (which letter a role sat on) carried all of it. So both are varied
# independently. The off-diagonal cells are the whole point of the design.
#
# It also decides how much work adoption costs. The instruction is free to change. The
# label is a pinned string, so changing it means translating and pinning a FRESH output
# root. If the instruction alone carries the effect, that work disappears.
#
# Every cell is FIVE-option with one hatch, so chance is 1/5 throughout and option count
# is never a variable. The SIX-option arms differ in both count and chance, so they
# appear in the per-arm table for orientation only, never as a contrast.
#
# BOTH MECHANISMS, as always:
#   corrupt  the passage answers with something unlisted -> the hatch is correct
#   redact   the keyed verse is gone, the passage is silent -> the hatch is correct
# One hatch is correct in both, which is the entire point of collapsing them. The
# question is whether it is CHOSEN in both, and whether it stays quiet on clean text.
#
#   SAMPLE=16 bash evaluation/scripts/campaigns/current/run_unified_option_validation.sh
#                           # SCREEN first: the full 2x2 on 16 items spread across all ten
#                           # passages, ~55 min. Read it, then decide whether to spend 3.5 h.
#   nohup caffeinate -is bash evaluation/scripts/campaigns/current/run_unified_option_validation.sh &
#                           # the full run, all items
#   ARMS="9 10" bash ...    # add the dose arms (+~1 h)
#   LIMIT=8 bash ...        # plumbing rehearsal ONLY -- truncates to one passage.
#
# Deliberately NOT `set -e`: one failing arm must not take the others with it.
set -uo pipefail

MODEL="${MODEL:-qwen3:1.7b}"
LABELS="${LABELS:-ABCDE}"          # FIVE options: A-D plus the one hatch on E
ABSTAIN="${ABSTAIN:-E}"
LIMIT="${LIMIT:-0}"
# SAMPLE=N runs the same 2x2 on N items drawn evenly across the ten passages, which is
# the SCREENING configuration: SAMPLE=16 is ~55 min instead of ~3.5 h. It is a real
# sample -- unlike LIMIT, which truncates to the first N items and hands you one passage.
# Every cell gets the same items (same seed), so the contrasts stay paired.
# What it can and cannot see: at n=16 paired, a 40-point shift gives ~6-7 discordant
# pairs and McNemar p ~ 0.02; a 20-point shift gives ~3 and p = 0.25. So it screens for
# the LARGE effects this decision turns on -- does the hatch get chosen when it should,
# does it stay quiet on clean text -- and resolves nothing smaller. A null here is "no
# large effect", never "no effect".
SAMPLE="${SAMPLE:-0}"
SAMPLE_SEED="${SAMPLE_SEED:-0}"
# Default is the full 2x2 on both mechanisms (~3.5 h). ARMS="1 2 5 6" runs only the
# diagonal -- legacy-both vs unified-both, ~1.75 h -- which answers "does it work" but
# not "which half did it".
ARMS="${ARMS:-1 2 3 4 5 6 7 8}"
DOSES="${DOSES:-0% 30%}"
RUN_ROOT="${RUN_ROOT:-evaluation/outputs/tier1_bsb_unblinded_5opt}"
BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
PROBE=evaluation/scripts/mcq/diagnostics/abstention_thinking_probe.py
SCORE=evaluation/scripts/analysis/current/score_meta_arms.py

# Six-option arms, for the per-arm table only. Different chance, NOT a contrast.
REF_CORRUPT="${REF_CORRUPT:-evaluation/outputs/reports/f_wording_full/disjoint.json}"
REF_REDACT="${REF_REDACT:-evaluation/outputs/reports/abstention_overnight_20260913_015756/arm2_redact_think_on.json}"

TS="$(date +%Y%m%d_%H%M%S)"
OUT="evaluation/outputs/reports/unified_option_validation_${TS}"
mkdir -p "$OUT"
LOG="$OUT/run.log"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "preflight  model=$MODEL arms=$ARMS limit=$LIMIT sample=$SAMPLE options=$LABELS hatch=$ABSTAIN (nota OFF)"
curl -sf --max-time 10 "$BASE_URL/api/tags" -o "$OUT/ollama_tags.json" \
  || { log "FATAL: ollama unreachable at $BASE_URL"; exit 2; }
grep -q "\"${MODEL%%:*}" "$OUT/ollama_tags.json" \
  || { log "FATAL: $MODEL not pulled. run: ollama pull $MODEL"; exit 2; }
[ -d "$RUN_ROOT" ] || { log "FATAL: no run root at $RUN_ROOT"; exit 2; }
python3 "$PROBE" --self-test >>"$LOG" 2>&1 || { log "FATAL: probe self-tests failed"; exit 2; }
python3 "$SCORE" --self-test >>"$LOG" 2>&1 || { log "FATAL: scorer self-tests failed"; exit 2; }

# Show the exact prompt once. The string under test is the whole experiment; if it is
# wrong, that is visible here rather than four hours from now.
python3 - "$RUN_ROOT" "$SAMPLE" "$SAMPLE_SEED" <<'PY' | tee -a "$LOG"
import sys
from collections import Counter
sys.path.insert(0, "."); sys.path.insert(0, "evaluation/scripts/mcq/diagnostics")
from abstention_thinking_probe import (load_items, load_corrupt_items, load_dose_items,
                                       add_meta_options, build_prompt, stratified_sample,
                                       DEFAULT_WINDOWS)
root, sample, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
r, _ = load_items(root, DEFAULT_WINDOWS, 0)
c, _ = load_corrupt_items(root, DEFAULT_WINDOWS,
                          "evaluation/datasets/mcq/corrupted_windows.json", 0)
if sample:
    rs, cs = stratified_sample(r, sample, seed), stratified_sample(c, sample, seed)
    print(f"  SCREENING on a stratified sample, seed {seed}")
    print(f"  redact  {len(rs)} of {len(r)} across "
          f"{len(set(x['pid'] for x in rs))} passage(s): "
          f"{dict(Counter(x['pid'].replace('t1_', '') for x in rs))}")
    print(f"  corrupt {len(cs)} of {len(c)} across "
          f"{len(set(x['pid'] for x in cs))} passage(s)")
    r, c = rs, cs
else:
    print(f"  redact {len(r)} x2, corrupt {len(c)} x2   (FULL run)")
for d in ("omission", "mistranslation"):
    items, _ = load_dose_items(root, DEFAULT_WINDOWS, ["0%", "30%"], 0, d)
    print(f"  dose {d:15} {len(items)} items available")
n = 4 * (2 * len(r) + 2 * len(c))
print(f"  arms 1-8 (the 2x2): {n} generations, ~{n*13/60:.0f} min at 13 s/call")
ch = add_meta_options({"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                      "ABCDE", "E", "", "unified")
print("\n  --- the option and instruction under test ---")
for line in build_prompt({"Q": "谁？", "choices": ch}, "11 经文", "ABCDE", "E", "",
                         meta_wording="unified").splitlines():
    if line.startswith("E.") or line.startswith("必须从"):
        print("  " + line)
if not r or not c:
    raise SystemExit("FATAL: an arm loaded 0 items")
PY
[ "${PIPESTATUS[0]}" = "0" ] || { log "FATAL: preflight item load failed"; exit 2; }
log "outputs -> $OUT"

status=0
arm() {   # arm <n> <label> <outfile> <labelset> <wording> <extra...>
  local n="$1" label="$2" out="$3" mlab="$4" mword="$5"; shift 5
  case " $ARMS " in *" $n "*) ;; *) log "skip arm $n ($label)"; return 0 ;; esac
  log "=== arm $n: $label ==="
  if python3 "$PROBE" --run-root "$RUN_ROOT" --model "$MODEL" --limit "$LIMIT" \
       --sample "$SAMPLE" --sample-seed "$SAMPLE_SEED" \
       --labels "$LABELS" --abstain "$ABSTAIN" --nota "" \
       --meta-labels "$mlab" --meta-wording "$mword" \
       --out "$out" "$@" >>"$LOG" 2>&1; then
    log "arm $n done -> $out"
  else
    log "arm $n FAILED (continuing)"; status=1
  fi
}

#                       label      instruction
C_LL="$OUT/arm1_corrupt_labelLEG_instrLEG.json"     # legacy    legacy      (baseline)
C_UU="$OUT/arm2_corrupt_labelUNI_instrUNI.json"     # unified   unified     (candidate)
C_UL="$OUT/arm3_corrupt_labelUNI_instrLEG.json"     # unified   legacy      (label alone)
C_LU="$OUT/arm4_corrupt_labelLEG_instrUNI.json"     # legacy    unified     (instr alone)
R_LL="$OUT/arm5_redact_labelLEG_instrLEG.json"
R_UU="$OUT/arm6_redact_labelUNI_instrUNI.json"
R_UL="$OUT/arm7_redact_labelUNI_instrLEG.json"
R_LU="$OUT/arm8_redact_labelLEG_instrUNI.json"
D_OM="$OUT/arm9_dose_omission_unified5.json"
D_MT="$OUT/arm10_dose_mistrans_unified5.json"

arm 1 "corrupt  label=legacy  instr=legacy   (baseline)"  "$C_LL" current current --mode corrupt
arm 2 "corrupt  label=unified instr=unified  (candidate)" "$C_UU" unified unified --mode corrupt
arm 3 "corrupt  label=unified instr=legacy   (label only)" "$C_UL" unified current --mode corrupt
arm 4 "corrupt  label=legacy  instr=unified  (instr only)" "$C_LU" current unified --mode corrupt
arm 5 "redact   label=legacy  instr=legacy   (baseline)"  "$R_LL" current current --mode redact
arm 6 "redact   label=unified instr=unified  (candidate)" "$R_UU" unified unified --mode redact
arm 7 "redact   label=unified instr=legacy   (label only)" "$R_UL" unified current --mode redact
arm 8 "redact   label=legacy  instr=unified  (instr only)" "$R_LU" current unified --mode redact
arm 9  "dose omission, 5-opt UNIFIED"       "$D_OM" unified unified --mode dose --defect omission --doses $DOSES
arm 10 "dose mistranslation, 5-opt UNIFIED" "$D_MT" unified unified --mode dose --defect mistranslation --doses $DOSES

REPORT="$OUT/comparison.txt"
pair() { [ -f "$2" ] && [ -f "$3" ] || { echo; echo "--- $1 --- SKIPPED"; return; }
         echo; echo "--- $1 ---"; python3 "$SCORE" --contrast "$2" "$3"; }
{
  echo "############ five-option arms (chance 1/5, one hatch) ############"
  for f in "$C_LL" "$C_UU" "$C_UL" "$C_LU" "$R_LL" "$R_UU" "$R_UL" "$R_LU" \
           "$D_OM" "$D_MT"; do
    [ -f "$f" ] && python3 "$SCORE" "$f"
  done
  echo
  echo "############ six-option reference (chance 1/6, TWO hatches) ############"
  echo "#  For orientation only. Option count and chance both differ, so these are"
  echo "#  NOT contrasted against the arms above."
  for f in "$REF_CORRUPT" "$REF_REDACT"; do [ -f "$f" ] && python3 "$SCORE" "$f"; done
  echo
  echo "############ the 2x2: which half of the change did the work ############"
  echo "#  Read the two single-variable rows FIRST. If either matches the candidate,"
  echo "#  the other half is doing nothing and should not be adopted."
  echo; echo "===== MISTRANSLATION mechanism (corrupt) ====="
  pair "both changed      (baseline -> candidate)" "$C_LL" "$C_UU"
  pair "LABEL alone       (baseline -> label only)" "$C_LL" "$C_UL"
  pair "INSTRUCTION alone (baseline -> instr only)" "$C_LL" "$C_LU"
  echo; echo "===== OMISSION mechanism (redact) ====="
  pair "both changed      (baseline -> candidate)" "$R_LL" "$R_UU"
  pair "LABEL alone       (baseline -> label only)" "$R_LL" "$R_UL"
  pair "INSTRUCTION alone (baseline -> instr only)" "$R_LL" "$R_LU"
} 2>&1 | tee "$REPORT" >>"$LOG"

log "finished with status $status"
cat <<EOF

Read it here: $REPORT

  What would ADOPT the collapsed option:
    redacted   at or near the 81.2% ceiling  -- the hatch is still reachable when the
               passage is silent
    corrupted  well above the 38.5% the two-hatch design managed -- there is nowhere
               left to misroute
    intact / full / dose_0%  no worse than legacy -- the hatch stays quiet on clean text

  What would REJECT it: E firing on clean passages. One hatch that over-fires is worse
  than two that misroute, and this is the arm that shows it.

  If this was a SAMPLE run (SAMPLE=N), it screens for LARGE effects only. A 40-point
  shift is visible at n=16; a 20-point shift is not. Treat a null as "no large effect"
  and re-run at full n before concluding anything from it.

  STILL MISSING for the full gold72 x all-defects grid (this run does not build them):
    grammar, awkward, addition, inconsistency  -- 0/10 passages in $RUN_ROOT
    omission, mistranslation                   -- built, but only at 0% and 30%
      OUT_ROOT=$RUN_ROOT DEFECTS="grammar addition" RATES="0% 5% 10% 15% 20% 30%" \\
        SKIP_BASE=1 SKIP_BANKS=1 bash evaluation/scripts/campaigns/current/build_tier1_defect_variants.sh
      (awkward and inconsistency additionally need OPENAI_API_KEY for their banks)
EOF
exit $status
