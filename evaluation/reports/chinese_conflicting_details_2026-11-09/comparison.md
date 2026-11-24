# Following a conflicting detail in Chinese MCQs

The test compares the released Chinese Sol passages with the v1 pseudonyms. Each case keeps the question and four choices fixed while the altered passage makes a different existing choice correct. The clean control uses the same verse labels, including any delivery padding.

## Published mistranslations

| Model | Naming | Clean key on clean passage | Edited key on altered passage | Original key retained | Other / insufficient | Followed in both orders |
|---|---|---:|---:|---:|---:|---:|
| qwen3:8b | canonical | 14/14 | 13/14 | 1/14 | 0 / 0 | 6/7 |
| qwen3:8b | pseudonyms | 14/14 | 13/14 | 1/14 | 0 / 0 | 6/7 |
| gemma3:4b | canonical | 14/14 | 12/14 | 0/14 | 2 / 0 | 6/7 |
| gemma3:4b | pseudonyms | 12/14 | 12/14 | 0/14 | 2 / 0 | 6/7 |

Among presentations where the model first demonstrated the original fact on the clean control, the counts that also switched to the new key on the altered passage were as follows.

- qwen3:8b with original names 13/14 and with pseudonyms 13/14.
- gemma3:4b with original names 12/14 and with pseudonyms 10/12.

## Additional single-fact tests

| Model | Naming | Clean key on clean passage | Edited key on altered passage | Original key retained | Other / insufficient | Followed in both orders |
|---|---|---:|---:|---:|---:|---:|
| qwen3:8b | canonical | 20/20 | 20/20 | 0/20 | 0 / 0 | 10/10 |
| qwen3:8b | pseudonyms | 20/20 | 20/20 | 0/20 | 0 / 0 | 10/10 |
| gemma3:4b | canonical | 18/20 | 18/20 | 0/20 | 2 / 0 | 9/10 |
| gemma3:4b | pseudonyms | 20/20 | 20/20 | 0/20 | 0 / 0 | 10/10 |

Among presentations where the model first demonstrated the original fact on the clean control, the counts that also switched to the new key on the altered passage were as follows.

- qwen3:8b with original names 20/20 and with pseudonyms 20/20.
- gemma3:4b with original names 18/18 and with pseudonyms 20/20.

## What the misses looked like

All misses on the seven released conflicts came from Acts 20:7. The original says the first day of the week. The variant says the last day, making the seventh-day choice correct. With either set of names, Qwen chose the seventh day in the published order and the first day when the two options traded places. Gemma chose the sixth day in both orders and naming conditions. On every other published conflict both readers followed the edit in both orders.

In the supplemental cases, Gemma's two additional misses with biblical names were the two orders of one 2 Samuel 21 question. It chose Shimei's descendants, while the edited text says David's and the original says Rapha's. That difference gives little evidence for recall of the original answer.

## Selection and interpretation

I screened the 122 original Chinese MCQs against the edits in their assigned verse windows. The primary set uses pilot-eligible questions with one directly supported alternate option in both naming conditions. Each question enters once, at the lowest published dose at which its switch is clear. The seven questions span four passages. Five are from Judges. No reader's predictions were used to choose or label them.

Changes that merely removed evidence, broke the premise of the question, or made a distractor only approximately right were excluded. For example, the high-dose Acts 19 version changes both burning to selling and practitioners of magic to practitioners of medicine. The original stem still asks about practitioners of magic. The published 2 Kings 11 change says the people were devastated, while the existing choice specifically says they wept.

The separate supplemental set uses ten other eligible questions, one per passage, with a deliberate change to one fact. Repeated mentions of that fact were updated together. These passages exist only as diagnostic stimuli. The four choices were already in the bank. Each case was labeled before scoring. An independent choice-text readback corrected the tower-door foil letter before scoring.

Each local model had 136 independent requests. Each of the 17 questions appeared with both name sets, both clean and conflicting evidence, and two option orders. The second order exchanges the original and edited keys. Tables count semantic choices after reversing that permutation. Both models received the same Chinese passage-only prompt, without the keys or condition labels, at temperature zero with thinking disabled. A single option or an explicit insufficient-evidence response was allowed. Distinct option orders are repeated measures on the same questions.

Selecting the original key despite contrary evidence is compatible with prior knowledge, a reading mistake, or a guessing preference. These responses alone cannot distinguish them. The study materials and eligibility decisions were not modified.

cases.json records the reviewed alternate option, evidence, published dose or isolated edit. verified_windows.json contains the exact Chinese stimuli. item_results.json gives the clean and altered response for every question, naming condition and order.
