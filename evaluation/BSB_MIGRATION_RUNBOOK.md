# NIV to Berean Standard Bible migration runbook

Scope: rebuild the Tier-1 English-to-Chinese evaluation materials with the
Berean Standard Bible (BSB) as the English source while retaining the existing
entity-to-pseudonym assignments.

This is a dependency-ordered runbook, not a command to overwrite the current
NIV artifacts. Build into a new staging/output namespace first. Promote the BSB
artifacts only after every gate passes.

## Definition of done

- All 10 Tier-1 passage references are fetched from BSB and preserve usable
  verse boundaries.
- QA selection and verse windows are rebuilt against the BSB wording.
- Existing English and Chinese pseudonyms are reused for the same entities;
  no canonical entity names leak into participant-facing files.
- Chinese clean translations are regenerated once per passage.
- All configured defect variants are regenerated from those new clean bases.
- The agreed 94-item MCQ manifest passes structural, English answerability,
  Chinese answerability, and delivery checks.
- BSB artifacts and reports are promoted atomically; no NIV/BSB mixture remains.

## Gate 0: freeze scope and baseline

Do this before changing passage files.

1. Export a manifest of the 94 MCQs with, at minimum:
   `content_id`, passage ID, reference, question, choices A-D, correct choice,
   and current selected verse window.
2. Record checksums for the current English passages, QA JSON, pseudonym map,
   window map, clean Chinese passages, and defect banks.
3. Create a BSB staging namespace, for example:
   `evaluation/datasets/passages/tier1_bsb` and
   `evaluation/outputs/tier1_bsb`.
4. Record the Bible version as `BSB` in the run metadata. Do not rely on a
   directory name alone.

**Stop condition:** the repository currently does not identify a 94-item set:
the 10 canonical Tier-1 QA files contain 90 records, the curated window map has
110 records, and the current pilot selector yields 78 unique windows. Resolve
the 94 IDs and commit/freeze that manifest before continuing.

## Gate 1: re-fetch the 10 passages from BSB

Fetch into staging, never directly over the NIV files:

```bash
python evaluation/scripts/data_prep/fetch_biblegateway_passage.py \
  --csv evaluation/datasets/obscure_narrative_passages_tier1.csv \
  --version BSB \
  --out-dir evaluation/datasets/passages/tier1_bsb
```

Validate:

- 10 expected files exist and are non-empty.
- Each requested first and last verse is present.
- Cross-chapter references retain chapter-qualified verse labels.
- Section headings and footnote markers do not enter verse text as content.
- A diff report against NIV exists for every passage.

**Output:** staged BSB source passages plus a fetch/verse-integrity report.

## Gate 2: re-run QA selection against BSB wording

Keep stable `content_id` values. Re-evaluate content, not identity.

1. Check every candidate question and gold answer against BSB.
2. Re-annotate the minimal answer-bearing span where BSB moves or rephrases the
   evidence.
3. Rebuild the randomized three-verse windows.
4. Re-run the one-question-per-window selection and pilot partition.
5. Persist the chosen/not-chosen decisions and produce an old-versus-new report.

Relevant entry points:

```bash
python QA_algorithm/scripts/anchor_irt/build_tier1_verse_windows.py --self-test
python QA_algorithm/scripts/anchor_irt/build_tier1_verse_windows.py \
  --qa-root <BSB-aware-QA-root> \
  --spans QA_algorithm/inputs/tier1_required_spans_bsb.json \
  --out QA_algorithm/inputs/tier1_qa_verse_windows_bsb.json \
  --repojustrt-missing QA_algorithm/inputs/tier1_spans_bsb_TODO.json \
  --seed 20260803
python scripts/build_tier1_pilot_partition.py \
  --windows QA_algorithm/inputs/tier1_qa_verse_windows_bsb.json \
  --out evaluation/datasets/tier1_pilot_partition_bsb.json
```

Do not point the existing production metadata writers at the BSB files until
the staging report is approved; their defaults target the current NIV paths.

**Stop condition:** any selected MCQ lacks a complete answer-bearing span, has
more than one defensible correct option, or has no defensible correct option.

## Gate 3: mechanically re-apply English pseudonymization

Reuse `evaluation/datasets/pseudonym_remap/name_map_tier1_reconciled.json` as
the identity-to-pseudonym authority. Do not regenerate pseudonyms.

For each passage/QA pair, run
`evaluation/scripts/pseudonyms/pseudonymize_english_source.py` with the existing
map and the correct `--passage-id`, writing to a BSB staging directory.

BSB may spell an existing entity differently from NIV. Add that spelling as an
alias of the existing entity; do not mint a new pseudonym. Then rerun until:

- every expected canonical name is replaced in both passage and QA;
- question, choices, correct answer, and passage use the same pseudonym;
- the leak scan is empty;
- no generic word or pronoun is accidentally replaced.

**Output:** pseudonymized BSB English passages and QA, using the old pseudonyms.

## Gate 4: re-translate the clean passages and QA to Chinese

Translate each passage exactly once and share that base across answer models and
defect conditions. Use a new output root, for example:

```bash
OUT_ROOT=evaluation/outputs/tier1_bsb \
  STOP_AFTER=decanonicalize \
  bash evaluation/scripts/campaigns/run_tier1_small_models.sh
```

The campaign currently has hardcoded Tier-1 input directories, so either stage
the BSB inputs at those expected paths during a controlled promotion or add
input-directory knobs before running. Do not let it silently read NIV inputs.

Validate:

- all 10 base translations exist;
- all models/conditions share the same clean Chinese base per passage;
- QA questions and A-D choices are Chinese while scoring keys remain intact;
- pseudonyms are consistent and the Chinese leak scan is empty;
- verse labels still map to the BSB window metadata.

## Gate 5: regenerate defect variants

Build every variant from the new BSB-derived Chinese clean base:

```bash
OUT_ROOT=evaluation/outputs/tier1_bsb \
  bash evaluation/scripts/campaigns/build_tier1_defect_variants.sh
```

Regenerate passage-specific mistranslation and awkward-style banks. Do not
reuse banks derived from NIV Chinese wording. Confirm all expected passage ×
defect × rate cells exist, contain a non-empty passage, retain the same QA set,
and differ from the clean base at non-zero rates.

## Gate 6: verify the 94 MCQs

Verification is per manifest ID, not just an aggregate accuracy number.

### 6A. Structural checks (must be 94/94)

- ID is present exactly once.
- Passage and verse window exist.
- Question is non-empty.
- Choices are exactly A-D, non-empty, and distinct after normalization.
- Correct-choice label resolves to one displayed choice.
- English and Chinese files preserve the same ID and correct-choice label.
- The item is deliverable through the importer/runtime without whole-passage
  fallback or a missing verse.

### 6B. English semantic checks (must be 94 adjudicated)

Using only the BSB window, independently answer each item and classify it:

- `pass`: one choice is clearly supported and it is the keyed choice;
- `rewrite`: the keyed fact remains true but the question/choice wording no
  longer fits BSB;
- `rekey`: a different existing choice is uniquely correct;
- `retire`: BSB makes the item ambiguous or unsupported.

Require deterministic agreement plus manual review for every non-pass and every
model disagreement. Never repair an item by changing only the key without
recording the rationale.

### 6C. Chinese clean-baseline checks

Run the answer models only on the clean BSB Chinese base first. For every miss,
distinguish translation failure, pseudonym mismatch, bad verse window, choice
translation problem, and genuinely difficult item. Defect variants are not a
valid baseline for this gate.

### 6D. Delivery regression

Run:

```bash
python scripts/test_tier1_pilot_windows.py
python scripts/test_verify_experiment_delivery.py
python scripts/verify_experiment_delivery.py
```

Also assert that the runtime-delivered set equals the frozen 94-ID manifest.
The existing tests assert the current 90/78 NIV-derived counts, so those
expectations must be deliberately updated only after the BSB selection is
approved.

**Output:** a 94-row verification report with status, evidence window, old/new
key, action taken, reviewer, and final disposition.

## Gate 7: promote and archive

Promote only after Gates 0-6 pass.

1. Archive the NIV manifest and checksums.
2. Move the approved BSB passage, window, pseudonymized, Chinese, bank, and
   variant artifacts into the production paths in one reviewed change.
3. Update documentation and dataset metadata from NIV to BSB.
4. Re-run the complete test suite and delivery verifier from production paths.
5. Keep the BSB verification report with the dataset for auditability.

## Recommended execution order

`94-ID manifest` → `BSB fetch` → `BSB QA/span review` → `window selection` →
`English pseudonymization` → `clean Chinese translation` → `clean MCQ check` →
`defect banks and variants` → `delivery regression` → `promotion`.

