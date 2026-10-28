# Early QA simplification

Model-screened results; original datasets unchanged. Inferred targets remain provisional.

| Item | Status | Before | After |
|---|---|---|---|
| focus:escape:original:inferred | SIMPLIFIED | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | 谁受伤逃出了那房子？ |
| focus:escape:original:explicit | SIMPLIFIED | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | 谁受伤逃出了那房子？ |
| focus:escape:split:inferred | SIMPLIFIED | 那个被邪灵附身的人制服了一些人。这些人随后带伤逃出了那房子，他们是谁？ | 谁带伤逃出了那房子？ |
| focus:escape:split:explicit | SIMPLIFIED | 那个被邪灵附身的人制服了一些人。这些人随后带伤逃出了那房子，他们是谁？ | 谁受伤逃出了那房子？ |
| transfer:handkerchief:original:zh | SIMPLIFIED | 当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？ | 当手帕和围裙被带到病人那里时，病人发生了什么变化？ |
| constructed:direct | KEPT | 是谁把书搬进屋里的？ | 是谁把书搬进屋里的？ |
| hard:t1_acts20:f988:mcq | KEPT | 保罗为什么一直讲到午夜？ | 保罗为什么一直讲到午夜？ |
| control:escape:required_relation | KEPT | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ |
| control:necessary_time | KEPT | 吃饭前，谁离开了？ | 吃饭前，谁离开了？ |
| control:necessary_event | KEPT | 谁被那个人制服后，受伤逃出了房子？ | 谁被那个人制服后，受伤逃出了房子？ |
| control:direct:en | KEPT | Who left? | Who left? |
| control:unsupported_answer | HOLD_TARGET | 小林为什么离开了？ |  |

## focus:escape:original:inferred

Status: SIMPLIFIED

Target (inferred): 识别经文中受伤逃出房子的人，即士基瓦的七个儿子。

未提供明确的 intended_target 或更早的 original_question/original_answer，因此目标是依据当前问题保守推断的，不代表已获研究者确认的设计意图。19:14 将相关人物确定为士基瓦的七个儿子，19:16 说明他们被制服后受伤逃出房子，支持给定答案。回答无需另述他们被制服的经过，也无需补充问题未要求的赤身裸体状态。

- r1 / removable: 被那附着邪灵的人制服以后 — 这是叙述人物如何进入所问事件的先行背景，并非要求回答的时间关系或经过。本段只有一次受伤逃出房子的事件，保留该事件即可唯一确定所问人物，不需要此前被制服的描述。
- r2 / tested: 谁受伤逃出了那房子 — 这是问题直接要求恢复的人物身份及其事件范围。受伤和逃出房子共同限定所问事件，不能仅因预期答案相同而将问题改为识别其他事件中的人物。

### Proposal 1: SIMPLIFIED

谁受伤逃出了那房子？

删除被制服的先行背景，保留受伤逃出房子的事件及人物识别要求。

Verification 1: PASS
- contract_validity: pass — 原题要求识别受伤逃出房子的人，并未要求说明被制服的经过或先后关系。经文19:14和19:16支持将核心目标确定为士基瓦的七个儿子；将此前被制服的描述视为可删除的识别背景是合理的。
- same_target: pass — 候选题保留了“谁”“受伤”和“逃出了那房子”，仍要求识别同一事件中的人物，保留了必要的答案组成和事件范围。
- removals_justified: pass — 仅删除了“被那附着邪灵的人制服以后”。当前经文只有一次受伤逃出房子的事件，删除此前被制服的背景不会引入其他符合条件的人物或事件，也不影响核心目标。
- same_language: pass — 原题和候选题均为简体中文；本题没有选项。
- naturalness: 0/3 — 问句符合自然中文表达，直接询问人物，无需修补语意。
- processing: 0/3 — 单句结构清楚，人物疑问词直接对应受伤逃出房子的动作，没有多层修饰或额外指代链。
- context_economy: 0/3 — 题目仅保留定位目标事件所需的受伤状态和逃出房子的动作；“那房子”是简短的经文事件锚点，没有冗余叙事。

Verification 2: PASS
- contract_validity: pass — 原题要求识别受伤逃出房子的人，并非询问原因、条件或事件先后关系。契约保留了人物身份及“受伤逃出房子”的事件范围；将被制服的前情判为可删除背景是合理的。
- same_target: pass — 候选题仍问“谁受伤逃出了那房子”，完整保留原题的人物识别目标和事件限定，所需答案仍为士基瓦的七个儿子。
- removals_justified: pass — 仅删除“被那附着邪灵的人制服以后”这一前情。经文只有一次受伤逃出房子的事件，删除后没有新增竞争人物或事件，也不影响确定所问对象。
- same_language: pass — 原题和候选题均为中文；本题无选项。
- naturalness: 0/3 — 问句中文自然直接，“受伤逃出”的表达清楚，无需语义修补。
- processing: 0/3 — 单一简短问句直接询问人物；“那房子”可由经文中的唯一相关事件识别，没有额外的角色或指代链负担。
- context_economy: 0/3 — 候选题没有附加前情叙述；保留的受伤状态和逃出房子的动作共同界定目标事件，信息经济且有用。

## focus:escape:original:explicit

Status: SIMPLIFIED

Target (explicit): Identify the people who escaped from the house injured. The preceding overpowering event is identifying setup, not a separately tested relationship.

19:14将行驱魔之事的人明确为士基瓦的七个儿子；19:16以“他们”承接这些人，并叙述他们受伤逃出房子。因此固定答案得到所提供经文支持。无需另行回答制服者的身份、先后顺序或赤身裸体这一未被题目要求的细节。

- r1 / removable: 被那附着邪灵的人制服以后 — 明确目标将先前被制服的事件规定为识别性背景，而非单独考查的关系。题目并未询问事件顺序；本段只有一次受伤逃出房子的事件，保留该事件即可唯一定位所问的人。
- r2 / tested: 谁受伤逃出了那房子？ — 这是明确目标所规定的身份识别任务。回答必须把士基瓦的七个儿子与受伤逃出房子的事件对应起来，而不只是泛指段落中的驱魔师。

### Proposal 1: SIMPLIFIED

谁受伤逃出了那房子？

删除被制服的背景事件，保留识别受伤逃出房子者的考查目标。

Verification 1: PASS
- contract_validity: pass — 明确目标是识别受伤逃出房子的人，并明确将先前被制服的事件列为识别背景。合同保留了人物与受伤逃出房子事件的对应关系；19:14及19:16支持答案为士基瓦的七个儿子。
- same_target: pass — 候选题仍询问谁受伤逃出房子，完整保留人物识别目标及受伤、逃出房子的事件范围。
- removals_justified: pass — 唯一删除的内容是“被那附着邪灵的人制服以后”。这不是明确目标要求测试的关系；经文中仅有一次受伤逃出房子的事件，删除后没有新增竞争人物或事件。
- same_language: pass — 原题和候选题均为中文；本题无选项。
- naturalness: 0/3 — 问句符合中文表达习惯，直接自然，无需修补理解。
- processing: 0/3 — 单一疑问句直接询问事件参与者，没有多层指代、复杂修饰或角色转换负担。
- context_economy: 0/3 — 仅保留定位目标事件所需的受伤和逃出房子信息，没有额外事件叙述或可避免的背景链。

Verification 2: PASS
- contract_validity: pass — 明确目标是识别受伤逃出房子的人，不是考查被制服与逃离之间的先后关系。经文19:14及19:16支持所需答案为士基瓦的七个儿子，合同对测试内容和可移除背景的划分有效。
- same_target: pass — 候选题保留了受伤、逃出房子及识别人物这三个核心要素，仍要求将士基瓦的七个儿子与该事件对应起来。
- removals_justified: pass — 仅删除了“被那附着邪灵的人制服以后”这一先前事件背景。明确目标不单独测试该关系，且当前经文只有一次受伤逃出房子的事件；删除后没有引入其他可能的人物或事件。
- same_language: pass — 原题与候选题均使用中文；本题无选项。
- naturalness: 0/3 — 问句简洁自然，人物疑问词与事件描述搭配顺畅。
- processing: 0/3 — 候选题为单一直接问句，没有多层修饰、复杂角色关系或额外指代链。
- context_economy: 0/3 — 保留的受伤及逃出房子描述直接界定目标事件，没有多余事件铺垫。

## focus:escape:split:inferred

Status: SIMPLIFIED

Target (inferred): 识别在被附着邪灵的人制服后，受伤逃出房子的那些人是谁。

未提供非空的明确研究目标，因此依据当前问题、原题及两处一致的答案保守推断。19:14明确参与者为士基瓦的七个儿子，19:16以“他们”延续这些人物，记述其被制服并受伤逃出房子，支持固定答案。无需另外回答其父亲的祭司身份、驱魔用语或赤身裸体的细节。

- r1 / removable: 那个被邪灵附身的人制服了一些人。 — 这是人物到达所问事件之前的叙事背景，并非另行要求回答的事实。在本段中，受伤逃出房子的事件只有一次，仅凭该逃离事件仍能唯一定位所问人物。
- r2 / removable: 随后 — 问题询问人物身份，而非事件先后顺序；这一时间连接也不用于区分本段中的多个逃离事件。原题中的先后关系同样用于定位人物，而非要求解释或复述时间顺序。
- r3 / anchor: 这些人随后带伤逃出了那房子 — 受伤并逃出房子的事件用于定位身份问题的指称对象，段落中只有这一处符合的事件。此引文包含的时间连接词“随后”已在r2单独判定为可移除背景。
- r4 / tested: 他们是谁？ — 必须把所问人物与士基瓦的七个儿子对应起来；仅复述制服、受伤或逃离经过不能满足身份提问。

### Proposal 1: SIMPLIFIED

谁带伤逃出了那房子？

直接询问受伤逃出房子者的身份，保留定位事件，移除被制服的背景及先后连接。

Verification 1: PASS
- contract_validity: pass — 原题询问受伤逃出房子者的身份，并非要求说明被制服的原因或事件顺序。合同将身份识别列为测试核心，将此前被制服及先后关系视为定位背景，符合原题及经文。19:14与19:16支持所需答案“士基瓦的七个儿子”。
- same_target: pass — 候选题保留“带伤逃出了那房子”这一事件锚点，仍要求识别同一群人的身份，未改变所需答案或必要范围。
- removals_justified: pass — 删去被邪灵附身者制服众人的背景、“随后”及重复指代链是合理的。本段仅有一次受伤逃出房子的事件，删除这些内容不会引入另一组符合条件的人，也没有移除独立要求作答的关系。
- same_language: pass — 原题与候选题均为简体中文；本题没有选项。
- naturalness: 0/3 — “谁带伤逃出了那房子？”表达自然、直接，符合中文问句习惯。
- processing: 0/3 — 单句直接询问动作主体，没有多层修饰、角色转换或需要跨句解析的指代链。
- context_economy: 0/3 — 保留的受伤、逃离及房子共同构成清晰的事件定位，没有额外叙事铺垫或重复指代。

Verification 2: PASS
- contract_validity: pass — 原题要求识别受伤逃出房子的人，并非解释被制服的原因或回答事件顺序。经文19:14指出参与者是士基瓦的七个儿子，19:16延续指称他们。契约将人物身份列为测试目标、将被制服及先后关系列为可移除背景，符合原题与经文。
- same_target: pass — 候选题仍询问带伤逃出房子者的身份，保留了受伤、逃离及房子这一事件锚点；完整答案仍是士基瓦的七个儿子。
- removals_justified: pass — 删除了被邪灵附身的人制服他们的前置叙述、时间连接词“随后”和重复的人物指称。当前经文只有一次受伤逃出房子的事件，删除这些内容不会产生另一个符合条件的人物或事件，也未删除要求解释的关系。
- same_language: pass — 原题和候选题均为中文；此题无选项。
- naturalness: 0/3 — “谁带伤逃出了那房子？”是自然、直接的中文身份问句，无需修复语义。
- processing: 0/3 — 单句直接询问行动者，没有重复指称链、多层修饰或选项比较负担。
- context_economy: 0/3 — 题干只保留用于识别目标事件的受伤逃离及地点信息，没有附加事件叙述或冗余人物关系。

## focus:escape:split:explicit

Status: SIMPLIFIED

Target (explicit): Identify the people who escaped from the house injured. The preceding overpowering event is identifying setup, not a separately tested relationship.

显式目标与较早的 original_question、original_answer 一致。19:14 将参与者明确为士基瓦的七个儿子；19:16 说明他们受伤逃出房子，支持固定答案。段落中没有第二组受伤逃出房子的人，因此前置制服事件及其时间承接可判为冗余背景。

- r1 / removable: 那个被邪灵附身的人制服了一些人。 — 显式目标将制服事件规定为识别性背景，而非独立考查内容。本段只有一次受伤逃出房子的事件，因此不依赖制服事件也能唯一确定所问的人。
- r2 / removable: 这些人随后 — 这里的回指和时间顺序承接前面的背景，问题并未要求回答事件顺序。依据显式目标及本段唯一的受伤逃离事件，这一承接关系不是确定答案所必需的。
- r3 / tested: 带伤逃出了那房子，他们是谁？ — 这是显式目标所指定的身份识别任务；必须保留受伤逃出房子这一事件范围，而不能只以答案仍然相同作为目标保留的依据。

### Proposal 1: SIMPLIFIED

谁受伤逃出了那房子？

直接询问受伤逃出房子的人的身份，保留目标事件，删除制服事件及其回指和时间承接。

Verification 1: PASS
- contract_validity: pass — The explicit intended target is identification of those who escaped injured, not their prior overpowering or the sequence of events. The passage identifies the participants as Sceva’s seven sons in 19:14 and describes their injured escape in 19:16. The contract’s required answer and tested/removable relation assignments match this target.
- same_target: pass — “谁受伤逃出了那房子？” retains the identity question and the full identifying event of escaping from the house injured.
- removals_justified: pass — The candidate removes the overpowering event and its subsequent reference chain. These supply neither a separately tested relationship nor necessary disambiguation: the clean passage contains only one injured escape from a house. Removing them introduces no competing event or answer.
- same_language: pass — Both the original and candidate questions are in Chinese. Neither has options.
- naturalness: 0/3 — The candidate is a grammatical, idiomatic, direct Chinese identity question.
- processing: 0/3 — The single clause is readily parsed, with no avoidable reference chain or role-comparison burden.
- context_economy: 0/3 — The question contains only the requested identity and the useful event anchor, with no unnecessary narrative setup.

Verification 2: PASS
- contract_validity: pass — 显式目标是识别受伤逃出房子的人，而非解释制服事件或判断事件顺序。19:14明确参与者为士基瓦的七个儿子，19:16说明他们受伤逃出房子。合同的答案组件和关系角色与原题及经文一致。
- same_target: pass — 候选题保留了身份识别任务及“受伤逃出了那房子”这一完整事件范围，仍要求指出士基瓦的七个儿子。
- removals_justified: pass — 删去的是被邪灵附身的人制服他们这一前置事件，以及“这些人随后”的回指和时间承接。经文只有一组人受伤逃出房子，保留的逃离事件足以唯一识别人群；删去这些背景没有产生新的竞争答案，也没有删除独立考查的关系。
- same_language: pass — 原题与候选题均使用中文；本题无选项。
- naturalness: 0/3 — 中文问句自然直接，“谁”与后续动作描述搭配顺畅。
- processing: 0/3 — 单句直接询问事件参与者，没有多层回指、角色转换或额外比较负担。
- context_economy: 0/3 — 题目仅保留识别目标事件所需的受伤、逃离及房子信息，没有多余事件叙述或关系铺垫。

## transfer:handkerchief:original:zh

Status: SIMPLIFIED

Target (explicit): What happened to the sick people (illnesses and evil spirits leaving), not which objects touched Paul or where the objects were taken.

第12节明确记载，物品被带到病人那里后，“疾病和邪灵就离开了他们”。因此固定答案及选项B均有直接依据。目标由 supplied intended_target 明确给定；两个并列结果均须保留，不能只回答疾病离开或只回答邪灵离开。

- r1 / tested: 当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？ — 问题要求恢复这一特定事件中的结果，而不是其他驱魔事件的结果。“当……时”的事件范围限定结果所属的情境，但不要求额外推断因果机制。
- r2 / anchor: 手帕和围裙被带到病人那里 — 这一区分线索将问题定位于第12节，而非后文犹太驱魔师驱魔及遭受攻击的事件。物品名称和送达地点是事件定位信息，不是要求回答的独立知识点。
- r3 / removable: 触摸过保罗的 — 这是物品到达病人处之前的背景描述。本文只有一次手帕和围裙被带到病人处的事件，保留该送达事件即可唯一定位所问结果；明确目标也排除了考查哪些物品接触过保罗。

### Proposal 1: SIMPLIFIED

当手帕和围裙被带到病人那里时，病人发生了什么变化？

删除物品此前接触过保罗的背景描述，保留物品被带到病人那里的事件锚点，并直接询问病人的变化。
- A. 病人陷入了深度睡眠
- B. 疾病和邪灵离开了病人
- C. 犹太驱魔师给病人驱魔
- D. 病人变得无法说话
- E. 根据这段文字无法判断

Verification 1: PASS
- contract_validity: pass — 契约符合明确目标及第12节：考查物品被带到病人那里时，病人身上发生的结果，必须包含疾病和邪灵都离开病人。送达事件用于定位；物品此前接触保罗并非独立考点。
- same_target: pass — 候选题仍询问手帕和围裙被带到病人那里时病人的变化，保留同一事件范围及两个必要结果，没有转成物品名称、去向或其他驱魔事件的考查。
- removals_justified: pass — 删除的“触摸过保罗的”仅补充物品此前的接触背景。当前篇章只有一次手帕和围裙被带到病人那里的事件，保留的送达情境足以唯一定位；删除后没有引入竞争事件或答案。
- same_language: pass — 候选问题和A至E各选项均保持原来的简体中文。
- naturalness: 0/3 — 题干是自然、直接的中文问句，各选项表达清楚，不需要语义修补。
- processing: 0/3 — 题干只有一个清楚的时间情境和一个结果问题；“病人”的重复明确了变化主体，选项之间也容易比较。
- context_economy: 0/3 — 保留的物品送达情境能将目标事件与后文驱魔事件区分开，属于有用定位信息；没有多余的事件叙述或指代链。

Verification 2: PASS
- contract_validity: pass — 契约符合明确的预期目标及第12节：所问是物品被带到病人那里时的结果，答案必须同时包括疾病离开和邪灵离开。送达事件用于定位，物品此前接触保罗不是独立考点。
- same_target: pass — 候选仍询问同一送达事件中病人的变化，保留了结果关系、病人这一对象及两个必需的答案成分，没有改为询问物品或地点。
- removals_justified: pass — 删去的“触摸过保罗的”仅说明物品此前的接触背景。当前经文只有一次手帕和围裙被带到病人那里的事件，保留的事件描述足以唯一定位，不会引入另一竞争事件或答案。
- same_language: pass — 候选问题及A至E全部选项均保持原来的中文。
- naturalness: 0/3 — 问题的时间从句与结果问句搭配自然，选项表达清楚，无需修补语意。
- processing: 0/3 — 单一时间从句直接定位事件，主句明确询问病人的变化；没有复杂指代、角色转换或选项比较负担。
- context_economy: 0/3 — 手帕和围裙的送达事件是有用的定位线索，能将目标与后文驱魔事件区分开；问题没有保留额外背景叙述或不必要的指代链。

## constructed:direct

Status: KEPT

Target (explicit): Identify who moved the books inside.

所提供短文明确写道“小林把书搬进屋里”，支持固定答案“小林”。明确目标与当前问题、答案一致；没有提供更早的原始问题或答案。下雨是短文背景，并未出现在问题中，不属于本题要求恢复的因果或时间关系。

- r1 / tested: 是谁 — 问题要求回答人物身份；明确目标也规定识别是谁把书搬进屋里。
- r2 / anchor: 把书搬进屋里 — 该动作、对象和目的地共同定位所问事件。短文中只有一次搬书进屋的事件，与小周留在门口的事件不同；问题不要求另行回答搬了什么或搬到哪里。

### Proposal 1: KEPT

是谁把书搬进屋里的？

原问题已直接询问搬书进屋的人，动作、对象和目的地均为定位事件所需，无可实质删减的内容。

Verification 1: PASS
- contract_validity: pass — 合同准确识别了明确目标：回答搬书进屋这一事件的施事者。动作、对象和目的地用于定位事件，并非另行测试原因或条件。短文明确支持所需答案“小林”。
- same_target: pass — 候选问题与原问题完全相同，保留了人物识别目标以及“把书搬进屋里”的事件范围。
- removals_justified: pass — 候选问题未删除或改动任何原问题信息。
- same_language: pass — 原问题和候选问题均为中文；本题无选项。
- naturalness: 0/3 — “是谁把书搬进屋里的？”是自然、直接的中文人物询问句。
- processing: 0/3 — 问题结构清楚，直接询问指定动作的施事者，没有指代链或额外角色比较负担。
- context_economy: 0/3 — 问题没有附加叙事；“把书搬进屋里”是定位所问事件的有效锚点。

Verification 2: PASS
- contract_validity: pass — 契约与明确目标一致：识别搬书进屋这一事件的施事者。动作、对象和目的地是定位事件的必要锚点；原题未测试下雨与搬书之间的因果关系。
- same_target: pass — 候选题与原题完全相同，保留了人物识别目标及搬书进屋的事件范围。
- removals_justified: pass — 候选题未删除或改写原题信息，短文也未变化。
- same_language: pass — 原题与候选题均使用中文；本题没有选项。
- naturalness: 0/3 — “是谁把书搬进屋里的？”是自然、直接的中文人物询问句。
- processing: 0/3 — 单句直接询问明确动作的施事者，没有跨句指代、角色嵌套或选项比较负担。
- context_economy: 0/3 — 题干只保留识别目标事件所需的动作、对象和目的地，没有额外背景或可删除的叙事链。

## hard:t1_acts20:f988:mcq

Status: KEPT

Target (inferred): 理解保罗一直讲到午夜的原因是他准备第二天离开。

未提供非空的 intended_target、original_question 或 original_answer，因此目标依据当前问题与预期答案保守推断，不代表已获研究者明确确认的设计意图。所供经文20:7明确说：由于保罗第二天准备离开，他与他们交谈，并一直讲到午夜。这支持预期答案及所问因果关系。问题中没有可安全归为可删除描述性铺垫的内容。

- r1 / tested: 为什么 — 问题明确询问因果关系；回答必须说明原因，而非仅指出人物或复述讲谈事件。
- r2 / tested: 一直讲到午夜 — 这是因果问题所指定的结果及其时间范围；仅解释保罗为何交谈，不能完整保留当前问题的目标。
- r3 / anchor: 保罗 — 用于确定被询问的讲谈事件及其行动者；问题并非要求辨认讲谈者是谁。

### Proposal 1: KEPT

保罗为什么一直讲到午夜？

原问题已简洁直接；人物、因果提问及“一直讲到午夜”的时间范围均须保留，没有可安全删除的铺垫。
- A. 因为他打算第二天离开
- B. 因为他在庆祝节期
- C. 因为他在等人
- D. 因为楼上的房间里有许多灯

Verification 1: PASS
- contract_validity: pass — 契约准确保留原题的因果目标：解释保罗为何一直讲到午夜，而非只辨认人物或时间。经文20:7明确将第二天准备离开与交谈持续到午夜联系起来。
- same_target: pass — 候选题与原题完全相同，保留保罗这一行动者、讲到午夜这一结果，以及询问原因的关系；正确答案仍包含第二天离开的计划。
- removals_justified: pass — 候选题未删除或改动原题及选项中的信息，不存在因删减造成的范围变化或竞争事件。
- same_language: pass — 问题和全部选项均保持原有中文表述。
- naturalness: 0/3 — 题干中文自然直接，四个选项均以“因为”引出原因，表达流畅。
- processing: 0/3 — 题干明确指出人物和目标事件，选项结构简明平行，没有复杂指代或修饰关系需要解码。
- context_economy: 0/3 — 题干没有附加故事铺垫；人物、持续性和午夜时间均用于界定所问的因果事件，选项也无多余叙述。

Verification 2: PASS
- contract_validity: pass — 契约准确保留原题的因果目标：解释保罗为何持续讲到午夜，原因是他准备第二天离开。经文20:7明确支持这一关系；保罗是事件主体而非待辨认的答案。
- same_target: pass — 候选题与原题完全一致，保留了原因问法、讲谈持续到午夜的结果事件，以及第二天准备离开的必需答案内容。
- removals_justified: pass — 候选题未删除或改写原题及选项中的任何信息。
- same_language: pass — 问题及四个选项均保持原来的中文，文字未变。
- naturalness: 0/3 — 问句简洁自然，四个原因选项表达通顺，无需语言修补。
- processing: 0/3 — 题干直接指定人物、事件和时间终点；选项结构平行，没有复杂指代或额外关系比较负担。
- context_economy: 0/3 — 题干只包含确定因果目标所需的人物和事件，没有多余叙事或铺垫。“一直讲到午夜”是所问结果的必要范围。

## control:escape:required_relation

Status: KEPT

Target (explicit): Identify the people overpowered by the possessed man who subsequently escaped injured. The link between being overpowered by that man and then escaping injured is explicitly part of the tested relationship and must remain in the question.

19:14将参与驱魔的人指明为士基瓦的七个儿子；19:16用“他们”承接这群人，并叙述他们被制服、受伤逃出房子的经过，因此固定答案有支持。问题未要求回答他们赤身裸体或此前如何驱魔，这些细节不属于必需回答内容。

- r1 / tested: 被那附着邪灵的人制服以后 — 显式目标明确要求保留被制服与随后受伤逃出之间的联系，因此这不是可删除的背景叙述。
- r2 / tested: 谁 — 身份辨认是问题直接要求的回答内容；本段支持的身份是士基瓦的七个儿子。
- r3 / tested: 受伤逃出了那房子 — 受伤逃出是显式目标指定的后续事件，用来限定所问的是哪些人；不能只保留被制服而删去这一结果。

### Proposal 1: KEPT

被那附着邪灵的人制服以后，谁受伤逃出了那房子？

原问题已直接、简洁地询问人物身份；被制服与随后受伤逃出房子的联系均为测试内容，没有可实质删减的背景关系。

Verification 1: PASS
- contract_validity: pass — 契约符合原题和显式目标：辨认被附着邪灵的人制服、随后受伤逃出房子的同一群人。19:14和19:16支持答案为士基瓦的七个儿子；无需在答案中另行复述经过。
- same_target: pass — 候选题与原题完全相同，保留了被制服与随后受伤逃出的关系，以及辨认这些人身份的要求。
- removals_justified: pass — 候选题没有删除或改动原题信息。
- same_language: pass — 原题与候选题均为中文；本题无选项。
- naturalness: 0/3 — 问句完整、自然，前置时间关系与“谁”的身份询问衔接清楚。
- processing: 0/3 — 单句直接询问同一群人的身份，施事、受事及事件顺序清晰，没有额外的指代链或选择比较负担。
- context_economy: 0/3 — 被制服后受伤逃出的关系是显式测试目标，属于必要限定而非可删背景；问题没有添加无关叙述。

Verification 2: PASS
- contract_validity: pass — The contract matches the explicit intended target and the original question: identify the same people who were overpowered by the possessed man and then escaped injured. Verses 19:14–16 support the identity and event sequence.
- same_target: pass — The candidate question is unchanged and retains both the identity question and the required link between being overpowered and subsequently escaping injured.
- removals_justified: pass — No information was removed from the question or passage.
- same_language: pass — The question remains in Chinese. There are no options.
- naturalness: 0/3 — The Chinese question is grammatical and direct; the opening temporal clause connects naturally to the identity question.
- processing: 0/3 — The agent, affected people, and event sequence are readily parsed. The temporal relation is necessary to the explicit target rather than avoidable processing load.
- context_economy: 0/3 — The question contains only the required event relationship and the identity request. The opening clause is explicitly tested, not dispensable setup.

## control:necessary_time

Status: KEPT

Target (explicit): Identify who left before the meal, preserving the before/after distinction.

所供短文明确写道“吃饭前，小林离开了”，支持固定答案“小林”；“吃饭后，小周也离开了”构成时间对照。目标与问题及答案一致，没有可删除的描述性铺垫。

- r1 / tested: 吃饭前 — 明确目标要求保留饭前与饭后的区别；该时间条件也区分了文中的两次离开事件，不能删除。
- r2 / tested: 谁离开了 — 问题要求回答离开者的身份，并以离开事件限定所问行为；必须结合饭前这一时间条件确定人物。

### Proposal 1: KEPT

吃饭前，谁离开了？

原问题已简洁直接。“吃饭前”是区分两次离开事件的必要时间条件，不能删除；没有可移除的铺垫。

Verification 1: PASS
- contract_validity: pass — 合同与明确目标、原题及短文一致：须识别饭前离开的人，保留饭前与饭后的时间区别。答案是小林，不要求另行解释时间对照。
- same_target: pass — 候选题与原题完全相同，保留了人物识别、离开行为及“吃饭前”的必要时间限定。
- removals_justified: pass — 没有删除任何信息；用于区分两次离开事件的时间条件完整保留。
- same_language: pass — 候选问题与原题均为中文；本题无选项。
- naturalness: 0/3 — 问句中文自然、直接，时间短语与疑问表达搭配顺畅。
- processing: 0/3 — 问句结构简短清楚，没有指代链、角色混淆或多余修饰；饭前这一条件是目标所必需。
- context_economy: 0/3 — 问题仅包含必要的时间限定及人物识别要求，没有可删除的叙事铺垫。

Verification 2: PASS
- contract_validity: pass — The contract correctly identifies the target as the person who left before the meal. Its temporal condition and departure-role relation match the original question, explicit intended target, and passage. The required answer is 小林, distinguished from 小周, who left afterward.
- same_target: pass — The candidate preserves the original question exactly, including 吃饭前, which is essential to selecting the correct departure event.
- removals_justified: pass — No information was removed.
- same_language: pass — The question remains in Chinese. There are no options.
- naturalness: 0/3 — The Chinese question is idiomatic and direct.
- processing: 0/3 — The question has a simple temporal modifier followed by a clear request to identify the person who left.
- context_economy: 0/3 — There is no dispensable setup. The before-meal condition is necessary to distinguish the two departures.

## control:necessary_event

Status: KEPT

Target (inferred): 识别在被人制服后受伤逃出房子的人。

未提供明确的 intended_target，也没有更早的原题或原答案，因此目标为保守推断，而非已获研究者确认的设计意图。所给文本中，小林与小周均受伤逃出房子，只有小周还被描述为被另一个人制服，故固定答案“小周”有文本支持。题中的“那个人”未要求辨认制服者的身份。没有可安全删除的描述性条件。

- r1 / tested: 谁 — 作答必须指出人物，而不是只复述发生了什么。
- r2 / anchor: 被那个人制服后 — 这是区分两次受伤逃出房子事件的必要条件：小林和小周都受伤逃出了房子，但只有小周被描述为先被人制服。题目并非单独询问制服事件或时间顺序，但这一限定不能删除。
- r3 / tested: 受伤逃出了房子 — 这规定了身份识别所针对的事件及人物状态；答案须对应这一事件，并结合被制服的限定确定人物。

### Proposal 1: KEPT

谁被那个人制服后，受伤逃出了房子？

“被那个人制服后”是区分两名受伤逃出房子者的必要限定，不能删除；原题已简洁直接，无可安全删除的关系。

Verification 1: PASS
- contract_validity: pass — 契约符合原题和文本：须识别被人制服后受伤逃出房子的人。小林和小周均受伤逃出，只有小周被描述为先被制服，因此该限定是必要的区分条件，固定答案为小周。
- same_target: pass — 候选题与原题完全相同，保留了人物识别目标、被制服的先行条件，以及受伤逃出房子的事件范围。
- removals_justified: pass — 候选题没有删除或改写任何原题信息。
- same_language: pass — 原题和候选题均为中文；本题没有选项。
- naturalness: 0/3 — 问句符合中文表达习惯，人物、被动关系和后续动作表达直接清楚。
- processing: 0/3 — 单句即可清楚解析，动作围绕同一待识别人物展开，没有额外的指代链或角色切换。
- context_economy: 0/3 — 没有额外叙事铺垫；被制服的限定用于区分两个都受伤逃出房子的人，其他描述明确所问事件。

Verification 2: PASS
- contract_validity: pass — 契约符合原题及短文：要求识别被人制服后受伤逃出房子的人，答案为小周。小林也受伤逃出房子，因此“被那个人制服后”是必要的区分条件，不能将目标缩减为一般的逃出者识别。
- same_target: pass — 候选题与原题完全相同，保留了人物识别、被制服的限定以及受伤逃出房子的事件范围。
- removals_justified: pass — 候选题没有删除或改动原题信息。
- same_language: pass — 候选题保持原题的中文；本题无选项。
- naturalness: 0/3 — 题干表达自然，直接询问符合事件条件的人物，没有需要修补理解的措辞。
- processing: 0/3 — 被动结构和“后”表达的先后关系清楚，整体是简短、易解析的单句提问。
- context_economy: 0/3 — 题干没有额外叙事或冗余指代链；被制服的条件用于区分两名逃出者，受伤逃出房子则界定目标事件，均有实际作用。

## control:direct:en

Status: KEPT

Target (explicit): Identify who left.

The passage explicitly states, "Mara left." This supports the expected answer, Mara, and matches the explicit intended target. "Levi stayed" provides contrast but is not a separately requested answer component.

- r1 / tested: Who left? — The question directly tests the identity of the person who left. The passage contains only one leaving event, so no additional identifying anchor is needed.

### Proposal 1: KEPT

Who left?

The question already asks directly about the target event with minimum sufficient wording.

Verification 1: PASS
- contract_validity: pass — The explicit target is to identify who left. The passage states "Mara left.", supporting the required participant and action relation.
- same_target: pass — The candidate retains the original question unchanged and tests the identity of the person who left.
- removals_justified: pass — No information was removed.
- same_language: pass — The question remains in English; there are no options.
- naturalness: 0/3 — "Who left?" is idiomatic and direct.
- processing: 0/3 — The question has a simple structure with no reference or role-tracking burden.
- context_economy: 0/3 — The question directly asks for the target participant and contains no unnecessary setup.

Verification 2: PASS
- contract_validity: pass — The explicit target is to identify who left. The passage states "Mara left," supporting the required answer component and the contract's tested participant–action relation.
- same_target: pass — The candidate retains the exact question "Who left?" and tests the same identity, action, and scope.
- removals_justified: pass — Nothing was removed or changed.
- same_language: pass — The question remains in English; there are no options.
- naturalness: 0/3 — "Who left?" is idiomatic and direct.
- processing: 0/3 — The question is readily parsed and has no reference chain, modifiers, or choice-comparison burden.
- context_economy: 0/3 — The question directly asks for the target participant and contains no unnecessary setup.

## control:unsupported_answer

Status: HOLD_TARGET

Target (explicit): Identify why Xiaolin left.

所供经文为“小林离开了。经文没有说明原因。”，明确未提供离开的原因。固定答案“因为下雨了。”没有经文支持，因此不能建立可用的固定答案契约，状态为 hold。

- r1 / tested: 为什么 — 原因是问题明确要求的内容，不能改成仅识别人物或确认离开这一事实。
- r2 / anchor: 小林 — 用于确定所问原因所属的人物及事件。
- r3 / tested: 离开了 — 离开是所问因果关系中的结果，也是目标明确指定的事件范围。
