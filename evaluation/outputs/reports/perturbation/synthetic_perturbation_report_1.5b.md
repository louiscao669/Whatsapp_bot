# Synthetic Perturbation Results Report

Score file: `scores_target_llama.json`

This report aggregates whatever scored perturbation outputs currently exist.
Blank experiments are wired into the table and can be filled by rerunning the script after their runs finish.

## High-Level Notes

- `addition` baseline combined score is 0.758; lowest scored variant is `adversarial_30%` at 0.674 (-0.083 vs baseline).
- `omission` baseline combined score is 0.745; lowest scored variant is `30%` at 0.641 (-0.104 vs baseline).
- `mistranslation` baseline combined score is 0.766; lowest scored variant is `30%` at 0.609 (-0.156 vs baseline).
- `grammar` baseline combined score is 0.740; lowest scored variant is `15%` at 0.729 (-0.010 vs baseline).
- `inconsistency` has no scored variants yet.
- `local_inconsistency` has scored variants; best observed combined score is `style_5%` at 0.742.
- `awkward` baseline combined score is 0.747; lowest scored variant is `20%` at 0.727 (-0.021 vs baseline).

## Experiment Tables

### addition

MQM Accuracy > Addition: neutral, bad, or MCQ-adversarial inserted clauses.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.758 | 76.0% | 0.755 |  |  |  | 0 |
| neutral_5% | complete | 1,2,3,4,5,6,7,8 |  | 0.760 | 77.1% | 0.750 |  |  |  | 0 |
| bad_5% | complete | 1,2,3,4,5,6,7,8 |  | 0.758 | 78.1% | 0.734 |  |  |  | 0 |
| adversarial_5% | complete | 1,2,3,4,5,6,7,8 |  | 0.740 | 77.1% | 0.708 |  |  |  | 0 |
| neutral_10% | complete | 1,2,3,4,5,6,7,8 |  | 0.750 | 78.1% | 0.719 |  |  |  | 0 |
| bad_10% | complete | 1,2,3,4,5,6,7,8 |  | 0.747 | 79.2% | 0.703 |  |  |  | 0 |
| adversarial_10% | complete | 1,2,3,4,5,6,7,8 |  | 0.708 | 76.0% | 0.656 |  |  |  | 0 |
| neutral_15% | complete | 1,2,3,4,5,6,7,8 |  | 0.771 | 79.2% | 0.750 |  |  |  | 0 |
| bad_15% | complete | 1,2,3,4,5,6,7,8 |  | 0.729 | 78.1% | 0.677 |  |  |  | 0 |
| adversarial_15% | complete | 1,2,3,4,5,6,7,8 |  | 0.711 | 77.1% | 0.651 |  |  |  | 0 |
| neutral_20% | complete | 1,2,3,4,5,6,7,8 |  | 0.755 | 79.2% | 0.719 |  |  |  | 0 |
| bad_20% | complete | 1,2,3,4,5,6,7,8 |  | 0.734 | 79.2% | 0.677 |  |  |  | 0 |
| adversarial_20% | complete | 1,2,3,4,5,6,7,8 |  | 0.688 | 75.0% | 0.625 |  |  |  | 0 |
| neutral_30% | complete | 1,2,3,4,5,6,7,8 |  | 0.755 | 81.2% | 0.698 |  |  |  | 0 |
| bad_30% | complete | 1,2,3,4,5,6,7,8 |  | 0.721 | 79.2% | 0.651 |  |  |  | 0 |
| adversarial_30% | complete | 1,2,3,4,5,6,7,8 |  | 0.674 | 74.0% | 0.609 |  |  |  | 0 |

### omission

MQM Accuracy > Omission: clause-level removals.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.745 | 76.0% | 0.729 |  |  |  | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.745 | 80.2% | 0.688 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.753 | 82.3% | 0.682 |  |  |  | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.701 | 78.1% | 0.620 |  |  |  | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.714 | 79.2% | 0.635 |  |  |  | 0 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.641 | 72.9% | 0.552 |  |  |  | 0 |

### mistranslation

MQM Accuracy > Mistranslation: same-role phrase substitutions.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.766 | 76.0% | 0.771 |  |  |  | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.737 | 76.0% | 0.714 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.682 | 70.8% | 0.656 |  |  |  | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.672 | 70.8% | 0.635 |  |  |  | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.651 | 70.8% | 0.594 |  |  |  | 0 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.609 | 67.7% | 0.542 |  |  |  | 0 |

### grammar

MQM Fluency > Grammar: rule-based grammar degradation.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.740 | 76.0% | 0.719 |  |  |  | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.755 | 77.1% | 0.740 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.747 | 78.1% | 0.714 |  |  |  | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.729 | 77.1% | 0.688 |  |  |  | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.734 | 77.1% | 0.698 |  |  |  | 0 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.737 | 82.3% | 0.651 |  |  |  | 0 |

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
| style_5% | complete | 1,2,3,4,5,6,7,8 | 5.9% | 0.742 | 74.0% | 0.745 |  |  |  | 0 |
| style_10% | complete | 1,2,3,4,5,6,7,8 | 7.4% | 0.734 | 74.0% | 0.729 |  |  |  | 0 |
| style_15% | complete | 1,2,3,4,5,6,7,8 | 8.7% | 0.737 | 75.0% | 0.724 |  |  |  | 0 |
| style_20% | complete | 1,2,3,4,5,6,7,8 | 9.6% | 0.724 | 72.9% | 0.719 |  |  |  | 0 |

### awkward

MQM Style > Awkward: literalized/source-like phrasing replacements.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.747 | 76.0% | 0.734 |  |  |  | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.760 | 77.1% | 0.750 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.758 | 75.0% | 0.766 |  |  |  | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.732 | 77.1% | 0.693 |  |  |  | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.727 | 76.0% | 0.693 |  |  |  | 0 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.745 | 78.1% | 0.708 |  |  |  | 0 |

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
