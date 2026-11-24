# Report-only review of the 110 prepared Tier-1 questions

**60 questions fit the projected bank**, compared with the original 72. 51 original questions remain, 9 enter, and 21 leave. 94 qualify before scheduling. Of those, 34 lose a non-overlapping slot.

## From 110 questions to a projected bank

| Step | Questions |
|---|---|
| Pass blind and both editorial checks in at least one window as written | 54 |
| Eligible as written after duplicate checks | 54 |
| Fit the schedule as written | 42 |
| Additional faithful revisions passing a complete recheck | 40 |
| Individually eligible after revisions | 94 |
| Eligible after final duplicate checks | 94 |
| Fit the final schedule | 60 |

**73 questions flagged.** In the first pass, 169 of 277 candidate windows failed. 56 questions failed in every window and 17 passed in some windows only. 43 of the original 72 failed on their actual historical window. 22 of the proposed bank's questions use a checked revision.

[Every flagged question, key, window and reason](flagged_questions.md) · [Added, dropped, revised and all projected questions](selection_changes.md) · [Machine-readable selection](selection.json) · [Full audit](audit.json)

## Method

The audit uses canonical English Berean Standard Bible verses and the frozen 110 questions and keys supplied to the historical selector. Nine of those pairs already differed from the earlier shortened export. GPT-5 read each question alone with the key hidden and then judged the supported readings against the key. Two GPT-5.6 Sol reviews assessed wording and support; simple factual questions qualified. An item needed all three checks to pass on the same window. For questions with no passing window, a bounded revision could be proposed against original source intent. The exact revised pair was checked in every candidate window. Eligible questions received two within-passage duplicate checks in opposite orders. Unresolved duplicate groups are held for review. Historical selection and ranking were withheld from all model requests.

The local selector maximized question count in disjoint three-verse windows, then used the historical ranking for ties. A control replay reproduced all 72 historical question IDs and assignments. The main comparison preserves the original selector’s passage bounds. Allowing all checked windows through the actual end of each passage gives 60. This is an English open-question projection. The original QA bank and delivery records were not changed.

## Questions still held after review

| ID | Original question | Gold72 | Outcome |
|---|---|---|---|
| t1_judg9:g2ya | Why did Zebul send messengers? | Yes | No passing window |
| t1_judg9:z7va | What happens when Gaal fights Abimelech? | Yes | No passing window |
| t1_judg9:u7l2 | What does Abimelech do after capturing the city? | Yes | No passing window |
| t1_2kgs6_7:u21g | Why do leprous men go to Arameans? | Yes | No passing window |
| t1_2kgs6_7:lxi8 | Why do Arameans think Israel hired allies? | Yes | No passing window |
| t1_2kgs6_7:cc0k | Why does the king think Arameans left? | Yes | No passing window |
| t1_1kgs13:nc1x | What explanation did the old prophet give for the man of God's death? | Yes | No passing window |
| t1_1kgs13:w4ws | What does the old prophet do with the body? | Yes | No passing window |
| t1_2kgs11:rvb6 | What do people do after Jehoiada's covenant? | Yes | No passing window |
| t1_2sam21:wrtz | Why can't David go into battle? | No | No passing window |
| t1_2chr26:tglh | How does Uzziah follow his father's example? | Yes | No passing window |
| t1_2chr26:rxf3 | Why did Uzziah build watch towers? | No | No passing window |
| t1_acts19:zvnx | What happened to seven Jewish exorcists? | Yes | No passing window |
| t1_acts20:jxkk | What happened to the young man who fell? | Yes | No passing window |
| t1_acts23:xj40 | How did captain respond to the plan? | Yes | No passing window |
| t1_acts23:krfj | What did captain say in letter to Felix? | Yes | No passing window |
