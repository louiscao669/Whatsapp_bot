# Hard QA selection and clean-window answerability

The historical English pool contains 85 questions across 12 source passages. Every one of the 66 selected records matches its parent record, the selection export, and the published source question and key. The 19 others were removed. The separate 95-item BSB run shares 0 exact normalized question texts with the 66. The selection files establish membership. They do not identify the curator or reasons for individual removals.

The gpt-5 reader received one original question and its original clean English window. A second call compared the supported readings to the original answer key. Historical decisions, scores, rankings, competing answers and the authors’ rationales were withheld from both calls. This is a report-only answerability check.

| Historical selection | Model passed | Model flagged | Unchecked |
|---|---:|---:|---:|
| Retained | 61 | 5 | 0 |
| Removed | 17 | 2 | 0 |

Treating a model pass as a keep, the decisions agree on 63/85 checked questions (74.1%). The comparison measures agreement with the historical selection. A clear question can still be too easy or incidental for the study.

- The check flagged 5/66 checked retained questions (7.6%).
- The check flagged 2/19 checked removed questions (10.5%).

The parent directory holds the 12 per-passage candidate files and the combined 66-item selection export. The final per-passage files preserve the complete original records. The historical generator marked all 85 as passing its then-current checks, including the 19 later removed. [Parent and selection export](</Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo-v3-plus/v3/combo/qa_generation/outputs/tier1_hard_v3/tier1_strong_candidates.json>) · [Separate 95-question run](</Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo-v3-plus/v3/combo/qa_generation/outputs/tier1_hard_bsb>)

## All 19 historical removals

| Original item | Question and key | Model finding |
|---|---|---|
| 1 Kings 13:31–32 | Who gives the message that he says will happen? → the man of God | **pass**. In the quote, “he declared” clearly refers to the just-mentioned “man of God,” not the speaker. |
| 1 Kings 13:11–14 | Who mounts the donkey? → the old prophet | **pass**. Verse 13 clearly identifies the old prophet (the father) as the one who mounts the donkey. |
| 1 Kings 13:18–19 | According to the claim, who is to eat and drink? → The man of God. | **pass**. The claim’s “he… may eat and drink” clearly refers to the man of God. |
| 2 Kings 6:24–25 | What does the king do first? → He mobilizes his entire army | **pass**. The passage explicitly names mobilizing the army as the first action. |
| 2 Kings 7:12–13 | Following the capture of people what do the Arameans expect to do next? → enter the city | **pass**. The passage explicitly says the Arameans planned to “get into the city” after taking them alive, matching the key. |
| 2 Kings 7:19–20 | Who is trampled by the people? → The officer is trampled. | **pass**. The pronoun “him” in v.20 clearly refers back to “the officer” in v.19, showing the officer was trampled. |
| 2 Kings 7:10–11 | What is later reported? → the news | **multiple answers**. Blind answers: the news / that the Aramean camp was empty—no one was there, only tethered animals and tents left as they were. This restates the content of “the news” (“We went into the Aramean camp and no one was there…”) which is what was reported within the palace. |
| 2 Samuel 21:18–19 | In the battles at Gob, who kills first? → Sibbekai the Hushathite | **pass**. The text explicitly sequences two battles at Gob, with Sibbekai killing in the first (v.18) and Elhanan in another (v.19). |
| Acts 19:11–12 | What leaves the people on the items' arrival? → evil spirits | **multiple answers**. Blind answers: the evil spirits / their illnesses. The passage describes both illnesses being cured and evil spirits leaving upon the items’ arrival, so more than one different answer fits the question. |
| Acts 23:27–30 | Who is ordered to present a case to the addressee? → his accusers | **pass**. The passage directly states that “his accusers” were ordered to present their case to the addressee. |
| Judges 18:3–4 | For whom does Micah do something, according to the report? → the young Levite | **pass**. The passage explicitly states Micah had done something “for him,” the young Levite, confirmed by the Levite’s statement that Micah hired him. |
| Judges 18:11–13 | Which place do the Danites reach just before arriving at the residence the Danites visit? → The hill country of Ephraim. | **pass**. The text explicitly states they went to the hill country of Ephraim before arriving at Micah’s house. |
| Judges 18:9–10 | What do the listeners go there to take over? → the land | **pass**. The text directly states they are to go there and take over the land. |
| Judges 9:18–20 | What request comes just before the call for fire? → that Abimelek be their joy and they be his | **pass**. Verse 19 explicitly requests “may Abimelek be your joy, and may you be his, too” immediately before the call for fire in verse 20. |
| Judges 9:15–17 | Who is the man they should treat as he deserves? → Jerub-Baal | **pass**. The pronoun “him” in the verse directly refers to Jerub-Baal, so the reading matches the key. |
| Judges 9:21–25 | Why does Jotham live elsewhere? → Because he fears his brother Abimelek. | **pass**. The passage states he lived there because he feared his brother Abimelek. |
| Judges 9:11–12 | Why does the fig tree not want to rule the trees? → it would have to lose its sweet fruit | **pass**. The verse explicitly states the fig tree would have to give up its sweet fruit to rule, matching the key. |
| Judges 9:13–14 | Whose ruler do they ask the thornbush to become? → The trees’ own king. | **pass**. “All the trees … ‘Come and be our king’” explicitly shows the trees ask for the thornbush to be their own ruler. |
| Judges 9:56–57 | What happens to the people after God punishes them? → Jotham’s curse falls on them. | **pass**. The text explicitly states that Jotham’s curse came upon the people after God punished them. |

## Retained questions flagged or unchecked

| Original item | Question and key | Model finding |
|---|---|---|
| 2 Kings 11:12–14 | Why does Athaliah go to the crowd? → She hears noise made by the guards and the people | **multiple answers**. Blind answers: Because she heard the noise made by the guards and the people. / Because the king was being proclaimed and celebrated, causing the noisy commotion.. It cites the proclamation and celebration as the source of the noise and links that noise to her going; while more indirect, it aligns with the passage’s causal chain (“proclaimed him king... people... shouted... When Athaliah heard the noise... she went”). |
| Acts 23:16–18 | In Paul’s words, who has something to tell the commander? → the young man | **multiple answers**. Blind answers: this young man / the son of Paul’s sister. Verse 16 identifies the person as “the son of Paul’s sister,” and Paul’s words in verse 17 refer to the same individual as “this young man,” so it’s the same person described differently. |
| Judges 18:27–28 | Why does no one help the people at Laish? → They are far from Sidon and have no ties with others. | **multiple answers**. Blind answers: Because they lived a long way from Sidon and had no relationship with anyone else / Because they lived a long way from Sidon / Because they had no relationship with anyone else. It gives one explicit reason from the text (far from Sidon) but omits the second stated reason (no ties with others). |
| Judges 9:26–29 | During what activity do the people speak against Abimelek? → eating and drinking at the festival | **multiple answers**. Blind answers: While they were eating and drinking / During a festival in the temple of their god. They “held a festival in the temple of their god” and during it “they cursed Abimelek”; this captures the festival context but omits the specific activity of eating and drinking. |
| Judges 9:9–10 | Why does the olive tree refuse to take power over the other trees? → Because it would have to give up its oil that honors gods and humans. | **multiple answers**. Blind answers: Because it would have to give up its oil to hold sway over the trees. / Because its oil honors both gods and humans.. It captures the value of the oil (“by which both gods and humans are honored”) as the motive for refusal, though it omits the explicit “give up my oil” condition; still a reasonable paraphrase of the refusal’s basis. |

The accompanying JSON contains every question, verse window, blind answer, supporting quotation and recorded verdict.
