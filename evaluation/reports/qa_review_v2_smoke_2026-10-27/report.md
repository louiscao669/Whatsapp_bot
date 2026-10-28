# QA review: content validity and language accessibility

Version: qa_review_v2. Model: gpt-6.1-sol. Stage: final_translation. Repeats: 2.

Model judgments are screening evidence, not measured human difficulty. Disagreement or incomplete review requires review. No questions were edited or removed.

| Item | Decision | Repeated decisions |
|---|---|---|
| hard:t1_2kgs11:f49c:mcq | REWRITE | REWRITE, REWRITE |
| hard:t1_acts19:7628:mcq | REWRITE | REWRITE, REWRITE |
| hard:t1_acts20:f988:mcq | KEEP | KEEP, KEEP |
| gold:t1_2chr26:ryq4:open | KEEP | KEEP, KEEP |
| transfer:handkerchief:original:zh | REWRITE | REWRITE, REWRITE |
| transfer:handkerchief:repair:zh | REWRITE | REWRITE, REWRITE |
| transfer:handkerchief:repair:en | REVIEW | REVIEW, REVIEW |
| focus:handkerchief:direct:zh | KEEP | KEEP, KEEP |
| constructed:leak | HOLD_CONTENT | HOLD_CONTENT, HOLD_CONTENT |
| constructed:direct | KEEP | KEEP, KEEP |
| constructed:anchor | KEEP | KEEP, KEEP |
| constructed:ambiguous | HOLD_CONTENT | HOLD_CONTENT, HOLD_CONTENT |

## hard:t1_2kgs11:f49c:mcq

耶何耶大立的第一个约，是在哪些之间立的？

A. 耶和华、王和百姓
B. 王和百夫长
C. 耶和华和守卫
D. 王和百姓

**Run 1: REWRITE**

- Content / target_preservation: not_applicable — No original item or explicit intended target is supplied.
- Content / question_support: pass — Verse 17 describes one covenant involving the Lord, king, and people, followed by another involving king and people.
- Content / answer_support: pass — The expected answer lists the three parties named with Jehoiada in the first covenant statement.
- Content / answer_uniqueness: pass — The first-covenant qualifier distinguishes this group from the king and people named in the second covenant.
- Content / context_sufficiency: pass — Both covenant statements are displayed in sequence, allowing the first to be identified.
- Content / answer_leakage: pass — The question identifies Jehoiada and the first covenant without listing the requested parties.
- Content / mcq_validity: pass — A matches the first covenant's named parties. B introduces centurions not mentioned here. C incorrectly includes guards. D corresponds to the second covenant, not the full first-covenant group.
- Structure / nested_modifier: ordinary — 耶何耶大立的第一个约: 修饰结构较短，立约者与顺序限定共同确定所问的约。
- Structure / reference_chain: ordinary — 第一个约: 区分两次立约是题目语义目标所需的关系。
- Structure / option_overlap: ordinary — 耶和华、王和百姓: 列表较短，重合部分对应两次立约之间需要辨认的参与方差异。
- Language / naturalness: 2/3 — “是在哪些之间立的” is markedly unnatural because “哪些” lacks an expressed category for the parties to the covenant. Combined with “耶何耶大立的第一个约” and the repeated “立”, it requires the reader to mentally supply the missing nominal relationship.
- Language / processing: 1/3 — The reader must interpret “哪些之间” as asking for participating parties, then compare short lists such as “耶和华、王和百姓” and “王和百姓”. The wording needs repair, but the repair and list comparison remain local rather than creating substantial structural load.
- Language / context_economy: 0/3 — “耶何耶大” and “第一个约” identify the covenant under discussion. The ordinal is useful disambiguation, not excess setup.

**Run 2: REWRITE**

- Content / target_preservation: not_applicable — No original question, original answer, or explicit intended target is supplied.
- Content / question_support: pass — Verse 17 describes one covenant involving the Lord, king, and people, followed by another involving the king and people.
- Content / answer_support: pass — The first covenant statement explicitly names '耶和华、王和百姓'.
- Content / answer_uniqueness: pass — The qualifier '第一个约' distinguishes the requested group from the king and people named in the second covenant.
- Content / context_sufficiency: pass — Both covenant statements and their order appear in verse 17.
- Content / answer_leakage: pass — The question identifies the covenant-maker and sequence, not the requested parties.
- Content / mcq_validity: pass — A gives the first covenant's named group. D gives the second covenant's group; B and C introduce unsupported combinations.
- Structure / nested_modifier: ordinary — 耶何耶大立的第一个约: 这一限定用于区分经文中的两个约，是目标所需。
- Structure / option_overlap: ordinary — 耶和华、王和百姓: 列表重合对应第一次与第二次立约的关键参与方差别，比较负荷有限且与目标直接相关。
- Language / naturalness: 2/3 — “是在哪些之间立的”中的“哪些”缺少自然的指称中心，读者需要补出“哪些人／哪些方”。“耶何耶大立的第一个约”本身可以理解。
- Language / processing: 1/3 — 需将“第一个约”定位到先出现的立约事件，再比较“耶和华、王和百姓”与“王和百姓”等短列表。“哪些之间”虽需补足理解，但没有形成多层角色或修饰负担。
- Language / context_economy: 0/3 — “耶何耶大立的第一个约”用于区分两次立约，属于必要限定，没有多余引言。

## hard:t1_acts19:7628:mcq

被那附着邪灵的人制服以后，谁受伤逃出了那房子？

A. 那附着邪灵的人
B. 保罗
C. 以弗所的希腊人
D. 士基瓦的七个儿子

**Run 1: REWRITE**

- Content / target_preservation: not_applicable — No original item or explicit intended target is supplied.
- Content / question_support: pass — Verse 16 says the possessed man overpowered them and they fled the house injured.
- Content / answer_support: pass — Verse 14 identifies the men performing the exorcism as Sceva's seven sons; verse 16 describes their flight.
- Content / answer_uniqueness: pass — The fleeing group is the seven sons, not the attacker or Paul.
- Content / context_sufficiency: pass — Verses 14–16 provide the antecedent for the people attacked and fleeing.
- Content / answer_leakage: pass — The question supplies the event but not the fleeing group's identity.
- Content / mcq_validity: pass — D identifies the attacked group. A is the attacker; B is mentioned in the invocation, not as fleeing; C is not identified in this passage as participating.
- Structure / nested_modifier: ordinary — 被那附着邪灵的人制服以后: 修饰语用于识别攻击者，结构较短，并服务于所问事件关系。
- Structure / role_tracking: ordinary — 被那附着邪灵的人制服以后，谁受伤逃出了那房子？: 角色转换正是题目要求识别的关系；被动结构本身不构成额外负担。
- Structure / reference_chain: ordinary — 那附着邪灵的人: 人物与群体的对应是回答此题所必需的指称关系。
- Language / naturalness: 2/3 — “那附着邪灵的人”, repeated in option A, has an unnatural attachment: “附着邪灵的” makes the person sound like the entity bearing or attaching the spirit rather than clearly expressing possession. The reader must mentally repair this wording.
- Language / processing: 2/3 — In “被那附着邪灵的人制服以后，谁受伤逃出了那房子？”, the reader must repair the person–spirit relationship inside the agent phrase, then assign that person as the attacker and “谁” as both the person overpowered and the person fleeing. The awkward modifier adds avoidable role-decoding work beyond the intended event relationship.
- Language / context_economy: 0/3 — “被……制服以后” and “受伤逃出了那房子” identify the relevant event and participants. The difficulty is wording and role attachment, not excess contextual detail.

**Run 2: REWRITE**

- Content / target_preservation: not_applicable — No original question, original answer, or explicit intended target is supplied.
- Content / question_support: pass — Verse 16 says the possessed man overpowered them and they fled the house injured.
- Content / answer_support: pass — Verse 14 identifies the men as Sceva's seven sons; verses 15–16 continue the same encounter.
- Content / answer_uniqueness: pass — The injured fugitives are the seven sons, not the possessed man or Paul.
- Content / context_sufficiency: pass — Verses 14–16 supply both the participants and the outcome of the encounter.
- Content / answer_leakage: pass — The question names the event but does not identify those who fled.
- Content / mcq_validity: pass — D is supported. A is the attacker, B is only mentioned in the exchange, and C is not identified in this passage as participating.
- Structure / nested_modifier: ordinary — 被那附着邪灵的人制服以后: 修饰语用于识别制服七个儿子的人，结构服务于目标事件的区分。
- Structure / role_tracking: ordinary — 被那附着邪灵的人制服以后，谁受伤逃出了那房子？: 被制服者与逃走者的同一关系正是题目要求识别的关系。
- Structure / reference_chain: ordinary — 那附着邪灵的人: 需要跨经文句子确认人物，但没有额外引入不必要的指代层级。
- Language / naturalness: 2/3 — “那附着邪灵的人”中“人”与“附着邪灵”的搭配不自然，容易先被理解为人使邪灵附着，而非人被邪灵附着；选项A又重复这一说法，需要读者自行修复关系。
- Language / processing: 2/3 — 读者须先在“被那附着邪灵的人制服以后”中修复施事内部的附着关系，再区分制服者与受伤逃走者。后一个角色区分属于目标，但前一个修复是可避免的额外负担。
- Language / context_economy: 0/3 — “被……制服以后”用于限定所问的逃走事件，“那房子”提供地点联系，没有明显多余的背景。

## hard:t1_acts20:f988:mcq

保罗为什么一直讲到午夜？

A. 因为他打算第二天离开
B. 因为他在庆祝节期
C. 因为他在等人
D. 因为楼上的房间里有许多灯

**Run 1: KEEP**

- Content / target_preservation: not_applicable — No original item or explicit intended target is supplied.
- Content / question_support: pass — Verse 7 connects Paul's planned departure the next day with his conversation continuing until midnight.
- Content / answer_support: pass — The expected answer repeats the explicit reason introduced by 由于.
- Content / answer_uniqueness: pass — Only the next-day departure is stated as the reason for the extended speaking.
- Content / context_sufficiency: pass — Verse 7 supplies both the event and its reason.
- Content / answer_leakage: pass — The question identifies the speaking event but does not state its reason.
- Content / mcq_validity: pass — A gives the stated reason. B's festival and C's waiting for someone are unsupported. D mentions actual lamps but incorrectly treats them as the reason.
- Structure / reference_chain: ordinary — 因为他打算第二天离开: 回指对象明确，时间关系是识别所问原因的一部分。
- Language / naturalness: 0/3 — “保罗为什么一直讲到午夜？” and the options beginning with “因为” are idiomatic. “因为楼上的房间里有许多灯” is also a naturally formed clause.
- Language / processing: 1/3 — The reader connects “他” in options A–C to “保罗” and interprets “第二天” relative to the gathering. These are ordinary, manageable reference operations; the options are short and parallel.
- Language / context_economy: 0/3 — “一直讲到午夜” identifies the event whose reason is requested. No separate or unnecessary setup precedes the question.

**Run 2: KEEP**

- Content / target_preservation: not_applicable — No original question, original answer, or explicit intended target is supplied.
- Content / question_support: pass — Verse 7 explicitly connects Paul's planned departure the next day with his speaking until midnight.
- Content / answer_support: pass — '由于保罗第二天准备离开' directly supports the expected reason.
- Content / answer_uniqueness: pass — Only the next-day departure is given as the reason for Paul's extended speaking.
- Content / context_sufficiency: pass — Verse 7 contains the speaker, action, time, and reason.
- Content / answer_leakage: pass — The question states the action and asks for its cause without supplying that cause.
- Content / mcq_validity: pass — A states the explicit reason. B and C are unsupported; D describes the room but is not given as a cause.
- Structure / reference_chain: ordinary — 因为他打算第二天离开: 人物和时间回指简短，且都是识别离开计划这一原因所必需的关系。
- Language / naturalness: 0/3 — “保罗为什么一直讲到午夜？”直接自然，选项“因为他打算第二天离开”等也采用一致、常见的原因表达。
- Language / processing: 1/3 — 需要把选项中的“他”对应到保罗，并以讲话当天定位“第二天”；人物和时间联系都短而明确，属于普通的原因理解。
- Language / context_economy: 0/3 — “一直讲到午夜”明确所问行为及其持续时间，没有附加无关背景。

## gold:t1_2chr26:ryq4:open

What did Uzziah build at Jerusalem's gates?


**Run 1: KEEP**

- Content / target_preservation: not_applicable — No original item or explicit intended target is supplied.
- Content / question_support: pass — Verse 9 says Uzziah built towers in Jerusalem at the Corner Gate and Valley Gate.
- Content / answer_support: pass — The expected answer identifies towers, the requested structure. Its wording 'corner gates' is imprecise, but the core answer matches verse 9.
- Content / answer_uniqueness: pass — Towers are the only structures described as built by Uzziah at those gates.
- Content / context_sufficiency: pass — The Jerusalem gate location distinguishes these towers from the wilderness towers and other building projects.
- Content / answer_leakage: pass — The question names the builder and location without identifying the structure.
- Content / mcq_validity: not_applicable — This is an open question.
- Language / naturalness: 0/3 — “What did Uzziah build at Jerusalem's gates?” is idiomatic and direct.
- Language / processing: 0/3 — “What did Uzziah build” clearly requests an object; “at Jerusalem's gates” supplies a straightforward location without competing attachments.
- Language / context_economy: 0/3 — “at Jerusalem's gates” economically identifies the building activity being asked about. There is no additional setup.

**Run 2: KEEP**

- Content / target_preservation: not_applicable — No original question, original answer, or explicit intended target is supplied.
- Content / question_support: pass — Verse 9 states that Uzziah built towers at the Corner Gate and Valley Gate in Jerusalem.
- Content / answer_support: pass — The expected answer identifies towers, the requested structure. Its loose location wording does not change that answer.
- Content / answer_uniqueness: pass — Towers are the structures explicitly built at the gates; cisterns and military devices are described in other settings.
- Content / context_sufficiency: pass — Verse 9 directly identifies the builder, structures, and gate locations.
- Content / answer_leakage: pass — The question supplies the builder and location but not the type of structure.
- Content / mcq_validity: not_applicable — This is an open question.
- Language / naturalness: 0/3 — “What did Uzziah build at Jerusalem's gates?” is a direct, idiomatic English question.
- Language / processing: 0/3 — “What did Uzziah build” asks directly for the object, and “at Jerusalem's gates” supplies a short location restriction. There is no embedded clause or reference chain.
- Language / context_economy: 0/3 — “at Jerusalem's gates” usefully identifies the building event; the question contains no additional setup.

## transfer:handkerchief:original:zh

当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？

A. 病人陷入了深度睡眠
B. 疾病和邪灵离开了病人
C. 犹太驱魔师给病人驱魔
D. 病人变得无法说话
E. 根据这段文字无法判断

**Run 1: REWRITE**

- Content / target_preservation: pass — The question asks for the outcome when the cloths reached the patients, preserving the intended outcome target.
- Content / question_support: pass — Verse 12 describes the handkerchiefs and aprons being taken to the sick and the resulting departures.
- Content / answer_support: pass — The expected answer repeats the outcome stated in verse 12.
- Content / answer_uniqueness: pass — The departures of illnesses and spirits constitute the single stated compound outcome of this event.
- Content / context_sufficiency: pass — The cloths and patients identify verse 12 rather than the later exorcism incident.
- Content / answer_leakage: pass — The question states the occasion, not what happened to the patients.
- Content / mcq_validity: pass — B matches verse 12. A and D are unsupported. C concerns the separate exorcists' activity, not this event's outcome. E contradicts the explicit outcome.
- Structure / nested_modifier: potential_burden — 当触摸过保罗的手帕和围裙被带到病人那里时: 物品修饰、被动运输和时间框架层层嵌套，而目标只要求识别病人的变化。
- Structure / role_tracking: potential_burden — 触摸过保罗的手帕和围裙被带到病人那里: 需先处理目标之外的物品关系和角色转换，才能转向病人的结果。
- Structure / delayed_query: potential_burden — 当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？: 主问之前集中放置了多项关系，增加了识别实际所问内容之前的处理量。
- Language / naturalness: 2/3 — “触摸过保罗的手帕和围裙” is awkward: “保罗的手帕和围裙” initially invites a possessive reading, while the intended structure makes the cloths the things that “触摸过保罗”. This inanimate use of “触摸” further increases the need for mental repair.
- Language / processing: 2/3 — In “当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？”, the reader may initially read “保罗的手帕” as the object of “触摸过”, then must reattach “触摸过保罗的” to both cloth nouns when reaching “被带到”. That repaired phrase must then be integrated into the passive and the outer “当……时” clause. This is avoidable parsing work beyond identifying the patients' outcome.
- Language / context_economy: 1/3 — The transport event in “被带到病人那里” provides an anchor, but “触摸过保罗的手帕和围裙” supplies some removable object detail before the outcome question. The main difficulty is structural rather than the amount of context.

**Run 2: REWRITE**

- Content / target_preservation: pass — The question asks for the result when the cloths reached the sick, retaining the intended patient-outcome target.
- Content / question_support: pass — Verse 12 explicitly links the cloths being taken to the sick with illnesses and evil spirits leaving.
- Content / answer_support: pass — The expected answer directly reproduces the outcome stated in verse 12.
- Content / answer_uniqueness: pass — The specified event has one stated compound result: illnesses and evil spirits left the patients.
- Content / context_sufficiency: pass — The reference to Paul's handkerchiefs and aprons uniquely anchors the event in verse 12.
- Content / answer_leakage: pass — The question supplies the triggering event, not the requested result.
- Content / mcq_validity: pass — B is explicitly supported. A and D are not stated, C belongs to the separate exorcist episode, and E is false because the result is given.
- Structure / nested_modifier: potential_burden — 当触摸过保罗的手帕和围裙被带到病人那里时: 时间框架内又嵌入带边界歧义的修饰结构；这些物品识别操作超出了病人变化这一目标。
- Structure / delayed_query: potential_burden — 当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？: 实际询问位于多层背景之后，且未在开头明确病人是结果焦点，增加了提前解析和保持背景的负荷。
- Structure / role_tracking: potential_burden — 触摸过保罗的手帕和围裙被带到病人那里: 题目先聚焦物品的角色，再要求选择病人的变化；这一角色转换并非目标本身所需的全部结构。
- Language / naturalness: 2/3 — “触摸过保罗的手帕和围裙”容易读成有人触摸保罗所属的物品；若按预期修饰物品，则“手帕和围裙”作“触摸过”的主体也不自然，需要读者修复。
- Language / processing: 2/3 — 读者需保持“当……时”框架，重切“触摸过保罗的手帕和围裙”，接续“被带到病人那里”，最后才读到“发生了什么”。边界修复与未闭合时间框架叠加，形成可避免的负担。
- Language / context_economy: 1/3 — “被带到病人那里”有助于定位事件，但前面的物品名称和接触细节增加了询问病人结果所不必展开的背景；背景尚未主导整道题。

## transfer:handkerchief:repair:zh

摸过保罗的手帕和围裙被带到病人那里。病人随后怎么样了？

A. 病人陷入了深度睡眠
B. 疾病和邪灵离开了病人
C. 犹太驱魔师给病人驱魔
D. 病人变得无法说话
E. 根据这段文字无法判断

**Run 1: REWRITE**

- Content / target_preservation: pass — The question retains the patients' subsequent condition as its target; the cloths are only an event anchor.
- Content / question_support: pass — Verse 12 states that the cloths were taken to the sick and that diseases and spirits then left them.
- Content / answer_support: pass — The expected answer directly matches the stated outcome for the patients.
- Content / answer_uniqueness: pass — The text gives one compound outcome: illnesses and evil spirits leaving.
- Content / context_sufficiency: pass — The introductory sentence uniquely identifies the relevant patients and event.
- Content / answer_leakage: pass — The introduction describes delivery of the cloths but does not disclose the patients' subsequent condition.
- Content / mcq_validity: pass — B is explicit in verse 12. A and D are not stated. C describes a different group's attempted activity rather than these patients' outcome. E is ruled out by the explicit statement.
- Structure / nested_modifier: potential_burden — 摸过保罗的手帕和围裙被带到病人那里。: 物品接触保罗这一嵌入关系并非所测目标，却仍需在读到结果问句前解析。
- Structure / role_tracking: potential_burden — 摸过保罗的手帕和围裙被带到病人那里。病人随后怎么样了？: 目标只询问病人的结果，但前句要求先跟踪额外的接触和运输关系。
- Structure / delayed_query: potential_burden — 摸过保罗的手帕和围裙被带到病人那里。病人随后怎么样了？: 句号没有消除前置关系的处理量；实际所问内容仍出现在整段设置之后。
- Structure / reference_chain: ordinary — 病人随后怎么样了？: 时间承接明确，直接连接所问结果与前述事件。
- Language / naturalness: 2/3 — “摸过保罗的手帕和围裙” invites an initial reading of someone having touched “保罗的手帕和围裙”. Making the cloths themselves the subject of “摸过保罗” is awkward and requires reinterpretation. “病人随后怎么样了？” is natural.
- Language / processing: 2/3 — At “摸过保罗的手帕和围裙被带到”, readers may have to abandon the initial possessive reading of “保罗的手帕” and rebuild the cloths as both the things that touched Paul and the objects being transported. The sentence break does not remove this avoidable attachment repair.
- Language / context_economy: 1/3 — The first sentence anchors “随后”, but “摸过保罗的手帕和围裙” includes some removable object-identifying detail before the question about the patients. This is minor excess context; the larger burden comes from its wording.

**Run 2: REWRITE**

- Content / target_preservation: pass — The question asks what subsequently happened to the sick, preserving the intended outcome target.
- Content / question_support: pass — Verse 12 describes the handkerchiefs and aprons being taken to the sick, followed by the stated change.
- Content / answer_support: pass — Verse 12 explicitly says '疾病和邪灵就离开了他们'.
- Content / answer_uniqueness: pass — Healing and departure of evil spirits form the single compound outcome stated for these patients.
- Content / context_sufficiency: pass — The opening event anchor clearly identifies the patients and outcome in verse 12.
- Content / answer_leakage: pass — The question states the cloths' arrival but does not reveal what happened to the patients.
- Content / mcq_validity: pass — B reproduces the stated outcome. A and D are absent; C confuses the separate exorcist episode with these patients; E is false because verse 12 answers directly.
- Structure / nested_modifier: potential_burden — 摸过保罗的手帕和围裙被带到病人那里。: 修饰语内部的“保罗的手帕”可触发所属关系的先行切分，需要重新确定边界；辨认物品的接触关系又不是所问的病人结果。
- Structure / role_tracking: potential_burden — 摸过保罗的手帕和围裙被带到病人那里。病人随后怎么样了？: 在询问病人变化之前先建立物品中心的多个角色，增加了相对于目标可避免的焦点转换。
- Structure / delayed_query: potential_burden — 摸过保罗的手帕和围裙被带到病人那里。病人随后怎么样了？: 实际询问置于包含接触和运送关系的完整背景句之后，分成两句仍需先完成这些解析。
- Language / naturalness: 2/3 — “摸过保罗的手帕和围裙”容易先切分为“摸过〔保罗的手帕和围裙〕”；要将其理解为物品接触过保罗，又需接受手帕、围裙作“摸过”的主体，明显不自然。“病人随后怎么样了？”本身自然。
- Language / processing: 2/3 — 读者到“被带到病人那里”时可能才发现主语应是物品，需要回头重切“摸过保罗的手帕和围裙”，再转向病人的变化。修饰边界修复与焦点转换叠加，是可避免的负担；选项本身较短。
- Language / context_economy: 1/3 — “被带到病人那里”可作为事件定位，但“摸过保罗的手帕和围裙”详细交代物品及接触过程，超出询问病人变化所需的简短背景。

## transfer:handkerchief:repair:en

Cloths that had touched Paul were taken to the sick. What happened to the sick?


**Run 1: REVIEW**

- Content / target_preservation: pass — The cloths provide an event anchor, while the question still requests the outcome for the sick people.
- Content / question_support: pass — Verse 12 says handkerchiefs and aprons that touched Paul were taken to the sick.
- Content / answer_support: pass — The passage says their illnesses were cured and evil spirits left. Diseases 'leaving' is a harmless paraphrase of their being cured.
- Content / answer_uniqueness: pass — Healing and departure of evil spirits are the explicit compound outcome.
- Content / context_sufficiency: pass — The cloths and sick people uniquely anchor the question to verse 12.
- Content / answer_leakage: pass — The introductory sentence gives the preceding event, not its outcome.
- Content / mcq_validity: not_applicable — This is an open question.
- Structure / nested_modifier: potential_burden — Cloths that had touched Paul were taken to the sick.: The object-identifying relative clause adds an embedded relationship that is not itself being tested; the target is the sick people's outcome.
- Structure / role_tracking: potential_burden — Cloths that had touched Paul were taken to the sick. What happened to the sick?: The setup introduces several object and participant roles before a question that only asks about the sick people's change.
- Structure / delayed_query: potential_burden — Cloths that had touched Paul were taken to the sick. What happened to the sick?: Splitting the setup and question does not remove the need to process the additional relationships before the actual ask.
- Language / naturalness: 0/3 — “Cloths that had touched Paul were taken to the sick. What happened to the sick?” is grammatical, idiomatic English. Repeating “the sick” makes the question's focus explicit.
- Language / processing: 1/3 — The reader integrates “that had touched Paul” into the subject of “were taken”, then shifts to the recipients in “What happened to the sick?” The short relative clause and explicit repetition make these ordinary, manageable operations.
- Language / context_economy: 1/3 — “Cloths that had touched Paul were taken to the sick” gives an event anchor, but the contact detail “that had touched Paul” adds some removable setup to a question focused on the sick people's outcome. The excess is minor, not dominating.
- Structural concern without a failed burden dimension: review required.

**Run 2: REVIEW**

- Content / target_preservation: pass — The question asks what happened to the sick, rather than asking about the cloths or their destination.
- Content / question_support: pass — Verse 12 states that cloths that touched Paul were taken to the sick and describes what happened to them.
- Content / answer_support: pass — Verse 12 says their illnesses were cured and evil spirits left them; diseases 'leaving' harmlessly paraphrases being cured.
- Content / answer_uniqueness: pass — The passage gives one compound outcome for these sick people: healing and departure of evil spirits.
- Content / context_sufficiency: pass — The cloths anchor uniquely identifies the sick people in verse 12, distinguishing them from the later injured sons.
- Content / answer_leakage: pass — The opening sentence supplies the event anchor but does not state either outcome.
- Content / mcq_validity: not_applicable — This is an open question.
- Structure / nested_modifier: potential_burden — Cloths that had touched Paul were taken to the sick.: The embedded contact event must be parsed before reaching the patient-outcome question, although identifying the cloths is not the stated target.
- Structure / role_tracking: potential_burden — Cloths that had touched Paul were taken to the sick. What happened to the sick?: The respondent traverses an object-centered setup with several roles before answering about the patients; that role shift adds load beyond the outcome target.
- Structure / delayed_query: potential_burden — Cloths that had touched Paul were taken to the sick. What happened to the sick?: The actual ask follows a complete setup containing both an embedded event and a passive event; the sentence boundary does not remove that advance processing.
- Language / naturalness: 0/3 — “Cloths that had touched Paul were taken to the sick” and “What happened to the sick?” are idiomatic. “The sick” is a conventional expression for sick people.
- Language / processing: 1/3 — The reader parses the short modifier “that had touched Paul,” then follows the cloths to their recipients. Repeating “the sick” in the question makes the shift to the patients explicit, so the demand remains manageable.
- Language / context_economy: 0/3 — “Cloths that had touched Paul were taken to the sick” identifies the episode whose patient outcome is being asked about. It is a brief, useful event anchor rather than excessive framing.
- Structural concern without a failed burden dimension: review required.

## focus:handkerchief:direct:zh

根据这段经文，病人的情况有什么变化？

A. 病人陷入了深度睡眠
B. 疾病和邪灵离开了病人
C. 犹太驱魔师给病人驱魔
D. 病人变得无法说话
E. 根据这段文字无法判断

**Run 1: KEEP**

- Content / target_preservation: pass — The question asks about the patients' changed condition rather than the objects or their destination.
- Content / question_support: pass — Verse 12 explicitly describes a change in the sick people's condition.
- Content / answer_support: pass — Verse 12 states that diseases and evil spirits left them.
- Content / answer_uniqueness: pass — The two departures form the stated compound outcome for the sick people.
- Content / context_sufficiency: pass — The sick people are explicitly identified in verse 12; the later injured exorcists are a different group.
- Content / answer_leakage: pass — The question asks for the change without describing it.
- Content / mcq_validity: pass — B states verse 12's outcome. A and D are absent. C describes exorcists' activity rather than the stated change in these patients. E is false because the outcome is explicit.
- Language / naturalness: 0/3 — “根据这段经文，病人的情况有什么变化？” is idiomatic. The options, including “疾病和邪灵离开了病人” and “病人变得无法说话”, are clearly formed statements.
- Language / processing: 0/3 — “病人的情况有什么变化” establishes the focus immediately. Each option can be read independently, without nested modifiers, difficult pronouns, or closely interlocking lists.
- Language / context_economy: 0/3 — “根据这段经文” is a brief source cue, and “病人的情况” directly identifies the subject of the question. There is no unnecessary narrative setup.

**Run 2: KEEP**

- Content / target_preservation: pass — Asking how the patients' condition changed preserves the intended focus on their outcome.
- Content / question_support: pass — Verse 12 explicitly describes a change in the sick people's condition.
- Content / answer_support: pass — The expected answer matches '疾病和邪灵就离开了他们'.
- Content / answer_uniqueness: pass — Only verse 12 describes the outcome for people called '病人'; the later injured men are a separate group.
- Content / context_sufficiency: pass — The term '病人' identifies the group in verse 12 sufficiently, even without repeating the cloths event.
- Content / answer_leakage: pass — The question asks for a change without stating either component of it.
- Content / mcq_validity: pass — B is explicit in verse 12. A and D are unsupported; C concerns a different episode; E is contradicted by the stated outcome.
- Language / naturalness: 0/3 — “根据这段经文，病人的情况有什么变化？”自然直接。选项“疾病和邪灵离开了病人”等表述完整，没有明显的搭配或修饰问题。
- Language / processing: 0/3 — 主问句直接把“病人的情况”设为焦点；各选项均为短陈述，不需要先解析物品关系或跨句转换角色。
- Language / context_economy: 0/3 — “根据这段经文”是简短的依据提示，没有展开无关背景，其余文字直接询问变化。

## constructed:leak

小林把书搬进屋里。是谁把书搬进屋里的？


**Run 1: HOLD_CONTENT**

- Content / target_preservation: pass — The question still asks for the agent who moved the books inside.
- Content / question_support: pass — The passage explicitly says 小林 moved the books inside.
- Content / answer_support: pass — 小林 is the stated agent of the action.
- Content / answer_uniqueness: pass — Only 小林 moves the books; 小周 remains at the doorway.
- Content / context_sufficiency: pass — The action and its agent are explicitly identified.
- Content / answer_leakage: fail — The introduction says '小林把书搬进屋里,' directly supplying the name requested immediately afterward.
- Content / mcq_validity: not_applicable — This is an open question.
- Language / naturalness: 0/3 — Both “小林把书搬进屋里” and “是谁把书搬进屋里的？” are idiomatic Chinese sentences.
- Language / processing: 0/3 — The repeated “把书搬进屋里” uses the same simple action structure in both sentences. No complex reference resolution or syntactic repair is needed.
- Language / context_economy: 1/3 — “小林把书搬进屋里。” repeats the action immediately before “是谁把书搬进屋里的？”. This adds a short, removable introductory sentence without helping readers interpret the wording.

**Run 2: HOLD_CONTENT**

- Content / target_preservation: pass — The question still asks for the person who moved the books inside.
- Content / question_support: pass — The passage explicitly says Xiaolin moved the books inside.
- Content / answer_support: pass — '小林' is the stated actor in '小林把书搬进屋里'.
- Content / answer_uniqueness: pass — Only Xiaolin moves books; Xiaozhou stays at the doorway.
- Content / context_sufficiency: pass — The passage identifies the actor and distinguishes Xiaozhou's different action.
- Content / answer_leakage: fail — The question begins '小林把书搬进屋里', directly supplying the requested person's name.
- Content / mcq_validity: not_applicable — This is an open question.
- Language / naturalness: 0/3 — “小林把书搬进屋里”和“是谁把书搬进屋里的”都是自然的汉语句式；重复不造成语法或搭配问题。
- Language / processing: 0/3 — 两句沿用“把书搬进屋里”这一简单事件结构，第二句只聚焦行动者，没有复杂回指或角色转换。
- Language / context_economy: 1/3 — “小林把书搬进屋里。”在提问前完整重述同一事件，对理解“是谁把书搬进屋里的？”没有增加必要的限定，是一处简短但可移除的重复。

## constructed:direct

是谁把书搬进屋里的？


**Run 1: KEEP**

- Content / target_preservation: pass — The question preserves the action, inward destination, and requested agent.
- Content / question_support: pass — The passage states that 小林 moved the books inside.
- Content / answer_support: pass — The expected answer 小林 is explicitly named as the mover.
- Content / answer_uniqueness: pass — 小周 stayed at the doorway and is not described as moving the books.
- Content / context_sufficiency: pass — There is only one event involving moving books inside.
- Content / answer_leakage: pass — The question identifies the action without naming its agent.
- Content / mcq_validity: not_applicable — This is an open question.
- Language / naturalness: 0/3 — “是谁把书搬进屋里的？” is an idiomatic Chinese focus question.
- Language / processing: 0/3 — “是谁” directly requests the actor, and “把书搬进屋里” clearly specifies one action, its object, and its destination.
- Language / context_economy: 0/3 — “是谁把书搬进屋里的？” contains only the information needed to identify the action being asked about, with no additional setup.

**Run 2: KEEP**

- Content / target_preservation: pass — The final question asks exactly who performed the targeted action.
- Content / question_support: pass — The passage states that someone moved the books inside: Xiaolin.
- Content / answer_support: pass — The passage explicitly attributes moving the books inside to Xiaolin.
- Content / answer_uniqueness: pass — Xiaolin alone performs this action; Xiaozhou remains at the doorway.
- Content / context_sufficiency: pass — The action and its actor are fully specified.
- Content / answer_leakage: pass — The question does not name the person who moved the books.
- Content / mcq_validity: not_applicable — This is an open question.
- Language / naturalness: 0/3 — “是谁把书搬进屋里的？”是自然的行动者焦点问句。
- Language / processing: 0/3 — “谁”“书”“屋里”分别清楚标示行动者空位、搬运对象和终点，单句即可直接解析。
- Language / context_economy: 0/3 — “把书搬进屋里”提供识别行动所需的信息，没有额外铺垫。

## constructed:anchor

谁把书带到图书馆？


**Run 1: KEEP**

- Content / target_preservation: pass — The question retains the action, destination, and request for the person's identity.
- Content / question_support: pass — The passage states that 小周 took books to the library in the afternoon.
- Content / answer_support: pass — 小周 is explicitly the person who took the books to the library.
- Content / answer_uniqueness: pass — 小林 took books to school, not the library; only 小周 fits.
- Content / context_sufficiency: pass — The library destination uniquely identifies the relevant event.
- Content / answer_leakage: pass — The question does not supply the person's name.
- Content / mcq_validity: not_applicable — This is an open question.
- Language / naturalness: 0/3 — “谁把书带到图书馆？” is a natural, direct Chinese question.
- Language / processing: 0/3 — “谁” identifies the requested person, while “把书带到图书馆” clearly marks the object and destination in one simple action.
- Language / context_economy: 0/3 — “书” and “图书馆” specify the action being asked about; the question contains no excess introduction.

**Run 2: KEEP**

- Content / target_preservation: pass — The question preserves both the action and the destination, the library.
- Content / question_support: pass — The passage states that Xiaozhou took books to the library in the afternoon.
- Content / answer_support: pass — '小周' is explicitly the actor in the library event.
- Content / answer_uniqueness: pass — Only Xiaozhou takes books to the library; Xiaolin takes books to school.
- Content / context_sufficiency: pass — The destination in the question uniquely selects the afternoon event.
- Content / answer_leakage: pass — The question gives the destination but does not identify the actor.
- Content / mcq_validity: not_applicable — This is an open question.
- Language / naturalness: 0/3 — “谁把书带到图书馆？”是自然、直接的汉语问句，不必添加体标记才能成立。
- Language / processing: 0/3 — “谁”直接询问行动者，“把书带到图书馆”明确对象和终点，没有嵌套或代词解析。
- Language / context_economy: 0/3 — “图书馆”用于限定所问事件，其余内容也都直接服务于提问。

## constructed:ambiguous

谁把书带走了？


**Run 1: HOLD_CONTENT**

- Content / target_preservation: fail — The question omits the library destination and asks only who took books away, broadening the target to either transport event.
- Content / question_support: pass — Both described events involve someone taking books to another place, so the general action is supported.
- Content / answer_support: pass — 小周 did take books to another location, making the expected answer defensible, though not uniquely established.
- Content / answer_uniqueness: fail — 小林 also took books elsewhere, so both 小林 and 小周 defensibly answer the unqualified question.
- Content / context_sufficiency: fail — No destination or time distinguishes the morning school event from the afternoon library event.
- Content / answer_leakage: pass — The question supplies neither person's name.
- Content / mcq_validity: not_applicable — This is an open question.
- Language / naturalness: 0/3 — “谁把书带走了？” is a natural Chinese question.
- Language / processing: 0/3 — “谁把书带走了” presents one actor, one object, and a familiar resultative verb phrase. No wording repair or complex structural tracking is required.
- Language / context_economy: 0/3 — “谁把书带走了？” contains no introductory framing or removable contextual detail.

**Run 2: HOLD_CONTENT**

- Content / target_preservation: fail — The final question omits the library destination and asks only who took books away, losing the condition that distinguishes Xiaozhou's action.
- Content / question_support: pass — Both taking books to school and taking them to the library support the general description of taking books away.
- Content / answer_support: pass — Xiaozhou did take books to the library, so the expected name is a supported answer, though not uniquely selected.
- Content / answer_uniqueness: fail — Xiaolin and Xiaozhou both transport books, so either name is defensible under the destination-free wording.
- Content / context_sufficiency: fail — The question supplies neither destination nor time to distinguish the morning school event from the afternoon library event.
- Content / answer_leakage: pass — The question does not supply either person's name.
- Content / mcq_validity: not_applicable — This is an open question.
- Language / naturalness: 0/3 — “谁把书带走了？”是自然完整的汉语问句，“带走了”的搭配没有措辞问题。
- Language / processing: 0/3 — 句子只含一个行动者空位和一个“把”字结构；“带走了”可以直接解析，不涉及嵌套、角色切换或复杂回指。
- Language / context_economy: 0/3 — “谁把书带走了？”没有附加背景或重复说明；未明说终点不属于背景过多的问题。
