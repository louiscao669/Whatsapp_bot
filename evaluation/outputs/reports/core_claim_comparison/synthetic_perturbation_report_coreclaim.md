# Synthetic Perturbation Results Report

Score file: `scores_target_llama.json`

This report aggregates whatever scored perturbation outputs currently exist.
Blank experiments are wired into the table and can be filled by rerunning the script after their runs finish.

## High-Level Notes

- `addition` baseline combined score is 0.784; lowest scored variant is `adversarial_30%` at 0.696 (-0.088 vs baseline).
- `omission` baseline combined score is 0.824; lowest scored variant is `30%` at 0.689 (-0.135 vs baseline).
- `mistranslation` baseline combined score is 0.794; lowest scored variant is `30%` at 0.632 (-0.162 vs baseline).
- `grammar` baseline combined score is 0.772; lowest scored variant is `20%` at 0.750 (-0.022 vs baseline).
- `inconsistency` baseline combined score is 0.758; lowest scored variant is `name_5%` at 0.742 (-0.016 vs baseline).
- `local_inconsistency` has scored variants; best observed combined score is `style_20%` at 0.850.
- `awkward` baseline combined score is 0.762; lowest scored variant is `0%` at 0.762 (+0.000 vs baseline).

## Experiment Tables

### addition

MQM Accuracy > Addition: neutral, bad, or MCQ-adversarial inserted clauses.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.784 | 88.2% | 0.686 | 0.855 | 5.6% | 96.5% | 0 |
| neutral_5% | complete | 1,2,3,4,5,6,7,8 |  | 0.760 | 90.2% | 0.618 | 0.835 | 7.1% | 94.2% | 1 |
| bad_5% | complete | 1,2,3,4,5,6,7,8 |  | 0.792 | 88.2% | 0.701 | 0.846 | 4.9% | 96.2% | 0 |
| adversarial_5% | complete | 1,2,3,4,5,6,7,8 |  | 0.757 | 86.3% | 0.652 | 0.860 | 5.2% | 96.1% | 0 |
| neutral_10% | complete | 1,2,3,4,5,6,7,8 |  | 0.809 | 91.2% | 0.706 | 0.813 | 8.9% | 94.8% | 0 |
| bad_10% | complete | 1,2,3,4,5,6,7,8 |  | 0.782 | 88.2% | 0.681 | 0.850 | 4.5% | 96.1% | 1 |
| adversarial_10% | complete | 1,2,3,4,5,6,7,8 |  | 0.748 | 83.3% | 0.662 | 0.850 | 6.2% | 96.7% | 0 |
| neutral_15% | complete | 1,2,3,4,5,6,7,8 |  | 0.799 | 91.2% | 0.686 | 0.831 | 9.3% | 94.8% | 0 |
| bad_15% | complete | 1,2,3,4,5,6,7,8 |  | 0.770 | 88.2% | 0.657 | 0.849 | 4.2% | 95.8% | 0 |
| adversarial_15% | complete | 1,2,3,4,5,6,7,8 |  | 0.748 | 84.3% | 0.652 | 0.850 | 6.3% | 95.2% | 0 |
| neutral_20% | complete | 1,2,3,4,5,6,7,8 |  | 0.787 | 88.2% | 0.691 | 0.821 | 8.3% | 93.2% | 1 |
| bad_20% | complete | 1,2,3,4,5,6,7,8 |  | 0.801 | 90.2% | 0.701 | 0.839 | 5.1% | 95.9% | 0 |
| adversarial_20% | complete | 1,2,3,4,5,6,7,8 |  | 0.703 | 79.4% | 0.613 | 0.823 | 9.2% | 93.1% | 0 |
| neutral_30% | complete | 1,2,3,4,5,6,7,8 |  | 0.750 | 88.2% | 0.618 | 0.825 | 8.4% | 93.8% | 1 |
| bad_30% | complete | 1,2,3,4,5,6,7,8 |  | 0.750 | 87.3% | 0.627 | 0.839 | 5.6% | 96.3% | 0 |
| adversarial_30% | complete | 1,2,3,4,5,6,7,8 |  | 0.696 | 75.5% | 0.637 | 0.835 | 8.3% | 94.9% | 0 |

### omission

MQM Accuracy > Omission: clause-level removals.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.824 | 90.2% | 0.745 |  |  |  | 2 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.784 | 89.2% | 0.676 |  |  |  | 1 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.816 | 91.2% | 0.721 |  |  |  | 1 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.721 | 87.3% | 0.569 |  |  |  | 2 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.708 | 85.3% | 0.564 |  |  |  | 2 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.689 | 82.4% | 0.554 |  |  |  | 2 |

### mistranslation

MQM Accuracy > Mistranslation: same-role phrase substitutions.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.794 | 92.2% | 0.667 |  |  |  | 1 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.784 | 92.2% | 0.647 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.789 | 94.1% | 0.637 |  |  |  | 1 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.743 | 87.3% | 0.613 |  |  |  | 1 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.701 | 85.3% | 0.549 |  |  |  | 1 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.632 | 82.4% | 0.441 |  |  |  | 1 |

### grammar

MQM Fluency > Grammar: rule-based grammar degradation.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.772 | 87.3% | 0.672 | 0.852 | 5.7% | 96.1% | 1 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.789 | 89.2% | 0.686 | 0.833 | 5.5% | 95.2% | 1 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.765 | 87.3% | 0.657 | 0.846 | 4.5% | 96.9% | 1 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.752 | 86.3% | 0.642 | 0.821 | 6.4% | 93.2% | 1 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.750 | 87.3% | 0.627 | 0.823 | 7.4% | 95.3% | 1 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.752 | 85.3% | 0.652 | 0.843 | 7.5% | 95.6% | 1 |

### inconsistency

MQM Inconsistency: separate name/entity and style/register inconsistency.

Experiment chapters present: `1,2,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,4,5,6,7,8 |  | 0.758 | 86.3% | 0.653 | 0.855 | 4.3% | 95.4% | 1 |
| name_5% | complete | 1,2,4,5,6,7,8 |  | 0.742 | 89.5% | 0.589 | 0.840 | 6.2% | 93.5% | 3 |
| style_5% | complete | 1,2,4,5,6,7,8 |  | 0.755 | 87.4% | 0.637 | 0.830 | 5.7% | 93.2% | 1 |
| name_10% | complete | 1,2,4,5,6,7,8 |  | 0.776 | 91.6% | 0.637 | 0.846 | 6.5% | 94.8% | 2 |
| style_10% | complete | 1,2,4,5,6,7,8 |  | 0.755 | 88.4% | 0.626 | 0.820 | 6.9% | 92.1% | 1 |
| name_15% | complete | 1,2,4,5,6,7,8 |  | 0.763 | 90.5% | 0.621 | 0.833 | 5.5% | 92.5% | 3 |
| style_15% | complete | 1,2,4,5,6,7,8 |  | 0.766 | 88.4% | 0.647 | 0.812 | 7.3% | 91.7% | 1 |
| name_20% | complete | 1,2,4,5,6,7,8 |  | 0.758 | 88.4% | 0.632 | 0.839 | 6.2% | 93.7% | 4 |
| style_20% | complete | 1,2,4,5,6,7,8 |  | 0.768 | 88.4% | 0.653 | 0.815 | 7.3% | 91.7% | 1 |

### local_inconsistency

MQM Inconsistency: question-local style/register inconsistency inside each QA verse window.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| style_5% | complete | 1,2,3,4,5,6,7,8 |  | 0.817 | 93.3% | 0.700 | 0.842 | 5.6% | 96.2% | 0 |
| style_10% | complete | 1,2,3,4,5,6,7,8 |  | 0.767 | 91.1% | 0.622 | 0.848 | 3.8% | 96.2% | 0 |
| style_15% | complete | 1,2,3,4,5,6,7,8 |  | 0.844 | 97.8% | 0.711 | 0.837 | 6.2% | 95.0% | 0 |
| style_20% | complete | 1,2,3,4,5,6,7,8 |  | 0.850 | 97.8% | 0.722 | 0.843 | 6.9% | 95.0% | 0 |

### awkward

MQM Style > Awkward: literalized/source-like phrasing replacements.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.762 | 87.3% | 0.652 | 0.852 | 5.7% | 96.4% | 1 |
| 5% | complete | 1,2,3,4,5,6,7,8 |  | 0.797 | 90.2% | 0.691 | 0.828 | 5.7% | 95.6% | 1 |
| 10% | complete | 1,2,3,4,5,6,7,8 |  | 0.777 | 85.3% | 0.701 | 0.827 | 8.6% | 94.5% | 2 |
| 15% | complete | 1,2,3,4,5,6,7,8 |  | 0.789 | 86.3% | 0.716 | 0.837 | 6.4% | 94.3% | 2 |
| 20% | complete | 1,2,3,4,5,6,7,8 |  | 0.767 | 88.2% | 0.652 | 0.806 | 10.8% | 91.7% | 2 |
| 30% | complete | 1,2,3,4,5,6,7,8 |  | 0.777 | 88.2% | 0.672 | 0.822 | 7.3% | 95.5% | 3 |

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
