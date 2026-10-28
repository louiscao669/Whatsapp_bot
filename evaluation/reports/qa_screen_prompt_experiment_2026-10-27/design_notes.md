# Design and interpretation

The user requested testing alternative admission prompts on wording problems in Hard 66 and Gold 72. This is a diagnostic prompt experiment, not a human validation study.

## Frozen design

- 40 cases selected and labelled before model calls: 12 wording concerns, 15 clear controls, 13 borderline examples.
- Four prompts: substantive current removal filter, strict syntax gate, balanced burden gate, staged wording/grounding/format gate.
- Same GPT-6.1 Sol model for every prompt, two calls per item in differently shuffled batches, batch size 10. Prior scores, review notes, and provisional labels are withheld from the model.
- Hard 66: actual Chinese MCQ stems and four substantive options with expected key, plus the clean reviewed experimental verse window (including recorded window extensions). No abstention option added for this audit.
- Gold 72: English open questions except the exorcist item, which uses its actual longer MCQ stem and choices. Full English source fixture supplied. These are not the Chinese questions delivered in a participant session.
- Original production questions, scoring and pipeline remain unchanged. Prompt texts, case payloads, returned judgments, response identifiers and usage are saved.

## Adaptive follow-up

After inspecting the first four prompts, a fifth wording-only prompt was added. The first four prompts and their saved results were unchanged. The fifth explicitly separates wording assessment from answer grounding because source-rendering differences and out-of-window answer descriptors caused some rejection reasons unrelated to syntax. It was run twice on the same 40 cases, so its favorable performance is adaptive development-set evidence, not a held-out comparison. The initial manifest is retained as manifest_initial_four.json.

A second adaptive check uses six cases: the user's exact Chinese handkerchief MCQ, candidate Chinese and English handkerchief repairs, the Hard66 exorcist question and a candidate repair, and an unchanged simple Chinese passive question. It uses the wording-only prompt twice. These repairs are candidates for human review and have not been inserted into the QA sets.

## Important limits

- Concern/control labels are the assistant's provisional judgments from the preceding wording audit, not independent expert annotations. Metrics measure agreement with those labels, not validated sensitivity/specificity.
- The chosen cases are enriched for observed problems. They cannot estimate the removal rate in the complete corpus.
- No independent held-out prompt-development set: all four prompts were written before the calls, but results should be replicated on new items before pipeline adoption.
- Repeated judgments on the same item are not independent observations. Report both item-level agreement and repeat stability; do not treat 80 judgments as 80 independent questions.
- The English and Chinese groups differ in context and format. Do not infer one dataset is intrinsically better from group rejection rates.
- A DROP reason may identify answer/source mismatch rather than the targeted wording issue. Read the reasons; successful rejection alone is insufficient evidence of a syntax screen.
- English fixtures and QA preparation may use different Bible renderings. Apparent answer mismatches need review against the actual intended source; model objections are not automatically correct.
- A long question, a passive, a why question, a temporal clause, or a multi-part answer is not automatically bad. The desired outcome is a clear question about a meaningful relationship.
- REWRITE blocks admission pending repair while preserving the item for revision; DROP means the target/answer needs substantive reconsideration. Neither should delete production records automatically.

## Pipeline placement to investigate

Apply a final wording gate after shortening and after each format conversion. Apply the gate again to translated respondent-facing stems and options because English simplicity does not guarantee Chinese simplicity. Keep syntactic complexity separate from question type and from answer-recovery difficulty. Require evidence for each failure and retain a reviewable reason. Only consider production integration after evaluating false positives and reviewer agreement.
