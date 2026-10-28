# Targeted QA rewrite results

Accepted means all model preservation, content, structure and burden checks passed in every repeat. It is not a human validation result. Original datasets were not edited.

| Item | Status | Attempts |
|---|---|---:|
| gold:t1_1kgs13:o8ae:open | ACCEPTED | 1 |
| gold:t1_1kgs13:o8ae:mcq | ACCEPTED | 1 |
| gold:t1_2chr26:tglh:open | DECLINED | 1 |
| gold:t1_2chr26:tglh:mcq | DECLINED | 1 |
| gold:t1_2kgs11:otua:open | ACCEPTED | 1 |
| gold:t1_2kgs11:otua:mcq | ACCEPTED | 1 |
| gold:t1_2kgs6_7:pb1x:open | ACCEPTED | 1 |
| gold:t1_2kgs6_7:pb1x:mcq | ACCEPTED | 2 |
| gold:t1_acts20:jxkk#2:open | DECLINED | 1 |
| gold:t1_acts23:xj40:open | DECLINED | 1 |
| gold:t1_acts23:xj40:mcq | DECLINED | 1 |
| hard:t1_1kgs13:ec63:open | ACCEPTED | 1 |
| hard:t1_1kgs13:ec63:mcq | ACCEPTED | 1 |
| hard:t1_1kgs13:2f00:open | ACCEPTED | 1 |
| hard:t1_1kgs13:2f00:mcq | ACCEPTED | 1 |
| hard:t1_2chr26:9aab:open | ACCEPTED | 1 |
| hard:t1_2chr26:1cab:mcq | ACCEPTED | 1 |
| hard:t1_2chr26:1fc4:open | ACCEPTED | 1 |
| hard:t1_2chr26:1fc4:mcq | ACCEPTED | 1 |
| hard:t1_2chr26:723e:open | ACCEPTED | 1 |
| hard:t1_2chr26:723e:mcq | ACCEPTED | 1 |
| hard:t1_2kgs11:f49c:open | ACCEPTED | 1 |
| hard:t1_2kgs11:f49c:mcq | ACCEPTED | 1 |
| hard:t1_acts19:7628:open | ACCEPTED | 2 |
| hard:t1_acts19:7628:mcq | ACCEPTED | 2 |
| hard:t1_judg17_18:725d:open | ACCEPTED | 1 |
| hard:t1_judg17_18:725d:mcq | ACCEPTED | 1 |
| hard:t1_judg17_18:c2d9:mcq | ACCEPTED | 1 |
| hard:t1_judg17_18:3162:open | ACCEPTED | 1 |
| hard:t1_judg17_18:3250:mcq | ACCEPTED | 1 |
| hard:t1_judg17_18:97e8:mcq | ACCEPTED | 1 |
| hard:t1_judg9:6d68:open | DECLINED | 1 |
| hard:t1_judg9:6d68:mcq | DECLINED | 1 |
| hard:t1_judg9:f36a:open | ACCEPTED | 1 |
| hard:t1_judg9:f36a:mcq | ACCEPTED | 1 |

## gold:t1_1kgs13:o8ae:open

Original: What becomes sin to Jeroboam's family?


### Attempt 1: ACCEPTED

What action was counted as a sin for Jeroboam's family?

Replaces the unnatural and ambiguous phrase “becomes sin to” with “was counted as a sin for,” clearly asking which action constituted the family's sin.

Pass 1:
- Review: KEEP
- same_target: pass — Both questions ask which action constituted sin for Jeroboam's family: ordaining anyone who desired to be a priest of the high places. The shift from 'becomes sin' to 'was counted as a sin' preserves the event and relationship.
- same_language: pass — Both the original and revised questions are in English.
- naturalness: 1/3 — “Counted as a sin for Jeroboam's family” is understandable but slightly stiff: “for” is a less idiomatic way to express attribution of sin to the family.
- processing: 1/3 — “What action was counted as a sin for Jeroboam's family?” requires connecting Jeroboam's action with the sin attributed to his family. This is an ordinary, manageable relationship; the reader need not identify the unstated evaluator in “was counted.”
- context_economy: 0/3 — The question contains no extraneous setup. “Jeroboam's family” identifies whose sin is being asked about, and there are no introductory details or options adding unnecessary effort.

Pass 2:
- Review: KEEP
- same_target: pass — Both questions ask which action constituted sin for Jeroboam's family: ordaining anyone who desired to be a priest of the high places. The tense change does not change the event or temporal relationship.
- same_language: pass — Both the original and revised questions are in English.
- naturalness: 1/3 — “Was counted as a sin for Jeroboam's family” is mildly stiff: “for” makes the attribution less direct, though the question remains understandable without substantial mental repair.
- processing: 1/3 — “What action” requires identifying an act, while “Jeroboam's family” requires distinguishing the actor from the household implicated. This is ordinary, manageable role tracking needed to express the intended relationship; there are no nested clauses or options to compare.
- context_economy: 0/3 — The single question provides no extra setup. “Jeroboam's family” identifies the relevant household and is useful rather than excess context.

## gold:t1_1kgs13:o8ae:mcq

Original: What becomes sin to Jeroboam's family?

- A. Building a new altar.
- B. Worshiping false gods.
- C. Consecrating anyone as priests.
- D. Ignoring the prophet's warning.
- E. I can't tell from this passage

### Attempt 1: ACCEPTED

What action is described as the sin of Jeroboam's family?

Replaced the unnatural phrase “becomes sin to” with clear wording that asks which action is attributed as the family's sin. Changed “anyone as priests” to “anyone as a priest” to fix the singular–plural mismatch while preserving unrestricted appointment.
- A. Building a new altar.
- B. Worshiping false gods.
- C. Consecrating anyone as a priest.
- D. Ignoring the prophet's warning.
- E. I can't tell from this passage

Pass 1:
- Review: KEEP
- same_target: pass — Both questions ask which action constitutes the sin of Jeroboam's family, referring to his consecrating anyone as priests. The revision preserves the participants and relationship without adding an answer-revealing setup.
- same_language: pass — The revised question and all five options remain in English, as in the original.
- Option A meaning: pass — Both versions say 'Building a new altar.'
- Option B meaning: pass — Both versions say 'Worshiping false gods.'
- Option C meaning: pass — 'Consecrating anyone as a priest' preserves the meaning of 'Consecrating anyone as priests'; the singular expresses the same role for anyone consecrated.
- Option D meaning: pass — Both versions say 'Ignoring the prophet's warning.'
- Option E meaning: pass — Both versions retain the same abstention: 'I can't tell from this passage'.
- naturalness: 0/3 — “What action is described as the sin of Jeroboam's family?” is idiomatic and direct. The action options, including “Consecrating anyone as a priest,” are naturally formed and fit the question.
- processing: 1/3 — Readers must understand “Consecrating anyone as a priest” as Jeroboam appointing people to that role, then connect his action with “Jeroboam's family.” They also need to relate “consecrating” to the passage's “ordained.” These are manageable operations serving the intended meaning, without substantial avoidable role or option-comparison load.
- context_economy: 0/3 — There is no added introduction or digressive setup. “Jeroboam's family” identifies the attribution being asked about, and the options are concise.

Pass 2:
- Review: KEEP
- same_target: pass — Both questions ask which action constitutes the sin of Jeroboam's family. The revision preserves the participants and relationship without adding or removing an answer component.
- same_language: pass — The revised question and all choices remain in English, matching their original fields.
- Option A meaning: pass — Both versions say 'Building a new altar.'
- Option B meaning: pass — Both versions say 'Worshiping false gods.'
- Option C meaning: pass — 'Consecrating anyone as a priest' preserves the meaning of 'Consecrating anyone as priests': ordaining anyone to the priesthood, without changing who may be ordained.
- Option D meaning: pass — Both versions say 'Ignoring the prophet's warning.'
- Option E meaning: pass — Both versions retain the same abstention: 'I can't tell from this passage'.
- naturalness: 0/3 — “What action is described as the sin of Jeroboam's family?” is grammatical and direct. The action options use natural, parallel wording such as “Building a new altar” and “Consecrating anyone as a priest.”
- processing: 1/3 — Readers must identify Jeroboam as the unstated actor in “Consecrating anyone as a priest” and connect his action with “Jeroboam's family.” “Consecrating” also requires a vocabulary link to “ordained” in the passage. These are manageable demands relevant to the intended meaning, without substantial avoidable role-tracking or option-comparison load.
- context_economy: 0/3 — There is no added introductory framing. “What action” and “Jeroboam's family” economically establish what the reader should identify; the options contain no unnecessary explanations.

## gold:t1_2chr26:tglh:open

Original: How did Uzziah follow his father's example with Yahweh?


### Attempt 1: DECLINED



The awkward phrase “with Yahweh” could be clarified, but wording alone cannot resolve the answer-support problem. The passage explicitly compares Uzziah’s doing right with his father’s conduct; it does not say that seeking God also followed his father’s example. Preserving both the father–son comparison and the fixed answer “Did right and sought God” would retain that unsupported relationship.

## gold:t1_2chr26:tglh:mcq

Original: How does Uzziah follow his father's example with Yahweh?

- A. Worshipped other gods
- B. Ignored God's laws
- C. Built idols
- D. Did right and sought God
- E. I can't tell from this passage

### Attempt 1: DECLINED



The awkward phrase “with Yahweh” could be reworded, but wording alone cannot resolve the answer-support problem. The passage links doing right to Uzziah’s father’s example, but does not link seeking God to that example. Preserving both the father–son comparison and the fixed two-part answer would retain this unsupported relationship. Fixing it would require changing the question’s scope, the keyed answer, or the supplied passage.

## gold:t1_2kgs11:otua:open

Original: What did non-serving groups do on the Sabbath?


### Attempt 1: ACCEPTED

What were the two divisions going off duty on the Sabbath commanded to do?

Replaces the misleading label “non-serving groups” with the passage’s clear duty-transition description. Asking what they were commanded to do also matches the passage’s assignment rather than implying that it reports the command being carried out.

Pass 1:
- Review: KEEP
- same_target: pass — Both questions ask for the Sabbath duty of the off-duty groups: guarding the house of the LORD. The revision identifies those groups as the two divisions going off duty, as stated in verse 11:7; its command framing preserves the same assigned action and Sabbath anchor.
- same_language: pass — Both the original and revised questions are in English.
- naturalness: 0/3 — “What were the two divisions going off duty on the Sabbath commanded to do?” is idiomatic English. Both “going off duty” and “commanded to do” are familiar expressions and require no mental repair.
- processing: 1/3 — Readers must hold “What were” across the subject “the two divisions going off duty on the Sabbath” until reaching “commanded to do.” They must also identify the divisions as both receiving the command and performing the requested action. These are ordinary, manageable operations; the modifier identifies the relevant divisions rather than adding avoidable load.
- context_economy: 0/3 — The question contains no extra introductory framing. “Going off duty on the Sabbath” usefully identifies which two divisions are being asked about.

Pass 2:
- Review: KEEP
- same_target: pass — Both questions ask for the Sabbath duty of the off-duty groups: guarding the house of the LORD. The revision identifies them more explicitly as the two divisions going off duty and preserves the passage’s commanded-duty context.
- same_language: pass — Both respondent-facing questions are in English.
- naturalness: 0/3 — “What were the two divisions going off duty on the Sabbath commanded to do?” is idiomatic English. Both “going off duty” and “commanded to do” are familiar constructions, and their combination requires no wording repair.
- processing: 1/3 — Readers must retain “What were” across “the two divisions going off duty on the Sabbath” until reaching “commanded to do.” They must also distinguish the identifying duty transition from the requested action. This is an ordinary, manageable demand: the modifier identifies the relevant divisions, and the passive does not require recovering the commander.
- context_economy: 0/3 — There is no additional introduction or option text. “The two divisions going off duty on the Sabbath” economically identifies the group being asked about; the question contains no unnecessary setup.

## gold:t1_2kgs11:otua:mcq

Original: What did non-serving groups do on the Sabbath?

- A. Guard the house of Yahweh
- B. Visit the market
- C. Attend a feast
- D. Rest at home
- E. I can't tell from this passage

### Attempt 1: ACCEPTED

What were the two divisions going off duty on the Sabbath commanded to do?

Replaces the misleading label “non-serving groups” with the passage’s clear description, “two divisions going off duty.” Asking what they were commanded to do preserves the intended assignment question without implying that the passage reports their carrying it out.
- A. Guard the house of Yahweh
- B. Visit the market
- C. Attend a feast
- D. Rest at home
- E. I can't tell from this passage

Pass 1:
- Review: KEEP
- same_target: pass — Both ask for the Sabbath duty of the off-duty groups: guarding the house of Yahweh. The revision identifies 'non-serving groups' as the passage's two divisions going off duty and frames their duty as the command given in the passage.
- same_language: pass — The question remains in English, and every option is unchanged in English.
- Option A meaning: pass — Unchanged: guarding the house of Yahweh.
- Option B meaning: pass — Unchanged: visiting the market.
- Option C meaning: pass — Unchanged: attending a feast.
- Option D meaning: pass — Unchanged: resting at home.
- Option E meaning: pass — Unchanged: inability to determine the answer from the passage.
- naturalness: 0/3 — “What were the two divisions going off duty on the Sabbath commanded to do?” is idiomatic English. “Going off duty” naturally describes the end of a shift, and the action options use direct, familiar wording such as “Visit the market” and “Rest at home.”
- processing: 1/3 — Readers must attach “going off duty on the Sabbath” to “the two divisions” and understand those divisions as both receiving the command and performing the requested action. These are ordinary, manageable operations that identify the intended group; they do not introduce substantial avoidable load. The short options are readily compared.
- context_economy: 0/3 — The question supplies no unnecessary setup. “Going off duty on the Sabbath” usefully identifies which divisions are meant, while “commanded to do” directly asks for their assigned action.

Pass 2:
- Review: KEEP
- same_target: pass — Both questions ask for the Sabbath duty of the off-duty groups in verse 11:7: guarding the house of Yahweh. The revision identifies the original's 'non-serving groups' as the two divisions going off duty and makes the passage's command framing explicit without changing the requested duty.
- same_language: pass — The question and all options remain in English.
- Option A meaning: pass — Unchanged: guarding the house of Yahweh.
- Option B meaning: pass — Unchanged: visiting the market.
- Option C meaning: pass — Unchanged: attending a feast.
- Option D meaning: pass — Unchanged: resting at home.
- Option E meaning: pass — Unchanged: inability to determine the answer from the passage.
- naturalness: 0/3 — “What were the two divisions going off duty on the Sabbath commanded to do?” is idiomatic English. “Going off duty” naturally describes a shift ending, and the options use direct, familiar action phrases such as “Visit the market” and “Rest at home.”
- processing: 1/3 — Readers must connect “going off duty on the Sabbath” to “the two divisions” and understand those divisions as both receiving the command and carrying out the requested action. These are ordinary, manageable operations needed to identify the intended group. The short options introduce no substantial comparison or reference-tracking burden.
- context_economy: 0/3 — There is no additional introductory framing. “The two divisions going off duty on the Sabbath” usefully identifies the group being asked about rather than adding unnecessary setup.

## gold:t1_2kgs6_7:pb1x:open

Original: What did the captain say to Elisha's prophecy?


### Attempt 1: ACCEPTED

What did the officer say in response to Elisha's prophecy?

Replaces the unnatural “say to ... prophecy” with “say in response to” and uses the passage’s label “officer” instead of “captain,” while preserving the requested response and its connection to Elisha’s prophecy.

Pass 1:
- Review: KEEP
- same_target: pass — Both questions ask what the same official said in response to Elisha's prophecy. Replacing 'captain' with the passage's 'officer' preserves the participant and the requested response.
- same_language: pass — Both the original and revised questions are in English.
- naturalness: 0/3 — “What did the officer say in response to Elisha's prophecy?” is idiomatic, direct English. “In response to” naturally identifies the speech being requested.
- processing: 1/3 — Readers must distinguish “the officer,” whose words are requested, from “Elisha,” whose prophecy prompted them. This is ordinary, necessary speaker tracking; the question adds no avoidable modifier or reference load.
- context_economy: 0/3 — “In response to Elisha's prophecy” economically identifies the relevant speech event. There is no separate introduction or unnecessary setup.

Pass 2:
- Review: KEEP
- same_target: pass — Both questions ask what the same official said in response to Elisha's prophecy. Replacing 'captain' with the passage's 'officer' preserves the participant and the requested response.
- same_language: pass — The original and revised questions are both in English.
- naturalness: 0/3 — “What did the officer say in response to Elisha's prophecy?” is an idiomatic, direct English question. “In response to” naturally expresses the relationship between the prophecy and the officer's words.
- processing: 1/3 — “The officer” identifies the speaker sought, while “Elisha's prophecy” identifies what he was responding to. Readers must distinguish the officer's response from Elisha's subsequent reply, but this is ordinary, necessary speaker tracking rather than avoidable wording load.
- context_economy: 0/3 — There is no added introductory framing. “In response to Elisha's prophecy” economically identifies the relevant speech; the question contains no unnecessary setup.

## gold:t1_2kgs6_7:pb1x:mcq

Original: What does the captain say to Elisha's prophecy?

- A. It will happen soon
- B. Impossible even if Yahweh helped
- C. We must prepare
- D. The people will rejoice
- E. I can't tell from this passage

### Attempt 1: NOT_ACCEPTED

What does the captain say in response to Elisha's prophecy?

Replaced the awkward “say to Elisha's prophecy” with “say in response to Elisha's prophecy.” Expanded option B into a complete clause while preserving its judgment of impossibility even under hypothetical divine help.
- A. It will happen soon
- B. It would be impossible even if Yahweh helped
- C. We must prepare
- D. The people will rejoice
- E. I can't tell from this passage

Pass 1:
- Review: KEEP
- same_target: pass — Both questions ask what the captain says in response to Elisha's prophecy; adding 'in response' makes the same relationship explicit.
- same_language: pass — The question and all five options remain in English.
- Option A meaning: pass — Both versions state 'It will happen soon.'
- Option B meaning: pass — Adding 'It would be' preserves the claim that the prophesied event is impossible even if Yahweh helps.
- Option C meaning: pass — Both versions state 'We must prepare.'
- Option D meaning: pass — Both versions state 'The people will rejoice.'
- Option E meaning: pass — Both versions retain the same abstention: 'I can't tell from this passage.'
- naturalness: 0/3 — “What does the captain say in response to Elisha's prophecy?” is direct, idiomatic English. The options also use natural phrasing, including “It would be impossible even if Yahweh helped.”
- processing: 1/3 — Readers must connect “the captain” in the question with “the officer” in the passage and distinguish his response from Elisha's reply. Using different role labels adds a small, avoidable matching step, but the overall demand remains manageable. Resolving “It” to the predicted event and interpreting “even if Yahweh helped” require ordinary reference and conditional processing central to the intended meaning.
- context_economy: 0/3 — There is no added introductory framing. “In response to Elisha's prophecy” usefully identifies the speech turn being asked about; the question and options contain no substantial excess setup.

Pass 2:
- Review: REVIEW
- same_target: pass — Both questions ask what the captain says in response to Elisha's prophecy; the revision only makes the response relationship explicit.
- same_language: pass — The question and every option remain in English.
- Option A meaning: pass — Both versions state that it will happen soon.
- Option B meaning: pass — Adding 'It would be' preserves the claim of impossibility even under the condition that Yahweh helped.
- Option C meaning: pass — The option is unchanged: 'We must prepare'.
- Option D meaning: pass — The option is unchanged: 'The people will rejoice'.
- Option E meaning: pass — The unchanged option expresses inability to tell from the passage.
- naturalness: 0/3 — The question, “What does the captain say in response to Elisha's prophecy?”, is idiomatic English. The options are also naturally phrased, including the concessive construction “It would be impossible even if Yahweh helped.”
- processing: 1/3 — Readers must distinguish the requested speaker's response from Elisha's reply and interpret “even if Yahweh helped” as a concession that does not change the claimed impossibility. These are manageable operations central to the target. The shifts from the passage's “officer” to “captain” and from “LORD” to “Yahweh” add small, avoidable label-matching demands, but do not create substantial decoding or option-comparison load.
- context_economy: 0/3 — There is no additional introductory framing. “In response to Elisha's prophecy” usefully specifies which statement the question requests; the question and options contain no substantial removable setup.

### Attempt 2: ACCEPTED

What does the officer say in response to Elisha's prophecy?

Makes the response relationship explicit and turns the compressed wording in B into a complete sentence. Uses “officer” and “the LORD” to match the passage, removing the terminology shifts noted in the previous reviews while preserving all option meanings.
- A. It will happen soon
- B. It would be impossible even if the LORD helped
- C. We must prepare
- D. The people will rejoice
- E. I can't tell from this passage

Pass 1:
- Review: KEEP
- same_target: pass — Both questions ask what the same officer/captain said in response to Elisha's prophecy. The revision preserves the speaker, prophecy, and requested response.
- same_language: pass — The question and all five options remain in English.
- Option A meaning: pass — Both versions state that it will happen soon.
- Option B meaning: pass — Both express impossibility even with divine help; 'the LORD' corresponds to 'Yahweh' in the supplied passage.
- Option C meaning: pass — Both versions state 'We must prepare.'
- Option D meaning: pass — Both versions state that the people will rejoice.
- Option E meaning: pass — Both versions express the same inability to tell from the passage.
- naturalness: 0/3 — The question, “What does the officer say in response to Elisha's prophecy?”, is idiomatic and direct. The options use natural English, including “It would be impossible even if the LORD helped”; none requires mental repair.
- processing: 1/3 — “The officer” and “Elisha's prophecy” require ordinary speaker tracking to identify whose response is requested. In option B, “impossible even if the LORD helped” requires interpreting a hypothetical concession rather than an actual occurrence. Both operations serve the intended meaning; the question and options add no substantial avoidable parsing or comparison load.
- context_economy: 0/3 — The question moves directly to the requested response with “What does the officer say”. There is no added introductory framing or unnecessary setup in the question or options.

Pass 2:
- Review: KEEP
- same_target: pass — Both questions ask for the same man's response to Elisha's prophecy. 'Officer' identifies the participant called 'captain' in the original and matches the passage.
- same_language: pass — The revised question and all options remain in English, as in the original.
- Option A meaning: pass — Both versions say, 'It will happen soon.'
- Option B meaning: pass — Both express impossibility even with divine help; 'the LORD' refers to Yahweh, and the added words make the same proposition explicit.
- Option C meaning: pass — Both versions say, 'We must prepare.'
- Option D meaning: pass — Both versions say, 'The people will rejoice.'
- Option E meaning: pass — Both versions retain the same abstention: 'I can't tell from this passage.'
- naturalness: 0/3 — “What does the officer say in response to Elisha's prophecy?” is idiomatic and direct. The options, including “It would be impossible even if the LORD helped,” use natural English and require no mental repair.
- processing: 1/3 — Readers must identify the officer as the speaker, connect “It” in the options to the prophesied event, and interpret “even if the LORD helped” as a condition that would not change his judgment. These are ordinary, manageable operations needed to express the intended skepticism, not avoidable wording load. The short options are easy to compare.
- context_economy: 0/3 — There is no added introduction or unnecessary framing. “In response to Elisha's prophecy” usefully identifies which statement the question asks about.

## gold:t1_acts20:jxkk#2:open

Original: What happens after Paul stretches on the young man?


### Attempt 1: DECLINED



“Stretches on” could be replaced with “throws himself on,” but that would not resolve the reported answer-support concern. Although the young man is described as dead, Paul says he is “still alive,” leaving revival versus continued life uncertain. Wording alone cannot make the fixed answer, “He comes back to life,” unambiguous without changing the tested fact or the supplied passage.

## gold:t1_acts23:xj40:open

Original: How did captain respond to the plan?


### Attempt 1: DECLINED



Adding “the” before “captain” would fix the grammatical omission, but the supplied passage neither identifies the captain nor describes the plan prompting his response. Resolving those context gaps would require expanding the fixed passage or changing the question’s intended relation, not merely revising its wording.

## gold:t1_acts23:xj40:mcq

Original: How did captain respond to the plan?

- A. Dismissed the young man without acting.
- B. Ordered Paul returned to the council.
- C. Released Paul without an escort.
- D. Ordered guard to protect Paul.
- E. I can't tell from this passage

### Attempt 1: DECLINED



The missing determiners in “did captain” and “Ordered guard” can be corrected, but wording changes cannot resolve the reported context problem. The supplied passage neither identifies the captain nor mentions the plan, so it does not establish that the protective orders were his response to that plan. Preserving this required relationship would require additional passage context; removing it would change the question. With the window and key fixed, D cannot be established uniquely over E.

## hard:t1_1kgs13:ec63:open

Original: 带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？


### Attempt 1: ACCEPTED

一起吃饭时，先知宣告谁的尸首必定不能葬在自己的祖坟里？

用吃饭的场景定位宣告，避免“带他回来”中所指未明的代词；将“必不得入他列祖的坟墓”改为更自然的现代汉语，并用“自己的祖坟”明确领属关系，保留宣告者与宣告对象的区别及确定的否定结果。

Pass 1:
- Review: KEEP
- same_target: pass — Both ask whose corpse the prophet declared would not enter that person's ancestral tomb: the man of God from Judah. The meal-time setup matches 13:20 and does not reveal the answer; “不能葬在自己的祖坟里” preserves the stated burial exclusion.
- same_language: pass — Both respondent-facing questions are in Chinese.
- naturalness: 0/3 — “一起吃饭时”自然地交代时间，“先知宣告谁的尸首必定不能葬在自己的祖坟里？”也是通顺的中文问法。“宣告”“尸首”虽偏正式，但符合题材，无须修补句意。
- processing: 1/3 — 读者需要区分“先知”这一宣告者与“谁的尸首”所询问的人，并把“自己”理解为尸首所属的人。这是同一句内的常规角色区分和回指；“谁的尸首”也明确限定了所问对象，未增加实质性的可避免负担。
- context_economy: 0/3 — “一起吃饭时”是简短的事件定位信息，直接连接所问的宣告；题目没有额外铺陈或无关背景。

Pass 2:
- Review: KEEP
- same_target: pass — Both questions ask whose corpse the prophet declared would not be buried in his ancestral tomb: the man of God from Judah. The meal setting is supplied by verse 13:20 and does not reveal the answer or change the declaration being asked about.
- same_language: pass — The original and revised respondent-facing questions are both in Chinese.
- naturalness: 0/3 — “一起吃饭时”作为时间背景自然简洁；“先知宣告谁的尸首必定不能葬在自己的祖坟里”符合汉语疑问句习惯。“尸首”“祖坟”虽带有特定语境色彩，但搭配自然，不需要修补句意。
- processing: 1/3 — 读者需要区分“先知”这一宣告者与“谁的尸首”所询问的人，并把“自己的祖坟”中的“自己”理解为尸首所属的人，而非先知。这是短距离的角色和指代追踪；虽有短暂辨认需求，但没有多层嵌套或额外比较，属于辨认目标人物所需的可管理负担。
- context_economy: 0/3 — “一起吃饭时”简短地定位宣告发生的场景，其余文字均用于说明宣告者和所问的宣告内容，没有明显多余的铺垫。

## hard:t1_1kgs13:ec63:mcq

Original: 带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？

- A. 耶罗波安
- B. 带他回来的先知
- C. 他的列祖
- D. 从犹大来的神人
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

坐席时，先知宣告谁的尸首必定不能葬在自己的祖坟里？

用“坐席时”定位宣告事件，避免题干开头“带他回来”中指代未明的“他”；用“自己的祖坟”明确坟墓属于所问人物，并将“必不得入”改为更自然的“必定不能葬在”。保留宣告者与受宣告者的区别、否定结果及全部选项原意。
- A. 耶罗波安
- B. 带他回来的先知
- C. 他的列祖
- D. 从犹大来的神人
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 两题都问先知宣告谁的尸首不得葬入其列祖的坟墓，所指均为从犹大来的神人。“坐席时”符合原文中同一宣告事件的时间，“不能葬在自己的祖坟里”保留了原来的关系和否定意义。
- same_language: pass — 修订后的问题和所有选项仍使用中文，与原对应字段一致。
- Option A meaning: pass — 选项未变，仍指耶罗波安。
- Option B meaning: pass — 选项未变，仍指带他回来的先知。
- Option C meaning: pass — 选项未变，仍指他的列祖。
- Option D meaning: pass — 选项未变，仍指从犹大来的神人。
- Option E meaning: pass — 选项未变，仍表示根据这段文字无法判断。
- naturalness: 0/3 — “坐席时，先知宣告谁的尸首必定不能葬在自己的祖坟里？”语序自然，所问人物通过“谁的尸首”表达清楚。“尸首”“祖坟”虽带有特定语境色彩，但都是可直接理解的中文用语；各选项也没有需要修补的搭配。
- processing: 1/3 — 读者需要区分“先知宣告”中的宣告者与“谁的尸首”所问的人，并理解“自己的祖坟”属于后者；选项“带他回来的先知”还需结合上下文识别“他”。这些关系较短，属于辨认人物所需的普通处理，没有多层嵌套或实质性的可避免比较负担。
- context_economy: 0/3 — 题干只用“坐席时”定位宣告发生的场景，随后直接提问，没有额外介绍或重复铺陈。选项“根据这段文字无法判断”也是简短的常规表述，不构成多余背景。

Pass 2:
- Review: KEEP
- same_target: pass — 两题都问先知宣告谁的尸首不得进入其列祖的坟墓，所指均为从犹大来的神人。“不能葬在自己的祖坟里”保留了原来的否定关系及坟墓归属；“坐席时”对应经文13:20的同一事件，没有透露答案。
- same_language: pass — 修订后的题干及全部选项均保持中文，与原对应字段语言一致。
- Option A meaning: pass — 选项未改，仍指耶罗波安。
- Option B meaning: pass — 选项未改，仍指带他回来的先知。
- Option C meaning: pass — 选项未改，仍为“他的列祖”，人物及指代范围不变。
- Option D meaning: pass — 选项未改，仍指从犹大来的神人。
- Option E meaning: pass — 选项未改，仍表示根据所给文字无法判断。
- naturalness: 0/3 — “坐席时，先知宣告谁的尸首必定不能葬在自己的祖坟里？”语序自然，疑问落点清楚。“尸首”“祖坟”符合这一叙述语境；“带他回来的先知”“从犹大来的神人”作为人物称谓也能自然理解，无须修补句法。
- processing: 1/3 — 读者需要区分“先知”这一宣告者与“谁的尸首”所询问的人，并把“自己”理解为尸首所属的人。选项“带他回来的先知”还需要结合经文确定“他”的所指。这些是局部、可管理的人物对应操作，服务于辨认宣告对象，没有额外嵌套或实质性的可避免比较负担。
- context_economy: 0/3 — 题干仅以“坐席时”定位宣告发生的场景，随后直接询问人物，没有另加无关介绍或重复解释；选项也均为简短的人物称谓或常规的无法判断选项。

## hard:t1_1kgs13:2f00:open

Original: 带他回来的先知先把神人的尸首带到哪里？


### Attempt 1: ACCEPTED

先知在路上找到神人的尸首后，先把尸首带到哪里？

用找到尸首的事件定位所问情节，去掉“带他回来的”这一涉及另一次带回事件的修饰语，避免前置代词和相似事件造成的理解负担；保留先知、神人的尸首及首个目的地的关系。

Pass 1:
- Review: KEEP
- same_target: pass — 两题都问同一位先知首先把神人的尸首带到哪里，答案均为他自己的城里。修订以“在路上找到神人的尸首后”指明同一事件，没有改变人物、先后关系或所求目的地，也未透露答案。
- same_language: pass — 原题和修订后的题目均为中文。
- naturalness: 0/3 — “先知在路上找到神人的尸首后，先把尸首带到哪里？”语序自然，“把尸首带到哪里”直接询问目的地，无需修补或重解措辞。
- processing: 1/3 — 读者需将“找到神人的尸首后”理解为时间背景，将“在路上”与所问的目的地“哪里”区分，并留意“先”所限定的行动顺序。这些都是普通、可管理的理解操作；前后两处“尸首”指向清楚，没有明显可避免的修饰或指代负担。
- context_economy: 0/3 — “在路上找到神人的尸首后”用于定位所问事件，“先”用于限定行动顺序，均服务于地点提问；没有额外引言或无关铺垫。

Pass 2:
- Review: KEEP
- same_target: pass — 两题都问同一位先知先把神人的尸首带到哪里，答案均为他自己的城里（13:29）。修订用“在路上找到神人的尸首后”明确同一事件的背景，未改变人物、先后关系或所问目的地，也未透露答案。
- same_language: pass — 原问题和修订问题均为简体中文。
- naturalness: 0/3 — “先知在路上找到神人的尸首后，先把尸首带到哪里？”语序自然，“……后，先……”顺畅地询问后续行动的先后次序，没有需要读者自行修补的措辞。
- processing: 0/3 — “先知”明确充当找到和搬运尸首的共同主语，“神人的尸首”明确标示死者；再次使用“尸首”也避免了代词指代不清。读者只需理解一个时间关系并识别所问地点，没有多层修饰或可避免的角色辨认负担。
- context_economy: 0/3 — “在路上找到神人的尸首后”用于定位所问事件，“先”用于限定行动次序，均服务于问题，没有额外引言或无关铺垫。

## hard:t1_1kgs13:2f00:mcq

Original: 带他回来的先知先把神人的尸首带到哪里？

- A. 到自己的坟墓。
- B. 回到自己的城里。
- C. 到王宫。
- D. 到坛那里。
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

先知找到神人的尸首后，先把尸首带到哪里？

用找到尸首这一当前事件作简短定位，去掉“带他回来的”引入的较早事件和前置代词，避免两次“带回”相混淆。保留“先”，仍询问尸首先被带到的地点，并保留全部选项的原意。
- A. 到自己的坟墓。
- B. 回到自己的城里。
- C. 到王宫。
- D. 到坛那里。
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 两题都询问同一位先知先把神人的尸首带到哪里，保留了行动者、尸首和先后关系。修订中的“找到神人的尸首后”符合13:28的事件顺序，也未透露目的地；答案仍是“回到自己的城里”。
- same_language: pass — 修订后的问题及A至E各选项均保持中文，与原对应字段的语言一致。
- Option A meaning: pass — 原文与修订均为“到自己的坟墓。”，目的地及所属关系不变。
- Option B meaning: pass — 原文与修订均为“回到自己的城里。”，返回的目的地及所属关系不变。
- Option C meaning: pass — 原文与修订均为“到王宫。”，目的地不变。
- Option D meaning: pass — 原文与修订均为“到坛那里。”，目的地不变。
- Option E meaning: pass — 原文与修订均为“根据这段文字无法判断”，无法依据所给段落作答的含义不变。
- naturalness: 0/3 — “先知找到神人的尸首后，先把尸首带到哪里？”表达自然，“……后，先……”清楚地询问行动顺序。选项“到自己的坟墓”“回到自己的城里”等作为地点回答也符合汉语习惯，无须修补句意。
- processing: 1/3 — 读者需把“找到神人的尸首后”作为时间起点，依据“先”区分带回城里与随后安葬，并将选项A、B中的“自己”理解为先知。这些是理解所问行动及地点归属的常规操作；问句主语明确，选项简短，没有明显可避免的修饰或比较负担。
- context_economy: 0/3 — 没有额外引言。“找到神人的尸首后”限定所问的行动阶段，“先”标明要辨认先后顺序，均服务于问题，没有多余背景。

Pass 2:
- Review: KEEP
- same_target: pass — 两题都询问同一位先知先把神人的尸首带到哪里，保留了行动者、尸首和“先”的顺序关系。新增“找到神人的尸首后”符合13:28–29的事件顺序，未透露目的地；答案仍为先知自己的城里。
- same_language: pass — 修订后的问题及全部选项与原对应字段一样，均为中文。
- Option A meaning: pass — 选项未变，仍表示带到先知自己的坟墓。
- Option B meaning: pass — 选项未变，仍表示带回先知自己的城里。
- Option C meaning: pass — 选项未变，仍表示带到王宫。
- Option D meaning: pass — 选项未变，仍表示带到坛那里。
- Option E meaning: pass — 选项未变，仍表示根据所给文字无法判断。
- naturalness: 0/3 — “先知找到神人的尸首后，先把尸首带到哪里？”表达自然，时间关系和询问方向明确。“到自己的坟墓”“回到自己的城里”等选项作为地点回答，省略主语也符合中文习惯，无需修补句意。
- processing: 1/3 — 读者需要把“找到”和“带”的行动者都理解为先知，将“自己的”回指先知，并依据“先”区分带回的地点与随后安葬的地点。这些是理解所问事件顺序及地点归属所需的普通操作；题干较短，选项也简短，没有明显可避免的角色或比较负担。
- context_economy: 0/3 — “先知找到神人的尸首后”用于定位所问事件，“先”用于限定事件顺序，均有明确作用。没有额外的介绍或无关铺垫。

## hard:t1_2chr26:9aab:open

Original: 犹大全体百姓立乌西雅，是为了什么？


### Attempt 1: ACCEPTED

犹大全体百姓拥立乌西雅的目的是什么？

将单独使用时显得未说完整的“立乌西雅”改为更自然的“拥立乌西雅”，减少读者补足动作含义的负担；保留行动双方及对目的的询问，不提前透露接替谁作王。

Pass 1:
- Review: KEEP
- same_target: pass — “立乌西雅，是为了什么”与“拥立乌西雅的目的是什么”均询问犹大全体百姓立乌西雅的目的，即使他接替父亲亚玛谢作王；参与者、关系和所求内容未变。
- same_language: pass — 原问题与修订问题均为中文。
- naturalness: 0/3 — “犹大全体百姓拥立乌西雅的目的是什么？”措辞自然，符合中文书面提问习惯；“拥立”虽偏正式，但与立王的语境相称，无需修补语意。
- processing: 0/3 — “犹大全体百姓”是行动者，“乌西雅”是拥立对象，“的目的是什么”明确标出所问关系。全句可直接解析，没有嵌套修饰、含混指代或选项比较负担。
- context_economy: 0/3 — 题目直接以“犹大全体百姓拥立乌西雅”指明所问事件，没有额外引言、重复说明或无关背景。

Pass 2:
- Review: KEEP
- same_target: pass — “立乌西雅，是为了什么”与“拥立乌西雅的目的是什么”都询问犹大全体百姓立乌西雅的目的，所求仍是让他接替父亲亚玛谢作王，未改变参与者或所求关系。
- same_language: pass — 原问题与修订问题均为中文。
- naturalness: 0/3 — “犹大全体百姓拥立乌西雅的目的是什么？”语序自然，“拥立”与人物对象搭配恰当，“目的是什么”是常见的提问方式，无需在理解时修补措辞。
- processing: 0/3 — 全句直接呈现“犹大全体百姓—拥立—乌西雅”的施事、行为和对象，再用“的目的是什么”标明所问内容；没有嵌套修饰、跨句指代或选项比较，能够顺畅解析。
- context_economy: 0/3 — 题目没有额外引言；“犹大全体百姓”和“乌西雅”用于明确所问的拥立行为，没有多余的背景铺陈。

## hard:t1_2chr26:1cab:mcq

Original: 神帮助乌西雅攻打哪些人？

- A. 亚扪人、住在姑珥巴力的阿拉伯人和米乌尼人
- B. 非利士人、住在亚实突的阿拉伯人和亚扪人
- C. 摩押人、住在埃及边界的亚玛力人和亚扪人
- D. 非利士人、住在姑珥巴力的阿拉伯人和米乌尼人
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

神帮助乌西雅攻打哪些人？

保留自然、简明的题干。将各名单统一为每行一个群体，并把居住地紧随对应族名放在括号中，便于按相同位置核对族名和地点，减少在近似长列表中反复回扫的负担。所有选项的群体、地点限定及原有含义均保留。
- A. • 亚扪人
• 阿拉伯人（住在姑珥巴力）
• 米乌尼人
- B. • 非利士人
• 阿拉伯人（住在亚实突）
• 亚扪人
- C. • 摩押人
• 亚玛力人（住在埃及边界）
• 亚扪人
- D. • 非利士人
• 阿拉伯人（住在姑珥巴力）
• 米乌尼人
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 问题原文未变，仍询问神帮助乌西雅攻打哪些人，保留全部所求对象。
- same_language: pass — 问题及所有选项仍为中文；项目符号和括号未改变语言。
- Option A meaning: pass — 仍列出亚扪人、住在姑珥巴力的阿拉伯人和米乌尼人；括号保留了阿拉伯人的居住地限定。
- Option B meaning: pass — 仍列出非利士人、住在亚实突的阿拉伯人和亚扪人，人物群体及地点限定均未改变。
- Option C meaning: pass — 仍列出摩押人、住在埃及边界的亚玛力人和亚扪人，地点限定仍修饰亚玛力人。
- Option D meaning: pass — 仍列出非利士人、住在姑珥巴力的阿拉伯人和米乌尼人，完整保留原选项的三个群体。
- Option E meaning: pass — “根据这段文字无法判断”原文未变。
- naturalness: 0/3 — “神帮助乌西雅攻打哪些人？”是自然、直接的中文问句。“阿拉伯人（住在姑珥巴力）”以括号补充居住地点，虽是清单式表达，但修饰对象明确，不需要修补语意。
- processing: 1/3 — 读者需要理解“神帮助乌西雅攻打”的角色关系，再逐项核对三个群体。A与D的后两项相同，B与D也共享“非利士人”，因此不能只凭一个名称选择；但这种比较直接服务于辨认三个群体的目标。分行清单及紧邻名称的地点括注便于核对，没有明显可避免的额外解析负担。
- context_economy: 0/3 — 题目直接以“神帮助乌西雅攻打哪些人？”提问，没有额外引言或情境铺垫。选项中的“住在姑珥巴力”等地点限定用于区分群体，“根据这段文字无法判断”也简洁明了，没有多余说明。

Pass 2:
- Review: KEEP
- same_target: pass — 问题完全未变，仍询问神帮助乌西雅攻打哪些人，保留了相同的参与者、关系及完整的群体范围。
- same_language: pass — 问题和全部选项仍为中文；项目符号、换行及括号未改变语言。
- Option A meaning: pass — 仍列出亚扪人、住在姑珥巴力的阿拉伯人和米乌尼人；括号中的居住地仍仅修饰阿拉伯人。
- Option B meaning: pass — 仍列出非利士人、住在亚实突的阿拉伯人和亚扪人，群体及居住地限定均未改变。
- Option C meaning: pass — 仍列出摩押人、住在埃及边界的亚玛力人和亚扪人，括号保留了亚玛力人的居住地限定。
- Option D meaning: pass — 仍列出非利士人、住在姑珥巴力的阿拉伯人和米乌尼人，完整保留原选项的三个群体及限定。
- Option E meaning: pass — 选项文字完全未变，仍表示根据这段文字无法判断。
- naturalness: 0/3 — “神帮助乌西雅攻打哪些人？”是直接、自然的问法。选项中的“阿拉伯人（住在姑珥巴力）”虽采用名单式表达，但括号说明符合中文列表习惯，无需修补语意。
- processing: 1/3 — 读者需理解“神帮助乌西雅攻打”的参与者关系，并逐项比较各选项的三个人群及括号内的居住地，例如区分A、D中的“亚扪人”和“非利士人”。这些操作属于核对完整人群名单所需的普通负荷；分行列举且修饰语紧邻所指人群，没有明显可避免的解析或比较负担。
- context_economy: 0/3 — 题目前没有额外引入说明，“神帮助乌西雅攻打哪些人？”直接提出任务。选项中的“住在姑珥巴力”等说明用于限定相应人群，不属于多余铺垫。

## hard:t1_2chr26:1fc4:open

Original: 谁爱好土地，所以设立了农夫和葡萄园工人？


### Attempt 1: ACCEPTED

谁喜爱土地，因此安排了农夫和葡萄园工人？

将搭配生硬的“爱好土地”改为“喜爱土地”，将不适合直接搭配人员的“设立”改为“安排”，保留人物识别目标及喜爱土地与安排人员之间的因果关系。

Pass 1:
- Review: KEEP
- same_target: pass — 两题都问谁因喜爱土地而设立农夫和葡萄园工人，所指均为乌西雅。“喜爱／爱好”“因此／所以”“安排／设立”在此保留了相同的参与者、行为及因果关系。
- same_language: pass — 原问题与修订问题均为中文。
- naturalness: 1/3 — “谁喜爱土地”表达直接；“安排了农夫和葡萄园工人”略显生硬，因为“安排”后只列出人员，没有说明安排他们做什么，但在耕作语境中仍可理解，不需要明显的语义修补。
- processing: 1/3 — 读者需要将“谁”同时理解为“喜爱土地”和“安排了农夫和葡萄园工人”的主体，并通过“因此”连接两项行为。两个谓语相邻、主体不变，“农夫和葡萄园工人”也明确是被安排的人员，属于普通、可管理的理解要求。
- context_economy: 0/3 — 题干“谁喜爱土地，因此安排了农夫和葡萄园工人？”没有额外引言或旁支说明；两项行为共同限定所问人物，没有明显可删的冗余铺垫。

Pass 2:
- Review: KEEP
- same_target: pass — Both questions ask who loved the land and consequently appointed farmers and vineyard workers. “喜爱/爱好,” “因此/所以,” and “安排/设立” preserve the participants, actions, and causal relationship; the passage identifies the person as 乌西雅.
- same_language: pass — Both the original and revised respondent-facing questions are in Chinese.
- naturalness: 1/3 — “安排了农夫和葡萄园工人”略显生硬：“安排”后只列出人员，没有说明安排他们做什么，但仍可自然理解为安排这些人从事相应工作。其余措辞通顺。
- processing: 1/3 — 读者需将“谁”同时理解为“喜爱土地”和“安排了农夫和葡萄园工人”的主语，并用“因此”连接两个动作。这是普通、可管理的因果结构；并列宾语也较短，没有明显可避免的复杂修饰或指代负担。
- context_economy: 0/3 — 题目没有额外引言；“喜爱土地”和“安排了农夫和葡萄园工人”共同构成所问人物的描述，没有明显多余的背景铺垫。

## hard:t1_2chr26:1fc4:mcq

Original: 谁爱好土地，所以设立了农夫和葡萄园工人？

- A. 葡萄园工人
- B. 约坦
- C. 乌西雅
- D. 田野中的农夫
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

谁因为喜爱土地而安排了农夫和葡萄园工人？

将搭配生硬的“爱好土地”和“设立了农夫和葡萄园工人”改为“喜爱土地”和“安排了农夫和葡萄园工人”，保留所问人物、因果关系及两类工作人员，使表达更自然。
- A. 葡萄园工人
- B. 约坦
- C. 乌西雅
- D. 田野中的农夫
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 两题都询问因喜爱土地而设立或安排农夫和葡萄园工人的人是谁；“因为喜爱土地而安排”保留了原题的因果关系、行为主体及两类工人，答案均为乌西雅。
- same_language: pass — 修订后的问题和所有选项均保持原文的中文。
- Option A meaning: pass — 选项保持“葡萄园工人”不变。
- Option B meaning: pass — 选项保持“约坦”不变。
- Option C meaning: pass — 选项保持“乌西雅”不变。
- Option D meaning: pass — 选项保持“田野中的农夫”不变。
- Option E meaning: pass — 选项保持“根据这段文字无法判断”不变，仍表达无法依据所给文字确定答案。
- naturalness: 1/3 — “谁因为喜爱土地而安排了农夫和葡萄园工人？”整体通顺，但“安排了农夫和葡萄园工人”对人员安排的表述略显生硬，没有说出安排他们做什么；结合“农夫和葡萄园工人”的职业名称仍能直接理解，无须明显的语义修补。
- processing: 1/3 — 读者需把“因为喜爱土地”理解为“安排”的原因，并区分“谁”所指的安排者与“农夫和葡萄园工人”这些被安排者。这是识别人选所需的普通角色辨认，主动句关系清楚。选项“田野中的农夫”的修饰关系也直接，没有实质性的可避免解析或选项比较负担。
- context_economy: 0/3 — 没有额外的介绍或铺垫；“因为喜爱土地”和“农夫和葡萄园工人”均用于界定所问的行为与人物，不属于冗余背景。

Pass 2:
- Review: KEEP
- same_target: pass — 两题均询问因喜爱土地而设立农夫和葡萄园工人的人是谁。“喜爱土地”对应“爱好土地”，“因为……而安排”保留了“所以设立”的因果关系及两类工人，目标均为乌西雅。
- same_language: pass — 修订后的问题和所有选项均保持原文的中文。
- Option A meaning: pass — 选项保持为“葡萄园工人”，含义未变。
- Option B meaning: pass — 选项保持为“约坦”，人物未变。
- Option C meaning: pass — 选项保持为“乌西雅”，人物未变。
- Option D meaning: pass — 选项保持为“田野中的农夫”，范围和身份未变。
- Option E meaning: pass — 选项保持为“根据这段文字无法判断”，无法判断的含义和依据范围未变。
- naturalness: 1/3 — “安排了农夫和葡萄园工人”略显生硬：“安排了”直接接人员，却没有说明安排他们做什么或到哪里，搭配不如日常表达完整；不过整句意思仍可直接理解，无须明显的语义修补。
- processing: 1/3 — 读者需把“因为喜爱土地”和“安排了”的主体都理解为“谁”，并区分安排者与“农夫和葡萄园工人”。这是普通的因果和主宾关系处理；选项“葡萄园工人”“田野中的农夫”也容易作为人员身份理解，没有实质性的额外修饰、指代或选项比较负担。
- context_economy: 0/3 — 题目没有额外引言；“因为喜爱土地”用于限定所问行动及其动机，“农夫和葡萄园工人”说明安排的对象，均服务于题意，没有多余背景铺陈。

## hard:t1_2chr26:723e:open

Original: 这三十万七千五百训练有素的军队由谁统领？


### Attempt 1: ACCEPTED

这三十万七千五百名训练有素的士兵由谁统领？

将数量短语改为“三十万七千五百名训练有素的士兵”，明确数字表示士兵人数，而非军队数量，消除量词缺失和数量修饰关系不清造成的理解负担，同时保留人数、训练情况和所问的统领关系。

Pass 1:
- Review: KEEP
- same_target: pass — Both questions ask who commanded the same 307,500 trained soldiers. Replacing “军队” with “名…士兵” preserves the commanded group and leadership relationship; verses 26:12–13 identify the commanders as the 2,600 family leaders.
- same_language: pass — Both the original and revised respondent-facing questions are in Chinese.
- naturalness: 0/3 — “这三十万七千五百名训练有素的士兵由谁统领？”符合自然的中文问法；数量和“训练有素”都清楚地修饰“士兵”，“由谁统领”直接询问统领者，无须修补语意或重组句子。
- processing: 1/3 — 读者需将“这三十万七千五百名训练有素的士兵”对应到经文中的军队，再追溯“他们统领的军队”中“他们”的所指。这是理解所问统领关系所需的普通跨句指代处理；问句没有增加可避免的角色、修饰层级或选项比较负担。
- context_economy: 0/3 — 问句没有额外引言或旁支说明。“这三十万七千五百名训练有素的士兵”用于明确所问的军队，属于有用的对象标识，而非多余铺垫。

Pass 2:
- Review: KEEP
- same_target: pass — 两题都询问谁统领这三十万七千五百名训练有素的士兵；将“军队”改为“名……士兵”未改变所指群体或统领关系。根据26:12–13，答案均为二千六百名勇士家族的首领。
- same_language: pass — 原题与修订题均使用中文。
- naturalness: 0/3 — “这三十万七千五百名训练有素的士兵由谁统领？”语序自然，“由谁统领”是常用的询问统领者的表达；数量与“训练有素”修饰“士兵”，搭配清楚，无须修补句意。
- processing: 1/3 — 读者需要用“三十万七千五百名训练有素的士兵”定位相应军队，再将“他们统领”中的“他们”回指到上一节的“勇士家族的首领”。这是识别统领者所需的普通跨句关联；问句本身没有增加可避免的角色转换或修饰语嵌套。
- context_economy: 0/3 — 问句没有额外引言；“这三十万七千五百名训练有素的士兵”直接指明所问的军队，是有用且简洁的定位信息，没有无关铺垫。

## hard:t1_2chr26:723e:mcq

Original: 这三十万七千五百训练有素的军队由谁统领？

- A. 哈拿尼雅
- B. 耶列和玛西亚
- C. 乌西雅
- D. 那二千六百个家族首领
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

这三十万七千五百名训练有素的士兵由谁统领？

将人数后的中心语改为“名训练有素的士兵”，明确数字计量的是士兵而非军队，消除数量搭配不当造成的理解负担；保留人数、训练状态及所问的统领关系，选项不变。
- A. 哈拿尼雅
- B. 耶列和玛西亚
- C. 乌西雅
- D. 那二千六百个家族首领
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — Both questions ask who commanded the same 307,500 trained soldiers. Replacing “军队” with “名训练有素的士兵” preserves the force, command relationship, and requested leaders identified in verses 26:12–13.
- same_language: pass — The revised question and all five options remain in Chinese, matching their original fields.
- Option A meaning: pass — Unchanged: “哈拿尼雅” names the same individual.
- Option B meaning: pass — Unchanged: “耶列和玛西亚” names the same two individuals.
- Option C meaning: pass — Unchanged: “乌西雅” names the same individual.
- Option D meaning: pass — Unchanged: “那二千六百个家族首领” identifies the same 2,600 family leaders.
- Option E meaning: pass — Unchanged: “根据这段文字无法判断” retains the claim that the passage does not allow the answer to be determined.
- naturalness: 0/3 — “这三十万七千五百名训练有素的士兵由谁统领？”语序自然，“训练有素的”明确修饰“士兵”，“由谁统领”直接询问统领者。选项中的姓名及“那二千六百个家族首领”表述通顺，无须在理解时修补措辞。
- processing: 1/3 — 读者需识别“三十万七千五百名训练有素的士兵”所指的军队，再把“他们统领”中的“他们”联系到上一节的家族首领，并比较选项中的人物角色。这是辨认统领者所需的普通处理需求；问句本身没有额外的嵌套、含混角色或可避免的迂回指代。
- context_economy: 0/3 — 没有额外的题目前言。“这三十万七千五百名训练有素的士兵”用于定位所问的军队，随后直接问“由谁统领”，没有无关铺垫。

Pass 2:
- Review: KEEP
- same_target: pass — Both questions ask who commanded the same 307,500 trained troops. Replacing “训练有素的军队” with “名训练有素的士兵” preserves the participants and command relationship identified in 26:12–13.
- same_language: pass — The revised question and all five options remain in Chinese, matching their original fields.
- Option A meaning: pass — Unchanged: “哈拿尼雅” identifies the same person.
- Option B meaning: pass — Unchanged: “耶列和玛西亚” identifies the same pair of people.
- Option C meaning: pass — Unchanged: “乌西雅” identifies the same person.
- Option D meaning: pass — Unchanged: “那二千六百个家族首领” identifies the same 2,600 family leaders.
- Option E meaning: pass — Unchanged: “根据这段文字无法判断” retains the claim that the answer cannot be determined from the passage.
- naturalness: 0/3 — “这三十万七千五百名训练有素的士兵由谁统领？”语序自然，“由谁统领”直接询问统领者。各选项均为自然的人名、群体名称或判断表述；“那二千六百个家族首领”中的“个”也不妨碍理解。
- processing: 1/3 — 读者需要将“这三十万七千五百名训练有素的士兵”与经文中的军队对应，再将“他们”回指到前句的家族首领，并比较选项中的人物或群体。这些操作属于理解所考查统领关系的正常需求。“三十万七千五百名训练有素的士兵”虽较长，但修饰关系清楚，没有额外嵌套或需要返工的歧义。
- context_economy: 0/3 — 题目没有额外引言或情境铺垫。“这三十万七千五百名训练有素的士兵”用于明确所问的军队，选项“那二千六百个家族首领”中的人数用于对应群体，均有指称作用，没有明显多余的背景说明。

## hard:t1_2kgs11:f49c:open

Original: 耶何耶大立的第一个约，是在哪些之间立的？


### Attempt 1: ACCEPTED

耶何耶大第一次是与谁立约的？

将不完整的“在哪些之间”改为自然的“与谁”，明确询问与耶何耶大立约的其他各方，消除是否应将耶何耶大列入答案的歧义。保留“第一次”以区分两次立约，并减少“立的……立的”的重复。

Pass 1:
- Review: KEEP
- same_target: pass — 原题询问耶何耶大所立第一个约的参与方，修订题询问他第一次与谁立约；两者均指向11:17的第一个约，要求回答耶和华、王和百姓，未改变人物关系或先后顺序。
- same_language: pass — 原题和修订题均为中文。
- naturalness: 0/3 — “耶何耶大第一次是与谁立约的？”语序自然，“是与谁……的”是常见的疑问表达，询问立约对象，不需要读者修补句意。
- processing: 1/3 — 读者需保持“耶何耶大”为立约主体，并将“第一次”对应到先叙述的立约事件，与“他又与王和百姓立约”区分。这是确定所问事件所需的普通顺序辨认与角色追踪，没有额外的修饰、指代或选项比较负担。
- context_economy: 0/3 — 题干没有额外铺垫；“第一次”用于区分所问的立约事件，是有用的限定，不是冗余背景。

Pass 2:
- Review: KEEP
- same_target: pass — 两问都询问耶何耶大所立第一个约涉及的对象，即耶和华、王和百姓；修订保留了“第一个约”的时间限定及全部所求对象。
- same_language: pass — 原问题与修订问题均为中文。
- naturalness: 0/3 — “耶何耶大第一次是与谁立约的？”表达自然；“是与谁……的”明确询问立约对象，无须读者修补语序或词语搭配。
- processing: 1/3 — 读者需要将“第一次”对应到先叙述的立约事件，并与“他又与王和百姓立约”区分，再提取相应对象。这是理解所问事件所需的普通定位操作，没有额外的嵌套、修饰语或选项比较负担。
- context_economy: 0/3 — 问句中的“耶何耶大”和“第一次”分别明确人物与所问事件，均有作用；没有另加冗余导语或旁枝说明。

## hard:t1_2kgs11:f49c:mcq

Original: 耶何耶大立的第一个约，是在哪些之间立的？

- A. 耶和华、王和百姓
- B. 王和百夫长
- C. 耶和华和守卫
- D. 王和百姓
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

第一次立约时，耶何耶大是与谁立约的？

将生硬的“在哪些之间”改为自然的“与谁立约”，保留第一次立约的事件限定。明确询问与耶何耶大立约的其他各方，而非所有参与者，解决原问法与答案名单范围不一致的问题；不将耶何耶大改作仅仅居间立约的人。
- A. 耶和华、王和百姓
- B. 王和百夫长
- C. 耶和华和守卫
- D. 王和百姓
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 两题均询问耶何耶大第一次立约所涉及的对象；原始答案元数据明确为“耶和华、王和百姓”，修订保留了这一关系及第一次立约的时间限定。
- same_language: pass — 修订后的问题仍为中文，所有选项也均保留原来的中文表述。
- Option A meaning: pass — 选项未变，仍指耶和华、王和百姓三方。
- Option B meaning: pass — 选项未变，仍指王和百夫长。
- Option C meaning: pass — 选项未变，仍指耶和华和守卫。
- Option D meaning: pass — 选项未变，仍指王和百姓。
- Option E meaning: pass — 选项未变，仍表示根据所给文字无法判断。
- naturalness: 0/3 — “第一次立约时，耶何耶大是与谁立约的？”表达自然，“是与谁……的”是常见的询问方式。选项“耶和华、王和百姓”等列举简洁，“根据这段文字无法判断”也符合中文习惯。
- processing: 1/3 — 读者需将“第一次立约时”对应到前一次立约，保持“耶何耶大”为立约者，再比较“耶和华、王和百姓”与“王和百姓”的成员差别。这些操作直接服务于所问对象的辨认；问句没有复杂嵌套，选项较短，属于普通且可管理的处理需求。
- context_economy: 0/3 — 题目没有额外引言；“第一次立约时”用于限定所问事件，“耶何耶大”明确立约者，均有实际作用，没有多余的背景铺陈。

Pass 2:
- Review: KEEP
- same_target: pass — 两题都询问耶何耶大第一次立约所涉及的对象；原始答案明确为“耶和华、王和百姓”。修订保留了耶何耶大、第一次立约的时间限定及全部所问对象。
- same_language: pass — 修订后的问题及全部选项均保持中文，与原对应字段的语言一致。
- Option A meaning: pass — 选项未改动，仍为“耶和华、王和百姓”。
- Option B meaning: pass — 选项未改动，仍为“王和百夫长”。
- Option C meaning: pass — 选项未改动，仍为“耶和华和守卫”。
- Option D meaning: pass — 选项未改动，仍为“王和百姓”。
- Option E meaning: pass — 选项未改动，仍表示根据所给文字无法判断。
- naturalness: 0/3 — “第一次立约时，耶何耶大是与谁立约的？”是自然的中文问法；“是与谁……的”明确询问参与者。各选项均为简短名单或常见的判断表述，没有不自然的修饰关系或需要心智修补的措辞。
- processing: 1/3 — 读者需将“第一次立约时”对应到前一次立约，再比较“耶和华、王和百姓”与“王和百姓”的名单差别。这是与辨认立约对象直接相关的普通定位和比较操作；问句角色明确，选项简短，没有显著可避免的解析或记忆负担。
- context_economy: 0/3 — 题目没有额外引言；“第一次立约时”用于限定所问事件，“耶何耶大”用于明确参与者，均有必要。选项直接呈现待比较的对象，没有多余背景铺陈。

## hard:t1_acts19:7628:open

Original: 被那附着邪灵的人制服以后，谁受伤逃出了那房子？


### Attempt 1: NOT_ACCEPTED

谁被那个邪灵附身的人制服后，带伤逃出了那房子？

将“附着邪灵的人”改为自然、关系明确的“邪灵附身的人”，并把“谁”提前，减少先解析被动时间分句、再补认受事的负担。保留被制服后受伤逃出房子的事件关系。

Pass 1:
- Review: REWRITE
- same_target: pass — 两题都询问谁被邪灵附着的人制服后，受伤逃出那房子；人物角色、事件及先后关系不变，答案均为士基瓦的七个儿子。
- same_language: pass — 原问题与修订问题均为中文；“邪灵附身”与“附着邪灵”、“带伤”与“受伤”均为同语言改述。
- naturalness: 1/3 — 整体可理解，“带伤逃出了那房子”也自然；但“被那个邪灵附身的人制服后”中，被动标记紧接“邪灵附身”的人物修饰语，表达略显拗口，容易先被读成“被那个邪灵附身”。
- processing: 2/3 — 读到“谁被那个邪灵附身”时，读者容易先把“谁”理解为被邪灵附身者；读到“的人制服后”才需重新划分结构，把“那个邪灵附身的人”整体认作制服者，再将“谁”保持为带伤逃离者。区分制服者与逃离者是目标所需，但这种由“被”的作用范围引起的回读是可避免的额外负担。
- context_economy: 0/3 — 题目没有额外铺垫。“制服后”“带伤逃出”用于限定所问事件，“那个……人”和“那房子”用于连接经文中的人物与地点，没有明显多余的背景说明。

Pass 2:
- Review: KEEP
- same_target: pass — 两题都询问被邪灵附身的人制服后，受伤逃出那房子的是谁；参与者、制服与逃离的先后关系及受伤状态均未改变，答案仍是士基瓦的七个儿子。
- same_language: pass — 原问题与修订问题均为中文；“附着邪灵”改为“邪灵附身”、“受伤”改为“带伤”不改变语言。
- naturalness: 1/3 — 整体问法通顺，但“那个邪灵附身的人”略显压缩：“那个”紧接“邪灵”，容易先被读成修饰“邪灵”，而不是后面的“人”。“带伤逃出了那房子”则直接自然。局部措辞稍欠顺畅，尚不需要大幅修复句意。
- processing: 1/3 — 读者需要把“那个邪灵附身的人”整体识别为“制服”的施事，并让“谁”同时承接被制服者和逃出者两个角色。“被那个邪灵附身的人”可能短暂被切分为“被那个邪灵附身”，但读到“制服后”即可确定结构。全句只有两个顺序事件，共同主语清楚，属于可管理的局部解析负担。
- context_economy: 0/3 — 没有额外的题目前言。“被……制服后”和“带伤逃出了那房子”均用于描述所问人物经历的事件，没有明显无关或重复的铺垫。

### Attempt 2: ACCEPTED

那个被邪灵附身的人制服了一些人。这些人随后带伤逃出了那房子，他们是谁？

用“被邪灵附身的人”明确人与邪灵的关系，并以主动句交代制服事件，避免先前“谁被那个邪灵附身……”造成的切分歧义。保留被制服者随后受伤逃出房子的事件关系，再询问其身份。

Pass 1:
- Review: KEEP
- same_target: pass — 两题都询问被邪灵附身的人制服后、带伤逃出那房子的人的身份，即士基瓦的七个儿子。修订保留了参与者角色、事件先后关系和受伤逃出房子的条件，未透露所求身份。
- same_language: pass — 原题和修订题均使用中文。
- naturalness: 0/3 — “那个被邪灵附身的人”“随后带伤逃出了那房子”和“他们是谁”都是自然、直接的中文表达。“一些人—这些人—他们”的衔接略有重复，但符合口语问答习惯，不需要读者修补句意。
- processing: 1/3 — 读者需要区分“被邪灵附身的人”与他“制服”的“一些人”，再把“这些人”和“他们”接续到后者。两句话中的角色和指代保持稳定，且“制服”与“带伤逃出”共同服务于人物辨认，属于普通、可管理的理解要求，没有明显可避免的解析负担。
- context_economy: 0/3 — “制服了一些人”和“这些人随后带伤逃出了那房子”提供了辨认所问群体的相关经历；题目没有额外背景或旁支说明。“他们是谁”直接提出身份问题，整体铺垫经济。

Pass 2:
- Review: KEEP
- same_target: pass — 两问都要求指出被附着邪灵的人制服后、带伤逃出那房子的人是谁；修订保留了人物角色、事件先后关系和受伤逃出的条件，未透露其身份。
- same_language: pass — 原问题和修订问题均为中文；“被邪灵附身”与“附着邪灵”是同一语言中的对应表述。
- naturalness: 0/3 — “被邪灵附身的人”“制服了一些人”和“带伤逃出了那房子”均是自然、清楚的中文表达。“这些人……他们是谁？”以先叙述、再提问的方式询问身份，虽重复指称，但不需要读者修补句意。
- processing: 1/3 — 读者需要区分“那个被邪灵附身的人”和被制服的“一些人”，再将“这些人”“他们”连接到后者。单数与复数的区别、相邻的回指以及“随后”的事件衔接使关系容易保持，属于普通且服务于辨认目标人物的处理需求，没有显著可避免的负担。
- context_economy: 0/3 — “制服了一些人”和“随后带伤逃出了那房子”提供用于辨认同一群人的事件线索，随后直接问“他们是谁？”。没有另加背景说明或无关铺垫。

## hard:t1_acts19:7628:mcq

Original: 被那附着邪灵的人制服以后，谁受伤逃出了那房子？

- A. 那附着邪灵的人
- B. 保罗
- C. 以弗所的希腊人
- D. 士基瓦的七个儿子
- E. 根据这段文字无法判断

### Attempt 1: NOT_ACCEPTED

谁被那个被邪灵附着的人制服后，受伤逃出了那房子？

将问句和选项A中的人物描述改为“被邪灵附着的人”，明确人与邪灵的关系；将“谁”提前，使被制服者与随后受伤逃出者直接衔接，保留原有事件顺序和地点。
- A. 那个被邪灵附着的人
- B. 保罗
- C. 以弗所的希腊人
- D. 士基瓦的七个儿子
- E. 根据这段文字无法判断

Pass 1:
- Review: REWRITE
- same_target: pass — 两题都问谁在被邪灵附着的人制服之后，受伤逃出那房子；人物角色、事件及先后关系均未改变，所求仍为士基瓦的七个儿子。
- same_language: pass — 修订后的题目和所有选项均保持原来的中文。
- Option A meaning: pass — “那附着邪灵的人”与“那个被邪灵附着的人”在本段语境中均指被邪灵附着、制服众人的那个人。
- Option B meaning: pass — 选项仍为“保罗”，指称未变。
- Option C meaning: pass — 选项仍为“以弗所的希腊人”，群体与范围未变。
- Option D meaning: pass — 选项仍为“士基瓦的七个儿子”，人物及人数未变。
- Option E meaning: pass — 选项仍为“根据这段文字无法判断”，无法据文判断的含义未变。
- naturalness: 1/3 — “谁被那个被邪灵附着的人制服后”语法成立，但两个“被”字结构套用，表达略显生硬、绕口；“受伤逃出了那房子”和各选项的措辞基本自然。
- processing: 2/3 — 读到“被那个被邪灵附着的人制服后”时，需要暂存第一个“被”所开启的关系，把“被邪灵附着”归入对“人”的修饰，再接回“制服”，确定谁制服了谁。这种嵌套造成明显且可避免的解析负荷；目标虽要求区分制服者与逃走者，却不要求用双层被动来表达。随后保持“谁”为“受伤逃出”的主体，以及比较各人物选项，均属普通可管理的任务。
- context_economy: 0/3 — 没有额外引言。“制服后，受伤逃出了那房子”直接限定所问事件，“那个被邪灵附着的人”用于说明事件参与者；这些内容均服务于人物识别，没有明显多余的背景铺陈。嵌套造成的问题属于句法处理负荷，而非背景过量。

Pass 2:
- Review: REWRITE
- same_target: pass — 两题都询问谁在被邪灵附着的人制服后，受伤逃出了那房子；人物角色、事件及先后关系均未改变，所求仍是士基瓦的七个儿子。
- same_language: pass — 修订后的问题和全部选项仍为中文，与各自原字段的语言一致。
- Option A meaning: pass — “那附着邪灵的人”与“那个被邪灵附着的人”在本段中指同一个被邪灵附着、制服他们的人。
- Option B meaning: pass — 选项保持为“保罗”，所指未变。
- Option C meaning: pass — 选项保持为“以弗所的希腊人”，群体与范围未变。
- Option D meaning: pass — 选项保持为“士基瓦的七个儿子”，人物及人数未变。
- Option E meaning: pass — 选项保持为“根据这段文字无法判断”，无法依据段落确定答案的含义未变。
- naturalness: 1/3 — “谁被那个被邪灵附着的人制服后”语法成立，但“被那个被……”连续嵌套，表达略显拗口；“受伤逃出了那房子”和各选项本身没有明显不自然的措辞。
- processing: 2/3 — 读到“谁被那个被邪灵附着的人制服后”时，读者必须暂存外层“谁被”，先把第二个“被”及“邪灵附着”收进“那个人”的修饰语，等到“制服”才完成外层施受关系。这种双层被动造成可避免的句法负荷，并非辨认制服者与逃走者所必需。后半句“受伤逃出了那房子”及简短选项未再增加明显的解析或比较负荷。
- context_economy: 0/3 — 没有额外的介绍或背景铺陈。“被那个被邪灵附着的人制服后”和“受伤逃出了那房子”都用于界定所问的人物和事件，属于有用信息；问题在于嵌套表达，而不是上下文过多。

### Attempt 2: ACCEPTED

谁被那个邪灵附身的人制服，随后受伤逃出了那房子？

将“谁”提前，明确被制服者也是随后受伤逃出的人；用自然的“邪灵附身的人”说明人物身份，修正原来的附着关系表达，并避免上一版双层“被”字结构的嵌套。保留了制服、受伤逃出及其先后关系，选项A同步调整措辞。
- A. 那个邪灵附身的人
- B. 保罗
- C. 以弗所的希腊人
- D. 士基瓦的七个儿子
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 两题均询问被邪灵附身的人制服后、受伤逃出房子的是谁；参与者、动作及先后关系均未改变，答案仍是士基瓦的七个儿子。
- same_language: pass — 修订后的问题及所有选项仍为中文，与各原始字段的语言一致。
- Option A meaning: pass — “那个邪灵附身的人”与“那附着邪灵的人”指同一个被邪灵附着的人。
- Option B meaning: pass — 选项仍为“保罗”，所指人物未变。
- Option C meaning: pass — 选项仍为“以弗所的希腊人”，群体及地域限定未变。
- Option D meaning: pass — 选项仍为“士基瓦的七个儿子”，人物关系及人数未变。
- Option E meaning: pass — 选项仍为“根据这段文字无法判断”，无法由本文判断的含义未变。
- naturalness: 1/3 — 整体表达可以理解，但“那个邪灵附身的人”的修饰关系略显不顺：“那个”紧接“邪灵”，容易短暂被理解为指示邪灵，而不是指示人。“随后受伤逃出了那房子”及各选项基本自然，没有明显病句。
- processing: 1/3 — 读到“谁被那个邪灵附身”时，可能先理解为询问谁被邪灵附身；读到“的人制服”后，需将“那个邪灵附身的人”重新组合为制服者。这是局部、可避免的回读诱因，但短语较短，后续谓语能明确角色，尚不构成 substantial 的解码负担。“随后”承接同一个“谁”，选项也都是简短的人物名称或判断，无须复杂比较。
- context_economy: 0/3 — 题目没有另加背景介绍。“被……制服”与“随后受伤逃出了那房子”共同限定所问人物，属于有用的事件描述；“那个”和“那房子”也只是简短回指，没有多余铺垫。

Pass 2:
- Review: KEEP
- same_target: pass — 两题均询问被邪灵附身的人制服后、受伤逃出那房子的是谁；参与者、被制服与逃出的先后关系及受伤状态均保留。
- same_language: pass — 修订后的问题及所有选项均与原文一样使用中文。
- Option A meaning: pass — “那个邪灵附身的人”与“那附着邪灵的人”指同一名被邪灵附着的人。
- Option B meaning: pass — 选项仍为“保罗”，指称未变。
- Option C meaning: pass — 选项仍为“以弗所的希腊人”，人群及地域范围未变。
- Option D meaning: pass — 选项仍为“士基瓦的七个儿子”，人物及人数未变。
- Option E meaning: pass — 选项仍为“根据这段文字无法判断”，无法依据段落作答的含义未变。
- naturalness: 0/3 — “谁被……制服，随后受伤逃出了那房子？”是自然的汉语问法；“邪灵附身的人”也是可理解的日常修饰结构。选项均为直接的人物名称、人物描述或常规的无法判断选项，没有明显生硬或需要修补的措辞。
- processing: 1/3 — 读者需要把“那个邪灵附身的人”整体识别为制服他人的施事，并让句首的“谁”继续充当“受伤逃出”的主体。读到“谁被那个邪灵附身”时，可能短暂理解为“谁被邪灵附身”，但紧接的“的人制服”即可明确结构，局部回读需求有限。选项之间没有复杂的句式差异，人物角色区分属于本题所需的普通理解负荷。
- context_economy: 0/3 — 没有额外的引言或背景铺陈。“随后受伤逃出了那房子”继续限定所问人物及其经历，“那房子”只是简短的地点回指，没有形成冗余情境负担。

## hard:t1_judg17_18:725d:open

Original: 他们请谁为他们求问这趟行程？


### Attempt 1: ACCEPTED

他们请谁为他们求问神，看看这趟行程是否顺利？

将生硬的“求问这趟行程”改为“求问神，看看这趟行程是否顺利”，明确求问的对象和内容，同时保留请求者、代为求问者及行程之间的关系。

Pass 1:
- Review: KEEP
- same_target: pass — 两题都问他们请谁为他们求问这趟行程，所指均为祭司。修订补明求问神及行程是否顺利，与经文一致，没有改变所问人物、关系或增加答案要求。
- same_language: pass — 原题和修订题均使用简体中文。
- naturalness: 0/3 — “他们请谁为他们求问神”语序自然，受托者的位置明确；“看看这趟行程是否顺利”也符合日常汉语表达。“求问神”沿用经文措辞，无须对句法作额外修补。
- processing: 1/3 — 读者需要区分“他们”“谁”和“神”的角色，并把“这趟行程”联系到经文中的“我们行这路”。这些是理解所问人物所需的普通操作；两处“他们”指向一致，后半句直接说明求问内容，没有明显可避免的解析负担。
- context_economy: 0/3 — 题目没有额外铺垫；“为他们求问神”和“看看这趟行程是否顺利”共同限定所问的请求，均服务于人物识别，没有多余背景。

Pass 2:
- Review: KEEP
- same_target: pass — 两题都问他们请谁代为求问这趟行程，所求人物均为祭司。修订补明向神求问行程是否顺利，与经文中的求问内容一致，未改变参与者、关系或所需答案。
- same_language: pass — 原题与修订题均为简体中文；修订未改变面向答题者的问题语言。
- naturalness: 0/3 — “他们请谁为他们求问神”语序自然，明确询问受请求的人；“看看这趟行程是否顺利”自然地说明求问的目的。题目用语连贯，无需修补句意。
- processing: 1/3 — 读者需在“他们请谁为他们求问神”中区分请求者、代为求问者和求问对象，并将“这趟行程”与经文中的“我们行这路”对应。这些是识别所问人物所需的普通处理；两处“他们”指向稳定，“是否顺利”也没有增加可避免的嵌套或歧义。
- context_economy: 0/3 — 题目没有额外引言。“为他们求问神”交代被请求的行动，“看看这趟行程是否顺利”限定此次请求的内容，均直接服务于人物识别，没有多余背景。

## hard:t1_judg17_18:725d:mcq

Original: 他们请谁为他们求问这趟行程？

- A. 神
- B. 米迦的母亲
- C. 米迦
- D. 祭司
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

他们请谁替他们求问神，看看这趟行程是否顺利？

将生硬的“求问这趟行程”改为“求问神，看看这趟行程是否顺利”，明确求问的对象和事项，保留请求者、代为求问者及行程之间的关系，减少读者自行补足语义的负担。
- A. 神
- B. 米迦的母亲
- C. 米迦
- D. 祭司
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 两题都询问他们请谁代为求问这趟行程，答案均为祭司。修订补明向神求问行程是否顺利，与经文中的求问内容一致，未改变所问人物或透露答案。
- same_language: pass — 修订后的问题和所有选项均保持中文，与原对应字段的语言一致。
- Option A meaning: pass — A项仍为“神”，指称未变。
- Option B meaning: pass — B项仍为“米迦的母亲”，人物及关系未变。
- Option C meaning: pass — C项仍为“米迦”，指称未变。
- Option D meaning: pass — D项仍为“祭司”，人物角色未变。
- Option E meaning: pass — E项仍为“根据这段文字无法判断”，无法据文判断的含义及范围未变。
- naturalness: 0/3 — “他们请谁替他们求问神”语序自然，清楚表达请人代为求问的关系；“看看这趟行程是否顺利”是自然的目的说明。“求问”虽带宗教语境色彩，但在“求问神”的搭配中无需修补理解。选项措辞简洁。
- processing: 1/3 — 读者需在“他们请谁替他们求问神”中区分请求者、代为求问者和求问对象，再把“这趟行程”对应到引文中的“我们行这路”。这些都是辨认所问人物所需的普通操作；“谁”明确标记作答焦点，“是否顺利”只是求问内容，不形成实质性的额外解析或选项比较负担。
- context_economy: 0/3 — “看看这趟行程是否顺利”交代求问的目的，与前面的“替他们求问神”紧密相连。整题没有另加人物背景、解释性铺垫或无关情节，设置经济。

Pass 2:
- Review: KEEP
- same_target: pass — 两题都询问他们请谁代为求问这趟行程，所指人物均为祭司。修订补明求问神及行程是否顺利，与经文中的同一请求一致，未改变所问角色或透露答案。
- same_language: pass — 修订后的问题和所有选项均保持原来的中文。
- Option A meaning: pass — 选项保持为“神”，所指对象不变。
- Option B meaning: pass — 选项保持为“米迦的母亲”，所指人物及关系不变。
- Option C meaning: pass — 选项保持为“米迦”，所指人物不变。
- Option D meaning: pass — 选项保持为“祭司”，所指角色不变。
- Option E meaning: pass — 选项保持为“根据这段文字无法判断”，无法依据本段作答的含义不变。
- naturalness: 0/3 — “请谁替他们求问神”角色表达明确，“看看这趟行程是否顺利”衔接自然，符合日常中文表达；选项“神”“米迦的母亲”“米迦”“祭司”及“根据这段文字无法判断”也都措辞自然，无需修补句意。
- processing: 1/3 — 读者需区分“他们”“谁”和“神”的角色，并将问题中的“他们”对应到引语中的“我们”，再联系“祭司对他们说”。这些是辨认受请求者所需的普通理解操作；“替他们”明确了角色，“这趟行程”也指向清楚，没有额外的修饰语、指代或选项比较负担。
- context_economy: 0/3 — 没有额外导语。“看看这趟行程是否顺利”简短说明求问的目的，与“请谁替他们求问神”构成完整、集中的提问，没有无关背景或重复铺垫。

## hard:t1_judg17_18:c2d9:mcq

Original: 谁进去拿走了雕像、以弗得、家用神像和熔铸的偶像？

- A. 六百带兵器的但人
- B. 那少年利未人
- C. 那五个窥探地的人
- D. 米迦和他的家人
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

谁进去拿走了雕像、以弗得、家用神像和熔铸的偶像？

将选项C中不自然且容易产生词性歧义的“窥探地”改为“曾去侦察那片土地”，明确侦察的对象，保留人数、人物身份及原有含义。题干的连续动作和四项物品均予以保留。
- A. 六百带兵器的但人
- B. 那少年利未人
- C. 那五个曾去侦察那片土地的人
- D. 米迦和他的家人
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 问题完全未变，仍询问谁进去拿走了所列的雕像、以弗得、家用神像和熔铸的偶像。
- same_language: pass — 问题和所有选项均保留中文；C项的改写也是中文。
- Option A meaning: pass — A项未变，仍指六百带兵器的但人。
- Option B meaning: pass — B项未变，仍指那少年利未人。
- Option C meaning: pass — “那五个曾去侦察那片土地的人”与“那五个窥探地的人”指同一组五人，保留了人数及他们此前窥探土地的身份。
- Option D meaning: pass — D项未变，仍指米迦和他的家人。
- Option E meaning: pass — E项未变，仍表示根据这段文字无法判断。
- naturalness: 1/3 — 问句“谁进去拿走了……”及选项C“那五个曾去侦察那片土地的人”表达自然。选项A“六百带兵器的但人”和B“那少年利未人”省略常见量词，带有轻微的经文式书面语色彩，但不需要明显的语义修补。
- processing: 1/3 — 读者需将“进去”和“拿走”归于同一行动者，并把选项C“曾去侦察那片土地的人”与文中的“窥探地的人”对应。这是普通的动作归属和同义表述对应；“雕像、以弗得、家用神像和熔铸的偶像”虽有四项，但均为平行宾语，不需要逐项比较其性质。整体有可管理的理解需求，没有实质性的可避免解码负担。
- context_economy: 0/3 — 没有额外引言或背景铺垫。问句直接以“谁进去拿走了……”询问行动者，所列物品用于明确所问事件；选项也仅列候选人物及“根据这段文字无法判断”，没有多余情境说明。

Pass 2:
- Review: KEEP
- same_target: pass — 两版问题完全相同，均询问谁进去拿走了所列的四类物品，未改变参与者角色、动作或所求信息。
- same_language: pass — 问题和所有选项均保持中文；选项C的改写也仍为中文。
- Option A meaning: pass — 选项A未变，均指六百带兵器的但人。
- Option B meaning: pass — 选项B未变，均指那少年利未人。
- Option C meaning: pass — “那五个曾去侦察那片土地的人”与“那五个窥探地的人”指同一组先前侦察该地的五个人，人数、身份和行为关系不变。
- Option D meaning: pass — 选项D未变，均指米迦和他的家人。
- Option E meaning: pass — 选项E未变，均表示根据这段文字无法判断。
- naturalness: 1/3 — 问句“谁进去拿走了……”直接自然，选项C“那五个曾去侦察那片土地的人”也符合汉语习惯。选项A“六百带兵器的但人”省略了人数后的量词，选项B“那少年利未人”也带有书面省略色彩；普通成人能够理解，但措辞略显生硬。
- processing: 1/3 — 读者需要把“进去”和“拿走”理解为同一个人的连续动作，并比较各选项中的人物身份。“雕像、以弗得、家用神像和熔铸的偶像”虽是较长的宾语列表，但并列关系明确，不必辨析每件物品的性质才能理解问题。选项C中的“曾去侦察那片土地”仅用一层修饰语识别人群，整体属于普通、可管理的阅读需求，未见实质性的可避免解析负担。
- context_economy: 0/3 — 没有额外的引导或背景铺陈；“谁进去拿走了……”直接询问行动者，所列物品用于明确所问事件。各人物选项也没有加入无关叙述，未见多余情境增加阅读成本。

## hard:t1_judg17_18:3162:open

Original: 那些神像最先发生了什么事？


### Attempt 1: ACCEPTED

经文中，人们最先对那些神像做了什么？

将生硬的“神像发生了什么事”改为“人们对神像做了什么”，明确神像是动作的承受对象，减少读者修补主谓关系的负担；保留对神像的回指及“最先”的事件顺序要求。

Pass 1:
- Review: KEEP
- same_target: pass — 两题都询问那些神像最先经历的事件，即五个窥探地的人从米迦家拿走它们。修订将事件表述为人们对神像的行动，保留了对象、事件关系及“最先”的时间限定，也未透露答案。
- same_language: pass — 原题和修订题均为中文。
- naturalness: 0/3 — “经文中，人们最先对那些神像做了什么？”语序自然，“对……做了什么”是常见问法；“人们”和“那些神像”虽较概括，但结合所给经文阅读，不需要修补句意。
- processing: 1/3 — 读者需要结合经文确定“人们”和“那些神像”的所指，并按“最先”区分前后的行动。这些是辨认最先行动所需的普通理解操作；问句没有额外的修饰嵌套、复杂角色关系或选项比较负担。
- context_economy: 0/3 — “经文中”简短地限定作答范围，“最先”明确所问的时间关系；没有额外引言或无关背景。

Pass 2:
- Review: KEEP
- same_target: pass — 两题均询问那些神像最先遭遇的事件，即五个窥探地的人从米迦家拿走它们。修订以主动表达询问人们对神像的行为，保留了对象、事件及“最先”的时间关系，未透露答案。
- same_language: pass — 原题和修订后的问题均为中文。
- naturalness: 0/3 — “经文中，人们最先对那些神像做了什么？”是自然的中文问句；“对……做了什么”直接询问动作，没有生硬搭配或需要重新拼接的语序。
- processing: 1/3 — 读者需将“人们”和“那些神像”对应到经文中的人物与物品，并根据“最先”区分前后的拿取动作。这是目标所需的普通回指和顺序判断；问句本身没有增加可避免的修饰、嵌套或选项比较负担。
- context_economy: 0/3 — 题面只有“经文中”这一简短的查找范围提示，其余文字均用于指定人物、对象、先后关系和所问动作，没有多余铺垫。

## hard:t1_judg17_18:3250:mcq

Original: 为什么没有人搭救来士的人？

- A. 因为那城远离西顿，也没有与人结盟。
- B. 因为他们夺了米迦的偶像和祭司
- C. 因为但人用刀杀灭他们
- D. 因为但人重建城邑，在那里居住
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

为什么没有人搭救来士的人？

将选项B中的“他们”明确为“但人”，避免读者误将其理解为题干中的来士居民，减少回查和修正指代的负担。其余内容保持不变。
- A. 因为那城远离西顿，也没有与人结盟。
- B. 因为但人夺了米迦的偶像和祭司
- C. 因为但人用刀杀灭他们
- D. 因为但人重建城邑，在那里居住
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 问题完全未变，仍询问无人搭救来士人的原因，保留远离西顿及没有与人结盟这两个答案组成部分。
- same_language: pass — 问题和所有选项均保持中文；B项只是将代词“他们”明确为“但人”。
- Option A meaning: pass — A项未变，仍表示那城远离西顿且没有与人结盟。
- Option B meaning: pass — B项将“他们”改为“但人”；根据所给经文，夺走米迦偶像和祭司的人就是但人，行为及参与者均未改变。
- Option C meaning: pass — C项未变，仍表示因为但人用刀杀灭他们。
- Option D meaning: pass — D项未变，仍表示因为但人重建城邑并在那里居住。
- Option E meaning: pass — E项未变，仍表示根据这段文字无法判断。
- naturalness: 0/3 — “为什么没有人搭救来士的人？”是自然的原因问句；“来士的人”在此表示该地居民，结合地名语境可以顺畅理解。选项采用“因为……”引出原因，措辞虽有“杀灭”“城邑”等书面用语，但不需要修补句法或词义。
- processing: 1/3 — 读者需要把“那城”联系到来士，把“他们”联系到来士居民，并区分居民与但人的行动；这些都是短距离、通常可管理的指代和角色衔接。“搭救来士的人”局部也可切分为“搭救来士”的人，但在“为什么没有人搭救……”及地名语境中，按“搭救／来士的人”理解并不困难。各选项句式简短，没有明显可避免的高负荷比较或嵌套。
- context_economy: 0/3 — 题目直接以“为什么没有人搭救来士的人？”提问，没有额外引言、情境铺陈或重复说明。选项也没有加入与作答操作无关的解释性背景。

Pass 2:
- Review: KEEP
- same_target: pass — 问题完全未变，仍询问为何无人搭救来士的人；所求原因仍是那城远离西顿且没有与人结盟。
- same_language: pass — 问题及所有选项均保留中文，未发生语言转换。
- Option A meaning: pass — A完全未变，保留远离西顿和没有与人结盟这两个原因。
- Option B meaning: pass — B将“他们”明确为“但人”；结合经文，夺走米迦的偶像和祭司的正是但人，参与者与行为未变。
- Option C meaning: pass — C完全未变，仍以但人用刀杀灭他们作为原因。
- Option D meaning: pass — D完全未变，仍以但人重建城邑并在那里居住作为原因。
- Option E meaning: pass — E完全未变，仍表示根据这段文字无法判断。
- naturalness: 1/3 — 问句“为什么没有人搭救来士的人？”自然可懂。选项B“但人夺了米迦的偶像和祭司”将物品和人物并列作“夺了”的宾语，略带经文式的生硬，尤其“夺了……祭司”不如日常表达自然，但不至于需要明显的语义修补。
- processing: 1/3 — 读者需要把选项A的“那城”、C的“他们”和D的“那里”分别联系到来士、当地居民和城邑，并区分居民与但人。这些回指较短，属于普通的阅读要求。“远离西顿，也没有与人结盟”直接并列两个原因，没有额外的否定或修饰层级；各选项也较短，未形成显著的可避免比较负担。
- context_economy: 0/3 — 题目没有另加背景介绍，直接以“为什么没有人搭救来士的人？”提出问题。选项均为简短的原因陈述或“根据这段文字无法判断”，没有无关铺垫或重复解释。

## hard:t1_judg17_18:97e8:mcq

Original: 约拿单和他的子孙作但支派的祭司，直到什么时候？

- A. 直到被掳之日。
- B. 直到他们给城起名叫但。
- C. 直到但人为自己立偶像。
- D. 神的殿在示罗多少日子，就到多少日子。
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

约拿单和他的子孙作但支派的祭司，直到什么时候？

仅修改D，将生硬的“多少日子，就到多少日子”改为明确的时间终点表达，保留任职持续到神的殿不再设在示罗这一时间关系，避免读者自行补足并转换时长与终点。
- A. 直到被掳之日。
- B. 直到他们给城起名叫但。
- C. 直到但人为自己立偶像。
- D. 直到神的殿不再设在示罗。
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 问题完全未变，仍询问约拿单和他的子孙作但支派祭司直到什么时候。
- same_language: pass — 问题及所有选项均保留中文。
- Option A meaning: pass — 选项未变，均以被掳之日为终点。
- Option B meaning: pass — 选项未变，均以他们给城起名叫但为终点。
- Option C meaning: pass — 选项未变，均以但人为自己立偶像为终点。
- Option D meaning: pass — 原选项表示任职持续到神的殿在示罗的时期结束；修订的“不再设在示罗”表达同一时间终点。
- Option E meaning: pass — 选项未变，均表示根据这段文字无法判断。
- naturalness: 0/3 — “约拿单和他的子孙作但支派的祭司，直到什么时候？”表达自然，所问的任职终止时间明确。“作……的祭司”符合此处语境；各选项措辞通顺，没有需要读者修补的语序或名词修饰关系。
- processing: 1/3 — 读者需将“他的”联系到紧邻的“约拿单”，并比较各选项所列的时间终点。“直到神的殿不再设在示罗”虽包含“不再”，但否定范围明确。这些都是普通、可管理的理解操作，未发现可避免的复杂嵌套或指代追踪负担。
- context_economy: 0/3 — 没有额外引言；“约拿单和他的子孙作但支派的祭司”直接限定所问人物和职分，“直到什么时候”提出时间问题。题干没有无关铺垫，选项也没有冗余说明。

Pass 2:
- Review: KEEP
- same_target: pass — 问题完全未变，仍询问约拿单和他的子孙作但支派祭司直到什么时候，参与者、职分和时间终点均保留。
- same_language: pass — 问题及全部选项均保持中文，D项的改写也未改变语言。
- Option A meaning: pass — A项未变，均以被掳之日为终点。
- Option B meaning: pass — B项未变，均以他们给城起名叫但为终点。
- Option C meaning: pass — C项未变，均以但人为自己立偶像为终点。
- Option D meaning: pass — 原D项表示任职持续到神的殿在示罗的这段时期结束；修订项以神的殿不再设在示罗表述同一时间终点。
- Option E meaning: pass — E项未变，均表示根据这段文字无法判断。
- naturalness: 0/3 — 题干“约拿单和他的子孙作但支派的祭司，直到什么时候？”表达自然，任职者、职务和所问时间都直接呈现。“直到被掳之日”较书面，但在这里是正常的时间表达，不需要修补句意。
- processing: 1/3 — 主要需求是把“直到什么时候”关联到“作但支派的祭司”的任职期限，并比较各选项的时间终点。B项“直到他们给城起名叫但”中的“他们”可能先被理解为题干中的约拿单及其子孙，需要结合经文的命名事件确认指代；不过只涉及一次局部回指，整体仍属普通、可管理的理解负荷。D项“不再设在示罗”的否定状态也可直接理解，没有复杂的否定嵌套。
- context_economy: 0/3 — 题干直接以“约拿单和他的子孙作但支派的祭司”限定所问事件，没有另加背景介绍、重复说明或无关铺垫；这些信息都有助于确定“直到什么时候”所问的期限。

## hard:t1_judg9:6d68:open

Original: 约坦呼叫示剑的众首领听他的话，是为了什么结果？


### Attempt 1: DECLINED



“呼叫……听他的话”和“是为了什么结果”的搭配确实生硬，但问题还涉及无法仅靠措辞解决的内容障碍：经文表达的是约坦要求众首领听他的话，并祝愿神也听他们的话，并未明确将后者作为前者的目的或结果。保留原题及固定答案的目的关系，会继续存在依据不足的问题；改问约坦表达了什么祝愿，则会改变原题所考查的关系，因此不能仅通过文字修订解决。

## hard:t1_judg9:6d68:mcq

Original: 约坦呼叫示剑的众首领听他的话，是为了什么结果？

- A. 为自己膏立一个王。
- B. 召集他们赴宴。
- C. 警告他们有危险。
- D. 使神也听他们的话。
- E. 根据这段文字无法判断

### Attempt 1: DECLINED



“呼叫……听他的话”和“是为了什么结果”的搭配确实生硬，但本题还有无法仅靠措辞解决的内容问题：经文表达的是“愿神也听你们的话”这一祝愿，并未确立它是约坦呼吁众首领听话的目的或结果。若改问约坦表达了什么祝愿，会改变原题所考查的目的关系；若保留该关系，固定答案D仍缺乏经文支持，且E仍可成立。因此，在不能更改考查关系、答案或经文窗口的限制下，无法作出合规修订。

## hard:t1_judg9:f36a:open

Original: 迦勒第一次说有人来时，西布说他看见的其实是什么？


### Attempt 1: ACCEPTED

迦勒第一次说有人来时，西布说迦勒看见的其实是什么？

将“他”改为“迦勒”，明确看见者，避免误将代词理解为西布；保留“第一次”的场次限定和西布作为解释者的角色。

Pass 1:
- Review: KEEP
- same_target: pass — 修订将“他”明确为“迦勒”，仍询问迦勒第一次说有人来时，西布称迦勒实际看见了什么；经文所指均为山上的影子。
- same_language: pass — 原问题与修订问题均为中文，仅将代词“他”替换为人名“迦勒”。
- naturalness: 0/3 — “迦勒第一次说有人来时”与“西布说迦勒看见的其实是什么？”衔接自然；“看见的”是常用的“的”字结构，“其实是什么”也符合日常询问某人如何解释所见事物的表达，无需修补措辞。
- processing: 1/3 — 读者需要把“第一次”对应到首次报告，并区分“迦勒”所见与“西布”对此所作的解释。“西布说迦勒看见的其实是什么”虽包含一层话语嵌入，但两个人名明确标示角色，负担普通且可管理；这些操作服务于题目所问的解释关系，没有明显可避免的额外负担。
- context_economy: 0/3 — 题目没有额外铺陈。“第一次说有人来时”用于限定所问的是哪一次报告，“西布说”用于限定回答谁的解释，均为有用的信息。

Pass 2:
- Review: KEEP
- same_target: pass — 修订仅将“他看见的”明确为“迦勒看见的”；两题均询问迦勒第一次报告有人来时，西布说迦勒实际看见了什么，答案均为山上的影子，而非人。
- same_language: pass — 原题与修订题均为中文，仅用中文人名“迦勒”替换代词“他”。
- naturalness: 0/3 — “迦勒第一次说有人来时”自然地交代时间范围，“西布说迦勒看见的其实是什么？”是通顺的间接转述问句。“迦勒看见的”指所见之物，属于常用表达，无需修补句意；未发现额外的措辞问题。
- processing: 1/3 — 读者需用“第一次”选定前一次报告，并在“西布说迦勒看见的其实是什么”中区分回应者西布与看见事物的迦勒。姓名明确标示了角色，“其实”也提示要辨认西布所解释的对象。这些操作直接服务于报告与回应的关系，属于普通、可管理的理解需求，没有明显可避免的嵌套或指称负担。
- context_economy: 0/3 — 题干中的“迦勒第一次说有人来时”用于区分两次报告，“西布说”用于指定所问的回应，均有明确作用；没有额外铺垫或无关背景。

## hard:t1_judg9:f36a:mcq

Original: 迦勒第一次说有人来时，西布说他看见的其实是什么？

- A. 伪装的士兵。
- B. 山上的影子，不是人。
- C. 从山上下来的人。
- D. 树林里的野兽。
- E. 根据这段文字无法判断

### Attempt 1: ACCEPTED

迦勒第一次说有人来时，西布说迦勒看见的其实是什么？

将指代不清的“他”改为“迦勒”，明确西布解释的是迦勒所见的对象，避免读者误将所见者理解为西布。保留“第一次”的时间定位及两人说法之间的关系，选项不变。
- A. 伪装的士兵。
- B. 山上的影子，不是人。
- C. 从山上下来的人。
- D. 树林里的野兽。
- E. 根据这段文字无法判断

Pass 1:
- Review: KEEP
- same_target: pass — 修订仅将“他看见的”明确为“迦勒看见的”。原文中西布对迦勒说“山上的影子在你眼中好像人”，因此指代与原题及答案一致；首次说有人来的时间限定和所问内容均未改变。
- same_language: pass — 修订后的问题和所有选项仍为中文，与原字段语言一致。
- Option A meaning: pass — 选项保持“伪装的士兵。”，含义未变。
- Option B meaning: pass — 选项保持“山上的影子，不是人。”，对象和否定内容均未变。
- Option C meaning: pass — 选项保持“从山上下来的人。”，含义未变。
- Option D meaning: pass — 选项保持“树林里的野兽。”，含义未变。
- Option E meaning: pass — 选项保持“根据这段文字无法判断”，无法判断的范围和含义未变。
- naturalness: 0/3 — “迦勒第一次说有人来时”与“西布说迦勒看见的其实是什么”衔接自然；“看见的”是常用的“的”字结构，“其实”自然地引出对先前判断的解释。选项“伪装的士兵”“树林里的野兽”等措辞直接，“根据这段文字无法判断”也是常见表达，无需修补语意或语法。
- processing: 1/3 — 读者需要用“第一次”定位发言，再区分“迦勒”报告所见与“西布”作出解释这两个角色。“西布说迦勒看见的其实是什么”虽包含言说内容和所见对象两层关系，但结构短，重复姓名也避免了代词指向不清。选项均为简短表述，“山上的影子，不是人”中的否定关系明确；整体只有目标本身需要的、可管理的理解需求。
- context_economy: 0/3 — 题干没有额外铺垫。“第一次说有人来时”用于限定所问的发言，“西布说”用于限定解释者，均有明确作用；选项也没有附加冗长说明。

Pass 2:
- Review: KEEP
- same_target: pass — 修订仅将“他看见的”明确为“迦勒看见的”，与原题、原答案和经文中“在你眼中”的指向一致；仍询问迦勒第一次说有人来时，西布称他实际看见的是什么。
- same_language: pass — 修订后的问题和所有选项均保持中文，与原对应字段一致。
- Option A meaning: pass — 选项未改，仍指伪装的士兵。
- Option B meaning: pass — 选项未改，仍指山上的影子，并否认是人。
- Option C meaning: pass — 选项未改，仍指从山上下来的人。
- Option D meaning: pass — 选项未改，仍指树林里的野兽。
- Option E meaning: pass — 选项未改，仍表示根据这段文字无法判断。
- naturalness: 0/3 — “迦勒第一次说有人来时”与“西布说迦勒看见的其实是什么？”衔接自然；“看见的”是常见的名词性表达，“其实是什么”也符合日常问法。选项如“伪装的士兵”“山上的影子，不是人”表达直接，无须在措辞上作心理修补。
- processing: 1/3 — 读者需要用“第一次”定位迦勒的初次报告，并区分“迦勒看见”与“西布说”所标示的观察者和解释者。这些操作直接服务于理解两人的不同判断，属于普通、可管理的负担。选项均为简短表达，“山上的影子，不是人”中的对比也不造成额外的复杂比较。
- context_economy: 0/3 — 没有额外引言或无关背景。“第一次说有人来时”用于限定所问的报告，“西布说”用于限定判断来源，均有明确作用，不属于多余铺垫。
