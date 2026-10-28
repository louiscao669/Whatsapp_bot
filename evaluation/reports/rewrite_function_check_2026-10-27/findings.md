# Rewrite-function check — 27 October 2026

The existing rephrasing functions execute successfully, but there is no complete automatic rewrite path from the new Gold/Hard reviewer. The two live examples also show that the old shortening and vocabulary-simplification prompts can leave the flagged wording unchanged.

## Checks performed

- Ran the existing anchor-rewrite, scored-generation, and hard-recovery test suites: **126 passed** in the project's Python 3.11 environment. These tests use mocked model outputs.
- Made **two live model calls**, using the existing **gpt-4o** shortening and simplification functions on two real Gold questions consistently flagged by the new reviewer.
- Both live functions returned two records with the original IDs preserved and no duplicated IDs.
- Inspected how the new reviewer and legacy repair/rewrite functions are connected.
- Checked anchor eligibility for all 35 forms flagged for rewriting in both review passes. This was a mechanical eligibility check, not a model rewrite.
- No production rewrite prompts, pipeline logic, or canonical question records were changed. Only this diagnostic script and its audit outputs were added.

## Live results

Both functions were tested independently on the original questions, not chained together. Neither receives the new reviewer's failure reasons. These observations are a manual comparison of the outputs; the resulting questions were not sent through another full model review.

| Item | Original question | Shortening output | Simplification output |
|---|---|---|---|
| Gold o8ae, open | What becomes sin to Jeroboam's family? | What becomes sin to Jeroboam's family? | What becomes sin to Jeroboam's family? |
| Gold pb1x, open | What did the captain say to Elisha's prophecy? | What does the captain say to Elisha's prophecy? | What did the captain say to Elisha's prophecy? |

The awkward expressions **“becomes sin to”** and **“say to Elisha's prophecy”** remained. Shortening changed the second question's tense only. Simplification changed the first answer from “Consecrating anyone as priests.” to “Making anyone priests.” That is an answer edit, not a correction of the flagged question wording.

## Integration findings

1. **The new reviewer only flags.** Its configured mutation policy explicitly retains all input records without rewriting them. It does not call any legacy rewriting function, and there is no connected rewrite → re-review → accept/revert cycle for the Gold/Hard revision queue.
2. **The older candidate repairer has a different input contract.** `ScoredGenerator.repair_candidates` expects `audit.failures` with prefixes such as `unnatural question:` or `question too complex:`. The new review records carry language statuses, scores, and evidence instead. All 35 current repeated rewrite flags fail the legacy eligibility check when supplied directly; an explicit adapter is required. This is an interface mismatch, not proof that the legacy repair function crashes.
3. **The anchor rewriter has a different job.** `rewrite_final` is off by default unless `rewrite_anchors=True`. It replaces words borrowed from a single passage verse and explicitly does not broadly restructure the question. Only 4 of the 11 flagged Gold forms and 1 of the 24 flagged Hard forms qualified for anchor rewriting in the mechanical check. Eligibility is not an accepted rewrite, and the English-oriented token rules do not establish reliable Chinese coverage.
4. **The anchor rewriter lacks a semantic-preservation judgment.** Mechanical checks can accept a meaning-changing edit. The existing test deliberately demonstrates that replacing “Jotham escaped” with “Jotham arrives” can be accepted. Passing that test suite does not establish that all rewrites preserve meaning.
5. **The general prompts need alignment with the new review design.** Shortening is driven by length limits and includes instructions to avoid why-questions and sometimes split questions. Simplification focuses on vocabulary and includes a one-fact rule that can remove parts of a compound answer. Those operations are not automatically equivalent to preserving the original semantic target while reducing wording burden.

## Required next connection

A targeted revision step needs the original question, answer choices where present, clean passage window, fixed semantic target, and the new review's specific failure evidence. Its output must then pass the same content-validity and language-accessibility checks before being accepted. MCQ changes need an explicit check of the answer key and every option. A rewrite should not be accepted merely because the model returned different text.

## Evidence files

- [Inputs](inputs.json)
- [Live shortening outputs](shorten_qa_pairs.json)
- [Live simplification outputs](simplify_qa_pairs.json)
- [Routing and anchor eligibility](routing_check.json)
- [Model and source fingerprints](manifest.json)
