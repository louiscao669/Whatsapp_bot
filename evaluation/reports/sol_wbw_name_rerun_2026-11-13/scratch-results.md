# From-scratch QA results for the corrected Google word-by-word passages

49 of 66 question windows changed. Each was rerun under the original seven multiple-choice configurations and three open-ended configurations. The comparison uses the latest pre-correction experiment with the same stems, choices, keys, model weights and prompts.

## Multiple choice on affected questions

| Reader | Correct, before → after | Correct, % | Gains / losses | Wrong A–D | E | Invalid |
|---|---:|---:|---:|---:|---:|---:|
| llama3.2:1b | 14/49 → 15/49 (+2.0 pp) | 28.6% → 30.6% | 3 / 2 | 29 → 26 | 6 → 8 | 0 → 0 |
| qwen2.5:1.5b | 29/49 → 31/49 (+4.1 pp) | 59.2% → 63.3% | 3 / 1 | 19 → 17 | 1 → 1 | 0 → 0 |
| qwen3:1.7b (thinking) | 36/49 → 28/49 (-16.3 pp) | 73.5% → 57.1% | 1 / 9 | 6 → 9 | 7 → 11 | 0 → 1 |
| qwen3:1.7b (no thinking) | 22/49 → 26/49 (+8.2 pp) | 44.9% → 53.1% | 5 / 1 | 22 → 20 | 5 → 3 | 0 → 0 |
| gemma3:4b | 25/49 → 27/49 (+4.1 pp) | 51.0% → 55.1% | 3 / 1 | 20 → 19 | 4 → 3 | 0 → 0 |
| phi4-mini:3.8b | 33/49 → 31/49 (-4.1 pp) | 67.3% → 63.3% | 1 / 3 | 16 → 18 | 0 → 0 | 0 → 0 |
| qwen2.5:3b | 37/49 → 35/49 (-4.1 pp) | 75.5% → 71.4% | 0 / 2 | 7 → 8 | 5 → 6 | 0 → 0 |
| All configurations | 196/343 → 193/343 (-0.9 pp) | 57.1% → 56.3% | 16 / 19 | 119 → 117 | 28 → 32 | 0 → 1 |

Gains and losses count paired question–configuration responses moving into or out of correctness. E means “cannot tell.” Rates include abstentions and invalid replies in the denominator.

## Open answers on affected questions

| Reader | Full credit, before → after | Full credit, % | Gains / losses of full credit | Partial credit | Zero credit | Mean points, before → after |
|---|---:|---:|---:|---:|---:|---:|
| llama3.2:1b | 7/49 → 6/49 (-2.0 pp) | 14.3% → 12.2% | 3 / 4 | 15 → 17 | 27 → 26 | 0.296 → 0.296 |
| qwen2.5:1.5b | 20/49 → 22/49 (+4.1 pp) | 40.8% → 44.9% | 3 / 1 | 8 → 7 | 21 → 20 | 0.490 → 0.520 |
| qwen3:1.7b (thinking) | 16/49 → 16/49 (+0.0 pp) | 32.7% → 32.7% | 6 / 6 | 9 → 11 | 24 → 22 | 0.418 → 0.439 |
| All configurations | 43/147 → 44/147 (+0.7 pp) | 29.3% → 29.9% | 12 / 11 | 32 → 35 | 72 → 68 | 0.401 → 0.418 |

Full credit is 1 point and partial credit is 0.5. The original scoring procedure translates and judges open answers using GPT-4.1-mini and reuses a grade for the same item and identical answer where available.

## Largest question-level MCQ changes

Counts are correct responses across the seven reader configurations. All ties at either extreme are shown.

| Passage | Question | Before | After | Change |
|---|---|---:|---:|---:|
| Judges 9:46–49 | 进入庙内室的人死于什么？ | 4/7 | 6/7 | +2 |
| 1 Kings 13:20–22 | 谁受到警告，说他死后不能葬在列祖的坟墓里？ | 3/7 | 1/7 | -2 |
| 2 Kings 7:10–11 | 亚兰军队的消息通过守门人传到王宫，消息是什么？ | 3/7 | 1/7 | -2 |

## Whole-set word-by-word results

These totals include the 17 question windows whose input stayed identical. Their recorded responses and scores were carried forward.

| Reader | Correct, before → after | Correct, % | Gains / losses | Wrong A–D | E | Invalid |
|---|---:|---:|---:|---:|---:|---:|
| llama3.2:1b | 17/66 → 18/66 (+1.5 pp) | 25.8% → 27.3% | 3 / 2 | 41 → 38 | 8 → 10 | 0 → 0 |
| qwen2.5:1.5b | 40/66 → 42/66 (+3.0 pp) | 60.6% → 63.6% | 3 / 1 | 25 → 23 | 1 → 1 | 0 → 0 |
| qwen3:1.7b (thinking) | 44/66 → 36/66 (-12.1 pp) | 66.7% → 54.5% | 1 / 9 | 10 → 13 | 12 → 16 | 0 → 1 |
| qwen3:1.7b (no thinking) | 32/66 → 36/66 (+6.1 pp) | 48.5% → 54.5% | 5 / 1 | 28 → 26 | 6 → 4 | 0 → 0 |
| gemma3:4b | 36/66 → 38/66 (+3.0 pp) | 54.5% → 57.6% | 3 / 1 | 26 → 25 | 4 → 3 | 0 → 0 |
| phi4-mini:3.8b | 41/66 → 39/66 (-3.0 pp) | 62.1% → 59.1% | 1 / 3 | 25 → 27 | 0 → 0 | 0 → 0 |
| qwen2.5:3b | 47/66 → 45/66 (-3.0 pp) | 71.2% → 68.2% | 0 / 2 | 12 → 13 | 7 → 8 | 0 → 0 |
| All configurations | 257/462 → 254/462 (-0.6 pp) | 55.6% → 55.0% | 16 / 19 | 167 → 165 | 38 → 42 | 0 → 1 |

| Reader | Full credit, before → after | Full credit, % | Gains / losses of full credit | Partial credit | Zero credit | Mean points, before → after |
|---|---:|---:|---:|---:|---:|---:|
| llama3.2:1b | 14/66 → 13/66 (-1.5 pp) | 21.2% → 19.7% | 3 / 4 | 18 → 20 | 34 → 33 | 0.348 → 0.348 |
| qwen2.5:1.5b | 29/66 → 31/66 (+3.0 pp) | 43.9% → 47.0% | 3 / 1 | 13 → 12 | 24 → 23 | 0.538 → 0.561 |
| qwen3:1.7b (thinking) | 22/66 → 22/66 (+0.0 pp) | 33.3% → 33.3% | 6 / 6 | 13 → 15 | 31 → 29 | 0.432 → 0.447 |
| All configurations | 65/198 → 66/198 (+0.5 pp) | 32.8% → 33.3% | 12 / 11 | 44 → 47 | 89 → 85 | 0.439 → 0.452 |

The pooled rates are descriptive. Each question contributes one response per configuration.
