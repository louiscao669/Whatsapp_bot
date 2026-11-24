"""Editorial audit of the latest 12 responses; does not alter study records."""
from collections import Counter
from hashlib import sha256
from html import escape as esc
import json
from pathlib import Path

HOME=Path(__file__).resolve().parent
data=json.loads((HOME/'results.json').read_text())
notes={
1:dict(impact='retained',support='supported',critical_deletions=[],
    finding='The phrase identifying Zechariah as the person teaching Uzziah to fear God remains explicit. The deleted place, father’s name and separate statement about seeking God do not remove this target. D is supported.'),
2:dict(impact='partial',support='core_answer_retained_premise_lost',critical_deletions=['，埋伏在田间'],
    finding='The report that Shechem’s people went into the fields remains verbatim, so C is recoverable. However, the statement that Abimelech set an ambush has been deleted. The question supplies an action no longer stated in the displayed passage. The reported news survives; the complete news-to-ambush proposition does not remain explicit.'),
3:dict(impact='partial',support='core_answer_retained_identity_lost',critical_deletions=['橄榄'],
    finding='The statement that the oil honors God and people is intact, supporting C. The tree is now only called 树 because 橄榄 was deleted. The question supplies its specific identity; oil production provides a contextual clue. This is retained answer content with a weakened named-actor link, not complete loss of the answer.'),
4:dict(impact='partial',support='abstention_requires_adjudication',critical_deletions=['三十万七千五百名训练有素的战士，'],
    finding='The troop count and training description were removed. Crucially, the commander relationship remains: 这些宗族首领共有二千六百人。……他们统领着一支强大军队。 C is still recoverable if the numerical description supplied by the question is accepted as identifying that army. E is understandable under a stricter rule requiring the displayed passage to establish the 307,500-person qualifier. Do not classify this as total removal of commander evidence or silently replace the key with E; it needs an explicit scoring convention or adjudication.'),
5:dict(impact='removed',support='supported_abstention',critical_deletions=['对荆棘','作我们的王'],
    finding='The passage still names the trees as speakers, but both the thorn bush as addressee and their invitation to become king were deleted. The surviving 请来 does not establish the event asked about. C can be guessed by importing the question’s premise into the remaining speech, but the complete thorn-bush invitation is unsupported. E is a defensible passage-only response despite being a clean-key mismatch.'),
6:dict(impact='removed',support='unsupported_choice',critical_deletions=['在山地和肥沃的田野','在丘陵和平原'],
    finding='The exact farm-worker location in C was deleted. A, hills and plains, describes the livestock location in the clean passage, not the location of the farmers and vineyard workers; it too is absent from the displayed version. The wilderness refers to construction, not the workers. The shown text does not identify where he employed the workers, so E is the most defensible response. A is unsupported. We discussed this item’s clean passage in chat during the run, so this observation is assisted rather than an unaided pilot response.'),
7:dict(impact='partial',support='core_answer_recoverable_order_weakened',critical_deletions=['，跟在他后面进去'],
    finding='Uzziah is still explicitly described as entering the temple. The comparison establishing that Azariah and the eighty priests entered behind him was deleted. B remains the most readily recoverable answer from the surviving sequence and the only explicitly narrated entrance, but the direct comparative-order evidence has been weakened.'),
8:dict(impact='retained',support='supported',critical_deletions=[],
    finding='Jonathan and his descendants are still named as priests, followed immediately by 直到那地的居民被掳的日子. The endpoint in D remains explicit; omitted ancestry and idol details do not change it.'),
9:dict(impact='partial',support='core_answer_retained_actor_event_place_lost',critical_deletions=['约坦逃到比珥，'],
    finding='Fear of Abimelech remains the explicit reason, supporting the core content of C. The deletion removes Jotham’s name, the escape and Beer. His and there in the remaining sentence lack their original introduction, and the question supplies those missing facts. A correct answer does not show that the full original causal episode remains supported by the passage alone.'),
10:dict(impact='partial',support='core_answer_retained_audience_lost',critical_deletions=['示剑的首领们啊，','请听我说，'],
    finding='Jotham’s wish 愿上帝也听你们 remains. The address identifying you as Shechem’s leaders, together with the request that they hear him, was deleted. A is recoverable by using the audience supplied in the question, but its full named-audience claim is not independently established by the displayed wording.'),
11:dict(impact='partial',support='causal_answer_inferable_outcome_removed',critical_deletions=['烧死了示剑楼里所有的人，'],
    finding='The passage retains the people entering the inner room and the later fire beside it. It deletes the explicit statement that the fire killed them and the detail that it was over those inside. Given the question’s assertion that they died, fire is a strong and plausible causal inference supporting D. This is not fully explicit death-cause evidence; the question supplies the outcome that the omission removed.'),
12:dict(impact='partial',support='audience_retained_sender_and_relay_removed',critical_deletions=['耶路巴力的儿子亚比米勒来到示剑，','请你们问示剑所有的首领：'],
    finding='The maternal brothers and maternal clan remain the immediate audience, making B recoverable. The speaker’s name and the instruction to relay the message to Shechem’s leaders were deleted. The question supplies both the identity and relay task; the complete sender-to-intermediaries-to-leaders relationship is no longer explicit.'),
}
items=[]
for r in data['answers']:
    assert r['status']=='submitted'
    note=notes[r['number']];deleted=' '.join(e['before'] for e in r['edits'])
    assert all(phrase in deleted for phrase in note['critical_deletions'])
    items.append(dict(**r,**note))
assert len(items)==12 and sum(r['clean_key_match'] for r in items)==9
assert [r['number'] for r in items if not r['clean_key_match']]==[4,5,6]
conditions=[]
for condition in ('omission15','omission30'):
    rs=[r for r in items if r['condition']==condition]
    conditions.append(dict(condition=condition,total=len(rs),clean_key_matches=sum(r['clean_key_match'] for r in rs),
        evidence=dict(Counter(r['impact'] for r in rs))))
review=dict(participant_id=data['participant_id'],review_type='Assistant editorial evidence audit; no additional independent model adjudication.',
    total=12,submitted=12,clean_key_matches=9,clean_key_accuracy=.75,conditions=conditions,
    evidence=dict(Counter(r['impact'] for r in items)),items=items,active_time_ms=sum(r['active_time_ms'] or 0 for r in items),
    scoring='Clean-key agreement is distinct from support in the displayed defective passage. Partial evidence does not automatically mean an item is unanswerable.',
    limitations=['Q4 requires a scoring convention about a numerical qualifier supplied only in the question; no replacement key was approved.',
        'Seven of the nine key matches retain answer content or clues while losing some premise, identity, order or outcome. These may remain answerable using the question’s supplied context.',
        'Q6’s clean passage was discussed in chat during this run. This is a diagnostic walkthrough, not a wholly unaided pilot.',
        'A single participant with different questions at each dose cannot establish a causal dose effect.',
        'No saved answers, grades, keys, passages or question eligibility were changed.'],
    source_sha256=sha256((HOME/'results.json').read_bytes()).hexdigest())
(HOME/'evidence_review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
labels={'retained':'Target evidence retained','partial':'Partial / question supplies missing context','removed':'Target event or answer detail removed'}
parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
 '<title>Latest 12-question omission test</title><style>body{font:17px/1.65 system-ui;max-width:1200px;margin:28px auto;padding:0 20px;color:#213b42}',
 'table{border-collapse:collapse;width:100%;margin:20px 0}td,th{padding:9px;border-bottom:1px solid #d4dfdf;text-align:left;vertical-align:top}',
 '.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.passage{background:#f0f5f4;padding:16px}.note{background:#fff3df;padding:15px;border-left:4px solid #b08039}',
 'details{margin:18px 0;border-top:1px solid #cbd8d6;padding-top:12px}summary{cursor:pointer;font-weight:600}[lang=zh]{font-size:18px;line-height:1.9}',
 '@media(max-width:800px){.grid{grid-template-columns:1fr}}</style><h1>Your latest 12-question test</h1>',
 '<p><b>All 12 responses saved. Clean-key agreement: 9/12 (75%).</b> Omission 15%: 5/6 (83.3%); omission 30%: 4/6 (66.7%).</p>',
 '<p class="note">Three mismatches: Q4 chose E where the count is missing but the commanders remain identifiable; Q5 chose E after the thorn-bush invitation was removed; Q6 chose A after the farming location was removed. Q4 is a borderline scoring case, Q5 is defensible abstention, and Q6’s A is unsupported. No single adjusted passage-based score is asserted.</p>',
 '<p>Two items retain clear target evidence; eight have partial evidence or missing question context; two lose the target event or answer detail. Partial does not mean unanswerable. Seven of the nine clean-key matches occur in that partial category.</p>',
 '<table><tr><th>#</th><th>Question</th><th>Dose</th><th>Your answer</th><th>Clean key</th><th>Evidence audit</th></tr>']
for r in items:
    selected=r['choices'][ord(r['raw_answer'])-65];key=r['choices'][ord(r['mcq_correct_choice'])-65]
    parts.append(f'<tr><td><a href="#q{r["number"]}">{r["number"]}</a></td><td lang="zh">'+esc(r['question_text'])+'</td><td>'+r['condition'].replace('omission','')+'%</td><td>'+esc(r['raw_answer']+'. '+selected)+'</td><td>'+esc(r['mcq_correct_choice']+'. '+key)+'</td><td>'+esc(labels[r['impact']])+'</td></tr>')
parts.append('</table><p>We supplied Q6’s clean passage in chat during the run. Treat these observations as diagnostic, and do not infer a dose effect from different questions and one familiar reader.</p>')
for r in items:
    parts.append(f'<details id="q{r["number"]}"'+(' open' if r['number'] in (4,5,6) else '')+f'><summary>{r["number"]}. '+esc(r['passage_reference'])+' · '+r['condition'].replace('omission','')+f'% omission · you {r["raw_answer"]}, clean key {r["mcq_correct_choice"]}</summary>')
    parts.append('<h2 lang="zh">'+esc(r['question_text'])+'</h2><ol type="A" lang="zh">')
    for i,text in enumerate(r['choices']):
        letter=chr(65+i);parts.append('<li>'+esc(text)+(' <b>← your answer</b>' if letter==r['raw_answer'] else '')+(' <b>[clean key]</b>' if letter==r['mcq_correct_choice'] else '')+'</li>')
    parts.append('</ol><p class="note">'+esc(r['finding'])+'</p><div class="grid">')
    for label,verses in [('Clean passage',r['clean_verses']),('Passage you saw',r['shown_verses'])]:
        parts.append('<div class="passage"><h3>'+label+'</h3>')
        for v,t in verses.items():parts.append('<p lang="zh">'+esc(v+'　'+t)+'</p>')
        parts.append('</div>')
    parts.append('</div><p>Actual omission: '+f'{r["actual_dose"]:.2f}%'+'.</p><details><summary>Exact deleted spans</summary><ul>')
    for e in r['edits']:parts.append('<li lang="zh">'+esc(e['verse'])+'　<del>'+esc(e['before'])+'</del></li>')
    parts.append('</ul></details></details>')
parts.append('<p>Read-only report. The local preview stores receipts without a grading worker; the clean-key score was calculated directly from those saved answers. No answer keys or response records were changed.</p></html>')
(HOME/'index.html').write_text(''.join(parts))
print(json.dumps({k:v for k,v in review.items() if k in ('submitted','clean_key_matches','total','conditions','evidence','active_time_ms')},ensure_ascii=False,indent=2))
