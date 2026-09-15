#!/usr/bin/env bash
# Does rewriting the two meta-options fix E/F misrouting -- without breaking abstention?
#
# THE DEFECT. In the corrupted condition, where the passage states an answer that no content
# option gives, the model took the abstain option on 21 of 52 items. All 21 were read: in 20
# the passage did state an answer, so abstaining was wrong, and two traces state the
# none-of-the-above condition aloud before abstaining anyway.
#
# THE FIX, three changes, all appended at run time -- no dataset regenerated, no retranslation:
#   1  --meta-labels explicit    The old abstain label 根据这段文字无法判断 is a claim about the
#                                READER, and in the corrupted condition it is TRUE: the model
#                                cannot determine which OPTION is right. The new labels put
#                                both conditions on the PASSAGE, where the divide lies.
#   2  --meta-wording sequential An order of operations instead of a description: does the
#                                passage answer at all, then is that answer among A-D.
#   3  --abstain F --nota E      Swaps which LETTER carries which role, so elimination
#                                reasoning walking A->F meets none-of-the-above first. This
#                                confounds role order with letter identity, so BOTH
#                                assignments run and the pair isolates it.
#
# THE TWO DEFECT MECHANISMS, each with a surgical control and the real variants:
#
#   OMISSION       text is REMOVED, so the passage falls silent -- abstain is correct.
#     redact       surgical: the keyed verse is deleted. Provably absent, fully countable.
#     dose omission  the real variants at 0% and 30%: verses truncated and some deleted.
#   MISTRANSLATION text is REPLACED, so the passage answers WRONGLY -- nota is correct.
#     corrupt      surgical: a verified LLM rewrite of the answer span. Ships an intact
#                  condition too, which is the collateral-damage check on clean text.
#     dose mistranslation  the real variants: bank-driven phrase substitution at each dose.
#
# Reading one mechanism alone buys a trade and calls it a fix: any wording that makes
# abstaining harder improves the mistranslation side and damages the omission side.
#
# SCORING. Conditions with a defensible answer (redacted, corrupted, intact, full, dose_0%)
# are scored for correctness. A dosed passage may or may not still answer, so dose_30% has
# no correct letter and only its abstain/nota/content RATES are reported -- which is the
# deployment question anyway: does the rate track dose.
#
#   nohup caffeinate -is bash evaluation/scripts/campaigns/current/run_meta_label_sweep.sh &
#   LIMIT=8 bash ...          # rehearsal, ~10 min. NOTE: --limit takes the first N items,
#                             # which all come from ONE passage -- fine for plumbing, not a
#                             # sample. Percentages from a LIMIT run mean nothing.
#   ARMS="1 2" bash ...       # just the corrupted pair
#   DOSES="0% 30%" DEFECTS="omission mistranslation"
#
# Deliberately NOT `set -e`: one failing arm must not take the others with it overnight.
set -uo pipefail

MODEL="${MODEL:-qwen3:1.7b}"
LABELS="${LABELS:-ABCDEF}"
META_LABELS="${META_LABELS:-explicit}"
META_WORDING="${META_WORDING:-sequential}"
LIMIT="${LIMIT:-0}"
ARMS="${ARMS:-1 2 3 4 5 6 7 8 9}"
DOSES="${DOSES:-0% 30%}"
RUN_ROOT="${RUN_ROOT:-evaluation/outputs/tier1_bsb_unblinded_5opt}"
BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
PROBE=evaluation/scripts/mcq/diagnostics/abstention_thinking_probe.py
SCORE=evaluation/scripts/analysis/current/score_meta_arms.py

# Baselines already on disk, all under the OLD labels and wording with abstain=E, nota=F.
BASE_CORRUPT="${BASE_CORRUPT:-evaluation/outputs/reports/f_wording_full/disjoint.json}"
BASE_REDACT="${BASE_REDACT:-evaluation/outputs/reports/abstention_overnight_20260913_015756/arm2_redact_think_on.json}"
BASE_DOSE_OM="${BASE_DOSE_OM:-evaluation/outputs/reports/abstention_overnight_20260913_015756/arm4_dose_think_on.json}"

TS="$(date +%Y%m%d_%H%M%S)"
OUT="evaluation/outputs/reports/meta_label_sweep_${TS}"
mkdir -p "$OUT"
LOG="$OUT/run.log"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "preflight  model=$MODEL arms=$ARMS limit=$LIMIT labels=$META_LABELS wording=$META_WORDING"
curl -sf --max-time 10 "$BASE_URL/api/tags" -o "$OUT/ollama_tags.json" \
  || { log "FATAL: ollama unreachable at $BASE_URL"; exit 2; }
grep -q "\"${MODEL%%:*}" "$OUT/ollama_tags.json" \
  || { log "FATAL: $MODEL not pulled. run: ollama pull $MODEL"; exit 2; }
[ -d "$RUN_ROOT" ] || { log "FATAL: no run root at $RUN_ROOT"; exit 2; }
python3 "$PROBE" --self-test >>"$LOG" 2>&1 \
  || { log "FATAL: probe self-tests failed; see $LOG"; exit 2; }
python3 "$SCORE" --self-test >>"$LOG" 2>&1 \
  || { log "FATAL: scorer self-tests failed; see $LOG"; exit 2; }
for b in "$BASE_CORRUPT" "$BASE_REDACT" "$BASE_DOSE_OM"; do
  [ -f "$b" ] || log "  [warn] baseline missing, its contrast will be skipped: $b"
done

# Which dose arms can actually run. mistranslation substitutes passage vocabulary, so it
# needs a per-passage bank AND variants built into THIS run root; the banks that exist were
# built against the pseudonymized tier1 base, whose Chinese differs -- only 22% of their
# source strings occur in the canonical text, which would give a weak and wildly uneven
# dose. Rather than run a silently under-perturbed arm, skip it and say so.
HAVE_MISTRANS=0
python3 - "$RUN_ROOT" "$LIMIT" $DOSES <<'PY' | tee -a "$LOG"
import sys
sys.path.insert(0, "."); sys.path.insert(0, "evaluation/scripts/mcq/diagnostics")
from abstention_thinking_probe import (load_items, load_corrupt_items, load_dose_items,
                                       DEFAULT_WINDOWS)
root, limit, doses = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
r, _ = load_items(root, DEFAULT_WINDOWS, limit)
c, _ = load_corrupt_items(root, DEFAULT_WINDOWS,
                          "evaluation/datasets/mcq/corrupted_windows.json", limit)
print(f"  redact  {len(r):3d} items x 2 conditions")
print(f"  corrupt {len(c):3d} items x 2 conditions")
total = 2 * (2 * len(r) + 2 * len(c))
for d in ("omission", "mistranslation"):
    try:
        items, sk = load_dose_items(root, DEFAULT_WINDOWS, doses, limit, d)
    except Exception as exc:
        items, sk = [], {"error": exc}
    print(f"  dose {d:15} {len(items):3d} items x {len(doses)} doses"
          + ("" if items else f"   SKIPPED ({dict(sk)})"))
    if items:
        total += len(doses) * len(items) * (2 if d == "omission" else 3)
        if d == "mistranslation":
            open("/tmp/_have_mistrans", "w").write("1")
print(f"  ~{total} generations, ~{total*13/3600:.1f} h at the observed 13 s/call")
if not r or not c:
    raise SystemExit("FATAL: a control arm loaded 0 items")
PY
[ "${PIPESTATUS[0]}" = "0" ] || { log "FATAL: preflight item load failed"; exit 2; }
[ -f /tmp/_have_mistrans ] && { HAVE_MISTRANS=1; rm -f /tmp/_have_mistrans; }
[ "$HAVE_MISTRANS" = "1" ] || log "  mistranslation dose arms (7-9) will be skipped: no variants in $RUN_ROOT.
    Build them first (needs OPENAI_API_KEY, ~minutes):
      OUT_ROOT=$RUN_ROOT DEFECTS=mistranslation RATES='$DOSES' SKIP_BASE=1 \\
        bash evaluation/scripts/campaigns/current/build_tier1_defect_variants.sh"
log "outputs -> $OUT"

status=0
arm() {   # arm <n> <label> <outfile> <abstain> <nota> <labelset> <wording> <extra...>
  local n="$1" label="$2" out="$3" ab="$4" nota="$5" mlab="$6" mword="$7"; shift 7
  case " $ARMS " in *" $n "*) ;; *) log "skip arm $n ($label)"; return 0 ;; esac
  log "=== arm $n: $label ==="
  if python3 "$PROBE" --run-root "$RUN_ROOT" --model "$MODEL" --limit "$LIMIT" \
       --labels "$LABELS" --abstain "$ab" --nota "$nota" \
       --meta-labels "$mlab" --meta-wording "$mword" \
       --out "$out" "$@" >>"$LOG" 2>&1; then
    log "arm $n done -> $out"
  else
    log "arm $n FAILED (continuing)"; status=1
  fi
}

C_EF="$OUT/arm1_corrupt_EF.json";        C_FE="$OUT/arm2_corrupt_FE.json"
R_EF="$OUT/arm3_redact_EF.json";         R_FE="$OUT/arm4_redact_FE.json"
DO_EF="$OUT/arm5_dose_omission_EF.json"; DO_FE="$OUT/arm6_dose_omission_FE.json"
DM_BASE="$OUT/arm7_dose_mistrans_BASELINE.json"
DM_EF="$OUT/arm8_dose_mistrans_EF.json"; DM_FE="$OUT/arm9_dose_mistrans_FE.json"

# --- mistranslation mechanism: the passage answers wrongly, nota is correct -------------
arm 1 "corrupt  (surgical mistranslation), E=abstain F=nota" "$C_EF" E F "$META_LABELS" "$META_WORDING" --mode corrupt
arm 2 "corrupt  (surgical mistranslation), F=abstain E=nota" "$C_FE" F E "$META_LABELS" "$META_WORDING" --mode corrupt
# --- omission mechanism: the passage falls silent, abstain is correct -------------------
arm 3 "redact   (surgical omission), E=abstain F=nota"       "$R_EF" E F "$META_LABELS" "$META_WORDING" --mode redact
arm 4 "redact   (surgical omission), F=abstain E=nota"       "$R_FE" F E "$META_LABELS" "$META_WORDING" --mode redact
# --- the real defect variants -----------------------------------------------------------
arm 5 "dose omission, E=abstain F=nota"                      "$DO_EF" E F "$META_LABELS" "$META_WORDING" --mode dose --defect omission --doses $DOSES
arm 6 "dose omission, F=abstain E=nota"                      "$DO_FE" F E "$META_LABELS" "$META_WORDING" --mode dose --defect omission --doses $DOSES
if [ "$HAVE_MISTRANS" = "1" ]; then
  # No mistranslation dose arm has ever been run, so its baseline has to be measured here
  # rather than read off disk.
  arm 7 "dose mistranslation, OLD labels+wording (baseline)"  "$DM_BASE" E F current current --mode dose --defect mistranslation --doses $DOSES
  arm 8 "dose mistranslation, E=abstain F=nota"               "$DM_EF" E F "$META_LABELS" "$META_WORDING" --mode dose --defect mistranslation --doses $DOSES
  arm 9 "dose mistranslation, F=abstain E=nota"               "$DM_FE" F E "$META_LABELS" "$META_WORDING" --mode dose --defect mistranslation --doses $DOSES
else
  log "skip arms 7-9 (no mistranslation variants in $RUN_ROOT)"
fi

REPORT="$OUT/comparison.txt"
pair() {   # pair <title> <before> <after>
  [ -f "$2" ] && [ -f "$3" ] || { echo; echo "--- $1 --- SKIPPED (missing arm)"; return; }
  echo; echo "--- $1 ---"; python3 "$SCORE" --contrast "$2" "$3"
}
{
  echo "############ per-arm ############"
  for f in "$BASE_CORRUPT" "$C_EF" "$C_FE" "$BASE_REDACT" "$R_EF" "$R_FE" \
           "$BASE_DOSE_OM" "$DO_EF" "$DO_FE" "$DM_BASE" "$DM_EF" "$DM_FE"; do
    [ -f "$f" ] && python3 "$SCORE" "$f"
  done
  echo; echo "############ contrasts ############"
  echo; echo "===== MISTRANSLATION: does the relabel fix it ====="
  pair "surgical: baseline vs relabel+sequential"      "$BASE_CORRUPT" "$C_EF"
  pair "surgical: does listing nota FIRST add anything" "$C_EF" "$C_FE"
  pair "real variants: baseline vs relabel"            "$DM_BASE" "$DM_EF"
  pair "real variants: letter swap"                    "$DM_EF" "$DM_FE"
  echo; echo "===== OMISSION: what did it COST ====="
  pair "surgical: baseline vs relabel+sequential"      "$BASE_REDACT" "$R_EF"
  pair "surgical: letter swap"                         "$R_EF" "$R_FE"
  pair "real variants: baseline vs relabel"            "$BASE_DOSE_OM" "$DO_EF"
  pair "real variants: letter swap"                    "$DO_EF" "$DO_FE"
} 2>&1 | tee "$REPORT" >>"$LOG"

log "finished with status $status"
cat <<EOF

Read in the morning:
  $REPORT
    MISTRANSLATION  baseline 38.5% correct on the surgical control -- did the relabel beat it
    OMISSION        baseline 81.2% correct on the surgical control -- this is the cost side.
                    A fix that moves this down materially is a trade, not a fix.
    dose_30%        no correct letter; read the abstain/nota RATES and whether they track dose
  $OUT/run.log      per-arm detail and reasoning traces
EOF
exit $status
