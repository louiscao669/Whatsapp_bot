# Six hard-QA selection decisions

The editorial calls below were recorded before the revised prompt ran. Each model run used the archived English window, question, key and proposed competitor. We held the model (GPT-5.6 Sol), reasoning effort (high), inputs, three item orders and 66-place bank size fixed. Only the selection instructions changed.

## Matched prompt comparison

| Order | Prompt | Matches my six /6 | Matches history on other 79 /79 | Matches history on all 85 /85 | Historical removals found /19 |
|---|---|---:|---:|---:|---:|
| original | previous | 2 | 75 | 75 | 14 |
| original | refined | 3 | 64 | 67 | 10 |
| 67411 | previous | 2 | 67 | 67 | 10 |
| 67411 | refined | 1 | 62 | 63 | 8 |
| 81937 | previous | 2 | 69 | 69 | 11 |
| 81937 | refined | 3 | 64 | 67 | 10 |
| Mean | previous | 2.0 | 70.3 | 70.3 | 11.7 |
| Mean | refined | 2.3 | 63.3 | 65.7 | 9.3 |

The six shaped the revision. The other 79 give an internal check on whether any gain carries over. For those 79 the reference is the historical selection, which can differ from editorial judgment.

## What changed on the other 79?

| Order | Moved into agreement with history | Moved out of agreement with history |
|---|---:|---:|
| original | 4 | 15 |
| 67411 | 7 | 12 |
| 81937 | 5 | 10 |

## The six decisions at a glance

| Window | Original question | Key | My call | Previous kept /3 | Refined kept /3 |
|---|---|---|---|---:|---:|
| 1 Kings 13:11–14 | Who mounts the donkey? | the old prophet | keep | 3 | 3 |
| 1 Kings 13:18–19 | According to the claim, who is to eat and drink? | The man of God. | remove | 3 | 3 |
| Acts 23:19–22 | What must happen before the ambushers act? | The commander’s consent to their request. | keep | 0 | 2 |
| Acts 23:27–30 | Who is ordered to present a case to the addressee? | his accusers | remove | 3 | 3 |
| Judges 9:21–25 | Why does Jotham live elsewhere? | Because he fears his brother Abimelek. | remove | 3 | 1 |
| Judges 9:11–12 | Why does the fig tree not want to rule the trees? | it would have to lose its sweet fruit | keep | 3 | 0 |

## Review against the original windows

### 1 Kings 13:11–14 · Who mounts the donkey?

**Keep as written.** The sons prepare the animal and their father rides it. Verse 13 changes from plural 'they' to singular 'he'. 'For me' helps identify the rider, but the reader still has to assign the two actions to the right people. The short question tests that cleanly.

**Answer key** — the old prophet  
**Proposed competitor** — his sons

Historically removed. Previous prompt kept it 3/3 times. Revised prompt kept it 3/3 times.

> **11** Now there was a certain old prophet living in Bethel, whose sons came and told him all that the man of God had done there that day. They also told their father what he had said to the king.
> **12** Their father asked them, “Which way did he go?” And his sons showed him which road the man of God from Judah had taken.
> **13** So he said to his sons, “Saddle the donkey for me.” And when they had saddled the donkey for him, he mounted it
> **14** and rode after the man of God. He found him sitting under an oak tree and asked, “Are you the man of God who came from Judah?” “I am,” he replied.

### 1 Kings 13:18–19 · According to the claim, who is to eat and drink?

**Remove as written.** The man of God is a supported key. The stem makes the reader identify what 'the claim' refers to inside nested reported speech, yet verse 19 gives the same person simply by saying who ate. A question about what the old prophet claimed would make this distinction worth testing.

**Answer key** — The man of God.  
**Proposed competitor** — The old prophet.

Historically removed. Previous prompt kept it 3/3 times. Revised prompt kept it 3/3 times.

> **18** The old prophet answered, “I too am a prophet, as you are. And an angel said to me by the word of the Lord: ‘Bring him back with you to your house so that he may eat bread and drink water.’” (But he was lying to him.)
> **19** So the man of God returned with him and ate and drank in his house.

### Acts 23:19–22 · What must happen before the ambushers act?

**Keep as written.** The ambushers are already in position. The young man says exactly what they are still waiting for: the commander's consent. This distinguishes approval of the request from Paul actually arriving before the council. 'Act' could be tightened, but 'ready now, waiting for' resolves the intended stage.

**Answer key** — The commander’s consent to their request.  
**Proposed competitor** — Paul being brought before the Sanhedrin.

Historically retained. Previous prompt kept it 0/3 times. Revised prompt kept it 2/3 times.

> **19** The commander took the young man by the hand, drew him aside and asked, “What is it you want to tell me?”
> **20** He said: “Some Jews have agreed to ask you to bring Paul before the Sanhedrin tomorrow on the pretext of wanting more accurate information about him.
> **21** Don’t give in to them, because more than forty of them are waiting in ambush for him. They have taken an oath not to eat or drink until they have killed him. They are ready now, waiting for your consent to their request.”
> **22** The commander dismissed the young man with this warning: “Don’t tell anyone that you have reported this to me.”

### Acts 23:27–30 · Who is ordered to present a case to the addressee?

**Remove as written.** Verse 30 explicitly supplies 'his accusers'. The stem turns the writer's perfectly ordinary 'you' into 'the addressee' and then follows the wording of that same clause. It tests familiarity with a letter-writing term more than the reader's understanding of the order.

**Answer key** — his accusers  
**Proposed competitor** — the Sanhedrin

Historically removed. Previous prompt kept it 3/3 times. Revised prompt kept it 3/3 times.

> **27** This man was seized by the Jews and they were about to kill him, but I came with my troops and rescued him, for I had learned that he is a Roman citizen.
> **28** I wanted to know why they were accusing him, so I brought him to their Sanhedrin.
> **29** I found that the accusation had to do with questions about their law, but there was no charge against him that deserved death or imprisonment.
> **30** When I was informed of a plot to be carried out against the man, I sent him to you at once. I also ordered his accusers to present to you their case against him.

### Judges 9:21–25 · Why does Jotham live elsewhere?

**Remove as written.** Verse 21 gives Jotham's move and fear of his brother in a single because-clause. The Shechemites appear in the subsequent conflict with Abimelek. The window gives no comparable reason to think Jotham moved because he feared them. This is a sound basic comprehension question with little discriminating value here.

**Answer key** — Because he fears his brother Abimelek.  
**Proposed competitor** — Because he fears the citizens of Shechem.

Historically removed. Previous prompt kept it 3/3 times. Revised prompt kept it 1/3 times.

> **21** Then Jotham fled, escaping to Beer, and he lived there because he was afraid of his brother Abimelek.
> **22** After Abimelek had governed Israel three years,
> **23** God stirred up animosity between Abimelek and the citizens of Shechem so that they acted treacherously against Abimelek.
> **24** God did this in order that the crime against Jerub-Baal’s seventy sons, the shedding of their blood, might be avenged on their brother Abimelek and on the citizens of Shechem, who had helped him murder his brothers.
> **25** In opposition to him these citizens of Shechem set men on the hilltops to ambush and rob everyone who passed by, and this was reported to Abimelek.

### Judges 9:11–12 · Why does the fig tree not want to rule the trees?

**Keep as written.** The fig tree answers with a rhetorical question. A reader must infer that ruling would mean giving up its sweet fruit and that this cost explains its refusal. Naming fruit alone would be an incomplete answer. The later invitation to the vine is a weak distractor, but the open question and key still test a meaningful inference.

**Answer key** — it would have to lose its sweet fruit  
**Proposed competitor** — because the trees turned to the vine

Historically removed. Previous prompt kept it 3/3 times. Revised prompt kept it 0/3 times.

> **11** “But the fig tree replied, ‘Should I give up my fruit, so good and sweet, to hold sway over the trees?’
> **12** “Then the trees said to the vine, ‘Come and be our king.’

## Revised prompt

[Exact selection and output instructions](design.json) · [Added criteria](prompt_addition.txt) · [All model decisions, scores and reasons](all_item_decisions.csv)
