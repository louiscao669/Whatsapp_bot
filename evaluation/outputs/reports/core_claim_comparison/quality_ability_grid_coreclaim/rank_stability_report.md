# Quality x Ability x Item Rank-Stability Check

Models: llama 1b, 1.5b, 1.7b
Quality methods: google_word_by_word, llm_prompt_high, llm_prompt_low, mBART-50, nllb-200-1.3B
Full scored grid cells: 3033
Balanced item count: 186
Balanced scored cells: 2790

**Verdict:** The quality ranking is not invariant across the selected answerer ability tiers; the QA proxy is entangled with answerer ability and should be corrected before treating it as pure translation quality.

Minimum pairwise Spearman rho: 0.7000

## Method Means On Balanced Grid

| ability_model | quality_method | item_count | mean_score |
| --- | --- | --- | --- |
| 1.5b | google_word_by_word | 186 | 0.6183 |
| 1.5b | llm_prompt_high | 186 | 0.7688 |
| 1.5b | llm_prompt_low | 186 | 0.8280 |
| 1.5b | mBART-50 | 186 | 0.6640 |
| 1.5b | nllb-200-1.3B | 186 | 0.6828 |
| 1.7b | google_word_by_word | 186 | 0.6828 |
| 1.7b | llm_prompt_high | 186 | 0.8656 |
| 1.7b | llm_prompt_low | 186 | 0.7823 |
| 1.7b | mBART-50 | 186 | 0.7177 |
| 1.7b | nllb-200-1.3B | 186 | 0.7742 |
| llama 1b | google_word_by_word | 186 | 0.2742 |
| llama 1b | llm_prompt_high | 186 | 0.5457 |
| llama 1b | llm_prompt_low | 186 | 0.3360 |
| llama 1b | mBART-50 | 186 | 0.3226 |
| llama 1b | nllb-200-1.3B | 186 | 0.5376 |

## Ranking Within Each Ability Tier

| ability_model | rank_order |
| --- | --- |
| 1.5b | llm_prompt_low > llm_prompt_high > nllb-200-1.3B > mBART-50 > google_word_by_word |
| 1.7b | llm_prompt_high > llm_prompt_low > nllb-200-1.3B > mBART-50 > google_word_by_word |
| llama 1b | llm_prompt_high > nllb-200-1.3B > llm_prompt_low > mBART-50 > google_word_by_word |

## Pairwise Rank Agreement

| ability_model_a | ability_model_b | method_count | spearman_rho | same_rank_count | same_rank_fraction | order_a | order_b |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1.5b | 1.7b | 5 | 0.9000 | 3 | 0.6000 | llm_prompt_low > llm_prompt_high > nllb-200-1.3B > mBART-50 > google_word_by_word | llm_prompt_high > llm_prompt_low > nllb-200-1.3B > mBART-50 > google_word_by_word |
| 1.5b | llama 1b | 5 | 0.7000 | 2 | 0.4000 | llm_prompt_low > llm_prompt_high > nllb-200-1.3B > mBART-50 > google_word_by_word | llm_prompt_high > nllb-200-1.3B > llm_prompt_low > mBART-50 > google_word_by_word |
| 1.7b | llama 1b | 5 | 0.9000 | 3 | 0.6000 | llm_prompt_high > llm_prompt_low > nllb-200-1.3B > mBART-50 > google_word_by_word | llm_prompt_high > nllb-200-1.3B > llm_prompt_low > mBART-50 > google_word_by_word |

Interpretation: Spearman rho is computed over method rankings within each answer model. A pure translation-quality proxy should preserve the same method ordering across ability tiers; disagreement means the proxy is partly measuring the answerer's interaction with a translation method.
