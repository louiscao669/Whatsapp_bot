# Answer Model Comparison

Models: llama 1b, 1.5b, 1.7b
Chapters: 1, 2, 3, 4, 5, 6, 7, 8
Methods: google_word_by_word, llm_prompt_high, llm_prompt_low, mBART-50, nllb-200-1.3B

## Overall By Model

| model | item_count | combined_mean | mcq_accuracy | open_llm_mean |
| --- | --- | --- | --- | --- |
| 1.5b | 1020 | 0.7157 | 0.7863 | 0.6451 |
| 1.7b | 1020 | 0.7765 | 0.8765 | 0.6765 |
| llama 1b | 993 | 0.4189 | 0.4493 | 0.3902 |

## By Chapter And Method

| chapter | method | model | item_count | combined_mean | mcq_accuracy | open_llm_mean |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | google_word_by_word | 1.5b | 44 | 0.7500 | 0.9091 | 0.5909 |
| 1 | google_word_by_word | 1.7b | 44 | 0.7955 | 0.9091 | 0.6818 |
| 1 | google_word_by_word | llama 1b | 44 | 0.4091 | 0.3636 | 0.4545 |
| 1 | llm_prompt_high | 1.5b | 44 | 0.9091 | 0.9091 | 0.9091 |
| 1 | llm_prompt_high | 1.7b | 44 | 0.9318 | 0.9545 | 0.9091 |
| 1 | llm_prompt_high | llama 1b | 44 | 0.6136 | 0.6818 | 0.5455 |
| 1 | llm_prompt_low | 1.5b | 44 | 0.9773 | 1.0000 | 0.9545 |
| 1 | llm_prompt_low | 1.7b | 44 | 0.8864 | 0.9091 | 0.8636 |
| 1 | llm_prompt_low | llama 1b | 44 | 0.4318 | 0.3636 | 0.5000 |
| 1 | mBART-50 | 1.5b | 44 | 0.6136 | 0.7727 | 0.4545 |
| 1 | mBART-50 | 1.7b | 44 | 0.8182 | 0.8636 | 0.7727 |
| 1 | mBART-50 | llama 1b | 44 | 0.3864 | 0.3636 | 0.4091 |
| 1 | nllb-200-1.3B | 1.5b | 44 | 0.7045 | 0.8182 | 0.5909 |
| 1 | nllb-200-1.3B | 1.7b | 44 | 0.8636 | 0.9545 | 0.7727 |
| 1 | nllb-200-1.3B | llama 1b | 44 | 0.5909 | 0.7273 | 0.4545 |
| 2 | google_word_by_word | 1.5b | 24 | 0.5833 | 0.7500 | 0.4167 |
| 2 | google_word_by_word | 1.7b | 24 | 0.6250 | 0.8333 | 0.4167 |
| 2 | google_word_by_word | llama 1b | 24 | 0.3333 | 0.4167 | 0.2500 |
| 2 | llm_prompt_high | 1.5b | 24 | 0.7083 | 0.8333 | 0.5833 |
| 2 | llm_prompt_high | 1.7b | 24 | 0.7917 | 0.9167 | 0.6667 |
| 2 | llm_prompt_high | llama 1b | 24 | 0.6250 | 0.8333 | 0.4167 |
| 2 | llm_prompt_low | 1.5b | 24 | 0.7083 | 0.8333 | 0.5833 |
| 2 | llm_prompt_low | 1.7b | 24 | 0.7083 | 0.7500 | 0.6667 |
| 2 | llm_prompt_low | llama 1b | 24 | 0.3750 | 0.3333 | 0.4167 |
| 2 | mBART-50 | 1.5b | 24 | 0.6250 | 0.5833 | 0.6667 |
| 2 | mBART-50 | 1.7b | 24 | 0.7917 | 0.9167 | 0.6667 |
| 2 | mBART-50 | llama 1b | 24 | 0.4583 | 0.3333 | 0.5833 |
| 2 | nllb-200-1.3B | 1.5b | 24 | 0.6250 | 0.7500 | 0.5000 |
| 2 | nllb-200-1.3B | 1.7b | 24 | 0.8750 | 0.9167 | 0.8333 |
| 2 | nllb-200-1.3B | llama 1b | 24 | 0.4583 | 0.5833 | 0.3333 |
| 3 | google_word_by_word | 1.5b | 14 | 0.7857 | 1.0000 | 0.5714 |
| 3 | google_word_by_word | 1.7b | 14 | 0.7857 | 1.0000 | 0.5714 |
| 3 | google_word_by_word | llama 1b | 14 | 0.2857 | 0.2857 | 0.2857 |
| 3 | llm_prompt_high | 1.5b | 14 | 0.8571 | 1.0000 | 0.7143 |
| 3 | llm_prompt_high | 1.7b | 14 | 1.0000 | 1.0000 | 1.0000 |
| 3 | llm_prompt_high | llama 1b | 14 | 0.5000 | 0.7143 | 0.2857 |
| 3 | llm_prompt_low | 1.5b | 14 | 0.9286 | 1.0000 | 0.8571 |
| 3 | llm_prompt_low | 1.7b | 14 | 0.9286 | 1.0000 | 0.8571 |
| 3 | llm_prompt_low | llama 1b | 14 | 0.3571 | 0.5714 | 0.1429 |
| 3 | mBART-50 | 1.5b | 14 | 0.7857 | 1.0000 | 0.5714 |
| 3 | mBART-50 | 1.7b | 14 | 0.7857 | 1.0000 | 0.5714 |
| 3 | mBART-50 | llama 1b | 14 | 0.4286 | 0.2857 | 0.5714 |
| 3 | nllb-200-1.3B | 1.5b | 14 | 0.8571 | 1.0000 | 0.7143 |
| 3 | nllb-200-1.3B | 1.7b | 14 | 0.8571 | 0.8571 | 0.8571 |
| 3 | nllb-200-1.3B | llama 1b | 14 | 0.6429 | 0.5714 | 0.7143 |
| 4 | google_word_by_word | 1.5b | 44 | 0.7273 | 0.8636 | 0.5909 |
| 4 | google_word_by_word | 1.7b | 44 | 0.6364 | 0.6818 | 0.5909 |
| 4 | google_word_by_word | llama 1b | 44 | 0.2500 | 0.2273 | 0.2727 |
| 4 | llm_prompt_high | 1.5b | 44 | 0.7500 | 0.8636 | 0.6364 |
| 4 | llm_prompt_high | 1.7b | 44 | 0.7955 | 0.7727 | 0.8182 |
| 4 | llm_prompt_high | llama 1b | 44 | 0.6136 | 0.6818 | 0.5455 |
| 4 | llm_prompt_low | 1.5b | 44 | 0.8182 | 0.9091 | 0.7273 |
| 4 | llm_prompt_low | 1.7b | 44 | 0.7500 | 0.8636 | 0.6364 |
| 4 | llm_prompt_low | llama 1b | 44 | 0.2500 | 0.2727 | 0.2273 |
| 4 | mBART-50 | 1.5b | 44 | 0.6591 | 0.7727 | 0.5455 |
| 4 | mBART-50 | 1.7b | 44 | 0.7045 | 0.7727 | 0.6364 |
| 4 | mBART-50 | llama 1b | 44 | 0.4091 | 0.3636 | 0.4545 |
| 4 | nllb-200-1.3B | 1.5b | 44 | 0.6136 | 0.7727 | 0.4545 |
| 4 | nllb-200-1.3B | 1.7b | 44 | 0.7045 | 0.8636 | 0.5455 |
| 4 | nllb-200-1.3B | llama 1b | 44 | 0.6364 | 0.7273 | 0.5455 |
| 5 | google_word_by_word | 1.5b | 26 | 0.6923 | 0.8462 | 0.5385 |
| 5 | google_word_by_word | 1.7b | 26 | 0.6154 | 0.7692 | 0.4615 |
| 5 | google_word_by_word | llama 1b | 26 | 0.2308 | 0.0769 | 0.3846 |
| 5 | llm_prompt_high | 1.5b | 26 | 0.8462 | 0.9231 | 0.7692 |
| 5 | llm_prompt_high | 1.7b | 26 | 0.8077 | 0.9231 | 0.6923 |
| 5 | llm_prompt_high | llama 1b | 26 | 0.5385 | 0.6923 | 0.3846 |
| 5 | llm_prompt_low | 1.5b | 26 | 0.8846 | 0.9231 | 0.8462 |
| 5 | llm_prompt_low | 1.7b | 26 | 0.6154 | 0.6923 | 0.5385 |
| 5 | llm_prompt_low | llama 1b | 26 | 0.2308 | 0.0769 | 0.3846 |
| 5 | mBART-50 | 1.5b | 26 | 0.6923 | 0.6923 | 0.6923 |
| 5 | mBART-50 | 1.7b | 26 | 0.7692 | 0.8462 | 0.6923 |
| 5 | mBART-50 | llama 1b | 26 | 0.1538 | 0.1538 | 0.1538 |
| 5 | nllb-200-1.3B | 1.5b | 26 | 0.8077 | 0.8462 | 0.7692 |
| 5 | nllb-200-1.3B | 1.7b | 26 | 0.9231 | 1.0000 | 0.8462 |
| 5 | nllb-200-1.3B | llama 1b | 26 | 0.5769 | 0.5385 | 0.6154 |
| 6 | google_word_by_word | 1.5b | 16 | 0.7500 | 1.0000 | 0.5000 |
| 6 | google_word_by_word | 1.7b | 16 | 0.8750 | 1.0000 | 0.7500 |
| 6 | google_word_by_word | llama 1b | 16 | 0.2500 | 0.2500 | 0.2500 |
| 6 | llm_prompt_high | 1.5b | 16 | 0.9375 | 1.0000 | 0.8750 |
| 6 | llm_prompt_high | 1.7b | 16 | 0.8750 | 1.0000 | 0.7500 |

## Largest Item-Level Disagreements

| chapter | method | item_index | q_type | passage_reference | score_range | llama 1b_score | 1.5b_score | 1.7b_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | google_word_by_word | 2 | mcq | 文本甲 1:4 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 3 | open | 文本甲 1:6 | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| 1 | google_word_by_word | 6 | mcq | 文本甲 1:7 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 9 | open | 文本甲 1:12 | 1.0000 | 0.0000 | 0.0000 | 1.0000 |
| 1 | google_word_by_word | 12 | mcq | 文本甲 1:13 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 14 | mcq | 文本甲 1:16 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 15 | open | 文本甲 1:17 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| 1 | google_word_by_word | 17 | open | 文本甲 1:20 | 1.0000 | 0.0000 | 0.0000 | 1.0000 |
| 1 | google_word_by_word | 20 | mcq | 文本甲 1:27 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 22 | mcq | 文本甲 1:31 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 23 | open | 文本甲 1:33 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| 1 | google_word_by_word | 25 | open | 文本甲 1:35 | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| 1 | google_word_by_word | 26 | mcq | 文本甲 1:35 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 27 | open | 文本甲 1:35 (#2) | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 28 | mcq | 文本甲 1:35 (#2) | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| 1 | google_word_by_word | 29 | open | 文本甲 1:41 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 30 | mcq | 文本甲 1:41 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 32 | mcq | 文本甲 1:42 | 1.0000 | 0.0000 | 0.0000 | 1.0000 |
| 1 | google_word_by_word | 34 | mcq | 文本甲 1:63 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 37 | open | 文本甲 1:66 | 1.0000 | 1.0000 | 0.0000 | 0.0000 |
| 1 | google_word_by_word | 38 | mcq | 文本甲 1:66 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 41 | open | 文本甲 1:77 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 42 | mcq | 文本甲 1:77 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 43 | open | 文本甲 1:80 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | google_word_by_word | 44 | mcq | 文本甲 1:80 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | llm_prompt_high | 1 | open | 文本甲 1:4 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | llm_prompt_high | 3 | open | 文本甲 1:6 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | llm_prompt_high | 6 | mcq | 文本甲 1:7 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | llm_prompt_high | 9 | open | 文本甲 1:12 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
| 1 | llm_prompt_high | 15 | open | 文本甲 1:17 | 1.0000 | 0.0000 | 1.0000 | 1.0000 |
