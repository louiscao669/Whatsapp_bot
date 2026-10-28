# Targeted rewrite results: Gold72 and Hard66

Run scope: 35 consistently flagged question forms, representing 21 unique question IDs. Open and multiple-choice versions were reviewed separately. Gold questions are in English; Hard questions are in Chinese.

Writer and reviewer: gpt-6.1-sol. Each accepted revision passed two preservation checks and two complete content, structural, and wording-burden reviews. At most two rewrite proposals were allowed per form. Acceptance here is a model-screening result, not human validation.

| Dataset | Selected forms | Accepted | Declined | Unresolved | Execution errors |
|---|---:|---:|---:|---:|---:|
| Gold72 | 11 | 6 | 5 | 0 | 0 |
| Hard66 | 24 | 22 | 2 | 0 | 0 |

Accepted changes: 24 forms with revised question wording; 4 forms with changes only to the choices. Answers, answer keys, passage windows, and option labels are unchanged. The original datasets were not overwritten.

## Accepted Gold72 revisions

| Question ID | Form | Before | Accepted wording |
|---|---|---|---|
| t1_1kgs13:o8ae | open | What becomes sin to Jeroboam's family? | What action was counted as a sin for Jeroboam's family? |
| t1_1kgs13:o8ae | mcq | What becomes sin to Jeroboam's family? | What action is described as the sin of Jeroboam's family? |
| t1_2kgs11:otua | open | What did non-serving groups do on the Sabbath? | What were the two divisions going off duty on the Sabbath commanded to do? |
| t1_2kgs11:otua | mcq | What did non-serving groups do on the Sabbath? | What were the two divisions going off duty on the Sabbath commanded to do? |
| t1_2kgs6_7:pb1x | open | What did the captain say to Elisha's prophecy? | What did the officer say in response to Elisha's prophecy? |
| t1_2kgs6_7:pb1x | mcq | What does the captain say to Elisha's prophecy? | What does the officer say in response to Elisha's prophecy? |

## Accepted Hard66 revisions

| Question ID | Form | Before | Accepted wording |
|---|---|---|---|
| t1_1kgs13:ec63 | open | 带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？ | 一起吃饭时，先知宣告谁的尸首必定不能葬在自己的祖坟里？ |
| t1_1kgs13:ec63 | mcq | 带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？ | 坐席时，先知宣告谁的尸首必定不能葬在自己的祖坟里？ |
| t1_1kgs13:2f00 | open | 带他回来的先知先把神人的尸首带到哪里？ | 先知在路上找到神人的尸首后，先把尸首带到哪里？ |
| t1_1kgs13:2f00 | mcq | 带他回来的先知先把神人的尸首带到哪里？ | 先知找到神人的尸首后，先把尸首带到哪里？ |
| t1_2chr26:9aab | open | 犹大全体百姓立乌西雅，是为了什么？ | 犹大全体百姓拥立乌西雅的目的是什么？ |
| t1_2chr26:1cab | mcq | 神帮助乌西雅攻打哪些人？ | 神帮助乌西雅攻打哪些人？ [question unchanged; choices revised] |
| t1_2chr26:1fc4 | open | 谁爱好土地，所以设立了农夫和葡萄园工人？ | 谁喜爱土地，因此安排了农夫和葡萄园工人？ |
| t1_2chr26:1fc4 | mcq | 谁爱好土地，所以设立了农夫和葡萄园工人？ | 谁因为喜爱土地而安排了农夫和葡萄园工人？ |
| t1_2chr26:723e | open | 这三十万七千五百训练有素的军队由谁统领？ | 这三十万七千五百名训练有素的士兵由谁统领？ |
| t1_2chr26:723e | mcq | 这三十万七千五百训练有素的军队由谁统领？ | 这三十万七千五百名训练有素的士兵由谁统领？ |
| t1_2kgs11:f49c | open | 耶何耶大立的第一个约，是在哪些之间立的？ | 耶何耶大第一次是与谁立约的？ |
| t1_2kgs11:f49c | mcq | 耶何耶大立的第一个约，是在哪些之间立的？ | 第一次立约时，耶何耶大是与谁立约的？ |
| t1_acts19:7628 | open | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | 那个被邪灵附身的人制服了一些人。这些人随后带伤逃出了那房子，他们是谁？ |
| t1_acts19:7628 | mcq | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | 谁被那个邪灵附身的人制服，随后受伤逃出了那房子？ |
| t1_judg17_18:725d | open | 他们请谁为他们求问这趟行程？ | 他们请谁为他们求问神，看看这趟行程是否顺利？ |
| t1_judg17_18:725d | mcq | 他们请谁为他们求问这趟行程？ | 他们请谁替他们求问神，看看这趟行程是否顺利？ |
| t1_judg17_18:c2d9 | mcq | 谁进去拿走了雕像、以弗得、家用神像和熔铸的偶像？ | 谁进去拿走了雕像、以弗得、家用神像和熔铸的偶像？ [question unchanged; choices revised] |
| t1_judg17_18:3162 | open | 那些神像最先发生了什么事？ | 经文中，人们最先对那些神像做了什么？ |
| t1_judg17_18:3250 | mcq | 为什么没有人搭救来士的人？ | 为什么没有人搭救来士的人？ [question unchanged; choices revised] |
| t1_judg17_18:97e8 | mcq | 约拿单和他的子孙作但支派的祭司，直到什么时候？ | 约拿单和他的子孙作但支派的祭司，直到什么时候？ [question unchanged; choices revised] |
| t1_judg9:f36a | open | 迦勒第一次说有人来时，西布说他看见的其实是什么？ | 迦勒第一次说有人来时，西布说迦勒看见的其实是什么？ |
| t1_judg9:f36a | mcq | 迦勒第一次说有人来时，西布说他看见的其实是什么？ | 迦勒第一次说有人来时，西布说迦勒看见的其实是什么？ |

## Revised choices

### gold:t1_1kgs13:o8ae:mcq

- **C, before:** Consecrating anyone as priests.
- **C, accepted:** Consecrating anyone as a priest.

### gold:t1_2kgs6_7:pb1x:mcq

- **B, before:** Impossible even if Yahweh helped
- **B, accepted:** It would be impossible even if the LORD helped

### hard:t1_2chr26:1cab:mcq

- **A, before:** 亚扪人、住在姑珥巴力的阿拉伯人和米乌尼人
- **A, accepted:** • 亚扪人<br>• 阿拉伯人（住在姑珥巴力）<br>• 米乌尼人
- **B, before:** 非利士人、住在亚实突的阿拉伯人和亚扪人
- **B, accepted:** • 非利士人<br>• 阿拉伯人（住在亚实突）<br>• 亚扪人
- **C, before:** 摩押人、住在埃及边界的亚玛力人和亚扪人
- **C, accepted:** • 摩押人<br>• 亚玛力人（住在埃及边界）<br>• 亚扪人
- **D, before:** 非利士人、住在姑珥巴力的阿拉伯人和米乌尼人
- **D, accepted:** • 非利士人<br>• 阿拉伯人（住在姑珥巴力）<br>• 米乌尼人

### hard:t1_acts19:7628:mcq

- **A, before:** 那附着邪灵的人
- **A, accepted:** 那个邪灵附身的人

### hard:t1_judg17_18:c2d9:mcq

- **C, before:** 那五个窥探地的人
- **C, accepted:** 那五个曾去侦察那片土地的人

### hard:t1_judg17_18:3250:mcq

- **B, before:** 因为他们夺了米迦的偶像和祭司
- **B, accepted:** 因为但人夺了米迦的偶像和祭司

### hard:t1_judg17_18:97e8:mcq

- **D, before:** 神的殿在示罗多少日子，就到多少日子。
- **D, accepted:** 直到神的殿不再设在示罗。

## Forms without an accepted revision

### gold:t1_2chr26:tglh:open — DECLINED

How did Uzziah follow his father's example with Yahweh?

The awkward phrase “with Yahweh” could be clarified, but wording alone cannot resolve the answer-support problem. The passage explicitly compares Uzziah’s doing right with his father’s conduct; it does not say that seeking God also followed his father’s example. Preserving both the father–son comparison and the fixed answer “Did right and sought God” would retain that unsupported relationship.

### gold:t1_2chr26:tglh:mcq — DECLINED

How does Uzziah follow his father's example with Yahweh?

The awkward phrase “with Yahweh” could be reworded, but wording alone cannot resolve the answer-support problem. The passage links doing right to Uzziah’s father’s example, but does not link seeking God to that example. Preserving both the father–son comparison and the fixed two-part answer would retain this unsupported relationship. Fixing it would require changing the question’s scope, the keyed answer, or the supplied passage.

### gold:t1_acts20:jxkk#2:open — DECLINED

What happens after Paul stretches on the young man?

“Stretches on” could be replaced with “throws himself on,” but that would not resolve the reported answer-support concern. Although the young man is described as dead, Paul says he is “still alive,” leaving revival versus continued life uncertain. Wording alone cannot make the fixed answer, “He comes back to life,” unambiguous without changing the tested fact or the supplied passage.

### gold:t1_acts23:xj40:open — DECLINED

How did captain respond to the plan?

Adding “the” before “captain” would fix the grammatical omission, but the supplied passage neither identifies the captain nor describes the plan prompting his response. Resolving those context gaps would require expanding the fixed passage or changing the question’s intended relation, not merely revising its wording.

### gold:t1_acts23:xj40:mcq — DECLINED

How did captain respond to the plan?

The missing determiners in “did captain” and “Ordered guard” can be corrected, but wording changes cannot resolve the reported context problem. The supplied passage neither identifies the captain nor mentions the plan, so it does not establish that the protective orders were his response to that plan. Preserving this required relationship would require additional passage context; removing it would change the question. With the window and key fixed, D cannot be established uniquely over E.

### hard:t1_judg9:6d68:open — DECLINED

约坦呼叫示剑的众首领听他的话，是为了什么结果？

“呼叫……听他的话”和“是为了什么结果”的搭配确实生硬，但问题还涉及无法仅靠措辞解决的内容障碍：经文表达的是约坦要求众首领听他的话，并祝愿神也听他们的话，并未明确将后者作为前者的目的或结果。保留原题及固定答案的目的关系，会继续存在依据不足的问题；改问约坦表达了什么祝愿，则会改变原题所考查的关系，因此不能仅通过文字修订解决。

### hard:t1_judg9:6d68:mcq — DECLINED

约坦呼叫示剑的众首领听他的话，是为了什么结果？

“呼叫……听他的话”和“是为了什么结果”的搭配确实生硬，但本题还有无法仅靠措辞解决的内容问题：经文表达的是“愿神也听你们的话”这一祝愿，并未确立它是约坦呼吁众首领听话的目的或结果。若改问约坦表达了什么祝愿，会改变原题所考查的目的关系；若保留该关系，固定答案D仍缺乏经文支持，且E仍可成立。因此，在不能更改考查关系、答案或经文窗口的限制下，无法作出合规修订。

## Verification and detailed records

All 42 source file hashes still match the baseline. Every accepted record has two complete passing reviews, and fixed metadata and option-label order were verified.

One model request timed out during the initial run. Its error result is preserved in execution_recovery/. The identical run was resumed from cached responses; prompts, thresholds, models, and completed quality judgments were unchanged.

- accepted_cases.json: accepted normalized QA records only.
- report.md: every attempt, option, and review explanation.
- results.json: complete machine-readable audit.
- verification.json: counts and integrity checks.
