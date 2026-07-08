# Item-Level Translation Quality Analysis

Input rows: 4756
Methods: google_word_by_word, helsinki, llm_prompt_high, llm_prompt_low, llm_prompt_medium, mBART-50, nllb-200-1.3B, nllb-200-distilled-600M
Models: llama1b, qwen1.5b, qwen1.7b
Unique chapter-items: 204
Missing method/model/item cells: 140
Balanced rows used for fair rank tests: 2616

## Main Takeaway

- Best method on all available rows: `llm_prompt_high` at 0.734.
- Best method on the balanced item grid: `llm_prompt_high` at 0.777.
- Rank invariance across answer models: no; minimum pairwise Spearman rho is 0.563.
- Because rankings change by answer model, item-level QA score is not a pure translation-quality measure; it includes method × answerer interaction.

## Method Summary, All Available Rows

| method | row_count | mean_score | open_mean | mcq_mean | open_count | mcq_count |
| --- | --- | --- | --- | --- | --- | --- |
| llm_prompt_high | 612 | 0.734 | 0.647 | 0.820 | 306 | 306 |
| nllb-200-1.3B | 612 | 0.688 | 0.611 | 0.765 | 306 | 306 |
| llm_prompt_medium | 585 | 0.653 | 0.599 | 0.708 | 297 | 288 |
| llm_prompt_low | 603 | 0.642 | 0.614 | 0.670 | 306 | 297 |
| nllb-200-distilled-600M | 579 | 0.625 | 0.588 | 0.663 | 294 | 285 |
| helsinki | 559 | 0.599 | 0.556 | 0.644 | 284 | 275 |
| mBART-50 | 603 | 0.582 | 0.533 | 0.633 | 306 | 297 |
| google_word_by_word | 603 | 0.547 | 0.448 | 0.650 | 306 | 297 |

## Method Summary, Balanced Grid

| method | row_count | mean_score | open_mean | mcq_mean | open_count | mcq_count |
| --- | --- | --- | --- | --- | --- | --- |
| llm_prompt_high | 327 | 0.777 | 0.703 | 0.852 | 165 | 162 |
| nllb-200-1.3B | 327 | 0.743 | 0.691 | 0.796 | 165 | 162 |
| llm_prompt_low | 327 | 0.694 | 0.675 | 0.715 | 169 | 158 |
| llm_prompt_medium | 327 | 0.676 | 0.645 | 0.709 | 169 | 158 |
| helsinki | 327 | 0.654 | 0.621 | 0.690 | 169 | 158 |
| nllb-200-distilled-600M | 327 | 0.642 | 0.598 | 0.690 | 169 | 158 |
| google_word_by_word | 327 | 0.590 | 0.497 | 0.690 | 169 | 158 |
| mBART-50 | 327 | 0.581 | 0.515 | 0.652 | 169 | 158 |

## Chapter Summary

| chapter | row_count | mean_score | open_mean | mcq_mean |
| --- | --- | --- | --- | --- |
| luke6 | 384 | 0.714 | 0.620 | 0.807 |
| luke1 | 1056 | 0.705 | 0.667 | 0.744 |
| luke3 | 336 | 0.705 | 0.619 | 0.792 |
| luke4 | 1012 | 0.618 | 0.543 | 0.692 |
| luke5 | 624 | 0.614 | 0.583 | 0.644 |
| luke2 | 552 | 0.600 | 0.529 | 0.670 |
| luke8 | 378 | 0.558 | 0.477 | 0.667 |
| luke7 | 414 | 0.510 | 0.488 | 0.531 |

## Model x Method Means

| model | method | row_count | mean_score | open_mean | mcq_mean |
| --- | --- | --- | --- | --- | --- |
| llama1b | llm_prompt_high | 204 | 0.569 | 0.422 | 0.716 |
| llama1b | nllb-200-1.3B | 204 | 0.569 | 0.510 | 0.627 |
| llama1b | llm_prompt_medium | 177 | 0.395 | 0.430 | 0.357 |
| llama1b | nllb-200-distilled-600M | 195 | 0.359 | 0.402 | 0.312 |
| llama1b | mBART-50 | 195 | 0.338 | 0.363 | 0.312 |
| llama1b | llm_prompt_low | 195 | 0.323 | 0.363 | 0.280 |
| llama1b | helsinki | 195 | 0.303 | 0.343 | 0.258 |
| llama1b | google_word_by_word | 195 | 0.282 | 0.294 | 0.269 |
| qwen1.5b | llm_prompt_low | 204 | 0.819 | 0.794 | 0.843 |
| qwen1.5b | llm_prompt_high | 204 | 0.784 | 0.745 | 0.824 |
| qwen1.5b | helsinki | 204 | 0.750 | 0.686 | 0.814 |
| qwen1.5b | llm_prompt_medium | 204 | 0.750 | 0.676 | 0.824 |
| qwen1.5b | nllb-200-distilled-600M | 204 | 0.730 | 0.706 | 0.755 |
| qwen1.5b | nllb-200-1.3B | 204 | 0.676 | 0.598 | 0.755 |
| qwen1.5b | google_word_by_word | 204 | 0.657 | 0.520 | 0.794 |
| qwen1.5b | mBART-50 | 204 | 0.642 | 0.569 | 0.716 |
| qwen1.7b | llm_prompt_high | 204 | 0.848 | 0.775 | 0.922 |
| qwen1.7b | nllb-200-1.3B | 204 | 0.819 | 0.725 | 0.912 |
| qwen1.7b | nllb-200-distilled-600M | 180 | 0.794 | 0.667 | 0.922 |
| qwen1.7b | llm_prompt_medium | 204 | 0.779 | 0.676 | 0.882 |
| qwen1.7b | llm_prompt_low | 204 | 0.770 | 0.686 | 0.853 |
| qwen1.7b | helsinki | 160 | 0.769 | 0.662 | 0.875 |
| qwen1.7b | mBART-50 | 204 | 0.755 | 0.667 | 0.843 |
| qwen1.7b | google_word_by_word | 204 | 0.691 | 0.529 | 0.853 |

## Rank Stability Across Answer Models, Balanced Grid

| model | rank_order |
| --- | --- |
| llama1b | nllb-200-1.3B > llm_prompt_high > llm_prompt_medium > llm_prompt_low > helsinki > nllb-200-distilled-600M > mBART-50 > google_word_by_word |
| qwen1.5b | llm_prompt_low > llm_prompt_high > helsinki > llm_prompt_medium > nllb-200-1.3B=nllb-200-distilled-600M > google_word_by_word > mBART-50 |
| qwen1.7b | llm_prompt_high > nllb-200-1.3B > llm_prompt_medium > llm_prompt_low > nllb-200-distilled-600M > helsinki > mBART-50 > google_word_by_word |

| model_a | model_b | method_count | spearman_rho | order_a | order_b |
| --- | --- | --- | --- | --- | --- |
| llama1b | qwen1.5b | 8 | 0.563 | nllb-200-1.3B > llm_prompt_high > llm_prompt_medium > llm_prompt_low > helsinki > nllb-200-distilled-600M > mBART-50 > google_word_by_word | llm_prompt_low > llm_prompt_high > helsinki > llm_prompt_medium > nllb-200-1.3B=nllb-200-distilled-600M > google_word_by_word > mBART-50 |
| llama1b | qwen1.7b | 8 | 0.952 | nllb-200-1.3B > llm_prompt_high > llm_prompt_medium > llm_prompt_low > helsinki > nllb-200-distilled-600M > mBART-50 > google_word_by_word | llm_prompt_high > nllb-200-1.3B > llm_prompt_medium > llm_prompt_low > nllb-200-distilled-600M > helsinki > mBART-50 > google_word_by_word |
| qwen1.5b | qwen1.7b | 8 | 0.587 | llm_prompt_low > llm_prompt_high > helsinki > llm_prompt_medium > nllb-200-1.3B=nllb-200-distilled-600M > google_word_by_word > mBART-50 | llm_prompt_high > nllb-200-1.3B > llm_prompt_medium > llm_prompt_low > nllb-200-distilled-600M > helsinki > mBART-50 > google_word_by_word |

## Hardest Items

| chapter | item_index | q_type | reference | mean_score | zero_rate | question |
| --- | --- | --- | --- | --- | --- | --- |
| luke8 | 17 | open | 文本甲 8:55 | 0.111 | 0.889 | 人物己在人物05家做了什么？ |
| luke1 | 18 | mcq | 文本甲 1:20 | 0.125 | 0.875 | 因不信，人物甲发生了什么？ |
| luke2 | 22 | mcq | 文本甲 2:46 | 0.130 | 0.870 | 人物己的父母在哪里找到他？ |
| luke5 | 21 | open | Luke 5:35 | 0.167 | 0.833 | 人物己的门徒什么时候禁食？ |
| luke8 | 6 | open | Luke 8:21 | 0.167 | 0.833 | 人物己的母亲和兄弟是谁？ |
| luke8 | 16 | mcq | 文本甲 8:48 | 0.167 | 0.833 | 是什么医治了流血的妇人？ |
| luke1 | 37 | open | 文本甲 1:66 | 0.208 | 0.792 | 大家对孩子有什么认识？ |
| luke5 | 3 | open | Luke 5:5 | 0.208 | 0.792 | 尽管一无所获，彼得做了什么？ |
| luke2 | 3 | open | 文本甲 2:7 | 0.217 | 0.783 | 人物丁把她刚出生的儿子放在哪里？ |
| luke4 | 43 | open | Luke 4:41 | 0.217 | 0.783 | 恶魔被驱逐时说什么？ |
| luke1 | 31 | open | 文本甲 1:42 | 0.250 | 0.750 | 人物乙说谁是蒙福的？ |
| luke6 | 5 | open | Luke 6:23 | 0.250 | 0.750 | 根据人物己，为什么人们应该喜乐？ |

## Most Method-Sensitive Items

| chapter | item_index | q_type | reference | method_score_range | question | method_order |
| --- | --- | --- | --- | --- | --- | --- |
| luke1 | 19 | open | 文本甲 1:27 | 1.000 | 六个月后，使者乙访问了谁？ | llm_prompt_low > llm_prompt_high=llm_prompt_medium=mBART-50=nllb-200-distilled-600M > helsinki > google_word_by_word=nllb-200-1.3B |
| luke1 | 21 | open | 文本甲 1:31 | 1.000 | 人物丁会发生什么事？ | llm_prompt_high=llm_prompt_low=nllb-200-1.3B=nllb-200-distilled-600M > helsinki > google_word_by_word=llm_prompt_medium=mBART-50 |
| luke1 | 29 | open | 文本甲 1:41 | 1.000 | 当人物丁问候人物乙时，人物乙的宝宝做了什么？ | helsinki=llm_prompt_low=llm_prompt_medium > google_word_by_word=llm_prompt_high=nllb-200-1.3B=nllb-200-distilled-600M > mBART-50 |
| luke2 | 14 | mcq | 文本甲 2:22 | 1.000 | 人物戊和人物丁为什么带人物己去场所甲？ | llm_prompt_high=nllb-200-1.3B > google_word_by_word=helsinki=llm_prompt_low=llm_prompt_medium=mBART-50 > nllb-200-distilled-600M |
| luke2 | 23 | open | 文本甲 2:49 | 1.000 | 人物己如何回答人物丁关于寻找他的事？ | helsinki > llm_prompt_high=llm_prompt_low=nllb-200-1.3B > nllb-200-distilled-600M > llm_prompt_medium=mBART-50 > google_word_by_word |
| luke3 | 9 | open | Luke 3:16 | 1.000 | 人物丙 说 有人 会 用 什么 施洗？ | nllb-200-1.3B > llm_prompt_high=llm_prompt_low=llm_prompt_medium=nllb-200-distilled-600M > google_word_by_word=helsinki > mBART-50 |
| luke3 | 11 | open | Luke 3:22 | 1.000 | 人物己 受洗后 谁 从 天 降下？ | llm_prompt_medium=mBART-50=nllb-200-1.3B > llm_prompt_high=nllb-200-distilled-600M > llm_prompt_low > google_word_by_word=helsinki |
| luke4 | 5 | open | Luke 4:3 | 1.000 | 魔鬼挑战耶稣做什么？ | llm_prompt_low > google_word_by_word=mBART-50=nllb-200-distilled-600M > llm_prompt_high=llm_prompt_medium=nllb-200-1.3B > helsinki |
| luke4 | 7 | open | Luke 4:4 | 1.000 | 耶稣对魔鬼的回答是什么？ | llm_prompt_high=llm_prompt_low=llm_prompt_medium > google_word_by_word=helsinki=mBART-50=nllb-200-1.3B=nllb-200-distilled-600M |
| luke4 | 17 | open | Luke 4:21 | 1.000 | 耶稣说那天实现了什么？ | mBART-50 > llm_prompt_high=nllb-200-distilled-600M > google_word_by_word=llm_prompt_low=llm_prompt_medium=nllb-200-1.3B > helsinki |
| luke4 | 20 | mcq | Luke 4:24 | 1.000 | 先知在本国受到什么样的接待？ | llm_prompt_low > mBART-50=nllb-200-1.3B > helsinki > llm_prompt_medium=nllb-200-distilled-600M > google_word_by_word=llm_prompt_high |
| luke4 | 21 | open | Luke 4:28 | 1.000 | 人们如何回应耶稣的榜样？ | nllb-200-distilled-600M > llm_prompt_high=mBART-50=nllb-200-1.3B > google_word_by_word=llm_prompt_low=llm_prompt_medium > helsinki |

## Most Model-Sensitive Items

| chapter | item_index | q_type | reference | model_score_range | question | model_order |
| --- | --- | --- | --- | --- | --- | --- |
| luke2 | 15 | open | 文本甲 2:26 | 1.000 | 灵甲向人物03显明了什么？ | qwen1.7b > qwen1.5b > llama1b |
| luke2 | 24 | mcq | 文本甲 2:49 | 1.000 | 人物己对人物丁说了什么关于寻找他的事？ | qwen1.7b > qwen1.5b > llama1b |
| luke3 | 1 | open | Luke 3:3 | 1.000 | 人物丙 在 约旦 河 周围 传讲 什么 信息？ | qwen1.5b > qwen1.7b > llama1b |
| luke4 | 41 | open | Luke 4:36 | 1.000 | 耶稣驱魔后人们有何反应？ | qwen1.5b=qwen1.7b > llama1b |
| luke5 | 2 | mcq | Luke 5:4 | 1.000 | 人物己 吩咐西门将船划到哪里？ | qwen1.7b > qwen1.5b > llama1b |
| luke5 | 14 | mcq | Luke 5:20 | 1.000 | 人物己对瘫痪的人说了什么？ | qwen1.5b=qwen1.7b > llama1b |
| luke5 | 24 | mcq | Luke 5:37 | 1.000 | 如果新酒装入旧皮袋会发生什么？ | qwen1.5b=qwen1.7b > llama1b |
| luke6 | 4 | mcq | Luke 6:5 | 1.000 | 人物己 为自己宣称什么称号？ | qwen1.5b=qwen1.7b > llama1b |
| luke7 | 12 | mcq | Luke 7:26 | 1.000 | 人物己怎样评价施洗人物丙？ | qwen1.7b > llama1b > qwen1.5b |
| luke8 | 5 | open | Luke 8:15 | 1.000 | 好地上的种子是谁？ | qwen1.5b > qwen1.7b > llama1b |
| luke8 | 17 | open | 文本甲 8:55 | 1.000 | 人物己在人物05家做了什么？ | llama1b > qwen1.5b=qwen1.7b |
| luke1 | 6 | mcq | 文本甲 1:7 | 0.875 | 人物甲和人物乙为什么没有孩子？ | qwen1.5b=qwen1.7b > llama1b |

## Missing Cells

| chapter | method | model | row_count |
| --- | --- | --- | --- |
| luke2 | nllb-200-distilled-600M | qwen1.7b | 24 |
| luke4 | helsinki | qwen1.7b | 44 |
| luke7 | llm_prompt_medium | llama1b | 18 |
| luke8 | google_word_by_word | llama1b | 9 |
| luke8 | helsinki | llama1b | 9 |
| luke8 | llm_prompt_low | llama1b | 9 |
| luke8 | llm_prompt_medium | llama1b | 9 |
| luke8 | mBART-50 | llama1b | 9 |
| luke8 | nllb-200-distilled-600M | llama1b | 9 |
