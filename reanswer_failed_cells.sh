#!/usr/bin/env bash
# Re-answer score cells that were silently zeroed (Ollama down / per-item generation failures).
# Generated 2026-07-07. Run from the repo root (eten-whatsapp-bot).
# Requires `ollama serve` running. Each cell is re-answered in full with --include-scored.
set -uo pipefail
cd "$(dirname "$0")"

# ---- preflight: refuse to run if Ollama is unreachable (so we never record zeros again) ----
if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "ERROR: Ollama not reachable at http://localhost:11434 — start ollama serve first." >&2
  exit 1
fi
export PYTHONPATH=.
S=evaluation/scripts/answer_score_subset_in_place.py
fail=0; ok=0

# ================= RE_ANSWER: 56 cells =================
python3 "$S" 12 --chapters 2 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke2/luke{chapter}/1.7b/local_inconsistency/name_10%" >&2; }
python3 "$S" 12 --chapters 2 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke2/luke{chapter}/1.7b/local_inconsistency/name_15%" >&2; }
python3 "$S" 12 --chapters 2 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke2/luke{chapter}/1.7b/local_inconsistency/name_20%" >&2; }
python3 "$S" 12 --chapters 2 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke2/luke{chapter}/1.7b/local_inconsistency/name_5%" >&2; }
python3 "$S" 12 --chapters 2 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke2/luke{chapter}/1.7b/local_inconsistency/style_10%" >&2; }
python3 "$S" 12 --chapters 2 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke2/luke{chapter}/1.7b/local_inconsistency/style_15%" >&2; }
python3 "$S" 12 --chapters 2 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke2/luke{chapter}/1.7b/local_inconsistency/style_20%" >&2; }
python3 "$S" 12 --chapters 2 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke2/luke{chapter}/1.7b/local_inconsistency/style_5%" >&2; }
python3 "$S" 7 --chapters 3 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke3/luke{chapter}/1.7b/local_inconsistency/name_10%" >&2; }
python3 "$S" 7 --chapters 3 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke3/luke{chapter}/1.7b/local_inconsistency/name_15%" >&2; }
python3 "$S" 7 --chapters 3 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke3/luke{chapter}/1.7b/local_inconsistency/name_20%" >&2; }
python3 "$S" 7 --chapters 3 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke3/luke{chapter}/1.7b/local_inconsistency/name_5%" >&2; }
python3 "$S" 7 --chapters 3 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke3/luke{chapter}/1.7b/local_inconsistency/style_10%" >&2; }
python3 "$S" 7 --chapters 3 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke3/luke{chapter}/1.7b/local_inconsistency/style_15%" >&2; }
python3 "$S" 7 --chapters 3 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke3/luke{chapter}/1.7b/local_inconsistency/style_20%" >&2; }
python3 "$S" 7 --chapters 3 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke3/luke{chapter}/1.7b/local_inconsistency/style_5%" >&2; }
python3 "$S" 18 --chapters 4 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke4/luke{chapter}/1.7b/local_inconsistency/name_10%" >&2; }
python3 "$S" 18 --chapters 4 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke4/luke{chapter}/1.7b/local_inconsistency/name_15%" >&2; }
python3 "$S" 18 --chapters 4 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke4/luke{chapter}/1.7b/local_inconsistency/name_20%" >&2; }
python3 "$S" 18 --chapters 4 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke4/luke{chapter}/1.7b/local_inconsistency/name_5%" >&2; }
python3 "$S" 18 --chapters 4 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke4/luke{chapter}/1.7b/local_inconsistency/style_10%" >&2; }
python3 "$S" 18 --chapters 4 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke4/luke{chapter}/1.7b/local_inconsistency/style_15%" >&2; }
python3 "$S" 18 --chapters 4 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke4/luke{chapter}/1.7b/local_inconsistency/style_20%" >&2; }
python3 "$S" 18 --chapters 4 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke4/luke{chapter}/1.7b/local_inconsistency/style_5%" >&2; }
python3 "$S" 11 --chapters 5 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke5/luke{chapter}/1.7b/local_inconsistency/name_10%" >&2; }
python3 "$S" 11 --chapters 5 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke5/luke{chapter}/1.7b/local_inconsistency/name_15%" >&2; }
python3 "$S" 11 --chapters 5 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke5/luke{chapter}/1.7b/local_inconsistency/name_20%" >&2; }
python3 "$S" 11 --chapters 5 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke5/luke{chapter}/1.7b/local_inconsistency/name_5%" >&2; }
python3 "$S" 11 --chapters 5 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke5/luke{chapter}/1.7b/local_inconsistency/style_10%" >&2; }
python3 "$S" 11 --chapters 5 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke5/luke{chapter}/1.7b/local_inconsistency/style_15%" >&2; }
python3 "$S" 11 --chapters 5 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke5/luke{chapter}/1.7b/local_inconsistency/style_20%" >&2; }
python3 "$S" 11 --chapters 5 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke5/luke{chapter}/1.7b/local_inconsistency/style_5%" >&2; }
python3 "$S" 8 --chapters 6 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke6/luke{chapter}/1.7b/local_inconsistency/name_10%" >&2; }
python3 "$S" 8 --chapters 6 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke6/luke{chapter}/1.7b/local_inconsistency/name_15%" >&2; }
python3 "$S" 8 --chapters 6 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke6/luke{chapter}/1.7b/local_inconsistency/name_20%" >&2; }
python3 "$S" 8 --chapters 6 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke6/luke{chapter}/1.7b/local_inconsistency/name_5%" >&2; }
python3 "$S" 8 --chapters 6 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke6/luke{chapter}/1.7b/local_inconsistency/style_10%" >&2; }
python3 "$S" 8 --chapters 6 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke6/luke{chapter}/1.7b/local_inconsistency/style_15%" >&2; }
python3 "$S" 8 --chapters 6 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke6/luke{chapter}/1.7b/local_inconsistency/style_20%" >&2; }
python3 "$S" 8 --chapters 6 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke6/luke{chapter}/1.7b/local_inconsistency/style_5%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/local_inconsistency/name_10%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/local_inconsistency/name_15%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/local_inconsistency/name_20%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/local_inconsistency/name_5%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/local_inconsistency/style_10%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/local_inconsistency/style_15%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/local_inconsistency/style_20%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/local_inconsistency/style_5%" >&2; }
python3 "$S" 9 --chapters 8 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke8/luke{chapter}/1.7b/local_inconsistency/name_10%" >&2; }
python3 "$S" 9 --chapters 8 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke8/luke{chapter}/1.7b/local_inconsistency/name_15%" >&2; }
python3 "$S" 9 --chapters 8 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke8/luke{chapter}/1.7b/local_inconsistency/name_20%" >&2; }
python3 "$S" 9 --chapters 8 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "name_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke8/luke{chapter}/1.7b/local_inconsistency/name_5%" >&2; }
python3 "$S" 9 --chapters 8 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke8/luke{chapter}/1.7b/local_inconsistency/style_10%" >&2; }
python3 "$S" 9 --chapters 8 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke8/luke{chapter}/1.7b/local_inconsistency/style_15%" >&2; }
python3 "$S" 9 --chapters 8 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke8/luke{chapter}/1.7b/local_inconsistency/style_20%" >&2; }
python3 "$S" 9 --chapters 8 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/local_inconsistency" \
  --methods "style_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke8/luke{chapter}/1.7b/local_inconsistency/style_5%" >&2; }

# ================= PARTIAL_WRONG: 13 cells =================
python3 "$S" 22 --chapters 1 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/mistranslation" \
  --methods "30%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke1/luke{chapter}/1.7b/mistranslation/30%" >&2; }
python3 "$S" 12 --chapters 2 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/awkward" \
  --methods "30%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke2/luke{chapter}/1.7b/awkward/30%" >&2; }
python3 "$S" 18 --chapters 4 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/addition" \
  --methods "neutral_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke4/luke{chapter}/1.7b/addition/neutral_20%" >&2; }
python3 "$S" 18 --chapters 4 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/addition" \
  --methods "neutral_30%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke4/luke{chapter}/1.7b/addition/neutral_30%" >&2; }
python3 "$S" 11 --chapters 5 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/inconsistency" \
  --methods "name_15%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke5/luke{chapter}/1.7b/inconsistency/name_15%" >&2; }
python3 "$S" 11 --chapters 5 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/inconsistency" \
  --methods "name_20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke5/luke{chapter}/1.7b/inconsistency/name_20%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/addition" \
  --methods "bad_10%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/addition/bad_10%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/addition" \
  --methods "neutral_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/addition/neutral_5%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/awkward" \
  --methods "20%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/awkward/20%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/inconsistency" \
  --methods "name_5%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/inconsistency/name_5%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/1.7b/omission" \
  --methods "30%" --answer-model qwen3:1.7b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/1.7b/omission/30%" >&2; }
python3 "$S" 9 --chapters 7 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/llama 1b" \
  --methods "llm_prompt_high" --answer-model llama3.2:1b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke7/luke{chapter}/llama 1b/llm_prompt_high" >&2; }
python3 "$S" 9 --chapters 8 \
  --artifact-root-template "evaluation/outputs/luke{chapter}/llama 1b" \
  --methods "llm_prompt_high" --answer-model llama3.2:1b --answer-verse-window 2 \
  --formats both --include-scored \
  && ok=$((ok+1)) || { fail=$((fail+1)); echo "FAILED: luke8/luke{chapter}/llama 1b/llm_prompt_high" >&2; }

echo "re-answered ok=$ok  failed=$fail"
if [ "$fail" -gt 0 ]; then echo "Some cells failed — re-run this script (already-good cells are cheap to redo)."; fi
echo "Next: rebuild the MQM grid and re-run fit:defect from the refreshed scores."
