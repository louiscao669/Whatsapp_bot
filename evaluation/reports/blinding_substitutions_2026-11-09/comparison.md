# Chinese substitution candidates

These are preview rules for the November 9 blinded Sol release. The rules match the original Chinese wording. This matters in Judges 17–18, where two different source expressions currently produce 韦伦.

| Source wording | Current display | Proposed display | Reason |
|---|---|---|---|
| 老先知, 年老的先知, 老的先知 | 利德 | 年长的先知 | Keeps the occupation visible when a later verse calls him simply 先知. |
| 神人, 男人的上帝 in 1 Kings 13 | 尼伦 | 属神的人 | Keeps the religious designation. The alternative 属至高者的人 repeats 至高者 from the stem in the keyed choice of one question. |
| 利未人 in Judges 17–18 | 韦伦 | 岚丘族人 | Identifies membership in a fictional clan. Explicit mentions of 约拿单 still use the personal pseudonym 韦伦. |
| 示剑 | 韦姆村 | 韦姆 | Removes the invented village designation. Judges 9:31 refers to 全城 in the same sentence. |
| 以禄 | 隆昂村 | 隆昂 | Preserves the geographic name when the answer describes rebuilding a city. |
| 占卜者橡树, 占卜师橡树, 占卜树 | 利伦地 | 利伦橡树 or 利伦树 | Keeps the tree as the landmark. The shorter source form uses 利伦树. |

The proposed question for 1 Kings 13:14 is **年长的先知在哪里找到属神的人？** The current question reads **利德在哪里找到尼伦？**. Gemma initially selected both the road and the oak tree. With the proposed roles it selected only the oak tree. The role changes also caused two previously correct Gemma answers in 1 Kings 13 to gain an extra distractor.

## Paired reader results

Every clean question with a changed stem, choice, or delivered verse window was included. There were 41 eligible questions and one withheld question. Scores below count a response only when it selects the keyed option alone. The answer letters, option order and verse ranges were fixed. Each reader used the same local weights, prompt, settings and question grouping as its own previous blinded comparison.

| Eligible questions | Number | Gemma 3 4B, current → proposed | Qwen3 8B, current → proposed |
|---|---:|---:|---:|
| 1 Kings 13 | 15 | 6 → 8 | 15 → 15 |
| Judges 17–18 | 7 | 6 → 6 | 7 → 7 |
| Judges 9 | 18 | 12 → 15 | 17 → 17 |
| 2 Chronicles 26 | 1 | 0 → 1 | 1 → 1 |
| **Total** | **41** | **24 → 30** | **40 → 40** |

Gemma gained eight answers and lost two. Qwen kept the same exact-match outcome on every eligible item. On the seven Judges 17–18 items the proposed clan term has a semantic benefit with no observed score gain. The tree wording preserves a source detail. The three newly correct Judges 9 items contained the change to 韦姆 and did not contain the tree wording.

Gemma also tried two alternatives. On the same 15 eligible 1 Kings items, 年长的先知 plus 属至高者的人 scored 7/15, compared with 8/15 for 年长的先知 plus 属神的人. In Judges 9, changing 示剑 to 索岚 and 以别/耶比底 to 达柯, while retaining the proposed tree wording, scored 14/18. Keeping the familiar 韦姆 and 慕姆 scored 15/18. These small comparisons informed the shortlist. The Gemma numbers are exploratory and Qwen supplied a second-reader check. Human readers have not evaluated these candidates.

## Integrity checks

All 122 Chinese stems and 488 choices passed the release's known-name checks, with four distinct options per question and all keys preserved. The renderer verified all 200 Chinese condition texts. The proposed display changed 75. All 180 positive-dose variants replayed from their existing edit selections, and the maximum dose deviation was 1.99 percentage points. Reader accuracy was tested on clean windows. The current release and participant assignments were not modified.

The exact proposed source-to-display rules are in `recommended.json`. Per-item outcomes for the shortlist are in `shortlist_gemma.json` and `confirmation.json`.
