#!/usr/bin/env bash
# Is the overnight abstention run finished, still going, or dead?
#
# "No output yet" is ambiguous on its own -- a thinking arm is legitimately quiet for
# minutes at a time. What separates the three states is the HEARTBEAT: the probe prints a
# timestamped progress line every 5 items, so a log that has not moved in far longer than
# one heartbeat interval is stalled, not slow.
#
#   bash evaluation/scripts/campaigns/current/check_abstention_run.sh          # newest run
#   bash evaluation/scripts/campaigns/current/check_abstention_run.sh <dir>    # a specific one
set -uo pipefail

D="${1:-$(ls -dt evaluation/outputs/reports/abstention_overnight_* 2>/dev/null | head -1)}"
[ -n "$D" ] && [ -d "$D" ] || { echo "no run directory found"; exit 1; }
echo "run: $D"

LOG="$D/run.log"
[ -f "$LOG" ] || { echo "  no run.log -- the run never started"; exit 1; }

# 1. did it reach the end?
if grep -q "finished with status" "$LOG"; then
  echo "  STATE: FINISHED -- $(grep 'finished with status' "$LOG" | tail -1)"
else
  echo "  STATE: not finished"
fi

# 2. is a process still alive? (only meaningful on the machine that launched it)
# Only meaningful ON THE MACHINE THAT LAUNCHED THE RUN. Checking from anywhere else -- a
# mounted folder, another shell -- sees a different process table and says "not running"
# about a run that is perfectly healthy, so the staleness check below is the real signal.
pids="$(ps axo pid=,command= 2>/dev/null \
        | grep -F abstention_thinking_probe.py \
        | grep -v -e grep -e check_abstention_run \
        | awk '$1 > 1 {printf "%s ", $1}')"
if [ -n "${pids// /}" ]; then
  echo "  process: RUNNING (pid ${pids%% })"
else
  echo "  process: none visible here (conclusive only on the launching machine)"
fi

# 3. how stale is the log?
idle=$(python3 - "$LOG" <<'PY'
import os, sys, time
print(f"{(time.time() - os.path.getmtime(sys.argv[1]))/60:.1f}")
PY
)
echo "  last write: ${idle} min ago"
awk -v i="$idle" 'BEGIN{ if (i+0 > 15) print "  ^^ a heartbeat prints every 5 items; >15 min idle means STALLED, not slow" }'

# 4. per-arm progress, read from the partial results themselves
echo "  arms:"
for f in arm1_redact_think_off arm2_redact_think_on arm3_dose_think_off arm4_dose_think_on; do
  p="$D/$f.json"
  if [ -f "$p" ]; then
    python3 - "$p" "$f" <<'PY'
import json, sys
try:
    rows = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as e:
    print(f"    {sys.argv[2]:24} unreadable ({e})"); raise SystemExit
conds = {}
for r in rows:
    conds[r["condition"]] = conds.get(r["condition"], 0) + 1
per = ", ".join(f"{k} {v}" for k, v in sorted(conds.items()))
ab = sum(r.get("abstained") for r in rows)
print(f"    {sys.argv[2]:24} {len(rows):4d} result(s)  [{per}]  abstained {ab}")
PY
  else
    echo "    $f  (not started)"
  fi
done

# 5. the comparison, if it got that far
if [ -s "$D/comparison.txt" ]; then
  echo "  comparison.txt: $(wc -l < "$D/comparison.txt" | tr -d ' ') lines -- ready to read"
else
  echo "  comparison.txt: not written yet"
fi
echo
echo "  last log line: $(tail -1 "$LOG")"
