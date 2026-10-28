# Targeted QA rewrite results

Accepted means all model preservation, content, structure and burden checks passed in every repeat. It is not a human validation result. Original datasets were not edited.

| Item | Status |
|---|---|
| gold:t1_1kgs13:o8ae:open | ACCEPTED |
| gold:t1_1kgs13:o8ae:mcq | ACCEPTED |
| gold:t1_2chr26:tglh:open | DECLINED |
| gold:t1_2chr26:tglh:mcq | DECLINED |
| gold:t1_2kgs11:otua:open | ACCEPTED |
| gold:t1_2kgs11:otua:mcq | ACCEPTED |
| gold:t1_2kgs6_7:pb1x:open | ACCEPTED |
| gold:t1_2kgs6_7:pb1x:mcq | ACCEPTED |
| gold:t1_acts20:jxkk#2:open | DECLINED |
| gold:t1_acts23:xj40:open | DECLINED |
| gold:t1_acts23:xj40:mcq | DECLINED |
| hard:t1_1kgs13:ec63:open | ACCEPTED |
| hard:t1_1kgs13:ec63:mcq | ACCEPTED |
| hard:t1_1kgs13:2f00:open | ACCEPTED |
| hard:t1_1kgs13:2f00:mcq | ACCEPTED |
| hard:t1_2chr26:9aab:open | ACCEPTED |
| hard:t1_2chr26:1cab:mcq | ACCEPTED |
| hard:t1_2chr26:1fc4:open | ACCEPTED |
| hard:t1_2chr26:1fc4:mcq | ACCEPTED |
| hard:t1_2chr26:723e:open | ACCEPTED |
| hard:t1_2chr26:723e:mcq | ACCEPTED |
| hard:t1_2kgs11:f49c:open | ACCEPTED |
| hard:t1_2kgs11:f49c:mcq | ACCEPTED |
| hard:t1_acts19:7628:open | ACCEPTED |
| hard:t1_acts19:7628:mcq | ACCEPTED |
| hard:t1_judg17_18:725d:open | ACCEPTED |
| hard:t1_judg17_18:725d:mcq | ACCEPTED |
| hard:t1_judg17_18:c2d9:mcq | ACCEPTED |
| hard:t1_judg17_18:3162:open | ACCEPTED |
| hard:t1_judg17_18:3250:mcq | ACCEPTED |
| hard:t1_judg17_18:97e8:mcq | ACCEPTED |
| hard:t1_judg9:6d68:open | DECLINED |
| hard:t1_judg9:6d68:mcq | DECLINED |
| hard:t1_judg9:f36a:open | ACCEPTED |
| hard:t1_judg9:f36a:mcq | ACCEPTED |

## gold:t1_1kgs13:o8ae:open

Original: What becomes sin to Jeroboam's family?


Accepted wording: What action was counted as a sin for Jeroboam's family?


Replaces the unnatural and ambiguous phrase “becomes sin to” with “was counted as a sin for,” clearly asking which action constituted the family's sin.

## gold:t1_1kgs13:o8ae:mcq

Original: What becomes sin to Jeroboam's family?

- A. Building a new altar.
- B. Worshiping false gods.
- C. Consecrating anyone as priests.
- D. Ignoring the prophet's warning.
- E. I can't tell from this passage

Accepted wording: What action is described as the sin of Jeroboam's family?

- A. Building a new altar.
- B. Worshiping false gods.
- C. Consecrating anyone as a priest.
- D. Ignoring the prophet's warning.
- E. I can't tell from this passage

Replaced the unnatural phrase “becomes sin to” with clear wording that asks which action is attributed as the family's sin. Changed “anyone as priests” to “anyone as a priest” to fix the singular–plural mismatch while preserving unrestricted appointment.

## gold:t1_2chr26:tglh:open

Original: How did Uzziah follow his father's example with Yahweh?


The awkward phrase “with Yahweh” could be clarified, but wording alone cannot resolve the answer-support problem. The passage explicitly compares Uzziah’s doing right with his father’s conduct; it does not say that seeking God also followed his father’s example. Preserving both the father–son comparison and the fixed answer “Did right and sought God” would retain that unsupported relationship.

## gold:t1_2chr26:tglh:mcq

Original: How does Uzziah follow his father's example with Yahweh?

- A. Worshipped other gods
- B. Ignored God's laws
- C. Built idols
- D. Did right and sought God
- E. I can't tell from this passage

The awkward phrase “with Yahweh” could be reworded, but wording alone cannot resolve the answer-support problem. The passage links doing right to Uzziah’s father’s example, but does not link seeking God to that example. Preserving both the father–son comparison and the fixed two-part answer would retain this unsupported relationship. Fixing it would require changing the question’s scope, the keyed answer, or the supplied passage.

## gold:t1_2kgs11:otua:open

Original: What did non-serving groups do on the Sabbath?


Accepted wording: What were the two divisions going off duty on the Sabbath commanded to do?


Replaces the misleading label “non-serving groups” with the passage’s clear duty-transition description. Asking what they were commanded to do also matches the passage’s assignment rather than implying that it reports the command being carried out.

## gold:t1_2kgs11:otua:mcq

Original: What did non-serving groups do on the Sabbath?

- A. Guard the house of Yahweh
- B. Visit the market
- C. Attend a feast
- D. Rest at home
- E. I can't tell from this passage

Accepted wording: What were the two divisions going off duty on the Sabbath commanded to do?

- A. Guard the house of Yahweh
- B. Visit the market
- C. Attend a feast
- D. Rest at home
- E. I can't tell from this passage

Replaces the misleading label “non-serving groups” with the passage’s clear description, “two divisions going off duty.” Asking what they were commanded to do preserves the intended assignment question without implying that the passage reports their carrying it out.

## gold:t1_2kgs6_7:pb1x:open

Original: What did the captain say to Elisha's prophecy?


Accepted wording: What did the officer say in response to Elisha's prophecy?


Replaces the unnatural “say to ... prophecy” with “say in response to” and uses the passage’s label “officer” instead of “captain,” while preserving the requested response and its connection to Elisha’s prophecy.

## gold:t1_2kgs6_7:pb1x:mcq

Original: What does the captain say to Elisha's prophecy?

- A. It will happen soon
- B. Impossible even if Yahweh helped
- C. We must prepare
- D. The people will rejoice
- E. I can't tell from this passage

Accepted wording: What does the officer say in response to Elisha's prophecy?

- A. It will happen soon
- B. It would be impossible even if the LORD helped
- C. We must prepare
- D. The people will rejoice
- E. I can't tell from this passage

Makes the response relationship explicit and turns the compressed wording in B into a complete sentence. Uses “officer” and “the LORD” to match the passage, removing the terminology shifts noted in the previous reviews while preserving all option meanings.

## gold:t1_acts20:jxkk#2:open

Original: What happens after Paul stretches on the young man?


“Stretches on” could be replaced with “throws himself on,” but that would not resolve the reported answer-support concern. Although the young man is described as dead, Paul says he is “still alive,” leaving revival versus continued life uncertain. Wording alone cannot make the fixed answer, “He comes back to life,” unambiguous without changing the tested fact or the supplied passage.

## gold:t1_acts23:xj40:open

Original: How did captain respond to the plan?


Adding “the” before “captain” would fix the grammatical omission, but the supplied passage neither identifies the captain nor describes the plan prompting his response. Resolving those context gaps would require expanding the fixed passage or changing the question’s intended relation, not merely revising its wording.

## gold:t1_acts23:xj40:mcq

Original: How did captain respond to the plan?

- A. Dismissed the young man without acting.
- B. Ordered Paul returned to the council.
- C. Released Paul without an escort.
- D. Ordered guard to protect Paul.
- E. I can't tell from this passage

The missing determiners in “did captain” and “Ordered guard” can be corrected, but wording changes cannot resolve the reported context problem. The supplied passage neither identifies the captain nor mentions the plan, so it does not establish that the protective orders were his response to that plan. Preserving this required relationship would require additional passage context; removing it would change the question. With the window and key fixed, D cannot be established uniquely over E.

## hard:t1_1kgs13:ec63:open

Original: 带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？


Accepted wording: 一起吃饭时，先知宣告谁的尸首必定不能葬在自己的祖坟里？


用吃饭的场景定位宣告，避免“带他回来”中所指未明的代词；将“必不得入他列祖的坟墓”改为更自然的现代汉语，并用“自己的祖坟”明确领属关系，保留宣告者与宣告对象的区别及确定的否定结果。

## hard:t1_1kgs13:ec63:mcq

Original: 带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？

- A. 耶罗波安
- B. 带他回来的先知
- C. 他的列祖
- D. 从犹大来的神人
- E. 根据这段文字无法判断

Accepted wording: 坐席时，先知宣告谁的尸首必定不能葬在自己的祖坟里？

- A. 耶罗波安
- B. 带他回来的先知
- C. 他的列祖
- D. 从犹大来的神人
- E. 根据这段文字无法判断

用“坐席时”定位宣告事件，避免题干开头“带他回来”中指代未明的“他”；用“自己的祖坟”明确坟墓属于所问人物，并将“必不得入”改为更自然的“必定不能葬在”。保留宣告者与受宣告者的区别、否定结果及全部选项原意。

## hard:t1_1kgs13:2f00:open

Original: 带他回来的先知先把神人的尸首带到哪里？


Accepted wording: 先知在路上找到神人的尸首后，先把尸首带到哪里？


用找到尸首的事件定位所问情节，去掉“带他回来的”这一涉及另一次带回事件的修饰语，避免前置代词和相似事件造成的理解负担；保留先知、神人的尸首及首个目的地的关系。

## hard:t1_1kgs13:2f00:mcq

Original: 带他回来的先知先把神人的尸首带到哪里？

- A. 到自己的坟墓。
- B. 回到自己的城里。
- C. 到王宫。
- D. 到坛那里。
- E. 根据这段文字无法判断

Accepted wording: 先知找到神人的尸首后，先把尸首带到哪里？

- A. 到自己的坟墓。
- B. 回到自己的城里。
- C. 到王宫。
- D. 到坛那里。
- E. 根据这段文字无法判断

用找到尸首这一当前事件作简短定位，去掉“带他回来的”引入的较早事件和前置代词，避免两次“带回”相混淆。保留“先”，仍询问尸首先被带到的地点，并保留全部选项的原意。

## hard:t1_2chr26:9aab:open

Original: 犹大全体百姓立乌西雅，是为了什么？


Accepted wording: 犹大全体百姓拥立乌西雅的目的是什么？


将单独使用时显得未说完整的“立乌西雅”改为更自然的“拥立乌西雅”，减少读者补足动作含义的负担；保留行动双方及对目的的询问，不提前透露接替谁作王。

## hard:t1_2chr26:1cab:mcq

Original: 神帮助乌西雅攻打哪些人？

- A. 亚扪人、住在姑珥巴力的阿拉伯人和米乌尼人
- B. 非利士人、住在亚实突的阿拉伯人和亚扪人
- C. 摩押人、住在埃及边界的亚玛力人和亚扪人
- D. 非利士人、住在姑珥巴力的阿拉伯人和米乌尼人
- E. 根据这段文字无法判断

Accepted wording: 神帮助乌西雅攻打哪些人？

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

保留自然、简明的题干。将各名单统一为每行一个群体，并把居住地紧随对应族名放在括号中，便于按相同位置核对族名和地点，减少在近似长列表中反复回扫的负担。所有选项的群体、地点限定及原有含义均保留。

## hard:t1_2chr26:1fc4:open

Original: 谁爱好土地，所以设立了农夫和葡萄园工人？


Accepted wording: 谁喜爱土地，因此安排了农夫和葡萄园工人？


将搭配生硬的“爱好土地”改为“喜爱土地”，将不适合直接搭配人员的“设立”改为“安排”，保留人物识别目标及喜爱土地与安排人员之间的因果关系。

## hard:t1_2chr26:1fc4:mcq

Original: 谁爱好土地，所以设立了农夫和葡萄园工人？

- A. 葡萄园工人
- B. 约坦
- C. 乌西雅
- D. 田野中的农夫
- E. 根据这段文字无法判断

Accepted wording: 谁因为喜爱土地而安排了农夫和葡萄园工人？

- A. 葡萄园工人
- B. 约坦
- C. 乌西雅
- D. 田野中的农夫
- E. 根据这段文字无法判断

将搭配生硬的“爱好土地”和“设立了农夫和葡萄园工人”改为“喜爱土地”和“安排了农夫和葡萄园工人”，保留所问人物、因果关系及两类工作人员，使表达更自然。

## hard:t1_2chr26:723e:open

Original: 这三十万七千五百训练有素的军队由谁统领？


Accepted wording: 这三十万七千五百名训练有素的士兵由谁统领？


将数量短语改为“三十万七千五百名训练有素的士兵”，明确数字表示士兵人数，而非军队数量，消除量词缺失和数量修饰关系不清造成的理解负担，同时保留人数、训练情况和所问的统领关系。

## hard:t1_2chr26:723e:mcq

Original: 这三十万七千五百训练有素的军队由谁统领？

- A. 哈拿尼雅
- B. 耶列和玛西亚
- C. 乌西雅
- D. 那二千六百个家族首领
- E. 根据这段文字无法判断

Accepted wording: 这三十万七千五百名训练有素的士兵由谁统领？

- A. 哈拿尼雅
- B. 耶列和玛西亚
- C. 乌西雅
- D. 那二千六百个家族首领
- E. 根据这段文字无法判断

将人数后的中心语改为“名训练有素的士兵”，明确数字计量的是士兵而非军队，消除数量搭配不当造成的理解负担；保留人数、训练状态及所问的统领关系，选项不变。

## hard:t1_2kgs11:f49c:open

Original: 耶何耶大立的第一个约，是在哪些之间立的？


Accepted wording: 耶何耶大第一次是与谁立约的？


将不完整的“在哪些之间”改为自然的“与谁”，明确询问与耶何耶大立约的其他各方，消除是否应将耶何耶大列入答案的歧义。保留“第一次”以区分两次立约，并减少“立的……立的”的重复。

## hard:t1_2kgs11:f49c:mcq

Original: 耶何耶大立的第一个约，是在哪些之间立的？

- A. 耶和华、王和百姓
- B. 王和百夫长
- C. 耶和华和守卫
- D. 王和百姓
- E. 根据这段文字无法判断

Accepted wording: 第一次立约时，耶何耶大是与谁立约的？

- A. 耶和华、王和百姓
- B. 王和百夫长
- C. 耶和华和守卫
- D. 王和百姓
- E. 根据这段文字无法判断

将生硬的“在哪些之间”改为自然的“与谁立约”，保留第一次立约的事件限定。明确询问与耶何耶大立约的其他各方，而非所有参与者，解决原问法与答案名单范围不一致的问题；不将耶何耶大改作仅仅居间立约的人。

## hard:t1_acts19:7628:open

Original: 被那附着邪灵的人制服以后，谁受伤逃出了那房子？


Accepted wording: 那个被邪灵附身的人制服了一些人。这些人随后带伤逃出了那房子，他们是谁？


用“被邪灵附身的人”明确人与邪灵的关系，并以主动句交代制服事件，避免先前“谁被那个邪灵附身……”造成的切分歧义。保留被制服者随后受伤逃出房子的事件关系，再询问其身份。

## hard:t1_acts19:7628:mcq

Original: 被那附着邪灵的人制服以后，谁受伤逃出了那房子？

- A. 那附着邪灵的人
- B. 保罗
- C. 以弗所的希腊人
- D. 士基瓦的七个儿子
- E. 根据这段文字无法判断

Accepted wording: 谁被那个邪灵附身的人制服，随后受伤逃出了那房子？

- A. 那个邪灵附身的人
- B. 保罗
- C. 以弗所的希腊人
- D. 士基瓦的七个儿子
- E. 根据这段文字无法判断

将“谁”提前，明确被制服者也是随后受伤逃出的人；用自然的“邪灵附身的人”说明人物身份，修正原来的附着关系表达，并避免上一版双层“被”字结构的嵌套。保留了制服、受伤逃出及其先后关系，选项A同步调整措辞。

## hard:t1_judg17_18:725d:open

Original: 他们请谁为他们求问这趟行程？


Accepted wording: 他们请谁为他们求问神，看看这趟行程是否顺利？


将生硬的“求问这趟行程”改为“求问神，看看这趟行程是否顺利”，明确求问的对象和内容，同时保留请求者、代为求问者及行程之间的关系。

## hard:t1_judg17_18:725d:mcq

Original: 他们请谁为他们求问这趟行程？

- A. 神
- B. 米迦的母亲
- C. 米迦
- D. 祭司
- E. 根据这段文字无法判断

Accepted wording: 他们请谁替他们求问神，看看这趟行程是否顺利？

- A. 神
- B. 米迦的母亲
- C. 米迦
- D. 祭司
- E. 根据这段文字无法判断

将生硬的“求问这趟行程”改为“求问神，看看这趟行程是否顺利”，明确求问的对象和事项，保留请求者、代为求问者及行程之间的关系，减少读者自行补足语义的负担。

## hard:t1_judg17_18:c2d9:mcq

Original: 谁进去拿走了雕像、以弗得、家用神像和熔铸的偶像？

- A. 六百带兵器的但人
- B. 那少年利未人
- C. 那五个窥探地的人
- D. 米迦和他的家人
- E. 根据这段文字无法判断

Accepted wording: 谁进去拿走了雕像、以弗得、家用神像和熔铸的偶像？

- A. 六百带兵器的但人
- B. 那少年利未人
- C. 那五个曾去侦察那片土地的人
- D. 米迦和他的家人
- E. 根据这段文字无法判断

将选项C中不自然且容易产生词性歧义的“窥探地”改为“曾去侦察那片土地”，明确侦察的对象，保留人数、人物身份及原有含义。题干的连续动作和四项物品均予以保留。

## hard:t1_judg17_18:3162:open

Original: 那些神像最先发生了什么事？


Accepted wording: 经文中，人们最先对那些神像做了什么？


将生硬的“神像发生了什么事”改为“人们对神像做了什么”，明确神像是动作的承受对象，减少读者修补主谓关系的负担；保留对神像的回指及“最先”的事件顺序要求。

## hard:t1_judg17_18:3250:mcq

Original: 为什么没有人搭救来士的人？

- A. 因为那城远离西顿，也没有与人结盟。
- B. 因为他们夺了米迦的偶像和祭司
- C. 因为但人用刀杀灭他们
- D. 因为但人重建城邑，在那里居住
- E. 根据这段文字无法判断

Accepted wording: 为什么没有人搭救来士的人？

- A. 因为那城远离西顿，也没有与人结盟。
- B. 因为但人夺了米迦的偶像和祭司
- C. 因为但人用刀杀灭他们
- D. 因为但人重建城邑，在那里居住
- E. 根据这段文字无法判断

将选项B中的“他们”明确为“但人”，避免读者误将其理解为题干中的来士居民，减少回查和修正指代的负担。其余内容保持不变。

## hard:t1_judg17_18:97e8:mcq

Original: 约拿单和他的子孙作但支派的祭司，直到什么时候？

- A. 直到被掳之日。
- B. 直到他们给城起名叫但。
- C. 直到但人为自己立偶像。
- D. 神的殿在示罗多少日子，就到多少日子。
- E. 根据这段文字无法判断

Accepted wording: 约拿单和他的子孙作但支派的祭司，直到什么时候？

- A. 直到被掳之日。
- B. 直到他们给城起名叫但。
- C. 直到但人为自己立偶像。
- D. 直到神的殿不再设在示罗。
- E. 根据这段文字无法判断

仅修改D，将生硬的“多少日子，就到多少日子”改为明确的时间终点表达，保留任职持续到神的殿不再设在示罗这一时间关系，避免读者自行补足并转换时长与终点。

## hard:t1_judg9:6d68:open

Original: 约坦呼叫示剑的众首领听他的话，是为了什么结果？


“呼叫……听他的话”和“是为了什么结果”的搭配确实生硬，但问题还涉及无法仅靠措辞解决的内容障碍：经文表达的是约坦要求众首领听他的话，并祝愿神也听他们的话，并未明确将后者作为前者的目的或结果。保留原题及固定答案的目的关系，会继续存在依据不足的问题；改问约坦表达了什么祝愿，则会改变原题所考查的关系，因此不能仅通过文字修订解决。

## hard:t1_judg9:6d68:mcq

Original: 约坦呼叫示剑的众首领听他的话，是为了什么结果？

- A. 为自己膏立一个王。
- B. 召集他们赴宴。
- C. 警告他们有危险。
- D. 使神也听他们的话。
- E. 根据这段文字无法判断

“呼叫……听他的话”和“是为了什么结果”的搭配确实生硬，但本题还有无法仅靠措辞解决的内容问题：经文表达的是“愿神也听你们的话”这一祝愿，并未确立它是约坦呼吁众首领听话的目的或结果。若改问约坦表达了什么祝愿，会改变原题所考查的目的关系；若保留该关系，固定答案D仍缺乏经文支持，且E仍可成立。因此，在不能更改考查关系、答案或经文窗口的限制下，无法作出合规修订。

## hard:t1_judg9:f36a:open

Original: 迦勒第一次说有人来时，西布说他看见的其实是什么？


Accepted wording: 迦勒第一次说有人来时，西布说迦勒看见的其实是什么？


将“他”改为“迦勒”，明确看见者，避免误将代词理解为西布；保留“第一次”的场次限定和西布作为解释者的角色。

## hard:t1_judg9:f36a:mcq

Original: 迦勒第一次说有人来时，西布说他看见的其实是什么？

- A. 伪装的士兵。
- B. 山上的影子，不是人。
- C. 从山上下来的人。
- D. 树林里的野兽。
- E. 根据这段文字无法判断

Accepted wording: 迦勒第一次说有人来时，西布说迦勒看见的其实是什么？

- A. 伪装的士兵。
- B. 山上的影子，不是人。
- C. 从山上下来的人。
- D. 树林里的野兽。
- E. 根据这段文字无法判断

将指代不清的“他”改为“迦勒”，明确西布解释的是迦勒所见的对象，避免读者误将所见者理解为西布。保留“第一次”的时间定位及两人说法之间的关系，选项不变。
