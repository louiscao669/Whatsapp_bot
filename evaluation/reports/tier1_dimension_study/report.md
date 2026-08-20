# Tier-1 Gold-72 dimension study

Dimension coverage: **72/72 items**; requested runs per item: **3**; aggregate complete: **True**.

## Scoring reliability

| Dimension | ICC(2,1) | ICC(2,k) | Mean pairwise Spearman |
|---|---:|---:|---:|
| structure_dependence | 0.783 | 0.915 | 0.751 |
| statement_uniqueness | 0.829 | 0.936 | 0.572 |
| answer_certainty | 0.804 | 0.925 | 0.795 |
| centrality | 0.794 | 0.921 | 0.736 |

## Structure dependence versus sensitivity

| Family | Outcome | n | Spearman rho | Passage-clustered 95% CI | Permutation p | BH q |
|---|---|---:|---:|---:|---:|---:|
| omission | s_i | 72 | -0.033 | [-0.332, 0.289] | 0.7896 | 0.9976 |
| omission | p | 72 | 0.040 | [-0.216, 0.344] | 0.7407 | 0.9976 |
| omission | neg_log10_p | 72 | -0.040 | [-0.344, 0.216] | 0.7407 | 0.9976 |
| mistranslation | s_i | 72 | 0.015 | [-0.270, 0.387] | 0.9050 | 0.9976 |
| mistranslation | p | 72 | -0.107 | [-0.447, 0.182] | 0.3773 | 0.9976 |
| mistranslation | neg_log10_p | 72 | 0.107 | [-0.182, 0.447] | 0.3773 | 0.9976 |
| adversarial | s_i | 72 | -0.132 | [-0.272, -0.010] | 0.3053 | 0.9976 |
| adversarial | p | 72 | -0.044 | [-0.264, 0.202] | 0.7291 | 0.9976 |
| adversarial | neg_log10_p | 72 | 0.044 | [-0.202, 0.264] | 0.7291 | 0.9976 |

## Gate coverage

- adversarial: 10/72 pass p <= 0.1 and s_i > 0
- mistranslation: 11/72 pass p <= 0.1 and s_i > 0
- omission: 17/72 pass p <= 0.1 and s_i > 0

## Interpretation rules

- A positive correlation with `s_i` means higher rubric scores accompany greater translation sensitivity.
- A negative correlation with raw `p` means higher rubric scores accompany stronger dose-response evidence. `neg_log10_p` is the same ordering with the intuitive sign.
- Correlations use all items. They are not filtered to p-gated items, which would condition on the outcome and bias the estimates.
- Confidence intervals resample whole passages; permutation tests shuffle dimension scores within passages. This accounts conservatively for overlapping windows and shared passage context.
- BH q-values cover the nonredundant `s_i` and `neg_log10_p` tests across four dimensions and three families. Raw-p rows reuse the corresponding evidence q-value.

## Limitation

The 72 questions were selected partly using p/s_i. These are exploratory, post-selection associations, not an independent validation of the rubric. Confirm any promising structural-dependence result on held-out questions or a newly collected grid.
