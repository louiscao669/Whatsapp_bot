# Quality of the previous and new English QA banks

**I would choose Prepared60 + Hard77 for English open-response answerability.** The independent reader earned full credit on 123/137 intact questions versus 119/137 previously. A second, blinded scoring pass also favored the new bank. Accuracy fell by 44.5 percentage points for the new bank and 46.0 for the previous bank when one verse was removed. The omission comparison gives no clear advantage to either bank.

The comparison uses the 60 projected prepared questions and the revised 77-item hard bank. The previous bank contains all 72 selected prepared IDs and the English source forms corresponding to the 65 active hard IDs. Both pairings contain 137 questions from ten passages. Historical membership came from the selected Gold72 schedule and the active Hard65 evaluation manifest. The prepared questions use their assigned English Berean Standard Bible text. The hard questions use their archived English generator windows. Comparisons within each family use the same source edition.

## Independent reader results

Qwen3 8B answered each exact English question using its assigned verse window. It saw neither the key nor bank identity. It also answered a separate version with one verse removed. Both conditions used the same prompt. Gemma 3 4B graded replies for meaning with the question and key, blind to bank, condition and passage. Exact matches and the standard abstention were scored directly. Each distinct input was answered once and reused everywhere it occurred. The primary score counts a fully correct answer. Partial credit is listed separately.

| Bank | Clean, full credit | One verse omitted, full credit | Accuracy loss (points) | Partial on clean |
|---|---|---|---|---|
| Gold72 | 64/72 (88.9%) | 27/72 (37.5%) | 51.4 | 1 |
| Prepared60 | 56/60 (93.3%) | 26/60 (43.3%) | 50.0 | 0 |
| Hard65 | 55/65 (84.6%) | 29/65 (44.6%) | 40.0 | 3 |
| Hard77 | 67/77 (87.0%) | 36/77 (46.8%) | 40.3 | 4 |
| Previous combined | 119/137 (86.9%) | 56/137 (40.9%) | 46.0 | 4 |
| New combined | 123/137 (89.8%) | 62/137 (45.3%) | 44.5 | 4 |

The pooled clean accuracy difference was +2.9 percentage points (paired ten-passage bootstrap range -0.8 to +7.2). The between-bank difference in accuracy loss under omission was -1.5 points (range -6.0 to +4.0). These 95% percentile ranges resample passages in pairs across banks, using 10,000 draws. They describe variation across these passages for this reader and grader.

A fixed hash of passage ID and verse labels chose the verse to remove before any response was collected. It used neither the question nor the key, so the omitted verse sometimes left all answer evidence intact. Matching windows lost the same verse. This tests one type of information loss on English text. The two conditions did not vary translation language, grammaticality or mistranslation severity.

## Previous editorial and answerability evidence

The blind check used GPT-5. Two GPT-5.6 Sol reviews judged the question and key on their own window. Prepared questions could be straightforward factual questions. Hard questions were also expected to test a meaningful distinction. The table scores the old forms as originally selected, and the new forms exactly as finally worded and placed. The new banks were selected using these checks, so the figures measure compliance with their selection rules.

| Bank | Blind answerability | Passed blind and both item reviews |
|---|---|---|
| Gold72 | 45/72 (62.5%) | 29/72 (40.3%) |
| Prepared60 | 60/60 (100.0%) | 60/60 (100.0%) |
| Hard65 | 60/65 (92.3%) | 53/65 (81.5%) |
| Hard77 | 77/77 (100.0%) | 77/77 (100.0%) |
| Previous combined | 105/137 (76.6%) | 82/137 (59.9%) |
| New combined | 137/137 (100.0%) | 137/137 (100.0%) |

## Independent check of the grading

I also scored all 204 distinct replies that were neither exact key matches nor standard abstentions. I saw the question, key and reply, with bank, condition and Gemma's grade hidden. Equivalent descriptions received full credit. Partial answers and contradictions were scored separately. My scores matched Gemma on 167/204 of these three-way decisions. Both graders are models.

| Bank | Clean, full credit on rescore | One verse omitted, full credit on rescore |
|---|---|---|
| Gold72 | 55/72 (76.4%) | 21/72 (29.2%) |
| Prepared60 | 53/60 (88.3%) | 23/60 (38.3%) |
| Hard65 | 50/65 (76.9%) | 29/65 (44.6%) |
| Hard77 | 65/77 (84.4%) | 38/77 (49.4%) |
| Previous combined | 105/137 (76.6%) | 50/137 (36.5%) |
| New combined | 118/137 (86.1%) | 61/137 (44.5%) |

## What changed

Of 51 shared prepared IDs, 19 have a revised question or key and 14 moved to a different window; some did both. Of 62 shared hard IDs, 10 have revised questions or keys. Across both families 75 question–key–window combinations are unchanged at the same ID.

On the 113 shared IDs, the change in fully correct clean responses was -1. The reader answered 24/24 of the added items correctly, compared with 19/24 of the items that left the bank.

One improvement is the Judges 18:27–28 hard question. The new stem asks for the *two circumstances* that left Laish without a rescuer, matching the two-part key. A tradeoff appears in 2 Kings 6:24–26. The earlier prepared question asks why food was expensive. Its revision asks what condition existed in Samaria at the stated price. The key is easier to grade, but the causal inference is no longer required.

The Hard77 also restores Judges 17:3–4, keyed to Micah’s son as the maker of the image. The earlier Chinese pilot excluded it because the rendering says the image was made for the son and names the silversmith as its maker. This comparison concerns the English instruments; that item needs target-language resolution before returning to the same Chinese pilot. [Canonical pilot note](../../datasets/qa/tier1_hard66_canonical/t1_judg17_18.json)

## Repeated questions across the two families

I inspected every prepared/hard pairing in each combined bank sharing at least one verse. Of 90 overlapping pairs per bank, seven previous pairs and six new pairs asked for essentially the same fact. The counts cover only overlapping references. In the new bank, for example, both families ask what the practitioners did with their books in Acts 19, and both ask which duty the off-Sabbath companies were assigned in 2 Kings 11. [Pair-level review](cross_family_overlap.json)

[Every question, response, omitted verse and grade](results.json) · [Frozen model digests and protocol](manifest.json) · [Prepared comparison](../prepared110_review_2026-11-08/review.md) · [Hard revision history](../hard85_revised_bank_2026-11-07/comparison_with_original_hard66.md)
