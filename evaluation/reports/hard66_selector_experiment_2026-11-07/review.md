# Reproducing the original 85-to-66 selection

Tested 28 complete prompt and model configurations. Each scored all 85 original English questions against its original passage, key and proposed competitor. Opaque IDs and randomized order hid the original decision and rank. Whole books were separated before choosing a winner.

The development winner was **gpt-5.6-sol (high effort) / historical_context**. It matched 25/31 held-out decisions and 75/85 in the full reconstruction. Ranking retrospectively on all 85 gives **original_high / historical_context** with 75/85 matches.

## Prompt and model comparisons

| Model setting | Prompt | Dev removal F1 | Held-out removal F1 | Held-out matches /31 | Full matches /85 | Full removals found /19 |
|---|---|---:|---:|---:|---:|---:|
| original_high | historical_context | 0.636 | 0.625 | 25 | 75 | 14 |
| sol_high | ordinary_reader | 0.636 | 0.500 | 23 | 69 | 11 |
| astra_high | editorial_panel | 0.545 | 0.625 | 25 | 69 | 11 |
| original_high | editorial_panel | 0.545 | 0.625 | 25 | 71 | 12 |
| original_high | ordinary_reader | 0.545 | 0.625 | 25 | 67 | 10 |
| sol_high | editorial_panel | 0.545 | 0.625 | 25 | 69 | 11 |
| sol_high | luke_examples | 0.545 | 0.750 | 27 | 71 | 12 |
| astra_high | claude_artifact_rubric | 0.455 | 0.500 | 23 | 65 | 9 |
| astra_high | historical_context | 0.455 | 0.750 | 27 | 67 | 10 |
| astra_high | luke_examples | 0.455 | 0.750 | 27 | 69 | 11 |
| astra_high | ordinary_reader | 0.455 | 0.500 | 23 | 65 | 9 |
| astra_high | original_request | 0.455 | 0.500 | 23 | 65 | 9 |
| original_high | claude_artifact_rubric | 0.455 | 0.750 | 27 | 69 | 11 |
| original_high | luke_examples | 0.455 | 0.625 | 25 | 67 | 10 |
| original_high | original_request | 0.455 | 0.625 | 25 | 67 | 10 |
| original_low | editorial_panel | 0.455 | 0.625 | 25 | 67 | 10 |
| original_low | historical_context | 0.455 | 0.625 | 25 | 67 | 10 |
| sol_high | claude_artifact_rubric | 0.455 | 0.500 | 23 | 65 | 9 |
| sol_high | historical_context | 0.455 | 0.625 | 25 | 69 | 11 |
| sol_high | original_request | 0.455 | 0.375 | 21 | 63 | 8 |
| astra_high | damaged_translation | 0.364 | 0.375 | 21 | 61 | 7 |
| original_low | luke_examples | 0.364 | 0.625 | 25 | 67 | 10 |
| sol_high | damaged_translation | 0.364 | 0.375 | 21 | 61 | 7 |
| original_high | damaged_translation | 0.273 | 0.500 | 23 | 63 | 8 |
| original_low | claude_artifact_rubric | 0.273 | 0.625 | 25 | 65 | 9 |
| original_low | damaged_translation | 0.273 | 0.625 | 25 | 65 | 9 |
| original_low | ordinary_reader | 0.273 | 0.625 | 25 | 65 | 9 |
| original_low | original_request | 0.273 | 0.500 | 23 | 61 | 7 |

## Most frequent disagreements across configurations

Each configuration makes its own 19-item cut. Counts below use the first run of each complete OpenAI configuration.

| Historical decision | Configurations disagreeing | Passage | Question |
|---|---:|---|---|
| removed | 28/28 | 1 Kings 13:11–14 | Who mounts the donkey? |
| removed | 27/28 | 1 Kings 13:18–19 | According to the claim, who is to eat and drink? |
| removed | 27/28 | 2 Kings 7:19–20 | Who is trampled by the people? |
| retained | 19/28 | 2 Kings 11:4–8 | Who is instructed to protect the temple on the king’s behalf? |
| retained | 17/28 | 2 Chronicles 26:1–2 | For what purpose do the people of Judah take Amaziah's son? |
| retained | 16/28 | Acts 23:19–22 | What must happen before the ambushers act? |

## Questions where the development winner disagrees

| Passage | Historical | Model | Original question | Model’s reason |
|---|---|---|---|---|
| Judges 18:22–23 | retained | remove | What prompts the Danites to turn? | The shouting and overtaking occur together, so the precise cause of the Danites turning is not uniquely discriminating. |
| 1 Kings 13:33–34 | retained | remove | What does Jeroboam not do? | The contrast is recoverable, but the broad negative question is unnatural and underspecified. |
| Acts 23:19–22 | retained | remove | What must happen before the ambushers act? | The commander’s consent is an explicit trigger, but the broad verb “act” leaves some interpretive room. |
| 2 Chronicles 26:1–2 | retained | remove | For what purpose do the people of Judah take Amaziah's son? | The purpose is clear, but “take Amaziah’s son” is less natural than naming Uzziah. |
| Judges 17:3–4 | retained | remove | Whom does the mother say will make the image? | The mother’s wording assigns the making to her son, though the later silversmith creates some interpretive friction. |
| Judges 9:21–25 | removed | retain | Why does Jotham live elsewhere? | Jotham’s fear of Abimelek is explicit, although “lives elsewhere” is slightly imprecise. |
| 1 Kings 13:18–19 | removed | retain | According to the claim, who is to eat and drink? | “According to the claim” appropriately targets the old prophet’s assertion about the man of God. |
| Judges 9:11–12 | removed | retain | Why does the fig tree not want to rule the trees? | The fig tree’s rhetorical reply clearly identifies surrendering its sweet fruit as its reason for refusing. |
| Acts 23:27–30 | removed | retain | Who is ordered to present a case to the addressee? | The speaker explicitly orders the accusers to present their case to the addressee. |
| 1 Kings 13:11–14 | removed | retain | Who mounts the donkey? | The old prophet’s request and subsequent mounting are explicit, while his sons only saddle the donkey. |

## How to read the comparison

Development used 54 questions outside Judges. The held-out set used all 31 Judges questions. At the known 19/85 removal rate each configuration removed 12 on development and seven on holdout. The independent full reconstruction ranks the combined scores and removes 19. Its cutoff can move questions across the two split cutoffs.

Removal F1 weights precision and recall for the rarer removal decision. The development winner uses removal F1, balanced accuracy, then a fixed name tie-break. An all-keep baseline agrees with 66/85 and finds zero removals. An uninformed random cut of 19 has an expected 4.25 historical removals in common. Aggregate scores describe this finite collection. The model prompts were blind. The analyst had previously inspected this corpus, so the held-out book is an internal check rather than a new independent corpus.

The original model was GPT-5.6 Sol at low effort. In the table, original_low and original_high are GPT-5.6 Sol, sol_high is GPT-6.1 Sol, and astra_high is GPT-6 Astra. Each model saw all candidates in one split together. [Source of the original instruction](provenance.md) · [Exact prompts](design.json) · [Every configuration’s decision on every question](all_item_decisions.csv).

## Supplemental runs

The Claude Sonnet 5.5 development batch had already been submitted before authorization was restricted to OpenAI. Claude received no held-out batch. The local Qwen fallback ran while authorization was pending. These runs were outside the OpenAI model comparison. [Supplemental results](supplemental_runs.csv)

## Repeat runs

Two more runs for each development finalist shuffled question order within the same splits. Model sampling can also vary between calls.

| Model setting | Prompt | Shuffle seed | Full matches /85 | Removals found /19 | Decisions identical to first run /85 |
|---|---|---:|---:|---:|---:|
| original_high | historical_context | 67411 | 67 | 10 | 71 |
| original_high | historical_context | 81937 | 69 | 11 | 75 |
| sol_high | ordinary_reader | 67411 | 67 | 10 | 77 |
| sol_high | ordinary_reader | 81937 | 69 | 11 | 77 |

The three-draw summary averages the historical matches. The median-rank selection uses the median of each question's three positions, with average position and opaque ID as tie-breaks, then removes the bottom 19. This is a descriptive follow-up on the same bank.

| Finalist | Matches by draw /85 | Average matches /85 | Median-rank matches /85 |
|---|---|---:|---:|
| original_high / historical_context | 75, 67, 69 | 70.33 | 69 |
| sol_high / ordinary_reader | 69, 67, 69 | 68.33 | 69 |