#!/usr/bin/env bash
# Abstention: thinking OFF vs ON, under a surgical control AND under real defect variants.
# Unattended, no API spend, local Ollama only.
#
# Four arms. Every arm answers the same items, so each contrast changes one thing.
#
#   1  redact  think off    2  redact  think on
#   3  dose    think off    4  dose    think on
#
#   redact   the keyed verse is removed from the window. The answer is provably absent, so
#            E is the only defensible choice and every failure is countable. This is the
#            clean control: it establishes whether the model CAN abstain.
#   dose     the real omission variants at 0% and 30%. Verses are truncated and some are
#            deleted outright -- 39 of 71 windows lose at least one verse at 30%, and 2
#            lose all three. This is the deployment question: does abstention track DOSE.
#
# Six options throughout: A-D plus E (abstain) and F (none of the above).
#
#   think off -> the rate, and it is fast.
#   think on  -> the rate PLUS the reasoning trace, which is the only way to see the model
#                conclude "the passage does not say" and then pick a content option anyway.
#                That is a prompt/format failure, not a reading failure, and it is fixed
#                differently. The trace is normally discarded: clean_raw_answer strips it
#                and only thinking_chars survives.
#
#   bash evaluation/scripts/campaigns/current/run_abstention_overnight.sh
#   nohup bash evaluation/scripts/campaigns/current/run_abstention_overnight.sh &
#   LIMIT=15 bash ...        # rehearsal, ~8 min, exercises every path
#   ARMS="1 2" bash ...      # only the redact pair
#
# Deliberately NOT `set -e`: one failing arm must not take the others with it overnight.
set -uo pipefail

MODEL="${MODEL:-qwen3:1.7b}"
# Six options: E "根据这段文字无法判断" (the passage does not say) and F "以上都不是"
# (it does say, but not any of A-D). The translated QA in a finished run is 5-option
# because no 6-option set has ever been translated; F is a FIXED string, so the probe
# appends it at no cost, exactly as pin_meta_options.py --add-missing would.
# F is never the correct answer in either condition, so its rate is a false-alarm
# measure -- and shows whether offering it cannibalises E.
LABELS="${LABELS:-ABCDEF}"
ABSTAIN="${ABSTAIN:-E}"
NOTA="${NOTA:-F}"
LIMIT="${LIMIT:-0}"
ARMS="${ARMS:-1 2 3 4}"
DOSES="${DOSES:-0% 30%}"
DEFECT="${DEFECT:-omission}"
RUN_ROOT="${RUN_ROOT:-evaluation/outputs/tier1_bsb_unblinded_5opt}"
BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
PROBE=evaluation/scripts/mcq/diagnostics/abstention_thinking_probe.py

TS="$(date +%Y%m%d_%H%M%S)"
OUT="evaluation/outputs/reports/abstention_overnight_${TS}"
mkdir -p "$OUT"
LOG="$OUT/run.log"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# ---- preflight: fail in ten seconds, not at 3am ----------------------------------
log "preflight  model=$MODEL  arms=$ARMS  limit=${LIMIT}  options=$LABELS abstain=$ABSTAIN nota=${NOTA:-off}"
curl -sf --max-time 10 "$BASE_URL/api/tags" -o "$OUT/ollama_tags.json" \
  || { log "FATAL: ollama unreachable at $BASE_URL"; exit 2; }
grep -q "\"${MODEL%%:*}" "$OUT/ollama_tags.json" \
  || { log "FATAL: $MODEL not pulled. run: ollama pull $MODEL"; exit 2; }
[ -d "$RUN_ROOT" ] || { log "FATAL: no run root at $RUN_ROOT"; exit 2; }
python3 "$PROBE" --self-test >>"$LOG" 2>&1 \
  || { log "FATAL: probe self-tests failed; see $LOG"; exit 2; }
python3 - "$RUN_ROOT" "$LIMIT" "$DEFECT" $DOSES <<'PY' | tee -a "$LOG"
import sys
sys.path.insert(0, "."); sys.path.insert(0, "evaluation/scripts/mcq/diagnostics")
from abstention_thinking_probe import load_items, load_dose_items
root, limit, defect, doses = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4:]
W = "QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json"
r, _ = load_items(root, W, limit)
d, _ = load_dose_items(root, W, doses, limit, defect)
calls = 2 * len(r) + len(doses) * len(d)
print(f"  redact {len(r)} items x 2, dose {len(d)} items x {len(doses)}")
print(f"  {calls} generations per thinking arm; "
      f"~{calls*12.78/60:.0f} min on, ~{calls*0.54/60:.1f} min off")
if not r or not d:
    raise SystemExit("FATAL: an arm loaded 0 items")
PY
[ "${PIPESTATUS[0]}" = "0" ] || { log "FATAL: preflight item load failed"; exit 2; }
log "outputs -> $OUT"

status=0
arm() {                       # arm <n> <label> <outfile> <extra args...>
  local n="$1" label="$2" out="$3"; shift 3
  case " $ARMS " in *" $n "*) ;; *) log "skip arm $n ($label)"; return 0 ;; esac
  log "=== arm $n/4: $label ==="
  if python3 "$PROBE" --run-root "$RUN_ROOT" --model "$MODEL" --limit "$LIMIT" \
       --labels "$LABELS" --abstain "$ABSTAIN" --nota "$NOTA" \
       --out "$out" "$@" >>"$LOG" 2>&1; then
    log "arm $n done -> $out"
  else
    log "arm $n FAILED (continuing)"; status=1
  fi
}

R_OFF="$OUT/arm1_redact_think_off.json"; R_ON="$OUT/arm2_redact_think_on.json"
D_OFF="$OUT/arm3_dose_think_off.json";   D_ON="$OUT/arm4_dose_think_on.json"

arm 1 "redact, thinking OFF"  "$R_OFF" --mode redact --no-think
arm 2 "redact, thinking ON"   "$R_ON"  --mode redact
arm 3 "dose, thinking OFF"    "$D_OFF" --mode dose --defect "$DEFECT" --doses $DOSES --no-think
arm 4 "dose, thinking ON"     "$D_ON"  --mode dose --defect "$DEFECT" --doses $DOSES

: > "$OUT/comparison.txt"
for pair in "REDACT:$R_OFF:$R_ON" "DOSE:$D_OFF:$D_ON"; do
  name="${pair%%:*}"; rest="${pair#*:}"; a="${rest%%:*}"; b="${rest#*:}"
  if [ -f "$a" ] && [ -f "$b" ]; then
    log "=== $name: paired thinking off vs on ==="
    { echo; echo "############ $name ############"; } >> "$OUT/comparison.txt"
    python3 "$PROBE" --compare "$a" "$b" 2>&1 | tee -a "$OUT/comparison.txt" | tee -a "$LOG"
  else
    log "skip $name comparison: an arm is missing"
  fi
done

log "finished with status $status"
cat <<EOF

Read in the morning:
  $OUT/comparison.txt          both contrasts, with paired McNemar p
  $OUT/run.log                 per-arm detail, including traces that said "absent"
  $OUT/arm2_redact_think_on.json   traces under the surgical control
  $OUT/arm4_dose_think_on.json     traces under the real defect variants
EOF
exit $status
