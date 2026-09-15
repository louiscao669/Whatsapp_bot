#!/usr/bin/env bash
# Tier-1 gold72, CANONICAL names, 6-option MCQs (E = "I can't tell from this passage",
# F = "None of the above"), MCQ ARM ONLY, every defect family, answered by qwen3:1.7b
# with THINKING ENABLED.
#
# Differences from run_gold72_canonical_5opt.sh, all deliberate:
#   MCQ_CHOICE_LABELS=ABCDEF   six options; parse gates and prompt text follow this
#   QA_FORMATS=mcq             skip the open arm entirely. Open items are what cost
#                              money -- each needs an OpenAI back-translation and a
#                              judge call -- and nothing here analyses them.
#   NO_THINK=0                 qwen3 reasons. /no_think alone is ignored by qwen3:1.7b,
#                              so the pipeline sends Ollama's structured think:false;
#                              omitting the flag is what actually enables thinking. The
#                              cell is written to <passage>/qwen317b_think/ so it cannot
#                              collide with the non-thinking condition.
#   DEFECTS=all six families   addition and inconsistency carry prefixed levels
#                              (adversarial_/bad_/neutral_, style_), which DISCOVER_LEVELS
#                              handles rather than a fixed RATES list.
#
# Self-contained: campaign scripts read ~20 environment knobs and a leftover export
# silently changes what runs, so every control flag is cleared and then set explicitly.
#
#   bash evaluation/scripts/campaigns/current/run_gold72_canonical_6opt_think.sh
#   PREVIEW=1 bash ...                       # print the plan, run nothing
#   SKIP_BUILD=1 bash ...                    # variants already built in this OUT_ROOT
set -euo pipefail

unset DRY_RUN STOP_AFTER SKIP_BASE SKIP_BANKS PASSAGES FORCE_ANSWER FORCE_TRANSLATE \
      FORCE_PASSAGE_TRANSLATE FORCE_BACKTRANSLATE FORCE_SCORE REPLACE_INPUTS \
      DISCOVER_LEVELS RAW SHARE_TRANSLATION VERSE_WINDOW ARM_SUFFIX ARMS \
      CHAPTERS OUT_ROOT QA_DIR PASSAGE_DIR WINDOWS MAP METHOD DEFECTS RATES MODELS \
      SLUG_SUFFIX MCQ_ROTATE MCQ_SHUFFLE_SEED 2>/dev/null || true

export MCQ_CHOICE_LABELS=ABCDEF
export MCQ_ABSTAIN_LABEL=E
export MCQ_NOTA_LABEL=F
export QA_FORMATS=mcq
export NO_THINK=0
export OUT_ROOT=evaluation/outputs/tier1_bsb_unblinded_6opt_think
export QA_DIR=evaluation/datasets/qa/tier1_gold72_canonical_6opt
export PASSAGE_DIR=evaluation/datasets/passages/tier1_bsb
export MAP=evaluation/datasets/pseudonym_remap/empty_map_unblinded.json
export WINDOWS=QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json
export METHOD=llm_prompt_high
# Scope. Named *_OVERRIDE rather than DEFECTS/RATES so that a stale `export DEFECTS=`
# from an earlier command cannot silently change what runs -- that class of accident has
# cost this project two runs already.
export DEFECTS="${DEFECTS_OVERRIDE:-omission mistranslation grammar awkward addition inconsistency}"
export RATES="${RATES_OVERRIDE:-0% 5% 10% 15% 20% 30%}"
export MODELS="${MODELS_OVERRIDE:-qwen3:1.7b}"

: "${OPENAI_API_KEY:?export OPENAI_API_KEY (set -a; source .env; set +a)}"
[ -d "$QA_DIR" ]   || { echo "missing $QA_DIR -- run add_meta_options.py --nota first" >&2; exit 1; }
[ -f "$WINDOWS" ]  || { echo "missing $WINDOWS" >&2; exit 1; }
n6=$(python3 - <<'PY'
import json, os
d = os.environ["QA_DIR"]
bad = 0
for fn in sorted(os.listdir(d)):
    if not fn.endswith(".json"): continue
    for it in json.load(open(os.path.join(d, fn))):
        m = it.get("mcq")
        if m and len(m.get("mcq_options") or []) != 6: bad += 1
print(bad)
PY
)
[ "$n6" = "0" ] || { echo "$n6 item(s) in $QA_DIR do not have 6 options" >&2; exit 1; }

say() { echo; echo "======== [$(date '+%H:%M:%S')] $*"; }
PREVIEW="${PREVIEW:-0}"
if [ "$PREVIEW" = "1" ]; then
  echo "PREVIEW -- would run, in order:"
  echo "  QA         $QA_DIR (6 options, MCQ arm only)"
  echo "  out        $OUT_ROOT"
  echo "  model      $MODELS  thinking=on  -> <passage>/qwen317b_think/"
  echo "  defects    $DEFECTS"
  echo "  rates      $RATES  (answering uses DISCOVER_LEVELS=1)"
  python3 - <<'PY'
import os
fams = os.environ["DEFECTS"].split()
rates = os.environ["RATES"].split()
per = {"addition": 1 + 3 * len([r for r in rates if r != "0%"])}
lv = sum(per.get(f, len(rates)) for f in fams)
# The 71 items are spread ACROSS the 10 passages (~7 each), so one (family, dose) cell is
# 71 answers in total, not 71 per passage. Translations are per passage per level, so those
# DO scale with 10.
n = lv * 71
print(f"  scale      {lv} (family,dose) cells x 71 items = {n:,} answers")
print(f"             ~{n*12.78/3600:.1f}h with thinking on (measured mean 12.78s/answer),")
print(f"             ~{n*0.54/3600:.1f}h without (0.54s).")
print(f"             build: {lv*10} passage translations ({lv} levels x 10 passages)")
PY
  echo "  1 build variants for every family at every rate"
  echo "  2 translate QA only (STOP_AFTER=translate)"
  echo "  3 pin E and F to fixed Chinese strings"
  echo "  4 answer (FORCE_ANSWER=1, DISCOVER_LEVELS=1)"
  echo "  5 verify window binding + meta-option firing rates"
  exit 0
fi

if [ "${SKIP_BUILD:-0}" != "1" ]; then
  say "1/5 build base translation + every defect family at every rate"
  bash evaluation/scripts/campaigns/current/build_tier1_defect_variants.sh
else
  say "1/5 build SKIPPED (SKIP_BUILD=1)"
fi

say "2/5 translate QA per model (no answering yet)"
STOP_AFTER=translate bash evaluation/scripts/campaigns/current/run_tier1_defect_models.sh

say "3/5 meta-options: how did the translator render E and F?"
python3 evaluation/scripts/mcq/preparation/pin_meta_options.py "$OUT_ROOT"
say "3/5 pinning them to one string each"
python3 evaluation/scripts/mcq/preparation/pin_meta_options.py "$OUT_ROOT" --apply

say "4/5 answer (MCQ only, thinking on, every generated level)"
FORCE_ANSWER=1 DISCOVER_LEVELS=1 \
  bash evaluation/scripts/campaigns/current/run_tier1_defect_models.sh

say "5/5 verify"
python3 evaluation/scripts/analysis/current/check_window_binding.py "$OUT_ROOT"
python3 evaluation/scripts/analysis/current/compare_meta_options.py || true

cat <<'NOTE'

Caveat recorded when the 6-option set was built, and it applies directly to this run:
with ONE meta-option, abstention fired at 6.6% at omission 30% (14/213 observations).
Split two ways -- E for "the passage does not say", F for "it says something not listed"
-- that is roughly 7 events per cell, and this run has a single answer model rather than
three. Check the firing rates before reading anything into a family x option interaction.
NOTE
