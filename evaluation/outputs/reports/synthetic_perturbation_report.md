# Synthetic Perturbation Results Report

Score file: `scores_target_llama.json`

This report aggregates whatever scored perturbation outputs currently exist.
Blank experiments are wired into the table and can be filled by rerunning the script after their runs finish.

## High-Level Notes

- `omission` baseline combined score is 0.562; lowest scored variant is `5%` at 0.466 (-0.096 vs baseline).
- `mistranslation` baseline combined score is 0.539; lowest scored variant is `30%` at 0.445 (-0.094 vs baseline).
- `grammar` baseline combined score is 0.539; lowest scored variant is `10%` at 0.508 (-0.031 vs baseline).

## Experiment Tables

### omission

MQM Accuracy > Omission: clause-level removals.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.562 | 66.7% | 0.458 |  |  |  | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.466 | 65.6% | 0.276 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.518 | 62.5% | 0.411 |  |  |  | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.513 | 63.5% | 0.391 |  |  |  | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.495 | 62.5% | 0.365 |  |  |  | 0 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.474 | 59.4% | 0.354 |  |  |  | 0 |

### mistranslation

MQM Accuracy > Mistranslation: same-role phrase substitutions.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.539 | 64.6% | 0.432 |  |  |  | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.542 | 66.7% | 0.417 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.503 | 58.3% | 0.422 |  |  |  | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.531 | 64.6% | 0.417 |  |  |  | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.458 | 54.2% | 0.375 |  |  |  | 0 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.445 | 55.2% | 0.339 |  |  |  | 0 |

### grammar

MQM Fluency > Grammar: rule-based grammar degradation.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.539 | 64.6% | 0.432 |  |  |  | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.531 | 65.6% | 0.406 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.508 | 61.5% | 0.401 |  |  |  | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.552 | 66.7% | 0.438 |  |  |  | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.586 | 70.8% | 0.464 |  |  |  | 0 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.536 | 62.5% | 0.448 |  |  |  | 0 |

## Columns

- `Ch`: chapters with scored results included in that row.
- `Actual`: mean actual perturbation rate from variant metadata, when available.
- `Combined`: weighted score using MCQ correctness plus open-question LLM scores.
- `MCQ`: MCQ direct accuracy.
- `Open`: mean open-question LLM score.
- `Conf`: mean answer-model confidence, if the run used expanded answer format.
- `Insuff`: mean insufficient-information rate.
- `Evidence`: mean evidence-supported rate.
- `Errors`: answer generation errors counted in score files.

To fill currently blank inconsistency results later, rerun this script without `--blank-experiments inconsistency`.
