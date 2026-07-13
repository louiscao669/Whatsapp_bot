# Answer Model Comparison

Models: llama 1b, 1.5b, 1.7b
Chapters: 1, 2, 3, 4, 5, 6, 7, 8
Methods: google_word_by_word, helsinki, llm_prompt_high, llm_prompt_low, llm_prompt_medium, mBART-50, nllb-200-1.3B, nllb-200-distilled-600M

## Overall By Model

| model | item_count | combined_mean | mcq_accuracy | open_llm_mean |
| --- | --- | --- | --- | --- |
| 1.5b | 1632 | 0.7086 | 0.7904 | 0.6268 |
| 1.7b | 1632 | 0.7525 | 0.8762 | 0.6287 |
| llama 1b | 1578 | 0.3736 | 0.3842 | 0.3630 |

## By Chapter And Method

| chapter | method | model | item_count | combined_mean | mcq_accuracy | open_llm_mean |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | google_word_by_word | 1.5b | 44 | 0.6364 | 0.9091 | 0.3636 |
| 1 | google_word_by_word | 1.7b | 44 | 0.7841 | 0.9091 | 0.6591 |
| 1 | google_word_by_word | llama 1b | 44 | 0.3864 | 0.3636 | 0.4091 |
| 1 | helsinki | 1.5b | 44 | 0.8864 | 1.0000 | 0.7727 |
| 1 | helsinki | 1.7b | 44 | 0.7727 | 0.9091 | 0.6364 |
| 1 | helsinki | llama 1b | 44 | 0.3750 | 0.3182 | 0.4318 |
| 1 | llm_prompt_high | 1.5b | 44 | 0.8182 | 0.9091 | 0.7273 |
| 1 | llm_prompt_high | 1.7b | 44 | 0.8864 | 0.9545 | 0.8182 |
| 1 | llm_prompt_high | llama 1b | 44 | 0.5795 | 0.6818 | 0.4773 |
| 1 | llm_prompt_low | 1.5b | 44 | 0.9205 | 1.0000 | 0.8409 |
| 1 | llm_prompt_low | 1.7b | 44 | 0.8636 | 0.9091 | 0.8182 |
| 1 | llm_prompt_low | llama 1b | 44 | 0.3864 | 0.3636 | 0.4091 |
| 1 | llm_prompt_medium | 1.5b | 44 | 0.7727 | 0.9091 | 0.6364 |
| 1 | llm_prompt_medium | 1.7b | 44 | 0.8295 | 0.8636 | 0.7955 |
| 1 | llm_prompt_medium | llama 1b | 44 | 0.4205 | 0.3636 | 0.4773 |
| 1 | mBART-50 | 1.5b | 44 | 0.6818 | 0.7727 | 0.5909 |
| 1 | mBART-50 | 1.7b | 44 | 0.7727 | 0.8636 | 0.6818 |
| 1 | mBART-50 | llama 1b | 44 | 0.4432 | 0.3636 | 0.5227 |
| 1 | nllb-200-1.3B | 1.5b | 44 | 0.7159 | 0.8182 | 0.6136 |
| 1 | nllb-200-1.3B | 1.7b | 44 | 0.8409 | 0.9545 | 0.7273 |
| 1 | nllb-200-1.3B | llama 1b | 44 | 0.5568 | 0.7273 | 0.3864 |
| 1 | nllb-200-distilled-600M | 1.5b | 44 | 0.7955 | 0.8182 | 0.7727 |
| 1 | nllb-200-distilled-600M | 1.7b | 44 | 0.7955 | 0.9091 | 0.6818 |
| 1 | nllb-200-distilled-600M | llama 1b | 44 | 0.3977 | 0.2727 | 0.5227 |
| 2 | google_word_by_word | 1.5b | 24 | 0.5000 | 0.7500 | 0.2500 |
| 2 | google_word_by_word | 1.7b | 24 | 0.6458 | 0.8333 | 0.4583 |
| 2 | google_word_by_word | llama 1b | 24 | 0.3333 | 0.4167 | 0.2500 |
| 2 | helsinki | 1.5b | 24 | 0.7292 | 0.8333 | 0.6250 |
| 2 | helsinki | 1.7b | 24 | 0.6667 | 0.8333 | 0.5000 |
| 2 | helsinki | llama 1b | 24 | 0.1667 | 0.0833 | 0.2500 |
| 2 | llm_prompt_high | 1.5b | 24 | 0.6250 | 0.8333 | 0.4167 |
| 2 | llm_prompt_high | 1.7b | 24 | 0.7500 | 0.9167 | 0.5833 |
| 2 | llm_prompt_high | llama 1b | 24 | 0.5417 | 0.8333 | 0.2500 |
| 2 | llm_prompt_low | 1.5b | 24 | 0.7292 | 0.8333 | 0.6250 |
| 2 | llm_prompt_low | 1.7b | 24 | 0.6875 | 0.7500 | 0.6250 |
| 2 | llm_prompt_low | llama 1b | 24 | 0.3542 | 0.3333 | 0.3750 |
| 2 | llm_prompt_medium | 1.5b | 24 | 0.7292 | 0.8333 | 0.6250 |
| 2 | llm_prompt_medium | 1.7b | 24 | 0.6875 | 0.8333 | 0.5417 |
| 2 | llm_prompt_medium | llama 1b | 24 | 0.3333 | 0.3333 | 0.3333 |
| 2 | mBART-50 | 1.5b | 24 | 0.6458 | 0.5833 | 0.7083 |
| 2 | mBART-50 | 1.7b | 24 | 0.6667 | 0.9167 | 0.4167 |
| 2 | mBART-50 | llama 1b | 24 | 0.3333 | 0.3333 | 0.3333 |
| 2 | nllb-200-1.3B | 1.5b | 24 | 0.6667 | 0.7500 | 0.5833 |
| 2 | nllb-200-1.3B | 1.7b | 24 | 0.7708 | 0.9167 | 0.6250 |
| 2 | nllb-200-1.3B | llama 1b | 24 | 0.4375 | 0.5833 | 0.2917 |
| 2 | nllb-200-distilled-600M | 1.5b | 24 | 0.7083 | 0.6667 | 0.7500 |
| 2 | nllb-200-distilled-600M | 1.7b | 24 | 0.7500 | 1.0000 | 0.5000 |
| 2 | nllb-200-distilled-600M | llama 1b | 24 | 0.3750 | 0.4167 | 0.3333 |
| 3 | google_word_by_word | 1.5b | 14 | 0.7143 | 1.0000 | 0.4286 |
| 3 | google_word_by_word | 1.7b | 14 | 0.7857 | 1.0000 | 0.5714 |
| 3 | google_word_by_word | llama 1b | 14 | 0.2500 | 0.2857 | 0.2143 |
| 3 | helsinki | 1.5b | 14 | 0.7500 | 0.8571 | 0.6429 |
| 3 | helsinki | 1.7b | 14 | 0.7143 | 0.8571 | 0.5714 |
| 3 | helsinki | llama 1b | 14 | 0.2143 | 0.2857 | 0.1429 |
| 3 | llm_prompt_high | 1.5b | 14 | 0.8929 | 1.0000 | 0.7857 |
| 3 | llm_prompt_high | 1.7b | 14 | 1.0000 | 1.0000 | 1.0000 |
| 3 | llm_prompt_high | llama 1b | 14 | 0.5000 | 0.7143 | 0.2857 |
| 3 | llm_prompt_low | 1.5b | 14 | 0.9643 | 1.0000 | 0.9286 |
| 3 | llm_prompt_low | 1.7b | 14 | 0.9286 | 1.0000 | 0.8571 |
| 3 | llm_prompt_low | llama 1b | 14 | 0.3571 | 0.5714 | 0.1429 |
| 3 | llm_prompt_medium | 1.5b | 14 | 0.8929 | 1.0000 | 0.7857 |
| 3 | llm_prompt_medium | 1.7b | 14 | 0.9643 | 1.0000 | 0.9286 |
| 3 | llm_prompt_medium | llama 1b | 14 | 0.4286 | 0.4286 | 0.4286 |
| 3 | mBART-50 | 1.5b | 14 | 0.7500 | 1.0000 | 0.5000 |
| 3 | mBART-50 | 1.7b | 14 | 0.6786 | 1.0000 | 0.3571 |
| 3 | mBART-50 | llama 1b | 14 | 0.4286 | 0.2857 | 0.5714 |
| 3 | nllb-200-1.3B | 1.5b | 14 | 0.9286 | 1.0000 | 0.8571 |
| 3 | nllb-200-1.3B | 1.7b | 14 | 0.8214 | 0.8571 | 0.7857 |
| 3 | nllb-200-1.3B | llama 1b | 14 | 0.6429 | 0.5714 | 0.7143 |
| 3 | nllb-200-distilled-600M | 1.5b | 14 | 0.8929 | 0.8571 | 0.9286 |
| 3 | nllb-200-distilled-600M | 1.7b | 14 | 0.8571 | 1.0000 | 0.7143 |
| 3 | nllb-200-distilled-600M | llama 1b | 14 | 0.2857 | 0.4286 | 0.1429 |
| 4 | google_word_by_word | 1.5b | 44 | 0.6818 | 0.8636 | 0.5000 |
| 4 | google_word_by_word | 1.7b | 44 | 0.6250 | 0.6818 | 0.5682 |
| 4 | google_word_by_word | llama 1b | 44 | 0.2500 | 0.2273 | 0.2727 |
| 4 | helsinki | 1.5b | 44 | 0.7159 | 0.9091 | 0.5227 |
| 4 | helsinki | 1.7b | 44 | 0.5000 | 0.5909 | 0.4091 |
| 4 | helsinki | llama 1b | 44 | 0.3182 | 0.3636 | 0.2727 |
| 4 | llm_prompt_high | 1.5b | 44 | 0.7386 | 0.8636 | 0.6136 |
| 4 | llm_prompt_high | 1.7b | 44 | 0.8068 | 0.7727 | 0.8409 |

## Largest Item-Level Disagreements

| chapter | method | item_index | q_type | passage_reference | score_range | llama 1b_score | 1.5b_score | 1.7b_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | google_word_by_word | 2 | mcq | 文本甲 1:4 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 6 | mcq | 文本甲 1:7 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 12 | mcq | 文本甲 1:13 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 14 | mcq | 文本甲 1:16 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 15 | open | 文本甲 1:17 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| 1 | google_word_by_word | 17 | open | 文本甲 1:20 | 1.0000 | 0.0000 | 0.0000 | 1.0000 |
| 1 | google_word_by_word | 20 | mcq | 文本甲 1:27 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 22 | mcq | 文本甲 1:31 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 25 | open | 文本甲 1:35 | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| 1 | google_word_by_word | 26 | mcq | 文本甲 1:35 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 27 | open | 文本甲 1:35 (#2) | 1.0000 | 0.0000 | 0.0000 | 1.0000 |
| 1 | google_word_by_word | 28 | mcq | 文本甲 1:35 (#2) | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| 1 | google_word_by_word | 29 | open | 文本甲 1:41 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 30 | mcq | 文本甲 1:41 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 32 | mcq | 文本甲 1:42 | 1.0000 | 0.0000 | 0.0000 | 1.0000 |
| 1 | google_word_by_word | 33 | open | 文本甲 1:63 | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| 1 | google_word_by_word | 34 | mcq | 文本甲 1:63 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 38 | mcq | 文本甲 1:66 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 42 | mcq | 文本甲 1:77 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 43 | open | 文本甲 1:80 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 44 | mcq | 文本甲 1:80 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | helsinki | 2 | mcq | 文本甲 1:4 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | helsinki | 4 | mcq | 文本甲 1:6 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | helsinki | 6 | mcq | 文本甲 1:7 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | helsinki | 8 | mcq | 文本甲 1:11 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | helsinki | 13 | open | 文本甲 1:16 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | helsinki | 14 | mcq | 文本甲 1:16 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | helsinki | 15 | open | 文本甲 1:17 | 1.0000 | 0.0000 | 1.0000 | 0.5000 |
| 1 | helsinki | 17 | open | 文本甲 1:20 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | helsinki | 18 | mcq | 文本甲 1:20 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
