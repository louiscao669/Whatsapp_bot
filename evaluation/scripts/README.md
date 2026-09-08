# Evaluation scripts

Run commands from the repository root unless a script says otherwise. The
folders distinguish production workflow from optional utilities and retained
legacy experiments.

## Status guide

- **Current**: part of the Tier 1, BSB, or Hard-v3 workflow.
- **Utility**: manually run preparation, maintenance, or diagnostic tool.
- **Legacy**: retained to reproduce the completed Luke experiments; not called
  by current Tier 1 campaigns.
- **Library**: imported by another script rather than normally launched itself.

## Current entry points

| Script | Status | Purpose |
|---|---|---|
| `campaigns/current/build_tier1_pseudonymized.sh` | Current | Build aligned pseudonymized Tier 1 passages and QA. |
| `campaigns/current/run_tier1_small_models.sh` | Current | Build shared translations and run the clean small-model cells. |
| `campaigns/current/build_tier1_defect_variants.sh` | Current | Build Tier 1 defect ladders from one shared translation. |
| `campaigns/current/run_tier1_defect_models.sh` | Current | Answer and score selected defect cells. |
| `campaigns/current/run_tier1_wbw_models.sh` | Current | Run the Tier 1 word-by-word baseline. |
| `campaigns/current/run_tier1_hard_v3.sh` | Current | Translate, verify, refresh, and score Hard-v3. |
| `campaigns/current/smoke_test_bsb_mcqs.py` | Utility | Small BSB MCQ end-to-end validation. |

## Pipeline libraries

| Script | Status | Purpose |
|---|---|---|
| `pipeline/translate_qa.py` | Current library | Normalize and translate QA; enforce the bilingual pseudonym glossary. |
| `pipeline/decanonicalize.py` | Current library | Canonicalization mappings and protected-token cleanup. |
| `pipeline/apply_qa_corrections.py` | Current utility | Apply reviewed Chinese QA corrections to generated artifacts. |

These modules are used by `evaluation/main.py` and current campaign scripts.

## Data preparation

### Tier 1

| Script | Status | Purpose |
|---|---|---|
| `data_prep/tier1/clean_tier1_qa.py` | Utility | Repair duplicate IDs, collisions, and missing references. |
| `data_prep/tier1/import_tier1_gold_qa.py` | Utility | Import reviewed Gold-72 items missing from the canonical QA set. |
| `data_prep/tier1/export_tier1_gold_qa_subset.py` | Utility | Export exactly the selected Gold-72 QA and windows. |
| `data_prep/tier1/refresh_tier1_defect_variant_qa.py` | Current utility | Copy refreshed base QA into existing defect variants. |

### Sources

| Script | Status | Purpose |
|---|---|---|
| `data_prep/sources/fetch_biblegateway_passage.py` | Utility | Fetch source passages; translation/version must be selected explicitly. |
| `data_prep/sources/bible_csv_to_parallel_json.py` | Utility | Convert Bible CSV data into parallel JSON. |
| `data_prep/sources/tag_passage_headers.py` | Utility | Tag headings so they do not enter verse windows as content. |

### Maintenance and legacy

| Script | Status | Purpose |
|---|---|---|
| `data_prep/maintenance/restore_tier1_clean_after_wrong_root.py` | Maintenance | One-off recovery tool for incorrectly rooted Tier 1 artifacts. |
| `data_prep/legacy/prepare_protected_qa.py` | Legacy | Build old `__PERSON_A__`-style protected-token QA. |
| `data_prep/legacy/fetch_cuv_reference.py` | Legacy | Fetch references for the older Luke/CUV workflow. |

## Analysis

- `analysis/utils/`: reusable score-summary utilities.
- `analysis/diagnostics/`: judge variance, replicate variance, transliteration,
  and thinking-trace investigations. These never run automatically.
- `analysis/legacy_luke/`: Luke answer-model comparisons, Window3 sensitivity,
  canary, separability, and omission-only analyses.

## Campaign maintenance and legacy

- `campaigns/maintenance/`: safe refresh, reseeding, and follow-up helpers.
- `campaigns/legacy_luke/`: completed Luke campaign entry points retained for
  reproducibility, including the core-claim rescoring campaign.

## MCQ tools

No script under `mcq/` runs automatically in the current Tier 1 campaigns.

- `mcq/preparation/`: build and audit rewritten distractors.
- `mcq/diagnostics/`: closed-book, A/B, and raw-output investigations.
- `mcq/maintenance/`: repair missing choices, selectively rerun them, and
  rescore existing files.
- `mcq/legacy_luke/`: old Luke MCQ orchestration and scoring corrections.

The participant importer reads the committed
`evaluation/datasets/mcq/mcq_rewrites.json`; it does not automatically execute
`mcq/preparation/build_rewrites_v2.py`.

## Other folders

- `variants/current/`: active omission, mistranslation, grammar, awkward-style,
  addition, and inconsistency generators.
- `variants/banks/`: passage-specific mistranslation, awkward-style, and
  placeholder-inconsistency bank builders.
- `variants/legacy_luke/`: local inconsistency, untranslated-text, and
  backcanonicalization tools retained for Luke reproducibility.
- `variants/maintenance/`: one-time source patch and migration utilities.
- `pseudonyms/current/`: the active Tier 1 entity-map audit, QA-alias
  reconciliation, and pre-translation pseudonymization workflow.
- `pseudonyms/supporting/`: generation of the reusable Luke-derived English
  pseudonym table.
- `pseudonyms/legacy_luke/`: the older post-translation placeholder-to-pseudonym
  remapping workflow.
- `scoring/current/`: live passage-translation methods, answer
  back-translation, and QA scoring used by `evaluation/main.py`.
- `scoring/metrics/`: optional MQM and CometKiwi translation metrics.
- `scoring/legacy_luke/`: the incremental Luke subset answer-and-score runner.
- `reporting/`: report and visualization generation.
- `archive/superseded/`: superseded source retained temporarily for provenance.
- `_common.py`: shared utilities used across script groups.

## Common commands

Import missing Gold-72 artifacts:

```bash
python3 evaluation/scripts/data_prep/tier1/import_tier1_gold_qa.py --dry-run
python3 evaluation/scripts/data_prep/tier1/import_tier1_gold_qa.py
```

Fetch passages listed in the Tier 1 CSV:

```bash
python evaluation/scripts/data_prep/sources/fetch_biblegateway_passage.py \
  --csv evaluation/datasets/obscure_narrative_passages_tier1.csv
```

Existing passage files are skipped unless `--force` is supplied.
