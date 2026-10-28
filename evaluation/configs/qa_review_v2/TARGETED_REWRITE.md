# Targeted rewriting after QA review

`evaluation/scripts/analysis/rewrite_flagged_qa.py` connects completed v2 reviews
to a separate, bounded rewrite-and-recheck workflow. It handles English Gold and
Chinese Hard items in their existing language, including full MCQ options.
It does not run the older shortening or anchor-substitution functions.

## Contract

1. Read `cases.json`, `results.json`, `id_map.json`, and `manifest.json` from each review directory.
   Verify that the reviews match the exact input and current review criteria.
2. Select forms whose language status is `REWRITE` in every completed baseline
   repeat, with at least two repeats. Include a form even when a content hold takes
   precedence in its overall decision. `--include-single-pass` also selects forms
   flagged in only some baseline repeats. Incomplete reviews are never selected.
3. Send the writer the exact item, clean passage, original source metadata, and
   specific content/structure/burden evidence. The prompt targets those issues,
   rather than imposing a word limit or asking for generic simplification.
4. Allow edits to the question and option text only. The expected answer, key,
   passage, form, ID, explicit target, option labels, and option order stay fixed.
   A model may decline when faithful wording repair is not possible.
5. For each candidate, run two separate verification passes by default. Each has:
   - An edit-preservation comparison: same target, same displayed language, and
     equivalent meaning for **every** labeled option, including distractors.
   - The existing content-validity, structural-inspection, and burden checks.
6. Accept only if **every** preservation judgment passes and the existing reviewer
   returns `KEEP` in both passes. Uncertainty, a content hold, residual burden, or
   disagreement cannot be overridden by a fluent-looking rewrite.
7. Otherwise, feed the specific failures to the writer for one further attempt
   by default. Every attempt stays bound to the original input, never to the
   potentially drifted meaning of a previous proposal. Stop after the configured
   attempt limit. Unchanged or repeated wording does not receive another chance
   to pass through judge variability.

The edit-preservation comparison has a specific purpose: the existing content
judge checks whether the final options work, but cannot establish that an edited
distractor means the same thing as its original. An equally false new distractor
is not an equivalent paraphrase. The extra comparison also checks language
preservation and the original question's full semantic scope.

The post-rewrite judges do not see the writer's rationale, earlier failure scores,
or previous attempts. They receive the final item and source metadata needed to
evaluate it. Inferred targets are not silently promoted to explicit design targets.

## Prepare the current Gold and Hard queue without model calls

From `/Users/louiscao/whatsapp-bot/eten-whatsapp-bot`:

```bash
python3 evaluation/scripts/analysis/rewrite_flagged_qa.py \
  --review-dir evaluation/reports/qa_review_v2_full_2026-10-27/gold \
  --review-dir evaluation/reports/qa_review_v2_full_2026-10-27/hard \
  --output-dir evaluation/reports/qa_targeted_rewrite_2026-10-27 \
  --prepare-only
```

This selects **35 forms: 11 Gold and 24 Hard**. Adding `--include-single-pass`
selects 48 forms; use a different output directory for that selection.

## Run targeted rewriting

Use the same command without `--prepare-only`, supplying the configured API key
through the environment or `--env-file`:

```bash
python3 evaluation/scripts/analysis/rewrite_flagged_qa.py \
  --review-dir evaluation/reports/qa_review_v2_full_2026-10-27/gold \
  --review-dir evaluation/reports/qa_review_v2_full_2026-10-27/hard \
  --output-dir evaluation/reports/qa_targeted_rewrite_2026-10-27 \
  --env-file '/Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo/qa_generation/.env'
```

The writer and judge default to the review configuration's `gpt-6.1-sol`.
Override them with `--writer-model` and `--judge-model`. Defaults are two attempts,
two verification repeats, and two concurrent items. Each fully checked attempt
uses one writer call plus eight verification calls, before any transport or
invalid-response retries. Declined and unchanged proposals need no verification
calls. This is intentionally a bounded process, not an indefinite retry-until-pass
loop.

For a small sample, use `--limit 2` or repeat `--id` for exact form IDs, with a
separate output directory. For example:

```bash
python3 evaluation/scripts/analysis/rewrite_flagged_qa.py \
  --review-dir evaluation/reports/qa_review_v2_full_2026-10-27/gold \
  --output-dir evaluation/reports/qa_targeted_rewrite_sample \
  --id gold:t1_1kgs13:o8ae:open \
  --id gold:t1_2kgs6_7:pb1x:open \
  --env-file '/Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo/qa_generation/.env'
```

Requested IDs must meet the selection policy; an unknown or ineligible ID is an
error rather than a silently empty run. `--review-repeats` must be at least two.
`--max-attempts`, `--workers`, and `--limit` must be positive.

## Results and resuming

- `selection.json`: selection reason for every input form.
- `selected_inputs.json`: frozen original items and baseline evidence.
- `items/item_NNNN/attempt_N/`: cached model responses for each attempt and repeat.
- `results.json`: every item, proposal, decision, and review, including failures.
- `accepted_cases.json`: **only** candidates that passed every check, in the
  existing review-input format. This is a separate file, not a dataset promotion.
- `summary.json`: counts of accepted, unresolved, declined, and error outcomes.
- `report.md`: readable before/after wording, option changes, and evidence.

Rerun the exact command to resume from matching response caches. Fingerprints bind
inputs, models, prompts, review code, schemas, and settings; changed criteria require
a new output directory. The output must be separate from the source review
directories, and an unrelated nonempty directory is rejected. Original datasets
and baseline reviews are never overwritten.

Malformed or missing judgments and API errors do not produce an acceptance. Errors
are recorded, and the command exits unsuccessfully if any item has status `ERROR`.
`UNRESOLVED` and `DECLINED` are valid research outcomes, not execution failures.

## Validation and limits

`evaluation/tests/test_targeted_qa_rewrite.py` exercises selection, immutable fields,
option labels, semantic failure/uncertainty, two-pass acceptance, bounded feedback,
unchanged proposals, failed calls, stale inputs, safe output paths, caching, and
the complete CLI workflow with synthetic model responses.

These tests validate software behavior, not prompt accuracy. Model acceptance
still needs calibration and does not establish human clean-passage performance.
The new script has not automatically rewritten or promoted the full Gold/Hard set.

The API request format follows the
[official OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).
