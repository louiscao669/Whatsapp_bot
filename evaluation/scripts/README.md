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
| `campaigns/current/run_full_conditions_5opt.sh` | Current | Check and rerun the unblinded full six-dose grid with all three answer models. |
| `campaigns/current/run_hard66_full_ladder.py` | Current | Bind reviewed Hard 66 QA/windows to the repaired six-dose release and run all three models. |
| `campaigns/current/run_tier1_hard_v3.sh` | Current | Translate, verify, refresh, and score Hard-v3. |
| `campaigns/current/smoke_test_bsb_mcqs.py` | Utility | Small BSB MCQ end-to-end validation. |
| `analysis/review_qa_items.py` | Utility | Review final source or translated QAs with separate content validity and language accessibility checks; see [workflow and prompts](../configs/qa_review_v2/README.md). |
| `analysis/rewrite_flagged_qa.py` | Utility | Rewrite flagged question/option wording using review evidence; require repeated preservation and full QA checks before exporting accepted revisions. See [usage](../configs/qa_review_v2/TARGETED_REWRITE.md). |
| `analysis/simplify_qa_items.py` | Utility | Simplify unnecessary setup before compact verification; freeze the intended target and use detailed burden diagnosis only for failures. See [usage and validation](../configs/qa_simplify_v3/README.md). |
| `campaigns/current/rerun_rewritten_qa.py` | Utility | Replay the 16 accepted Gold/Hard rewritten forms across saved model configurations and conditions; publish revised result copies while retaining original runs. |
| `analysis/report_rewritten_qa_models.py` | Utility | Compare the verified rewrite replay against matching saved results; export condition totals, question comparisons, and before/after figures. |

The October 27 rewrite replay uses `--phase prepare`, `--phase run`, and
`--phase publish`. Preparation freezes question translations, exact passage
windows, model settings, and source hashes. Only changed forms are generated;
identical model inputs reuse a response with that reuse recorded. Published
copies preserve all untouched rows. Newly evaluated forms stay separate from
existing full-set totals. The report uses the default dated replay directory.

### Full six-dose rerun

The full five-option grid uses clean once, word-by-word once, and omission,
mistranslation, and structural grammar at 5%, 10%, 15%, 20%, 25%, and 30%:
20 conditions × 10 passages × 3 models = 600 cells. It uses the shared canonical
Gold-72 QA, open and MCQ formats, and Qwen3 thinking by default. The default models
are `llama3.2:1b`, `qwen2.5:1.5b`, and `qwen3:1.7b`.

```bash
# Read-only input check, with no model/API calls:
CHECK_ONLY=1 bash evaluation/scripts/campaigns/current/run_full_conditions_5opt.sh

# Run only after the input check passes:
bash evaluation/scripts/campaigns/current/run_full_conditions_5opt.sh
```

The full runner does not generate variants. It refuses missing levels, duplicate
texts, non-increasing coverage, old mechanical grammar, unvalidated mistranslation
banks, and coverage outside ±2 percentage points (`COVERAGE_TOLERANCE_PP`). Grammar
coverage counts the source characters in affected clauses; mistranslation counts
replaced source spans; omission counts removed clause content. These metrics are
not interchangeable. Input checks are not a replacement for semantic review.
`PREVIEW=1` prints the plan without checking readiness. `PASSAGES` and `MODELS`
can select a subset. A run refreshes all model-cell inputs (including WBW), forces
new answers and downstream scoring, and writes to the selected `OUT_ROOT`.
The separate `run_pilot_conditions_5opt.sh` retains the seven-condition pilot slate.

For the repaired release in `evaluation/runs/full_ladder_2026-10-23`, use the
reviewed canonical Hard 66 question set with:

```bash
python3 evaluation/scripts/campaigns/current/run_hard66_full_ladder.py --prepare-only
python3 -u evaluation/scripts/campaigns/current/run_hard66_full_ladder.py
```

To omit grammar evaluations, add `--exclude-grammar` to either command. This
selects clean, omission and mistranslation at 5–30% in 5-point steps, and
word-by-word: 14 conditions, 420 model/passage/condition cells, and 5,418 responses
across the three models. The full prepared passage release remains available;
the exclusion applies to model evaluation and its completion counts.

The first command makes no model calls. The second runs in the foreground,
resuming its own completed cells and keeping macOS awake while it works.
It uses a separate `evaluation/runs/hard66_full_ladder_2026-10-23` output directory.
The reviewed set excludes one unsupported question and restricts one to MCQ:
65 retained questions (64 open + 65 MCQ forms), giving 7,740 responses across
20 conditions and three models. Every MCQ includes option E, and the explicit
Hard 66 verse windows include review overrides. A window emptied by omission is
extended identically across all conditions, following the pilot's rule, with
extensions recorded in `readiness.json`. All question/window bindings are checked
before answering. Order: clean, omission, mistranslation, grammar, word-by-word.
Qwen3 thinking remains enabled. This command reuses passage texts without generating
new variants, and does not reuse Gold-72 answer results.

## Every-sentence grammar condition

`variants/current/create_every_sentence_grammar.py` creates a separate condition
in which every content-bearing sentence must contain an approved structural
grammar defect. Sentence boundaries use 。！？.!? and closing quotation marks;
sentences crossing verse boundaries are split into fragments, each requiring an
edit. This preserves verse alignment for question windows. The condition is
called `100%` for sentence coverage, **not** character edit distance and not a
continuation of the earlier affected-clause percentage ladder.

```bash
python3 -m dotenv run -- python3 -u evaluation/scripts/variants/current/create_every_sentence_grammar.py \
  --source-root evaluation/runs/grammar_full_5_30_2026-10-24 \
  --output-root evaluation/runs/grammar_every_sentence_2026-10-25 \
  --generator-model gpt-6.1-sol --judge-model gpt-6.1-sol \
  --workers 4 --retry-rounds 4
```

The generator and grammar judge prefer multiple disruptions per sentence but
accept one clear structural error when further disruption would be unsafe or
infeasible. A single edit need not match the severity of a compound edit, even
in a longer sentence. Grammatical awkwardness, isolated function-word moves,
word splitting, and meaning changes remain disallowed. Independent source-blind
meaning checks still apply. This sentence policy is separate from the earlier
clause ladder's compound-or-severe policy, with separate prompt fingerprints;
old judgments are not silently reclassified. A policy change builds a new bank
and preserves historical bank files. Use a new output root when changing policy
for an already exported or currently running experiment.

It caches proposals and judgments, retries only
unapproved units with rejection feedback, and rejects duplicate proposals.
Rerunning resumes cached work; increase `--retry-rounds` to allow additional
rounds. Each passage has `grammar/sentence_review.html` and `.json` containing
every before/after pair, along with `progress.json`. A passage is exported to
`grammar/100%` only when every unit passes. Partial work is saved with a `draft_`
prefix and explicitly reports unresolved sentences. `run_state.json` summarizes
all passages. This command generates passages only; it does not run the answer
models or update pilot data.

To retain all existing approved edits and retry only unresolved sentences after
updating the sentence policy, add `--resume-from <previous-run-root>` and choose
a new `--output-root`. The prior run must have stopped. The retry takes a frozen
snapshot, recovers fully approved edits from cached reviews if the old process
stopped before writing a bank, and preserves their exact replacements and review
provenance. Only unresolved units are proposed and judged under the new policy.
Historical failures are supplied as feedback; severity-only rejects may be
proposed again for fresh judgment. Existing meaning checks still apply, and the
source run is never modified. Rerun the same command to resume the retry itself.

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

## GPT-6 Sol mistranslation banks and independent review

`variants/banks/generate_mistranslation_banks.py` now defaults to `gpt-6-sol` for
both proposing candidates and independently judging each proposed source/target
mapping. The judge receives the clean passage, exact replacement and every matched
occurrence in context, without the generator's rationale. Every criterion must
be `yes`: substantive meaning change, fluent Chinese, substitution rather than
addition/omission, a localized change, and validity at every matched occurrence.
`no` or `uncertain` on any criterion rejects the candidate. Synonym swaps, list
shortening, detail-dropping paraphrases and broken collocations are explicitly
excluded. Negation and number changes can qualify as substitutions.

Generate fresh candidates and judge them for all ten current Tier 1 passages,
with approved-candidate targets based on each passage's length:

```bash
python3 -u evaluation/scripts/variants/banks/generate_mistranslation_banks.py \
  --root evaluation/outputs/tier1_bsb_unblinded_5opt_think \
  --passage-dirs t1_1kgs13 t1_2chr26 t1_2kgs11 t1_2kgs6_7 t1_2sam21 t1_acts19 t1_acts20 t1_acts23 t1_judg17_18 t1_judg9 \
  --source-model-dir _base \
  --generator-model gpt-6-sol \
  --judge-model gpt-6-sol \
  --max-items 80 \
  --target-candidates auto \
  --chars-per-candidate 20 --min-target-candidates 10 \
  --max-refill-rounds 3 \
  --passage-workers 3 --judge-workers 4 \
  --output-name mistranslation_bank_sol_length_zh.json
```

`--passage-workers 3 --judge-workers 4` processes up to three passages at once
and judges up to four candidates concurrently within each active passage, for
at most 12 simultaneous model requests. Each judge request still contains one
candidate and its passage context. Generation and refill rounds remain sequential
within a passage, so every refill uses all preceding judgments and rejection
reasons. Both worker settings default to 1 and accept 1–8. This changes scheduling,
not prompts, approval criteria, or token limits; no asynchronous Batch API job is
submitted.

Completed responses are saved as they arrive, with synchronized writes to the
shared judgment cache. Results are consumed in a stable order so changing worker
counts does not change refill requests or bank identities. Completed calls can be
reused after an API failure or interruption. Independent passage failures do not
discard other passages' work, but the overall command exits nonzero. Avoid running
two separate processes against the same passage cache simultaneously; use these
worker flags in one process. Duplicate or aliased passage paths are rejected.

Add `--dry-run` to preview every passage's content-character count, resolved
target and batch limits without model calls or file writes.

With `--target-candidates auto`, the planning rule is:

```text
approved target = max(min_target_candidates, ceil(content_characters / chars_per_candidate))
initial proposal limit = min(max_items, ceil(1.5 * approved target))
```

The default is one approved mapping per 20 content characters, with a floor of
10. The content-character metric is the same one used by the variant renderer;
punctuation and whitespace do not count. The first batch has 50% headroom for
rejections, subject to `--max-items`. That cap applies to batches, not the total
bank: a long passage can accumulate more approved mappings across refill rounds.
Lower `--chars-per-candidate` to request a denser bank, or adjust
`--min-target-candidates` for very short passages. Numeric `--target-candidates`
keeps the fixed-count behavior and ignores those two automatic-policy settings.
Omitting the target retains the original one-batch behavior.

Current Tier 1 lengths resolve to these targets and initial proposal limits with
the defaults above:

| Passage | Content characters | Approved target | Initial proposal limit |
| --- | ---: | ---: | ---: |
| 1 Kings 13 | 1,180 | 59 | 80 |
| 2 Chronicles 26 | 841 | 43 | 65 |
| 2 Kings 11 | 761 | 39 | 59 |
| 2 Kings 6–7 | 1,236 | 62 | 80 |
| 2 Samuel 21 | 318 | 16 | 24 |
| Acts 19 | 301 | 16 | 24 |
| Acts 20 | 173 | 10 | 15 |
| Acts 23 | 698 | 35 | 53 |
| Judges 17–18 | 1,483 | 75 | 80 |
| Judges 9 | 1,941 | 98 | 80 |

These are configurable planning heuristics, not measured requirements for 30%
coverage. Accepted source spans can overlap, recur, or have different lengths.
Check achieved coverage after rendering. The exact length policy, count, initial
proposal limit and resolved target are recorded in the bank configuration and
audit; different policy settings cannot silently reuse a final bank. Matching
proposal and judgment calls remain reusable from cache.

To seek a minimum of **20 approved mappings** for Acts 20, with at most three
refill batches after the initial batch:

```bash
python3 -u evaluation/scripts/variants/banks/generate_mistranslation_banks.py \
  --root evaluation/outputs/tier1_bsb_unblinded_5opt_think \
  --passage-dirs t1_acts20 \
  --source-model-dir _base \
  --generator-model gpt-6-sol --judge-model gpt-6-sol \
  --max-items 20 --target-candidates 20 --max-refill-rounds 3 \
  --output-name mistranslation_bank_sol_refill_zh.json
```

`--target-candidates` enables refill; without it, generation remains one batch.
The target is an approved **mapping count**, not character coverage, a percentage,
or a guarantee of distinct usable spans. `--max-items` caps each proposal batch.
Each refill requests at most the smaller of that cap and the remaining shortfall.
The entire initial batch is reviewed, so it can exceed a smaller target. Generation
stops once a completed batch meets the target, or after `--max-refill-rounds`
additional batches (default 3; 0 permits only the initial batch).

Refills receive every previously attempted source/target pair, including approved
pairs, with failed criteria, the judge's explanation, and specific deterministic
validation failures for rejected pairs. The generator is instructed to avoid
repeating them. The script also skips exact repeated pairs regardless of mode,
category, rationale, or surrounding whitespace; duplicates are never rejudged.
A new target for a previously used source is allowed. The judge still sees only
the clean passage and that candidate in context, without generator feedback or
other candidates. Approval criteria are unchanged. Empty, rejected, or duplicate
batches consume the round budget; they cannot cause an unbounded loop.

If the budget runs out, a nonempty partial bank is saved with `refill.target_met:
false` and its shortfall, and the command exits **1**, including on reuse of that
partial bank. `validation.status: complete` means all included mappings passed
review; it does not mean the requested count was reached. If none pass, only the
audit and caches are saved. No rejected candidates are added to fill the target.
Increase `--max-refill-rounds` with `--force` (or a new `--output-name`) to extend
the run; prior proposal batches and judgments are reused. Repeating the same
settings does not buy a fresh random attempt. An interrupted run can be resumed
with the same command; completed responses, including refill responses, are
reused. API errors stop the run rather than becoming linguistic rejections.

To judge the **existing mini-generated candidates** without generating new ones:

```bash
python3 -u evaluation/scripts/variants/banks/generate_mistranslation_banks.py \
  --root evaluation/outputs/tier1_bsb_unblinded_5opt_think \
  --passage-dirs t1_1kgs13 t1_2chr26 t1_2kgs11 t1_2kgs6_7 t1_2sam21 t1_acts19 t1_acts20 t1_acts23 t1_judg17_18 t1_judg9 \
  --source-model-dir _base \
  --review-existing-bank-name mistranslation_bank_zh.json \
  --judge-model gpt-6-sol \
  --output-name mistranslation_bank_mini_sol_reviewed_zh.json
```

Review-only mode preserves the original generator's recorded model; a mini bank
reviewed by Sol is not labeled Sol-generated. Input banks are never overwritten
by review-only mode. The new bank files contain only approved candidates. There
is no automatic fallback to unreviewed candidates if few or none pass. Review-only
mode cannot be combined with `--target-candidates`.

Generate passage variants from the fresh reviewed banks:

```bash
python3 evaluation/scripts/variants/current/create_mistranslation_variants.py \
  --root evaluation/outputs/tier1_bsb_unblinded_5opt_think \
  --passage-dirs t1_1kgs13 t1_2chr26 t1_2kgs11 t1_2kgs6_7 t1_2sam21 t1_acts19 t1_acts20 t1_acts23 t1_judg17_18 t1_judg9 \
  --source-model-dir _base \
  --chapter-bank-name mistranslation_bank_sol_length_zh.json \
  --output-model-dir mistranslation_sol_length \
  --rates 0% 5% 10% 15% 20% 30% \
  --require-bank --require-judged-bank
```

Each passage's `_base/_shared/_mistranslation_review/` contains cached proposals,
judgments (including rejections), response token usage and a `review_<hash>.json`
audit with the candidate-level reasons, per-round counts, duplicate attempts and
refill outcome. Refill responses are cached in `refill_proposals.json` with their
exact feedback requests and model identities. Each completed model response is saved
immediately. Interrupted runs reuse completed work. Cache keys include the exact
source/request, model, rubric, schema and output limit. `--offline` prohibits API
calls; `--force` rebuilds the final bank while reusing matching cached responses.
An interrupted response that was never saved may need to be requested again.

The Responses API uses strict structured output, with no explicit temperature
([GPT-6 Sol model reference](https://developers.openai.com/api/docs/models/gpt-6-sol),
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)).
The dedicated defaults can be overridden using `--generator-model`/`--model`,
`--judge-model`, `OPENAI_MISTRANSLATION_GENERATOR_MODEL`, or
`OPENAI_MISTRANSLATION_JUDGE_MODEL`. Generic translation/evaluation model variables
no longer silently change this workflow's model. `--max-items` limits proposals per batch,
not the number that will pass review. A stronger model does not guarantee a
minimum accepted coverage or flawless linguistic judgments.

Reviewed banks are bound to the exact clean text and every approved mapping.
The variant script automatically checks these bindings for schema-2 banks, and
`--require-judged-bank` also refuses legacy/unreviewed banks. If raw and
decanonicalized passages differ, one context-bound bank cannot authorize both;
the script refuses that mismatch. The current unblinded Tier 1 sources are
identical. Existing outputs from other banks are not silently reused.

This review is candidate-level, not a judgment of every combined passage or QA
outcome. Percentage selection remains the existing independent per-rate method,
and coverage still counts matched source-span characters. Review does not make
those rates a measure of semantic severity or make their selections nested.

```bash
python3 -m pytest evaluation/tests/test_mistranslation_validation.py -q
```

### Held-out comparison of mistranslation judge prompts

`analysis/evaluate_mistranslation_judge.py` compares two frozen prompts in
`evaluation/configs/mistranslation_judge_holdout_v1/`. The revised prompt is the
proposed stricter `meaning_changed` rubric; the remaining criteria are identical.
This experiment does not change the production `JUDGE_PROMPT` or candidate banks.

The dataset contains 48 new synthetic Chinese narrative cases: 24 expected
acceptances and 24 expected rejections across 12 families. Passages, substitutions,
labels, reasons and the eight cases selected for repeat testing were fixed before
API calls. The expected labels are assistant-authored, not independently validated
human ground truth. Cases are held out from the prompt examples, not asserted to
be absent from model pretraining. They are a small challenge set, not an estimate
of accuracy over all Bible passages.

```bash
python3 -u evaluation/scripts/analysis/evaluate_mistranslation_judge.py \
  --output-dir evaluation/reports/mistranslation_judge_holdout_2026-10-22 \
  --model gpt-6-sol --workers 4 --repeats 3
```

This schedules 128 responses: 48 cases for each prompt, plus two additional trials
of eight preselected cases for each prompt. Calls use the production request
builder, JSON schema and acceptance gate. Expected labels, reasons and family names
never enter requests. Separate per-trial caches ensure repeats are fresh calls;
rerunning the same command resumes saved responses. `--offline` replays cached
results without API calls, and `--prepare-only` freezes the run without calling a
model. Changed datasets, models or prompts require a new output directory.

The output includes `report.html`, all-case `results.json`, `summary.json`, frozen
dataset/prompt snapshots, a hash manifest, and raw response caches with token usage.
Primary accuracy uses only trial 1, with false acceptance and false rejection rates
reported separately. Repeat disagreement is reported separately; errors are never
counted as model rejections. The predeclared conservative screening gate requires
zero false acceptances, at most one false rejection, and no repeated-case decision
flips. Passing would still require human label review and broader validation.

After inspecting results to tune a prompt, treat this set as development/regression
data and reserve fresh cases for another independent evaluation. This follows the
[OpenAI Docs evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
on task-specific tests, explicit metrics, edge cases and human calibration.

The 2026-10-22 run is summarized in
`evaluation/reports/mistranslation_judge_holdout_2026-10-22/overview.html`.
Its raw primary scores are 46/48 for the baseline and 45/48 for the revised
prompt, with no accepted expected-reject cases for either. The report identifies
three primary reference labels requiring adjudication; do not interpret raw
disagreements as proven judge errors. A separate post-observation diagnostic
fixture, `evaluation/configs/mistranslation_judge_followup_v1/`, adds 13 fresh
challenge/control cases and three clarified-context probes, using unchanged
prompts. Those results and a further disputed fluency label are reported
separately under `followup/`; original labels and results remain intact.

### Conservative judge with structured acceptance gates

`analysis/evaluate_mistranslation_judge_v2.py` tests the next proposed policy using
three arms: the production prompt (`current`), the first revised prompt (`previous`),
and the stricter prompt plus code gates (`conservative`). The experimental contract
is in `variants/banks/mistranslation_conservative_judge.py`; production bank generation
does not import it. Frozen prompts, schemas and cases are in
`evaluation/configs/mistranslation_judge_holdout_v2/`.

The conservative response adds `change_basis`, `change_dimension`,
`difference_evidence` and `needs_repair`. The code rejects vague/equivalent/uncertain
bases, missing evidence, and needed or uncertain repairs, even when the original
five criteria are all `yes`. Scalar changes cannot use the action/referent exception.
These fields are still model judgments; code gates do not establish their truth.

```bash
python3 -u evaluation/scripts/analysis/evaluate_mistranslation_judge_v2.py \
  --output-dir evaluation/reports/mistranslation_judge_conservative_2026-10-22 \
  --model gpt-6-sol --workers 4 --repeats 3
```

This schedules 138 responses: 32 fresh cases (16 positive, 16 negative), six
separately scored known regression/control cases, and three trials of four
preselected fresh cases, for each arm. Fresh source/target pairs are absent from
the earlier evaluation datasets and prompt examples. Labels are assistant-authored
under the stated conservative policy, not human-validated ground truth. Known
examples appearing in prompts are never counted as fresh generalization evidence.
The old awkward frequency example is an explicitly predeclared negative regression
in this version; its original experiment record remains unchanged.

The manifest freezes the dataset, all prompts and schemas, and the acceptance-code
hashes. `--prepare-only` freezes without API calls; `--offline` regenerates reports
from cached responses. Each trial has an independent response cache. The report
contains raw judgments, rejection reasons, source-context evidence, token usage,
fresh/regression confusion matrices and repeat consistency. It also records whether
an extra gate overrode otherwise approving criteria, without claiming that an
observed improvement comes from one particular component of the combined change.

## LLM-generated grammar variants

`variants/current/create_grammar_variants.py` uses an LLM to propose structural
grammar defects, evaluates them with a separate judge call, and builds a cached
bank for nested percentages. The default proposal path has no handwritten noun,
verb, or phrase-matching templates. Each accepted clause keeps the exact same
replacement at every dose.

Dose measures the original content-character count of affected clauses, not
characters edited or a model's grammaticality score. Whole clauses prevent some
exact percentages. Both grammar CLIs now select distinct nested subsets jointly,
within `--coverage-tolerance-pp` percentage points of each target (default ±2).
The closest feasible lower level takes priority, with backtracking when needed
to fit later levels. Undershoot is allowed within this tolerance. The default
maximum bank rate is 30%; use `--bank-rate 60%` for a ladder through 60%.

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
For this explicit shortfall export, the old prefix selection is used; distinct
levels and the coverage tolerance are not guaranteed. Normal planned exports
record actual coverage and `within_tolerance` in `dose_selection.json`.
Per-file `target_met` still means the nominal rounded character target was
reached; a planned slight undershoot can have `target_met=false` while remaining
within tolerance. This also applies to the highest requested rate: for example,
a bank covering 58.9% can export a nominal 60% condition at ±2 points, provided
the planner finds a complete distinct nested ladder. The bank's nominal build
target remains recorded as unmet; it is not relabeled as exactly 60%.

The generator receives the clean passage plus batches of eight clean clauses
(`--proposal-batch-size`). It returns up to three alternatives per clause
(`--max-candidates-per-clause`), each with the edited clause, an error type, and
an explanation. It can return an empty list when no suitable defect exists.
Every alternative starts from the clean clause. Every eligible clause can be
sent to the model; generation stops requesting batches once coverage is met.
If the first pass falls short, `--retry-rounds` adds bounded proposal rounds
(default 2, with 0 disabling retries). Only clauses without an approved edit are
retried. Requests include previous candidates and the actual grammar/meaning
rejection evidence, or the fact that no candidate was proposed. They ask for
different rearrangements under exactly the same quality and meaning rules.
Duplicates across rounds are skipped before judging. Approved replacements are
never regenerated or replaced. Responses and both meaning stages remain cached,
so interruptions resume completed work without repeating model calls.

The retry number is an absolute budget after the first pass: repeating an
exhausted `--retry-rounds 2` run reuses its results; increasing it to 4 permits two
more rounds. A larger budget does not guarantee sufficient acceptable edits.
Existing single-pass banks can be extended with the default retries. The old
whole-script hash does not invalidate approvals for this code-only update;
source, seed, models, prompts, schemas and protection settings must still match.
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

Grammar-approved candidates now also require `source_blind_reading_v1` meaning
review. First, a separate reader sees the candidate inserted into its passage,
without the original clause, the generator's rationale, or the grammar verdict.
It records participant roles, event meaning, modifier scope, and plausible
alternative interpretations. A second call compares this saved reading with the
source. Changed roles, direction versus continuation, ownership, negation,
quantities, or other semantic scope must fail. An ambiguous/unrecoverable reading,
any alternative reading, any `no`/`uncertain` comparison, or any identified risk
span vetoes acceptance. The source-aware comparison cannot override the reader's
ambiguity by reconstructing the intended original.

Alternative readings must be natural and supported by the edited context,
including quoted speech. The reader preserves ordinary lexical units rather
than inventing ambiguity through character resegmentation: in an oath context,
`说起誓` naturally retains `起誓`, so hypothetical `说起 + 誓` is insufficient
grounds for rejection. This does not automatically approve the whole clause.
Unchanged pronoun uncertainty is also not treated as an introduced meaning
change. Updated prompt fingerprints require fresh readings and comparisons.

For example, `作战下去` may mean continuing to fight instead of going down to
fight; inserting `杀了` before an original actor's `儿子` may make that son read
as the victim. These are general semantic criteria, not forbidden phrase lists.
The generator is instructed to avoid these risks and try another rearrangement.
This additional review uses the configured judge model in two separate requests
per previously unseen grammar-approved candidate. It is a conservative model
check, not a proof of semantic equivalence. Strong corruption may therefore
produce fewer accepted clauses; the normal coverage/shortfall rules still apply.

The current `compound_or_severe_v2` rearrangement policy targets two or more
rearrangements within each selected clause. Intact phrases and whole lexical
words (including adverbs and verbs) can move, and the judge assesses the combined
result. A single move remains acceptable when it already creates a comparably
substantial break, such as `拿重三百舍客勒的着一根铜矛`. Merely moving the
opponent phrase to produce `非利士人再次争战与以色列` is too mild; the stronger
target is an order such as `非利士人与以色列争战再次`. The prompts also illustrate
combining `向他` displacement with `起誓`/`说` reordering. These are severity
examples, not templates or a deterministic minimum edit distance.

Function-word-only sprinkling, split lexical words, cancelling moves, grammatical
reorderings, and changes in participant roles still fail. The generator explains
all movements; the judge independently identifies the broken constructions and
rejects mild candidates using `structural_error=no`, even if
`grammar_worsened=yes`. These remain model-based linguistic criteria, not a
deterministic phrase parser or a measured comprehension score.

New banks and per-file export metadata record `rearrangement_policy`. The existing
`operations` marker and `operation_count` count complete clause replacements,
each of which may contain several movements; they do not count linguistic moves.
Character-weighted dose and nested selection are unchanged. Prompt fingerprints
prevent reuse of old proposals, judgments, and banks for newly generated runs.
Previously saved banks can still be replayed under their recorded judgments;
existing exports are not retroactively revised or labeled with the new policy.
New banks also record `meaning_policy`, reviewer fingerprints, and each entry's
`meaning_review` and `meaning_review_id`; applying a new bank requires the saved
meaning approval. Old banks lack this gate and must be regenerated to obtain it.
For a fresh run, use a new output folder such as `grammar_meaning_test` with the
same command options; no extra enabling flag is needed.

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
- `meaning_readings.json`: readings of the edited passage without the source,
  checkpointed before comparison so interrupted comparisons can resume.
- `meaning_judgments.json`: complete semantic reviews, including rejections,
  keyed by both prompts/schemas, the model, and the exact source/edit/context.
  Both meaning caches support offline reuse and candidate-pool cache transfer.
- `bank_<fingerprint>.json`: approved before/after clauses, generator explanations
  and proposal IDs, judge explanations, fixed selection order, and coverage.
  Counts distinguish generated alternatives (including unused batch results),
  attempted candidates rejected by hard checks, duplicate/no-op candidates, and
  candidates evaluated by the judge.
  `retry_rounds_attempted` records the highest retry round started. Approved
  entries remain in append order; rendering selects nested subsets of this pool.

Both stages checkpoint each completed response. Interrupted runs resume saved
work; a request interrupted before saving its response may need to be resent.
Each API attempt has a 300-second timeout, with up to two SDK retries for
transient connection, timeout, rate-limit, or server errors. These transport
retries are separate from `--retry-rounds`, which proposes new edits for clauses
without an approval. Neither kind of retry relaxes the validation criteria.
Identical raw and decanonicalized text shares proposals, judgments, and a bank.
Different text is evaluated separately. The first build has generation costs in
addition to judging costs. Lower doses perform neither stage again.

Repeat the command with `--offline` to prohibit all model calls, and change
`--rates` to `0% 5% 10% 15% 20% 30%` to export nested doses. Keep the seed, models,
batch size, and candidate count the same. `--force` rewrites outputs without
clearing either cache. A changed generation setting makes a new proposal request;
it is not guaranteed to produce the same candidates as an earlier configuration.
Increasing the candidate limit does not guarantee higher accepted coverage.

The standard script treats existing exported rates as exact anchors: their
edited text and chosen clauses stay unchanged while missing rates are fitted
around them. Bank-extension/selection metadata can be refreshed without changing
the text. If a saved rate lies outside the requested tolerance or prevents a
nested ladder, the script fails explicitly; `--force` opts into replanning those
outputs. All approved bank edits are retained even if a particular rate uses
only a subset. If no feasible ladder exists, no new variants are exported.

For the existing 2 Samuel 21 test, rerun the same command with:

```bash
--rates 0% 10% 20% 30% 40% 50% 60% \
--bank-rate 60% \
--retry-rounds 2 \
--coverage-tolerance-pp 2
```

The last two options are defaults. Keep `--output-model-dir
grammar_meaning_calibrated_test` to reuse its 11 approved edits and preserve the
exported 30% passage. An offline check of that saved pool fits the lower ladder
at approximately 9.9%, 19.2%, 31.1%, and 39.7%, replacing the old 27.2% overshoot
for the nominal 20% condition. Reaching 50% and 60% still requires new approvals.

### Promoting reviewed variants to the pilot and its LLM inputs

`human_pilot/operations/promote_reviewed_variants.py` promotes the reviewed
`grammar_sol_phrase_test/30%` and curated `mistranslation_sol_length/{15%,30%}`
texts to the standard pilot paths in `tier1_bsb_unblinded_5opt_think`. It updates
existing model-cell passage inputs and archives their obsolete answers and
scores. It refreshes passage/verse rows for both Gold72 and Hard66, plus unfinished
test assignments and unpresented study assignments. Completed responses and
already-presented study snapshots are preserved. QA and window definitions are
not changed. The operation does not launch LLM evaluations.

Prepare an offline release, then apply that exact staged release:

```bash
python3 human_pilot/operations/promote_reviewed_variants.py prepare \
  --release-dir evaluation/reports/pilot_variant_release_2026-10-23
python3 human_pilot/operations/promote_reviewed_variants.py apply \
  --release-dir evaluation/reports/pilot_variant_release_2026-10-23
```

Use a new release directory for later promotions. The manifest records source
hashes, bank identities, nominal conditions, actual coverage, and destinations;
apply refuses if an input or destination changed after preparation. Original
files/results and database texts are backed up in that release directory. This
does not fill coverage shortfalls. The pilot campaign always refreshes model
inputs (`REPLACE_INPUTS=1`) before answering.

### Expanding the approved pool for distinct nested levels

`variants/current/create_grammar_candidate_variants.py` separates the approved
candidate pool from the edits selected for the final passages. Use it when a few
large clauses make percentage levels identical. `--target-candidates N` requests
at least **N approved edits on different clauses in total**, including reused
approvals. It does not request N additional edits or count alternative proposals
for the same clause. Generation continues until both this count and the highest
requested rate's coverage are available, or every eligible clause has been tried.
The same bounded retries apply to this script; the approval criteria are unchanged.

For Acts 20, start with eight approved clauses and reuse the existing Sol caches:

```bash
python3 -u evaluation/scripts/variants/current/create_grammar_candidate_variants.py \
  --root evaluation/outputs/tier1_bsb_unblinded_5opt_think \
  --passage-dirs t1_acts20 \
  --source-model-dir _base \
  --source-method llm_prompt_high \
  --reuse-cache-model-dir grammar_sol_phrase_test \
  --output-model-dir grammar_sol_nested_test \
  --generator-model gpt-6.1-sol \
  --judge-model gpt-6.1-sol \
  --target-candidates 8 \
  --rates 0% 5% 10% 15% 20% 30% \
  --coverage-tolerance-pp 2
```

The script copies and merges cached proposals and judgments into the new output
directory. It does not modify the source experiment. Keep the source passage,
seed, models, prompts, protected terms, batch size and alternatives per clause
unchanged to reuse the corresponding responses. Increasing `--target-candidates`
alone does not change a model request's identity. Each source text has its own
count target; identical raw/decanonicalized sources share all work.

Selection searches the approved pool jointly across the requested levels. Each
positive level must add at least one clause, retain every lower-level edit, and
stay within `--coverage-tolerance-pp` percentage points of its nominal rate
(default ±2 points). Undershoot is allowed. It prefers the closest feasible lower
level first and backtracks if that choice blocks a later level; this is not a
minimum-total-error objective across all levels. Whole-clause sizes still prevent
some exact percentages. The bank can cover more than 30%; surplus approvals can
be left out of the final 30% passage. Its text may consequently change from the
old four-edit version.

If the requested count or a complete selection cannot be achieved, the script
fails before exporting variants and retains completed caches and banks. After a
selection failure, increase `--target-candidates` and rerun in the same output
directory; prior proposals and judgments are reused. If all eligible clauses
have been tried, increasing the count alone cannot help. The selection search
has a work limit and reports explicitly if it reaches that limit. It never
silently exports duplicated levels or widens the requested tolerance.

`dose_selection.json` records pool size, pool coverage, selected bank/clause
indices, and actual coverage at every level. Each variant retains its complete
before/after evidence in `grammar_metadata.json`. Its existing `target_met` field
still means coverage reached the nominal character threshold; a valid planned
undershoot may have `target_met: false`. Use `within_tolerance` in the selection
report to check the new acceptance rule. Use `--offline` for cache-only replay;
use `--force` to replace exports after intentionally changing the selection.

LLM banks use schema version 3 and `edit_style: llm_structural_v1`. Earlier
particle-based or handwritten-template banks are not reused as LLM banks. Use a
new output directory or `--force` when replacing variants. The revised judge
rubric also requires fresh judgments. Existing files and caches are not deleted.
Generating files does not import them into the participant platform.

`--legacy-unvalidated` retains the original independent per-rate mechanical
algorithm without GPT. Model approval is not human verification; review a sample
of a new bank before experimental use. Offline regression tests make no API calls:

```bash
python3 -m pytest evaluation/tests/test_grammar_variants.py evaluation/tests/test_grammar_candidate_variants.py evaluation/tests/test_grammar_meaning.py -q
```
