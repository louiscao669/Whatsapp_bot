# Synthetic Perturbation Results Report

Score file: `scores_target_llama.json`

This report aggregates whatever scored perturbation outputs currently exist.
Blank experiments are wired into the table and can be filled by rerunning the script after their runs finish.

## High-Level Notes

- `addition` baseline combined score is 0.594; lowest scored variant is `adversarial_20%` at 0.542 (-0.052 vs baseline).
- `omission` baseline combined score is 0.562; lowest scored variant is `5%` at 0.466 (-0.096 vs baseline).
- `mistranslation` baseline combined score is 0.539; lowest scored variant is `30%` at 0.445 (-0.094 vs baseline).
- `grammar` baseline combined score is 0.539; lowest scored variant is `10%` at 0.508 (-0.031 vs baseline).
- `inconsistency` has no scored variants yet.
- `local_inconsistency` has scored variants; best observed combined score is `style_5%` at 0.583.
- `awkward` baseline combined score is 0.544; lowest scored variant is `15%` at 0.529 (-0.016 vs baseline).

## Experiment Tables

### addition

MQM Accuracy > Addition: neutral, bad, or MCQ-adversarial inserted clauses.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.594 | 69.8% | 0.490 | 0.880 | 4.5% | 97.7% | 0 |
| neutral_5% | complete | 1,2,3,4,5,6,7,8 | 5.4% | 0.612 | 72.9% | 0.495 | 0.866 | 6.8% | 95.5% | 0 |
| bad_5% | complete | 1,2,3,4,5,6,7,8 | 5.2% | 0.609 | 69.8% | 0.521 | 0.882 | 4.5% | 97.7% | 0 |
| adversarial_5% | complete | 1,2,3,4,5,6,7,8 | 5.2% | 0.596 | 67.7% | 0.516 | 0.880 | 4.5% | 97.7% | 0 |
| neutral_10% | complete | 1,2,3,4,5,6,7,8 | 10.0% | 0.625 | 71.9% | 0.531 | 0.886 | 4.5% | 97.7% | 0 |
| bad_10% | complete | 1,2,3,4,5,6,7,8 | 10.1% | 0.565 | 66.7% | 0.464 | 0.882 | 2.3% | 97.7% | 0 |
| adversarial_10% | complete | 1,2,3,4,5,6,7,8 | 10.7% | 0.568 | 64.6% | 0.490 | 0.900 | 2.3% | 100.0% | 0 |
| neutral_15% | complete | 1,2,3,4,5,6,7,8 | 15.4% | 0.609 | 75.0% | 0.469 | 0.841 | 6.8% | 95.5% | 0 |
| bad_15% | complete | 1,2,3,4,5,6,7,8 | 15.8% | 0.596 | 71.9% | 0.474 | 0.875 | 2.3% | 97.7% | 0 |
| adversarial_15% | complete | 1,2,3,4,5,6,7,8 | 15.1% | 0.581 | 65.6% | 0.505 | 0.898 | 2.3% | 100.0% | 0 |
| neutral_20% | complete | 1,2,3,4,5,6,7,8 | 20.0% | 0.602 | 71.9% | 0.484 | 0.861 | 2.3% | 97.7% | 0 |
| bad_20% | complete | 1,2,3,4,5,6,7,8 | 20.4% | 0.586 | 71.9% | 0.453 | 0.877 | 2.3% | 97.7% | 0 |
| adversarial_20% | complete | 1,2,3,4,5,6,7,8 | 20.5% | 0.542 | 61.5% | 0.469 | 0.859 | 6.8% | 95.5% | 0 |
| neutral_30% | complete | 1,2,3,4,5,6,7,8 | 30.2% | 0.576 | 69.8% | 0.453 | 0.902 | 4.5% | 100.0% | 0 |
| bad_30% | complete | 1,2,3,4,5,6,7,8 | 30.3% | 0.615 | 74.0% | 0.490 | 0.857 | 4.5% | 95.5% | 0 |
| adversarial_30% | complete | 1,2,3,4,5,6,7,8 | 30.3% | 0.544 | 60.4% | 0.484 | 0.880 | 6.8% | 97.7% | 0 |

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

### inconsistency

MQM Inconsistency: separate name/entity and style/register inconsistency.

Experiment chapters present: `none`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | missing |  |  |  |  |  |  |  |  |  |
| name_5% | missing |  |  |  |  |  |  |  |  |  |
| style_5% | missing |  |  |  |  |  |  |  |  |  |
| name_10% | missing |  |  |  |  |  |  |  |  |  |
| style_10% | missing |  |  |  |  |  |  |  |  |  |
| name_15% | missing |  |  |  |  |  |  |  |  |  |
| style_15% | missing |  |  |  |  |  |  |  |  |  |
| name_20% | missing |  |  |  |  |  |  |  |  |  |
| style_20% | missing |  |  |  |  |  |  |  |  |  |

### local_inconsistency

MQM Inconsistency: question-local style/register inconsistency inside each QA verse window.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| style_5% | complete | 1,2,3,4,5,6,7,8 | 5.9% | 0.583 | 68.8% | 0.479 |  |  |  | 0 |
| style_10% | complete | 1,2,3,4,5,6,7,8 | 7.3% | 0.573 | 67.7% | 0.469 |  |  |  | 0 |
| style_15% | complete | 1,2,3,4,5,6,7,8 | 8.5% | 0.562 | 68.8% | 0.438 |  |  |  | 0 |
| style_20% | complete | 1,2,3,4,5,6,7,8 | 9.3% | 0.562 | 66.7% | 0.458 |  |  |  | 0 |

### awkward

MQM Style > Awkward: literalized/source-like phrasing replacements.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.544 | 64.6% | 0.443 |  |  |  | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.555 | 63.5% | 0.474 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.536 | 63.5% | 0.438 |  |  |  | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.529 | 63.5% | 0.422 |  |  |  | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.539 | 63.5% | 0.443 |  |  |  | 0 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.529 | 59.4% | 0.464 |  |  |  | 0 |

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
