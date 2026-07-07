# Synthetic Perturbation Results Report

Score file: `scores_target_llama.json`

This report aggregates whatever scored perturbation outputs currently exist.
Blank experiments are wired into the table and can be filled by rerunning the script after their runs finish.

## High-Level Notes

- `addition` baseline combined score is 0.828; lowest scored variant is `adversarial_30%` at 0.701 (-0.127 vs baseline).
- `omission` baseline combined score is 0.892; lowest scored variant is `30%` at 0.730 (-0.162 vs baseline).
- `mistranslation` baseline combined score is 0.909; lowest scored variant is `30%` at 0.659 (-0.250 vs baseline).
- `grammar` baseline combined score is 0.809; lowest scored variant is `20%` at 0.770 (-0.039 vs baseline).
- `inconsistency` baseline combined score is 0.799; lowest scored variant is `name_5%` at 0.789 (-0.010 vs baseline).
- `awkward` baseline combined score is 0.838; lowest scored variant is `10%` at 0.794 (-0.044 vs baseline).

## Experiment Tables

### addition

MQM Accuracy > Addition: neutral, bad, or MCQ-adversarial inserted clauses.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.828 | 88.2% | 0.775 | 0.855 | 5.6% | 96.5% | 0 |
| neutral_5% | complete | 1,2,3,4,5,6,7,8 | 5.3% | 0.799 | 90.2% | 0.696 | 0.835 | 7.1% | 94.2% | 1 |
| bad_5% | complete | 1,2,3,4,5,6,7,8 | 5.6% | 0.799 | 88.2% | 0.716 | 0.846 | 4.9% | 96.2% | 0 |
| adversarial_5% | complete | 1,2,3,4,5,6,7,8 | 5.5% | 0.799 | 86.3% | 0.735 | 0.860 | 5.2% | 96.1% | 0 |
| neutral_10% | complete | 1,2,3,4,5,6,7,8 | 10.2% | 0.828 | 91.2% | 0.745 | 0.813 | 8.9% | 94.8% | 0 |
| bad_10% | complete | 1,2,3,4,5,6,7,8 | 10.5% | 0.814 | 88.2% | 0.745 | 0.850 | 4.5% | 96.1% | 1 |
| adversarial_10% | complete | 1,2,3,4,5,6,7,8 | 10.5% | 0.770 | 83.3% | 0.706 | 0.850 | 6.2% | 96.7% | 0 |
| neutral_15% | complete | 1,2,3,4,5,6,7,8 | 15.4% | 0.828 | 91.2% | 0.745 | 0.831 | 9.3% | 94.8% | 0 |
| bad_15% | complete | 1,2,3,4,5,6,7,8 | 15.4% | 0.794 | 88.2% | 0.706 | 0.849 | 4.2% | 95.8% | 0 |
| adversarial_15% | complete | 1,2,3,4,5,6,7,8 | 15.4% | 0.770 | 84.3% | 0.696 | 0.850 | 6.3% | 95.2% | 0 |
| neutral_20% | complete | 1,2,3,4,5,6,7,8 | 20.4% | 0.809 | 88.2% | 0.735 | 0.821 | 8.3% | 93.2% | 1 |
| bad_20% | complete | 1,2,3,4,5,6,7,8 | 20.5% | 0.809 | 90.2% | 0.716 | 0.839 | 5.1% | 95.9% | 0 |
| adversarial_20% | complete | 1,2,3,4,5,6,7,8 | 20.3% | 0.730 | 79.4% | 0.667 | 0.823 | 9.2% | 93.1% | 0 |
| neutral_30% | complete | 1,2,3,4,5,6,7,8 | 30.3% | 0.794 | 88.2% | 0.706 | 0.825 | 8.4% | 93.8% | 1 |
| bad_30% | complete | 1,2,3,4,5,6,7,8 | 30.4% | 0.775 | 87.3% | 0.676 | 0.839 | 5.6% | 96.3% | 0 |
| adversarial_30% | complete | 1,2,3,4,5,6,7,8 | 30.5% | 0.701 | 75.5% | 0.647 | 0.835 | 8.3% | 94.9% | 0 |

### omission

MQM Accuracy > Omission: clause-level removals.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.892 | 92.2% | 0.863 |  |  |  | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 | 5.3% | 0.824 | 89.2% | 0.755 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 | 10.2% | 0.838 | 91.2% | 0.765 |  |  |  | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 | 15.2% | 0.819 | 89.2% | 0.745 |  |  |  | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 | 20.4% | 0.809 | 86.3% | 0.755 |  |  |  | 0 |
| 30% | complete | 1,2,3,4,5,6,7,8 | 30.5% | 0.730 | 82.4% | 0.637 |  |  |  | 1 |

### mistranslation

MQM Accuracy > Mistranslation: same-role phrase substitutions.

Experiment chapters present: `1`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1 |  | 0.909 | 95.5% | 0.864 |  |  |  | 0 |
| 5% | complete | 1 | 5.0% | 0.909 | 95.5% | 0.864 |  |  |  | 0 |
| 10% | complete | 1 | 10.0% | 0.841 | 95.5% | 0.727 |  |  |  | 0 |
| 15% | complete | 1 | 15.0% | 0.864 | 90.9% | 0.818 |  |  |  | 0 |
| 20% | complete | 1 | 20.0% | 0.818 | 86.4% | 0.773 |  |  |  | 0 |
| 30% | complete | 1 | 30.0% | 0.659 | 81.8% | 0.500 |  |  |  | 1 |

### grammar

MQM Fluency > Grammar: rule-based grammar degradation.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.809 | 88.2% | 0.735 | 0.855 | 5.6% | 96.3% | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 | 5.3% | 0.819 | 90.2% | 0.735 | 0.839 | 5.1% | 95.5% | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 | 10.2% | 0.794 | 89.2% | 0.696 | 0.847 | 4.5% | 96.8% | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 | 15.1% | 0.789 | 87.3% | 0.706 | 0.826 | 6.4% | 93.4% | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 | 20.3% | 0.770 | 89.2% | 0.647 | 0.830 | 7.6% | 95.3% | 0 |
| 30% | complete | 1,2,3,4,5,6,7,8 | 30.4% | 0.799 | 86.3% | 0.735 | 0.845 | 7.1% | 95.5% | 0 |

### inconsistency

MQM Inconsistency: separate name/entity and style/register inconsistency.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.799 | 88.2% | 0.716 | 0.855 | 5.6% | 96.3% | 0 |
| name_5% | complete | 1,2,3,4,5,6,7,8 | 5.6% | 0.789 | 89.2% | 0.686 | 0.842 | 7.6% | 93.7% | 1 |
| style_5% | complete | 1,2,3,4,5,6,7,8 | 5.3% | 0.814 | 89.2% | 0.735 | 0.828 | 8.1% | 93.8% | 0 |
| name_10% | complete | 1,2,3,4,5,6,7,8 | 10.3% | 0.819 | 92.2% | 0.716 | 0.844 | 6.9% | 94.3% | 0 |
| style_10% | complete | 1,2,3,4,5,6,7,8 | 7.8% | 0.804 | 90.2% | 0.706 | 0.823 | 9.0% | 93.2% | 0 |
| name_15% | complete | 1,2,3,4,5,6,7,8 | 14.3% | 0.824 | 90.2% | 0.745 | 0.839 | 5.3% | 93.6% | 1 |
| style_15% | complete | 1,2,3,4,5,6,7,8 | 8.5% | 0.833 | 91.2% | 0.755 | 0.817 | 9.6% | 92.9% | 0 |
| name_20% | complete | 1,2,3,4,5,6,7,8 | 18.1% | 0.799 | 89.2% | 0.706 | 0.846 | 6.0% | 94.4% | 1 |
| style_20% | complete | 1,2,3,4,5,6,7,8 | 9.0% | 0.848 | 91.2% | 0.784 | 0.819 | 9.9% | 92.9% | 0 |

### awkward

MQM Style > Awkward: literalized/source-like phrasing replacements.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.838 | 88.2% | 0.794 | 0.855 | 5.6% | 96.5% | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 | 5.4% | 0.809 | 88.2% | 0.735 | 0.830 | 5.9% | 95.3% | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 | 10.5% | 0.794 | 86.3% | 0.725 | 0.829 | 8.6% | 94.6% | 0 |
| 15% | complete | 1,2,3,4,5,6,7,8 | 15.3% | 0.809 | 89.2% | 0.725 | 0.837 | 6.7% | 94.2% | 0 |
| 20% | complete | 1,2,3,4,5,6,7,8 | 20.4% | 0.794 | 89.2% | 0.696 | 0.815 | 9.8% | 92.2% | 1 |
| 30% | complete | 1,2,3,4,5,6,7,8 | 30.0% | 0.799 | 89.2% | 0.706 | 0.826 | 7.5% | 95.2% | 2 |

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
