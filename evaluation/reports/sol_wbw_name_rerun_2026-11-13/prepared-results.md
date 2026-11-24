# Prepared QA results for the corrected Google word-by-word passages

37 of 48 question windows changed. Each was rerun under the original seven multiple-choice configurations and three open-ended configurations. The comparison uses the latest pre-correction experiment with the same stems, choices, keys, model weights and prompts.

## Multiple choice on affected questions

| Reader | Correct, before → after | Correct, % | Gains / losses | Wrong A–D | E | Invalid |
|---|---:|---:|---:|---:|---:|---:|
| llama3.2:1b | 12/37 → 14/37 (+5.4 pp) | 32.4% → 37.8% | 2 / 0 | 21 → 21 | 4 → 2 | 0 → 0 |
| qwen2.5:1.5b | 28/37 → 29/37 (+2.7 pp) | 75.7% → 78.4% | 1 / 0 | 9 → 8 | 0 → 0 | 0 → 0 |
| qwen3:1.7b (thinking) | 27/37 → 31/37 (+10.8 pp) | 73.0% → 83.8% | 5 / 1 | 5 → 4 | 5 → 2 | 0 → 0 |
| qwen3:1.7b (no thinking) | 26/37 → 26/37 (+0.0 pp) | 70.3% → 70.3% | 0 / 0 | 10 → 10 | 1 → 1 | 0 → 0 |
| gemma3:4b | 26/37 → 25/37 (-2.7 pp) | 70.3% → 67.6% | 1 / 2 | 10 → 10 | 1 → 2 | 0 → 0 |
| phi4-mini:3.8b | 28/37 → 27/37 (-2.7 pp) | 75.7% → 73.0% | 1 / 2 | 9 → 10 | 0 → 0 | 0 → 0 |
| qwen2.5:3b | 35/37 → 35/37 (+0.0 pp) | 94.6% → 94.6% | 0 / 0 | 2 → 2 | 0 → 0 | 0 → 0 |
| All configurations | 182/259 → 187/259 (+1.9 pp) | 70.3% → 72.2% | 10 / 5 | 66 → 65 | 11 → 7 | 0 → 0 |

Gains and losses count paired question–configuration responses moving into or out of correctness. E means “cannot tell.” Rates include abstentions and invalid replies in the denominator.

## Open answers on affected questions

| Reader | Full credit, before → after | Full credit, % | Gains / losses of full credit | Partial credit | Zero credit | Mean points, before → after |
|---|---:|---:|---:|---:|---:|---:|
| llama3.2:1b | 4/37 → 12/37 (+21.6 pp) | 10.8% → 32.4% | 8 / 0 | 13 → 5 | 20 → 20 | 0.284 → 0.392 |
| qwen2.5:1.5b | 17/37 → 15/37 (-5.4 pp) | 45.9% → 40.5% | 2 / 4 | 9 → 11 | 11 → 11 | 0.581 → 0.554 |
| qwen3:1.7b (thinking) | 17/37 → 15/37 (-5.4 pp) | 45.9% → 40.5% | 5 / 7 | 9 → 10 | 11 → 12 | 0.581 → 0.541 |
| All configurations | 38/111 → 42/111 (+3.6 pp) | 34.2% → 37.8% | 15 / 11 | 31 → 26 | 42 → 43 | 0.482 → 0.495 |

Full credit is 1 point and partial credit is 0.5. The original scoring procedure translates and judges open answers using GPT-4.1-mini and reuses a grade for the same item and identical answer where available.

## Largest question-level MCQ changes

Counts are correct responses across the seven reader configurations. All ties at either extreme are shown.

| Passage | Question | Before | After | Change |
|---|---|---:|---:|---:|
| Judges 9:44–46 | 示剑楼里的首领进了哪里？ | 5/7 | 7/7 | +2 |
| 1 Kings 13:26–28 | 驴备好后，老先知做了什么？ | 2/7 | 1/7 | -1 |
| 2 Chronicles 26:14–16 | 乌西雅在强盛的时候如何得罪了耶和华他的上帝？ | 4/7 | 3/7 | -1 |
| 2 Samuel 21:20–22 | 谁死在大卫和他臣仆的手下？ | 6/7 | 5/7 | -1 |
| Judges 9:22–24 | 上帝为什么让示剑的首领用欺诈手段对待亚比米勒？ | 7/7 | 6/7 | -1 |
| Judges 9:47–49 | 亚比米勒如何杀死示剑的首领？ | 4/7 | 3/7 | -1 |

## Whole-set word-by-word results

These totals include the 11 question windows whose input stayed identical. Their recorded responses and scores were carried forward.

| Reader | Correct, before → after | Correct, % | Gains / losses | Wrong A–D | E | Invalid |
|---|---:|---:|---:|---:|---:|---:|
| llama3.2:1b | 19/48 → 21/48 (+4.2 pp) | 39.6% → 43.8% | 2 / 0 | 24 → 24 | 5 → 3 | 0 → 0 |
| qwen2.5:1.5b | 37/48 → 38/48 (+2.1 pp) | 77.1% → 79.2% | 1 / 0 | 11 → 10 | 0 → 0 | 0 → 0 |
| qwen3:1.7b (thinking) | 37/48 → 41/48 (+8.3 pp) | 77.1% → 85.4% | 5 / 1 | 5 → 4 | 6 → 3 | 0 → 0 |
| qwen3:1.7b (no thinking) | 35/48 → 35/48 (+0.0 pp) | 72.9% → 72.9% | 0 / 0 | 10 → 10 | 3 → 3 | 0 → 0 |
| gemma3:4b | 37/48 → 36/48 (-2.1 pp) | 77.1% → 75.0% | 1 / 2 | 10 → 10 | 1 → 2 | 0 → 0 |
| phi4-mini:3.8b | 38/48 → 37/48 (-2.1 pp) | 79.2% → 77.1% | 1 / 2 | 10 → 11 | 0 → 0 | 0 → 0 |
| qwen2.5:3b | 45/48 → 45/48 (+0.0 pp) | 93.8% → 93.8% | 0 / 0 | 3 → 3 | 0 → 0 | 0 → 0 |
| All configurations | 248/336 → 253/336 (+1.5 pp) | 73.8% → 75.3% | 10 / 5 | 73 → 72 | 15 → 11 | 0 → 0 |

| Reader | Full credit, before → after | Full credit, % | Gains / losses of full credit | Partial credit | Zero credit | Mean points, before → after |
|---|---:|---:|---:|---:|---:|---:|
| llama3.2:1b | 7/48 → 15/48 (+16.7 pp) | 14.6% → 31.2% | 8 / 0 | 16 → 8 | 25 → 25 | 0.312 → 0.396 |
| qwen2.5:1.5b | 23/48 → 21/48 (-4.2 pp) | 47.9% → 43.8% | 2 / 4 | 10 → 12 | 15 → 15 | 0.583 → 0.562 |
| qwen3:1.7b (thinking) | 22/48 → 20/48 (-4.2 pp) | 45.8% → 41.7% | 5 / 7 | 10 → 11 | 16 → 17 | 0.562 → 0.531 |
| All configurations | 52/144 → 56/144 (+2.8 pp) | 36.1% → 38.9% | 15 / 11 | 36 → 31 | 56 → 57 | 0.486 → 0.497 |

The pooled rates are descriptive. Each question contributes one response per configuration.
