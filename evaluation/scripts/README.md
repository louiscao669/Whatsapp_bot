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

## LLM-generated grammar variants

`variants/current/create_grammar_variants.py` uses an LLM to propose structural
grammar defects, evaluates them with a separate judge call, and builds a cached
bank for nested percentages. The default proposal path has no handwritten noun,
verb, or phrase-matching templates. Each accepted clause keeps the exact same
replacement at every dose.

Dose measures the original content-character count of affected clauses, not
characters edited or a model's grammaticality score. Whole clauses can overshoot
a target. The default maximum bank rate is 30%, even when exporting lower rates.

From the repository root, with `OPENAI_API_KEY` set and the `openai` package
installed, test Judges 17–18 in a separate directory:

```bash
python3 evaluation/scripts/variants/current/create_grammar_variants.py \
  --root evaluation/outputs/tier1_bsb_unblinded_5opt_think \
  --passage-dirs t1_judg17_18 \
  --source-model-dir _base \
  --source-method llm_prompt_high \
  --output-model-dir grammar_llm_test \
  --generator-model gpt-4o-mini \
  --judge-model gpt-4o-mini \
  --bank-rate 30% \
  --rates 0% 30% \
  --allow-shortfall
```

`--allow-shortfall` permits inspection when accepted coverage is below 30%; check
`actual_affected_rate`, `target_met`, and `shortfall_content_chars` in each output's
`grammar_metadata.json`. Without that flag, insufficient coverage fails before
exporting requested variants and retains the bank and completed responses.

The generator receives the clean passage plus batches of eight clean clauses
(`--proposal-batch-size`). It returns up to three alternatives per clause
(`--max-candidates-per-clause`), each with the edited clause, an error type, and
an explanation. It can return an empty list when no suitable defect exists.
Every alternative starts from the clean clause. Every eligible clause can be
sent to the model; generation stops requesting batches once coverage is met.
There is no mechanical fallback. Refusals, truncated output, malformed response
objects, wrong clause IDs, and altered source echoes stop the run.

The model chooses the structural change, but local checks require unchanged
character counts, punctuation/whitespace positions, verse markers, numbers, and
registered protected terms. Added filler, omitted text, substitutions, unchanged
candidates, and duplicates cannot reach the judge. The judge separately checks
that words remain intact, a specific new structural violation exists, the
intended meaning remains recoverable, and the defect is local to the clause.
The generator's explanation is saved for review but is not sent to the judge.
Changing who did what, grammatical topicalization, or merely awkward style must
be rejected. A finite pool of LLM proposals still does not guarantee 30% coverage.

The judge prompt explicitly distinguishes introducing a defect (`yes`) from
judging a sentence correct, and asks for decisions consistent with its explanation.
Cosmetic enclosing quotation marks around an error span can be removed only
when that yields an exact substring of the edited clause. No decision is flipped,
no fuzzy text match is used, and raw responses remain available for audit.

For pseudonymized passages, pass `--protected-terms path/to/name_map.json`
(repeatable). The Tier 1 campaign supplies its `MAP` automatically. Configure the
judge through `--judge-model` or `OPENAI_GRAMMAR_MODEL` (default `gpt-4o-mini`).
The generator defaults to the judge model; override it with `--generator-model`
or `OPENAI_GRAMMAR_GENERATOR_MODEL`. Both models need Chat Completions Structured
Outputs support and account access. There is no automatic model fallback.

The following are saved under `<output-model-dir>/_grammar_bank/`:

- `proposals.json`: complete generation batches, including empty and subsequently
  rejected proposals, keyed by generator model, prompt, schema, context, source
  clauses, seed, protected terms, and requested alternative count.
- `judgments.json`: accepted, rejected, and uncertain evaluations keyed by judge
  model, prompt, schema, context, and exact candidate. Each distinct candidate is
  judged once for those settings.
- `bank_<fingerprint>.json`: approved before/after clauses, generator explanations
  and proposal IDs, judge explanations, fixed selection order, and coverage.
  Counts distinguish generated alternatives (including unused batch results),
  attempted candidates rejected by hard checks, duplicate/no-op candidates, and
  candidates evaluated by the judge.

Both stages checkpoint each completed response. Interrupted runs resume saved
work; a request interrupted before saving its response may need to be resent.
Identical raw and decanonicalized text shares proposals, judgments, and a bank.
Different text is evaluated separately. The first build has generation costs in
addition to judging costs. Lower doses perform neither stage again.

Repeat the command with `--offline` to prohibit all model calls, and change
`--rates` to `0% 5% 10% 15% 20% 30%` to export nested doses. Keep the seed, models,
batch size, and candidate count the same. `--force` rewrites outputs without
clearing either cache. A changed generation setting makes a new proposal request;
it is not guaranteed to produce the same candidates as an earlier configuration.
Increasing the candidate limit does not guarantee higher accepted coverage.

LLM banks use schema version 3 and `edit_style: llm_structural_v1`. Earlier
particle-based or handwritten-template banks are not reused as LLM banks. Use a
new output directory or `--force` when replacing variants. The revised judge
rubric also requires fresh judgments. Existing files and caches are not deleted.
Generating files does not import them into the participant platform.

`--legacy-unvalidated` retains the original independent per-rate mechanical
algorithm without GPT. Model approval is not human verification; review a sample
of a new bank before experimental use. Offline regression tests make no API calls:

```bash
python3 -m pytest evaluation/tests/test_grammar_variants.py -q
```
