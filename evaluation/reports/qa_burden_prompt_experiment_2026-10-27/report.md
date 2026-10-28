# Testing question burden beyond sentence structure

## Finding

The independent-dimensions prompt was the most consistent candidate on the Chinese handkerchief example: both the original and split-sentence versions were held for rewriting in all four checks, including two with anonymous IDs. The concise outcome question was kept in all four checks. The model attributed the Chinese wording's problem to naturalness and avoidable parsing burden, not to leakage of the declared outcome target.

This is a targeted success, not evidence of a generally superior question filter. The burden-based procedures were more permissive than the earlier structural checklist on several other previously flagged questions. Retain structural flags and dimension evidence for reviewer consideration rather than silently replacing the old screen with the most favorable prompt for this example.

## Design

Three new procedures were compared with the prior wording gate, using GPT-6.1 Sol throughout:

1. Whole-item rubric: rate naturalness, processing burden, context and leakage separately.
2. Target-preserving comparison: propose a diagnostic alternative when a real burden can be removed while preserving the intended target, and use that contrast to justify scores.
3. Independent dimensions: work through naturalness, avoidable mental operations, necessary context and leakage in sequence, then enforce a separate admission threshold for each.
4. Prior wording gate: the previous structure-trigger prompt with its original decision/reason schema.

The new prompts assign 0–3 scores to all four dimensions and require REWRITE if any score is at least 2. A score of 1 denotes ordinary manageable demand or minor stiffness. Scores cannot offset one another. These anchors and thresholds are operational research choices, not validated human difficulty scales.

The main comparison used 40 cases twice per prompt: 20 previously examined questions (8 concerns, 8 clear controls, 4 borderline), 4 focal handkerchief variants, 4 constructed checks, and 12 seeded corpus questions absent from prior prompt trials. This produced 320 item judgments in 40 requests. A further 10-case check used neutral IDs and shuffled order twice per prompt, producing 80 judgments in 8 requests. Total: 48 requests, 400 item judgments. Every call completed; all new-prompt decisions obeyed their stated score threshold.

The fresh questions were not independently annotated by humans. English Gold72 cases used full source passages; Chinese Hard66 cases used their reviewed clean verse windows. These differences preclude language or dataset superiority claims. Prompts were frozen before this experiment's model calls, but were developed using the preceding discussion and examples. Main-run IDs were descriptive; the focal anonymous-ID check tests whether conclusions persist without those labels.

## Focal results

Counts are repeated decisions on the same question, not independent sample observations.

| Screening procedure | Original Chinese: REWRITE / 4 | Split Chinese: REWRITE / 4 | Concise Chinese: KEEP / 4 | Split English: REWRITE / 4 |
|---|---:|---:|---:|---:|
| Prior wording gate | 4 | 2 | 4 | 3 |
| Whole-item rubric | 1 | 3 | 4 | 0 |
| Target-preserving comparison | 2 | 3 | 4 | 0 |
| Independent dimensions | 4 | 4 | 4 | 0 |

Original Chinese: 当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？

Split Chinese: 摸过保罗的手帕和围裙被带到病人那里。病人随后怎么样了？

Concise Chinese: 根据这段经文，病人的情况有什么变化？

Split English: Cloths that had touched Paul were taken to the sick. What happened to the sick?

All procedures retained the eight provisionally clear corpus controls in both main runs. The two unchanged clear corpus controls in the anonymous check were also retained on both repeats by every procedure. All procedures correctly handled the constructed diagnostic contrasts on both main and anonymous runs: they held the explicitly answer-revealing item and the missing-location-anchor item, and kept their clear counterparts. This limited control set cannot estimate a general false-positive rate.

## Why the independent-dimensions prompt held the split Chinese version

Across its four assessments:

- Naturalness: 2/3. The opening 摸过保罗的手帕和围裙 can invite a transient reading of 保罗的手帕和围裙 as the object of 摸过, or require reinterpreting the cloths as what touched Paul. These are model-predicted potential misparses, not measured reader behavior.
- Processing: 2/3. Before answering the direct outcome question, the reader must resolve that modifier/participant relationship and the passive transfer construction. The contact relationship is not the declared testing target.
- Context: 0 or 1/3. The background supplies a useful event anchor, with at most minor removable detail. The model did not consistently consider it substantially irrelevant.
- Leakage: 0/3. The target metadata explicitly asks about the outcome for the sick. The setup does not state that illnesses or evil spirits left. If a different study target were the contact or transfer relationship, the leakage judgment could change.

The English split version received KEEP from all three new procedures in all four checks. They judged its wording idiomatic and its event sequence manageable. This is precisely why a syntax blacklist and a predicted burden assessment can disagree: analogous grammatical structures need not create identical wording difficulties across languages.

## Broader tradeoff

| Procedure | Earlier concern cases held on both main runs / 8 | Clear controls kept on both main runs / 8 |
|---|---:|---:|
| Prior wording gate | 6 | 8 |
| Whole-item rubric | 1 | 8 |
| Target-preserving comparison | 2 | 8 |
| Independent dimensions | 2 | 8 |

These counts describe agreement with provisional prior flags, not recall against proven defects. For example, the independent-dimensions prompt accepted the Hard66 exorcist question 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ and the Gaal/Zebul speech question in both main runs, judging their role tracking manageable in context. The earlier structural gate flags them by explicit construction rules. This disagreement requires a defined audience standard and independent human adjudication; maximizing rejection would not settle it.

On the twelve fresh corpus items, the independent-dimensions procedure held one consistently and disagreed on one across repeats. The consistent new concern was the English question “What does the old prophet say to the man of God?”: its grammar is simple, but the full passage contains multiple exchanges, so the intended speech event needs an anchor. The target-preserving comparison also consistently flagged “How did captain respond to the plan?” and proposed identifying the relevant plot. Shortness alone is therefore an inadequate screen.

## Recommended use

Use `prompt_independent_dimensions.txt` as a candidate supplementary burden assessment. Preserve its concrete dimension evidence alongside the structural flags. Disagreement between screens should go to review, not be silently interpreted as a safe pass or an established defect. The audience assumption in this experiment is an ordinary adult native speaker; audio delivery, low literacy, or another target population needs a separately specified and validated standard.

The critical prompt changes are:

1. Evaluate the complete displayed item across sentence boundaries, including introductions and choices.
2. Require evidence for naturalness, processing burden, context sufficiency/necessity and leakage separately.
3. Identify the intended semantic target before deciding what context is unnecessary or revealing.
4. Preserve clear causal, temporal, conditional and negative meanings; do not reject merely because they are expressed with a clause or passive.
5. Require a failed dimension to affect admission directly; never average it away with easy answer recoverability.
6. Treat alternative wording as a diagnostic proposal requiring target-preservation review, not as an automatically approved replacement.

The target-preserving comparison produced useful diagnostic proposals, but some add event details or replace a contact relationship with possession (“Paul's handkerchiefs”). Those changes require source and target review. They were not applied to the corpus.

Before production deployment, test the frozen prompt on independently annotated questions and, ideally, measure comprehension or response time in the intended population. Model stability on these examples is not evidence of measured reader burden. No production question sets, generation prompts or campaigns were changed.

## Saved evidence

- `prompt_*.txt`: exact frozen prompts.
- `cases.json` and `manifest.json`: cases, provisional groups and configuration.
- `responses/`: all main model outputs, dimension evidence, request hashes, response IDs and usage.
- `item_results.md`: readable per-question judgments.
- `summary.json` and `focus_summary.json`: aggregate and focal counts.
- `blind_check/mapped_results.json`: anonymous-ID judgments mapped back to the cases for review.
- `verification.json`: completion, threshold checks and token usage.
- `design_notes.md`: selection and interpretation limits.
