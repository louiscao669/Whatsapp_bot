# Synthetic Perturbation Results Report

Score file: `scores_target_llama.json`

This report aggregates whatever scored perturbation outputs currently exist.
Blank experiments are wired into the table and can be filled by rerunning the script after their runs finish.

## High-Level Notes

- `addition` baseline combined score is 0.828; lowest scored variant is `adversarial_30%` at 0.701 (-0.127 vs baseline).
- `omission` baseline combined score is 0.868; lowest scored variant is `30%` at 0.716 (-0.152 vs baseline).
- `mistranslation` baseline combined score is 0.843; lowest scored variant is `30%` at 0.681 (-0.162 vs baseline).
- `grammar` baseline combined score is 0.799; lowest scored variant is `20%` at 0.760 (-0.039 vs baseline).
- `local_inconsistency` has scored variants; best observed combined score is `style_5%` at 0.863.
- `awkward` baseline combined score is 0.833; lowest scored variant is `10%` at 0.784 (-0.049 vs baseline).

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
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.868 | 90.2% | 0.833 |  |  |  | 1 |
| 5% | complete | 1,2,3,4,5,6,7,8 | 5.3% | 0.814 | 89.2% | 0.735 |  |  |  | 1 |
| 10% | complete | 1,2,3,4,5,6,7,8 | 10.2% | 0.828 | 91.2% | 0.745 |  |  |  | 1 |
| 15% | complete | 1,2,3,4,5,6,7,8 | 15.2% | 0.789 | 87.3% | 0.706 |  |  |  | 2 |
| 20% | complete | 1,2,3,4,5,6,7,8 | 20.4% | 0.784 | 85.3% | 0.716 |  |  |  | 2 |
| 30% | complete | 1,2,3,4,5,6,7,8 | 30.5% | 0.716 | 82.4% | 0.608 |  |  |  | 2 |

### mistranslation

MQM Accuracy > Mistranslation: same-role phrase substitutions.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.843 | 94.1% | 0.745 |  |  |  | 0 |
| 5% | complete | 1,2,3,4,5,6,7,8 | 5.0% | 0.819 | 92.2% | 0.716 |  |  |  | 0 |
| 10% | complete | 1,2,3,4,5,6,7,8 | 10.0% | 0.819 | 94.1% | 0.696 |  |  |  | 1 |
| 15% | complete | 1,2,3,4,5,6,7,8 | 15.0% | 0.740 | 87.3% | 0.608 |  |  |  | 1 |
| 20% | complete | 1,2,3,4,5,6,7,8 | 20.0% | 0.740 | 85.3% | 0.627 |  |  |  | 1 |
| 30% | complete | 1,2,3,4,5,6,7,8 | 29.5% | 0.681 | 82.4% | 0.539 |  |  |  | 1 |

### grammar

MQM Fluency > Grammar: rule-based grammar degradation.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.799 | 87.3% | 0.725 | 0.852 | 5.7% | 96.1% | 1 |
| 5% | complete | 1,2,3,4,5,6,7,8 | 5.3% | 0.799 | 89.2% | 0.706 | 0.833 | 5.5% | 95.2% | 1 |
| 10% | complete | 1,2,3,4,5,6,7,8 | 10.2% | 0.779 | 87.3% | 0.686 | 0.846 | 4.5% | 96.9% | 1 |
| 15% | complete | 1,2,3,4,5,6,7,8 | 15.1% | 0.799 | 86.3% | 0.735 | 0.821 | 6.4% | 93.2% | 1 |
| 20% | complete | 1,2,3,4,5,6,7,8 | 20.3% | 0.760 | 87.3% | 0.647 | 0.823 | 7.4% | 95.3% | 1 |
| 30% | complete | 1,2,3,4,5,6,7,8 | 30.4% | 0.775 | 85.3% | 0.696 | 0.843 | 7.5% | 95.6% | 1 |

### local_inconsistency

MQM Inconsistency: question-local style/register inconsistency inside each QA verse window.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| style_5% | complete | 1,2,3,4,5,6,7,8 | 5.9% | 0.863 | 97.5% | 0.750 | 0.848 | 5.0% | 96.2% | 0 |
| style_10% | complete | 1,2,3,4,5,6,7,8 | 7.4% | 0.838 | 95.0% | 0.725 | 0.846 | 3.8% | 96.2% | 0 |
| style_15% | complete | 1,2,3,4,5,6,7,8 | 8.7% | 0.863 | 97.5% | 0.750 | 0.838 | 6.2% | 95.0% | 0 |
| style_20% | complete | 1,2,3,4,5,6,7,8 | 9.6% | 0.838 | 97.5% | 0.700 | 0.849 | 6.2% | 95.0% | 0 |

### awkward

MQM Style > Awkward: literalized/source-like phrasing replacements.

Experiment chapters present: `1,2,3,4,5,6,7,8`

| Variant | Status | Ch | Actual | Combined | MCQ | Open | Conf | Insuff | Evidence | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0% | complete | 1,2,3,4,5,6,7,8 |  | 0.833 | 87.3% | 0.794 | 0.852 | 5.7% | 96.4% | 1 |
| 5% | complete | 1,2,3,4,5,6,7,8 | 5.4% | 0.824 | 90.2% | 0.745 | 0.828 | 5.7% | 95.6% | 1 |
| 10% | complete | 1,2,3,4,5,6,7,8 | 10.5% | 0.784 | 85.3% | 0.716 | 0.827 | 8.6% | 94.5% | 2 |
| 15% | complete | 1,2,3,4,5,6,7,8 | 15.3% | 0.789 | 86.3% | 0.716 | 0.837 | 6.4% | 94.3% | 2 |
| 20% | complete | 1,2,3,4,5,6,7,8 | 20.4% | 0.804 | 88.2% | 0.725 | 0.806 | 10.8% | 91.7% | 2 |
| 30% | complete | 1,2,3,4,5,6,7,8 | 30.0% | 0.799 | 88.2% | 0.716 | 0.822 | 7.3% | 95.5% | 3 |

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
