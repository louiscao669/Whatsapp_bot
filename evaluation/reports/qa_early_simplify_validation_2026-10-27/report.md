# Early QA simplification

Model-screened results; original datasets unchanged. Inferred targets remain provisional.

| Item | Status | Before | After |
|---|---|---|---|
| focus:escape:original:inferred | SIMPLIFIED | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | 谁受伤逃出了那房子？ |
| focus:escape:original:explicit | SIMPLIFIED | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | 谁受伤逃出了那房子？ |
| focus:escape:split:inferred | SIMPLIFIED | 那个被邪灵附身的人制服了一些人。这些人随后带伤逃出了那房子，他们是谁？ | 谁带伤逃出了那房子？ |
| focus:escape:split:explicit | SIMPLIFIED | 那个被邪灵附身的人制服了一些人。这些人随后带伤逃出了那房子，他们是谁？ | 谁带伤逃出了那房子？ |
| transfer:handkerchief:original:zh | SIMPLIFIED | 当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？ | 手帕和围裙被带到病人那里时，病人发生了什么变化？ |
| constructed:direct | REVIEW | 是谁把书搬进屋里的？ |  |
| hard:t1_acts20:f988:mcq | KEPT | 保罗为什么一直讲到午夜？ | 保罗为什么一直讲到午夜？ |
| control:escape:required_relation | KEPT | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ |
| control:necessary_time | KEPT | 吃饭前，谁离开了？ | 吃饭前，谁离开了？ |
| control:necessary_event | KEPT | 谁被那个人制服后，受伤逃出了房子？ | 谁被那个人制服后，受伤逃出了房子？ |
| control:direct:en | KEPT | Who left? | Who left? |
| control:unsupported_answer | HOLD_TARGET | 小林为什么离开了？ |  |

## focus:escape:original:inferred

Status: SIMPLIFIED

Target (inferred): 识别这段经文中受伤逃出房子的人是士基瓦的七个儿子。

未提供明确的 intended_target，也未提供更早的原始问答，因此目标为保守推断，并非已获确认的研究设计意图。19:14 将相关人物明确为士基瓦的七个儿子；19:16 以“他们”承接这些人，叙述他们被制服并受伤逃出房子，支持给定答案。

- r1 / removable: 被那附着邪灵的人制服以后 — 这是对所问事件之前经过的叙述，问题并未要求回答事件顺序或制服者的身份。本段只有一次受伤逃出房子的事件，保留该逃离事件即可唯一定位所问人物，无须依赖此前被制服的经过。
- r2 / tested: 谁受伤逃出了那房子 — 这是问题直接要求恢复的人物与事件的对应关系；受伤及逃出房子共同界定所问事件。所需答案是这些人的身份，而不是其受伤原因或逃离时间。

### Proposal 1: SIMPLIFIED

谁受伤逃出了那房子？

删除被制服的前情，保留受伤并逃出房子的事件及人物识别目标。

Verification 1: PASS
- contract_validity: pass — 原题询问受伤逃出房子者的身份，并非询问被制服的原因或事件顺序。经文19:14明确相关人物是士基瓦的七个儿子，19:16叙述他们受伤逃出房子。契约对目标、答案组成及关系角色的判断符合原题和经文。
- same_target: pass — 候选题保留了“谁”“受伤”“逃出了那房子”，仍要求识别同一事件中的人物，完整答案仍为士基瓦的七个儿子。
- removals_justified: pass — 仅删除“被那附着邪灵的人制服以后”这一前情限定。当前经文只有一次受伤逃出房子的事件，删除后没有新增竞争人物或事件，也未删除题目要求回答的关系。
- same_language: pass — 原题和候选题均为中文；没有选项。
- naturalness: 0/3 — “谁受伤逃出了那房子？”是自然、直接的中文问句，“那房子”可由经文中的房子定位。
- processing: 0/3 — 问题结构简短，没有额外前情、嵌套修饰或人物指代链；阅读经文后即可直接确定所问人物。
- context_economy: 0/3 — 候选题没有额外铺陈；“受伤逃出了那房子”直接界定目标事件，未保留可删的制服经过。

Verification 2: PASS
- contract_validity: pass — The original asks who escaped wounded, not why they escaped or who overpowered them. The inferred identity target is valid. Verse 19:14 identifies the participants as Sceva’s seven sons, and 19:16 describes their escape. The preceding overpowering clause functions as an event identifier rather than a separately tested relation.
- same_target: pass — The candidate retains both defining actions, being wounded and escaping the house, and still asks for the people’s identity. It preserves the target and supports the complete expected answer.
- removals_justified: pass — The only removed information is “被那附着邪灵的人制服以后.” The passage contains just one wounded escape from a house, so removing this preceding-event identifier introduces no competing event or answer. No explicit intended target requires testing the sequence or the overpowering relation.
- same_language: pass — Both questions are in Chinese. There are no displayed options.
- naturalness: 0/3 — “谁受伤逃出了那房子？” is idiomatic, direct Chinese. The house reference is readily understood from the passage.
- processing: 0/3 — The question has a straightforward who–action structure without embedded clauses or an added reference chain. Identifying the passage’s participants requires only clear, local reference resolution.
- context_economy: 0/3 — The candidate adds no event narration or identifying setup. The retained wounded-escape description usefully specifies the target event.

## focus:escape:original:explicit

Status: SIMPLIFIED

Target (explicit): Identify the people who escaped from the house injured. The preceding overpowering event is identifying setup, not a separately tested relationship.

19:14将相关人物明确为士基瓦的七个儿子；19:16说明他们受伤逃出房子，支持固定答案。无需在答案中另行复述制服事件，也不要求补充问题未问及的赤身裸体细节。

- r1 / removable: 被那附着邪灵的人制服以后 — 明确目标将先前的制服事件界定为定位背景，而非独立考查的关系。本段只有一次受伤逃出房子的事件，因此保留受伤逃离房子的事件即可唯一定位所问人物，无须依靠这一先前事件。
- r2 / tested: 谁受伤逃出了那房子 — 这是问题直接要求恢复的人物身份；受伤、逃出以及房子共同界定目标事件。答案须识别该群体，不能仅凭同一人物在其他事件中的身份作答。

### Proposal 1: SIMPLIFIED

谁受伤逃出了那房子？

删除先前被制服的背景，保留受伤逃出房子这一目标事件及人物识别要求。

Verification 1: PASS
- contract_validity: pass — 明确目标是识别受伤逃出房子的人，而非考查制服与逃离的先后关系。19:14指出人物是士基瓦的七个儿子，19:16叙述他们受伤逃出房子；合同的答案成分及关系角色与此一致。
- same_target: pass — 候选题保留了“谁”“受伤”“逃出那房子”，完整保留人物识别目标和限定目标事件的条件。
- removals_justified: pass — 仅删除“被那附着邪灵的人制服以后”这一先前事件背景。段落中只有一次受伤逃出房子的事件，删除后没有新增竞争事件或可能答案，也未删除明确要求考查的关系。
- same_language: pass — 原题与候选题均为中文；本题没有选项。
- naturalness: 0/3 — “谁受伤逃出了那房子？”表达自然直接，“那房子”可由经文中的房子明确承接。
- processing: 0/3 — 题干为单一人物问句，无嵌套修饰或额外关系比较；经文中的人物指代清楚。
- context_economy: 0/3 — 候选题未保留额外事件铺垫，受伤、逃离和房子均用于定位目标事件，没有可避免的题干指代链。

Verification 2: PASS
- contract_validity: pass — 明确目标是识别受伤逃出房子的人，而非考查制服与逃离的先后关系。19:14明确人物为士基瓦的七个儿子，19:16叙述他们受伤逃出房子，支持合同中的目标、答案组成及关系角色。
- same_target: pass — 候选问题保留了“谁”“受伤”“逃出那房子”，完整保留目标人物及定位事件所需的范围。
- removals_justified: pass — 仅删除“被那附着邪灵的人制服以后”这一前置定位背景。当前经文只有一次受伤逃出房子的事件，删除后没有新增竞争人物或事件，也未删除明确要求考查的关系。
- same_language: pass — 原问题和候选问题均为中文；本题没有选项。
- naturalness: 0/3 — “谁受伤逃出了那房子？”是自然、直接的中文问句；“那房子”可由经文中的房子定位。
- processing: 0/3 — 问句结构简短清楚，没有额外的角色嵌套或修饰负担；只需从经文恢复“他们”的人物身份。
- context_economy: 0/3 — 候选问题没有额外铺陈制服事件；保留的受伤、逃离及房子均用于直接界定目标事件。

## focus:escape:split:inferred

Status: SIMPLIFIED

Target (inferred): 识别受伤逃出房子的那些人的身份：士基瓦的七个儿子。问题考查这一事件中的参与者身份，而不单独考查他们此前被制服的经过。

未提供非空的 intended_target，因此目标是依据当前问题及 original_question、original_answer 保守推断的，不代表明确给定的研究设计意图。原问题同样询问受伤逃出房子者的身份，与当前问题及固定答案一致。19:14明确人物为士基瓦的七个儿子，19:16以“他们”承接并叙述其受伤逃出房子，支持该答案。

- r1 / removable: 那个被邪灵附身的人制服了一些人。 — 这是到达逃跑事件之前的叙事背景，并非问题要求回答的事实。本文只有一处人们受伤逃出房子的事件，因此保留该逃跑事件即可唯一确定所问人物，无须依靠被制服的经过来消歧。
- r2 / anchor: 这些人随后带伤逃出了那房子 — 这是身份问题的事件定位信息，与19:16的受伤逃出房子相对应。“随后”连接前面的叙事，但问题并未要求判断事件顺序；该事件描述的作用是确定在问哪一群人。
- r3 / tested: 他们是谁？ — 受试者必须把逃跑事件中的人物与19:14所指明的士基瓦的七个儿子联系起来；只复述逃跑或受伤的情况不能回答身份问题。

### Proposal 1: SIMPLIFIED

谁带伤逃出了那房子？

直接询问带伤逃出房子者的身份，保留定位人物所需的事件，删除此前被制服的背景叙述。

Verification 1: PASS
- contract_validity: pass — 原问题及 original_question 都询问受伤逃出房子者的身份，并不要求解释制服经过或判断事件顺序。19:14 指明士基瓦的七个儿子，19:16 承接叙述他们受伤逃出房子，支持合同所列目标、答案成分及关系角色。
- same_target: pass — 候选仍要求识别带伤逃出那房子的人，保留了事件定位与人物身份这一核心目标；完整答案仍为士基瓦的七个儿子。
- removals_justified: pass — 删除了被邪灵附身者制服他们的前情，以及“这些人—他们”的重复指代和“随后”的连接。经文只有一处受伤逃出房子的事件，直接以该事件提问即可唯一定位人物，删除没有引入竞争事件或答案。
- same_language: pass — 原题与候选题均为中文；本题没有选项。
- naturalness: 0/3 — “谁带伤逃出了那房子？”是自然、直接的中文问句，“带伤”与经文的“受伤”含义一致。
- processing: 0/3 — 题干直接询问事件参与者，没有额外嵌套、角色转换或重复指代链；联系经文人物与事件属于必要的理解任务。
- context_economy: 0/3 — 候选题干只保留定位目标事件所需的信息，没有复述制服经过或另设人物指代链。

Verification 2: PASS
- contract_validity: pass — The original and source question ask for the identity of those who fled wounded, not an explanation of their defeat or a judgment about event order. The contract correctly identifies Sceva’s seven sons as the required answer and treats their prior defeat as removable background.
- same_target: pass — “谁带伤逃出了那房子？” preserves the identity question and its defining event: fleeing the house wounded. It retains all required answer components.
- removals_justified: pass — The candidate removes the prior overpowering event and the “一些人—这些人—他们” reference chain. The passage contains only one wounded escape from a house, so those details are unnecessary for identification. Removing “随后” does not remove a tested temporal relation.
- same_language: pass — Both questions are in Chinese. There are no answer options.
- naturalness: 0/3 — “谁带伤逃出了那房子？” is idiomatic, direct Chinese and requires no mental repair.
- processing: 0/3 — The question directly asks for the participant in one clearly specified event, without an avoidable pronoun chain or nested setup.
- context_economy: 0/3 — The retained wounded-escape description usefully anchors the requested identity. The candidate adds no unnecessary event narration or relationship setup.

## focus:escape:split:explicit

Status: SIMPLIFIED

Target (explicit): Identify the people who escaped from the house injured. The preceding overpowering event is identifying setup, not a separately tested relationship.

The explicit target agrees with the earlier original question and answer. In the supplied passage, 19:14 identifies the actors as Sceva’s seven sons, and 19:16 describes those same people being overpowered and escaping from the house injured. This supports the fixed answer. Their nakedness, also mentioned in the passage, is not a requested answer component.

- r1 / removable: 那个被邪灵附身的人制服了一些人。 — The explicit target treats the overpowering event as setup rather than a separately tested relationship. The passage contains only one event in which people escape from a house injured, so that escape still uniquely identifies the relevant people without this setup.
- r2 / removable: 随后 — This narrates the sequence leading to the escape; the question does not independently ask about temporal order. The injured escape uniquely identifies the event without this sequencing detail.
- r3 / anchor: 带伤逃出了那房子 — This identifies the particular event whose participants must be named. The injury and escape from the house define the scope specified by the explicit target, rather than requiring a separate account of what happened.
- r4 / tested: 他们是谁 — The requested understanding is the identity of those people, not an explanation of how they were overpowered or why they fled.

### Proposal 1: SIMPLIFIED

谁带伤逃出了那房子？

删除了被制服的背景和先后顺序，直接询问带伤逃出房子的人的身份。

Verification 1: PASS
- contract_validity: pass — The explicit intended target is to identify those who escaped from the house injured, not to test the preceding overpowering or temporal relationship. Verse 19:14 identifies the participants as Sceva’s seven sons, and 19:16 describes their injured escape. The contract preserves the required identity and event anchor.
- same_target: pass — “谁带伤逃出了那房子？” directly asks for the identity of the people in the specified injured escape, preserving the full intended target and required answer.
- removals_justified: pass — The candidate removes the overpowering setup, “随后,” and the repeated references through “一些人／这些人／他们.” These identify or sequence the same event but are not independently tested. The passage contains no competing injured escape from a house, so removing them creates no ambiguity.
- same_language: pass — The original and candidate questions are both in Chinese. There are no displayed options.
- naturalness: 0/3 — “谁带伤逃出了那房子？” is idiomatic, direct Chinese; “带伤” naturally expresses the injury accompanying the escape.
- processing: 0/3 — The candidate uses one straightforward question with an explicit event description and no avoidable participant-reference chain.
- context_economy: 0/3 — The question retains only the requested identity and the injured-escape event anchor. It adds no unnecessary narration of the preceding attack.

Verification 2: PASS
- contract_validity: pass — The explicit intended target is to identify those who escaped injured, not to test the preceding overpowering or temporal sequence. Acts 19:14 identifies Sceva’s seven sons, and 19:16 describes those same people escaping injured. The contract correctly distinguishes the identifying escape event from removable setup.
- same_target: pass — “谁带伤逃出了那房子？” retains the identity question and the complete target event: escaping from the house injured. It still requires identifying Sceva’s seven sons.
- removals_justified: pass — The candidate removes the overpowering event, “随后,” and the repeated references “一些人／这些人／他们.” These are dispensable setup: the clean passage contains only one injured escape from a house, so their removal introduces no competing event or answer.
- same_language: pass — Both the original and candidate questions are in Chinese. There are no displayed options.
- naturalness: 0/3 — “谁带伤逃出了那房子？” is idiomatic, direct Chinese. “带伤” naturally expresses the injury condition, and the passage supplies the referent for “那房子.”
- processing: 0/3 — The question has a single interrogative participant and a straightforward event description, with no avoidable reference chain or clause-comparison burden.
- context_economy: 0/3 — The candidate supplies no unnecessary question setup. Injury and escape from the house are useful anchors defining the explicitly intended target.

## transfer:handkerchief:original:zh

Status: SIMPLIFIED

Target (explicit): What happened to the sick people (illnesses and evil spirits leaving), not which objects touched Paul or where the objects were taken.

第12节直接说明，手帕和围裙被带到病人那里后，疾病和邪灵就离开了他们，支持固定答案及选项B。目标按所提供的 intended_target 原文保留；未提供非空的 original_question 或 original_answer。事件范围用于定位，既不把物品接触史扩展为测试目标，也不把疾病和邪灵这两个必要结果缩减为其中一个。

- r1 / tested: 发生了什么 — 明确目标要求理解病人发生的变化；只回答其中一项，或只指出物品及其去向，都不足以满足目标。
- r2 / anchor: 手帕和围裙 — 这些物品帮助定位第12节的事件，区别于后文驱魔师及被邪灵附着者的事件；物品名称本身不是要求作答的内容。
- r3 / anchor: 被带到病人那里时 — 这一事件范围使所问结果明确对应第12节，而不是后文其他与邪灵有关的结果。问题并不要求回答物品被送往何处，但所答结果必须属于这个事件。
- r4 / removable: 触摸过保罗的 — 这是物品的前置描述，不是明确目标要求理解的结果。当前段落仅有一次手帕和围裙被带到病人那里的事件，保留物品及送达病人的事件信息即可唯一定位，无须依靠此前接触保罗这一细节。

### Proposal 1: SIMPLIFIED

手帕和围裙被带到病人那里时，病人发生了什么变化？

删除物品此前触摸过保罗的描述，保留物品及送到病人那里的事件范围，直接询问病人的变化。
- A. 病人陷入了深度睡眠
- B. 疾病和邪灵离开了病人
- C. 犹太驱魔师给病人驱魔
- D. 病人变得无法说话
- E. 根据这段文字无法判断

Verification 1: PASS
- contract_validity: pass — 明确目标是病人在所指事件中经历的结果。原题和第12节均支持两个必要成分：疾病离开病人、邪灵离开病人。物品及送达事件用于定位；此前触摸过保罗不是独立测试目标。
- same_target: pass — 候选仍询问手帕和围裙被带到病人那里时，病人发生的变化，保留了事件范围和两个必要结果，没有改问物品、地点或其他事件。
- removals_justified: pass — 唯一实质删减是“触摸过保罗的”。当前窗口只有一次手帕和围裙被带到病人那里的事件，剩余描述足以唯一定位；删除接触史没有引入竞争事件或答案。
- same_language: pass — 原题和候选题均使用中文，A至E各选项也保持原来的中文表述。
- naturalness: 0/3 — “手帕和围裙被带到病人那里时，病人发生了什么变化？”是自然、直接的中文问句，各选项也无需语言修补。
- processing: 0/3 — 题干以一个时间从句定位事件，主句直接询问病人的变化；没有复杂指代链、角色转换或难以比较的选项结构。
- context_economy: 0/3 — 题干保留的物品及送达病人的信息能定位第12节，区别于后文驱魔事件；没有额外叙述接触史或加入可删的事件铺垫。

Verification 2: PASS
- contract_validity: pass — 明确目标是病人经历的结果。第12节支持疾病离开、邪灵离开两个必要成分，并将其限定在手帕和围裙被带到病人那里的事件中。物品及送达事件是定位信息；此前接触保罗不是被测试的关系。
- same_target: pass — 候选题仍询问同一送达事件中病人的变化，保留疾病和邪灵离开这两个必要结果，没有改成询问物品或去向。
- removals_justified: pass — 仅删除物品“触摸过保罗”的前置描述。文中只有一次手帕和围裙被带到病人那里的事件，剩余信息足以唯一定位；删除后没有引入其他竞争事件。
- same_language: pass — 问题及所有选项均保持中文。
- naturalness: 0/3 — “手帕和围裙被带到病人那里时，病人发生了什么变化？”表达自然直接，时间范围与询问对象清楚。
- processing: 1/3 — 读者需要在经文中定位送达事件，并识别疾病和邪灵两个结果；这是普通的阅读匹配要求，没有额外指代链或角色辨认负担。
- context_economy: 0/3 — 题干保留的物品与送达病人的事件共同提供有用定位，区别于后文另一驱魔事件；没有额外叙述接触史或设置可避免的指代链。

## constructed:direct

Status: REVIEW

Target (explicit): Identify who moved the books inside.

所给段落明确写道“小林把书搬进屋里”，支持固定答案“小林”，并与显式目标一致。下雨和小周留在门口均未出现在问题中，也不是回答所需的信息。

- r1 / tested: 谁 — 问题要求回答是谁实施了该动作；人物身份是必须恢复的信息。
- r2 / anchor: 把书搬进屋里 — 该动作、对象和目的地共同定位所问事件，使施事者身份有明确指向；问题并未单独要求回答搬了什么或搬到哪里。

### Proposal 1: NOT_ACCEPTED

是谁把书搬进屋里的？

原问题已简洁直接，搬运对象和目的地均是定位所问事件的必要信息，无可实质删减的内容。

Verification 1: REVIEW
- contract_validity: pass — 契约与显式目标一致：识别搬书进屋这一事件的施事者。原文直接支持“小林”；动作、对象和目的地用于定位事件，不是额外要求回答的内容。
- same_target: pass — 候选问题与原问题完全相同，仍要求识别把书搬进屋里的人，保留了完整的事件范围。
- removals_justified: pass — 候选未删除或改动任何信息。
- same_language: pass — 问题保持原有中文；本题没有选项。
- naturalness: 0/3 — 段落和“是谁把书搬进屋里的？”均为自然、直接的中文表达。
- processing: 0/3 — 句子短，人物均直接以姓名出现，没有需要追踪的代词或复杂修饰关系。
- context_economy: 2/3 — 整个展示段落中，“下雨了”和“小周留在门口”均非识别搬书者所必需。直接保留“小林把书搬进屋里”即可充分定位事件；其余内容是可避免的天气和另一人物事件铺陈。

Verification 2: PASS
- contract_validity: pass — 契约与原题、显式目标和原文一致：测试搬书事件的施事者；“把书搬进屋里”用于定位事件，所需答案为“小林”。
- same_target: pass — 候选题与原题完全相同，仍要求识别把书搬进屋里的人，未改变事件范围或答案要求。
- removals_justified: pass — 候选题未删除或改写任何原有内容。
- same_language: pass — 问题保持原有中文；本题没有选项。
- naturalness: 0/3 — “是谁把书搬进屋里的？”是自然、直接的中文问法。
- processing: 0/3 — 问题直接询问单一动作的施事者，无复杂修饰、跨句指代或角色转换。
- context_economy: 0/3 — 题干仅保留定位目标事件所需的动作、对象和目的地，没有复述下雨或小周留在门口等背景，也没有多余的指代链。

### Proposal 2: REPEATED_PROPOSAL

是谁把书搬进屋里的？

原问题自然、直接，仅包含识别搬书者所需的事件信息，无可实质简化的内容。

## hard:t1_acts20:f988:mcq

Status: KEPT

Target (inferred): 理解保罗一直讲到午夜的原因是他准备第二天离开，识别离开计划与延长讲话之间的因果关系。

未提供明确的 intended_target 或早期原题、原答案，因此目标为保守推断，并非已获研究者确认的设计意图。所供经文20:7明确说“由于保罗第二天准备离开，他与他们交谈，并一直讲到午夜”，支持固定答案及其因果关系。题目没有可安全归为冗余叙事的铺垫。

- r1 / anchor: 保罗 — 限定所问原因属于保罗的讲话事件，不是尤提古斯沉睡或坠楼等其他事件。
- r2 / tested: 为什么一直讲到午夜 — 直接考查因果关系；持续讲话及其终点午夜界定了需要解释的行为，不能仅保留人物或讲话事实而删去这一范围。

### Proposal 1: KEPT

保罗为什么一直讲到午夜？

原题已简洁直接；人物、持续讲话及午夜这一终点均为必要信息，没有可安全删除的冗余内容。
- A. 因为他打算第二天离开
- B. 因为他在庆祝节期
- C. 因为他在等人
- D. 因为楼上的房间里有许多灯

Verification 1: PASS
- contract_validity: pass — 原题询问保罗一直讲到午夜的原因。经文20:7用“由于保罗第二天准备离开”明确说明原因；契约保留了离开计划与延长讲话之间的因果关系、人物及午夜这一事件范围。
- same_target: pass — 候选题与原题完全相同，仍要求解释保罗为何一直讲到午夜，没有把因果理解降为事实识别。
- removals_justified: pass — 候选题没有删除或改写原题、选项或经文中的信息。
- same_language: pass — 问题及A至D各选项均保持原有中文表述。
- naturalness: 0/3 — “保罗为什么一直讲到午夜？”自然直接，四个“因为……”选项与问句衔接顺畅。
- processing: 0/3 — 问题直接点明人物与待解释事件；选项简短、结构一致，没有复杂指代或角色辨认负担。
- context_economy: 0/3 — 题干没有另加叙事铺垫或重复指代链；“保罗”和“一直讲到午夜”均用于准确界定所问的因果关系。

Verification 2: PASS
- contract_validity: pass — 原题询问保罗一直讲到午夜的原因；经文20:7用“由于”明确连接第二天离开的计划与持续讲话。合同正确保留了原因、行为及午夜这一范围，人物锚点也准确。
- same_target: pass — 候选题与原题完全相同，仍考查离开计划与持续讲话至午夜之间的因果关系，没有降为事实识别题。
- removals_justified: pass — 候选未删除或修改原题、选项或经文，不存在未经论证的信息移除。
- same_language: pass — 题干及A至D四个选项均保持原来的中文表述。
- naturalness: 0/3 — “保罗为什么一直讲到午夜？”表达自然直接，四个选项也都是通顺的中文原因短语。
- processing: 0/3 — 题干直接点明人物、行为和时间终点，无额外指代链；选项结构平行，比较负担低。
- context_economy: 0/3 — 题干没有另加事件铺垫或重复叙述；保罗、持续讲话和午夜均用于界定所问事件，适合保持不变。

## control:escape:required_relation

Status: KEPT

Target (explicit): Identify the people overpowered by the possessed man who subsequently escaped injured. The link between being overpowered by that man and then escaping injured is explicitly part of the tested relationship and must remain in the question.

所供经文19:14将参与者确定为犹太大祭司士基瓦的七个儿子；19:16说明那附着邪灵的人制服了他们所有人，随后他们受伤逃出房子。因此固定答案有经文支持，且与明确目标一致。经文另述他们赤身裸体，但问题和明确目标均未要求这一细节。

- r1 / tested: 被那附着邪灵的人制服以后 — 明确目标规定，被制服与随后受伤逃出之间的联系属于测试内容，不能作为可删除的叙事背景。
- r2 / tested: 谁 — 问题要求回答参与者是谁；正确答案必须识别士基瓦的七个儿子，而不只是描述事件。
- r3 / tested: 受伤逃出了那房子 — 受伤及逃出房子共同构成所问事件，且受伤逃出的结果由明确目标指定为测试关系的一部分。

### Proposal 1: KEPT

被那附着邪灵的人制服以后，谁受伤逃出了那房子？

原问题已简洁直接；被制服、随后受伤逃出房子的关系均为测试内容，没有可删除的铺垫。

Verification 1: PASS
- contract_validity: pass — 契约符合明确目标及经文：19:14确定人物为士基瓦的七个儿子，19:16说明同一群人被附着邪灵的人制服，随后受伤逃出房子。身份、先后关系和受伤逃出的状态均属于有效测试内容。
- same_target: pass — 候选问题与原题完全相同，保留了识别人物的要求，以及被制服后受伤逃出房子的完整关系。
- removals_justified: pass — 候选没有删除或改写任何题目或经文信息。
- same_language: pass — 问题仍为原来的中文；本题没有选项。
- naturalness: 0/3 — “被……制服以后，谁受伤逃出了……？”表达自然、直接，时间关系及所问人物清楚。
- processing: 0/3 — 问题只有一个必要的时间从句和一个身份询问，没有多层指代或修饰语堆叠；经文中的人物衔接清晰。
- context_economy: 0/3 — 问题没有额外叙事铺垫。“被那附着邪灵的人制服以后”是明确目标要求保留的测试关系，而非可删背景；受伤和逃出房子也都是目标事件的必要组成部分。

Verification 2: PASS
- contract_validity: pass — 契约符合明确目标及经文：19:14确定参与者为士基瓦的七个儿子，19:16说明同一群人被附着邪灵的人制服，随后受伤逃出房子。身份、先后关系及共同参与者均属有效测试内容。
- same_target: pass — 候选问题与原题完全相同，保留了被制服与随后受伤逃出房子的联系，并要求识别经历这些事件的人。
- removals_justified: pass — 候选未删除或改写原题及经文中的任何信息。
- same_language: pass — 问题仍为原来的中文；本题没有选项。
- naturalness: 0/3 — 问题为直接、完整的中文问句，“被……制服以后”与“谁受伤逃出了……”衔接自然。
- processing: 0/3 — 单句清楚表达施事、受事及事件顺序，没有多层指代链或需要额外解码的结构。
- context_economy: 0/3 — 问题没有额外叙事铺垫；前置的被制服关系属于明确规定的测试内容，受伤逃出房子则界定目标事件，均有必要保留。

## control:necessary_time

Status: KEPT

Target (explicit): Identify who left before the meal, preserving the before/after distinction.

所供参与者短文明确写道“吃饭前，小林离开了”，并以“吃饭后，小周也离开了”形成时间对照。固定答案“小林”有直接支持，与显式目标一致。

- r1 / tested: 吃饭前 — 显式目标要求保留饭前与饭后的区别；这一时间条件也区分了文中两次离开事件，不能删除。
- r2 / tested: 谁离开了 — 问题要求回答离开者是谁；结合饭前条件，答案必须指向小林。

### Proposal 1: KEPT

吃饭前，谁离开了？

原问题已简洁直接；“吃饭前”是区分两次离开事件的必要时间条件，不能删除。

Verification 1: PASS
- contract_validity: pass — 契约符合显式目标和短文：识别吃饭前离开的小林，并保留与吃饭后离开的小周的时间区别。所需答案为“小林”，不必在作答中复述整个对照。
- same_target: pass — 候选与原题完全相同，保留“吃饭前”的时间条件及“谁离开了”的身份识别目标。
- removals_justified: pass — 候选未删除或改动原题、短文中的任何信息。
- same_language: pass — 问题仍为中文；本题没有选项。
- naturalness: 0/3 — 短文和“吃饭前，谁离开了？”均自然、直接，无需修补理解。
- processing: 0/3 — 两句使用平行结构，人物明确；只需匹配问题中的“吃饭前”与第一句。
- context_economy: 0/3 — 第一句提供答案，第二句提供显式目标所需的饭后对照；没有多余叙事或指代链。

Verification 2: PASS
- contract_validity: pass — The explicit target and passage support identifying 小林 as the person who left before the meal, distinguishing that event from 小周 leaving afterward. Both identity and the tested temporal condition are correctly represented in the contract.
- same_target: pass — The candidate is unchanged and preserves both the identity question and the essential 吃饭前 condition.
- removals_justified: pass — No information was removed or altered.
- same_language: pass — The question remains in Chinese. There are no options.
- naturalness: 0/3 — The Chinese passage and question are idiomatic and direct.
- processing: 0/3 — Two short parallel sentences clearly associate each named person with a departure time; the question requires a straightforward temporal match.
- context_economy: 0/3 — The before/after contrast serves the explicit target. There is no extraneous setup or avoidable reference chain.

## control:necessary_event

Status: KEPT

Target (inferred): 识别在被人制服后受伤逃出房子的参与者。

未提供明确的 intended_target 或更早的原题、原答案，因此目标为保守推断，不代表研究者已确认的设计意图。段落明确写出小周被另一个人制服，也受伤逃出了房子，支持固定答案“小周”。小林也受伤逃出了房子，故制服这一限定不可删除；没有可安全认定为冗余的整项关系。

- r1 / tested: 谁 — 问题直接询问人物身份，而非制服或逃离的原因。
- r2 / anchor: 被那个人制服后 — 这是区分两名参与者的必要条件：小林和小周都受伤逃出了房子，但只有小周被描述为先遭到制服。此处的先后关系用于限定所问事件，并非另行要求解释时间关系。
- r3 / tested: 受伤逃出了房子 — 这是身份问句所指向的核心事件，包含受伤与逃出房子两个描述；不能仅因仍能猜出同一人物，就将所问事件改成单纯被制服。

### Proposal 1: KEPT

谁被那个人制服后，受伤逃出了房子？

原题已直接询问人物身份。“被那个人制服后”是区分两人的必要条件，“受伤逃出了房子”是所问的核心事件，没有可安全删除的关系。

Verification 1: PASS
- contract_validity: pass — 原题要求识别先被制服、随后受伤逃出房子的人。契约保留人物身份、制服限定及受伤逃离事件，没有将问题缩减为只问谁被制服。段落支持答案“小周”。
- same_target: pass — 候选与原题完全相同，保留全部事件条件、先后关系及人物身份这一回答目标。
- removals_justified: pass — 候选未删除或改写原题、段落中的任何信息。
- same_language: pass — 问题仍为中文；本题没有选项。
- naturalness: 1/3 — 整体表达通顺，但问句使用“那个人”，段落只引入“另一个人”，指称衔接略显生硬，不影响理解。
- processing: 1/3 — 读者需比较两名都受伤逃离的人，并利用被制服这一条件筛选小周；这是必要且可管理的理解负担。
- context_economy: 0/3 — 问句直接询问目标事件，没有额外铺垫或重复指称链。被制服的限定用于区分同样受伤逃离的小林，具有实际作用。

Verification 2: PASS
- contract_validity: pass — The original asks for the participant who was subdued and then escaped injured. The passage supports 小周. The contract preserves the identity target, the distinguishing subduing condition, and the injured escape event.
- same_target: pass — The candidate is identical to the original, retaining the subduing condition, temporal sequence, injury, and escape from the house.
- removals_justified: pass — No information was removed or changed.
- same_language: pass — The question remains in Chinese. There are no options.
- naturalness: 0/3 — The Chinese question is idiomatic and direct. The construction “谁被……制服后，受伤逃出了房子” naturally expresses the participant and event sequence.
- processing: 1/3 — The reader must distinguish two injured escapees using the passive subduing condition. This is manageable, target-relevant comparison rather than avoidable reference complexity.
- context_economy: 0/3 — The question contains no separate setup or repeated reference chain. The subduing condition distinguishes 小周 from 小林, while injury and escape preserve the event being queried.

## control:direct:en

Status: KEPT

Target (explicit): Identify who left.

The clean participant passage explicitly states, "Mara left." This supports the expected answer, Mara; "Levi stayed" supplies a contrasting participant but adds no requested answer component.

- r1 / tested: Who left? — The question directly tests the identity of the person who left. No additional setup or identifying conditions appear in the question.

### Proposal 1: KEPT

Who left?

The question directly tests the intended target with no removable setup or unnecessary wording.

Verification 1: PASS
- contract_validity: pass — The explicit target is to identify who left. The passage states that Mara left, supporting Mara as the sole required answer component and agent of leaving.
- same_target: pass — The candidate retains the original question, passage, and expected answer unchanged.
- removals_justified: pass — No information was removed.
- same_language: pass — The question remains in English; there are no options.
- naturalness: 0/3 — Both passage statements and 'Who left?' are idiomatic and direct.
- processing: 0/3 — The short clauses name their participants explicitly, and the question requires a straightforward identification.
- context_economy: 1/3 — 'Levi stayed' provides a brief contrast but is not necessary to identify who left. There is no extended setup or reference chain.

Verification 2: PASS
- contract_validity: pass — The explicit target is to identify who left. The passage states 'Mara left,' supporting Mara as the required answer and the leaving participant as the tested role.
- same_target: pass — The candidate preserves the original question, passage, target, and expected answer unchanged.
- removals_justified: pass — No information was removed.
- same_language: pass — The question remains in English. There are no options.
- naturalness: 0/3 — 'Who left?' and both passage sentences are idiomatic and direct.
- processing: 0/3 — The reader can match the leaving action directly to Mara, with no reference chain or complex comparison.
- context_economy: 0/3 — The setup is brief. Mara's action provides the answer, and Levi's contrasting action supplies a useful alternative participant without unnecessary narration.

## control:unsupported_answer

Status: HOLD_TARGET

Target (explicit): Identify why Xiaolin left.

参与者经文为“小林离开了。经文没有说明原因。”，明确未提供离开的原因。固定答案“因为下雨了。”没有经文支持，因此必须暂缓，不能将其确立为可用的答案契约。

- r1 / tested: 为什么 — 原因是明确要求恢复的关系，也是显式目标的核心，不能删除或改为仅识别人物。
- r2 / anchor: 小林 — 将所问原因定位到经文中小林的离开事件。
- r3 / tested: 离开了 — 限定需要解释的事件；必须说明离开的原因，而非其他行为的原因。
