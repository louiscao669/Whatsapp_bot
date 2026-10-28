# Gold72 and Hard66: completed QA review

These are questions flagged for rewriting. No replacement questions were generated, and no canonical questions were changed or removed.

Gold: 71 English questions, each in open and multiple-choice form (142 forms). Hard: 65 active Chinese questions, 64 open and 65 multiple-choice forms (129 forms). Two excluded Hard forms and one inactive open form were not judged.

Model: gpt-6.1-sol; two independent repeat passes; three stages per pass: content validity, structural inspection, then wording burden. Actual campaign windows and hash-verified clean passages were used. Model screening is not measured human difficulty, and English Gold versus Chinese Hard is not a controlled quality comparison.

A wording score of 2 or 3 in naturalness, processing, or context economy triggers a rewrite flag. A structural concern without a failed wording dimension goes to review. Content failures are held separately. A rewrite flag on both passes is reported even when content problems take priority in the overall decision.

Technical response-validation fixes accepted verbatim joined option quotations and corrected inferred-target provenance labels from the input. Prompts, thresholds, and substantive judgments were not edited. Invalid responses were preserved and retried where needed; see [execution notes](execution_notes.json). Content holds caused by short passage windows need contextual adjudication.

## Counts by form

| Set and form | Reviewed | Rewrite both passes | Rewrite one pass only | No rewrite flag |
|---|---:|---:|---:|---:|
| Gold open | 71 | 6 | 3 | 62 |
| Gold mcq | 71 | 5 | 4 | 62 |
| Hard open | 64 | 11 | 2 | 51 |
| Hard mcq | 65 | 13 | 4 | 48 |

‘No rewrite flag’ does not imply acceptance: content or unresolved structure may still require review.

| Set | KEEP both passes | Stable REWRITE decision | Stable content HOLD | REVIEW / disagreement |
|---|---:|---:|---:|---:|
| Gold | 87 | 5 | 32 | 18 |
| Hard | 81 | 20 | 13 | 15 |

## Wording flagged for rewriting on both passes

### gold:t1_1kgs13:o8ae:open

What becomes sin to Jeroboam's family?

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “What becomes sin to Jeroboam's family?” uses the markedly unnatural combination “becomes sin to.” Readers must mentally repair how the action is related to the family's sin.
  - processing: “Becomes sin to” leaves readers deciding whether an action becomes sinful over time or is counted as sin for the family. Resolving that unintended relational uncertainty adds avoidable work beyond identifying the action.
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “What becomes sin to Jeroboam's family?” is markedly unnatural English. In particular, “becomes sin to” does not idiomatically express an action counting as a family’s sin and requires mental repair.
  - processing: Readers must reconstruct the relationship expressed by “becomes sin to”: whether something changes into sin, is regarded as sin by the family, or constitutes the family’s sin. Resolving that avoidable wording problem adds substantial interpretation beyond identifying the relevant action.

### gold:t1_1kgs13:o8ae:mcq

What becomes sin to Jeroboam's family?

- A. Building a new altar.
- B. Worshiping false gods.
- C. Consecrating anyone as priests.
- D. Ignoring the prophet's warning.
- E. I can't tell from this passage

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “What becomes sin to Jeroboam's family?” is markedly unidiomatic: “becomes sin to” requires repair to understand the relationship between an action, sin, and the family. “Consecrating anyone as priests” also awkwardly combines singular “anyone” with plural “priests.”
  - processing: Readers must reinterpret “becomes sin to” to decide whether the question concerns an action counted as the family's sin or something becoming sinful over time. This avoidable relational uncertainty is separate from understanding the appointment of priests.
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “What becomes sin to Jeroboam's family?” is markedly unnatural: “becomes sin to” does not clearly express ordinary attribution of wrongdoing. “Consecrating anyone as priests” also awkwardly pairs singular “anyone” with plural “priests.”
  - processing: Readers must mentally repair “becomes sin to” into a familiar relationship between an action and a family's wrongdoing, then reconcile “anyone as priests” as appointment of individuals to a role. These wording repairs are avoidable and are not required by the intended appointment relationship.

### gold:t1_2chr26:tglh:open

How did Uzziah follow his father's example with Yahweh?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: REWRITE / REWRITE. Content: HOLD / HOLD.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: "Follow his father's example with Yahweh" is an unnatural combination. "With Yahweh" does not clearly express the relationship between the example and Uzziah's religious conduct, so readers must mentally repair that connection.
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: In “follow his father's example with Yahweh,” “with Yahweh” is an awkward way to specify conduct toward God and requires mental repair.

Content issues:
- Pass 1, answer_support (fail): Doing right is explicitly compared with his father's conduct. Although Uzziah also sought God, the passage does not say his father sought God, so that component is not supported as a way he followed his father's example.
- Pass 2, answer_support (fail): Doing right answers the comparison with his father. Although 26:5 says Uzziah sought God, it does not say that his father did so or that this followed his father's example.

### gold:t1_2chr26:tglh:mcq

How does Uzziah follow his father's example with Yahweh?

- A. Worshipped other gods
- B. Ignored God's laws
- C. Built idols
- D. Did right and sought God
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: REWRITE / REWRITE. Content: HOLD / HOLD.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “Follow his father's example with Yahweh” is an unnatural combination. “With Yahweh” does not idiomatically express the religious conduct intended here and requires the reader to repair the relationship mentally.
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “Follow his father's example with Yahweh” is markedly awkward. “With Yahweh” does not naturally express the intended domain of conduct toward God and requires readers to repair the relationship mentally.
  - processing: In “How does Uzziah follow his father's example with Yahweh?”, readers must decide what “with Yahweh” modifies and reinterpret it as conduct toward God. This attachment repair is avoidable; it is not inherent in understanding the father–son comparison or the two actions in option D.

Content issues:
- Pass 1, answer_support (fail): Doing right is explicitly linked to his father's example. Seeking God is stated about Uzziah in verse 26:5, but the excerpt does not say his father sought God or that Uzziah's seeking followed his father's example.
- Pass 1, mcq_validity (fail): D adds seeking God to the father–son comparison without support for that relationship. A, B, and C contradict the positive conduct described, while E is inappropriate because verse 26:4 does establish how he followed his father's example.
- Pass 2, answer_support (fail): The passage attributes both doing right and seeking God to Uzziah, but only doing right is explicitly compared with his father. It does not establish that seeking God followed his father's example.
- Pass 2, mcq_validity (fail): D overextends the father–son comparison by adding seeking God. A, B, and C contradict the favorable conduct described. E is also unsuitable because verse 4 does explain the comparison; no option precisely gives the supported answer.

### gold:t1_2kgs11:otua:open

What did non-serving groups do on the Sabbath?

Overall: **REVIEW** (REWRITE, HOLD_CONTENT). Wording: REWRITE / REWRITE. Content: PASS / HOLD.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “Non-serving groups” is an unnatural description of divisions going off duty and can instead suggest groups that do not serve.
  - processing: Readers must repair “non-serving” into a duty-transition meaning before identifying the groups. This avoidable reinterpretation goes beyond the necessary distinction between those coming on duty and those going off duty.
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “Non-serving groups” is an unnatural personnel label here. It suggests groups performing no service, rather than divisions scheduled to go off duty, and requires mental repair.
  - processing: To interpret “What did non-serving groups do,” the reader must map “non-serving” to scheduled off-duty status while suppressing its more immediate meaning of not serving at all. This avoidable reinterpretation is not needed to ask about their assigned guarding duty.

Content issues:
- Pass 2, question_support (fail): The passage gives commands about what divisions going off duty are to do; it does not report what 'non-serving groups' actually did.
- Pass 2, answer_support (fail): Guarding the house of the LORD is explicitly assigned, but the displayed passage does not establish its performance as the question asks.
- Pass 2, context_sufficiency (fail): No account of the divisions carrying out the command is included, so the actual-action framing lacks necessary context.

### gold:t1_2kgs11:otua:mcq

What did non-serving groups do on the Sabbath?

- A. Guard the house of Yahweh
- B. Visit the market
- C. Attend a feast
- D. Rest at home
- E. I can't tell from this passage

Overall: **REVIEW** (REWRITE, HOLD_CONTENT). Wording: REWRITE / REWRITE. Content: PASS / HOLD.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “Non-serving groups” is an unnatural label for divisions going off duty. It sounds like groups that do not serve at all, requiring readers to repair the intended sense.
  - processing: Readers must reinterpret “non-serving” as going off duty rather than not serving, then identify the relevant groups. That extra interpretation is avoidable; distinguishing the duty groups is necessary, but this misleading label is not.
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “Non-serving groups” is an unnatural, underspecified label for divisions going off duty. Readers must mentally repair what kind of service “non-serving” excludes.
  - processing: “Non-serving groups” requires readers to infer an unstated duty category and reconcile being “non-serving” with performing an assignment such as “Guard the house of Yahweh.” This avoidable status-decoding step goes beyond identifying the assignment.

Content issues:
- Pass 2, question_support (fail): The passage states what the divisions were commanded to do, not what they actually did; the question presents performance of the duty as an established event.
- Pass 2, answer_support (fail): Guarding the house of the LORD is explicitly their assignment, but the passage does not establish that they carried it out, as the question asks. 'Yahweh' versus 'LORD' is not the problem.
- Pass 2, mcq_validity (fail): A is supported as an instruction, not an accomplished action. B, C, and D have no support. For the literal question about what they did, E is defensible, so the supplied key A is not uniquely justified.

### gold:t1_2kgs6_7:pb1x:open

What did the captain say to Elisha's prophecy?

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “Say to Elisha's prophecy” is an unnatural complement for “say”: a prophecy is treated as though it were the addressee. Readers must mentally reinterpret it as responding to the prophecy.
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “What did the captain say to Elisha's prophecy?” uses the unnatural combination “say to” with “prophecy.” Readers must mentally supply the relation “in response to,” rather than read the prophecy as an addressee.

### gold:t1_2kgs6_7:pb1x:mcq

What does the captain say to Elisha's prophecy?

- A. It will happen soon
- B. Impossible even if Yahweh helped
- C. We must prepare
- D. The people will rejoice
- E. I can't tell from this passage

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: 'What does the captain say to Elisha's prophecy?' awkwardly treats the prophecy as the recipient of 'say.' Readers must mentally repair this to mean what he says in response to it. 'Impossible even if Yahweh helped' is also noticeably compressed, though understandable as an option.
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “What does the captain say to Elisha's prophecy?” awkwardly makes “Elisha's prophecy” the complement of “say to,” a construction ordinarily used for an addressee. The reader must mentally recast it as a response to the prophecy.

### gold:t1_acts20:jxkk#2:open

What happens after Paul stretches on the young man?

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / REVIEW.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “Paul stretches on the young man” is markedly unnatural for the physical intervention described. “Stretches” without an appropriate complement or particle suggests an exercise or reaching motion and requires mental repair.
  - processing: Before locating the later event, the reader must infer what physical action “stretches on” denotes and reconcile it with “threw himself on ... and embraced him.” This avoidable action-decoding burden is separate from the necessary task of tracking the young man's condition.
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “Paul stretches on the young man” is markedly unnatural English for the described bodily action. “Stretches” without a reflexive object or an appropriate particle does not clearly express the intended posture or movement.
  - processing: Before answering “What happens after Paul stretches on the young man?”, readers must infer what “stretches on” means and mentally repair the action description using the passage. This lexical repair is avoidable; tracking the two participants and their event sequence is not itself the problem.

Content issues:
- Pass 2, answer_support (uncertain): The young man is first described as 'picked up dead,' supporting a return-to-life reading, but Paul's 'He is still alive' leaves unresolved whether a revival occurred or the earlier assessment was mistaken.
- Pass 2, answer_uniqueness (uncertain): The outcome that the young man is alive is clear, but the passage does not unambiguously distinguish revival from continued life.

### gold:t1_acts23:xj40:open

How did captain respond to the plan?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: REWRITE / REWRITE. Content: HOLD / HOLD.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “How did captain respond” omits the article normally required before the singular common noun “captain.” Readers must mentally supply it.
- Pass 2: naturalness 2/3, processing 0/3, context_economy 0/3.
  - naturalness: “How did captain respond” omits the determiner normally required before the singular common noun “captain.” Readers must mentally supply it; this is not ordinary direct-question phrasing.

Content issues:
- Pass 1, context_sufficiency (fail): The window begins with 'Then he' and supplies neither the identity of that speaker nor the antecedent plan.
- Pass 1, question_support (uncertain): Protective transport orders are explicit, but the passage does not identify a captain by title or describe a plan to which these orders respond.
- Pass 2, question_support (fail): The passage supplies military orders but neither identifies a captain nor mentions the plan to which he supposedly responded.
- Pass 2, context_sufficiency (fail): The opening 'he' has no supplied antecedent, and no plan is described.
- Pass 2, answer_support (uncertain): The orders provide for Paul's safe transport, supporting protective action, but the passage cannot establish that this was a response to the unspecified plan.
- Pass 2, answer_uniqueness (uncertain): Protective orders are visible, but the absent plan prevents establishing which action constitutes the requested response.

### gold:t1_acts23:xj40:mcq

How did captain respond to the plan?

- A. Dismissed the young man without acting.
- B. Ordered Paul returned to the council.
- C. Released Paul without an escort.
- D. Ordered guard to protect Paul.
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: REWRITE / REWRITE. Content: HOLD / HOLD.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “How did captain respond to the plan?” omits the determiner normally required before “captain.” “Ordered guard to protect Paul” likewise leaves the count noun “guard” without a determiner or plural marking. Both require mental repair.
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “How did captain respond” lacks a determiner before “captain.” Option D, “Ordered guard to protect Paul,” also leaves “guard” awkwardly bare, requiring readers to repair the intended noun phrase.

Content issues:
- Pass 1, question_support (fail): The excerpt contains orders by an unnamed “he,” but neither identifies a captain nor mentions a plan to which he responded.
- Pass 1, answer_support (fail): Protective transport orders are explicit, but their attribution to the captain as a response to the referenced plan is not established in this window.
- Pass 1, context_sufficiency (fail): The antecedent of “he,” the captain's identity, and the referenced plan are absent.
- Pass 1, mcq_validity (fail): A, B, and C lack support. D matches the orders but cannot be linked to the unspecified captain and plan, so E is defensible and the supplied key D is not established.
- Pass 2, question_support (fail): No plan or identified captain appears in the supplied passage, so the asserted response relationship is unsupported.
- Pass 2, context_sufficiency (fail): The passage begins with an unidentified 'he' and supplies no antecedent for 'the plan.'
- Pass 2, mcq_validity (fail): A, B, and C are unsupported. D describes the visible orders but cannot be established as a response to the absent plan; E is defensible, so D is not a uniquely supported key.
- Pass 2, answer_support (uncertain): Protective transport orders support D's action, but their relationship to the unspecified plan cannot be established.
- Pass 2, answer_uniqueness (uncertain): The protective action is described, but missing information prevents uniquely identifying a response to the plan.

### hard:t1_1kgs13:ec63:open

带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 1/3, processing 2/3, context_economy 0/3.
  - processing: 开头“带他回来的先知”先用尚未明示所指的“他”引入另一名男性，随后又出现“谁的尸首”和“他列祖”。读者须在宣告者与待识别者之间连续分配代词，并将末尾“他”重新绑定到“谁”。识别宣告对象是必要的，但这种先行词不明、连续代词交替造成了可避免的负担。
- Pass 2: naturalness 1/3, processing 2/3, context_economy 0/3.
  - processing: 读者先要解析“带他回来的先知”中未明示对象的“他”，再区分宣告者与“谁”，并将“他列祖”的“他”绑定到所问者，而不是先知。问句在短距离内混用代词、疑问指称和领属关系，增加了并非识别宣告对象所必需的参照维护。

### hard:t1_1kgs13:ec63:mcq

带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？

- A. 耶罗波安
- B. 带他回来的先知
- C. 他的列祖
- D. 从犹大来的神人
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 1/3, processing 2/3, context_economy 0/3.
  - processing: 读者先要为“带他回来”的“他”找对象，再越过宣告者，确定“谁”是尸首所属者，最后把“他列祖”的“他”绑定到这个待识别人物。两个同形代词承担不同局部关系，增加了可避免的回指保持负担；区分宣告者与受宣告者本身则是必要的。
- Pass 2: naturalness 1/3, processing 2/3, context_economy 0/3.
  - processing: 在“带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？”中，读者先要解析修饰语里的带回者与被带回者，再转到“谁”，并确定末尾“他”的归属。对两个人物连续使用未直接命名的关系和代词，增加了可避免的回指保持与角色切换负担。

### hard:t1_1kgs13:2f00:open

带他回来的先知先把神人的尸首带到哪里？

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: “带他回来的”先引入未明示身份的“他”及一次带回事件，随后“把神人的尸首带到哪里”又引入相似搬运事件。读者需向后落实指代并保持两次动作的区别；这超出了识别尸首目的地所需的加工。
- Pass 2: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: “带他回来的”先引入一次带人返回的事件，主句又问“把神人的尸首带到哪里”。读者需区分两次“带”的事件，并在先出现“他”、后出现“神人”的次序下确认同一人物，造成可避免的事件和指代切换。

### hard:t1_1kgs13:2f00:mcq

带他回来的先知先把神人的尸首带到哪里？

- A. 到自己的坟墓。
- B. 回到自己的城里。
- C. 到王宫。
- D. 到坛那里。
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: 句首先出现“带他回来的”，读者须暂存尚未明示的“他”，读到“神人的尸首”后再对应人物，同时区分先前带人回来与后来搬运尸首两次相似动作。这一身份修饰额外引入事件，对询问尸首目的地造成可避免的负担；选项“自己的城里”本身回指清楚。
- Pass 2: naturalness 1/3, processing 2/3, context_economy 1/3.
  - processing: 读者要先处理“带他回来的”所指的较早事件，确定“他”是神人、被修饰的“先知”是另一人，再转入搬运尸首的事件。两个“带”的事件相邻，增加了可避免的事件分离和指称暂存；这不同于必要的城与坟墓的先后比较。

### hard:t1_2chr26:9aab:open

犹大全体百姓立乌西雅，是为了什么？

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “犹大全体百姓立乌西雅，是为了什么？”中的“立乌西雅”缺少现代汉语通常期待的身份补足，独立使用显得未完成，需要读者从上下文补成册立为王的意思。
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “犹大全体百姓立乌西雅，是为了什么？”把“立乌西雅”单独作为已经完整说明的行动，现代汉语中显得宾语后的身份或职位没有说完。普通读者可能需为“立”补足未明说的任立含义，才能顺畅理解后面的目的问句。

### hard:t1_2chr26:1cab:mcq

神帮助乌西雅攻打哪些人？

- A. 亚扪人、住在姑珥巴力的阿拉伯人和米乌尼人
- B. 非利士人、住在亚实突的阿拉伯人和亚扪人
- C. 摩押人、住在埃及边界的亚玛力人和亚扪人
- D. 非利士人、住在姑珥巴力的阿拉伯人和米乌尼人
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: A至D反复列出三个群体，差异分散在首项、居住地点和末项。例如A与D仅在“亚扪人／非利士人”上不同，B又改变“住在亚实突的”和末项。读者必须保持名单位置并多次逐项核对；这种重复而交错的比较超过辨认三个群体本身所需的负荷。
- Pass 2: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: A、B、D反复使用三个人群的长列表，读者既要比较“亚扪人／非利士人”，又要检查列表内部的“姑珥巴力／亚实突”。族名和嵌入地点同时变化，迫使读者多次回扫并暂存比较结果；这种双层近似选项比较增加了可避免的负担。

### hard:t1_2chr26:1fc4:open

谁爱好土地，所以设立了农夫和葡萄园工人？

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “爱好土地”搭配生硬，土地不像通常所说的兴趣活动；“设立了农夫和葡萄园工人”又把通常用于机构、职位的“设立”接到具体劳动者上，需读者自行修复为人员安排的意思。
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “爱好土地”较生硬，尤其“设立了农夫和葡萄园工人”将通常用于机构、职位等的“设立”直接搭配人员，需读者在心中调整为安排或设置相关人员的意思。

### hard:t1_2chr26:1fc4:mcq

谁爱好土地，所以设立了农夫和葡萄园工人？

- A. 葡萄园工人
- B. 约坦
- C. 乌西雅
- D. 田野中的农夫
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “爱好土地”搭配生硬，“设立了农夫和葡萄园工人”又把通常用于机构、职位等的“设立”直接用于人员；读者需要调整对这些搭配的理解。
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “爱好土地”搭配生硬，通常“爱好”指向活动或领域；“设立了农夫和葡萄园工人”又把常用于机构、职位等的“设立”直接用于人员。两处都需要读者按语境修复理解。

### hard:t1_2chr26:723e:open

这三十万七千五百训练有素的军队由谁统领？

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “这三十万七千五百训练有素的军队”把裸数词直接接到“训练有素的军队”前，缺少人数单位或表示成员关系的成分，容易读成在数三十多万支军队，需自行修补词语关系。
  - processing: 读者必须把“三十万七千五百”从表面的“军队”数量重新解释为军队中士兵的人数，才能确定受统领者。识别人数对应的队伍是必要的，但这种数量与集体名词的错接造成了可避免的解析负担。
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “这三十万七千五百训练有素的军队”中的数词直接连接“训练有素的军队”，缺少与人数相配的量词和人员名词，容易先被读成在数若干支军队，需要读者修复名词组。
  - processing: 读者必须先把“三十万七千五百”重新理解为军队中的人数，而不是军队的数量，才能稳定解析“由谁统领”。这一数字与中心名词的连接问题是可避免的，并非识别统领者所必需。

### hard:t1_2chr26:723e:mcq

这三十万七千五百训练有素的军队由谁统领？

- A. 哈拿尼雅
- B. 耶列和玛西亚
- C. 乌西雅
- D. 那二千六百个家族首领
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “这三十万七千五百训练有素的军队”把人数直接接在“军队”前，缺少合适的计量连接，容易被初读为军队的数量；读者须自行修复为士兵人数。
  - processing: 读者必须先修复“这三十万七千五百训练有素的军队”的数量修饰关系，再处理“由谁统领”。识别统领者本身是必要任务，但判断数字究竟计量士兵还是军队是可避免的额外负担。
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “这三十万七千五百训练有素的军队”把人数直接接到“军队”上，缺少合适的人员量词或中心语。读者须自行补出按士兵人数计数的意思，属于明显需要修补的名词结构。
  - processing: 读者读完“三十万七千五百”后，要跨过“训练有素的”才遇到“军队”，随后还须将表面上的军队数量重解为士兵人数。这是数量与中心语搭配造成的可避免负担，不是识别统领职责本身所需。

### hard:t1_2kgs11:f49c:open

耶何耶大立的第一个约，是在哪些之间立的？

Overall: **REVIEW** (HOLD_CONTENT, REWRITE). Wording: REWRITE / REWRITE. Content: HOLD / PASS.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “是在哪些之间立的”没有明确说出“哪些”所指的类别，需读者自行补成参与方的概念，措辞明显不完整。“立的第一个约……立的”也稍显重复。
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “是在哪些之间立的”中的“哪些”缺少明确的中心词，直接放在“之间”前不自然；读者需要自行补出所问的是哪些立约方。
  - processing: 读者读到“哪些之间”时，需要先修复疑问短语，再判断应列举哪些参与方。这是表达缺口造成的额外操作，并非区分“第一个约”本身所必需。

Content issues:
- Pass 1, answer_support (fail): The displayed text says Jehoiada made a covenant with the LORD, the king, and the people. The expected answer omits Jehoiada, although the question asks without restriction between whom the covenant was made.

### hard:t1_2kgs11:f49c:mcq

耶何耶大立的第一个约，是在哪些之间立的？

- A. 耶和华、王和百姓
- B. 王和百夫长
- C. 耶和华和守卫
- D. 王和百姓
- E. 根据这段文字无法判断

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: REWRITE / REWRITE. Content: HOLD / HOLD.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “是在哪些之间立的”中的“哪些”缺少明确的类别中心语，表达明显不完整；读者须自行补出所问的是立约各方。“立的第一个约……立的”也略显拖沓。
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “是在哪些之间立的”中，“哪些”没有明确的中心成分，单独放在“之间”前明显生硬。读者需要借助选项补足所问的是立约各方，才能修复这一表达。

Content issues:
- Pass 1, answer_support (fail): The displayed wording says 耶何耶大与耶和华、王和百姓立约, explicitly including Jehoiada as contracting with the other three. The expected list omits Jehoiada from an unrestricted question about the parties.
- Pass 1, mcq_validity (fail): A omits Jehoiada from the parties explicitly named by this rendering. B and C introduce unsupported parties; D belongs to the second covenant and is incomplete for the first. E is false because the passage provides the information. No option gives the full displayed list.
- Pass 2, answer_support (fail): 所给文本写的是“耶何耶大与耶和华、王和百姓立约”，把耶何耶大也表述为立约的一方。问题问约是在“哪些之间”立的，预期答案只列后三方，遗漏了文本中的耶何耶大；不能据外部知识把他改作仅仅居间立约的人。
- Pass 2, mcq_validity (fail): A是给定键，但遗漏文本列为立约一方的耶何耶大；B的百夫长和C的守卫不属于第一个约，D对应后一个约且也遗漏耶何耶大，E亦不合适，因为经文明示参与者。没有完整符合问题的选项。

### hard:t1_acts19:7628:open

被那附着邪灵的人制服以后，谁受伤逃出了那房子？

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “那附着邪灵的人”搭配明显不自然：“人”容易被读成“附着”的施事，而所指是被邪灵附着的人。读者需要借经文修复这一修饰关系。
  - processing: 在“被那附着邪灵的人制服以后”中，读者尚未读到“制服”就要解析不自然的“附着邪灵的人”，再把整个人物短语作为制服者，最后将省略的受事接到“谁”。其中修复附着关系的负担可避免，并非识别逃走者所必需。
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “那附着邪灵的人”容易先被理解为该人实施“附着邪灵”的动作，需要读者修补人与邪灵的关系。即使这一说法沿用经文，问句自身的名词修饰仍明显别扭。
  - processing: 在读到“谁”之前，读者须先解析“那附着邪灵的人”，再处理“被……制服”，最后将省略的被制服者与后面的受伤逃出者合并。人物修饰的不自然又增加一次关系修补，这些前置解码并非识别逃出者所必需的复杂性。

### hard:t1_acts19:7628:mcq

被那附着邪灵的人制服以后，谁受伤逃出了那房子？

- A. 那附着邪灵的人
- B. 保罗
- C. 以弗所的希腊人
- D. 士基瓦的七个儿子
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: 问句和选项A中的“那附着邪灵的人”容易先被理解为“人”是“附着”的施事，不能顺畅表达人与邪灵的被附着关系，需要读者借助语境修复。
  - processing: 在“被那附着邪灵的人制服以后，谁……”中，读者先要解析内部关系不顺的“附着邪灵的人”，再将整个人物短语作为“制服”的施事，暂存尚未出现的受事，直到“谁”才将其与受伤、逃出者合并。人物描述和受事的延后共同造成可避免的角色整合负担；目标本身并不要求这种表达次序。
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “那附着邪灵的人”中的“附着邪灵”不自然地挂接到“人”，容易先被理解为人主动附着邪灵，而非邪灵附着于人。该表述在前置分句和选项A中重复，需要读者修正关系。
  - processing: 读者先要修复“那附着邪灵的人”内部的附着关系，再将这个人识别为“制服”的施事，并把省略的被制服者接到主句“谁”。主要可避免负担来自不自然的名词修饰，而非被动句本身。

### hard:t1_judg17_18:725d:open

他们请谁为他们求问这趟行程？

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “求问这趟行程”搭配明显生硬：“行程”被直接写成“求问”的对象，读者需自行理解为求问有关行程的情况。“他们请谁为他们”本身自然。
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “求问这趟行程”搭配明显生硬：“行程”被直接接作“求问”的对象，读者需自行补出向谁求问以及求问行程的什么情况。

### hard:t1_judg17_18:725d:mcq

他们请谁为他们求问这趟行程？

- A. 神
- B. 米迦的母亲
- C. 米迦
- D. 祭司
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “求问这趟行程”搭配明显生硬。“求问”通常涉及向某个对象询问事情，这里直接接“这趟行程”，需要读者补出“就行程向神求问”的关系。
  - processing: “他们请谁为他们”本身可解析，但接上“求问这趟行程”后，读者须把表面的宾语“行程”重新理解为求问的话题，并补出求问对象。该补足不是辨认受请求者所必需的负担。
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “求问这趟行程”的动宾搭配不自然：“行程”被直接放在“求问”后，读者需将其修复理解为就行程进行求问，而不是把行程当作被询问者。

### hard:t1_judg17_18:c2d9:mcq

谁进去拿走了雕像、以弗得、家用神像和熔铸的偶像？

- A. 六百带兵器的但人
- B. 那少年利未人
- C. 那五个窥探地的人
- D. 米迦和他的家人
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: 题干“谁进去拿走了……”自然，但选项“那五个窥探地的人”中的“窥探地”不符合普通现代中文中清晰、自然的搭配。“地”紧接在“窥探”后又接“的”，需要读者修补为被窥探的土地。
  - processing: 读者比较选项时，需要判断“窥探地的人”中的“地”是土地名词而非结构助词，并重新划分“窥探地／的人”。这种词性和修饰边界的消歧可避免，并非识别行动群体所必需；四项物品的并列本身则结构清楚。
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: 问句中的物品并列自然，但选项“那五个窥探地的人”中“窥探地”的说法不够自然。“地”需被理解为土地或地域，而不是通常紧接动词出现时容易联想到的结构助词，读者可能需要回读修补。

### hard:t1_judg17_18:3162:open

那些神像最先发生了什么事？

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “那些神像最先发生了什么事”把“神像”直接接作“发生了什么事”的主体，搭配不够自然。读者需把它重新理解为询问神像遭遇了什么，而不是神像发生了某事。
  - processing: 除了按“最先”辨认事件顺序，还须修复“那些神像……发生了什么事”的主语与事件关系，转而寻找作用于神像的行动。这一步不是时间顺序目标所必需的。
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “那些神像最先发生了什么事？”把“神像”直接放在“发生”的主语位置，搭配明显生硬。读者需要把它转解为以神像为话题、询问其遭遇，而不是按表面主谓关系理解。

### hard:t1_judg17_18:3250:mcq

为什么没有人搭救来士的人？

- A. 因为那城远离西顿，也没有与人结盟。
- B. 因为他们夺了米迦的偶像和祭司
- C. 因为但人用刀杀灭他们
- D. 因为但人重建城邑，在那里居住
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: 题干最后的人物是“来士的人”，但选项B“因为他们夺了米迦的偶像和祭司”中的“他们”须另行接回经文中的但人。读者容易先沿用题干人物，再返回经文修正行为主体；这种未明示的群体切换是可避免的选项比较负担。
- Pass 2: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: 题干刚提到“来士的人”，选项B就使用“他们”，容易先被理解为来士居民。读者必须回查并改认其为进攻者，而选项C、D又直接使用“但人”；这种主语表达不一致造成可避免的指代修正负担。

### hard:t1_judg17_18:97e8:mcq

约拿单和他的子孙作但支派的祭司，直到什么时候？

- A. 直到被掳之日。
- B. 直到他们给城起名叫但。
- C. 直到但人为自己立偶像。
- D. 神的殿在示罗多少日子，就到多少日子。
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: 问句“约拿单和他的子孙作但支派的祭司，直到什么时候？”自然，但D“神的殿在示罗多少日子，就到多少日子”明显生硬。“多少日子”表示时长，“到”却引出终点，后半句缺少自然的承接，读者需自行修复其时间关系。
  - processing: D“神的殿在示罗多少日子，就到多少日子”要求读者补出任职持续关系，并把时长重新解释为终止界限，才能与“直到被掳之日”等选项比较。这种由不完整时间搭配引起的重构不是理解任职终点本身所必需的。
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: 题干“直到什么时候”自然，但选项D“神的殿在示罗多少日子，就到多少日子”搭配明显生硬：“到”通常需要时间界点，此处却接“多少日子”这一时长表达，需要读者自行修补。
  - processing: 比较选项D时，读者必须把两处“多少日子”配对，补出省略的任职事件，再把持续时长转换成“直到什么时候”所问的截止点。这些由选项表达方式引起的补足和转换是可避免的。

### hard:t1_judg9:6d68:open

约坦呼叫示剑的众首领听他的话，是为了什么结果？

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: REWRITE / REWRITE. Content: HOLD / HOLD.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “是为了什么结果”不是自然的目的或预期结果问法，“为了”与“什么结果”的组合需要读者自行整理其表达意图。“呼叫示剑的众首领听他的话”也略显生硬。
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “呼叫示剑的众首领听他的话”将“呼叫”用于要求别人听从的结构，搭配生硬；“是为了什么结果”也不如通常的目的或结果问法自然，读者需在心中调整表达。

Content issues:
- Pass 1, question_support (fail): 9:7 gives an appeal followed by a wish: '你们要听我的话，愿神也听你们的话.' It does not establish that obtaining God's attention was the purpose of Jotham's appeal, as '是为了什么结果' presupposes.
- Pass 1, answer_support (fail): God listening to them is explicitly wished for, but the expected answer's 'So that' turns that wish into an established purpose relation not supplied by the passage.
- Pass 2, question_support (fail): 9:7说“你们要听我的话，愿神也听你们的话”，明确表达吩咐与祝愿，但没有把神听他们的话陈述为呼吁的目的或结果；问题加入了“是为了”的关系。
- Pass 2, answer_support (fail): 经文支持约坦愿神听他们的话，却不足以支持预期答案中“So that”所断定的目的关系，因此不能直接回答问题要求的“为了什么结果”。

### hard:t1_judg9:6d68:mcq

约坦呼叫示剑的众首领听他的话，是为了什么结果？

- A. 为自己膏立一个王。
- B. 召集他们赴宴。
- C. 警告他们有危险。
- D. 使神也听他们的话。
- E. 根据这段文字无法判断

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: REWRITE / REWRITE. Content: HOLD / HOLD.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “呼叫示剑的众首领听他的话”把“呼叫”直接接在要求别人听话的结构前，搭配生硬；“是为了什么结果”也把目的问法和结果问法拼接在一起，需要读者自行整理表达。
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “呼叫示剑的众首领听他的话”搭配生硬，“是为了什么结果”又把目的问法和结果问法拼接在一起。读者需要自行理顺为询问这一呼吁想达到的结果。

Content issues:
- Pass 1, question_support (fail): 9:7 juxtaposes ‘你们要听我的话’ with the wish ‘愿神也听你们的话’. It does not state that securing God's hearing was the purpose or result of their listening.
- Pass 1, answer_support (fail): ‘使神也听他们的话’ converts the expressed wish into a purpose or causal outcome that the displayed wording does not establish.
- Pass 1, mcq_validity (fail): D is not established as a purpose or result. A belongs to the trees' story, and B and C are unstated. E is defensible because the requested purpose is not specified, so the supplied key D is not securely correct.
- Pass 2, question_support (fail): 9:7说“你们要听我的话，愿神也听你们的话”，表达要求和祝愿，并未把后者确立为呼叫他们听话的目的或结果。
- Pass 2, answer_support (fail): “使神也听他们的话”把“愿神也听”的祝愿改成了所要促成的结果；这一目的关系在所给文字中没有建立。
- Pass 2, mcq_validity (fail): D将祝愿转为目的，不能据此确立为正确答案；A、B、C也没有目的关系的依据，因此E比给定键D更有根据。

### hard:t1_judg9:f36a:open

迦勒第一次说有人来时，西布说他看见的其实是什么？

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: 在“西布说他看见的其实是什么”中，“他”紧跟西布，容易先被理解为西布；读者随后需回到前一分句或对话，把看见者改接为迦勒。区分报告者与解释者是必要的，但由这个代词引起的角色重判可以避免。
- Pass 2: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: 读到“西布说他看见的”时，容易先把紧随西布的“他”理解为西布；随后必须返回前一分句，将其改指迦勒，并恢复西布对迦勒所见之物的解释。这个可避免的参照竞争叠加在本就需要区分的两个人物观点之上。

### hard:t1_judg9:f36a:mcq

迦勒第一次说有人来时，西布说他看见的其实是什么？

- A. 伪装的士兵。
- B. 山上的影子，不是人。
- C. 从山上下来的人。
- D. 树林里的野兽。
- E. 根据这段文字无法判断

Overall: **REWRITE** (REWRITE, REWRITE). Wording: REWRITE / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “西布说他看见的其实是什么”中，“他”紧随“西布说”，容易先被理解为西布本人；读者随后需要把指称改接到迦勒，表述需要 mental repair。
  - processing: “迦勒第一次说有人来时”已经引入一名说话者，主句又转到“西布说他看见的”。读者既要保留两人的不同判断，又要越过最近的“西布”将“他”接回迦勒；后一消歧操作是可避免的额外负担。
- Pass 2: naturalness 1/3, processing 2/3, context_economy 0/3.
  - processing: 读到“西布说他看见的”时，读者容易先把“他”接到西布，再根据前文将其改接到迦勒。区分两人的说法是必要的，但这种由代词位置造成的初始误接和回查是可避免的。


## Wording flagged on only one pass: adjudicate before rewriting

### gold:t1_1kgs13:mjwk:open

Who came from Judah by Yahweh's word?

Overall: **REVIEW** (KEEP, REWRITE). Wording: PASS / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “Who came from Judah by Yahweh's word?” uses the nonconversational expression “by Yahweh's word,” which requires readers to recover the intended sense of divine direction.

### gold:t1_1kgs13:mjwk:mcq

Who comes from Judah by Yahweh's word?

- A. A prophet from Bethel
- B. King Jeroboam
- C. A priest of the high places
- D. A man of God
- E. I can't tell from this passage

Overall: **REVIEW** (KEEP, REWRITE). Wording: PASS / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “By Yahweh's word” in “Who comes from Judah by Yahweh's word?” is not ordinary contemporary phrasing for acting under divine direction and requires interpretation.

### gold:t1_1kgs13:w4ws:mcq

What does the old prophet do with the body?

- A. He leaves it by the road.
- B. He takes it to the king.
- C. He buries it in his grave.
- D. He burns it as a sacrifice.
- E. I can't tell from this passage

Overall: **REVIEW** (REWRITE, KEEP). Wording: REWRITE / PASS. Content: PASS / PASS.

- Pass 1: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: In “He buries it in his grave,” readers must assign “his” to the old prophet rather than to the dead man represented by “the body.” Both ownership readings are linguistically plausible, creating avoidable reference-resolution work at the point where the burial location is specified.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

### gold:t1_2kgs6_7:cc0k:open

Why did the king think Arameans left their camp?

Overall: **REVIEW** (HOLD_CONTENT, REWRITE). Wording: PASS / REWRITE. Content: HOLD / PASS.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 2/3, context_economy 0/3.
  - processing: “Why did the king think Arameans left their camp?” allows two readings: why the king believed they had left, or what purpose he attributed to their leaving. Readers must choose the intended scope of “why.” This avoidable ambiguity is separate from the necessary task of understanding the king’s viewpoint.

Content issues:
- Pass 1, answer_support (fail): An ambush of the city's inhabitants is supported, but the passage does not identify those inhabitants as Israelites. That identification requires information outside the supplied passage.

### gold:t1_2sam21:kjsg:mcq

How did Abishai rescue David when he was weary?

- A. He killed the huge man with six fingers
- B. He killed Ishbi Benob
- C. He killed Goliath's brother
- D. He killed Saph
- E. I can't tell from this passage

Overall: **REVIEW** (REVIEW, REWRITE). Wording: REVIEW / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 1/3.
- Pass 2: naturalness 0/3, processing 2/3, context_economy 1/3.
  - processing: In “Abishai rescue David when he was weary,” either named man is a grammatically plausible referent for “he.” Readers must infer David as the weary person, then switch “He” back to Abishai in every substantive option. This avoidable reference shift adds load beyond identifying the rescue action.

### gold:t1_acts19:xtb7:open

What did Ephesus magicians do with their books?

Overall: **REVIEW** (REWRITE, KEEP). Wording: REWRITE / PASS. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “What did Ephesus magicians do with their books?” uses the conspicuously awkward phrase “Ephesus magicians.” Readers must mentally repair the bare city-name modifier into a natural expression of the magicians' location.
- Pass 2: naturalness 1/3, processing 0/3, context_economy 0/3.

### gold:t1_acts23:ewf2:mcq

When does Felix plan to hear Paul's case?

- A. When accusers arrived
- B. During the next council meeting
- C. After consulting with the Sanhedrin
- D. Immediately upon Paul's arrival
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / REWRITE. Content: HOLD / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: The question “When does Felix plan to hear Paul's case?” is natural, but “When accusers arrived” is conspicuously clipped and tense-discordant: it omits an expected determiner and uses past “arrived” for the prospective hearing.

Content issues:
- Pass 1, question_support (fail): The passage attributes the statement to 'the governor' but never identifies him as Felix.
- Pass 1, context_sufficiency (fail): The displayed passage does not establish that Felix is the governor who makes the promise.
- Pass 1, mcq_validity (fail): A gives the governor's stated condition; B, C, and D are unsupported. However, E is defensible because the passage never identifies the governor as Felix, so the supplied key is not uniquely defensible as worded.
- Pass 2, context_sufficiency (fail): The passage does not establish that the governor is the Felix named in the question.
- Pass 2, mcq_validity (fail): A matches the unnamed governor's statement, while B, C, and D are unsupported. Because Felix is not identified, E remains defensible for the question as written.
- Pass 2, question_support (uncertain): The governor promises a hearing, but the supplied passage never names him Felix.
- Pass 2, answer_support (uncertain): The expected timing exactly matches the governor's statement, but attributing that statement specifically to Felix requires an identification absent from the passage.

### hard:t1_2chr26:9aab:mcq

犹大全体百姓立乌西雅，是为了什么？

- A. 为要使他父亲亚玛谢继续作王
- B. 为要使他接替他父亲亚玛谢作王
- C. 为要重建以禄并使其归于犹大
- D. 为要教他耕种
- E. 根据这段文字无法判断

Overall: **REVIEW** (REWRITE, KEEP). Wording: REWRITE / PASS. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 1/3, context_economy 0/3.
  - naturalness: “犹大全体百姓立乌西雅，是为了什么？”把“立乌西雅”独立作为完整动作，却未说明立为什么，普通现代汉语中有未说完的感觉，读者需自行补出“立为王”的关系。
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

### hard:t1_2sam21:761c:open

在迦特的这四个拉法的后裔，被谁杀死了？

Overall: **REVIEW** (KEEP, REWRITE). Wording: PASS / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “在迦特的这四个拉法的后裔”把地点、“这四个”和祖属修饰连续堆在名词前。“四个拉法的后裔”容易先被切分成“四个拉法”的后裔，需要回头重组为四个后裔，表达不够顺畅。
  - processing: 读者需在“在迦特的这四个拉法的后裔”中确定两个“的”的附着，并确认“四个”计数的是后裔而不是拉法。群体范围本身必要，但这种连续前置限定造成的临时误切分可以避免，并非辨认集体施事所必需。

### hard:t1_acts23:a1ba:open

他们要请谁把保罗带到公会那里？

Overall: **REVIEW** (KEEP, REWRITE). Wording: PASS / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 2/3, context_economy 0/3.
  - processing: “他们要请谁”没有明确请求者。读者需在阴谋者、大祭司和长老等群体之间判断“他们”所指，还要转换引语中的“我们”“你们”。这一额外的请求者定位并非辨认被请求带领保罗者所必需，可以避免。

### hard:t1_acts23:a1ba:mcq

他们要请谁把保罗带到公会那里？

- A. 总督
- B. 军长
- C. 大祭司
- D. 百夫长
- E. 根据这段文字无法判断

Overall: **REVIEW** (KEEP, REWRITE). Wording: PASS / REWRITE. Content: PASS / PASS.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 2/3, context_economy 0/3.
  - processing: 读者需要在叙述中的阴谋者和引语中的“你们和公会”之间，为“他们”选择先行对象，同时追踪请求者、受请求者与保罗。未明示的请求方增加了可避免的群体和人称切换，并不是辨认受请求者必需的复杂性。

### hard:t1_judg17_18:3162:mcq

那些神像最先发生了什么事？

- A. 被毁坏了
- B. 被祭司拿走了
- C. 被那五个人从米迦家里拿走了
- D. 被米迦藏起来了
- E. 根据这段文字无法判断

Overall: **REVIEW** (REWRITE, KEEP). Wording: REWRITE / PASS. Content: PASS / PASS.

- Pass 1: naturalness 2/3, processing 2/3, context_economy 0/3.
  - naturalness: “那些神像最先发生了什么事”将“神像”直接作为“发生了什么事”的主体，搭配生硬，需要理解为神像遭遇的事件。相比之下，“被那五个人从米迦家里拿走了”等选项本身自然。
  - processing: 读者须把“神像……发生了什么事”重新分析为神像受到什么处置，再将其接入“被毁坏了”“被祭司拿走了”等被动选项。事件先后比较是必要的，问句到选项之间的关系修复则可避免。
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

### hard:t1_judg9:8e0b:mcq

橄榄树为什么不肯去作树木的王？

- A. 因为树木随后转向了无花果树。
- B. 因为它要让无花果树来作王。
- C. 因为它必须离开那荣耀神和人的油。
- D. 因为它要来作我们的王。
- E. 根据这段文字无法判断

Overall: **REVIEW** (REWRITE, REVIEW). Wording: REWRITE / REVIEW. Content: PASS / PASS.

- Pass 1: naturalness 1/3, processing 2/3, context_economy 0/3.
  - processing: 比较选项时，读者须在D“它要来作我们的王”中自行重建“我们”是谁，并从叙述者视角切换到树木的邀请视角。这一未标记的视角切换并非理解拒绝理由所必需，增加了可避免的参照辨认负担。
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.


## Additional content holds without a wording rewrite flag

### gold:t1_1kgs13:nntp:open

What does the old prophet say to the man of God?

Overall: **REVIEW** (HOLD_CONTENT, REVIEW). Wording: PASS / PASS. Content: HOLD / REVIEW.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The passage identifies the speaker as 'the prophet' but does not establish that he is old, as the question presupposes.
- Pass 2, question_support (uncertain): The prophet's speech to the man of God is explicit, but the displayed passage does not establish that the prophet is old.

### gold:t1_1kgs13:nntp:mcq

What does the old prophet say to the man of God?

- A. Leave this place immediately
- B. Come home with me and eat
- C. Build an altar with me
- D. Pray for my family
- E. I can't tell from this passage

Overall: **REVIEW** (HOLD_CONTENT, KEEP). Wording: PASS / PASS. Content: HOLD / PASS.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The passage identifies the speaker as 'the prophet' but does not establish that he is old.

### gold:t1_1kgs13:sy7m:open

What comes to the old prophet at the table?

Overall: **REVIEW** (KEEP, HOLD_CONTENT). Wording: PASS / PASS. Content: PASS / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 2, question_support (fail): The passage identifies the recipient as the prophet who brought the man back, but does not identify him as old.

### gold:t1_2chr26:b1ft:open

How did Uzziah trespass against Yahweh?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): The passage says he entered the temple 'to burn incense,' establishing his purpose, not that he actually burned it. The expected answer asserts completion of that action.
- Pass 2, answer_support (fail): The expected answer asserts that he burned incense. The displayed passage establishes that he entered the temple to burn it, but does not establish that he completed the burning.

### gold:t1_2chr26:b1ft:mcq

How does Uzziah trespass against Yahweh?

- A. Ignored the Sabbath
- B. Built idols
- C. Ate forbidden food
- D. Burned incense in Yahweh's house
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): The passage establishes that he entered the temple for the purpose of burning incense, not that he actually burned it. The expected answer changes intended action into completed action.
- Pass 1, mcq_validity (fail): D asserts completed incense burning, which is not established. A, B, and C are unsupported, while E also fails because the passage does identify his transgression.
- Pass 2, answer_support (fail): The passage says he entered the temple 'to burn incense'; it does not state that he actually burned it. The expected answer asserts completion.
- Pass 2, mcq_validity (fail): A–C have no support. D overstates entering to burn incense as actually burning it. E is not defensible because the passage does explain his unfaithfulness; no option accurately states that explanation.

### gold:t1_2kgs11:chty:open

What must commanders do before seeing the king's son?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): 11:4 reports that Jehoiada made a covenant with them and put them under oath before showing the son. It does not state that making the covenant was a mandatory condition for seeing him, as 'must' asserts.
- Pass 1, answer_uniqueness (fail): The passage also places being put under oath before seeing the son. The broad question does not distinguish this from making the covenant or request both.
- Pass 2, question_support (fail): The passage narrates a covenant and an oath before the son is shown; it does not state that making a covenant was a requirement for seeing him. 'Must' turns sequence into a prerequisite.
- Pass 2, answer_support (fail): The covenant occurs before the showing, but the passage does not establish the expected answer as something the commanders must do to see the son.
- Pass 2, answer_uniqueness (fail): Both entering the covenant and being put under oath precede seeing the son. The question does not distinguish these separate acts.

### gold:t1_2kgs11:chty:mcq

What must commanders do before seeing the king's son?

- A. Swear loyalty to Athaliah
- B. Make a covenant with Jehoiada
- C. Guard the temple gates
- D. Receive a blessing from the priest
- E. I can't tell from this passage

Overall: **REVIEW** (HOLD_CONTENT, KEEP). Wording: PASS / PASS. Content: HOLD / PASS.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): Verse 11:4 reports that Jehoiada made a covenant with them and put them under oath before showing the son. It does not state that making the covenant was a mandatory condition for seeing him, as 'must' asserts.
- Pass 1, answer_support (fail): Making a covenant with Jehoiada is supported as an event preceding the viewing, but the passage does not establish the required prerequisite asked for.
- Pass 1, mcq_validity (fail): B describes the preceding event but is not established as something they must do to see the son. A, C, and D are not stated as prerequisites either, making E defensible for the question's mandatory wording rather than the supplied key B.

### gold:t1_2kgs6_7:cc0k:mcq

Why does the king think the Arameans left their camp?

- A. To ambush Israelites
- B. To negotiate peace
- C. To retreat in fear
- D. To gather more troops
- E. I can't tell from this passage

Overall: **REVIEW** (KEEP, HOLD_CONTENT). Wording: PASS / PASS. Content: PASS / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 2, answer_support (fail): The ambush purpose is supported, but the expected answer identifies the intended victims as Israelites. The displayed passage does not establish the city's or its inhabitants' national identity.
- Pass 2, mcq_validity (fail): A captures the ambush explanation but adds an unsupported identification of the victims as Israelites. B–D do not match the king's explanation, and E is not defensible because his explanation is explicit. No option is fully supported as written.

### gold:t1_acts19:zvnx:open

What happened to seven Jewish exorcists?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The displayed passage identifies seven sons of a Jewish chief priest but does not establish that they are exorcists: 'were doing this' refers to an activity outside the supplied window.
- Pass 1, answer_support (fail): Their flight is supported, but the passage says the man with the evil spirit attacked and overpowered them, not that the spirit itself beat them. The expected answer changes the stated attacker.
- Pass 2, answer_support (fail): Their flight is supported, but the passage says the man with the evil spirit attacked and overpowered them, not that the spirit itself beat them.
- Pass 2, context_sufficiency (fail): The passage begins with 'were doing this' without explaining the activity, so it does not establish that the seven sons are the exorcists named in the question.
- Pass 2, question_support (uncertain): The passage describes what happens to seven sons of a Jewish chief priest, but their designation as 'exorcists' depends on the omitted antecedent of 'doing this.'

### gold:t1_acts19:zvnx:mcq

What happened when seven Jewish exorcists tried to cast out an evil spirit in the name of Jesus?

- A. The evil spirit healed them
- B. The evil spirit beat them and they fled
- C. The evil spirit taught them magic
- D. The evil spirit gave them money
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The displayed passage says the seven sons 'were doing this' but never states that they were attempting an exorcism in Jesus' name. The spirit's recognition of Jesus does not establish that action.
- Pass 1, answer_support (fail): Verse 19:16 identifies the man with the evil spirit as the attacker. The expected answer instead identifies the evil spirit itself as the agent who beat them; their flight is supported.
- Pass 1, context_sufficiency (fail): The antecedent of 'doing this' is missing, so the supplied window cannot establish the attempted exorcism used to identify the event.
- Pass 1, mcq_validity (fail): B changes the stated attacker from the possessed man to the spirit. A, C, and D are unsupported, while E is defensible given the missing exorcism context and the absence of a precisely supported outcome option.
- Pass 2, question_support (fail): The displayed passage says the seven sons 'were doing this,' but its antecedent is absent. It does not explicitly establish that they were exorcists attempting an expulsion in Jesus' name.
- Pass 2, answer_support (fail): Their flight is explicit, but the passage attributes the physical attack to 'the man with the evil spirit,' whereas the expected answer attributes it directly to the spirit.
- Pass 2, context_sufficiency (fail): The missing antecedent of 'doing this' is needed to establish the question's specific attempted-exorcism setting.
- Pass 2, mcq_validity (fail): B misidentifies the stated attacker. A, C, and D describe unreported outcomes, and E is not defensible for the outcome because the attack and flight are explicitly narrated.

### gold:t1_acts20:jxkk#2:mcq

What happens to the young man who falls?

- A. He is injured but conscious
- B. He is picked up dead
- C. He is caught by someone
- D. He is unharmed
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, target_preservation (fail): The original asks about the outcome after Paul stretches himself on the young man. The final question and key instead test his being picked up dead after the fall, before Paul's intervention.
- Pass 2, target_preservation (fail): The original asks about the outcome after Paul's intervention; the final question and key instead test the young man's being picked up dead after falling.

### gold:t1_acts23:i7yf:open

What pact did 40 Jewish men make?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The question identifies the group as 40 men, but 23:13 explicitly says more than forty were involved. No distinct group of exactly forty is identified.
- Pass 2, question_support (fail): The question describes a group of forty men, whereas 23:13 explicitly says 'More than forty' were involved.

### gold:t1_acts23:lik5:mcq

How did Paul learn about the plan of the 40 Jewish men?

- A. The high priest told him
- B. A Roman soldier told him
- C. His sister's son heard of it and told him
- D. A fellow prisoner told him
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The passage describes a murder plot but does not identify its participants as 40 Jewish men. That added identification is unsupported within the displayed passage.
- Pass 2, question_support (fail): The passage describes a plot and the nephew informing Paul, but does not identify the plotters as forty Jewish men.

### gold:t1_acts23:krfj:open

What did the captain say about accusations against Paul?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, context_sufficiency (fail): The excerpt begins mid-speech and identifies neither its speaker as the captain nor the accused man as Paul. Those participant references require omitted context.
- Pass 2, context_sufficiency (fail): The excerpt starts mid-sentence and never identifies the speaker as the captain or the accused man as Paul. Those identities require omitted context.

### gold:t1_acts23:krfj:mcq

What does the captain say about the accusations against Paul?

- A. Paul didn't deserve death or imprisonment
- B. Paul was guilty of treason
- C. Paul should be exiled
- D. Paul was innocent of all charges
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, context_sufficiency (fail): The excerpt starts mid-speech and supplies neither the captain's identity nor Paul's name, so the question's named references cannot be established from this window.
- Pass 1, question_support (uncertain): The passage contains a first-person assessment of accusations, but does not identify the speaker as the captain or the accused as Paul.
- Pass 2, context_sufficiency (fail): The excerpt never identifies its first-person speaker as the captain or the accused man as Paul; those identities require missing context.

### gold:t1_acts23:ewf2:open

When would Felix hear Paul's case?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The governor promises to hear Paul's case, but the supplied passage never identifies that governor as Felix.
- Pass 1, context_sufficiency (fail): The governor remains unnamed throughout the displayed passage, leaving the question's reference to Felix unestablished.
- Pass 2, context_sufficiency (fail): The passage identifies the speaker only as the governor; connecting Felix to that speaker requires context outside the supplied window.
- Pass 2, question_support (uncertain): The governor states when he will hear Paul's case, but the displayed passage never identifies that governor as Felix.

### gold:t1_judg17_18:qysg:mcq

What does Micah steal?

- A. A priest's robe
- B. A sacred ephod
- C. A golden idol
- D. 1,100 pieces of silver
- E. I can't tell from this passage

Overall: **REVIEW** (KEEP, HOLD_CONTENT). Wording: PASS / PASS. Content: PASS / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 2, answer_support (fail): The passage specifies 'eleven hundred shekels of silver,' not 1,100 individual pieces. The keyed answer changes the stated unit into an unsupported piece count.
- Pass 2, mcq_validity (fail): D identifies silver but adds an unsupported count of pieces instead of the stated shekels. A, B, and C are unsupported, and E is not an adequate alternative because the passage does identify what was taken.

### gold:t1_judg17_18:rhwo:open

What did Dan's people want the Levite to ask God?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The request to inquire of God is explicit, but the displayed passage does not identify the speakers as Dan's people or the priest as a Levite.
- Pass 1, context_sufficiency (fail): The passage begins with unidentified speakers and supplies neither the Danite identity nor the priest's identification as a Levite.
- Pass 2, question_support (fail): The request to inquire about a successful journey is explicit, but the displayed passage does not identify the speakers as Dan's people or the priest as a Levite.
- Pass 2, context_sufficiency (fail): The identities behind 'they' and the priest's Levite designation are missing, so the question's named participants cannot be established from this window.

### gold:t1_judg17_18:rhwo:mcq

What do Dan's people want the Levite to ask God?

- A. If they would succeed
- B. If they should make peace
- C. If they should return home
- D. If they should build a temple
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, context_sufficiency (fail): The supplied verses leave the speakers as 'they' and identify the addressee only as a priest, without establishing the question's group and Levite references.
- Pass 1, question_support (uncertain): The request to inquire about a successful journey is explicit, but the window does not establish that the speakers are Dan's people or that the priest is a Levite.
- Pass 2, context_sufficiency (fail): The excerpt supplies only 'they' and 'the priest,' without establishing the participant identities used in the question.
- Pass 2, mcq_validity (fail): A matches the unnamed speakers' request; B, C, and D are not requested. E remains defensible for the question as written because neither Dan's people nor the Levite is identified in the supplied passage.
- Pass 2, question_support (uncertain): The request to inquire about journey success is explicit, but the speakers are not identified as Dan's people or the priest as a Levite.
- Pass 2, answer_support (uncertain): The quoted request directly concerns whether their journey will succeed, but connecting it to the named participants requires information outside the excerpt.

### gold:t1_judg17_18:zd8a:open

What did five men from Dan want in Laish?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The passage describes returning men and their proposal, but does not say there were five, that they were from Dan, or that the land was Laish.
- Pass 1, context_sufficiency (fail): The displayed context does not connect its unnamed men and land to the question's five men from Dan and Laish.
- Pass 2, context_sufficiency (fail): The supplied window does not establish the question's five-men identification, tribal affiliation, or Laish location.
- Pass 2, question_support (uncertain): The passage supports the men's desire to possess the land, but does not identify them as five men from Dan or name the land as Laish.

### gold:t1_judg17_18:zd8a:mcq

What do five men from Dan want in Laish?

- A. To form an alliance
- B. To trade goods
- C. To take possession of the land
- D. To find a new priest
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The displayed passage does not identify the men as five men from Dan or name the land as Laish.
- Pass 1, context_sufficiency (fail): Nothing in the supplied window establishes the connection between the described men and land and the question's Dan and Laish references.
- Pass 1, mcq_validity (fail): C matches the unnamed men's proposal, while A, B, and D are unsupported. E is also defensible because the passage does not establish that these are the five men from Dan discussing Laish.
- Pass 2, context_sufficiency (fail): The displayed passage refers only to 'the men' and 'the land'; it does not establish that there are five men, that they are from Dan, or that the destination is Laish.

### gold:t1_judg9:qsc4:open

What does Abimelech do with 70 silver pieces?

Overall: **REVIEW** (HOLD_CONTENT, KEEP). Wording: PASS / PASS. Content: HOLD / PASS.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): Hiring men is supported, but the expected answer calls them 'violent'; the passage describes them as 'worthless and reckless.' It attributes the subsequent murders to Abimelech, not explicitly to these men.

### gold:t1_judg9:qsc4:mcq

What does Abimelech do with 70 silver pieces?

- A. Buys land
- B. Hires wicked, violent men
- C. Donates to the poor
- D. Builds a temple
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): Hiring men is explicit, but the passage calls them 'worthless and reckless,' not violent. The subsequent murder is attributed to Abimelech and does not establish that these men were violent.
- Pass 1, mcq_validity (fail): B contains the unsupported characterization 'violent.' A, C, and D are not supported, while E is inappropriate because the passage explicitly states how the money was used. Thus no option is fully supported as written.
- Pass 2, answer_support (fail): Hiring men is supported, but the passage calls them 'worthless and reckless,' not violent. The subsequent murders are attributed to Abimelech, not explicitly to these men.
- Pass 2, mcq_validity (fail): B includes the unsupported description 'violent.' A, C, and D are unreported uses, while E is not defensible because the passage explicitly states how the money was used.

### gold:t1_judg9:m3kf:open

When did Jotham address Shechem's leaders?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, context_sufficiency (fail): The passage begins mid-address and does not establish that Jotham is speaking or explicitly identify the addressees as Shechem's leaders.
- Pass 1, question_support (uncertain): The excerpt is an address mentioning Shechem's leaders, but it never identifies its speaker as Jotham.
- Pass 2, context_sufficiency (fail): The excerpt starts mid-speech and supplies no identification of Jotham as the speaker or of Shechem's leaders as the audience.
- Pass 2, question_support (uncertain): The speech refers to the killings 'this day,' but the displayed excerpt does not name its speaker as Jotham or explicitly identify its addressees.

### gold:t1_judg9:m3kf:mcq

When did Jotham address Shechem's leaders?

- A. Before Abimelech was made king.
- B. Many years after the killings.
- C. Same day they killed 70 sons.
- D. After the tower of Shechem was burned.
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, context_sufficiency (fail): The passage begins mid-speech and omits the identification of Jotham as speaker. The participant cannot establish that this is the named person's address using this window alone.
- Pass 1, mcq_validity (fail): C matches the internal timing of the displayed speech, whereas A, B, and D lack support. However, E is also defensible because the excerpt does not identify the speech as Jotham's, preventing a uniquely established keyed answer to the question as written.
- Pass 1, question_support (uncertain): The excerpt contains an address referring to the leaders of Shechem, but it never identifies its speaker as Jotham. That attribution cannot be verified from the supplied text.
- Pass 2, context_sufficiency (fail): The passage begins mid-address and never identifies Jotham as the speaker, so the named event cannot be established from the supplied text alone.
- Pass 2, mcq_validity (fail): C matches the displayed speech's 'this day'; A and B conflict with its account, and D is unsupported. However, E is defensible because the passage never identifies the address as Jotham's, so C is not uniquely established for the named event.
- Pass 2, question_support (uncertain): The excerpt contains an address mentioning killings 'this day,' but does not identify its speaker as Jotham.
- Pass 2, answer_support (uncertain): 'This day' supports same-day timing for the displayed speech, but attributing that speech to Jotham requires missing context.

### gold:t1_judg9:iw06:open

What is Jotham's curse?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): 'Fire from Abimelech and Shechem' names abbreviated sources but omits the curse's essential reciprocal outcome: each side consuming the other, including the leaders of Beth-millo.
- Pass 2, answer_support (fail): 'Fire from Abimelech and Shechem' names sources but omits the essential curse that each side's fire consume the other; it also leaves out Beth-millo.

### gold:t1_judg9:j38o:open

Why does God allow Shechem's treachery?

Overall: **REVIEW** (HOLD_CONTENT, KEEP). Wording: PASS / PASS. Content: HOLD / PASS.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The question frames God's role as allowing treachery, whereas 9:23 explicitly says God sent animosity and caused the leaders to act deceitfully. This changes the stated causal role.

### gold:t1_judg9:g2ya:open

Why does Zebul send messengers to Abimelech?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): 9:31 supports sending messengers to Abimelech, but identifies the sender only as 'he,' not as Zebul.
- Pass 1, context_sufficiency (fail): The sender's antecedent is outside the supplied passage, so the identification as Zebul cannot be established.
- Pass 2, context_sufficiency (fail): The supplied window lacks an antecedent identifying the messenger-sender as Zebul.
- Pass 2, question_support (uncertain): The passage supports sending messengers to Abimelech, but identifies the sender only as 'he'; it does not establish that the sender is Zebul.

### gold:t1_judg9:g2ya:mcq

Why does Zebul send messengers to Abimelech?

- A. To ask Abimelech to make peace with Gaal
- B. To assure Abimelech of Shechem's loyalty
- C. To summon Abimelech to a meeting in Shechem
- D. To warn about Gaal's incitement
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, context_sufficiency (fail): The opening 'he' has no supplied antecedent, and Zebul is never named. The passage therefore cannot establish the question's named sender.
- Pass 1, question_support (uncertain): The passage reports a warning sent to Abimelech, but calls the sender only 'he'; it does not establish that the sender is Zebul.
- Pass 2, context_sufficiency (fail): The passage begins 'he covertly sent messengers' and never identifies that sender as Zebul. His identity cannot be verified from the displayed window.

### gold:t1_judg9:z7va:open

What happens when Gaal fights Abimelech?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): Gaal's flight is explicit, but the passage says many Shechemites 'fell wounded,' not that many died.
- Pass 2, answer_support (fail): Gaal's flight is explicit, but the passage says many Shechemites 'fell wounded,' not that many died.

### gold:t1_judg9:z7va:mcq

What happens when Gaal fights Abimelech?

- A. Abimelech is captured
- B. Gaal wins the battle
- C. The city is destroyed
- D. Gaal flees; many die
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): Gaal's flight is explicit, but the passage says many Shechemites 'fell wounded,' not that many died.
- Pass 1, mcq_validity (fail): Key D adds unsupported deaths. A, B, and C are also unsupported. E does not repair the absence of an accurate substantive outcome option.
- Pass 2, answer_support (fail): 9:40 supports Gaal's flight but says many Shechemites 'fell wounded,' not that many died. Death cannot be assumed from wounding.
- Pass 2, mcq_validity (fail): Key D includes unsupported deaths. A, B, and C are not reported outcomes. E does not repair the item: the passage does describe what happens, but no option accurately states that outcome.

### gold:t1_judg9:u7l2:open

What does Abimelech do after capturing the city?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): The passage places capturing the city and killing its people together before 'Then he demolished the city.' It does not establish killing the people as an action after capture, as the expected answer requires.
- Pass 2, answer_support (fail): The passage groups killing the people with capturing the city, then explicitly places demolition and sowing salt afterward. The expected answer treats the killing as a post-capture action, which the supplied sequence does not establish.

### gold:t1_judg9:u7l2:mcq

What does Abimelech do to the city after capturing it?

- A. Leaves it untouched
- B. Destroys it
- C. Gives it to his allies
- D. Rebuilds it
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, target_preservation (fail): The original answer includes killing people and destroying the city. The final question narrows the object to the city, and its key retains only destruction.
- Pass 2, target_preservation (fail): The original answer includes both killing people and destroying the city. The final question narrows the object to the city, and its key retains only destruction, dropping the killing component.

### gold:t1_judg9:mu3p:open

How does Abimelech kill Shechem's leaders?

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The passage says the fire killed everyone in the tower of Shechem, about a thousand men and women. It does not identify those victims as Shechem's leaders, as the question presupposes.
- Pass 1, context_sufficiency (fail): The displayed window does not introduce Shechem's leaders or connect that group to the people inside the tower.
- Pass 1, answer_support (uncertain): Setting the refuge on fire is supported as the means of killing the tower's occupants. Whether this answers the question about Shechem's leaders cannot be established because the excerpt does not identify those leaders among the victims.
- Pass 2, question_support (fail): The passage describes killing everyone in the tower, about a thousand men and women, but never identifies these victims as Shechem's leaders.
- Pass 2, answer_support (fail): Burning the inner chamber explains the deaths of the tower's occupants, but the supplied passage does not establish that this killed the leaders named in the question.
- Pass 2, context_sufficiency (fail): Context identifying Shechem's leaders with the tower's occupants is missing.

### gold:t1_judg9:mu3p:mcq

How does Abimelech kill the leaders of Shechem?

- A. Shooting arrows
- B. Poisoning their water
- C. Setting the tower on fire
- D. Collapsing the building
- E. I can't tell from this passage

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): The passage reports the deaths of everyone in the tower, about a thousand men and women, but never identifies these victims as Shechem's leaders.
- Pass 1, answer_support (fail): Burning is supported as the means of killing the tower's occupants, but the passage does not establish that it killed the leaders named in the question.
- Pass 1, context_sufficiency (fail): Context identifying Shechem's leaders among the tower's occupants is missing.
- Pass 1, mcq_validity (fail): A, B, and D are unsupported. C describes the occupants' deaths but is not established for the leaders specifically, making E defensible instead of the supplied key C.
- Pass 2, question_support (fail): The passage reports killing everyone in the tower, about a thousand men and women, but does not identify those people as Shechem's leaders.
- Pass 2, answer_support (fail): Setting the chamber on fire explains the tower occupants' deaths, but the displayed passage does not establish that the victims were the leaders named in the question.
- Pass 2, context_sufficiency (fail): Context identifying Shechem's leaders as occupants or victims is missing; the opening 'he' also lacks an explicit preceding antecedent in the window.
- Pass 2, mcq_validity (fail): A, B, and D are unsupported. C describes the tower deaths but cannot be established for the specified leaders. E is defensible because the passage does not identify those leaders as the victims, so the supplied key C is not securely supported.

### hard:t1_1kgs13:9a0c:mcq

王吩咐人捉拿谁？

- A. 从犹大来的神人
- B. 耶罗波安
- C. 坛旁烧香的祭司
- D. 伯特利的老先知
- E. 根据这段文字无法判断

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): 本文支持被捉拿者是“神人”，但没有说明他“从犹大来”。预期答案增加了无法由所给经文核实的来处。
- Pass 1, context_sufficiency (fail): 所给经文足以辨认神人，却不足以核实预期答案及 A 选项中的“从犹大来”这一身份限定。
- Pass 1, mcq_validity (fail): 键 A 的核心人物正确，但“从犹大来”未获本文支持。B 是发令的王，C 和 D 也无依据；E 不能解决这种部分身份可知、来处未知的问题，因此不能确认唯一完整受支持的键项。
- Pass 2, answer_support (fail): The passage identifies the target as the man of God but does not say that he came from Judah, as the expected answer asserts.
- Pass 2, mcq_validity (fail): Key A includes the unsupported origin “从犹大来的”. B is the king issuing the command; C and D are not identified as its target. E does not fix the unsupported key: the target is identifiable as a man of God, but his asserted origin is not established.

### hard:t1_1kgs13:a6cd:mcq

王求神人为他祷告，谁为王祷告了？

- A. 从犹大来的神人
- B. 伯特利的老先知
- C. 坛旁的祭司
- D. 耶罗波安
- E. 根据这段文字无法判断

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 1/3.

Content issues:
- Pass 1, answer_support (fail): 经文支持“神人”，但没有交代他“从犹大来”；预期答案增加了无法由本段确认的来源信息。
- Pass 1, mcq_validity (fail): A增加未获支持的“从犹大来”；B、C未被记为祷告者，D也无支持。经文明说神人为王祷告，所以E也不能作为整题无法判断的答案；没有完全受支持的选项。
- Pass 2, answer_support (fail): The passage supports “神人” but never says he came from Judah. The expected answer adds an unsupported geographical identification.
- Pass 2, mcq_validity (fail): Key A adds “从犹大来的”, which the passage does not establish. B and C are not identified as praying, and D is not identified in the passage. E cannot repair the missing support for A: the text identifies a man of God, but not the qualified identity required by A.

### hard:t1_1kgs13:4661:open

神人为什么不肯跟王回去？

Overall: **REVIEW** (HOLD_CONTENT, KEEP). Wording: PASS / PASS. Content: HOLD / PASS.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, context_sufficiency (fail): 显示的段落只称对方为“你”，没有说明他是王；仅凭这段文字无法建立问题中“王”与对话对象的身份对应。

### hard:t1_1kgs13:4661:mcq

神人为什么不肯跟王回去？

- A. 因为他很匆忙。
- B. 因为王只给他一半的家产。
- C. 因为耶和华的话这样吩咐他。
- D. 因为他累了。
- E. 根据这段文字无法判断

Overall: **REVIEW** (REVIEW, HOLD_CONTENT). Wording: PASS / PASS. Content: REVIEW / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (uncertain): 13:8–9 explicitly connects the refusal to the LORD's command, but the displayed passage does not identify the person addressed as the king.
- Pass 1, context_sufficiency (uncertain): The refusal and its explanation are clear, but identifying the interlocutor as the king requires context outside the displayed verses.
- Pass 2, context_sufficiency (fail): The displayed passage calls the interlocutor only '你'; it never identifies him as a king, so the question's royal reference cannot be verified within the supplied window.

### hard:t1_1kgs13:8a66:open

谁在路上被狮子咬死了？

Overall: **REVIEW** (HOLD_CONTENT, KEEP). Wording: PASS / PASS. Content: HOLD / PASS.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 0/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): 13:24 says the lion killed him, but does not specify biting as the means of death, as 咬死 does.

### hard:t1_1kgs13:8a66:mcq

谁在路上被狮子咬死了？

- A. 耶罗波安
- B. 伯特利的老先知
- C. 从犹大来的神人
- D. 王的仆人
- E. 根据这段文字无法判断

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): The victim is supported as the man of God, but nothing in 13:23–25 establishes that he came from Judah, as the expected answer asserts.
- Pass 1, context_sufficiency (fail): The passage identifies the victim's role but omits the geographical origin needed to verify the full keyed option.
- Pass 1, mcq_validity (fail): C adds an unsupported Judah origin. A and D are not identified as the victim, and B is the person who supplied the donkey. E becomes defensible because no fully supported substantive option is supplied.
- Pass 2, answer_support (fail): 经文支持死者是“神人”，但未说他“从犹大来”。预期答案增加了显示段落不能支持的来源信息。
- Pass 2, mcq_validity (fail): 指定答案C包含未经本段支持的“从犹大来”。A、B、D也没有得到受害者身份的支持；E又不能准确替代本段已经能够作出的“神人”回答，因此没有一个完全由本段支持的实质答案选项。

### hard:t1_2kgs11:df0e:mcq

耶何耶大吩咐百夫长，要杀死哪些人？

- A. 百夫长
- B. 凡跟随她的人
- C. 被带出去的那女人
- D. 城门的守卫
- E. 根据这段文字无法判断

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, answer_uniqueness (fail): 问题未限定为明确命令中提到的跟随者。“不可在耶和华的殿里杀她”也表明那女人是要被处死的对象，随后又记载她被带到外面杀死，因此 C 也可作为宽泛问题的回答。
- Pass 1, mcq_validity (fail): B 有明确命令支持；C 也可由禁止在殿内杀她及随后在外处死她得到支持。A 百夫长是受命者，D 守卫无依据，E 不成立，但 B 与 C 的并存使键不唯一。
- Pass 2, answer_uniqueness (fail): The broad question also admits the woman herself: Jehoiada says not to kill her in the temple, orders her taken out, and 11:16 reports her execution. Her intended killing is therefore defensible alongside the explicit order concerning followers.
- Pass 2, mcq_validity (fail): B is explicitly supported, but C is also defensible from the instruction not to kill the woman in the temple and her subsequent execution outside it. A and D are unsupported, and E is false. The key is not the only defensible option.

### hard:t1_2kgs6_7:9cf3:open

四个长大麻风的人说坐在这里也必死，之后他们决定怎么做？

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): 经文支持前往叙利亚营，但未说他们决定“投降”。预期答案中的 surrender 增加了未获本文支持的行动含义。
- Pass 2, answer_support (fail): The passage states their decision to go to the camp, but does not state a decision to surrender. Their willingness to risk being spared or killed does not by itself establish surrender.

### hard:t1_2kgs6_7:9cf3:mcq

四个长大麻风的人说坐在这里也必死，之后他们决定怎么做？

- A. 藏在田间
- B. 去求王帮助
- C. 往叙利亚营去投降
- D. 进城去
- E. 根据这段文字无法判断

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 1/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, answer_support (fail): The passage supports going to the Syrian camp and accepting the possibility of being spared or killed, but does not state that they would surrender. 投降 adds an action not established by this passage.
- Pass 1, mcq_validity (fail): C adds the unsupported action 投降. A and B are absent, D is the alternative they associate with death, and E is not justified because the passage does state their plan to go to the camp. No option fully matches the supported answer.
- Pass 2, answer_support (fail): The passage supports '往叙利亚营去', but does not state that they decided to surrender. Considering whether the camp's occupants will spare or kill them does not establish that additional action.
- Pass 2, mcq_validity (fail): Key C adds an unsupported surrender component. A and B are unsupported, D is rejected in the passage, and E is not appropriate because their decision to go to the camp is stated. There is no fully supported option.

### hard:t1_2kgs6_7:fe00:open

她们约定哪一天吃另一个妇人的儿子？

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): 6:28 只记载另一妇人提出“明天我们就吃我的儿子”，没有记载说话的妇人同意；“她们约定”将单方提议变成了双方协议。
- Pass 2, question_support (fail): “她们约定” presupposes a mutual agreement. The displayed passage reports one woman’s proposal, “明天我们就吃我的儿子”, but does not state the other woman’s acceptance.

### hard:t1_2kgs6_7:fe00:mcq

她们约定哪一天吃另一个妇人的儿子？

- A. 今天
- B. 下个星期
- C. 昨天
- D. 明天
- E. 根据这段文字无法判断

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, question_support (fail): 6:28 reports one woman’s proposal, 明天我们就吃我的儿子. The displayed passage does not establish that both women agreed, as 她们约定 presupposes.
- Pass 2, question_support (fail): 经文只记载一个妇人提出“明天我们就吃我的儿子”，没有记载另一个妇人同意；“她们约定”把单方提出的计划说成了双方达成的约定。

### hard:t1_2kgs6_7:ea44:mcq

两个妇人先吃了谁的孩子？

- A. 另一个妇人的孩子
- B. 使者的孩子
- C. 向王呼喊的那个妇人的孩子
- D. 王的孩子
- E. 根据这段文字无法判断

Overall: **REVIEW** (KEEP, HOLD_CONTENT). Wording: PASS / PASS. Content: PASS / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 2, answer_support (fail): 段落支持孩子属于正在向王说话的妇人，但没有记载她“向王呼喊”；预期答案加入了未展示的识别事件。
- Pass 2, context_sufficiency (fail): 所给上下文能识别说话妇人，却缺少将她确定为选项所称“向王呼喊”的妇人的记载。
- Pass 2, mcq_validity (fail): C是预期身份，但其“向王呼喊”的限定不在段落中；A与“我的儿子”不符，B、D无依据，因而无法严格确立所给键C为唯一受支持选项。

### hard:t1_acts23:2b9c:open

军长吩咐谁去预备护送的队伍？

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, context_sufficiency (fail): The passage starts with '随后，他' without an antecedent. Earlier context is needed to verify the question's identification of the order-giver as 军长.
- Pass 1, question_support (uncertain): The escort order is explicit, but the person issuing it is only 他. The displayed passage does not establish that this person is the commander named in the question.
- Pass 2, question_support (fail): 文段支持有人吩咐两个百夫长预备队伍，但发令者只称“他”，没有说明其身份是军长；题干添加了这一身份。
- Pass 2, context_sufficiency (fail): 窗口从“随后，他”开始，缺少发令者的先行身份信息，无法仅凭所给文字确认题干所称的军长。

### hard:t1_acts23:2b9c:mcq

军长吩咐谁去预备护送的队伍？

- A. 二百步兵
- B. 两个百夫长
- C. 七十骑兵
- D. 长老们
- E. 根据这段文字无法判断

Overall: **HOLD_CONTENT** (HOLD_CONTENT, HOLD_CONTENT). Wording: PASS / PASS. Content: HOLD / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 1/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 1, context_sufficiency (fail): The displayed passage starts with '他' and supplies no antecedent establishing the commander named in the question.
- Pass 1, question_support (uncertain): 23:23–24 supports the preparation and escort order, but calls its speaker only '他'; the identification of that speaker as '军长' cannot be verified.
- Pass 2, question_support (fail): 段落只称发令者为“他”，没有说明他是“军长”；问题添加了未获支持的身份。
- Pass 2, context_sufficiency (fail): 缺少“他”的先行身份介绍，无法仅凭所给段落确认问题中的军长就是发令者。

### hard:t1_judg17_18:97e8:open

约拿单和他的子孙作但支派的祭司，直到什么时候？

Overall: **REVIEW** (KEEP, HOLD_CONTENT). Wording: PASS / PASS. Content: PASS / HOLD.

- Pass 1: naturalness 0/3, processing 1/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 2, answer_support (fail): 段落支持“直到被掳之日”，但没有说明被掳的是“那地”。预期答案“Until the captivity of the land”加入了显示文本未提供的被掳对象。

### hard:t1_judg9:79d0:open

城楼上的人是怎么死的？

Overall: **REVIEW** (KEEP, HOLD_CONTENT). Wording: PASS / PASS. Content: PASS / HOLD.

- Pass 1: naturalness 0/3, processing 0/3, context_economy 0/3.
- Pass 2: naturalness 0/3, processing 1/3, context_economy 0/3.

Content issues:
- Pass 2, answer_support (fail): 预期答案中的“fire”符合烧死的方式，但“on the stronghold”把失火处说成堡垒；段落明确记载点火烧的是神庙内室，没有将其称为堡垒。


## Complete inventory

| ID | Question | Overall decision | Wording passes | Content passes |
|---|---|---|---|---|
| gold:t1_1kgs13:mjwk:open | Who came from Judah by Yahweh's word? | REVIEW | PASS / REWRITE | PASS / PASS |
| gold:t1_1kgs13:mjwk:mcq | Who comes from Judah by Yahweh's word? | REVIEW | PASS / REWRITE | PASS / PASS |
| gold:t1_1kgs13:kcyl:open | What happens when the man of God prays? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:kcyl:mcq | What happens when the man of God prays? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:uut5:open | What does the king say to the man of God? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:uut5:mcq | What does the king say to the man of God? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:gfxe:open | Who showed the old prophet which way the man of God had gone? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:gfxe:mcq | Who showed the old prophet which way the man of God had gone? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:nntp:open | What does the old prophet say to the man of God? | REVIEW | PASS / PASS | HOLD / REVIEW |
| gold:t1_1kgs13:nntp:mcq | What does the old prophet say to the man of God? | REVIEW | PASS / PASS | HOLD / PASS |
| gold:t1_1kgs13:sqkb:open | What does the old prophet tell the man of God? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:sqkb:mcq | What does the old prophet tell the man of God? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:sy7m:open | What comes to the old prophet at the table? | REVIEW | PASS / PASS | PASS / HOLD |
| gold:t1_1kgs13:sy7m:mcq | What comes to the old prophet at the table? | REVIEW | PASS / PASS | REVIEW / PASS |
| gold:t1_1kgs13:trr6:open | What happens after the man of God leaves? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:trr6:mcq | What happens after the man of God leaves? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:nc1x:open | What explanation did the old prophet give for the man of God's death? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:nc1x:mcq | What explanation did the old prophet give for the man of God's death? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:w4ws:open | What does the old prophet do with the body? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_1kgs13:w4ws:mcq | What does the old prophet do with the body? | REVIEW | REWRITE / PASS | PASS / PASS |
| gold:t1_1kgs13:o8ae:open | What becomes sin to Jeroboam's family? | REWRITE | REWRITE / REWRITE | PASS / PASS |
| gold:t1_1kgs13:o8ae:mcq | What becomes sin to Jeroboam's family? | REWRITE | REWRITE / REWRITE | PASS / PASS |
| gold:t1_2chr26:abwv:open | What did Uzziah do to Eloth as king? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2chr26:abwv:mcq | What does Uzziah do to Eloth as king? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2chr26:tglh:open | How did Uzziah follow his father's example with Yahweh? | HOLD_CONTENT | REWRITE / REWRITE | HOLD / HOLD |
| gold:t1_2chr26:tglh:mcq | How does Uzziah follow his father's example with Yahweh? | HOLD_CONTENT | REWRITE / REWRITE | HOLD / HOLD |
| gold:t1_2chr26:ryq4:open | What did Uzziah build at Jerusalem's gates? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2chr26:ryq4:mcq | What does Uzziah build at Jerusalem's gates? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2chr26:ubmy:open | How did Uzziah's army go out to war? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2chr26:ubmy:mcq | How did Uzziah's army go out to war? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2chr26:b1ft:open | How did Uzziah trespass against Yahweh? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_2chr26:b1ft:mcq | How does Uzziah trespass against Yahweh? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_2chr26:s927:open | Why does leprosy break out on Uzziah? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2chr26:s927:mcq | Why does leprosy appear on Uzziah's forehead? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2chr26:mv16:open | Why does Uzziah live separately until death? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2chr26:mv16:mcq | Why does Uzziah live in a separate house until he dies? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs11:fn7d:open | Who was Athaliah unable to kill? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs11:fn7d:mcq | Whom was Athaliah unable to kill? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs11:chty:open | What must commanders do before seeing the king's son? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_2kgs11:chty:mcq | What must commanders do before seeing the king's son? | REVIEW | PASS / PASS | HOLD / PASS |
| gold:t1_2kgs11:otua:open | What did non-serving groups do on the Sabbath? | REVIEW | REWRITE / REWRITE | PASS / HOLD |
| gold:t1_2kgs11:otua:mcq | What did non-serving groups do on the Sabbath? | REVIEW | REWRITE / REWRITE | PASS / HOLD |
| gold:t1_2kgs11:w4ys:open | What did Jehoiada give the commanders? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs11:w4ys:mcq | What did Jehoiada give the commanders? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs11:dpu2:open | What did Athaliah see before she tore her clothes? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs11:dpu2:mcq | What did Athaliah see before she tore her clothes? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs11:rvb6:open | What did people do after Jehoiada's covenant? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs11:rvb6:mcq | What did people do after Jehoiada's covenant? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs11:t7qw:open | How did people respond when Joash sat on the throne? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs11:t7qw:mcq | How did people respond when Joash sat on the throne? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:dbzo:open | Why was a donkey's head sold for silver? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:dbzo:mcq | Why was a donkey's head sold for eighty pieces of silver? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:sz5j:open | What troubled the woman who spoke to the king? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:sz5j:mcq | What troubles the woman who speaks to the king? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:kenl:open | What did Elisha tell the elders to do? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:kenl:mcq | What does Elisha tell the elders to do? | REVIEW | REVIEW / PASS | PASS / PASS |
| gold:t1_2kgs6_7:rvt6:open | What happens to the unbelieving captain? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:rvt6:mcq | What happens to the unbelieving captain? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:u21g:open | Why did four leprous men go to the Arameans? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:u21g:mcq | Why do four leprous men go to the Arameans? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:lxi8:open | Why did Arameans think Israel hired Hittites and Egyptians? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:lxi8:mcq | Why do the Arameans think Israel hired Hittites and Egyptians? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:n556:open | What did gatekeepers do after hearing about Arameans? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:n556:mcq | What do the gatekeepers do after hearing about the Arameans? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:cc0k:open | Why did the king think Arameans left their camp? | REVIEW | PASS / REWRITE | HOLD / PASS |
| gold:t1_2kgs6_7:cc0k:mcq | Why does the king think the Arameans left their camp? | REVIEW | PASS / PASS | PASS / HOLD |
| gold:t1_2kgs6_7:dmm3:open | What was the road full of? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:dmm3:mcq | What is the road full of? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2kgs6_7:pb1x:open | What did the captain say to Elisha's prophecy? | REWRITE | REWRITE / REWRITE | PASS / PASS |
| gold:t1_2kgs6_7:pb1x:mcq | What does the captain say to Elisha's prophecy? | REWRITE | REWRITE / REWRITE | PASS / PASS |
| gold:t1_2sam21:kjsg:open | How does Abishai rescue David? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2sam21:kjsg:mcq | How did Abishai rescue David when he was weary? | REVIEW | REVIEW / REWRITE | PASS / PASS |
| gold:t1_2sam21:gphm:open | Who fell at the hands of David and his servants in Gath? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_2sam21:gphm:mcq | Who fell at the hands of David and his servants in Gath? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_acts19:b1be:open | What happened when handkerchiefs and aprons that had touched Paul were taken to the sick? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_acts19:b1be:mcq | What happened when handkerchiefs and aprons that had touched Paul were taken to the sick? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_acts19:zvnx:open | What happened to seven Jewish exorcists? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_acts19:zvnx:mcq | What happened when seven Jewish exorcists tried to cast out an evil spirit in the name of Jesus? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_acts19:xtb7:open | What did Ephesus magicians do with their books? | REVIEW | REWRITE / PASS | PASS / PASS |
| gold:t1_acts19:xtb7:mcq | In Ephesus, what did many who practiced magical arts do? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_acts20:jxkk#2:open | What happens after Paul stretches on the young man? | REWRITE | REWRITE / REWRITE | PASS / REVIEW |
| gold:t1_acts20:jxkk#2:mcq | What happens to the young man who falls? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_acts23:i7yf:open | What pact did 40 Jewish men make? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_acts23:i7yf:mcq | What pact concerning Paul did some Jewish men make? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_acts23:lik5:open | How did Paul learn about the plan? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_acts23:lik5:mcq | How did Paul learn about the plan of the 40 Jewish men? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_acts23:xj40:open | How did captain respond to the plan? | HOLD_CONTENT | REWRITE / REWRITE | HOLD / HOLD |
| gold:t1_acts23:xj40:mcq | How did captain respond to the plan? | HOLD_CONTENT | REWRITE / REWRITE | HOLD / HOLD |
| gold:t1_acts23:krfj:open | What did the captain say about accusations against Paul? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_acts23:krfj:mcq | What does the captain say about the accusations against Paul? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_acts23:ewf2:open | When would Felix hear Paul's case? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_acts23:ewf2:mcq | When does Felix plan to hear Paul's case? | HOLD_CONTENT | PASS / REWRITE | HOLD / HOLD |
| gold:t1_judg17_18:qysg:open | What did Micah steal? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:qysg:mcq | What does Micah steal? | REVIEW | PASS / PASS | PASS / HOLD |
| gold:t1_judg17_18:webl:open | What role did Micah give his son? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:webl:mcq | What role does Micah give his son? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:xy2r:open | Why did the Levite leave Bethlehem? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:xy2r:mcq | Why does the Levite leave Bethlehem? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:tyai:open | Why did Micah think Yahweh would be good to him? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:tyai:mcq | Why does Micah think Yahweh will be good to him? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:e4u2:open | Why were Dan's descendants seeking territory? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:e4u2:mcq | Why are Dan's descendants seeking territory? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:rhwo:open | What did Dan's people want the Levite to ask God? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg17_18:rhwo:mcq | What do Dan's people want the Levite to ask God? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg17_18:zd8a:open | What did five men from Dan want in Laish? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg17_18:zd8a:mcq | What do five men from Dan want in Laish? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg17_18:shz9:open | What religious objects did the spies say were in one of the houses? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:shz9:mcq | What religious objects did the spies say were in one of the houses? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:tlmz:open | Why was Micah angry? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:tlmz:mcq | Why is Micah angry? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:ramy:open | Why can't Laish be rescued? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:ramy:mcq | Why can't Laish be rescued? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:h3z1:open | Who are the Danites' priests? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg17_18:h3z1:mcq | Who are the Danites' priests? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:w5fv:open | Who is Abimelech's father? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:w5fv:mcq | Who is Abimelech's father? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:qsc4:open | What does Abimelech do with 70 silver pieces? | REVIEW | PASS / PASS | HOLD / PASS |
| gold:t1_judg9:qsc4:mcq | What does Abimelech do with 70 silver pieces? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:m3kf:open | When did Jotham address Shechem's leaders? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:m3kf:mcq | When did Jotham address Shechem's leaders? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:iw06:open | What is Jotham's curse? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:iw06:mcq | What is Jotham's curse? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:j38o:open | Why does God allow Shechem's treachery? | REVIEW | PASS / PASS | HOLD / PASS |
| gold:t1_judg9:j38o:mcq | Why does God allow Shechem's treachery? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:lt0r:open | Who do Shechem's leaders plan to ambush? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:lt0r:mcq | Who do Shechem's leaders plan to ambush? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:eo5e:open | When does Zebul become angry? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:eo5e:mcq | When does Zebul become angry? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:g2ya:open | Why does Zebul send messengers to Abimelech? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:g2ya:mcq | Why does Zebul send messengers to Abimelech? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:qn8s:open | How did Zebul describe the men? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:qn8s:mcq | How did Zebul describe the men? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:ax04:open | What does Zebul tell Gaal to do? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:ax04:mcq | What does Zebul tell Gaal to do? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:z7va:open | What happens when Gaal fights Abimelech? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:z7va:mcq | What happens when Gaal fights Abimelech? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:u7l2:open | What does Abimelech do after capturing the city? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:u7l2:mcq | What does Abimelech do to the city after capturing it? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:u0vj:open | Where did the leaders in the tower of Shechem enter? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:u0vj:mcq | Where did the leaders in the tower of Shechem enter? | KEEP | PASS / PASS | PASS / PASS |
| gold:t1_judg9:mu3p:open | How does Abimelech kill Shechem's leaders? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| gold:t1_judg9:mu3p:mcq | How does Abimelech kill the leaders of Shechem? | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_1kgs13:0887:open | 谁必在这坛上把那些烧香的祭司献为祭？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_1kgs13:0887:mcq | 谁必在这坛上把那些烧香的祭司献为祭？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_1kgs13:9a0c:open | 王吩咐人捉拿谁？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_1kgs13:9a0c:mcq | 王吩咐人捉拿谁？ | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_1kgs13:a6cd:open | 王求神人为他祷告，谁为王祷告了？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_1kgs13:a6cd:mcq | 王求神人为他祷告，谁为王祷告了？ | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_1kgs13:4661:open | 神人为什么不肯跟王回去？ | REVIEW | PASS / PASS | HOLD / PASS |
| hard:t1_1kgs13:4661:mcq | 神人为什么不肯跟王回去？ | REVIEW | PASS / PASS | REVIEW / HOLD |
| hard:t1_1kgs13:ec63:open | 带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_1kgs13:ec63:mcq | 带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_1kgs13:8a66:open | 谁在路上被狮子咬死了？ | REVIEW | PASS / PASS | HOLD / PASS |
| hard:t1_1kgs13:8a66:mcq | 谁在路上被狮子咬死了？ | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_1kgs13:2f00:open | 带他回来的先知先把神人的尸首带到哪里？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_1kgs13:2f00:mcq | 带他回来的先知先把神人的尸首带到哪里？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_1kgs13:e302:mcq | 这些事以后，耶罗波安仍然不肯做什么？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2chr26:9aab:open | 犹大全体百姓立乌西雅，是为了什么？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_2chr26:9aab:mcq | 犹大全体百姓立乌西雅，是为了什么？ | REVIEW | REWRITE / PASS | PASS / PASS |
| hard:t1_2chr26:4cb0:open | 谁教导乌西雅敬畏神？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2chr26:4cb0:mcq | 谁教导乌西雅敬畏神？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2chr26:1cab:open | 神帮助乌西雅攻打哪些人？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2chr26:1cab:mcq | 神帮助乌西雅攻打哪些人？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_2chr26:1fc4:open | 谁爱好土地，所以设立了农夫和葡萄园工人？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_2chr26:1fc4:mcq | 谁爱好土地，所以设立了农夫和葡萄园工人？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_2chr26:723e:open | 这三十万七千五百训练有素的军队由谁统领？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_2chr26:723e:mcq | 这三十万七千五百训练有素的军队由谁统领？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_2chr26:eb1d:open | 祭司亚撒利亚和八十位祭司跟随谁进了耶和华的殿？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2chr26:eb1d:mcq | 祭司亚撒利亚和八十位祭司跟随谁进了耶和华的殿？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2chr26:f9a9:open | 乌西雅自己为什么急忙出去？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2chr26:f9a9:mcq | 乌西雅自己为什么急忙出去？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2chr26:9860:open | 乌西雅被埋葬以后，发生了什么事？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2chr26:9860:mcq | 乌西雅被埋葬以后，发生了什么事？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:a99f:open | 谁和他的奶母在耶和华的殿里藏了六年？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:a99f:mcq | 谁和他的奶母在耶和华的殿里藏了六年？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:5bea:open | 谁被吩咐要为王看守耶和华的殿？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:5bea:mcq | 谁被吩咐要为王看守耶和华的殿？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:b13a:open | 谁把枪和盾牌交给了百夫长？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:b13a:mcq | 谁把枪和盾牌交给了百夫长？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:d4f4:open | 亚他利雅为什么出来到耶和华的殿中见众人？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:d4f4:mcq | 亚他利雅为什么出来到耶和华的殿中见众人？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:df0e:open | 耶何耶大吩咐百夫长，要杀死哪些人？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:df0e:mcq | 耶何耶大吩咐百夫长，要杀死哪些人？ | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_2kgs11:f49c:open | 耶何耶大立的第一个约，是在哪些之间立的？ | REVIEW | REWRITE / REWRITE | HOLD / PASS |
| hard:t1_2kgs11:f49c:mcq | 耶何耶大立的第一个约，是在哪些之间立的？ | HOLD_CONTENT | REWRITE / REWRITE | HOLD / HOLD |
| hard:t1_2kgs11:8730:open | 城中为什么安静了？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs11:8730:mcq | 城中为什么安静了？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:c343:open | 那官怀疑以利沙的话，以利沙怎样回答他？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:c343:mcq | 那官怀疑以利沙的话，以利沙怎样回答他？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:9cf3:open | 四个长大麻风的人说坐在这里也必死，之后他们决定怎么做？ | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_2kgs6_7:9cf3:mcq | 四个长大麻风的人说坐在这里也必死，之后他们决定怎么做？ | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_2kgs6_7:5bba:open | 叙利亚人以为谁要来攻击他们？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:5bba:mcq | 叙利亚人以为谁要来攻击他们？ | REVIEW | PASS / REVIEW | PASS / PASS |
| hard:t1_2kgs6_7:3452:open | 长大麻风的人承认做得不对以后，打算怎么做？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:3452:mcq | 长大麻风的人承认做得不对以后，打算怎么做？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:6138:open | 百姓出去掠夺叙利亚营之前，刚发生了什么事？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:6138:mcq | 百姓出去掠夺叙利亚营之前，刚发生了什么事？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:2ac1:open | 百姓在城门口践踏了谁？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:2ac1:mcq | 百姓在城门口践踏了谁？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:fe00:open | 她们约定哪一天吃另一个妇人的儿子？ | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_2kgs6_7:fe00:mcq | 她们约定哪一天吃另一个妇人的儿子？ | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_2kgs6_7:ea44:open | 两个妇人先吃了谁的孩子？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:ea44:mcq | 两个妇人先吃了谁的孩子？ | REVIEW | PASS / PASS | PASS / HOLD |
| hard:t1_2kgs6_7:5e57:open | 以利沙称谁为“杀人犯”？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2kgs6_7:5e57:mcq | 以利沙称谁为“杀人犯”？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2sam21:de9f:open | 亚比筛击杀了谁？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2sam21:de9f:mcq | 亚比筛击杀了谁？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_2sam21:761c:open | 在迦特的这四个拉法的后裔，被谁杀死了？ | REVIEW | PASS / REWRITE | PASS / PASS |
| hard:t1_2sam21:761c:mcq | 在迦特的这四个拉法的后裔，被谁杀死了？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts19:7628:open | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_acts19:7628:mcq | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_acts19:9b0c:open | 行邪术的人把书拿出来以后，接着做了什么？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts19:9b0c:mcq | 行邪术的人把书拿出来以后，接着做了什么？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts20:f988:open | 保罗为什么一直讲到午夜？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts20:f988:mcq | 保罗为什么一直讲到午夜？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts20:9b52:open | 保罗离开之前，最后做的是什么？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts20:9b52:mcq | 保罗离开之前，最后做的是什么？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts23:a1ba:open | 他们要请谁把保罗带到公会那里？ | REVIEW | PASS / REWRITE | PASS / PASS |
| hard:t1_acts23:a1ba:mcq | 他们要请谁把保罗带到公会那里？ | REVIEW | PASS / REWRITE | PASS / PASS |
| hard:t1_acts23:f57c:open | 按保罗的话，谁有话要告诉军长？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts23:f57c:mcq | 按保罗的话，谁有话要告诉军长？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts23:5613:open | 埋伏的人动手之前，还在等什么？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts23:5613:mcq | 埋伏的人动手之前，还在等什么？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts23:2b9c:open | 军长吩咐谁去预备护送的队伍？ | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_acts23:2b9c:mcq | 军长吩咐谁去预备护送的队伍？ | HOLD_CONTENT | PASS / PASS | HOLD / HOLD |
| hard:t1_acts23:9035:open | 这封信是谁写的？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts23:9035:mcq | 这封信是谁写的？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts23:058f:open | 第二天谁回到了兵营？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_acts23:058f:mcq | 第二天谁回到了兵营？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:9f00:open | 谁咒诅了被偷的银子？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:9f00:mcq | 谁咒诅了被偷的银子？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:7713:open | 但支派的人为什么要寻找地业居住？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:7713:mcq | 但支派的人为什么要寻找地业居住？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:725d:open | 他们请谁为他们求问这趟行程？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_judg17_18:725d:mcq | 他们请谁为他们求问这趟行程？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_judg17_18:c60a:open | 那少年利未人为什么离开伯利恒？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:c60a:mcq | 那少年利未人为什么离开伯利恒？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:1654:open | 来士的人为什么富足？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:1654:mcq | 来士的人为什么富足？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:1fd1:open | 米迦为什么认为耶和华必向他施恩？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:1fd1:mcq | 米迦为什么认为耶和华必向他施恩？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:c2d9:open | 谁进去拿走了雕像、以弗得、家用神像和熔铸的偶像？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:c2d9:mcq | 谁进去拿走了雕像、以弗得、家用神像和熔铸的偶像？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_judg17_18:3162:open | 那些神像最先发生了什么事？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_judg17_18:3162:mcq | 那些神像最先发生了什么事？ | REVIEW | REWRITE / PASS | PASS / PASS |
| hard:t1_judg17_18:616b:open | 是什么使但人转过身来？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:616b:mcq | 是什么使但人转过身来？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:3250:open | 为什么没有人搭救来士的人？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg17_18:3250:mcq | 为什么没有人搭救来士的人？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_judg17_18:97e8:open | 约拿单和他的子孙作但支派的祭司，直到什么时候？ | REVIEW | PASS / PASS | PASS / HOLD |
| hard:t1_judg17_18:97e8:mcq | 约拿单和他的子孙作但支派的祭司，直到什么时候？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_judg9:c232:open | 亚比米勒请谁把他的话转告示剑的众首领？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:c232:mcq | 亚比米勒请谁把他的话转告示剑的众首领？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:6d68:open | 约坦呼叫示剑的众首领听他的话，是为了什么结果？ | HOLD_CONTENT | REWRITE / REWRITE | HOLD / HOLD |
| hard:t1_judg9:6d68:mcq | 约坦呼叫示剑的众首领听他的话，是为了什么结果？ | HOLD_CONTENT | REWRITE / REWRITE | HOLD / HOLD |
| hard:t1_judg9:8e0b:open | 橄榄树为什么不肯去作树木的王？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:8e0b:mcq | 橄榄树为什么不肯去作树木的王？ | REVIEW | REWRITE / REVIEW | PASS / PASS |
| hard:t1_judg9:c5c7:open | 众人在做什么的时候咒诅亚比米勒？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:c5c7:mcq | 众人在做什么的时候咒诅亚比米勒？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:1246:open | 谁暗暗打发人去见亚比米勒？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:1246:mcq | 谁暗暗打发人去见亚比米勒？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:f36a:open | 迦勒第一次说有人来时，西布说他看见的其实是什么？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_judg9:f36a:mcq | 迦勒第一次说有人来时，西布说他看见的其实是什么？ | REWRITE | REWRITE / REWRITE | PASS / PASS |
| hard:t1_judg9:e935:open | 亚比米勒听到什么消息后设下埋伏？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:e935:mcq | 亚比米勒听到什么消息后设下埋伏？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:79d0:open | 城楼上的人是怎么死的？ | REVIEW | PASS / PASS | PASS / HOLD |
| hard:t1_judg9:79d0:mcq | 城楼上的人是怎么死的？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:0bd2:open | 亚比米勒来到楼门，是要做什么？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:0bd2:mcq | 亚比米勒来到楼门，是要做什么？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:a602:open | 谁被他的甲士刺死了？ | KEEP | PASS / PASS | PASS / PASS |
| hard:t1_judg9:a602:mcq | 谁被他的甲士刺死了？ | REVIEW | PASS / REVIEW | PASS / PASS |

Full evidence for every stage and both passes: [Gold](gold/report.md), [Hard](hard/report.md). Exact windows and input hashes: [provenance](provenance.json). Machine-readable queue: [revision_queue.json](revision_queue.json).
