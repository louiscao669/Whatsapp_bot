# QA admission prompt experiment

## Finding

A dedicated wording gate is more useful for the observed sentence-structure failures than asking a model whether an answer is directly recoverable. On this development set, the wording-only gate consistently held seven of the twelve initially flagged items for rewriting, while retaining all fifteen clear-wording controls. It also flagged the user's exact Chinese handkerchief question twice and accepted simpler candidate wording twice. This is evidence of behavior under explicit prompt rules, not evidence that the model independently establishes what is difficult for human readers.

## Design

Forty cases: 24 Chinese Hard66 MCQs using their actual reviewed clean passage windows, and 16 English Gold72 questions using full English source passages (15 open, one MCQ). Twelve initially flagged wording concerns, fifteen provisionally clear-wording controls, thirteen borderline cases. All labels were frozen before calls. GPT-6.1 Sol judged each case twice per prompt in independently shuffled batches of ten. The four initial prompts were frozen together. A fifth wording-only prompt was developed after inspecting their results. Forty batch requests produced 400 item judgments. Two additional requests produced twelve judgments on six transfer/repair cases. The original scores and provisional labels were withheld from judges.

The current filter baseline preserved its substantive instructions, with a JSON/multi-case wrapper and Remove mapped to KEEP/DROP. It was rerun with the same newer model as every alternative; this is a prompt comparison, not a GPT-4o-versus-new-model experiment or an exact reproduction of historical runs.

## Results

Counts below are item-level consistency across two runs. A block means REWRITE or DROP. The initial flagged group is not independent gold-standard truth; grounding objections are included in broad block counts and must not be mistaken for syntax detection.

| Prompt | Initially flagged items blocked both times / 12 | Clear-wording controls kept both times / 15 | Admission disagreements across 40 items |
|---|---:|---:|---:|
| Current recoverability filter | 2 | 12 | 3 |
| Strict syntax | 9 | 11 | 2 |
| Balanced burden | 7 | 11 | 4 |
| Staged wording + grounding + format | 9 | 11 | 2 |
| Wording only, adaptive follow-up | 7 | 15 | 2 |

The strict and staged prompts' additional blocks include answer/source mismatches rather than wording catches. Examples: whether the spirit or the possessed man beat the exorcists; and whether the source names one silver-covered image or distinct carved and molten images. These may be legitimate grounding issues or rendering mismatches and require source review. They do not demonstrate better syntax screening.

Some apparently clear questions were blocked by combined gates because their keyed choices say 'from Judah' while that descriptor is outside the displayed window. Another objection depended on Eloth/Elath spelling. Thus 'clear-wording controls blocked' is not automatically a false positive for a comprehensive grounding gate; it does show why wording and grounding must be evaluated separately.

## Seven consistent wording catches

| Item | Question or identifying phrase | Current baseline | Wording-only gate |
|---|---|---|---|
| Hard 1 Kings 13 ec63 | 带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？ | KEEP twice | REWRITE twice: modified reporting actor, repeated pronouns, archaic negative prediction |
| Hard 2 Kings 11 f49c | 耶何耶大立的第一个约，是在哪些之间立的？ | KEEP twice | REWRITE twice: incomplete/unnatural 哪些之间 |
| Hard Acts 19 7628 | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | KEEP twice | REWRITE twice: modified actor inside fronted passive temporal setup |
| Hard Judges 9 6d68 | 约坦呼叫示剑的众首领听他的话，是为了什么结果？ | DROP twice | REWRITE twice: awkward purpose/result wording |
| Hard Judges 9 f36a | 迦勒第一次说有人来时，西布说他看见的其实是什么？ | KEEP twice | REWRITE twice: layered reporting/perception and viewpoint tracking |
| Gold Acts 19 b1be | What happened when handkerchiefs and aprons that had touched Paul were taken to the sick? | KEEP twice | REWRITE twice: relative clause inside passive temporal clause |
| Gold Judges 17–18 rhwo | What did Dan's people want the Levite to ask God? | KEEP twice | REWRITE twice: desire/consultation across three roles |

The wording gate accepted five of the initial twelve concerns. These include the 'Who showed the old prophet which way...' question and the 'What religious objects did the spies say...' question. Those initial flags should not be described as proven defects. The gate also accepted the four leprous men's decision question and the 'images first' question when the supplied context resolved the target. Expert review is still needed if their naturalness is unacceptable for the intended reader population.

Two borderline cases changed decisions across runs: 王求神人为他祷告，谁为王祷告了？ and 他们请谁为他们求问这趟行程？. A majority vote cannot be claimed from two runs. These need human review.

## Exact Chinese example and candidate repairs

All following decisions were repeated identically in both adaptive transfer trials.

| Candidate | Decision |
|---|---|
| 当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？ | REWRITE |
| 摸过保罗的手帕和围裙被带到病人那里。病人随后怎么样了？ | KEEP |
| Cloths that had touched Paul were taken to the sick. What happened to the sick? | KEEP |
| 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | REWRITE |
| 谁受伤逃出了那房子？ | KEEP |
| 谁在路上被狮子咬死了？ (unchanged passive control) | KEEP |

The handkerchief repair retains a relative modifier and passive statement but separates the event setup from the direct outcome question. This reduces nesting rather than merely deleting information. It still needs validation that supplying this setup does not disclose the particular meaning a study intends to test. The exorcist repair preserves the actor-identification query but removes the fronted passive setup; passage context and answer uniqueness should be rechecked before adoption. Neither repair is installed in production.

## Recommended prompt change

Use the exact tested prompt in `prompt_wording_only_v2.txt` as a candidate separate admission gate. Its critical changes are:

1. Parse the entire question, explicitly identifying nested clauses and pronoun antecedents before deciding; do not infer simplicity from a WH word.
2. Block nested temporal/passive modifiers, delayed actor identification, layered reporting viewpoints, repeated unresolved pronouns and malformed phrasing.
3. Permit ordinary single temporal clauses, simple passives, clear causal/conditional targets and necessary semantic relationships.
4. Separate wording failures from answer grounding, source-rendering differences and option correctness.
5. Use KEEP or REWRITE for this gate. REWRITE means retain the record but prevent release until repaired/reviewed. Grounding failures need their own reviewed disposition.

The tested prompt includes context-sensitive option burden and answer-cueing checks. Its automatic rules express the researcher's desired admission standard; they do not establish that every named construction is intrinsically too hard for humans.

## Placement and next validation

Run the wording gate after shortening, after MCQ conversion, and on the final target-language questions/options. The current prepared-UW route does not call the separate lexical simplification function used on the LLM-generated route. Adding a final gate is therefore different from assuming shortening already guarantees simple syntax.

Do not apply the new wording prompt to old difficulty scores and assume they are comparable. Revise question-complexity scoring separately so syntax is not conflated with who/what/why type. Fixing admission can be evaluated without rebuilding the historical difficulty scale.

Before automatic integration, freeze the prompt and have translation scholars or target-language readers independently label a new sample of clear and problematic questions. Evaluate wording catches, unjustified holds, reviewer agreement and human performance. Repeat on respondent-facing translations. This experiment used an enriched development set and a partially adaptive fifth prompt, so its success cannot be reported as held-out sensitivity/specificity or proof of improved human comprehension.

No QA records, production prompts, or running campaigns were changed.

## Files

- `prompt_*.txt`: all exact prompts.
- `cases.json`: frozen cases and provisional labels.
- `manifest_initial_four.json` and `manifest.json`: configurations and prompt hashes.
- `responses/`: model outputs, response IDs, timings and usage.
- `summary.json`: aggregate counts.
- `item_results.md`: all decisions and explanations.
- `transfer_cases.json` and `transfer_results.json`: exact Chinese example and repairs.
- `design_notes.md`: design caveats and adaptive follow-up disclosure.
