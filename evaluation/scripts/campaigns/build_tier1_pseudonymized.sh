#!/usr/bin/env bash
# Build the pre-pipeline pseudonymized Tier 1 inputs.
#
# Four steps, in order:
#   1. build_passage_name_map.py   -- LLM entity extraction over the 10 Tier 1
#      passages -> one map with pseudonym_en + pseudonym_zh per entity. Entities
#      already committed for Luke 1-8 keep their pseudonyms, so old and new
#      material stay comparable.
#   2. audit_name_map.py           -- deterministic repair of the LLM's output.
#      The 2026-08-04 extraction gave "Paul" the aliases `he`/`him` and gave
#      "Jeroboam" the aliases `king`/`the king`; applied unedited those rewrite
#      every pronoun and every generic king across all ten passages. Also merges
#      the three competing deity entries and restores the documented
#      "generic -> not substituted" policy for lion/donkey/altar/etc.
#   3. reconcile_qa_aliases.py     -- deterministic. The passage (NIV) and the
#      uW QA use different spellings (Abimelek/Abimelech, Jerub-Baal/Jerubbaal),
#      so QA spellings are folded in as aliases. Exits 1 on any unmatched proper
#      noun; resolve with ALIASES / IGNORES below and re-run.
#   4. pseudonymize_english_source.py -- applies the ONE table to each passage
#      and its QA together, so the expected answers land in the same namespace
#      as the passage the model reads. That is the property the first Tier 1 run
#      lacked.
#
# Then run evaluation/scripts/campaigns/run_tier1_small_models.sh.
#
# Requirements: OPENAI_API_KEY exported (step 1 only). Steps 2-3 are offline.
#
# Knobs:
#   ALIASES=("Canonical=QaSpelling" ...)   force a QA spelling onto an entity
#   IGNORES=("Word" ...)                   candidate that is not a name
#   MODEL=gpt-4.1-mini
#   FORCE_MAP=1                            rebuild step 1 even if the map exists
set -euo pipefail

MAP_DIR="evaluation/datasets/pseudonym_remap"
RAW_MAP="$MAP_DIR/name_map_tier1.json"
AUDITED_MAP="$MAP_DIR/name_map_tier1_audited.json"
SUPPLEMENT="$MAP_DIR/name_map_tier1_supplement.json"
MAP="$MAP_DIR/name_map_tier1_reconciled.json"
PASSAGE_DIR="evaluation/datasets/passages/tier1"
QA_DIR="evaluation/datasets/qa/tier1_QAs_easy"
OUT_PASSAGE_DIR="evaluation/datasets/pseudonymized/passages/tier1"
OUT_QA_DIR="evaluation/datasets/pseudonymized/qa/tier1"
MODEL="${MODEL:-gpt-4.1-mini}"

# Cross-name identities and non-names, resolved against all 11 Tier 1 QA files
# on 2026-08-04. Every entry is a QA spelling that no fuzzy threshold could
# safely reach on its own.
if [[ -z "${ALIASES+x}" ]]; then
  ALIASES=(
    "Jerub-Baal=Gideon"                            # same person, similarity 0.29
    "Beth Millo=Beth"
    "Beth Millo=Millo"
    "Gaal son of Ebed=Ebed"
    "Danites=Dan"                                  # bare "Dan" = the tribe, 48 hits
    "Jews=Jewish"
    "Egyptian kings=Egyptians"
    "Elath=Eloth"                                  # spelling variant
    "Hittite kings=Hittites"
    "Ishbi-Benob=Benob"
    "Ishbi-Benob=Ishbi"
    "Israel (tribe)=Israelites"
    "Mount Gerizim=Gerizim"
    "Roman citizen=Roman"
    "Levite=Gershom"                               # after the SAME_ENTITY fold below
    "Joash=King Joash"
    "Mount Zalmon=Zalmon"
  )
fi
# Titles and religious register, deliberately NOT blinded: the decision is to
# blind which deity/person, not the fact that the text is scripture.
if [[ -z "${IGNORES+x}" ]]; then
  IGNORES=("Mount" "King" "Come" "About" "Give" "Sabbath" "Holy" "Holies")
fi
# One participant the extraction split into two entities. Judges 18:30 reveals
# that "the Levite" of chapters 17-18 is Jonathan son of Gershom; split, the
# expected answer for that item named someone the passage never introduced.
if [[ -z "${SAME_ENTITY+x}" ]]; then
  SAME_ENTITY=("Levite=Jonathan son of Gershom son of Moses")
fi

PAIRS=(
  "t1_judg9:judg_9_1-57.txt"
  "t1_judg17_18:judg_17_1-18_31.txt"
  "t1_2kgs6_7:2kgs_6_24-7_20.txt"
  "t1_1kgs13:1kgs_13_1-34.txt"
  "t1_2kgs11:2kgs_11_1-21.txt"
  "t1_2chr26:2chr_26_1-23.txt"
  "t1_2sam21:2sam_21_15-22.txt"
  "t1_acts19:acts_19_11-20.txt"
  "t1_acts20:acts_20_7-12.txt"
  "t1_acts23:acts_23_12-35.txt"
)

echo "=== 1/4  entity extraction -> $RAW_MAP"
if [[ -f "$RAW_MAP" && "${FORCE_MAP:-0}" != "1" ]]; then
  echo "reuse $RAW_MAP (FORCE_MAP=1 to rebuild)"
else
  : "${OPENAI_API_KEY:?export OPENAI_API_KEY for step 1}"
  python evaluation/scripts/pseudonyms/build_passage_name_map.py \
    --passage-dir "$PASSAGE_DIR" --glob "*.txt" \
    --out "$RAW_MAP" --model "$MODEL" --temperature 0 --report
fi

echo
echo "=== 2/4  audit the generated map -> $AUDITED_MAP"
same_args=()
for spec in ${SAME_ENTITY+"${SAME_ENTITY[@]}"}; do same_args+=(--same-entity "$spec"); done
if ! python evaluation/scripts/pseudonyms/audit_name_map.py \
      --map "$RAW_MAP" --out "$AUDITED_MAP" --report \
      ${same_args+"${same_args[@]}"}; then
  echo "audit reported unresolved problems; not proceeding." >&2
  exit 1
fi

echo
echo "=== 3/4  reconcile QA spellings -> $MAP"
alias_args=()
for spec in ${ALIASES+"${ALIASES[@]}"}; do alias_args+=(--alias "$spec"); done
for word in ${IGNORES+"${IGNORES[@]}"}; do alias_args+=(--ignore "$word"); done
merge_args=()
[[ -f "$SUPPLEMENT" ]] && merge_args+=(--merge "$SUPPLEMENT")

if ! python evaluation/scripts/pseudonyms/reconcile_qa_aliases.py \
      --map "$AUDITED_MAP" ${merge_args+"${merge_args[@]}"} \
      --qa-dir "$QA_DIR" --out "$MAP" \
      --report "${alias_args[@]}"; then
  echo
  echo "Unmatched proper nouns above. Each one would survive into the blinded" >&2
  echo "QA. Add them to ALIASES (a known entity under another name) or IGNORES" >&2
  echo "(not a name), then re-run. Nothing downstream has been written." >&2
  exit 1
fi

echo
echo "=== 4/4  apply to all 10 passage/QA pairs"
mkdir -p "$OUT_PASSAGE_DIR" "$OUT_QA_DIR"
for pair in "${PAIRS[@]}"; do
  pid="${pair%%:*}"
  name="${pair#*:}"
  echo "--- $pid"
  # --passage-id scopes the table: the Tier 1 set has two men called Jonathan,
  # in different passages, and both legitimately keep the bare alias.
  passage_id="${name%.txt}"
  python evaluation/scripts/pseudonyms/pseudonymize_english_source.py \
    --table "$MAP" --passage-id "$passage_id" \
    --passage "$PASSAGE_DIR/$name" \
    --out-passage "$OUT_PASSAGE_DIR/$name"
  python evaluation/scripts/pseudonyms/pseudonymize_english_source.py \
    --table "$MAP" --passage-id "$passage_id" \
    --qa "$QA_DIR/${pid}_all_formats.json" \
    --out-qa "$OUT_QA_DIR/${pid}_all_formats.json"
done

echo
echo "done. Inputs are in:"
echo "  $OUT_PASSAGE_DIR"
echo "  $OUT_QA_DIR"
echo "Any 'LEAKS' line above means a canonical name survived -- fix before running."
echo "Next: bash evaluation/scripts/campaigns/run_tier1_small_models.sh"
