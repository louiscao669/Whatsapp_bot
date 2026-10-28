# Hard 66 Chinese QA wording audit

Scope: every record in evaluation/datasets/qa/tier1_hard66_canonical; qualitative inspection of Chinese stems, MCQ choices, English open answers and review metadata. Not a new external-model judgment or full passage-grounded correctness audit. No source questions were changed.

66 question IDs; 65 retained; one retained item is MCQ-only (64 open + 65 MCQ = 129 active forms). Open and MCQ stem differences: 0. Retained-item review categories: {'Moderate': 16, 'No salient issue': 20, 'Review': 21, 'Priority': 8}.

Priority = strongest wording/structural concern; Review = possible ambiguity, cueing or answer-option burden; Moderate = observable construction, not a defect by itself; No salient issue = no obvious wording problem on this inspection. Proposed issues require validation against displayed context and intended target.

| # | Item | Status / format | Chinese question | Assessment | Observation |
|---|---|---|---|---|---|
| 1 | uw-t1_1kgs13:0887 | open + MCQ | 谁必在这坛上把那些烧香的祭司献为祭？ | Moderate | Long modified object plus 把 construction; biblical sacrificial wording. |
| 2 | uw-t1_1kgs13:9a0c | open + MCQ | 王吩咐人捉拿谁？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 3 | uw-t1_1kgs13:a6cd | open + MCQ | 王求神人为他祷告，谁为王祷告了？ | Review | Lead-in 王求神人为他祷告 strongly cues 神人 as the answer before passage consultation; this can reduce diagnostic value. |
| 4 | uw-t1_1kgs13:4661 | open + MCQ | 神人为什么不肯跟王回去？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 5 | uw-t1_1kgs13:ec63 | open + MCQ | 带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？ | Priority | Relative clause 带他回来的 plus reporting frame 宣告, negation 必不得 and repeated 他; referent tracking and archaic wording. |
| 6 | uw-t1_1kgs13:8a66 | open + MCQ | 谁在路上被狮子咬死了？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 7 | uw-t1_1kgs13:2f00 | open + MCQ | 带他回来的先知先把神人的尸首带到哪里？ | Review | Relative clause 带他回来的 plus 把 and sequencing 先; initial 他 depends on context. Keep actor identity and first-event target when rewriting. |
| 8 | uw-t1_1kgs13:e302 | MCQ only | 这些事以后，耶罗波安仍然不肯做什么？ | Review | Existing MCQ-only restriction: open question is underbounded. These events and negation add context dependence. |
| 9 | uw-t1_2chr26:9aab | open + MCQ | 犹大全体百姓立乌西雅，是为了什么？ | Review | 立乌西雅 leaves the role unstated and asks an awkward purpose question; options carry long causative constructions. |
| 10 | uw-t1_2chr26:4cb0 | open + MCQ | 谁教导乌西雅敬畏神？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 11 | uw-t1_2chr26:1cab | open + MCQ | 神帮助乌西雅攻打哪些人？ | Review | Stem is straightforward but four three-group option lists impose substantial entity discrimination and reading load. |
| 12 | uw-t1_2chr26:1fc4 | open + MCQ | 谁爱好土地，所以设立了农夫和葡萄园工人？ | Moderate | Two linked propositions with 所以; 爱好土地 is marked wording. Not automatically invalid. |
| 13 | uw-t1_2chr26:723e | open + MCQ | 这三十万七千五百训练有素的军队由谁统领？ | Review | Large written-out number and modifier 训练有素 before 军队; passive-like 由谁统领. Unnecessary quantity load unless identifying the army requires it. |
| 14 | uw-t1_2chr26:eb1d | open + MCQ | 祭司亚撒利亚和八十位祭司跟随谁进了耶和华的殿？ | Moderate | Long coordinated subject and follow-plus-enter event sequence; no deeply nested clause. |
| 15 | uw-t1_2chr26:f9a9 | open + MCQ | 乌西雅自己为什么急忙出去？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 16 | uw-t1_2chr26:9860 | open + MCQ | 乌西雅被埋葬以后，发生了什么事？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 17 | uw-t1_2kgs11:a99f | open + MCQ | 谁和他的奶母在耶和华的殿里藏了六年？ | Moderate | 他的 referent is the questioned person; relationship plus duration. Check comprehension without simplifying away the relationship. |
| 18 | uw-t1_2kgs11:5bea | open + MCQ | 谁被吩咐要为王看守耶和华的殿？ | Review | Passive instruction plus embedded purpose; correct option 那两班安息日不值勤的 is elliptical and negated. |
| 19 | uw-t1_2kgs11:b13a | open + MCQ | 谁把枪和盾牌交给了百夫长？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 20 | uw-t1_2kgs11:d4f4 | open + MCQ | 亚他利雅为什么出来到耶和华的殿中见众人？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 21 | uw-t1_2kgs11:df0e | open + MCQ | 耶何耶大吩咐百夫长，要杀死哪些人？ | Review | Correct option 凡跟随她的人 has an unnamed female referent; name Athaliah if preserving the intended target allows. |
| 22 | uw-t1_2kgs11:f49c | open + MCQ | 耶何耶大立的第一个约，是在哪些之间立的？ | Priority | 在哪些之间 is incomplete/unnatural phrasing. First covenant presupposes an ordering of covenants; distinguish participant sets carefully. |
| 23 | uw-t1_2kgs11:8730 | open + MCQ | 城中为什么安静了？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 24 | uw-t1_2kgs6_7:c343 | open + MCQ | 那官怀疑以利沙的话，以利沙怎样回答他？ | Moderate | Two-clause reporting frame and pronoun; quoted options require speaker attribution. |
| 25 | uw-t1_2kgs6_7:9cf3 | open + MCQ | 四个长大麻风的人说坐在这里也必死，之后他们决定怎么做？ | Priority | Reported proposition 坐在这里也必死 inside a temporal sequence; 这里 and 他们 require tracking. Long setup partly supplies passage content. |
| 26 | uw-t1_2kgs6_7:5bba | open + MCQ | 叙利亚人以为谁要来攻击他们？ | Moderate | Embedded belief proposition under 以为; paired ruler lists increase option load. |
| 27 | uw-t1_2kgs6_7:3452 | open + MCQ | 长大麻风的人承认做得不对以后，打算怎么做？ | Moderate | Temporal clause plus embedded judgment 承认做得不对; open-ended action question. |
| 28 | uw-t1_2kgs6_7:6138 | open + MCQ | 百姓出去掠夺叙利亚营之前，刚发生了什么事？ | Review | Before plus 刚 demands an immediate-predecessor event and exact event segmentation. |
| 29 | uw-t1_2kgs6_7:2ac1 | open + MCQ | 百姓在城门口践踏了谁？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 30 | uw-t1_2kgs6_7:fe00 | open + MCQ | 她们约定哪一天吃另一个妇人的儿子？ | Review | 她们 and 另一个妇人 are context dependent; 今天/昨天/明天 require the temporal viewpoint of the quotation, not the participant’s day. |
| 31 | uw-t1_2kgs6_7:ea44 | open + MCQ | 两个妇人先吃了谁的孩子？ | Review | 先 and 两个妇人 require distinguishing participants; correct option uses a relative clause 向王呼喊的那个妇人. |
| 32 | uw-t1_2kgs6_7:5e57 | open + MCQ | 以利沙称谁为“杀人犯”？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 33 | uw-t1_2sam21:de9f | open + MCQ | 亚比筛击杀了谁？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 34 | uw-t1_2sam21:761c | open + MCQ | 在迦特的这四个拉法的后裔，被谁杀死了？ | Moderate | Fronted locative, long nominal modifier and passive; entity burden is separate from syntax. |
| 35 | uw-t1_acts19:7628 | open + MCQ | 被那附着邪灵的人制服以后，谁受伤逃出了那房子？ | Priority | Fronted passive temporal clause 被那附着邪灵的人制服以后 contains a relative modifier; delayed 谁 makes role tracking demanding. |
| 36 | uw-t1_acts19:9b0c | open + MCQ | 行邪术的人把书拿出来以后，接着做了什么？ | Moderate | Temporal clause with 把 plus sequencing 接着; reasonable if sequence is the intended target. |
| 37 | uw-t1_acts20:f988 | open + MCQ | 保罗为什么一直讲到午夜？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 38 | uw-t1_acts20:9b52 | open + MCQ | 保罗离开之前，最后做的是什么？ | Review | Before plus 最后 requires defining the final event; legitimate sequence target but check passage window and event boundaries. |
| 39 | uw-t1_acts23:a1ba | open + MCQ | 他们要请谁把保罗带到公会那里？ | Review | 他们 has no named referent; request + causative 把保罗带到 creates multiple actor roles. |
| 40 | uw-t1_acts23:f57c | open + MCQ | 按保罗的话，谁有话要告诉军长？ | Review | 按保罗的话 reporting frame; correct option 这个年轻人 relies on deixis/context. |
| 41 | uw-t1_acts23:5613 | open + MCQ | 埋伏的人动手之前，还在等什么？ | Moderate | Temporal modifier plus waiting-for-event target; distinguishes agreement from subsequent delivery. |
| 42 | uw-t1_acts23:2b9c | open + MCQ | 军长吩咐谁去预备护送的队伍？ | Moderate | Instruction plus purpose chain 吩咐…去预备; not deeply nested. |
| 43 | uw-t1_acts23:9035 | open + MCQ | 这封信是谁写的？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 44 | uw-t1_acts23:058f | open + MCQ | 第二天谁回到了兵营？ | Review | 第二天 is context dependent and 士兵们 may be interpreted broadly enough to include cavalry; contrast should be checked against wording in the passage. |
| 45 | uw-t1_judg17_18:9f00 | open + MCQ | 谁咒诅了被偷的银子？ | Priority | 谁咒诅了被偷的银子 reads as cursing the silver itself. Verify whether source means a curse concerning the theft/thief; semantic target may be distorted. |
| 46 | uw-t1_judg17_18:7713 | open + MCQ | 但支派的人为什么要寻找地业居住？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 47 | uw-t1_judg17_18:ac64 | excluded | 母亲说谁要用这银子制作雕像？ | Excluded | Already excluded; do not count this as a current test item. |
| 48 | uw-t1_judg17_18:725d | open + MCQ | 他们请谁为他们求问这趟行程？ | Review | 他们…为他们 leaves both groups implicit; 求问这趟行程 is awkwardly compressed. Request plus consultation introduces multiple roles. |
| 49 | uw-t1_judg17_18:c60a | open + MCQ | 那少年利未人为什么离开伯利恒？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 50 | uw-t1_judg17_18:1654 | open + MCQ | 来士的人为什么富足？ | Review | Why the people are wealthy may impose a causal reading rather than a directly stated relation; requires source/window verification. |
| 51 | uw-t1_judg17_18:1fd1 | open + MCQ | 米迦为什么认为耶和华必向他施恩？ | Moderate | Embedded belief proposition plus archaic 必向他施恩; why scope and biblical vocabulary require attention. |
| 52 | uw-t1_judg17_18:c2d9 | open + MCQ | 谁进去拿走了雕像、以弗得、家用神像和熔铸的偶像？ | Review | Four-object list with specialized terms 以弗得/熔铸的偶像. Stem structure is manageable; lexical/list load is high. |
| 53 | uw-t1_judg17_18:3162 | open + MCQ | 那些神像最先发生了什么事？ | Priority | 那些神像最先发生了什么事 is unnatural topic wording; 最先 has no explicit starting point. Existing window override also matters. |
| 54 | uw-t1_judg17_18:616b | open + MCQ | 是什么使但人转过身来？ | Review | Correct option has long place-modified subject; near-causal distractor 被…追上 may invite competing causal explanations. Check specificity of evidence. |
| 55 | uw-t1_judg17_18:3250 | open + MCQ | 为什么没有人搭救来士的人？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 56 | uw-t1_judg17_18:97e8 | open + MCQ | 约拿单和他的子孙作但支派的祭司，直到什么时候？ | Review | Long coordinated subject and temporal endpoint; option D uses archaic correlative wording. This is option burden as much as stem syntax. |
| 57 | uw-t1_judg9:c232 | open + MCQ | 亚比米勒请谁把他的话转告示剑的众首领？ | Moderate | Request plus 把 reporting chain and repeated 他; several participant roles. |
| 58 | uw-t1_judg9:6d68 | open + MCQ | 约坦呼叫示剑的众首领听他的话，是为了什么结果？ | Priority | 呼叫…听他的话 plus 是为了什么结果 is awkward purpose/result wording; the target is not transparently stated in the question. |
| 59 | uw-t1_judg9:8e0b | open + MCQ | 橄榄树为什么不肯去作树木的王？ | Review | Stem is fairly direct but figurative context and correct option 离开那荣耀神和人的油 add interpretation and relative-clause load. |
| 60 | uw-t1_judg9:c5c7 | open + MCQ | 众人在做什么的时候咒诅亚比米勒？ | Moderate | Temporal slot 在做什么的时候; vocabulary 咒诅 is separate from syntax. |
| 61 | uw-t1_judg9:1246 | open + MCQ | 谁暗暗打发人去见亚比米勒？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 62 | uw-t1_judg9:f36a | open + MCQ | 迦勒第一次说有人来时，西布说他看见的其实是什么？ | Priority | Temporal clause with embedded speech followed by another speech clause and 他看见的 nominalization; pronoun and viewpoint tracking. |
| 63 | uw-t1_judg9:e935 | open + MCQ | 亚比米勒听到什么消息后设下埋伏？ | Moderate | Temporal dependency 听到什么消息后; depends on ordering of report and ambush. |
| 64 | uw-t1_judg9:79d0 | open + MCQ | 城楼上的人是怎么死的？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 65 | uw-t1_judg9:0bd2 | open + MCQ | 亚比米勒来到楼门，是要做什么？ | No salient issue | Direct, manageable wording; this does not establish textual validity or ease of answering. |
| 66 | uw-t1_judg9:a602 | open + MCQ | 谁被他的甲士刺死了？ | Moderate | Passive plus subject-dependent possessor 他的; 甲士 is uncommon vocabulary. |
