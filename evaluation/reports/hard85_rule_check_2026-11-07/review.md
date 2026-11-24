# Which Hard85 questions qualify as written?

Applied a fixed decision rule to the original 85 English questions and their clean windows. **61 are ready as written.** The historical selection and prior editorial calls were hidden. The rule has no target bank size and uses no score cutoff.

| Action | After item checks | After duplicate check |
|---|---:|---:|
| Keep | 62 | 61 |
| Revise | 9 | 9 |
| Review | 13 | 13 |
| Drop | 1 | 2 |

## Decision rule

1. Check whether a reader can recover one complete, supported answer from the clean window. Accept equivalent labels and paraphrases. Check whether the question is clear on first reading.
2. Require a specific distinction a translation could change, such as agency, sequence, reference or scope. The evaluator must quote evidence for a supported key and explain the distinction. A simple stem can pass. A weak supplied competitor can be replaced by another grounded misreading.
3. Two GPT-5.6 Sol high-effort assessments evaluate each item from different perspectives in shuffled batches. Code maps their findings to actions. Unsupported targets and pure lookup are dropped from the hard set. A fixable key or stem goes to revision and must be rechecked after editing. Uncertainty or disagreement goes to review. A proposed keep also needs a pass from the earlier key-blind GPT-5 check.
4. Compare ready items within each archived source passage in two presentation orders. Drop a redundant item only when both comparisons identify the same preferred representative. Route disputed duplicate clusters to review. Recheck a passage's duplicates whenever an edited or reviewed item is admitted.

The two assessments from the same model agreed on the initial action for 76/85. Duplicate removals: 1. The rules are deterministic given the findings. The semantic findings are model judgments. This is a source-English screening result. Discrimination on actual damaged translations and with human readers requires separate measurements.

## Six previously discussed questions

| Window | Question | No-quota action | Basis |
|---|---|---|---|
| 1 Kings 13:11–14 | Who mounts the donkey? | keep | The singular “he” refers to the old prophet who requested the donkey; the sons are the plural “they” who saddle it. |
| 1 Kings 13:18–19 | According to the claim, who is to eat and drink? | review | Reader revise; editor keep. In the alleged angelic message, “him” and “he” refer to the man of God. However, “According to the claim” is an avoidably generic reference and should identify the old prophet’s alleged message. The old prophet is plausible because he voices the claim and owns the house, but the third-person “him” and “he” refer to the person he is addressing. The following action confirms that this is the man of God. |
| Acts 23:19–22 | What must happen before the ambushers act? | revise | “Act” is vague enough to mean beginning the plan or actually attacking Paul, making both consent and Paul’s transfer plausible prerequisites. Asking what the ambushers are “waiting for” would uniquely recover the intended answer. |
| Acts 23:27–30 | Who is ordered to present a case to the addressee? | revise | The key is explicitly and uniquely supported, and understanding it requires resolving participant roles. However, “the addressee” is an avoidable technical label; “Who was ordered to present the case?” would be clearer. |
| Judges 9:21–25 | Why does Jotham live elsewhere? | revise | The causal statement uniquely supports the key, but “live elsewhere” is an avoidably vague description of fleeing to and living in Beer. |
| Judges 9:11–12 | Why does the fig tree not want to rule the trees? | keep | The fig tree's rhetorical question presents loss of its fruit as the reason it rejects rule. The following approach to the vine is an outcome of that refusal, not its cause. |

These six are examples previously used in developing the rubric. They are not an independent test of selection quality.

[Every decision and both gate assessments](decisions.csv) · [Exact rubric and policy](design.json) · [Original windows and duplicate judgments](audit.json)

## A pending duplicate check

The fig-tree question qualified. The olive-tree question went to review, so those two were never compared by the duplicate judge. If the olive item is approved, reassess the pair before publishing an updated bank.
