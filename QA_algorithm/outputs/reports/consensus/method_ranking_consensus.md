# Method Ranking & Cross-Model Consensus

_Generated 2026-07-06 · source: `outputs/luke1-8/{model}/{method}/scores_target_llama.json`_

**Metric.** Per item: open answers use the LLM judge score in [0,1]; MCQ items score 1.0 if correct else 0.0. Combined per method as noted below.

**Answer models (ability tiers):** llama3.2:1b < qwen2.5:1.5b < qwen3:1.7b.


## 1. Consensus ranking (mean of the 3 models' per-item scores)

For each item, average the three models' scores (matched items only — all three answered it), pool over Luke 1–8, then mean per method. Best → worst.

| rank | method | consensus | 1b | 1.5b | 1.7b | items |
|---|---|---|---|---|---|---|
| 1 | llm_prompt_high | **0.734** | 0.573 | 0.781 | 0.849 | 192 |
| 2 | nllb-200-1.3B | **0.684** | 0.578 | 0.661 | 0.812 | 192 |
| 3 | llm_prompt_medium | **0.671** | 0.410 | 0.788 | 0.814 | 156 |
| 4 | llm_prompt_low | **0.659** | 0.322 | 0.845 | 0.810 | 174 |
| 5 | nllb-200-distilled-600M | **0.638** | 0.360 | 0.740 | 0.813 | 150 |
| 6 | helsinki | **0.633** | 0.312 | 0.783 | 0.804 | 138 |
| 7 | mBART-50 | **0.596** | 0.351 | 0.655 | 0.782 | 174 |
| 8 | google_word_by_word | **0.550** | 0.293 | 0.649 | 0.707 | 174 |

## 2. Per-model method means (combined accuracy, all available items)

| method | llama1b | qwen1.5b | qwen1.7b |
|---|---|---|---|
| google_word_by_word | 0.255 | 0.633 | 0.694 |
| mBART-50 | 0.311 | 0.649 | 0.751 |
| helsinki | 0.286 | 0.740 | 0.754 |
| nllb-200-distilled-600M | 0.340 | 0.713 | 0.806 |
| llm_prompt_low | 0.329 | 0.793 | 0.770 |
| llm_prompt_medium | 0.373 | 0.751 | 0.792 |
| nllb-200-1.3B | 0.559 | 0.685 | 0.826 |
| llm_prompt_high | 0.550 | 0.772 | 0.852 |

## 3. Pairwise Spearman rho (agreement of method rankings, n=8)

How much two ability tiers agree on the *ordering* of the 8 methods. +1 identical, 0 unrelated, -1 reversed. Separability wants high rho across tiers. At n=8, two-tailed p<0.05 needs |rho| >= ~0.74.

| pair | rho |
|---|---|
| llama1b vs qwen1.5b | +0.381 |
| llama1b vs qwen1.7b | +0.929 |
| qwen1.5b vs qwen1.7b | +0.500 |

## Notes & caveats

- Consensus here is the **unweighted mean** over items and models (equal weight per respondent). Median-across-models or ability/discrimination weighting are alternatives.

- The consensus order is cleaner/more monotonic than any single model, because averaging cancels per-model noise — the argument for an **ensemble** of answer models.

- `llm_prompt_low` ranks higher than its quality warrants; it is inflated by qwen1.5b (0.845) and swings widely across tiers (0.32 / 0.85 / 0.81) — least trustworthy cell.

- Most method×model cells still rest on a **single chapter**; middle-of-table ordering is provisional until the grid is filled. Item counts shown per method.

