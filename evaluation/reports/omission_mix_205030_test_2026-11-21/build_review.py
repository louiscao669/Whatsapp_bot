"""Read-only editorial evidence audit of the eight submitted preview answers."""
from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path

HOME=Path(__file__).resolve().parent
data=json.loads((HOME/'results.json').read_text())
notes={
1:dict(impact='retained',support='supported',
    surviving_evidence='于是神人恳求耶和华，王的手就恢复了',
    finding='The introductions identifying the speaker were deleted, but the person performing the requested prayer is still explicitly 神人. The restoration of the king’s hand also connects the request to the king. A remains supported.'),
2:dict(impact='retained',support='supported',
    surviving_evidence='不会吃饭喝水。因为耶和华的话这样吩咐我',
    finding='The refusal and its explicit divine-command explanation remain adjacent. The separate prohibition against drinking was deleted, and the route restriction was broadened by deletion, but neither removes the stated reason for the refusal. C remains supported.'),
3:dict(impact='weakened_ambiguous',support='ambiguous',
    surviving_evidence='神人吃喝完毕，那位带他回来的老先知就备好驴。他上路后',
    critical_deletions=['为他','到老先知所住的城里'],
    finding='The clean text already uses 他 rather than naming the traveler in 13:24. Deleting 为他 from 老先知就为他备好驴 removes a useful link between the donkey and the man of God. The old prophet is now the nearest explicit subject before 他上路后, so B is a plausible reading of the shortened text. Deleting the report’s destination also removes context mentioning the old prophet’s home. The original key C is no longer securely distinguished from B. This is increased reference ambiguity, not proof that B is definitely the new correct key; E is defensible if a unique answer is required.'),
4:dict(impact='removed',support='not_uniquely_supported',
    surviving_evidence='耶和华的话临到先知。“耶和华如此说：……你的尸体必不得葬入坟墓。”',
    critical_deletions=['先知就向那位从犹大来的神人呼喊说：','你祖先的'],
    finding='The entire sentence identifying the warning’s recipient as the man of God from Judah was deleted. The remaining 先知 is the recipient of revelation, which does not uniquely establish the addressee of the quoted warning. It explains why A could attract the reader, but does not establish the full role description in A. The ancestors qualifier was also removed, broadening the burial prohibition and damaging the question’s premise. B cannot be recovered uniquely from this window; E is the most defensible passage-only response. This mismatch is not an ordinary error with intact evidence.'),
5:dict(impact='retained',support='supported',
    surviving_evidence='名叫约西亚。他必将那些在你上面烧香的丘坛祭司献为祭',
    finding='Josiah’s name and the following action remain connected by 他. The omitted authority, location and bone-burning details do not remove the identity asked for. A remains supported.'),
6:dict(impact='retained',support='supported',
    surviving_evidence='老先知就抬起尸体，放在驴背上，运回自己的城里',
    finding='The old prophet’s action and destination remain explicit. The deletion of later burial details does not remove the first stated destination. A remains supported.'),
7:dict(impact='retained',support='supported',
    surviving_evidence='于是先知对儿子们说：“给我备驴。”他们就为他备好驴，他便骑上',
    finding='The old prophet, his instruction, the sons preparing the donkey and his riding remain linked. The omitted later encounter description does not remove the rider’s identity. B remains supported.'),
8:dict(impact='identity_removed_action_retained',support='partial_support',
    surviving_evidence='不肯离开他的恶道',
    critical_deletions=['耶罗波安仍不悔改，','耶罗波安家'],
    finding='The action supporting C remains: the unnamed man would not leave his evil conduct. However, both occurrences identifying Jeroboam were deleted. The question supplies the name missing from the passage. C is recoverable if that supplied identity is accepted, but the passage alone does not independently identify the man as Jeroboam. A clean-key match therefore masks damage to the subject–action link; do not silently treat the complete question as fully supported.'),
}
labels={'omission15':'Omission 15%','omission30':'Omission 30%'}
impact_labels={'retained':'Target evidence retained','weakened_ambiguous':'Referent weakened / ambiguous',
    'removed':'Recipient evidence removed','identity_removed_action_retained':'Action retained; identity removed'}
items=[]
for row in data['answers']:
    assert row['trial_status']=='submitted'
    note=notes[row['number']]
    deleted=' '.join(e['before'] for e in row['edits'])
    for phrase in note.get('critical_deletions',[]):assert phrase in deleted,(row['number'],phrase,deleted)
    items.append(dict(**row,**note))
conditions=[]
for condition,label in labels.items():
    group=[r for r in items if r['condition']==condition]
    conditions.append(dict(condition=condition,label=label,total=len(group),
        clean_key_matches=sum(r['clean_key_match'] for r in group),
        evidence_impact=dict(Counter(r['impact'] for r in group))))
correct=sum(r['clean_key_match'] for r in items)
assert correct==6 and [r['number'] for r in items if not r['clean_key_match']]==[3,4]
assert all(r['clean_key_match'] for r in items if r['impact']=='retained')
review=dict(participant_id=data['participant_id'],review_type='Assistant editorial review; no new independent model adjudication.',
    original_scoring='Agreement with original clean-source keys; not an altered-passage answer key.',
    clean_key_matches=correct,total=len(items),clean_key_accuracy=correct/len(items),
    conditions=conditions,evidence_counts=dict(Counter(r['impact'] for r in items)),
    active_time_ms=sum(r['active_time_ms'] or 0 for r in items),items=items,
    source_sha256=sha256((HOME/'results.json').read_bytes()).hexdigest(),
    limitations=['No grades, keys, passages, question eligibility or participant records were changed.',
        'A selected choice alone cannot establish whether the reader used the passage, inference, prior knowledge or earlier exposure.',
        'Different questions were assigned to the two doses; four observations per dose from one walkthrough cannot establish a causal dose effect.',
        'Q3 remains referentially ambiguous; Q4 loses the target recipient; Q8 relies on an identity supplied by the question. No single revised passage-based accuracy is asserted.'])
(HOME/'evidence_review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
    '<title>Your eight-question omission test</title><style>body{font:17px/1.65 system-ui;max-width:1200px;margin:28px auto;padding:0 20px;color:#233b42}',
    'table{border-collapse:collapse;width:100%;margin:18px 0}td,th{padding:9px;border-bottom:1px solid #d5dfdf;text-align:left;vertical-align:top}',
    '.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.passage{background:#f1f5f4;padding:15px}.note{background:#fff4df;padding:15px;border-left:4px solid #aa7830}',
    'details{margin:20px 0;border-top:1px solid #cad9d6;padding-top:14px}summary{cursor:pointer;font-weight:600}[lang=zh]{font-size:18px;line-height:1.9}',
    '@media(max-width:800px){.grid{grid-template-columns:1fr}}</style><h1>Your eight-question omission test</h1>',
    '<p><b>6/8 (75%) matched the original clean answer key.</b> Both doses scored 3/4 (75%). All eight responses were saved.</p>',
    '<div class="note">The two mismatches both involve damaged answer evidence. Q3 becomes ambiguous after a relational deletion; Q4 loses the warning’s recipient. Q8 matches the key but loses the person’s name. These judgments inspect the exact displayed text; they are an editorial audit, not newly approved scoring keys.</div>',
    '<table><tr><th>#</th><th>Question</th><th>Dose</th><th>Your answer</th><th>Clean key</th><th>Evidence</th></tr>']
for r in items:
    selected=r['choices'][ord(r['raw_answer'])-65];key=r['choices'][ord(r['mcq_correct_choice'])-65]
    parts.append(f'<tr><td><a href="#q{r["number"]}">{r["number"]}</a></td><td lang="zh">'+escape(r['question_text'])+'</td><td>'+escape(labels[r['condition']])+'</td><td>'+escape(r['raw_answer']+'. '+selected)+'</td><td>'+escape(r['mcq_correct_choice']+'. '+key)+'</td><td>'+escape(impact_labels[r['impact']])+'</td></tr>')
parts.append('</table><p>All five questions with retained target evidence matched the clean key. Of the three with weakened or missing links, one matched it. This describes this walkthrough; it does not prove that omission alone caused any individual response.</p>')
for r in items:
    parts.append(f'<details id="q{r["number"]}"'+(' open' if r['number'] in (3,4,8) else '')+f'><summary>{r["number"]}. '+escape(r['passage_reference']+' · '+labels[r['condition']])+f' · you {r["raw_answer"]}, clean key {r["mcq_correct_choice"]}</summary>')
    parts.append('<h2 lang="zh">'+escape(r['question_text'])+'</h2><ol type="A" lang="zh">')
    for i,text in enumerate(r['choices']):
        letter=chr(65+i);parts.append('<li>'+escape(text)+(' <b>← your answer</b>' if letter==r['raw_answer'] else '')+(' <b>[clean key]</b>' if letter==r['mcq_correct_choice'] else '')+'</li>')
    parts.append('</ol><p class="note">'+escape(r['finding'])+'</p><div class="grid">')
    for label,verses in [('Clean passage',r['clean_verses']),('Passage you saw',r['shown_verses'])]:
        parts.append('<div class="passage"><h3>'+label+'</h3>')
        for v,t in verses.items():parts.append('<p lang="zh">'+escape(v+'　'+t)+'</p>')
        parts.append('</div>')
    parts.append('</div><p>Achieved omission: '+f'{r["actual_dose"]:.2f}%'+'. Deletion occurrences: '+escape(str(r['unit_counts']))+'</p><details><summary>Exact deleted spans</summary><ul>')
    for e in r['edits']:parts.append('<li lang="zh">'+escape(e['verse'])+'　<del>'+escape(e['before'])+'</del></li>')
    parts.append('</ul></details></details>')
parts.append('<p>Read-only report. Your study records and clean answer keys are unchanged. The local preview stores answer receipts without a background grading worker; the score above was calculated directly from those saved responses.</p></html>')
(HOME/'index.html').write_text(''.join(parts))
print(json.dumps({k:v for k,v in review.items() if k in ('clean_key_matches','total','clean_key_accuracy','conditions','evidence_counts','active_time_ms')},ensure_ascii=False,indent=2))
