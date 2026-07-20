#!/usr/bin/env bash
# Launch the mixed-defect fill run (run_missing_mixed_cells.sh) inside a
# detached tmux session, with keep-awake (caffeinate) and a timestamped log.
#
# Usage (from anywhere; needs OPENAI_API_KEY exported and Ollama running):
#   bash evaluation/scripts/tmux_run_missing_mixed_cells.sh
#   MODELS="llama1b qwen1.5b" bash evaluation/scripts/tmux_run_missing_mixed_cells.sh
#
# Then:
#   tmux attach -t mixedfill     # watch progress   (detach again: Ctrl-b d)
#   tail -f <log path printed below>
#   tmux kill-session -t mixedfill   # abort (safe: rerun resumes via caching)
set -euo pipefail
cd "$(dirname "$0")/../.."

SESSION="${SESSION:-mixedfill}"
MODELS="${MODELS:-qwen1.7b llama1b qwen1.5b}"
LOG="evaluation/outputs/reports/mixed_fill_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$(dirname "$LOG")"

command -v tmux >/dev/null || { echo "tmux not installed (brew install tmux)" >&2; exit 1; }
[ -n "${OPENAI_API_KEY:-}" ] || { echo "OPENAI_API_KEY not set — export it first." >&2; exit 1; }
curl -s --max-time 3 http://localhost:11434/api/tags >/dev/null \
  || { echo "Ollama not reachable on :11434 — start it first." >&2; exit 1; }

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "session '$SESSION' already exists — attach with: tmux attach -t $SESSION" >&2
  exit 1
fi

KEEPAWAKE=""
command -v caffeinate >/dev/null && KEEPAWAKE="caffeinate -dims"

tmux new-session -d -s "$SESSION" -c "$(pwd)"
# export the key inside the tmux shell (fresh shells don't inherit it reliably)
tmux send-keys -t "$SESSION" "export OPENAI_API_KEY='${OPENAI_API_KEY}'; clear" C-m
tmux send-keys -t "$SESSION" \
  "$KEEPAWAKE env PYTHONUNBUFFERED=1 MODELS='${MODELS}' bash evaluation/scripts/run_missing_mixed_cells.sh 2>&1 | tee '${LOG}'; echo; echo '=== RUN FINISHED — log: ${LOG} ==='" C-m

echo "Started tmux session '$SESSION'  (models: $MODELS)"
echo "  watch:  tmux attach -t $SESSION    (detach: Ctrl-b then d)"
echo "  log:    tail -f $LOG"
