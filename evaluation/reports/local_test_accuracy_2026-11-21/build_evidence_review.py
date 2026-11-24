"""Assistant editorial audit of submitted choices; does not modify any study key."""
from collections import Counter
from hashlib import sha256
from html import escape as esc
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
source=HERE/'results.json'
archived=ROOT/'evaluation/runs/sol_low_dose_all66_2026-11-19/all_windows.json'
data=json.loads(source.read_text())
bank=json.loads(archived.read_text())
qa={w['id']:w['qa'] for w in bank['families']['omission']['windows']}

# Number: evidence status, support for the chosen response, displayed evidence, finding.
# "Supported" means the response is defensible from the displayed text. It does
# not assert that a fresh independent reviewer approved a unique replacement key.
notes={
1:('retained','supported','于是我们把我的儿子煮了吃了；王听见这妇人的话',
   'The speaking woman and her son remain identifiable. Removed clothing, wall, and ancestry details do not remove this answer.'),
2:('changed_or_lost','supported','因为从那时起，他们就已经在周围各民族中租到牧场',
   'E is defensible: the stated reason now concerns rented pasture. The original lack-of-inheritance explanation is no longer stated. Renting and inheritance are not logical opposites, so this is loss/replacement of the stated reason, not proof that A must be false in reality.'),
3:('excluded','excluded','百姓却在城门口把他踩死了',
   'Previously held officer question. Keep this response and the original displayed wording in the record, but exclude it from the 36-item interpretation. Its original clean passage had the same pronoun issue.'),
4:('changed_or_lost','supported','请求你明天把彼得赶出营房去；只等你答应',
   'E is defensible: the request is to expel Peter from the barracks, not to bring Paul to the council. None of A–D states the new request.'),
5:('retained','supported','侦察的人就回来向王报告。于是百姓出城，抢掠营地',
   'C remains supported by the explicit sequence. Earlier pursuit of the Aramean army also remains in the excerpt.'),
6:('context_or_partial','review','还有三名一直钻研医术的人，把自己的书带来，当众焚烧',
   'The burning action in D survives, but the stem asks about practitioners of magic whereas the text now describes practitioners of medicine. D can be recovered by matching the book-burning event; the full original subject–action proposition is damaged. Do not treat this match as proof that the complete question remains supported.'),
7:('context_or_partial','review','以利沙回答：“你必亲眼看见，却一点也吃不到。”',
   'The reply in C remains verbatim, but the sentence identifying the interlocutor as the officer was removed. The question supplies that identity. This is a recoverable reply with a missing role link, rather than a lost reply.'),
8:('changed_or_lost','unsupported','因为有一个利未人作了我的管家',
   'B says the Levite became his priest. The displayed reason consistently substitutes steward/housekeeper for priest. B earns the clean-key point but is unsupported by the displayed reason. E is the defensible unlisted-answer response.'),
9:('changed_or_lost','supported','那时，他的铜矛重三百舍客勒；击杀了那非利士人',
   'E is defensible: both the named adversary and the sentence naming Abishai as rescuer/killer were removed. The remaining pronouns and subjectless killing clause cannot identify Ishbi-Benob.'),
10:('retained','supported','第二天，步兵返回营房，让骑兵继续护送他',
    'D is directly supported. The substitutions elsewhere do not change who returned to the barracks.'),
11:('retained','supported','城里也安静了，因为亚他利雅已被刀杀死',
    'The explicit causal link supporting C survives. Removing the palace location does not change the reason asked for.'),
12:('changed_or_lost','supported','那十二个曾去攻打那城的人退出来，砸碎了',
    'E is defensible: five scouts entering and taking objects became twelve attackers coming out and smashing them. The original question event and its participant description no longer match. This also has a corrupted-premise issue.'),
13:('context_or_partial','review','那里一个人也没有；只有拴着的马和驴，帐篷也都完好无损',
    'The absence of people remains, but the explicit identification of the location as the Aramean camp was deleted. A is readily recoverable using the question and contextual tents/animals. Record the missing location link rather than claiming the whole answer proposition survived unchanged.'),
14:('retained','supported','保罗准备第二天离开，就向众人讲道，一直讲到半夜',
    'The original departure explanation in D remains. Changes to the meeting, room, and young man do not remove that explanation.'),
15:('changed_or_lost','supported','过了一些时候，亚兰王便哈达上来围攻撒马利亚',
    'The army-gathering step B was deleted. D is a defensible first event stated in the shortened account: beginning the siege. A adds leading an army, which the remaining text does not explicitly say. This is support for the chosen response, not independent validation of a new unique key.'),
16:('changed_or_lost','supported','不许你亵渎上帝，看看我们这次出行为何受阻',
    'E is defensible: the request to inquire of God was replaced by a prohibition against blasphemy. None of A–D gives that request.'),
17:('context_or_partial','review','等他们出城，我们就活捉他们，再进城去',
    'The planned next action in B survives. The introductory identification of the plan as the Arameans’ plan was deleted, leaving pronouns whose identity is supplied by the question. Core action is recoverable, context is weakened.'),
18:('changed_or_lost','unsupported','继续讲到日落，就离开了',
    'A says Paul continued until dawn. The displayed text says sunset. The action of continuing to speak remains, but the full option is false. This clean-key match does not demonstrate recovery from the text; no listed option states talking until sunset.'),
19:('changed_or_lost','unsupported','你们在安息日上值的人；三分之一要守在护卫后面的门',
    'The clause identifying the two groups going off duty was deleted. C is assigned to an on-duty third, not the requested off-duty groups. The temple location remains later, but its link to the off-duty groups is missing. C is unsupported; a strict passage-only reading cannot identify the requested groups’ assignment.'),
20:('changed_or_lost','supported','他对父亲说；我听见你为此发了咒诅；他父亲说',
    'E is defensible: father replaces mother, and father is absent from A–D. The altered custody/theft description also damages the stem’s theft premise.'),
21:('context_or_partial','review','现在，我们去报信吧',
    'A retains the action of reporting but adds the deleted destination, the palace. The excerpt also loses the lepers’ identification and explicit admission of wrongdoing. A is the closest available option, but the complete destination claim is unsupported. Hold this scoring judgment rather than automatically awarding A or E.'),
22:('changed_or_lost','unsupported','在便雅悯的基列耶琳扎营；绕过犹大平原，烧毁祭司的粮仓',
    'D names Benjamin’s hill country. The text only places a camp at Kiriath-jearim in Benjamin; it does not state Benjamin’s hill country or a journey to Micah’s house. The travelers also change from Danites to Judahites. Selecting D follows a changed place-name cue but does not answer the exact question as written.'),
23:('retained','supported','祭司把耶和华殿里大卫王的长矛和盾牌交给众百夫长',
    'D remains explicit. The omitted guard-position details do not affect the giver of the weapons.'),
24:('retained','supported','克劳狄·吕西亚致腓力斯总督阁下',
    'The signature still identifies B as the writer. First-person framing and the changed salutation do not remove that evidence.'),
25:('retained','supported','都死在大卫和他臣仆的手下',
    'D remains explicit. The omissions remove body details and an individual combat description, while retaining the summary answering the question.'),
26:('changed_or_lost','unsupported','要找一个可以耕种的庄园；绕过便雅悯山地米迦的家',
    'B claims he set out specifically to seek Micah. The displayed stated purpose is finding an estate to farm, and it says he bypassed Micah’s house. B is unsupported. E is defensible for the unlisted stated purpose; inferring a broader wish to settle from farming would require a separate scoring judgment.'),
27:('retained','unsupported','王派了一个使者先去；这个凶手派人来砍头',
    'The sender–messenger distinction supporting A remains: the person called murderer sends someone, and the preceding narrator identifies the king as sender. B selects the messenger. The reference is indirect even in the clean passage, so this response alone cannot establish that the deletions caused the confusion.'),
28:('context_or_partial','review','保罗的外甥；请带这个年轻人离开千夫长',
    'D’s identity survives, but the stem asks whom Paul ordered to be brought to the commander; the text now says to take him away. The final dialogue also makes the altered event internally awkward. D can be selected from identity matching despite a changed action premise. Review rather than force a full-text grade.'),
29:('changed_or_lost','supported','制伏了他们所有人。攻击如此猛烈',
    'E is defensible: the sentence saying they fled the house was deleted. The seven sons remain identifiable as victims, but being attacked does not establish that they ran out.'),
30:('changed_or_lost','unsupported','那地缺衣少食',
    'B says nothing was lacking, directly contradicted by shortage of clothing and food. Participant count and location also change. The broad statement about alliances may complicate choosing a replacement key, but it cannot support the selected B.'),
31:('retained','supported','凡跟随她的人，都用刀杀死；当亚他利雅来到马匹入口时',
    'D remains supported. Athaliah is still named, and the command targets her followers.'),
32:('retained','supported','他叫来两位百夫长，说：“预备二百名步兵',
    'D remains explicit. Changes to Paul’s escort destination do not change the recipients of the troop-preparation order.'),
33:('context_or_partial','review','当时，他们说；来吧，我们到亚兰人的营地去',
    'The decision in B survives, but the entire identification of the four men as lepers was deleted. The question supplies the missing participant identity, making the answer recoverable despite damaged context.'),
34:('changed_or_lost','supported','不要迟疑，去占领那城吧',
    'B is explicitly supported by the changed object, the city. The original key A referred to land. This clean-key mismatch is a faithful reading of the altered instruction.'),
35:('retained','supported','耶何耶大使耶和华与王和百姓立约，又使王与百姓立约',
    'The parties to the first covenant remain, so D is directly supported. Its purpose and later temple naming were omitted, not the requested participants.'),
36:('retained','supported','向千夫长提出请求；让他把保罗带到你们这里来',
    'A remains the officer requested to bring Paul. The wider plot changes, but this requested agent–action link survives.'),
37:('changed_or_lost','supported','甚至有人把接触过他的手帕和围裙拿到病人那里',
    'E is defensible: the entire healing-and-departing-spirits result was removed. No remaining sentence says what left the patients.'),
}

reviews=[]
for answer in data['answers']:
    number=answer['sequence_index']+1
    original=qa[answer['form_group_id']]
    assert (original['question'],original['choices'],original['correct'])==(answer['question_text'],answer['choices'],answer['clean_key'])
    impact,judgment,evidence,note=notes[number]
    assert evidence.replace('；','') or impact=='excluded'
    reviews.append(dict(**answer,number=number,original_clean_verses=original['verses'],
                        evidence_impact=impact,chosen_answer_support=judgment,
                        displayed_evidence=evidence,review_note=note))

included=[r for r in reviews if r['included']]
impact=Counter(r['evidence_impact'] for r in included)
support=Counter(r['chosen_answer_support'] for r in included)
assert impact=={'retained':13,'context_or_partial':7,'changed_or_lost':16},impact
assert support=={'supported':22,'unsupported':7,'review':7},support
assert all(r['chosen_answer_support']=='supported' for r in included if r['raw_answer']=='E')
missed=[r for r in included if r['raw_answer']!=r['clean_key']]
matched=[r for r in included if r['raw_answer']==r['clean_key']]
assert len(missed)==14 and sum(r['chosen_answer_support']=='supported' for r in missed)==10
assert len(matched)==22 and sum(r['chosen_answer_support']=='unsupported' for r in matched)==3
labels={'omission15':'Omission 15%','omission30':'Omission 30%',
        'mistranslation15':'Mistranslation 15%','mistranslation30':'Mistranslation 30%'}
conditions=[]
for key,label in labels.items():
    group=[r for r in included if r['condition']==key]
    conditions.append(dict(condition=key,label=label,n=len(group),
                           evidence=Counter(r['evidence_impact'] for r in group),
                           chosen_answer_support=Counter(r['chosen_answer_support'] for r in group)))
review=dict(review_type='Assistant editorial evidence audit; no additional model calls or independent adjudication.',
    scope='37 submitted responses, with the previously held question excluded from the 36-item summaries.',
    scoring_rule='Support for the chosen response in its displayed passage, under the user rule that E also covers unlisted answers.',
    counts=dict(evidence_impact=impact,chosen_answer_support=support),conditions=conditions,items=reviews,
    limitations=['Seven cases remain for adjudication because core answers survive but their subject/action context or an option detail is lost or changed.',
                 'No new production answer keys, question holds, grades, or passage rewrites were published.',
                 'Response correctness alone cannot identify use of memory, option elimination, inference, or prior discussion.',
                 'This was one diagnostic walkthrough with different questions assigned to different conditions; several items and clean passages were discussed in chat.',
                 'Original clean text was recovered from the pre-test bank, including the held officer item before its later clarification.'],
    input_sha256={str(source):sha256(source.read_bytes()).hexdigest(),str(archived):sha256(archived.read_bytes()).hexdigest()})
(HERE/'evidence_review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')

style='''body{font:17px/1.6 system-ui;max-width:1180px;margin:30px auto;padding:0 20px;color:#182c35}h1,h2{line-height:1.3}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{padding:9px;border-bottom:1px solid #ccd5db;text-align:left}details{padding:14px 0;border-bottom:1px solid #ccc}summary{cursor:pointer;font-weight:600}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}.passage{background:#f4f7f9;padding:16px;border-radius:8px}.note{border-left:4px solid #317080;padding:12px 18px;background:#f0f7f8}pre{white-space:pre-wrap;font:inherit}[lang=zh]{line-height:1.9}@media(max-width:750px){.pair{grid-template-columns:1fr}}'''
body='''<h1>What your answers reveal about the corruption</h1><p><b>The clean-key score is not a direct measure of how much answer evidence was damaged.</b> Some mismatches follow the changed text faithfully; some matches contradict the changed text.</p>
<p>36 included responses; the previously held officer question is shown separately below. This is an assistant editorial review, not an independent double-reviewed answer-key release.</p>
<div class="note"><b>Chosen-answer support:</b> 22 supported by the displayed text, 7 unsupported, and 7 requiring adjudication. These are not the same 22 answers as the clean-key matches. No single revised accuracy is asserted while seven cases remain unresolved.</div>
<ul><li>Of 14 clean-key mismatches: 8 E selections and 2 other A–D selections are defensible; 3 other selections lack support after target evidence was damaged; 1 selects the messenger although the sender–king evidence remains.</li>
<li>Of 22 clean-key matches: 12 have intact target evidence, 3 contradict changed answer facts, and 7 have a missing or changed premise/context or a partly unsupported option.</li></ul>
<h2>Did the corruption damage the information needed for the question?</h2><table><tr><th>Condition</th><th>Answer link retained</th><th>Context / partial support needs review</th><th>Original answer changed or unavailable</th></tr>'''
for row in conditions:
    c=row['evidence'];body+=f'<tr><td>{row["label"]}</td><td>{c["retained"]}</td><td>{c["context_or_partial"]}</td><td>{c["changed_or_lost"]}</td></tr>'
body+='''<tr><th>Total</th><th>13</th><th>7</th><th>16</th></tr></table>
<p>The 30% mistranslation questions in this rotation all had damaged target evidence. Its two clean-key matches both conflict with the displayed answer facts. This is descriptive of this particular question assignment, not an estimated causal effect of dose.</p>
<h2>Interpretation limits</h2><p>The clean-key score measures agreement with the intended source answer. A displayed-text judgment asks whether the reader follows the text they were actually given. An evidence audit asks whether that text still supports the original answer. These quantities can diverge.</p><p>We discussed several items and their clean passages during this walkthrough. Treat it as a diagnostic exercise, not an unaided pilot observation. The recorded choice cannot establish why it was selected.</p>
<h2>All 37 items</h2><p>Each entry preserves the actual displayed passage. The clean text comes from the pre-test bank, not the subsequently corrected release.</p>'''
for r in reviews:
    summary=f'{r["number"]}. {r["passage_reference"]} · {labels[r["condition"]]} · you {r["raw_answer"]}, clean key {r["clean_key"]} · {r["chosen_answer_support"]}'
    clean='\n\n'.join(k+' '+v for k,v in r['original_clean_verses'].items())
    choices=''.join(f'<li>{esc(choice)}'+(' <b>← your choice</b>' if chr(65+i)==r['raw_answer'] else '')+(' <b>[clean key]</b>' if chr(65+i)==r['clean_key'] else '')+'</li>' for i,choice in enumerate(r['choices']))
    body+=f'<details id="q{r["number"]}"><summary>{esc(summary)}</summary><h3 lang="zh">{esc(r["question_text"])}</h3><ol type="A" lang="zh">{choices}</ol><p class="note">{esc(r["review_note"])}</p><div class="pair"><div><h4>Original clean passage</h4><pre class="passage" lang="zh">{esc(clean)}</pre></div><div><h4>Passage you saw</h4><p class="passage" lang="zh">{esc(r["passage_text"] or "")}</p></div></div></details>'
page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Answer-evidence review · November 21</title><style>'+style+'</style>'+body+'</html>'
(HERE/'evidence_review.html').write_text(page)
print(json.dumps({'counts':review['counts'],'conditions':conditions,'report':str(HERE/'evidence_review.html')},ensure_ascii=False))
