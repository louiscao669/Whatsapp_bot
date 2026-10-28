# Whole-item burden prompt results

Two repetitions per prompt. Provisional labels are not independent human judgments. All prompts were frozen before this experiment’s model calls; prompts were developed from prior examples. Fresh corpus items are new to model trials, not an independently labelled test set.

## hard:t1_1kgs13:a6cd:mcq

王求神人为他祷告，谁为王祷告了？

Group: previous_borderline

**previous_wording_gate, run 1: KEEP**
The setup “王求神人为他祷告” contains one request with an embedded action, followed by the direct question “谁为王祷告了？” “他” clearly refers to the king. The setup identifies the requested actor without itself asserting who actually prayed; there is no second request layer or unresolved referent.


**previous_wording_gate, run 2: KEEP**
前半句“王求神人为他祷告”只有一层请求内容，后半句直接询问实际祷告者；只需跟踪王和神人两个角色。“他”明确指王，选项中的地点修饰语也没有嵌套。请求本身并未陈述谁实际完成祷告。


**whole_item_rubric, run 1: KEEP**
虽有轻微重复，但请求与实际行动的区别清楚，负担可接受。
naturalness=1: “祷告”连续出现两次略显重复，但整句仍自然可懂。; processing=1: 需区分王提出请求与有人实际祷告，两者衔接直接，人物关系清楚。; context=0: “王求神人为他祷告”提供相关事件背景，有助于定位。; leakage=0: 说王请求神人祷告，并未断言神人实际照做，因此没有直接给出所问事实。

**whole_item_rubric, run 2: KEEP**
背景提供轻微提示，但没有直接给出实际行动的答案，整体可保留。
naturalness=0: “王求神人为他祷告，谁为王祷告了”表达清楚，前后衔接自然。; processing=0: 请求与实际行动的关系简单明确，选项中的人物描述简短。; context=0: 王请求祷告的背景能够定位所问事件，没有多余叙述。; leakage=1: “王求神人”会提示神人可能是行动者，但请求本身并未说明神人实际作了祷告。

**target_preserving_comparison, run 1: KEEP**
请求与实际行动的区别清楚，背景有助于定位事件，无须仅因重复而改写。
naturalness=0: “王求神人为他祷告，谁为王祷告了”是自然可懂的事件提问。; processing=1: 需要区分王提出请求与有人实际祷告；两个短分句的关系容易掌握。; context=0: 王的请求提供相关事件背景，重复“为王祷告”没有造成实质负担。; leakage=0: “王求神人”只说明请求对象，并未断言该对象实际为王祷告。

**target_preserving_comparison, run 2: KEEP**
请求的背景不等于提供实际行动的答案；整体清楚、负担可管理。
naturalness=0: “王求神人为他祷告，谁为王祷告了”表达自然，前半句定位请求，后半句询问实际行动者。; processing=1: 需区分请求和实际祷告这两个相关动作，但角色清楚，选项结构简单。; context=0: 王提出祷告请求的背景有助于定位事件，没有明显无关信息。; leakage=0: “王求神人为他祷告”只说明请求对象，并未断言神人实际祷告了。

**independent_dimensions, run 1: KEEP**
请求与实际行动的区别明确，背景适量，没有显著负担或直接泄露。
naturalness=0: “王求神人为他祷告，谁为王祷告了”是自然的事件承接问法。; processing=1: 需区分王提出请求与有人实际祷告两个环节，角色清楚，负担普通。; context=0: “王求神人为他祷告”提供适度的事件锚点，没有加入无关背景。; leakage=0: 请求神人祷告不等于已经说明神人实际祷告了；题干没有直接陈述所问结果。

**independent_dimensions, run 2: KEEP**
请求提供了一定线索，但没有直接陈述所问行动已经发生；整体负担较低。
naturalness=0: “王求神人为他祷告，谁为王祷告了”是自然可懂的事件提问。; processing=1: 需区分王提出请求与有人实际祷告两个动作；角色明确，重复“祷告”并未造成明显负担。; context=0: 王请求代祷这一简短背景足以定位事件。; leakage=1: “王求神人为他祷告”提示了可能的行动者，但请求神人祷告并不等于说明神人实际祷告了。

## hard:t1_1kgs13:ec63:mcq

带他回来的先知宣告，谁的尸首必不得入他列祖的坟墓？

Group: previous_concerns

**previous_wording_gate, run 1: REWRITE**
“带他回来的”先修饰宣告者“先知”，随后嵌入宣告内容，并以“必不得”作否定预告。前一个“他”指被带回的人，后一个“他”须随“谁”确定所属；虽可由上下文解出，但关系修饰、古雅否定和重复代词叠加，造成不必要的指代追踪。


**previous_wording_gate, run 2: REWRITE**
“带他回来的”作“先知”的定语，主句“宣告”又引出含“他列祖”的疑问内容。关系性人物描述叠加“必不得入”的古雅否定表达，需要反复辨认两个“他”的所指，且后一个“他”与所问的“谁”相联系，增加了不必要的指代负担。


**whole_item_rubric, run 1: KEEP**
虽有书面语和人物关系修饰，整题仍能清楚地区分宣告者与宣告对象。
naturalness=1: “尸首必不得入他列祖的坟墓”带有经文式书面语色彩，但句意清楚。; processing=1: 读者需要区分“带他回来的先知”和受宣告的人，但题干的“谁的尸首”及明确的人物选项使这种角色辨认仍属可管理的负担。; context=0: “带他回来的先知宣告”与坟墓的内容共同定位了经文中的宣告；“他”的所指可由上下文确定。; leakage=0: 题干说明宣告的内容，却没有说明这项宣告针对谁，而这正是所问的目标。

**whole_item_rubric, run 2: KEEP**
The role distinction and formal wording create manageable demand, not substantial avoidable burden.
naturalness=1: “尸首必不得入他列祖的坟墓” is formal biblical wording, but intelligible.; processing=1: Readers must distinguish the announcing prophet from the person addressed; the passage makes these roles clear.; context=0: “带他回来的先知宣告” usefully anchors the announcement without unnecessary setup.; leakage=0: The question identifies the announcement but does not identify whose body is meant.

**target_preserving_comparison, run 1: REWRITE**
改写保留宣告者、受宣告者的辨认目标及不得葬入祖坟的否定意义，同时减少代词回指和书面语解码负担。
naturalness=1: “尸首必不得入他列祖的坟墓”偏经文书面语，但基本可理解。; processing=2: 开头“带他回来的先知”要求先解析一个未点名的“他”，随后又需处理“谁的尸首”和“他列祖”；选项B还重复同一指代短语。改用直接的宣告问句可避免这些额外指代转换。; context=0: “先知宣告”及不得入祖坟的内容已经能定位事件；所给经文也明确区分先知和神人。; leakage=0: 题干给出宣告内容，但没有说明这项宣告针对谁。
Diagnostic alternative: 先知宣告，谁死后不能葬在自己祖先的坟墓里？
A. 耶罗波安
B. 带神人回来的先知
C. 神人的列祖
D. 从犹大来的神人 (preservation: preserved)

**target_preserving_comparison, run 2: KEEP**
The reference tracking is manageable and necessary to the identity question; no meaningful target-preserving simplification is needed.
naturalness=1: “尸首必不得入他列祖的坟墓” is formal biblical wording, but the question is understandable.; processing=1: Readers must distinguish the announcing prophet from the person addressed; “带他回来的先知” usefully identifies the speaker.; context=0: The announcement and its speaker sufficiently locate the event in the passage.; leakage=0: The question does not identify whose body is meant; that identity must be recovered from the passage.

**independent_dimensions, run 1: REWRITE**
主要问题是关系修饰与多个“他”的指代转换，而不是所问的宣告内容本身复杂。
naturalness=1: “尸首必不得入他列祖的坟墓”带有经文式书面语色彩，但意思可以理解。; processing=2: 先要解析“带他回来的先知”中先知与“他”的关系，再转向“谁的尸首”和“他列祖”的所属关系；选项B又重复同一关系修饰。首个“他”的追踪并非识别受宣告者所必需，增加了可避免的指代切换。; context=0: 先知宣告尸首不得入祖坟足以定位事件；没有缺少关键事件背景。; leakage=0: 题干说明宣告的内容，却未指出该宣告针对谁，因此没有给出所测试的身份。

**independent_dimensions, run 2: KEEP**
The references require ordinary contextual reading, with no substantial avoidable burden.
naturalness=0: “先知宣告，谁的尸首……” is a natural way to ask about the announcement.; processing=1: “带他回来的先知” requires resolving “他” and distinguishing the two prophets, but the passage supplies those roles clearly.; context=0: The announcement and its distinctive burial consequence uniquely locate the event.; leakage=0: The question states the announced consequence but does not identify whose body it concerns.

## hard:t1_1kgs13:8a66:mcq

谁在路上被狮子咬死了？

Group: previous_controls

**previous_wording_gate, run 1: KEEP**
A simple passive question, “谁…被狮子咬死了,” includes only the location “在路上.” The deepest option modifier is “从犹大来的” modifying “神人”; no unresolved referent or nested setup impedes reading.


**previous_wording_gate, run 2: KEEP**
单层被动问句，“谁”是被咬死者，“在路上”是地点状语，没有时间框架内的嵌套修饰。选项为人物名词短语，无未解决的指代。


**whole_item_rubric, run 1: KEEP**
The item clearly asks for one participant without avoidable wording burden.
naturalness=0: “谁在路上被狮子咬死了” is natural and direct.; processing=0: The question presents one event, and the choices are straightforward person labels.; context=0: “在路上被狮子咬死” sufficiently identifies the event in the passage.; leakage=0: The question identifies the event but does not name its victim.

**whole_item_rubric, run 2: KEEP**
事件锚定充分，问法和选项均无明显理解障碍。
naturalness=0: “谁在路上被狮子咬死了？”表达自然清楚。; processing=0: 一个简单的受事身份问题；四个选项均为简短人物称谓。; context=0: “在路上被狮子咬死”清楚定位了经文中的事件。; leakage=0: 题干描述事件，但没有透露死者身份。

**target_preserving_comparison, run 1: KEEP**
The wording provides sufficient event context with no meaningful avoidable burden.
naturalness=0: “谁在路上被狮子咬死了” is a natural, direct question.; processing=0: The question asks for one participant, and the choices are short person descriptions.; context=0: “在路上被狮子咬死” uniquely anchors the relevant event.; leakage=0: The question gives the event but does not identify its victim.

**target_preserving_comparison, run 2: KEEP**
人物询问直接，被动表达没有造成可避免的理解负担。
naturalness=0: “谁在路上被狮子咬死了？”自然、清楚。; processing=0: 被动结构直接突出所问的人；选项均为简短人物称谓。; context=0: “在路上被狮子咬死”足以定位目标事件。; leakage=0: 题干给出事件，但未说明死者身份。

**independent_dimensions, run 1: KEEP**
The item directly tests the victim's identity with sufficient context and no avoidable burden.
naturalness=0: “谁在路上被狮子咬死了” is a natural way to ask who was killed.; processing=0: The passive clearly identifies the lion as the attacker; the four person choices are easy to distinguish.; context=0: “在路上被狮子咬死” uniquely anchors the event in the passage.; leakage=0: The question identifies the event but does not name its victim.

**independent_dimensions, run 2: KEEP**
被动表达服务于人物辨认，没有造成额外解码负担。负担判断仍需受访者验证。
naturalness=0: “谁在路上被狮子咬死了？”符合自然汉语表达。; processing=0: 被动句清楚标明狮子是施事、所问人物是受事；选项均为简短人物称谓。; context=0: “在路上被狮子咬死”足以定位唯一事件，无须补充老先知的背景。; leakage=0: 题干指出死亡事件，但未给出死者身份。

## hard:t1_2chr26:4cb0:mcq

谁教导乌西雅敬畏神？

Group: previous_controls

**previous_wording_gate, run 1: KEEP**
A direct subject question with the embedded complement “乌西雅敬畏神” under “教导.” Both named participants are clear, with no unresolved referent.


**previous_wording_gate, run 2: KEEP**
“教导乌西雅敬畏神”包含一层教导内容，乌西雅是敬畏神的人；参与者明确，没有未明指代，问句和选项自然简短。


**whole_item_rubric, run 1: KEEP**
问题直接，背景充分，没有明显可避免的理解负担。
naturalness=0: “谁教导乌西雅敬畏神”自然、直接。; processing=0: 只需辨认一个教导者，四个姓名选项没有额外结构负担。; context=0: “乌西雅”和“教导……敬畏神”准确定位经文中的关系。; leakage=0: 题干未提供教导者的姓名。

**whole_item_rubric, run 2: KEEP**
问题清楚简洁，没有可避免的理解负担。
naturalness=0: “谁教导乌西雅敬畏神”措辞自然、直接。; processing=0: 只需识别教导者，人物关系明确，选项均为人名。; context=0: 明确点名乌西雅及教导内容，足以定位经文。; leakage=0: 题干没有提供教导者的姓名。

**target_preserving_comparison, run 1: KEEP**
表述已清楚简洁，没有可明显减轻且仍保持目标的负担。
naturalness=0: “谁教导乌西雅敬畏神”表达直接自然。; processing=0: 只需辨认一个教导者；四个人名选项不增加额外的关系判断。; context=0: 乌西雅及“教导……敬畏神”明确定位经文中的关系。; leakage=0: 题干未透露教导者的身份。

**target_preserving_comparison, run 2: KEEP**
已是自然、明确的目标保持问法。
naturalness=0: “谁教导乌西雅敬畏神”是惯常、直接的问法。; processing=0: 只需辨认教导者，四个人名选项不增加复杂的比较要求。; context=0: 乌西雅及“教导……敬畏神”已明确所问关系。; leakage=0: 题干未给出教导者。

**independent_dimensions, run 1: KEEP**
表达直接，定位充分，没有可避免的显著负担或答案泄露。
naturalness=0: “谁教导乌西雅敬畏神”是自然、直接的人物提问。; processing=0: 只需辨认教导者，人物关系明确，选项均为人名。; context=0: “乌西雅”和“教导……敬畏神”足以定位所问关系。; leakage=0: 题干没有提供教导者的名字。

**independent_dimensions, run 2: KEEP**
问题直接，背景适量，选项为容易区分的人名。
naturalness=0: “谁教导乌西雅敬畏神”简洁、自然。; processing=0: 只需辨认教导者；没有额外的角色转换或复杂选项比较。; context=0: 乌西雅及“教导……敬畏神”充分定位所问关系。; leakage=0: 题干未给出教导者姓名。

## hard:t1_2chr26:1cab:mcq

神帮助乌西雅攻打哪些人？

Group: previous_borderline

**previous_wording_gate, run 1: REWRITE**
主问句结构简单；选项中最深的结构是“住在……的”修饰族群，没有未明指代。但四个选项均为三项名单，反复交叉替换“亚扪人”“非利士人”及居住地点，要求逐项核对重叠名单，增加了不必要的解码负担。


**previous_wording_gate, run 2: REWRITE**
题干是“帮助乌西雅攻打哪些人”的简单结构，人物指代明确；选项却均为三项名单，其中又嵌入“住在……的”定语。“亚扪人”“非利士人”“米乌尼人”在不同组合中反复出现，并同时变换居住地点，造成过多的重叠名单比对负担。


**whole_item_rubric, run 1: REWRITE**
问题本身清楚，但整组选项造成了显著且可避免的多项组合比较负担。
naturalness=0: “神帮助乌西雅攻打哪些人”及各选项的列举方式都符合中文表达习惯。; processing=2: 四个选项各列三个人群，还夹有“住在……”的地点限定。A与D仅首个人群不同，B又更换居住地和末个人群，迫使读者反复逐项对照；这种组合比较负担可以减少。; context=0: 题干直接指向神帮助乌西雅作战的记载，没有多余铺垫或缺失的事件线索。; leakage=0: 题干没有列出被攻打的人群；正确组合出现在选项中本身不构成泄露。

**whole_item_rubric, run 2: KEEP**
The lists impose ordinary comparison demand appropriate to identifying several peoples.
naturalness=0: “神帮助乌西雅攻打哪些人？” and the parallel answer lists are natural Chinese.; processing=1: Readers compare three-group lists with some repeated names and location qualifiers; the parallel structure keeps this manageable.; context=0: God’s help and Uzziah’s fighting identify the relevant event without extra setup.; leakage=0: The stem does not identify any of the peoples; their appearance in the choices is not leakage.

**target_preserving_comparison, run 1: KEEP**
比较完整名单有一定正常阅读需求，但没有明确的、保留完整辨认目标又能显著减负的改写。
naturalness=0: “神帮助乌西雅攻打哪些人”自然明确，各选项都是平行的人群列表。; processing=1: 需要比较四组三项名单及其中的居住地限定，但列表结构一致，不必解开嵌套或含混的角色关系。; context=0: 题干明确限定为“神帮助”攻打的人，能与相邻经文中的进贡等事件区分。; leakage=0: 题干没有列出受攻击的人群；选项本身不构成答案泄露。

**target_preserving_comparison, run 2: KEEP**
The options require ordinary comparison of the answer's constituent groups; shortening them would risk changing the tested distinctions.
naturalness=0: “神帮助乌西雅攻打哪些人？” and the listed answers are natural Chinese.; processing=1: Readers must compare three-group lists and their location modifiers, but these distinctions constitute the requested identification rather than avoidable wording load.; context=0: God's help and Uzziah's fighting identify the relevant statement without unnecessary setup.; leakage=0: The stem supplies none of the targeted peoples; the correct list appearing among choices is not leakage.

**independent_dimensions, run 1: REWRITE**
目标本身可以包含多个人群，但选项反复重组族名与地名，使比较负担明显增加。
naturalness=0: “神帮助乌西雅攻打哪些人”及各选项的列举方式都合乎中文表达。; processing=2: 四个选项都列出三组人，还夹有居住地修饰。读者须逐项比较“非利士人／亚扪人”、阿拉伯人的所在地及末项族名；A、D仅首项不同，B又重组其他成分，造成可避免的多位置核对负担。; context=0: “神帮助乌西雅攻打”明确定位所问事件，没有多余背景。; leakage=0: 题干没有列出受攻击的人群；选项本身不构成答案泄露。

**independent_dimensions, run 2: REWRITE**
The stem is accessible, but the overlapping multi-part choices make the whole item unnecessarily demanding.
naturalness=0: “神帮助乌西雅攻打哪些人？” and the individual answer phrases are idiomatic.; processing=2: The choices require comparing four three-part lists while tracking both peoples and residence modifiers. A and D repeat “住在姑珥巴力的阿拉伯人和米乌尼人,” while B recombines “非利士人,” another location, and “亚扪人.” These overlapping bundles add substantial avoidable comparison load.; context=0: Naming God’s help and Uzziah’s fighting sufficiently locates the relevant statement.; leakage=0: The stem does not identify the peoples; their appearance among the choices is not leakage.

## hard:t1_2chr26:723e:mcq

这三十万七千五百训练有素的军队由谁统领？

Group: previous_borderline

**previous_wording_gate, run 1: REWRITE**
The main “由谁统领” question has the heavily modified subject “这三十万七千五百训练有素的军队,” whose deepest modifier is “训练有素的.” The numeral runs directly into that modifier without a suitable counting expression, making the subject unnatural and requiring mental repair. “这” points to the passage’s army; no participant referent is unresolved.


**previous_wording_gate, run 2: REWRITE**
主句采用“军队由谁统领”的被动结构，主语内叠加数量和“训练有素”的修饰。“这三十万七千五百训练有素的军队”将人数直接修饰“军队”，缺少合适的计量或连接成分，读者须自行修补。所指军队明确，无未解决的指代。


**whole_item_rubric, run 1: REWRITE**
The army description requires grammatical repair in Chinese, although the intended question remains recoverable.
naturalness=2: “这三十万七千五百训练有素的军队” unnaturally attaches a headcount directly to “军队”; readers must mentally supply something like “名士兵组成的”.; processing=1: The long numeral and commander choices are manageable, though the missing counting expression briefly disrupts the noun phrase.; context=0: The headcount and “训练有素” identify the relevant army without unnecessary setup.; leakage=0: The question identifies the army but does not disclose who commanded it.

**whole_item_rubric, run 2: REWRITE**
人数与“军队”的搭配明显不自然，需修整措辞；不是因为数字较长或使用被动问法而要求重写。
naturalness=2: “这三十万七千五百训练有素的军队”把人数直接接到“军队”上，缺少合适的计数单位或中心词，需要读者自行补足理解。; processing=1: 完整人数和“训练有素”都放在“军队”前，增加少量阅读需求；统领关系及选项本身仍较简单。; context=0: 该人数能够定位所问军队，未加入大段无关军事背景。; leakage=0: 题干只标明军队，没有说明由谁统领。

**target_preserving_comparison, run 1: REWRITE**
The alternative explicitly connects the headcount to soldiers while preserving the same force, command relation, and answer choices.
naturalness=2: “这三十万七千五百训练有素的军队” places a headcount directly before “训练有素的军队,” requiring readers to mentally supply “名士兵” or reinterpret “军队.”; processing=1: The number and description require a small attachment repair, but the commander question and four short choices are otherwise manageable.; context=0: The headcount clearly identifies the force whose commanders are being asked about.; leakage=0: Neither the headcount nor “训练有素” supplies the commanders' identity.
Diagnostic alternative: 这支由三十万七千五百名训练有素的士兵组成的军队由谁统领？
A. 哈拿尼雅
B. 耶列和玛西亚
C. 乌西雅
D. 那二千六百个家族首领 (preservation: preserved)

**target_preserving_comparison, run 2: REWRITE**
改写补足人数所修饰的对象，消除明显的搭配问题，同时保留同一支军队、统领关系和答案范围。
naturalness=2: “这三十万七千五百训练有素的军队”把人数直接接到“军队”上，缺少“名士兵”等成分，需要读者自行修补。; processing=1: 人数、训练状况和统领关系仍可辨认，但读者需先把人数理解为士兵数量，而非军队数量。; context=0: 人数和“训练有素”准确定位所问军队，没有无关铺垫。; leakage=0: 题干说明军队规模，但没有给出统领者。
Diagnostic alternative: 这三十万七千五百名训练有素的士兵由谁统领？
A. 哈拿尼雅
B. 耶列和玛西亚
C. 乌西雅
D. 那二千六百个家族首领 (preservation: preserved)

**independent_dimensions, run 1: REWRITE**
The count-and-noun construction needs mental repair, so the naturalness gate fails even though the target is clear.
naturalness=2: “这三十万七千五百训练有素的军队” unnaturally attaches a bare personnel count to “军队,” requiring readers to mentally supply a counted noun such as soldiers.; processing=1: Readers must interpret the long numerical modifier and connect it to the army before selecting its commanders; the choices themselves are distinct.; context=0: The troop count and “训练有素” sufficiently identify the army whose leadership is being asked about.; leakage=0: The stem gives the army's size and description, not the identity of its commanders.

**independent_dimensions, run 2: REWRITE**
自然度未通过：数量短语需要读者作语言修补；应保留统领者这一目标而调整措辞。负担判断仍需受访者验证。
naturalness=2: “这三十万七千五百训练有素的军队”把人数直接接到“军队”上，缺少“名士兵”等成分，读者需要自行修补数量与名词的关系。; processing=1: 需读出较长人数并判断“由谁统领”的角色关系；除数量短语的表达问题外，任务结构仍较简单。; context=0: 人数及“训练有素”能明确定位所问军队，没有多余背景。; leakage=0: 题干只标识军队，没有说明统领者身份。

## hard:t1_2kgs11:b13a:mcq

谁把枪和盾牌交给了百夫长？

Group: previous_controls

**previous_wording_gate, run 1: KEEP**
单层“谁把……交给……”问句，没有嵌套从句或未明指代；选项简短，人物角色清楚。


**previous_wording_gate, run 2: KEEP**
单一“谁把……交给……”问句，没有嵌套从句或未明指代；“枪和盾牌”只是并列宾语，选项无需复杂解码。


**whole_item_rubric, run 1: KEEP**
问法直接，事件明确，没有明显可避免的理解负担。
naturalness=0: “谁把枪和盾牌交给了百夫长”是自然、直接的问法。; processing=0: 问题只要求辨认交付兵器的人，四个选项也都简短。; context=0: “枪和盾牌”及“百夫长”足以定位经文中的交付事件。; leakage=0: 题干没有说明交付者；“祭司耶何耶大”仅作为选项出现。

**whole_item_rubric, run 2: KEEP**
无需额外背景即可理解所问角色，保留。
naturalness=0: “谁把枪和盾牌交给了百夫长”是自然直接的问法。; processing=0: 交付者、物品和接收者的关系清晰，选项简短。; context=0: 枪、盾牌和百夫长足以定位经文中的交付事件。; leakage=0: 题干未透露交付者是谁。

**target_preserving_comparison, run 1: KEEP**
问法直接，事件明确，没有需要消除的显著措辞负担。
naturalness=0: “谁把枪和盾牌交给了百夫长”是自然、直接的问法。; processing=0: 只需辨认交付兵器的人；四个选项简短，没有复杂的比较要求。; context=0: “枪和盾牌”及“百夫长”足以定位经文中的交付事件。; leakage=0: 题干没有透露交付者；正确人物出现在选项中不构成泄露。

**target_preserving_comparison, run 2: KEEP**
问题简明且角色关系明确，无须改写。
naturalness=0: “谁把枪和盾牌交给了百夫长”表达直接、自然。; processing=0: 交付者、物品和接收者的关系清楚，选项均为简短人物称谓。; context=0: 枪、盾牌和百夫长提供了充分的事件定位。; leakage=0: 题干没有提供交付者的身份。

**independent_dimensions, run 1: KEEP**
措辞直接，事件明确，各项负担均低。
naturalness=0: “谁把枪和盾牌交给了百夫长”表达自然、直接。; processing=0: 只需识别交付兵器的人；选项简短，没有复杂修饰或角色转换。; context=0: “枪和盾牌”及“百夫长”足以定位经文中的交付事件。; leakage=0: 题干没有说明交付者是谁；正确答案出现在选项中不构成泄露。

**independent_dimensions, run 2: KEEP**
直接询问行动者，四个维度均无明显问题。
naturalness=0: “谁把枪和盾牌交给了百夫长”自然明确。; processing=0: 交付者、物品和接收者的角色清楚；无需处理经文中关于兵器来源的修饰。; context=0: 枪、盾牌和百夫长足以定位这次交付。; leakage=0: 题干没有提供交付者的身份。

## hard:t1_2kgs11:f49c:mcq

耶何耶大立的第一个约，是在哪些之间立的？

Group: previous_concerns

**previous_wording_gate, run 1: REWRITE**
The topic contains the relative modifier “耶何耶大立的” modifying “第一个约,” followed by a question about its parties. In “是在哪些之间立的,” “哪些” lacks a natural nominal head, requiring mental repair; the parties themselves are not unresolved referents.


**previous_wording_gate, run 2: REWRITE**
“耶何耶大立的”修饰“第一个约”，后接“是在哪些之间立的”的强调结构；约的指代可由上下文确定。但“哪些之间”缺少自然的中心语，读者须自行补成哪些人或哪些方之间，句法表达不完整自然。


**whole_item_rubric, run 1: REWRITE**
需改写“哪些之间”这一不完整表达；其余定位和选项负担可接受。
naturalness=2: “在哪些之间立的”缺少“哪些人／哪些方”等中心词，表达不完整，需要读者自行补足。; processing=1: 需区分经文中的两个约，但“第一个约”定位明确，选项比较负担可控。; context=0: “耶何耶大”和“第一个约”足以定位所问事件，无多余背景。; leakage=0: 题干没有列出立约各方；正确答案出现在选项中不构成泄露。

**whole_item_rubric, run 2: REWRITE**
The intended question is recoverable, but the phrase asking for the covenant’s parties needs natural wording.
naturalness=2: “是在哪些之间立的” is markedly awkward: “哪些” lacks a natural noun or expression identifying the parties.; processing=1: Readers must supply the missing category after “哪些,” though the choices make the intended relation recoverable.; context=0: “第一个约” sufficiently distinguishes the first covenant from the following one.; leakage=0: The stem does not state the parties to the covenant.

**target_preserving_comparison, run 1: REWRITE**
替代表述保留第一个约及其参与方这一目标，消除了“哪些之间”的不自然表达。
naturalness=2: “在哪些之间立的”缺少“人”或“各方”等中心语，需要读者补足。; processing=1: 需要区分第一个约和第二个约，并比较选项中的参与方；这是目标本身所需的普通负担。; context=0: “耶何耶大”和“第一个约”足以定位所问的约。; leakage=0: 题干没有说明第一个约涉及哪些方；正确组合只出现在选项中。
Diagnostic alternative: 耶何耶大立的第一个约包括哪几方？ (preservation: preserved)

**target_preserving_comparison, run 2: REWRITE**
The alternative repairs the unnatural interrogative while retaining the first covenant, its parties, and the original choices.
naturalness=2: “在哪些之间立的” leaves “哪些” without a natural nominal head; readers must mentally supply something such as “几方”.; processing=1: The first-covenant distinction is manageable, although the incomplete “哪些之间” phrasing briefly interrupts parsing.; context=0: “第一个约” usefully distinguishes the two covenants mentioned in the passage.; leakage=0: The stem identifies the covenant but does not name its parties.
Diagnostic alternative: 耶何耶大立的第一个约，是哪几方之间的约？
A. 耶和华、王和百姓
B. 王和百夫长
C. 耶和华和守卫
D. 王和百姓 (preservation: preserved)

**independent_dimensions, run 1: REWRITE**
自然度未通过：应修复“哪些之间”的缺省表达，同时保留辨认第一个约参与方的目标。
naturalness=2: “在哪些之间立的”中，“哪些”缺少所指类别，通常需说“哪些人之间”或“哪几方之间”，读者需要补足表达。; processing=1: 需要区分第一个约与后一个约，并比较各选项中的参与方；这是辨认目标所需的普通负担。; context=0: “耶何耶大立的第一个约”足以定位经文中的两个约之一。; leakage=0: 题干没有列出立约各方；正确组合出现在选项中不构成泄露。

**independent_dimensions, run 2: REWRITE**
The intended question is recoverable, but “在哪些之间” requires unnatural mental completion.
naturalness=2: “是在哪些之间立的” leaves “哪些” without a natural noun or category; readers must mentally supply the intended covenant participants.; processing=1: Readers must identify the first of two covenants and interpret “哪些” as its parties. The sequencing is necessary and otherwise manageable.; context=0: “第一个约” usefully distinguishes the two covenants in the passage.; leakage=0: The stem identifies the covenant but does not state its parties.

## hard:t1_2sam21:de9f:mcq

亚比筛击杀了谁？

Group: previous_controls

**previous_wording_gate, run 1: KEEP**
A single main clause asks for the object of “击杀了.” “亚比筛” is explicit, and there is no embedded modifier or unresolved referent.


**previous_wording_gate, run 2: KEEP**
单层主谓宾问句，“谁”询问“击杀”的对象，无嵌套从句。亚比筛指称明确，选项简洁，无未解决的指代。


**whole_item_rubric, run 1: KEEP**
措辞简洁，事件定位清楚，可保留。
naturalness=0: “亚比筛击杀了谁”是自然明确的问法。; processing=0: 仅询问一个动作的对象，选项易于比较；姓名本身不构成额外负担。; context=0: 经文中亚比筛的击杀事件明确，无须增加背景。; leakage=0: 题干没有透露被击杀者的身份。

**whole_item_rubric, run 2: KEEP**
问法直接，事件定位清楚，各维度均无明显负担。
naturalness=0: “亚比筛击杀了谁？”表达直接自然。; processing=0: 只需辨认一个动作的对象；选项均为简短的人物指称。; context=0: “亚比筛击杀”足以定位经文中的事件，无多余背景。; leakage=0: 题干未说明被击杀者是谁。

**target_preserving_comparison, run 1: KEEP**
问题已经直接询问目标关系，没有明显可移除的负担。
naturalness=0: “亚比筛击杀了谁”是自然、直接的人物提问。; processing=0: 只涉及施事与被杀者的单一关系；选项容易逐一理解。; context=0: 在所给经文中，亚比筛的击杀事件明确，无须补充背景。; leakage=0: 题干未提供被杀者的身份。

**target_preserving_comparison, run 2: KEEP**
问题简明且指向明确，没有值得通过改写消除的负担。
naturalness=0: “亚比筛击杀了谁？”表达自然、直接。; processing=0: 只需辨认动作的对象；四个选项没有额外的结构或比较负担。; context=0: “亚比筛击杀”足以定位经文中的事件。; leakage=0: 题干没有说明被击杀者是谁。

**independent_dimensions, run 1: KEEP**
问题简洁，事件定位明确，各项均通过。
naturalness=0: “亚比筛击杀了谁”表达自然，施事和所问对象清楚。; processing=0: 只需找到击杀事件中的对象；选项没有造成复杂的比较负担。; context=0: 所给段落只有一个亚比筛击杀人的事件，无需额外背景。; leakage=0: 题干没有说明被击杀者是谁。

**independent_dimensions, run 2: KEEP**
各维度均通过；直接询问人物身份。负担判断仍需受访者验证。
naturalness=0: “亚比筛击杀了谁？”自然直接。; processing=0: 只需辨认“亚比筛”这一施事及其击杀的对象；选项简短。; context=0: “亚比筛击杀”足以定位经文中的唯一事件，无多余背景。; leakage=0: 题干没有说明被击杀者是谁；答案出现在选项中不构成泄露。

## hard:t1_acts19:7628:mcq

被那附着邪灵的人制服以后，谁受伤逃出了那房子？

Group: previous_concerns

**previous_wording_gate, run 1: REWRITE**
The passive temporal setup “被那附着邪灵的人制服以后” contains the actor modifier “附着邪灵的” before the main question “谁受伤逃出了那房子”. This delays the queried participant behind a modified passive actor. The people and house are identifiable in context, but that does not remove the structural burden.


**previous_wording_gate, run 2: REWRITE**
前置时间从句“被那附着邪灵的人制服以后”采用被动结构，其施事“那附着邪灵的人”又含修饰语“附着邪灵”；被询问的受事直到主句“谁受伤逃出了那房子”才出现。该结构要求先处理带修饰施事的被动时间框架，再确定参与者。各指称可由经文确定，但不能消除这一阅读负担。


**whole_item_rubric, run 1: KEEP**
时间背景和被动表达都服务于事件定位，未造成显著可避免负担。
naturalness=0: “被……制服以后，谁受伤逃出了那房子？”是自然的事件衔接问法。; processing=1: 需要区分制服别人的人和受伤逃走的人，但被动结构及简短选项使角色关系清楚。; context=0: “被那附着邪灵的人制服以后”提供有用的事件定位，没有加入无关背景。; leakage=0: 题干没有指出被制服和逃走者的身份。

**whole_item_rubric, run 2: KEEP**
虽有经文式措辞和一个前置时间分句，整体仍是普通读者可处理的身份问题。
naturalness=1: “那附着邪灵的人”略带经文式表达，但整句含义清楚。; processing=1: 需把“被……制服以后”的受事与后面的“谁”联系起来，但只有一层时间关系，角色可清楚辨认。; context=0: 制服和逃出房子的事件锚定了同一场冲突，没有引入无关背景。; leakage=0: 题干未指出被制服并逃走者的身份。

**target_preserving_comparison, run 1: KEEP**
被动结构和时间关系均清楚，事件背景有助于限定问题，不构成实质性的额外负担。
naturalness=0: “被……制服以后，谁受伤逃出了……”是自然明确的问法。; processing=1: 需区分制服他人的人和受伤逃走的人；这一角色关系表达清楚，四个选项也都是简短的人物名称。; context=0: “被那附着邪灵的人制服以后”提供了有用的事件定位，没有无关铺垫。; leakage=0: 题干没有说出受伤逃走者的身份；该身份仅出现在选项中。

**target_preserving_comparison, run 2: KEEP**
前置事件提供有用定位，整体只有普通、可管理的阅读要求。
naturalness=0: “被……制服以后，谁受伤逃出了那房子？”语序自然，事件关系清楚。; processing=1: 需将前置的“被……制服以后”与后面的“谁”关联，但只有一个时间关系，选项也容易区分。; context=0: 被制服这一背景有助于明确所问的逃跑事件，“那房子”也能从经文定位。; leakage=0: 题干说明遭遇和结果，但没有透露受伤逃跑者的身份。

**independent_dimensions, run 1: KEEP**
被动关系带来普通、可处理的阅读需求，并未造成显著的额外负担。
naturalness=0: “被那附着邪灵的人制服以后，谁受伤逃出了那房子？”是通顺的中文问句。; processing=1: 需要区分制服别人的人和受伤逃走的人，但时间关系清楚，四个选项也容易区分。; context=0: “被那附着邪灵的人制服以后”提供相关事件线索，没有引入无关背景。; leakage=0: 题干说明所问事件，但没有说出逃走者的身份。

**independent_dimensions, run 2: KEEP**
虽有被动结构和时间关系，但整体清楚，未形成实质性的可避免负担。负担判断仍需受访者验证。
naturalness=1: “被那附着邪灵的人制服以后”略显书面，但意思明确，无须修补。; processing=1: 需区分制服他人的人和随后受伤逃走的人，并理解先后关系；角色链条短且连续，负担可管理。; context=0: 制服事件与“逃出了那房子”共同定位所问人物，没有无关背景。; leakage=0: 题干没有点明被制服并逃走者的身份。

## hard:t1_acts20:f988:mcq

保罗为什么一直讲到午夜？

Group: previous_controls

**previous_wording_gate, run 1: KEEP**
A single main-clause why-question includes the endpoint “到午夜”; the options are direct causal clauses. “他” in the options clearly refers to 保罗.


**previous_wording_gate, run 2: KEEP**
主问句“保罗为什么一直讲到午夜”直接询问原因，没有嵌套从句。选项是简明的“因为”原因分句；其中“他”明确指保罗，无未明指代。


**whole_item_rubric, run 1: KEEP**
题干直接，选项比较负担正常。
naturalness=0: “保罗为什么一直讲到午夜？”和各原因选项均自然易懂。; processing=1: 四个选项都直接提出原因，比较时无需处理嵌套关系或复杂指代。; context=0: “保罗”和“讲到午夜”足以确定所问事件。; leakage=0: 题干只指出讲话持续到午夜，没有给出原因。

**whole_item_rubric, run 2: KEEP**
The item asks directly for the reason and uses easily distinguished options.
naturalness=0: “保罗为什么一直讲到午夜？” and the “因为” choices are natural Chinese.; processing=1: Comparing four plainly expressed reasons imposes only ordinary multiple-choice reading demand.; context=0: Paul's speaking until midnight is a sufficient event anchor.; leakage=0: The question does not explain why he spoke so long; the explanation appears among the choices.

**target_preserving_comparison, run 1: KEEP**
整题表达清楚，选项比较属于正常且必要的作答要求。
naturalness=0: “保罗为什么一直讲到午夜？”自然直接，四个选项也都通顺。; processing=1: 四个简短的“因为”选项只要求比较可能的原因，没有复杂的角色或指代关系。; context=0: “保罗”和“一直讲到午夜”足以定位所问的事件。; leakage=0: 题干没有说明他第二天准备离开；正确原因仅作为选项出现。

**target_preserving_comparison, run 2: KEEP**
The whole item is accessible and directly tests the intended causal relation.
naturalness=0: “保罗为什么一直讲到午夜？” and the “因为” choices are idiomatic.; processing=0: The reader selects among four plainly expressed reasons without complex role or reference tracking.; context=0: Paul's speaking until midnight directly identifies the relevant event.; leakage=0: The question does not state his planned departure; its presence as one option is not leakage.

**independent_dimensions, run 1: KEEP**
题目准确聚焦原因，背景充分且没有泄露答案。
naturalness=0: “保罗为什么一直讲到午夜？”自然直接，选项表达也通顺。; processing=0: 只需在四个简短原因中作选择，没有复杂的修饰或相互重叠的选项。; context=0: “一直讲到午夜”足以定位所问事件。; leakage=0: 题干没有说明保罗第二天准备离开。

**independent_dimensions, run 2: KEEP**
The question and options clearly test the stated reason without unnecessary background.
naturalness=0: “保罗为什么一直讲到午夜？” is direct and idiomatic.; processing=1: The four parallel “因为” choices present distinct reasons with little comparison burden.; context=0: “保罗” and “一直讲到午夜” uniquely locate the relevant speech.; leakage=0: The departure is presented only as one of the choices, not supplied by the question's setup.

## hard:t1_judg17_18:725d:mcq

他们请谁为他们求问这趟行程？

Group: previous_borderline

**previous_wording_gate, run 1: KEEP**
问句以“他们请谁……”询问受请托者，其后“为他们求问这趟行程”说明行动和受益者；没有再嵌套求问内容的从句。两处“他们”均指文中的请求者，语境足以明确指代。


**previous_wording_gate, run 2: KEEP**
“请谁”后接“为他们求问这趟行程”这一动作补语，是自然的兼语结构，没有再嵌套一层请求。“他们”两次均指提出请求的人，语境可明确其指代；选项直接列出人物或对象。


**whole_item_rubric, run 1: KEEP**
措辞略有压缩，但不会造成明显的理解或角色辨认困难。
naturalness=1: “求问这趟行程”略显压缩，但结合经文，能自然理解为求问行程是否顺利。; processing=0: “他们请谁”明确询问受请求的人，选项简短，不需复杂比较。; context=0: 经文中的请求和祭司的回答足以确定“他们”及所问的事件。; leakage=0: 题干没有说他们请求的是祭司。

**whole_item_rubric, run 2: KEEP**
Despite minor compression in “求问这趟行程,” the intended participant question is readily understandable.
naturalness=1: “求问这趟行程” is mildly compressed: the reader supplies the sense of asking about the journey's prospects.; processing=1: “请谁为他们求问” requires distinguishing the requested intermediary from those making the request, but the roles remain manageable.; context=0: The passage's request and the priest's reply make “他们” and the relevant exchange sufficiently clear.; leakage=0: Neither the question nor introductory framing identifies the intermediary; “祭司” appears only as a choice.

**target_preserving_comparison, run 1: REWRITE**
改写明确求问的对象和事项，保留原来辨认受请求者的目标，避免不自然的动宾搭配。
naturalness=2: “求问这趟行程”的搭配不够自然，需要把“行程”理解为求问的事项，并补出求问神、询问是否顺利的意思。; processing=1: 句子和选项都短，但“求问这趟行程”需要读者补足省略的关系。; context=0: “他们”和“这趟行程”在所给经文中有明确对应，足以定位请求。; leakage=0: 题干未说明他们请的是谁。
Diagnostic alternative: 他们请谁求问神，看这趟行程是否顺利？
A. 神
B. 米迦的母亲
C. 米迦
D. 祭司 (preservation: preserved)

**target_preserving_comparison, run 2: KEEP**
Despite minor compression, the participant roles and answer scope are recoverable without substantial avoidable burden.
naturalness=1: “求问这趟行程” is slightly compressed wording for inquiring about the journey's prospects, but its meaning is understandable.; processing=1: The reader distinguishes the person asked to inquire from God, whom that person would consult. This distinction is central to the target.; context=0: The supplied exchange identifies “他们” as the speakers making the request and the priest as their interlocutor.; leakage=0: The question does not name the requested intermediary; “祭司” appears only as an option.

**independent_dimensions, run 1: KEEP**
虽有轻微措辞生硬，但所问角色清楚，选项简短，整体负担可控。
naturalness=1: “求问这趟行程”略显生硬，通常会说明求问行程是否顺利，但结合经文仍容易理解。; processing=1: 读者须分清被请求代为求问的人与被求问的神；“请谁为他们”已清楚标明所问角色。; context=0: “这趟行程”对应经文唯一的求问事件；不必知道“他们”的具体身份才能定位。; leakage=0: 题干没有说明他们请求的是祭司。

**independent_dimensions, run 2: KEEP**
Despite minor compression in “求问这趟行程,” the requested role is understandable without substantial avoidable burden.
naturalness=1: “求问这趟行程” is slightly compressed; the intended sense of inquiring about the journey is still clear.; processing=1: Respondents distinguish the person asked to make the inquiry from God, whom that person consults. This role distinction is central to the target, and the choices are short.; context=0: The displayed exchange supplies the referent for “他们” and identifies the request about the journey.; leakage=0: The wording does not identify the intermediary; “祭司” appears only among the choices.

## hard:t1_judg9:6d68:mcq

约坦呼叫示剑的众首领听他的话，是为了什么结果？

Group: previous_concerns

**previous_wording_gate, run 1: KEEP**
The question asks the purpose of an action whose deepest complement is “示剑的众首领听他的话” under “呼叫.” “他” clearly refers to 约坦, and “是为了什么结果” makes the requested purpose/result understandable without additional viewpoint tracking.


**previous_wording_gate, run 2: KEEP**
前半句“呼叫示剑的众首领听他的话”包含一层呼告内容，后半句询问目的或结果，没有再嵌套另一人的言语。“他”指约坦，“他们”指众首领，指代明确；“为了什么结果”虽稍显生硬，仍可直接理解。


**whole_item_rubric, run 1: REWRITE**
目标本身可以保留，但动词搭配和目的／结果问法明显生硬，应改写。
naturalness=2: “呼叫……听他的话”搭配生硬，“是为了什么结果”又混合了目的和结果的问法，需要读者自行理顺。; processing=1: 人物和所求结果的关系可以理解，选项也较短；主要困难是措辞，而非复杂结构。; context=0: 约坦、示剑众首领及听他说话的要求，足以定位相关话语。; leakage=0: 题干没有说明神也听他们的话这一所问结果。

**whole_item_rubric, run 2: KEEP**
措辞略生硬，但未达到需要心理修补的程度，整体负担可控。
naturalness=1: “呼叫……听他的话”和“为了什么结果”略显生硬，但仍能直接理解为询问目的或期望的结果。; processing=1: 需要把要求众首领聆听与期望的结果联系起来；这是所问意义本身，四个选项也易于区分。; context=0: 约坦、示剑众首领和听他说话的要求，清楚定位了相关话语。; leakage=0: 题干只交代聆听的要求，没有说出“神也听他们的话”这一结果。

**target_preserving_comparison, run 1: REWRITE**
保留呼吁者、听众、呼吁内容和所求结果，修复目的与结果表达的生硬搭配。
naturalness=2: “是为了什么结果”把“为了什么目的”和“希望得到什么结果”两种表达混在一起，搭配明显生硬。; processing=1: 需要联系约坦的呼吁与所希望的结果；这属于目标所需的关系理解，选项没有复杂嵌套。; context=0: 约坦、示剑众首领及“听他的话”足以定位经文中的呼吁。; leakage=0: 题干只提供呼吁内容，没有说出希望神也听他们的话。
Diagnostic alternative: 约坦叫示剑的众首领听他的话，是希望得到什么结果？ (preservation: preserved)

**target_preserving_comparison, run 2: REWRITE**
改写保留参与者、呼吁与期望结果的关系及原有答案范围，只修复“为了什么结果”的不自然搭配；原选项可保留。
naturalness=2: “是为了什么结果”搭配生硬，需要读者将其理解为“希望带来什么结果”。; processing=1: 需区分约坦的呼吁与期望结果；这是目标本身所需的关系，选项也较短。; context=0: 约坦、示剑的众首领以及“听他的话”充分定位了这次呼吁。; leakage=0: 题干只交代呼吁，没有说出希望神也听他们的话。
Diagnostic alternative: 约坦呼叫示剑的众首领听他的话，希望这样能带来什么结果？ (preservation: preserved)

**independent_dimensions, run 1: REWRITE**
主要问题是“为了什么结果”的不自然搭配；应改善问法而保留原有的结果目标。
naturalness=2: “是为了什么结果”搭配生硬，需要理解为“想达到什么结果”或询问目的，普通说话者较少这样提问。; processing=1: 需要把约坦要求首领听话的行动与所问结果联系起来；其余人物指代和选项比较负担普通。; context=0: “约坦呼叫示剑的众首领听他的话”能唯一定位所问话语，没有多余背景。; leakage=0: 题干没有说出“神也听他们的话”这一目标结果。

**independent_dimensions, run 2: REWRITE**
需要修改的是“为了什么结果”的不自然搭配，而非所问的目的关系。
naturalness=2: “是为了什么结果”搭配明显生硬，读者需要把它理解为询问目的或希望出现的结果。; processing=1: 需连接约坦要求众人听话与神听他们的话这两层关系；这一关系属于所测内容，整体仍可处理。; context=0: “约坦呼叫示剑的众首领听他的话”提供了充分且相关的事件定位。; leakage=0: 题干只说明约坦的呼叫，没有说出所求的结果。

## hard:t1_judg9:f36a:mcq

迦勒第一次说有人来时，西布说他看见的其实是什么？

Group: previous_concerns

**previous_wording_gate, run 1: REWRITE**
The temporal setup “迦勒第一次说有人来时” embeds reported speech, while “西布说他看见的其实是什么” adds another speaker's report containing “他看见的.” This requires nested speaker/perceiver tracking. “他” is inferable as 迦勒, but the wording unnecessarily requires resolving that shift.


**previous_wording_gate, run 2: REWRITE**
时间从句“迦勒第一次说有人来时”内含迦勒所说的内容，主问句“西布说他看见的其实是什么”又把西布的话与“他看见的”这一感知结构嵌套起来，需要切换人物视角。“他”可据上下文理解为迦勒，但这种先转述一人说话、再追问另一人对其所见的说法的结构应简化。


**whole_item_rubric, run 1: KEEP**
The question clearly locates the intended reply, with only ordinary speaker-tracking demands.
naturalness=0: “第一次说有人来时” and “其实是什么” form a natural Chinese question about the exchange.; processing=1: The reader tracks two speakers and the reported perception in “西布说他看见的”; their conversational roles make the reference manageable.; context=0: “第一次” usefully distinguishes the first report from “迦勒又说” in the next verse.; leakage=0: The stem does not name the shadows; “山上的影子” appears only as an answer choice.

**whole_item_rubric, run 2: KEEP**
The temporal anchor and speaker tracking are useful and manageable rather than avoidable burden.
naturalness=0: “第一次说有人来时” and “其实是什么” are natural ways to anchor the exchange and ask about the correction.; processing=1: Readers track two speakers and interpret “他” as 迦勒 in context; the short, concrete choices keep comparison manageable.; context=0: “第一次” usefully distinguishes the first report from 迦勒's later report.; leakage=0: “其实” signals a contrasting explanation but does not reveal “山上的影子.”

**target_preserving_comparison, run 1: KEEP**
The speaker and timing information support the intended reported-claim target with only manageable reference tracking.
naturalness=0: “第一次说有人来时” and “西布说他看见的其实是什么” form a natural Chinese question.; processing=1: The reader tracks two speakers and resolves “他” to 迦勒 within a clearly anchored exchange; the four choices are brief.; context=0: “第一次” usefully selects the first of 迦勒's two reports, and “西布说” preserves whose explanation is being requested.; leakage=0: The question reports the initial sighting without supplying 西布's explanation; the shadows appear only among the choices.

**target_preserving_comparison, run 2: KEEP**
The temporal anchor and reported explanation are necessary to the target and remain manageable in the displayed Chinese.
naturalness=0: “第一次说有人来时” and “其实是什么” are natural Chinese expressions in this question.; processing=1: The reader tracks Gaal's report and Zebul's explanation. The short options present readily distinguishable possibilities.; context=0: “第一次” usefully distinguishes the first report from Gaal's second report in the next verse; “他” is resolvable as Gaal in context.; leakage=0: The stem does not supply Zebul's explanation; “山上的影子，不是人” appears only among the choices.

**independent_dimensions, run 1: KEEP**
The speaker tracking is ordinary and necessary, and the first-report anchor is useful.
naturalness=0: “西布说他看见的其实是什么？” naturally asks for Zebul's explanation of what Gaal saw.; processing=1: The respondent tracks Gaal as the observer and Zebul as the speaker, then compares short choices; the dialogue context resolves “他.”; context=0: “第一次说有人来时” usefully distinguishes the first exchange from Gaal's second report.; leakage=0: The stem mentions seeing people but leaves Zebul's alternative explanation unstated.

**independent_dimensions, run 2: KEEP**
The temporal anchor and speaker tracking are useful, ordinary demands rather than avoidable burden.
naturalness=0: “迦勒第一次说有人来时，西布说他看见的其实是什么？” is idiomatic Chinese.; processing=1: Respondents distinguish 迦勒's report from 西布's explanation and resolve “他” to 迦勒. This is manageable and necessary to the target; the choices are distinct.; context=0: “第一次” usefully distinguishes the initial report from 迦勒's second statement.; leakage=0: The stem names the exchange but does not supply “山上的影子”; its presence in a choice is not leakage.

## gold:t1_1kgs13:gfxe:open

Who showed the old prophet which way the man of God had gone?

Group: previous_concerns

**previous_wording_gate, run 1: KEEP**
The main question contains one embedded interrogative, “which way the man of God had gone,” as the content shown. Both named roles are clear, with no unresolved referent.


**previous_wording_gate, run 2: KEEP**
The main question “Who showed the old prophet” takes one embedded interrogative, “which way the man of God had gone.” Both named roles are clear, with no unresolved referent or nested viewpoint.


**whole_item_rubric, run 1: KEEP**
The participant roles create only ordinary, manageable reading demand.
naturalness=0: “Who showed the old prophet which way…” is idiomatic and direct.; processing=1: The reader distinguishes the person showing the route, the old prophet, and the man of God; their roles are clearly expressed.; context=0: “The old prophet” and “which way the man of God had gone” identify the relevant exchange.; leakage=0: The question does not identify the sons or otherwise supply the requested person.

**whole_item_rubric, run 2: KEEP**
The question clearly identifies the event and asks directly for its participants.
naturalness=0: “Who showed ... which way” is idiomatic.; processing=1: The embedded “which way the man of God had gone” is readily understood and necessary to specify what was shown.; context=0: The old prophet and the route shown to him identify a distinct event.; leakage=0: The question does not identify the people who showed him the route.

**target_preserving_comparison, run 1: KEEP**
The named roles provide useful disambiguation; shortening them would not meaningfully improve accessibility.
naturalness=0: “Who showed … which way … had gone?” is idiomatic and direct.; processing=1: The reader tracks the old prophet and the man of God, but their roles are explicitly named and the embedded direction question is manageable.; context=0: “The old prophet” and the request for the man's route identify the relevant exchange.; leakage=0: The question does not identify the people who showed him the route.

**target_preserving_comparison, run 2: KEEP**
The participant and route information is necessary to express the target clearly, with no meaningful removable burden.
naturalness=0: “Who showed ... which way ... had gone” is ordinary English.; processing=1: The reader distinguishes the person receiving directions from the traveler whose route is described; both roles are explicitly named.; context=0: The old prophet, the man of God, and the route sufficiently identify the relevant exchange.; leakage=0: The question does not identify the sons who supplied the directions.

**independent_dimensions, run 1: KEEP**
The necessary participants and action are expressed clearly without avoidable background.
naturalness=0: “Who showed the old prophet which way…” is idiomatic and direct.; processing=1: The reader distinguishes the person showing the route from the prophet and the man who traveled; these roles are necessary and clearly expressed.; context=0: “The old prophet” and the route taken by “the man of God” identify the relevant exchange.; leakage=0: The question does not identify who showed him the route.

**independent_dimensions, run 2: KEEP**
The question clearly identifies the event and asks directly for its participants.
naturalness=0: “Who showed ... which way” is a natural way to ask about the informants.; processing=1: The respondent distinguishes the person receiving directions from the traveler; the explicit labels make these roles manageable.; context=0: The old prophet's being shown the man's route identifies a unique event.; leakage=0: The question does not name or describe the sons who supplied the directions.

## gold:t1_2chr26:ryq4:open

What did Uzziah build at Jerusalem's gates?

Group: previous_controls

**previous_wording_gate, run 1: KEEP**
A single direct question with the location phrase “at Jerusalem's gates”; no embedded clause or unresolved referent.


**previous_wording_gate, run 2: KEEP**
A direct main question with the location phrase “at Jerusalem’s gates”; there are no embedded clauses. Uzziah and the location are explicit, with no unresolved referent.


**whole_item_rubric, run 1: KEEP**
The question provides a helpful location anchor without unnecessary setup or answer disclosure.
naturalness=0: “What did Uzziah build at Jerusalem's gates?” is ordinary, direct English.; processing=0: The question has a straightforward actor–action–location structure.; context=0: “At Jerusalem's gates” usefully locates the relevant building activity among several construction projects.; leakage=0: The location does not reveal that the structures were towers.

**whole_item_rubric, run 2: KEEP**
The location provides useful anchoring without unnecessary detail.
naturalness=0: “What did Uzziah build at Jerusalem's gates?” is idiomatic and direct.; processing=0: One action and one location lead directly to the requested object.; context=0: Uzziah and Jerusalem's gates distinguish this construction from his other building projects.; leakage=0: The question gives the location, not what was built.

**target_preserving_comparison, run 1: KEEP**
The location is useful disambiguation, and there is no meaningful burden to remove.
naturalness=0: “What did Uzziah build at Jerusalem's gates?” is natural and direct.; processing=0: The question has one actor, one action, and a short location phrase.; context=0: “At Jerusalem's gates” distinguishes these structures from Uzziah's other building projects.; leakage=0: The location does not disclose that the structures were towers.

**target_preserving_comparison, run 2: KEEP**
The location is useful disambiguation, and the question has no meaningful removable burden.
naturalness=0: “What did Uzziah build at Jerusalem's gates?” is idiomatic and direct.; processing=0: One action and a short location phrase are readily parsed.; context=0: “At Jerusalem's gates” distinguishes the intended construction from Uzziah's other building projects.; leakage=0: The question supplies the location but not the structure built.

**independent_dimensions, run 1: KEEP**
The question uses a useful location anchor without unnecessary detail or answer disclosure.
naturalness=0: “What did Uzziah build at Jerusalem's gates?” is idiomatic and direct.; processing=0: The respondent connects one builder and location to the object built.; context=0: “Uzziah” and “Jerusalem's gates” distinguish this construction from his other building projects.; leakage=0: The location does not disclose that he built towers.

**independent_dimensions, run 2: KEEP**
The location supplies useful context without unnecessary detail or answer disclosure.
naturalness=0: “What did Uzziah build at Jerusalem's gates?” is idiomatic and direct.; processing=0: The question asks for one kind of structure with a simple location anchor.; context=0: “At Jerusalem's gates” distinguishes this construction from Uzziah's other building projects.; leakage=0: The location does not reveal what he built.

## gold:t1_2kgs11:w4ys:open

What did Jehoiada give the commanders?

Group: previous_controls

**previous_wording_gate, run 1: KEEP**
This is a single main question with a direct object queried by “What” and an explicit recipient, “the commanders.” There are no embedded clauses or unresolved referents.


**previous_wording_gate, run 2: KEEP**
A single main interrogative asks for the object of “give,” with Jehoiada as giver and “the commanders” as recipient. There are no embedded clauses or unresolved referents; the passage identifies the commanders clearly.


**whole_item_rubric, run 1: KEEP**
This is a straightforward question with sufficient context and no avoidable wording burden.
naturalness=0: “What did Jehoiada give the commanders?” is idiomatic and direct.; processing=0: The question has a single action with an explicitly named giver and recipient.; context=0: Jehoiada's giving something to the commanders clearly locates the relevant event.; leakage=0: No weapons or other answer details are supplied in the question.

**whole_item_rubric, run 2: KEEP**
The item asks directly for the intended information without avoidable burden.
naturalness=0: “What did Jehoiada give the commanders?” is idiomatic and direct.; processing=0: The giver, recipients, and requested information are immediately clear.; context=0: The named giver and recipients sufficiently identify the relevant action.; leakage=0: The question does not name the objects given.

**target_preserving_comparison, run 1: KEEP**
The question is already concise, natural, and unambiguous in context.
naturalness=0: “What did Jehoiada give the commanders?” is idiomatic and direct.; processing=0: The question presents one giver, one recipient group, and one requested object.; context=0: Jehoiada giving something to the commanders uniquely locates the relevant event.; leakage=0: No objects are named in the question.

**target_preserving_comparison, run 2: KEEP**
The item already asks for the intended information without avoidable burden.
naturalness=0: “What did Jehoiada give the commanders?” is direct and idiomatic.; processing=0: The giver, recipients, and requested information are immediately clear.; context=0: The named giver and recipients sufficiently identify the relevant action.; leakage=0: The question does not supply the objects given.

**independent_dimensions, run 1: KEEP**
The question is concise and sufficiently anchored, with no unnecessary background or answer cue.
naturalness=0: “What did Jehoiada give the commanders?” is ordinary, direct English.; processing=0: The reader identifies the objects transferred between two explicitly named roles.; context=0: Jehoiada giving something to the commanders uniquely locates the relevant transfer.; leakage=0: The question does not name the spears or shields.

**independent_dimensions, run 2: KEEP**
A clear, sufficiently anchored question with no unnecessary wording.
naturalness=0: “What did Jehoiada give the commanders?” is idiomatic and direct.; processing=0: The giver, recipients, and requested information are immediately clear.; context=0: Jehoiada giving something to the commanders identifies the relevant event in the passage.; leakage=0: The question does not name the objects given.

## gold:t1_acts19:b1be:open

What happened when handkerchiefs and aprons that had touched Paul were taken to the sick?

Group: previous_concerns

**previous_wording_gate, run 1: REWRITE**
The temporal clause introduced by “when” contains the passive “were taken to the sick” and an embedded relative clause, “that had touched Paul,” modifying “handkerchiefs and aprons.” Referents are clear, but this relative-inside-temporal/passive structure creates avoidable nesting.


**previous_wording_gate, run 2: REWRITE**
The temporal passive clause “when handkerchiefs and aprons ... were taken to the sick” contains the embedded relative clause “that had touched Paul.” This stacks a relative modifier inside a temporal/passive setup. No referent is unresolved, but the construction creates avoidable processing burden.


**whole_item_rubric, run 1: KEEP**
The modifiers serve the target and create only manageable reading demand.
naturalness=0: “What happened when” introduces the event naturally.; processing=1: “That had touched Paul” sits within the temporal clause, but both relationships are clear and necessary to identify the event.; context=0: The cloths, their contact with Paul, and their delivery to the sick provide useful event identification.; leakage=0: The question describes the circumstances without stating the healing or departure of spirits.

**whole_item_rubric, run 2: KEEP**
The sentence includes necessary event details with manageable processing demand.
naturalness=0: “What happened when” introduces the question naturally.; processing=1: “That had touched Paul” and “were taken to the sick” require manageable tracking of the cloths and their recipients; both identify the intended event.; context=0: The cloths, Paul, and the sick provide sufficient, relevant event identification.; leakage=0: Bringing the cloths to the sick does not state the resulting healing or departure of spirits.

**target_preserving_comparison, run 1: KEEP**
The event description is useful for locating the intended outcome; shortening it offers no meaningful burden reduction without losing specificity.
naturalness=0: “What happened when” introduces the event naturally, and “that had touched Paul” clearly describes the cloths.; processing=1: The reader follows the cloths' contact with Paul and their transfer to the sick. These linked details identify the necessary circumstances rather than adding avoidable load.; context=0: The handkerchiefs, aprons, and contact with Paul distinguish this event from the passage's other encounters involving evil spirits.; leakage=0: The question describes the circumstances but does not state the healing or departure of spirits.

**target_preserving_comparison, run 2: KEEP**
The modifying clause and passive construction carry useful event information and remain manageable.
naturalness=0: “What happened when” introduces the requested outcome naturally.; processing=1: The reader tracks the cloths' contact with Paul and subsequent delivery to the sick. These relations identify the event being tested.; context=0: “Handkerchiefs and aprons that had touched Paul” provides a precise, relevant event anchor.; leakage=0: The delivery of the cloths is stated, but healing and the departure of evil spirits are not.

**independent_dimensions, run 1: KEEP**
The event description has ordinary reading demands and supplies useful context without giving the outcome.
naturalness=0: “What happened when” naturally introduces a question about the outcome of this event.; processing=1: The respondent tracks the cloths touching Paul and then being taken to the sick. These linked details identify the intended event and remain manageable.; context=0: “Handkerchiefs and aprons that had touched Paul” distinguishes this event from the passage's other encounters involving evil spirits.; leakage=0: The question describes the delivery of the cloths, not the resulting cures or departure of evil spirits.

**independent_dimensions, run 2: KEEP**
The modest processing demand comes from necessary event identification, not avoidable complexity.
naturalness=0: “What happened when” introduces the event naturally.; processing=1: Respondents track the cloths touching Paul and then being taken to the sick. Both details identify the event, and the roles remain clear.; context=0: “Handkerchiefs and aprons that had touched Paul” uniquely locates the relevant event without unrelated background.; leakage=0: The question names the delivery of the cloths but does not state its effects.

## gold:t1_judg17_18:qysg:open

What did Micah steal?

Group: previous_controls

**previous_wording_gate, run 1: KEEP**
A simple main-clause object question, “What did Micah steal?”, has no embedded modifiers or unresolved referents.


**previous_wording_gate, run 2: KEEP**
A direct main-clause question with no embedded clauses or modifiers. “Micah” is explicit, and there is no unresolved referent.


**whole_item_rubric, run 1: KEEP**
A clear, low-burden question about the stolen property.
naturalness=0: “What did Micah steal?” is idiomatic and direct.; processing=0: The question asks for one object, with no competing roles or embedded conditions.; context=0: Naming Micah and the theft identifies the relevant event.; leakage=0: The question does not identify the stolen property.

**whole_item_rubric, run 2: KEEP**
A clear, low-burden question about the intended object.
naturalness=0: “What did Micah steal?” is idiomatic and direct.; processing=0: The question asks for one object without additional clauses or reference tracking.; context=0: Micah's name and the act of stealing identify the relevant event.; leakage=0: No setup supplies the stolen object.

**target_preserving_comparison, run 1: KEEP**
The question already expresses its narrow target clearly and economically.
naturalness=0: “What did Micah steal?” is idiomatic and direct.; processing=0: The reader only needs to identify the object of Micah’s theft.; context=0: Naming Micah and the theft sufficiently locates the relevant event.; leakage=0: The question does not identify the stolen property.

**target_preserving_comparison, run 2: KEEP**
The question already expresses the narrow target naturally and unambiguously.
naturalness=0: “What did Micah steal?” is direct and idiomatic.; processing=0: The question contains one participant and one straightforward action.; context=0: Micah's name and the action “steal” sufficiently identify the event in the passage.; leakage=0: No stolen object or amount is supplied.

**independent_dimensions, run 1: KEEP**
A clear, focused question with sufficient context and no avoidable burden.
naturalness=0: “What did Micah steal?” is idiomatic and direct.; processing=0: The respondent only needs to identify the object of Micah’s theft.; context=0: Micah and the act of stealing uniquely locate the relevant incident.; leakage=0: The question does not name the stolen property.

**independent_dimensions, run 2: KEEP**
The wording provides a clear, accessible request for the intended information.
naturalness=0: “What did Micah steal?” is idiomatic and direct.; processing=0: The question asks for one object with no extra roles or modifiers to track.; context=0: Micah's theft is uniquely identifiable in the passage.; leakage=0: The question does not name the stolen property.

## gold:t1_judg17_18:rhwo:open

What did Dan's people want the Levite to ask God?

Group: previous_concerns

**previous_wording_gate, run 1: REWRITE**
“What did Dan's people want the Levite to ask God?” nests asking inside wanting: Dan's people want something, the Levite asks it, and God receives the inquiry. No referent is unresolved, but identifying the requested content requires tracking three roles through two layers.


**previous_wording_gate, run 2: REWRITE**
“Want the Levite to ask God” nests a consultation inside a desire, requiring readers to track Dan’s people, the Levite, and God to identify what is asked. The participants are identifiable, but the two-layer structure creates avoidable burden.


**whole_item_rubric, run 1: KEEP**
The wording preserves the request's roles without unnecessary elaboration.
naturalness=0: “What did Dan's people want the Levite to ask God?” is a natural question.; processing=1: The request involves three parties, but “want the Levite to ask God” clearly assigns their roles.; context=0: “Dan's people” and “the Levite” identify the relevant request in the passage.; leakage=0: The question does not state that they wanted to know whether their journey would succeed.

**whole_item_rubric, run 2: KEEP**
The necessary participant relationships are expressed clearly and manageably.
naturalness=0: “Want the Levite to ask God” is an ordinary way to express the request.; processing=1: The question tracks the Danites, the Levite, and God, but their roles are clearly marked.; context=0: “Dan's people” and “the Levite” locate the request in the passage.; leakage=0: The question does not disclose what they wanted to learn.

**target_preserving_comparison, run 1: KEEP**
The wording directly tests the request's content, with no substantial avoidable burden.
naturalness=0: “What did Dan's people want the Levite to ask God?” is a natural way to ask for the content of their request.; processing=1: The request involves three participants, but “Dan's people,” “the Levite,” and “God” have clearly marked roles.; context=0: The participants identify the inquiry in the passage without unnecessary background.; leakage=0: The question identifies the request but does not state what they wanted to learn.

**target_preserving_comparison, run 2: KEEP**
The participant chain is manageable and necessary, rather than an avoidable wording burden.
naturalness=0: “Want the Levite to ask God” is ordinary, understandable wording.; processing=1: The reader tracks who requests the inquiry, who makes it, and whom he asks; these roles are integral to the target.; context=0: “Dan's people” and “the Levite” locate the relevant request without unnecessary setup.; leakage=0: The question does not state what they wanted to learn.

**independent_dimensions, run 1: KEEP**
The question directly asks for the content of the request with only necessary participant information.
naturalness=0: “What did Dan's people want the Levite to ask God?” is natural and understandable.; processing=1: The reader tracks the people making the request, the Levite acting for them, and God as the one consulted. These roles are necessary to the target and plainly ordered.; context=0: “Dan's people,” “the Levite,” and “ask God” identify the consultation in the passage.; leakage=0: The wording does not supply the requested question about their journey's success.

**independent_dimensions, run 2: KEEP**
The role structure is manageable and serves the intended meaning.
naturalness=0: “What did Dan's people want the Levite to ask God?” is natural, understandable wording.; processing=1: Respondents track the people making the request, the Levite asking, and God being asked; these roles are necessary to the target.; context=0: The request that the Levite ask God identifies a unique exchange.; leakage=0: The wording does not supply the question about the journey's success.

## transfer:handkerchief:original:zh

当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？

Group: focus_variants

**previous_wording_gate, run 1: REWRITE**
The temporal passive setup “当触摸过保罗的手帕和围裙被带到病人那里时” embeds the relative modifier “触摸过保罗的” before the main question “发生了什么”. This is a relative clause inside a temporal/passive setup; the referents are otherwise clear.


**previous_wording_gate, run 2: REWRITE**
“当……时”的时间框架内，“触摸过保罗的”修饰“手帕和围裙”，整个名词短语又充当“被带到病人那里”的被动主语，最后才问“发生了什么”。这是时间／被动铺垫内嵌关系修饰语的结构；没有未明指代，但前置层次造成额外阅读负担。


**whole_item_rubric, run 1: KEEP**
修饰语稍显生硬，但问题仍直接询问病人所经历的结果，整体负担可控。
naturalness=1: “触摸过保罗的手帕和围裙”略显生硬，但结合“被带到病人那里”仍可理解。; processing=1: 题干包含物品修饰语和一个时间框架；整体仍是一条清楚的事件线，五个选项也都简短。; context=0: 手帕、围裙和病人提供了识别医治事件所需的背景，没有转移到其他事件。; leakage=0: 题干只说物品被带到病人那里，没有透露疾病和邪灵随后离开。

**whole_item_rubric, run 2: KEEP**
时间框架和修饰语均服务于事件定位，没有形成实质性的可避免解析负担。
naturalness=0: “当……被带到病人那里时发生了什么”是可自然理解的事件结果问法。; processing=1: “触摸过保罗的”修饰“手帕和围裙”，再交代送到病人那里，结构有一定长度但关系清楚；五个选项也较简短。; context=0: 手帕、围裙和病人提供了有用的事件定位，没有引入后续驱魔事件的多余背景。; leakage=0: 题干只说明物品被送到病人那里，并未说出疾病和邪灵离开的结果。

**target_preserving_comparison, run 1: REWRITE**
改写保留同一事件、时间关系和病人变化的答案范围，去掉非目标性的接触修饰语，降低题干的解析负担。
naturalness=1: “当触摸过保罗的手帕和围裙被带到病人那里时”读起来略显拗口，修饰语边界不够醒目。; processing=2: 读者需先把“触摸过保罗的”解析为修饰“手帕和围裙”，再接上“被带到”及整个“当……时”结构。直接以保罗的物品定位事件，再问病人的变化，可免去这层不服务于目标的修饰语解析；五个选项本身较简单。; context=0: 物品被带到病人那里的事件提供了充分定位，没有缺少必要背景。; leakage=0: 题干没有说明疾病和邪灵离开了病人；这一结果仅出现在选项中。
Diagnostic alternative: 保罗的手帕和围裙被带到病人那里后，病人怎么样了？
A. 病人陷入了深度睡眠
B. 疾病和邪灵离开了病人
C. 犹太驱魔师给病人驱魔
D. 病人变得无法说话
E. 根据这段文字无法判断 (preservation: preserved)

**target_preserving_comparison, run 2: KEEP**
虽然略显书面，但事件和结果的关系清楚，没有足以要求改写的可避免负担。
naturalness=1: “触摸过保罗的手帕和围裙”略显书面，但整句仍是可理解的正常表达。; processing=1: 需读完“当……被带到病人那里时”这一事件定位，再判断结果；修饰语和时间框架并未形成明显的多层解码负担，选项也简短。; context=0: 接触过保罗的物品及其被带到病人那里，足以明确所问事件。; leakage=0: 题干未交代病人的变化；正确结果出现在选项中本身不构成泄露。

**independent_dimensions, run 1: REWRITE**
应保留病人发生何种变化这一目标，减少前置修饰，并修复“触摸过保罗的手帕和围裙”的不自然与歧义。
naturalness=2: “触摸过保罗的手帕和围裙”让无生命的物品作“触摸”的执行者，也容易先被理解为有人触摸过保罗的物品，需要回读修正。; processing=2: 在读到“发生了什么”之前，需解析“触摸过保罗的”的修饰范围，再处理物品“被带到病人那里”的关系；前一层细节并非测试病人变化所必需。; context=1: 物品被带到病人那里已能定位事件，“触摸过保罗”的细节对所问结果不是必需的。; leakage=0: 题干没有说明疾病和邪灵离开病人；选项B本身不构成答案泄露。

**independent_dimensions, run 2: REWRITE**
应保留对病人变化的询问，但现有前置修饰语存在歧义，并与被动、时间框架叠加，造成可避免的理解负担。
naturalness=2: “触摸过保罗的手帕和围裙”容易先被理解为有人触摸过保罗的物品；若理解为物品曾接触保罗，又需调整对“触摸”的通常理解。; processing=2: 读者需在较长的“当……时”框架内切分“触摸过保罗的”与“手帕和围裙”，再处理“被带到”的角色关系，最后才读到泛指的“发生了什么”。修饰范围的歧义增加了可避免的回读负担。; context=0: 物品被带到病人那里是相关且充分的事件定位；问题不在背景不足或无关。; leakage=0: 题干没有说出病人的变化；选项B列出正确结果本身不构成泄露。

## transfer:handkerchief:repair:zh

摸过保罗的手帕和围裙被带到病人那里。病人随后怎么样了？

Group: focus_variants

**previous_wording_gate, run 1: REWRITE**
The passive setup “摸过保罗的手帕和围裙被带到病人那里” embeds the relative modifier “摸过保罗的” before the main question “病人随后怎么样了？” This requires processing a modified passive subject and then linking “随后” to that setup. “病人” itself has a clear referent, but the relative-clause/passive setup creates the specified wording burden.


**previous_wording_gate, run 2: KEEP**
首句以“摸过保罗的”修饰“手帕和围裙”，再用简单被动结构交代物品被带到病人那里；第二句独立询问随后的结果。修饰语不嵌套于时间从句中，“病人”的指代明确，选项也都是直接的结果陈述。


**whole_item_rubric, run 1: REWRITE**
问题目标明确，但前置说明造成可避免的句法重析负担，应改写。
naturalness=2: “摸过保罗的手帕和围裙被带到……”容易先读成有人“摸过保罗的手帕和围裙”，读到“被带到”才需改析句子。; processing=2: 开头的“摸过保罗的”与后续名词、被动结构形成可避免的切分负担；即使末句简短，也需先修复整句的角色关系。; context=0: 物品被带到病人处是相关事件锚点，没有大量无关铺垫。; leakage=0: 铺垫只交代物品被带到病人那里，没有说明病人的变化。

**whole_item_rubric, run 2: REWRITE**
The introductory statement needs more natural wording even though the final question is clear.
naturalness=2: “摸过保罗的手帕和围裙” awkwardly makes the objects agents of “摸”; readers must repair this to mean objects that had been in contact with Paul.; processing=1: The opening modifier needs local interpretation, but “病人随后怎么样了？” and the choices are otherwise straightforward.; context=0: The objects being brought to the sick people provide a useful event anchor.; leakage=0: The setup does not say what subsequently happened to the patients; the answer’s presence among choices is not leakage.

**target_preserving_comparison, run 1: REWRITE**
替代表述保留病人、物品被带去之后的时间关系及变化的答案范围，去除了非目标性的触摸关系解析负担。
naturalness=2: “摸过保罗的手帕和围裙”容易被读成有人摸过保罗的物品；作为后续“被带到”的主语时，需要重新理解修饰关系。; processing=2: 读者须先判断“摸过”的施事及“保罗的”的归属，才能接到“被带到病人那里”。直接交代物品被带去这一事件即可保留所问的病人变化。; context=0: 物品被带到病人那里为“随后”提供了有用的事件锚点，没有缺少定位信息。; leakage=0: 开头只交代物品被送去，并未说明病人是否康复或邪灵是否离开。
Diagnostic alternative: 保罗的手帕和围裙被带到病人那里后，病人怎么样了？ (preservation: preserved)

**target_preserving_comparison, run 2: REWRITE**
The alternative retains the patients, delivery event, subsequent outcome, and answer scope while removing an ambiguous modifier that is not part of the explicit target.
naturalness=2: “摸过保罗的手帕和围裙” invites the reading ‘touched Paul's handkerchiefs and aprons’; treating the cloths as things that “摸过保罗” requires repair.; processing=2: Before reaching “被带到”, readers must resolve whether “摸过” describes the cloths or an action performed on them. The alternative removes this non-target attachment problem.; context=0: The cloths being brought to the sick people sufficiently identify the relevant event.; leakage=0: The setup states the delivery, not the resulting healing or departure of evil spirits.
Diagnostic alternative: 保罗的手帕和围裙被带到病人那里后，病人怎么样了？
A. 病人陷入了深度睡眠
B. 疾病和邪灵离开了病人
C. 犹太驱魔师给病人驱魔
D. 病人变得无法说话
E. 根据这段文字无法判断 (preservation: preserved)

**independent_dimensions, run 1: REWRITE**
开头存在需要修复的表达，并给目标之外的接触关系增加了显著解析负担；后面的简短问题不能抵消这部分负担。
naturalness=2: “摸过保罗的手帕和围裙”容易被读成手帕和围裙主动“摸”保罗，需要修复为物品曾接触保罗的意思。; processing=2: 回答病人状况前，需先解析“摸过保罗的”的修饰范围、确定物品与保罗的接触关系，再处理“被带到”的角色关系；前一层并非测试病人变化所必需。; context=1: 物品被带到病人那里可以定位事件，但详细交代物品与保罗的接触关系，对所问变化并非必要。; leakage=0: 开头只交代物品被送到病人那里，没有说明疾病或邪灵是否离开。

**independent_dimensions, run 2: REWRITE**
The introductory modifier creates avoidable ambiguity even though the outcome question itself is clear.
naturalness=2: “摸过保罗的手帕和围裙” is awkward: readers can initially take “保罗的手帕和围裙” as the object of “摸过,” rather than as objects that had touched Paul.; processing=2: Before reaching “病人随后怎么样了,” readers must resolve the attachment of “的” and who or what touched whom. That repair is unnecessary for testing the patients’ outcome.; context=0: The objects being brought to the patients provide a useful event anchor.; leakage=0: The setup says the objects arrived, not that the patients recovered or that evil spirits left.

## transfer:handkerchief:repair:en

Cloths that had touched Paul were taken to the sick. What happened to the sick?

Group: focus_variants

**previous_wording_gate, run 1: REWRITE**
The preliminary passive sentence embeds the relative clause “that had touched Paul” within “Cloths … were taken to the sick,” before the main question. “The sick” has a clear referent, but this relative-within-passive setup creates the prohibited layered lead-in.


**previous_wording_gate, run 2: REWRITE**
The passive setup “Cloths that had touched Paul were taken to the sick” embeds the relative clause “that had touched Paul” before the main question. This is the specified relative-within-passive setup burden, despite the sentence break. “The sick” clearly refers to the same people in both sentences; there is no unresolved referent.


**whole_item_rubric, run 1: KEEP**
The setup locates the event without supplying its outcome, and the question directly asks about the intended result.
naturalness=0: “Cloths that had touched Paul were taken to the sick” and “What happened to the sick?” are natural English.; processing=1: The setup contains one short modifier, “that had touched Paul,” followed by a direct question with a repeated, clear referent.; context=0: The cloths being taken to the sick provide a useful anchor for the particular healing event.; leakage=0: The setup states that cloths reached the sick, not that their illnesses were cured or spirits left.

**whole_item_rubric, run 2: KEEP**
The event anchor supports a clear question about the sick people's outcome without supplying that outcome.
naturalness=0: “What happened to the sick?” is idiomatic and directly identifies the people being asked about.; processing=1: The setup identifies the cloths and their destination, followed by a short outcome question; the combined item remains easy to follow.; context=0: “Cloths that had touched Paul were taken to the sick” usefully anchors the relevant healing event.; leakage=0: The setup states that the cloths were brought, not that healing or deliverance occurred.

**target_preserving_comparison, run 1: KEEP**
The setup supplies a useful event anchor without giving the outcome or imposing substantial avoidable load.
naturalness=0: Both “Cloths that had touched Paul were taken to the sick” and “What happened to the sick?” are ordinary English.; processing=1: The setup contains a short identifying clause and a passive, but establishes a straightforward event before the outcome question.; context=0: The cloths reaching the sick usefully identify which event's outcome is being asked about.; leakage=0: Saying the cloths were taken to the sick does not state that illnesses were cured or spirits left.

**target_preserving_comparison, run 2: KEEP**
The setup usefully identifies the event while leaving the intended outcome for respondents to supply.
naturalness=0: “Cloths that had touched Paul” and “What happened to the sick?” are idiomatic and direct.; processing=1: The reader retains one event anchor across two short sentences; the relative clause identifies the relevant cloths without unnecessary detail.; context=0: The cloths being taken to the sick clearly locates the event being asked about.; leakage=0: The setup states that the cloths were taken to the sick, not what subsequently happened to them.

**independent_dimensions, run 1: KEEP**
The setup locates the event without supplying its outcome, and the question directly tests the explicit target.
naturalness=0: “Cloths that had touched Paul were taken to the sick” and “What happened to the sick?” are natural English.; processing=1: The reader follows the cloths from Paul to the sick and then identifies the outcome for those people. This is a manageable event sequence, with “the sick” repeated clearly.; context=0: The cloths provide a useful anchor distinguishing this healing event from other events involving Paul.; leakage=0: The setup says only that the cloths reached the sick; it does not state that illnesses were cured or spirits left.

**independent_dimensions, run 2: KEEP**
The whole item provides a clear event anchor and directly asks about the intended outcome without supplying it.
naturalness=0: “Cloths that had touched Paul” and “What happened to the sick?” are idiomatic and clear.; processing=1: The reader processes one short identifying modifier and a passive transfer, then follows the repeated reference to “the sick.” The combined demand is manageable.; context=0: The cloths being taken to the sick provide a useful anchor for the particular healing event.; leakage=0: The setup states that cloths were taken to the sick, not that illnesses or evil spirits left them.

## focus:handkerchief:direct:zh

根据这段经文，病人的情况有什么变化？

Group: focus_variants

**previous_wording_gate, run 1: KEEP**
“根据这段经文” is a simple framing phrase, followed by one direct question about changes in the patients’ condition. There is no embedded clause, and “病人” clearly refers to the patients mentioned in the passage; the options present distinct outcomes.


**previous_wording_gate, run 2: KEEP**
“根据这段经文”是依据状语，主句以“病人的情况”为主语询问变化，无嵌套从句。“病人”在经文中有明确对应，选项为简单陈述，无未解决的指代。


**whole_item_rubric, run 1: KEEP**
直接询问预定目标，不加入与目标无关的解析负担，可保留。
naturalness=0: “病人的情况有什么变化”是自然直接的问法。; processing=0: 题干无需解析物品的修饰关系，选项均为简短、易比较的陈述。; context=0: 经文中“病人”的指向明确，“根据这段经文”提供了足够范围。; leakage=0: 题干只询问变化，没有预先说明疾病和邪灵离开。

**whole_item_rubric, run 2: KEEP**
直接询问既定目标，选项比较的阅读需求普通且可控。
naturalness=0: “病人的情况有什么变化？”是自然、直接的中文问法。; processing=1: 需比较五个简短选项，包括“无法判断”，但没有复杂的角色或修饰关系。; context=0: “根据这段经文”和“病人”足以定位相关内容，不必另加物品转送的背景。; leakage=0: 题干没有说明病人的具体变化；正确描述仅作为一个选项出现。

**target_preserving_comparison, run 1: KEEP**
问题直接针对病人的变化，现有语境足以消除歧义，没有明显可减轻的负担。
naturalness=0: “病人的情况有什么变化”自然直接，选项也均可理解。; processing=0: 只需查明病人的变化；五个选项不要求比较多层条件或角色关系。; context=0: 所给经文中“病人”明确指向第12节的群体，不必重述手帕和围裙的背景。; leakage=0: 题干没有说明变化的具体内容；正确答案作为选项出现不构成泄露。

**target_preserving_comparison, run 2: KEEP**
问题直接保留预定的结果目标，没有引入物品相关的无关负担。
naturalness=0: “病人的情况有什么变化？”自然地询问结果，选项表述清楚。; processing=1: 需要阅读五个选项并区分情况变化、他人行动和无法判断，但各项都短且结构简单。; context=0: “病人”能够定位经文中疾病和邪灵离开的群体，无需补充手帕、围裙等信息。; leakage=0: 题干没有说明发生了哪一种变化；正确答案出现在选项中不构成泄露。

**independent_dimensions, run 1: KEEP**
直接测试指定的病人变化，现有语境足以定位，无需加入物品相关背景。
naturalness=0: “病人的情况有什么变化”是自然、直接的状况提问。; processing=0: 直接询问病人的变化，无需先解码物品接触关系；各选项也容易区分。; context=0: 所给段落明确提到接受手帕和围裙的“病人”，这一称呼足以定位目标群体。; leakage=0: “根据这段经文”没有提供病人变化的具体内容。

**independent_dimensions, run 2: KEEP**
直接聚焦指定的病人变化，没有引入物品相关的额外任务。负担判断仍需受访者验证。
naturalness=0: “病人的情况有什么变化？”是自然、常见的询问方式。; processing=1: 需在五个选项中辨认病人的变化；包括“无法判断”选项，但整体比较要求仍属普通。; context=0: “病人”能定位经文前部明确提到的群体，无须重述手帕和围裙的经过。; leakage=0: 题干没有说明病人发生了哪种变化。

## constructed:leak

小林把书搬进屋里。是谁把书搬进屋里的？

Group: constructed

**previous_wording_gate, run 1: REWRITE**
A declarative setup is followed by a simple 是谁…的 question, with no embedded clauses or unresolved referents. However, “小林把书搬进屋里” explicitly supplies the answer to “是谁把书搬进屋里的？”


**previous_wording_gate, run 2: REWRITE**
结构是一个陈述句接一个“是谁”的提问，没有嵌套从句，也没有未明确的指代。但前句“小林把书搬进屋里”已经直接给出了后句所问的人物，题干泄露答案。


**whole_item_rubric, run 1: REWRITE**
The introductory statement explicitly supplies the target answer.
naturalness=0: Both “小林把书搬进屋里” and “是谁把书搬进屋里的” are idiomatic.; processing=0: The two short sentences have clear roles and references.; context=0: The setup directly concerns the event being asked about, with no irrelevant framing.; leakage=3: “小林把书搬进屋里” explicitly names the person immediately before asking who moved the books.

**whole_item_rubric, run 2: REWRITE**
The introductory statement explicitly supplies the answer to the intended identification question.
naturalness=0: Both “小林把书搬进屋里” and “是谁把书搬进屋里的” are natural Chinese.; processing=0: The two short sentences are easy to parse; their repetition adds little decoding demand.; context=0: The book-moving event is clearly identified, with no missing reference.; leakage=3: “小林把书搬进屋里” explicitly names the person immediately before asking who moved the books.

**target_preserving_comparison, run 1: REWRITE**
Removing the introductory answer preserves the actor-identification target and eliminates explicit leakage.
naturalness=0: Both “小林把书搬进屋里” and “是谁把书搬进屋里的” are natural Chinese.; processing=0: The repeated action is easy to parse and creates no substantial memory demand.; context=1: The introductory statement repeats the event already identified in the question and is removable.; leakage=3: “小林把书搬进屋里” explicitly names the person the following question asks respondents to identify.
Diagnostic alternative: 是谁把书搬进屋里的？ (preservation: preserved)

**target_preserving_comparison, run 2: REWRITE**
Removing the introductory answer statement preserves the exact actor-identification target without giving the answer away.
naturalness=0: Both “小林把书搬进屋里” and “是谁把书搬进屋里的” are natural Chinese.; processing=0: The repeated action is easy to parse and introduces no difficult role or reference tracking.; context=1: The introductory sentence is removable; the passage already provides enough context for the question.; leakage=3: “小林把书搬进屋里” explicitly names the person whom the following question asks respondents to identify.
Diagnostic alternative: 是谁把书搬进屋里的？ (preservation: preserved)

**independent_dimensions, run 1: REWRITE**
The introductory statement explicitly gives the identity being tested.
naturalness=0: Both “小林把书搬进屋里” and “是谁把书搬进屋里的” are idiomatic.; processing=0: The repeated action and simple actor question are readily parsed.; context=0: The book-moving event is clearly identified; there is no distracting background.; leakage=3: “小林把书搬进屋里” explicitly identifies 小林 immediately before asking who moved the books.

**independent_dimensions, run 2: REWRITE**
Although naturally worded, the setup explicitly supplies the target answer.
naturalness=0: Both “小林把书搬进屋里” and “是谁把书搬进屋里的？” are natural Chinese.; processing=0: The setup and question are straightforward and require no difficult reference tracking.; context=0: “把书搬进屋里” clearly identifies the relevant event.; leakage=3: The setup explicitly names “小林” as the person who moved the books, which is exactly what the question asks.

## constructed:direct

是谁把书搬进屋里的？

Group: constructed

**previous_wording_gate, run 1: KEEP**
A single 是……的 focus question asks for the actor of “把书搬进屋里”; there is no embedded clause or unresolved referent.


**previous_wording_gate, run 2: KEEP**
这是自然的“是谁……的”问句，“把书搬进屋里”直接说明所问的动作，没有嵌套从句或未明指代。


**whole_item_rubric, run 1: KEEP**
问法直接，事件明确，各项负担均低。
naturalness=0: “是谁把书搬进屋里的？”是自然、直接的问法。; processing=0: 只需识别搬书的人，没有额外的角色或指代负担。; context=0: “把书搬进屋里”明确对应文中的事件。; leakage=0: 题目没有透露是谁搬了书。

**whole_item_rubric, run 2: KEEP**
The item directly tests the explicit target with no unnecessary framing.
naturalness=0: “是谁把书搬进屋里的？” is a natural Chinese identification question.; processing=0: The action and destination are expressed directly, with no competing references.; context=0: “把书搬进屋里” uniquely identifies the relevant action in the passage.; leakage=0: The question names the action but not the person who performed it.

**target_preserving_comparison, run 1: KEEP**
问法自然明确，没有可通过改写消除的实质负担。
naturalness=0: “是谁把书搬进屋里的？”是自然、直接的问法。; processing=0: 只需识别“把书搬进屋里”这一动作的执行者。; context=0: “把书搬进屋里”准确定位了原文中的动作，无需补充背景。; leakage=0: 题目没有说出搬书的人是谁。

**target_preserving_comparison, run 2: KEEP**
The question is already direct, natural, and unambiguous.
naturalness=0: “是谁把书搬进屋里的？” is an idiomatic Chinese question identifying the actor.; processing=0: It asks for one participant in one concrete action.; context=0: “把书搬进屋里” uniquely identifies the relevant action in the supplied passage.; leakage=0: Neither 小林 nor any other answer is supplied in the question.

**independent_dimensions, run 1: KEEP**
问法自然，事件明确，没有多余负担或答案泄露。
naturalness=0: “是谁把书搬进屋里的？”是自然、直接的问法。; processing=0: 只需辨认“把书搬进屋里”这一动作的执行者。; context=0: “把书搬进屋里”足以定位短文中的唯一相关事件。; leakage=0: 题目没有说出搬书的人是谁。

**independent_dimensions, run 2: KEEP**
The wording directly tests the explicit target without unnecessary setup.
naturalness=0: “是谁把书搬进屋里的？” is idiomatic Chinese for identifying the person responsible.; processing=0: The action and destination are explicit; respondents only need to identify the actor.; context=0: “把书搬进屋里” uniquely identifies the action in the short passage.; leakage=0: The question does not supply the actor's name.

## constructed:anchor

谁把书带到图书馆？

Group: constructed

**previous_wording_gate, run 1: KEEP**
A single direct 谁-question using a straightforward 把-construction, “把书带到图书馆”; no embedded clause or unresolved referent.


**previous_wording_gate, run 2: KEEP**
单层“谁把书带到图书馆”的把字问句，“到图书馆”表示动作终点，没有嵌套从句。“书”和“图书馆”均有明确语境，对应人物唯一，无未解决的指代。


**whole_item_rubric, run 1: KEEP**
The wording directly tests the explicit target without additional burden.
naturalness=0: “谁把书带到图书馆？” is direct, idiomatic Chinese.; processing=0: The question asks for one person using a simple action and destination.; context=0: “图书馆” distinguishes the relevant event from the earlier trip to school.; leakage=0: The question states the identifying action but does not supply the person's name.

**whole_item_rubric, run 2: KEEP**
问法简洁，定位准确，无额外理解负担。
naturalness=0: “谁把书带到图书馆？”是自然直接的中文问法。; processing=0: 只需根据目的地辨认人物，没有附加修饰或选项比较。; context=0: “图书馆”足以区别于带书到学校的另一件事。; leakage=0: 题干没有给出人物姓名。

**target_preserving_comparison, run 1: KEEP**
The wording is already a natural, unambiguous way to test the explicit target.
naturalness=0: “谁把书带到图书馆？” is idiomatic, direct Chinese.; processing=0: The question asks for one participant in a simple action.; context=0: “图书馆” clearly distinguishes the relevant event from taking the book to school.; leakage=0: The question supplies the destination but does not name the person being tested.

**target_preserving_comparison, run 2: KEEP**
问题已自然且无歧义地询问预定目标，无需改写。
naturalness=0: “谁把书带到图书馆？”是自然、直接的问法。; processing=0: 只需根据目的地辨认人物，没有额外修饰或指代负担。; context=0: “图书馆”足以区分两次带书事件，无需再加“下午”。; leakage=0: 题干没有给出人物姓名。

**independent_dimensions, run 1: KEEP**
The destination alone provides sufficient context for the explicit person-identification target.
naturalness=0: “谁把书带到图书馆？” is a natural, direct Chinese question.; processing=0: The respondent matches “图书馆” to the person who brought the book there.; context=0: “图书馆” distinguishes the relevant action from taking the book to school; no time anchor is needed.; leakage=0: The question states the destination but does not identify the person.

**independent_dimensions, run 2: KEEP**
使用足够且简洁的事件锚点，准确保留指定目标。负担判断仍需受访者验证。
naturalness=0: “谁把书带到图书馆？”自然直接。; processing=0: 只需根据目的地“图书馆”辨认人物，没有额外角色或时间比较要求。; context=0: “图书馆”已能区分两次带书事件，无须再加“下午”。; leakage=0: 题干没有给出带书者的姓名。

## constructed:ambiguous

谁把书带走了？

Group: constructed

**previous_wording_gate, run 1: REWRITE**
The syntax is a simple subject question, but “把书带走了” leaves the relevant book-moving event unresolved. Both 小林 and 小周 take books somewhere in the passage, and the question supplies neither a destination nor a time to distinguish them.


**previous_wording_gate, run 2: REWRITE**
题目只有“谁”作疑问主语的简单把字句，没有嵌套结构；但“书”和“带走”没有限定时间或目的地。上下文中小林和小周都把书带到别处，所问事件的指向未解决，不能唯一确定是在问哪一次带书。


**whole_item_rubric, run 1: REWRITE**
明确目标是辨认把书带到图书馆的人，但当前问题未区分两次带书事件，需要补足事件限定。
naturalness=0: “谁把书带走了”作为独立问句自然通顺。; processing=1: 句式简单，但读者需在小林和小周两次带书事件之间猜测所指。; context=2: 缺少消歧信息：两人都把书带到某处，题干没有用“图书馆”或“下午”限定目标事件。; leakage=0: 题干没有提供所问人物的身份。

**whole_item_rubric, run 2: REWRITE**
The wording is easy to read but does not distinguish the library trip from the school trip.
naturalness=0: “谁把书带走了？” is idiomatic Chinese.; processing=0: The short question is readily parsed.; context=2: Insufficient disambiguation: both 小林 and 小周 took books somewhere, but the question omits “图书馆,” which distinguishes the intended event.; leakage=0: The question supplies no person’s identity.

**target_preserving_comparison, run 1: REWRITE**
补出目标中的目的地即可消除歧义，不改变所问人物或事件。
naturalness=0: “谁把书带走了”本身是自然的中文问句。; processing=0: 句子结构简单，没有额外的记忆或嵌套负担。; context=2: 缺少“图书馆”这一必要限定；小林和小周都把书带到了别处，“带走”不能唯一指向目标事件。; leakage=0: 题干没有透露带书者的身份。
Diagnostic alternative: 谁把书带到了图书馆？ (preservation: preserved)

**target_preserving_comparison, run 2: REWRITE**
The alternative supplies the destination required by the explicit target, allowing respondents to select the intended event rather than guess.
naturalness=0: “谁把书带走了？” is natural Chinese in isolation.; processing=1: The sentence is easy to parse, but readers must guess which of the two book-carrying events is intended.; context=2: Missing disambiguation: “带走” does not distinguish 小林 taking books to school from 小周 taking books to the library. Naming the destination repairs this.; leakage=0: The question does not state either person's identity.
Diagnostic alternative: 谁把书带到图书馆了？ (preservation: preserved)

**independent_dimensions, run 1: REWRITE**
语句自然，但缺少“图书馆”这一必要定位信息，无法稳定询问明确指定的目标。
naturalness=0: “谁把书带走了”本身是自然的口语问法。; processing=1: 需要在小林和小周两次带书的事件之间判断题目所指，但题干没有提供选择依据。; context=2: 缺少必要的目的地锚点：小林把书带到学校，小周把书带到图书馆，“带走”不能唯一指向后者。; leakage=0: 题干没有提供目标人物的身份。

**independent_dimensions, run 2: REWRITE**
The question needs an event anchor that distinguishes taking books to the library from taking them to school.
naturalness=0: “谁把书带走了？” is idiomatic Chinese.; processing=0: The sentence is readily parsed and directly asks for a person.; context=2: The destination anchor is missing: both 小林 and 小周 took books somewhere, so “带走了” does not uniquely select the library event.; leakage=0: The question supplies no person’s identity.

## hard:t1_judg17_18:1654:mcq

来士的人为什么富足？

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
The main question asks why “来士的人” were prosperous; each option supplies one straightforward causal clause. No nested viewpoint or unresolved referent creates extra burden.


**previous_wording_gate, run 2: KEEP**
主句“来士的人为什么富足”直接询问原因；选项用单层“因为”原因分句作答。“他们”均指来士的人，无未解决的指代或复杂修饰。


**whole_item_rubric, run 1: KEEP**
原因比较属于正常的选择题阅读需求，没有显著可避免负担。
naturalness=0: “来士的人为什么富足？”及四个“因为……”选项表达自然。; processing=1: 需要比较四个原因，但选项简短、结构一致，没有复杂的角色或指代转换。; context=0: “来士的人”明确指出所问的人群，无多余背景。; leakage=0: 题干没有说明富足的原因；正确原因出现在选项中本身不构成泄露。

**whole_item_rubric, run 2: KEEP**
原因问法本身清楚，没有可见的额外措辞负担。
naturalness=0: “来士的人为什么富足？”表达自然，选项与问法衔接顺畅。; processing=0: 只需比较四个简短的原因，没有嵌套条件或复杂指代。; context=0: “来士的人”明确限定了所问群体，无需补充其他背景。; leakage=0: 题干提出富足的原因，但没有提供该原因。

**target_preserving_comparison, run 1: KEEP**
原因问题及选项易于理解，没有明显可避免的措辞负担。
naturalness=0: “来士的人为什么富足？”及各个“因为”选项都自然通顺。; processing=1: 需比较四个简短的原因选项；各选项结构平行，没有额外的指代或修饰负担。; context=0: “来士的人”明确限定了所问的人群和事件。; leakage=0: 题干只提出富足的原因，没有提前提供该原因；答案出现在选项中不构成泄露。

**target_preserving_comparison, run 2: KEEP**
因果询问本身没有造成额外负担，题干和选项均易于理解。
naturalness=0: “来士的人为什么富足？”问法自然，各选项以“因为”承接。; processing=0: 四个选项结构平行，每项只提出一个原因。; context=0: “来士的人”明确指出所问的群体，不需要增加背景。; leakage=0: 题干提出富足这一状态，但没有给出所问的原因。

**independent_dimensions, run 1: KEEP**
原因问题直接明确，选项简洁，没有不必要的背景。
naturalness=0: “来士的人为什么富足？”及四个“因为”选项都自然通顺。; processing=0: 四个选项分别给出简短、可区分的原因，无需处理复杂的指代或角色关系。; context=0: “来士的人”明确指出所问的人群，不需要补充探子的行程。; leakage=0: 题干只提出富足的原因，没有预先给出原因；正确答案出现在选项中不构成泄露。

**independent_dimensions, run 2: KEEP**
原因问法本身不增加不必要负担，各维度均通过。负担判断仍需受访者验证。
naturalness=0: “来士的人为什么富足？”自然明确。; processing=0: 各选项以“因为”引出一个简短原因，没有嵌套关系或复杂比较要求。; context=0: “来士的人”明确定位所问群体，不需要补充五人出行的背景。; leakage=0: 题干给出待解释的富足状态，但没有提供其原因。

## hard:t1_2kgs11:a99f:mcq

谁和他的奶母在耶和华的殿里藏了六年？

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
A single main question coordinates “谁和他的奶母” as the subject, followed by location and duration phrases. There are no embedded clauses; “他的” naturally refers to the person queried by “谁,” so no referent is unresolved.


**previous_wording_gate, run 2: KEEP**
单一疑问主句；“和他的奶母”连接共同藏匿的人，“他的”回指待回答的“谁”。没有嵌套从句或未明指代，选项简明。


**whole_item_rubric, run 1: KEEP**
The item uses clear, relevant details to ask for a single participant.
naturalness=0: “谁和他的奶母……藏了六年” is natural Chinese.; processing=1: The companion, location, and duration form a straightforward event description; “他的” readily refers to the person being asked about.; context=0: “奶母”, “耶和华的殿”, and “六年” clearly locate the intended hiding event.; leakage=0: The question supplies identifying circumstances but does not name the hidden person.

**whole_item_rubric, run 2: KEEP**
问法直接，事件定位清楚，各维度均无须改写。
naturalness=0: “谁和他的奶母……藏了六年”表达自然，问人明确。; processing=0: 地点和时长都直接限定同一件事；四个选项均为人名，无额外比较负担。; context=0: “和他的奶母”“在耶和华的殿里”“六年”足以定位所问事件。; leakage=0: 题干没有说出藏身者的姓名。

**target_preserving_comparison, run 1: KEEP**
The item identifies the relevant episode clearly without unnecessary framing or difficult wording.
naturalness=0: “谁和他的奶母……藏了六年” is a natural way to ask which person hid with his nurse.; processing=0: “他的” readily refers to the person being asked about; the location, duration, and name choices are easy to follow.; context=0: “耶和华的殿里” and “六年” clearly identify the hiding episode.; leakage=0: The question supplies the hiding circumstances but not the person's name.

**target_preserving_comparison, run 2: KEEP**
事件线索清楚，措辞自然，没有需要消除的明显负担。
naturalness=0: “谁和他的奶母……藏了六年”是自然、直接的人物提问。; processing=1: 需结合奶母、地点和六年的时间定位人物；这些都是明确的事件线索，四个人名选项没有额外结构负担。; context=0: “在耶和华的殿里藏了六年”足以定位所问事件。; leakage=0: 题干没有说出藏起来的人是谁。

**independent_dimensions, run 1: KEEP**
The item asks a clear identity question with useful event anchors and no substantial avoidable burden.
naturalness=0: “谁和他的奶母……藏了六年” is a natural identity question.; processing=0: “他的” refers straightforwardly to the person being asked about; place and duration fit into a simple event description.; context=0: The nurse, temple, and six-year period clearly locate the hiding event without unrelated family background.; leakage=0: The stem describes the hiding event but does not name the person sought.

**independent_dimensions, run 2: KEEP**
问法自然，事件定位充分，没有明显可避免的理解负担。
naturalness=0: “谁和他的奶母……藏了六年”是自然、直接的问法。; processing=0: 只需辨认与奶母一起藏身的人；地点和时长共同定位事件，选项容易区分。; context=0: “在耶和华的殿里藏了六年”足以定位所问事件，没有多余背景。; leakage=0: 题干没有说出藏身者的姓名；正确姓名出现在选项中不构成泄露。

## hard:t1_2kgs6_7:3452:mcq

长大麻风的人承认做得不对以后，打算怎么做？

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
“长大麻风的人” is the subject, followed by one temporal clause, “承认做得不对以后,” and the main question “打算怎么做.” The omitted main-clause subject clearly remains the same people; the options are direct and distinct.


**previous_wording_gate, run 2: KEEP**
“承认做得不对以后”是一个时间修饰语，主问句为“打算怎么做”；“做得不对”是自然的补语结构。省略的主语明确承接“长大麻风的人”，选项简短，无未明指代。


**whole_item_rubric, run 1: KEEP**
The event anchor is useful, and the question and choices impose only ordinary reading demands.
naturalness=0: “承认做得不对以后，打算怎么做” is natural Chinese phrasing.; processing=1: The reader follows one temporal relation, “……以后,” and compares four short action choices.; context=0: “承认做得不对以后” usefully distinguishes their next plan from their earlier hiding of goods.; leakage=0: Acknowledging wrongdoing does not reveal that they planned to “告诉王家”; that action appears only among the choices.

**whole_item_rubric, run 2: KEEP**
The item clearly asks about the men's next intended action without avoidable burden.
naturalness=0: “承认做得不对以后，打算怎么做” is natural, direct Chinese.; processing=1: The temporal anchor and four short action choices create ordinary, manageable reading demand.; context=0: “承认做得不对以后” usefully identifies the point in the account being tested.; leakage=0: Acknowledging wrongdoing does not reveal their next plan; the answer appears only as one of the choices.

**target_preserving_comparison, run 1: KEEP**
The temporal anchor prevents confusion with earlier actions, and the choices impose only ordinary comparison demands.
naturalness=0: “承认做得不对以后，打算怎么做” is natural Chinese for asking about their next intended action.; processing=1: The reader tracks one temporal relation, “以后,” and compares four short, parallel action choices.; context=0: “长大麻风的人” identifies the participants, and “承认做得不对以后” usefully distinguishes their plan from their earlier hiding of goods.; leakage=0: Acknowledging wrongdoing does not disclose their subsequent plan; “告诉王家” appears only as an answer choice.

**target_preserving_comparison, run 2: KEEP**
The temporal framing is useful, and the question and options impose no substantial avoidable burden.
naturalness=0: “承认做得不对以后，打算怎么做” is natural, direct Chinese.; processing=1: The reader connects one temporal anchor with a planned action and compares four short, concrete choices.; context=0: “承认做得不对以后” usefully distinguishes their new plan from their earlier hiding of possessions.; leakage=0: Acknowledging wrongdoing does not disclose their plan to tell the royal household; that plan appears only among the choices.

**independent_dimensions, run 1: KEEP**
The temporal framing is useful, and the choices impose only ordinary reading demand.
naturalness=0: “承认做得不对以后，打算怎么做？” is a natural way to ask about their next intended action.; processing=1: The respondent follows one temporal anchor and compares four short, distinct actions.; context=0: “长大麻风的人” and their acknowledgment identify the relevant decision without unnecessary background.; leakage=0: Acknowledging wrongdoing does not reveal their plan; “去告诉王家” appears only as an answer choice.

**independent_dimensions, run 2: KEEP**
The event anchor and concise options support an accessible question about their next intended action.
naturalness=0: “承认做得不对以后，打算怎么做” is idiomatic and direct.; processing=1: Respondents connect the acknowledgment to the subsequent plan and compare four short, distinct actions; this is manageable and relevant.; context=0: “长大麻风的人” and “承认做得不对以后” clearly locate the decision in the passage.; leakage=0: Acknowledging wrongdoing does not itself disclose their plan; “告诉王家” appears only as an answer choice.

## hard:t1_judg9:0bd2:mcq

亚比米勒来到楼门，是要做什么？

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
“亚比米勒来到楼门” provides a simple event setup for the purpose question “是要做什么.” The options are direct action phrases without embedded clauses, and the shared actor is explicit.


**previous_wording_gate, run 2: KEEP**
“亚比米勒来到楼门”交代情境，主问句“是要做什么”询问同一人物的目的，省略的主语明确。选项为直接的动作短语，无嵌套视角或未解决的指代。


**whole_item_rubric, run 1: KEEP**
The event anchor is useful, and the question directly tests the intended purpose.
naturalness=0: “来到楼门，是要做什么” is an idiomatic purpose question.; processing=0: The question and four short action choices are readily parsed and compared.; context=0: “亚比米勒来到楼门” precisely anchors the intended moment.; leakage=0: Approaching the entrance does not itself disclose the intention to burn the tower.

**whole_item_rubric, run 2: KEEP**
背景必要且简洁，目的问法和选项易于理解。
naturalness=0: “来到楼门，是要做什么？”是自然的目的问法。; processing=0: 题干只询问一个目的，四个选项都是简短的行动描述。; context=0: “亚比米勒来到楼门”提供了有用的事件定位。; leakage=0: 来到楼门这一背景没有说明他要采取什么行动。

**target_preserving_comparison, run 1: KEEP**
The item directly and unambiguously asks about the intended action.
naturalness=0: “来到楼门，是要做什么” naturally asks about the purpose of his approach.; processing=0: The four choices are short actions with parallel “去” phrasing.; context=0: Naming “亚比米勒” and “楼门” distinguishes this moment from the earlier attack on the city.; leakage=0: The approach to the entrance is an event anchor and does not state the intended burning.

**target_preserving_comparison, run 2: KEEP**
事件定位有用，整体表达直接，无需改写。
naturalness=0: “来到楼门，是要做什么？”是自然的目的问法，选项也能顺畅承接。; processing=0: 题干只有人物、地点和目的询问，四个选项均为简短动作。; context=0: “来到楼门”提供了区分攻城与烧楼事件的有用定位。; leakage=0: 说明来到楼门，并未透露他准备在那里做什么。

**independent_dimensions, run 1: KEEP**
The question is direct, sufficiently anchored, and does not disclose the purpose it asks about.
naturalness=0: “来到楼门，是要做什么” and the action choices are idiomatic.; processing=0: The respondent identifies one person's purpose and compares four short, distinct actions.; context=0: “亚比米勒来到楼门” provides the necessary person and event anchor.; leakage=0: Coming to the tower entrance does not itself state the intended action.

**independent_dimensions, run 2: KEEP**
问法直接，事件锚点适量，没有明显的可避免负担。负担判断仍需受访者验证。
naturalness=0: “来到楼门，是要做什么？”是自然的目的问法。; processing=0: 题干只要求理解一次行动及其目的；四个选项都是简短动作。; context=0: “亚比米勒来到楼门”提供了必要且足够的事件定位。; leakage=0: 到达楼门并未说明其目的是“点火烧楼”。

## hard:t1_judg9:8e0b:mcq

橄榄树为什么不肯去作树木的王？

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
The main 为什么 question contains the straightforward complement “去作树木的王.” The deepest option modifier is “荣耀神和人的” modifying “油”; “它” clearly refers to 橄榄树. No unresolved referents or burdensome nesting.


**previous_wording_gate, run 2: KEEP**
主句直接询问“不肯去作树木的王”的原因，没有嵌套视角或未明指代。选项C的“那荣耀神和人的”是一层修饰“油”的结构，各选项均为独立原因陈述，无重叠列表解码负担。


**whole_item_rubric, run 1: KEEP**
The question and choices impose only ordinary reading and comparison demands.
naturalness=1: The question is natural; “那荣耀神和人的油” is slightly formal but understandable.; processing=1: Option C leaves the condition ‘if it became king’ implicit, but “不肯去作树木的王” makes that connection manageable.; context=0: “橄榄树” and “作树木的王” clearly identify the relevant refusal.; leakage=0: The question names the refusal without supplying its reason; the choices do not independently leak the answer.

**whole_item_rubric, run 2: KEEP**
题干直接，选项虽有少量经文式措辞，但未造成明显理解障碍。
naturalness=1: 题干自然；选项中的“那荣耀神和人的油”略带经文式表达，但意思仍清楚。; processing=1: 需比较拒绝作王的不同理由；“离开……油”的含义属于所测寓言内容，而非额外结构负担。; context=0: 明确指出橄榄树拒绝作王的事件，足以定位其回答。; leakage=0: 题干说明拒绝作王，但没有透露拒绝的原因。

**target_preserving_comparison, run 1: KEEP**
The item directly tests the reason for refusal without substantial avoidable burden.
naturalness=1: “那荣耀神和人的油” is somewhat formal, but the question and choices remain understandable Chinese.; processing=1: Readers must compare four short reasons and understand “荣耀神和人的” as modifying “油”; this is manageable and relevant to the target.; context=0: “橄榄树” and “作树木的王” clearly locate the refusal in the supplied passage.; leakage=0: The question states the refusal, not its reason; the answer's presence among the choices is not leakage.

**target_preserving_comparison, run 2: KEEP**
问题直接询问目标原因，选项虽需比较，但没有实质性的可避免负担。
naturalness=0: “为什么不肯去作树木的王”问法自然，选项也能直接衔接问题。; processing=1: 需比较四种原因，并理解“那荣耀神和人的油”的修饰关系；这是所问理由的一部分，没有明显多余的结构负担。; context=0: 橄榄树拒绝作王这一事件已明确，无须补充其他树木的经历。; leakage=0: 题干只说明拒绝作王，没有说明拒绝的原因。

**independent_dimensions, run 1: KEEP**
The minor stiffness does not prevent ordinary readers from understanding the question or comparing the reasons.
naturalness=1: “离开那荣耀神和人的油” is somewhat stiff, but the question “为什么不肯去作树木的王” is natural and understandable.; processing=1: The respondent compares four short reasons; “荣耀神和人的” adds a manageable modifier to “油.”; context=0: “橄榄树” and “不肯去作树木的王” clearly locate the refusal in the supplied passage.; leakage=0: The question names the refusal without stating its reason; the answer appears only among the choices.

**independent_dimensions, run 2: KEEP**
所问原因明确，选项虽略有经文式措辞，整体仍容易理解。
naturalness=1: 题干自然；选项C的“离开那荣耀神和人的油”略带经文式表达，但可以理解。; processing=1: 需要比较拒绝作王的理由与树木随后采取的行动；选项D的“我们”略有视角转换，但未形成实质性解码负担。; context=0: “橄榄树……不肯去作树木的王”足以定位寓言中的这次拒绝。; leakage=0: 题干只指出拒绝作王，没有给出拒绝的原因。

## hard:t1_2sam21:761c:mcq

在迦特的这四个拉法的后裔，被谁杀死了？

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
A simple passive question, “被谁杀死了,” with the locative modifier “在迦特的” attached to “这四个拉法的后裔.” “这四个” refers clearly to the group mentioned in the passage; the options require no nested decoding.


**previous_wording_gate, run 2: KEEP**
主干是“这四个拉法的后裔，被谁杀死了”，只有“在迦特的”这一地点定语，没有嵌套从句。“这四个”的指代可由上下文确定，选项简短清楚。


**whole_item_rubric, run 1: KEEP**
The identifying phrase is relevant, and the passive question presents no substantial avoidable burden.
naturalness=0: “在迦特的这四个拉法的后裔，被谁杀死了？” is understandable, natural Chinese despite the optional pause marked by the comma.; processing=1: The reader tracks one modified group, “在迦特的这四个拉法的后裔,” and selects its killers from short choices.; context=0: “这四个拉法的后裔” directly matches the group summarized in verse 22.; leakage=0: The stem identifies those killed without naming their killers; the answer's presence among choices is not leakage.

**whole_item_rubric, run 2: KEEP**
The group description and passive question are natural and impose no substantial avoidable load.
naturalness=0: “被谁杀死了” is a natural Chinese question; the comma marks a readable pause.; processing=1: “在迦特的这四个拉法的后裔” identifies the group, and the choices are short names or a short participant phrase.; context=0: “这四个拉法的后裔” has a clear referent in the passage's concluding statement.; leakage=0: The stem identifies those killed without naming their killers; the answer's presence among choices is not leakage.

**target_preserving_comparison, run 1: KEEP**
The group description is useful for preserving the collective answer scope, not unnecessary modifier load.
naturalness=0: “被谁杀死了” naturally asks for the agents of the killing.; processing=1: “在迦特的这四个拉法的后裔” identifies a group using manageable location and ancestry information; the choices are short names or groups.; context=0: “这四个” matches the passage's collective summary and distinguishes the question from the killing of the single man in the preceding verse.; leakage=0: The question identifies those killed but does not name their killers outside the choices.

**target_preserving_comparison, run 2: KEEP**
The group description and passive question preserve the intended scope without substantial avoidable burden.
naturalness=0: “被谁杀死了” is a natural way to ask for the killers; the comma marks a comprehensible topic pause.; processing=1: “在迦特的这四个拉法的后裔” identifies the group, and the four short choices are easy to compare.; context=0: “这四个拉法的后裔” clearly refers to the group summarized in verse 22.; leakage=0: The stem does not name the killers; “大卫和他的仆人” appears only as an answer choice.

**independent_dimensions, run 1: KEEP**
The descriptive anchor and passive question are manageable and directly serve the intended identification.
naturalness=0: “在迦特的这四个拉法的后裔，被谁杀死了？” is a natural, understandable identity question.; processing=1: The respondent tracks the group described by “这四个拉法的后裔” and selects its killers from short choices; this identification is necessary to the target.; context=0: “在迦特” and “这四个拉法的后裔” locate the passage's concluding group summary.; leakage=0: The stem identifies those killed but does not name their killers.

**independent_dimensions, run 2: KEEP**
The group description and passive wording are clear and necessary to identify the target event.
naturalness=0: “在迦特的这四个拉法的后裔，被谁杀死了？” is natural Chinese; the pause before “被谁” is acceptable.; processing=1: “在迦特的这四个拉法的后裔” identifies the group, and “被谁杀死” asks for the killers. The short choices are readily compared.; context=0: “这四个拉法的后裔” directly anchors the question to the passage's concluding statement.; leakage=0: The stem identifies those killed but does not name their killers; the answer's presence among the choices is not leakage.

## gold:t1_2kgs6_7:lxi8:open

Why did Arameans think Israel hired Hittites and Egyptians?

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
The main why-question contains one reported-belief complement, “think Israel hired Hittites and Egyptians.” This is ordinary single-viewpoint embedding, with no unresolved referent.


**previous_wording_gate, run 2: REWRITE**
The main causal question contains one reported-belief clause, “Israel hired Hittites and Egyptians”; no referent is unresolved. However, “Why did Arameans” omits the required determiner before “Arameans,” making the wording unnatural.


**whole_item_rubric, run 1: KEEP**
Minor grammatical clipping does not impede understanding of the intended causal question.
naturalness=1: “Why did Arameans” is slightly clipped without “the,” but the question remains clear.; processing=1: The reader must distinguish the Arameans' belief from its cause; this is integral to the target and expressed in one manageable clause.; context=0: The named groups and the belief about hiring troops locate the relevant event.; leakage=0: The question states the belief being explained, not the sounds that prompted it.

**whole_item_rubric, run 2: KEEP**
The causal question is accessible despite minor article omissions.
naturalness=1: “Arameans” and “Hittites and Egyptians” would read more naturally with articles here.; processing=1: Readers must distinguish the Arameans' belief from its cause, but “Why did … think” expresses this directly.; context=0: The named groups and the belief about hired forces identify the relevant episode.; leakage=0: The question supplies the belief being explained, not the sounds that caused it.

**target_preserving_comparison, run 1: KEEP**
The missing article is minor; the causal question is otherwise clear, with no meaningful burden reduction needed.
naturalness=1: “Why did Arameans” is slightly clipped; “the Arameans” would be more idiomatic here.; processing=1: The reader must distinguish the Arameans’ belief from the evidence prompting it, but that relationship is the target itself.; context=0: The belief that Israel hired Hittites and Egyptians uniquely anchors the relevant episode.; leakage=0: The question states the belief being explained, not the sounds that prompted it.

**target_preserving_comparison, run 2: KEEP**
The causal question is accessible, with only minor article stiffness and no substantial avoidable burden.
naturalness=1: “Why did Arameans” is slightly stiff without “the,” but the question remains readily understandable.; processing=1: The reader tracks the Arameans' belief about Israel hiring two groups; these roles are necessary to the target.; context=0: “Israel hired Hittites and Egyptians” clearly anchors the relevant episode.; leakage=0: The question states the belief being explained, not the sounds that prompted it.

**independent_dimensions, run 1: KEEP**
The slight article omission does not obstruct an otherwise clear causal question.
naturalness=1: “Why did Arameans” is slightly clipped without “the,” but the question remains readily understandable.; processing=1: The respondent must distinguish the Arameans’ belief from the evidence prompting it; this is necessary to the causal target.; context=0: The belief that Israel hired Hittites and Egyptians uniquely anchors the incident.; leakage=0: Naming the belief does not reveal the sounds that prompted it.

**independent_dimensions, run 2: KEEP**
Minor article omissions do not substantially impede this direct causal question.
naturalness=1: “Arameans” and “Hittites and Egyptians” sound slightly clipped without articles, but the question is readily understood.; processing=1: Respondents connect the Arameans' belief to its cause; that relationship is necessary to the target.; context=0: “Think Israel hired Hittites and Egyptians” uniquely identifies the relevant event.; leakage=0: The question names their belief without supplying the sounds that caused it.

## gold:t1_judg9:iw06:open

What is Jotham's curse?

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
A single copular question with the possessive “Jotham's curse,” without embedded clauses. The passage makes the curse identifiable; no unresolved referent.


**previous_wording_gate, run 2: KEEP**
A single copular question asks for the content of “Jotham's curse,” with only a possessive modifier and no embedded clauses. The passage supplies a clear referent for the curse; there is no unresolved participant reference.


**whole_item_rubric, run 1: KEEP**
The question clearly requests the curse's content; the complexity of that content is not added wording burden.
naturalness=0: “What is Jotham's curse?” is idiomatic and direct.; processing=0: The question contains a single request with no extra framing to decode.; context=0: “Jotham's curse” identifies the speech whose fulfillment is explicitly named at the end of the passage.; leakage=0: The question names the curse but does not state its content.

**whole_item_rubric, run 2: KEEP**
The complexity lies in the intended passage meaning, not in avoidable question wording.
naturalness=0: “What is Jotham’s curse?” is an idiomatic question.; processing=0: The wording asks directly for the content of one named curse.; context=0: The passage explicitly refers to “The curse of Jotham,” making the question’s reference identifiable.; leakage=0: The question supplies none of the curse’s content.

**target_preserving_comparison, run 1: KEEP**
The passage supplies a clear referent, and expanding the question is not needed to make its request accessible.
naturalness=0: “What is Jotham's curse?” is idiomatic and direct.; processing=0: The question contains one straightforward request; interpreting the curse belongs to the target rather than avoidable wording.; context=0: “Jotham's curse” identifies the pronouncement explicitly recalled as his curse at the passage's conclusion.; leakage=0: The question names the curse without stating its content.

**target_preserving_comparison, run 2: KEEP**
The complexity belongs to the curse being tested, not to the wording of the question.
naturalness=0: “What is Jotham's curse?” is idiomatic and direct.; processing=0: The question has no embedded roles, conditions, or competing references to unpack.; context=0: The passage identifies Jotham's curse and later explicitly refers back to it.; leakage=0: The question names the curse without supplying its content.

**independent_dimensions, run 1: KEEP**
The question supplies a sufficient anchor and leaves the curse's content for the respondent to explain.
naturalness=0: “What is Jotham's curse?” is idiomatic and direct.; processing=0: The question asks for the content of one named person's curse without adding structural complexity.; context=0: “Jotham's curse” identifies the pronouncement that the passage later explicitly calls his curse.; leakage=0: Naming the curse does not reveal what Jotham wished to happen.

**independent_dimensions, run 2: KEEP**
The target may involve a reciprocal curse, but the question adds no unnecessary complexity.
naturalness=0: “What is Jotham’s curse?” is a natural, direct question.; processing=0: The wording asks for one identifiable pronouncement without adding structural burden.; context=0: The passage presents Jotham’s curse and explicitly refers back to it at the end, so no further anchor is needed.; leakage=0: Calling the pronouncement a “curse” does not disclose its content.

## gold:t1_2sam21:kjsg:open

How does Abishai rescue David?

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
A single direct how-question, “How does Abishai rescue David?” Both participants are named; there are no embedded clauses or unresolved referents.


**previous_wording_gate, run 2: KEEP**
A single main interrogative asks how Abishai rescues David, without subordinate clauses or modifiers requiring additional tracking. Both named participants are clear, with no unresolved referent.


**whole_item_rubric, run 1: KEEP**
The event anchor is sufficient, and the requested action remains unstated.
naturalness=0: “How does Abishai rescue David?” is a natural narrative-comprehension question.; processing=0: The question names both participants and asks directly for the rescuing action.; context=0: Abishai rescuing David identifies a distinct event in the passage.; leakage=0: Stating that Abishai rescues David does not reveal how he does so.

**whole_item_rubric, run 2: KEEP**
This is a direct, accessible question about the rescue action.
naturalness=0: “How does Abishai rescue David?” is natural narrative-question wording.; processing=0: The question has clear participant roles and asks about one action.; context=0: Naming Abishai and David sufficiently locates the rescue.; leakage=0: Mentioning the rescue does not reveal how it was accomplished.

**target_preserving_comparison, run 1: KEEP**
The question directly requests the means of rescue without unnecessary setup or reference burden.
naturalness=0: “How does Abishai rescue David?” is direct and idiomatic.; processing=0: The reader identifies a single action linking the named rescuer and the person rescued.; context=0: “Abishai” and “David” uniquely anchor the rescue episode in the passage.; leakage=0: Stating that Abishai rescues David does not disclose how he does so.

**target_preserving_comparison, run 2: KEEP**
The how-question directly tests the intended action and introduces no unnecessary complexity.
naturalness=0: “How does Abishai rescue David?” is a natural narrative-present question.; processing=0: The question clearly asks how one named person rescued another.; context=0: Abishai and David identify the rescue event without additional setup.; leakage=0: Mentioning the rescue anchors the event but does not state how it happened.

**independent_dimensions, run 1: KEEP**
The concise question directly tests the rescue action without avoidable burden.
naturalness=0: “How does Abishai rescue David?” is a natural narrative-present question.; processing=0: The respondent identifies the action by which Abishai intervened; no extra reference tracking is imposed.; context=0: The named rescuer and David uniquely identify the rescue event.; leakage=0: Saying that Abishai rescues David anchors the event without revealing how he does so.

**independent_dimensions, run 2: KEEP**
The how-question directly tests the intended action without avoidable burden.
naturalness=0: “How does Abishai rescue David?” is natural narrative-question wording.; processing=0: The question directly asks for Abishai’s rescuing action without additional role or reference tracking.; context=0: Abishai’s rescue of David uniquely identifies the incident.; leakage=0: Naming the rescue does not supply how he accomplished it.

## gold:t1_acts23:xj40:open

How did captain respond to the plan?

Group: fresh_corpus

**previous_wording_gate, run 1: REWRITE**
The structure is a simple main-clause manner question, with “the plan” referring to the plot against Paul and “captain” identifiable as the commander. However, “How did captain respond” unnaturally omits a determiner before the singular role noun “captain,” requiring grammatical repair.


**previous_wording_gate, run 2: REWRITE**
A single main question with no embedded clause; “captain” and “the plan” are identifiable in context. However, “How did captain respond” unnaturally omits a determiner before “captain,” requiring grammatical repair.


**whole_item_rubric, run 1: KEEP**
The wording is mildly clipped and the event reference could be more specific, but neither creates substantial burden in context.
naturalness=1: “How did captain respond” omits the expected article before “captain,” producing minor stiffness.; processing=1: The reader must connect “the plan” to the murder plot, but the question itself has a simple structure.; context=1: “The plan” is less precise than naming the plot against Paul, though that prominent plot makes the reference recoverable.; leakage=0: The question does not disclose the protective orders.

**whole_item_rubric, run 2: KEEP**
Minor article omission and general reference do not create substantial comprehension burden.
naturalness=1: “How did captain respond” omits the article before “captain,” but remains understandable.; processing=0: A short, direct question about one person's response.; context=1: “The plan” is somewhat general, but the passage makes the plot against Paul a readily available referent.; leakage=0: The question does not state the commander's response.

**target_preserving_comparison, run 1: REWRITE**
Explicitly identifying the plot preserves the intended response target while removing avoidable uncertainty about the event.
naturalness=1: “How did captain respond” is clipped because “captain” lacks an article.; processing=2: “The plan” requires the reader to select a referent among the assassination plot, the proposed request to the commander, and the later transport arrangements. Naming the assassination plot removes this avoidable resolution step.; context=2: Insufficient disambiguation: “the plan” does not identify which plan prompted the response, although the intended event can be named directly.; leakage=0: The question does not state the commander’s protective response.
Diagnostic alternative: How did the commander respond when he learned of the plot to kill Paul? (preservation: preserved)

**target_preserving_comparison, run 2: REWRITE**
Specifying the murder plot removes avoidable event ambiguity while preserving the question about the commander's response.
naturalness=1: “How did captain” is missing the ordinary article before “captain.”; processing=1: The sentence is short, but the reader must resolve the unspecified reference “the plan.”; context=2: Missing disambiguation: the passage contains the murder plot, the proposed hearing, and transfer arrangements. Naming the plot to kill Paul identifies the intended event.; leakage=0: The question does not supply the commander's response.
Diagnostic alternative: How did the commander respond when he learned of the plot to kill Paul? (preservation: preserved)

**independent_dimensions, run 1: KEEP**
Minor clipped wording and a general reference remain resolvable from the passage without substantial repair.
naturalness=1: “How did captain respond” sounds slightly clipped because “captain” lacks an article.; processing=1: The respondent must connect “the plan” with the murder plot and then identify the commander’s response; the passage supports that connection.; context=1: “The plan” is less explicit than naming the murder plot, but that plot is the passage’s prominent plan reported to the commander.; leakage=0: The question gives no information about the commander’s protective orders.

**independent_dimensions, run 2: REWRITE**
The event needs a clearer anchor so respondents know which plan prompted the response.
naturalness=1: “How did captain” is slightly unnatural without “the” before “captain.”; processing=1: The short question is easy to parse, but respondents must identify the captain and resolve “the plan.”; context=2: Insufficient event anchoring: “the plan” does not specify the murder plot in a passage that also describes requests, warnings, and protective arrangements.; leakage=0: The question does not state how the captain responded.

## gold:t1_judg17_18:ramy:open

Why can't Laish be rescued?

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
A single why-question with the simple passive “be rescued”; no embedded clause. “Laish” is explicit, with no unresolved referent.


**previous_wording_gate, run 2: KEEP**
A single causal question uses the simple modal passive “can't Laish be rescued.” There are no embedded clauses, and “Laish” clearly identifies the place being discussed.


**whole_item_rubric, run 1: KEEP**
The wording makes the intended causal question accessible without avoidable burden.
naturalness=0: “Why can't Laish be rescued?” is a direct, idiomatic question.; processing=0: The short question asks for one causal explanation without added modifiers or competing references.; context=0: “Laish” identifies the city, and the passage supplies the attack and reasons no one rescued it.; leakage=0: The question does not supply either reason for the lack of rescue.

**whole_item_rubric, run 2: KEEP**
The question accessibly asks for the passage's explanation of why rescue was unavailable.
naturalness=0: “Why can't Laish be rescued?” is a direct, understandable question.; processing=0: The short passive question has no layered modifiers or difficult role tracking.; context=0: Laish and the reference to rescue identify the attack described in the passage.; leakage=0: The question states the lack of rescue, not the reasons being tested.

**target_preserving_comparison, run 1: KEEP**
The wording directly tests the intended causal relation without meaningful avoidable burden.
naturalness=0: “Why can't Laish be rescued?” is a direct, idiomatic question.; processing=0: The reader needs only to identify the reason for the lack of rescue; the passive adds no substantial load.; context=0: “Laish” and “rescued” identify the attack whose lack of outside help the passage explains.; leakage=0: The question does not supply either distance from Sidon or lack of allies.

**target_preserving_comparison, run 2: KEEP**
The passive wording is clear, and no additional framing is needed to locate the intended event.
naturalness=0: “Why can't Laish be rescued?” is a natural question about the city's situation.; processing=0: The question asks directly for the reason rescue was unavailable.; context=0: Laish and its inability to obtain rescue identify the attack described in the passage.; leakage=0: The lack of rescue is the premise, not the requested explanation about distance and lack of allies.

**independent_dimensions, run 1: KEEP**
The wording directly tests the intended causal explanation with only minor tense stiffness.
naturalness=1: “Why can't Laish be rescued?” is understandable, though the present tense is slightly awkward for this past event.; processing=0: The respondent identifies Laish and retrieves the reasons rescue was unavailable; the passive adds no substantial load.; context=0: “Laish” and “rescued” sufficiently identify the city's destruction in the passage.; leakage=0: The question does not supply either reason rescue was unavailable.

**independent_dimensions, run 2: KEEP**
The question provides sufficient context and directly asks for the intended causal explanation.
naturalness=0: “Why can't Laish be rescued?” is a natural question about the city's lack of help.; processing=0: The short question asks for a reason; the passive does not create unclear participant roles.; context=0: Naming Laish and asking about rescue identifies the attack for which the passage explicitly explains the absence of help.; leakage=0: The question states the lack of rescue, not the reasons being tested.

## gold:t1_1kgs13:nntp:open

What does the old prophet say to the man of God?

Group: fresh_corpus

**previous_wording_gate, run 1: KEEP**
A single main question with “the old prophet” as speaker and “the man of God” as addressee; there are no embedded clauses or unresolved participant referents.


**previous_wording_gate, run 2: KEEP**
A single main question asks what the old prophet says, with no embedded clause. “The old prophet” and “the man of God” identify clear participants; no pronoun referent is unresolved.


**whole_item_rubric, run 1: REWRITE**
The wording needs an event anchor to distinguish the intended speech from the other exchanges.
naturalness=0: “What does the old prophet say” is idiomatic and direct.; processing=1: The sentence is readily parsed, but the reader must locate the intended exchange.; context=2: Insufficient anchoring: the old prophet speaks to the man of God several times, including the invitation, the angel claim, and the judgment. Nothing identifies the invitation.; leakage=0: The question supplies no content from the intended invitation.

**whole_item_rubric, run 2: REWRITE**
The wording needs an event anchor to distinguish the intended invitation from the old prophet's other statements.
naturalness=0: The question is idiomatic and direct.; processing=0: The speaker, listener, and requested speech are easy to parse.; context=2: Missing event disambiguation: the old prophet speaks to the man of God several times, including an invitation, a false claim, and a judgment. Nothing identifies the invitation.; leakage=0: The question supplies none of the invitation's content.

**target_preserving_comparison, run 1: REWRITE**
The alternative locates the intended invitation without giving its content; the original leaves several exchanges available.
naturalness=0: “What does the old prophet say” is idiomatic and direct.; processing=0: The question has a simple structure and clearly names both participants.; context=2: Missing event anchoring: the old prophet speaks to the man of God several times, including asking his identity, inviting him home, lying about an angel, and announcing judgment. The question does not identify the intended exchange.; leakage=0: The question does not supply the invitation.
Diagnostic alternative: When the old prophet finds the man of God sitting under an oak tree, what does he invite him to do? (preservation: preserved)

**target_preserving_comparison, run 2: REWRITE**
Identifying the speech as an invitation removes the need to guess which exchange is intended while preserving the expected answer.
naturalness=0: “What does the old prophet say” is idiomatic and direct.; processing=0: The sentence itself is readily parsed, with clearly named participants.; context=2: Missing disambiguation: the old prophet speaks to the man of God several times, including asking his identity, inviting him home, and delivering judgment. The question does not identify the intended speech.; leakage=0: The question supplies none of the invitation's content.
Diagnostic alternative: What did the old prophet invite the man of God to do? (preservation: preserved)

**independent_dimensions, run 1: REWRITE**
The wording is easy to read but needs an event anchor to distinguish the intended speech from the old prophet's other statements.
naturalness=0: “What does the old prophet say” is idiomatic and direct.; processing=0: The question has straightforward speaker and listener roles, without complex modifiers.; context=2: Missing disambiguation: the old prophet speaks to the man of God several times, including an identity question, an invitation, a false claim, and a judgment. Nothing locates the intended invitation.; leakage=0: The question does not supply the content of the invitation.

**independent_dimensions, run 2: REWRITE**
The intended exchange needs an anchor so respondents can distinguish it from the prophet's other statements.
naturalness=0: “What does the old prophet say” is natural, direct English.; processing=0: The question has straightforward speaker and addressee roles, with no complex wording to decode.; context=2: Missing disambiguation: the old prophet speaks to the man of God several times, including an invitation, a claim about an angel, and a judgment. No anchor identifies the invitation.; leakage=0: The question supplies none of the invitation's content.

