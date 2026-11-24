"""Readable, side-by-side report for a nested defect run, including held drafts."""
import argparse
from collections import Counter
from html import escape
from pathlib import Path

from evaluation.scripts.pipeline.build_nested_window_defects import DOSES, PASS, all_pass, m, signature


LABELS={'pass':'Pass','pass_with_flags':'Pass with flags','rejected':'Rejected — held for review',
        'held':'Held for review','held_dose':'Held — outside dose band',
        'pending_combined_review':'Awaiting review'}


def report(result):
    title=result.get('title','1 Kings 13')
    window_count=len(next(iter(result['families'].values()))['windows'])
    cfg=result['configuration'];parts=['<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+' · Nested defect passages</title>',
        '<style>body{margin:30px auto;padding:0 22px;max-width:1600px;font:16px/1.6 system-ui,sans-serif;color:#203b42}h1{line-height:1.2}h2{margin-top:2.5rem}h3{margin-top:0}.note{background:#edf4f2;padding:16px;border-left:4px solid #397766}.scroll{overflow:auto}.grid{display:grid;grid-template-columns:repeat(4,minmax(260px,1fr));gap:14px}article{background:#f2f5f5;padding:16px;border:1px solid #d6e0df;border-radius:7px}article.held{border-top:4px solid #ad5e34}article.pass{border-top:4px solid #36796b}.zh{font-size:18px;line-height:1.85}small{color:#526a70}table{border-collapse:collapse;width:100%;margin:15px 0}td,th{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid #d6e0df}th{background:#edf3f2}details{margin:10px 0}summary{cursor:pointer;font-weight:600}li{margin:5px 0}.new{color:#075daa}a{color:#146c7d}.clean{max-width:1200px;background:#f6f4ee;padding:15px}.review{font-size:14px}</style></head><body>',
        '<h1>'+escape(title)+' · Nested 30%, 40%, 50%, 60% defects</h1>',
        '<p>'+str(window_count)+' displayed QA windows, with an omission ladder and a mistranslation ladder for each. '
        'Higher doses retain every lower-dose edit, including the same replacement wording for mistranslation. '
        'Each defect family has its own nested sequence; edited locations can differ between families.</p>',
        '<div class="note"><b>Local experimental drafts; not published.</b> All rates use clean Chinese content characters '
        'as the denominator. Omission counts deleted content; mistranslation counts the clean source spans selected for '
        'substitution, after trimming unchanged edges. These are not percentages of false facts or changed clauses. '
        'Each target allows ±2 percentage points. Every level needs its own whole-window review.</div>',
        '<p>Writer: '+escape(cfg['writer'])+'; reviewer: '+escape(cfg['reviewer'])+'. Newly generated wording comes from '
        'the pipeline. No manually written passage repairs were inserted. A changed 30% baseline is explicitly identified '
        'below; previous published passages remain unchanged.</p>']
    if result.get('agreement_migration'):
        parts.append('<p class="note"><b>Pronoun agreement rechecked.</b> All 32 mistranslation versions '
            'were audited for written gender agreement. Repaired ladders received all six checks again; '
            'unchanged text retains its previous five checks plus the new agreement audit. Clear '
            'gender mismatches are now blocking failures, not merely flags.</p>')
    for family,f in result['families'].items():
        states=f['windows'];complete=sum(all_pass(s['cells']) for s in states.values())
        statuses=Counter(c['status'] for s in states.values() for c in s['cells'].values())
        title=family.capitalize()
        parts.append('<h2>'+title+'</h2><p><b>'+str(complete)+' / '+str(len(states))+
            ' complete ladders passed</b>. '+escape('; '.join(f'{LABELS.get(k,k)}: {v}' for k,v in statuses.items()))+'.</p>')
        parts.append('<p><small>Stop status: '+escape(f.get('stop_reason','Run in progress'))+'</small></p>')
        parts.append('<div class="scroll"><table><tr><th>Window</th>'+''.join('<th>'+str(d)+'%</th>' for d in DOSES)+'<th>30% baseline</th></tr>')
        for wid,s in states.items():
            anchor=family+'-'+m.clean_digest(wid)[:12]
            parts.append('<tr><td><a href="#'+anchor+'">'+escape(s['reference'])+'</a></td>')
            for d in DOSES:
                c=s['cells'].get(str(d))
                parts.append('<td>'+(f'{c["actual_percent"]:.1f}%<br><small>{escape(LABELS.get(c["status"],c["status"]))}</small>' if c else 'Pending')+'</td>')
            parts.append('<td>'+('Revised draft' if s.get('baseline_30_changed') else 'Retained' if s['cells'] else 'Pending')+'</td></tr>')
        parts.append('</table></div>')
        if family=='omission':
            parts.append('<h3>Omission mix across the displayed windows</h3><p>The 20/40/40 target is by deletion occurrences, '
                'pooled separately at each dose. These counts describe retained drafts, including held versions. '
                'It is a soft objective after dose fit and nesting; any departure is shown. '
                'Each atom in a coordinated bundle counts according to its reviewed classification. Unclassified or '
                'multiple-clause spans are listed separately, not silently counted as one clause.</p><table><tr><th>Dose</th>'
                '<th>Word</th><th>Phrase</th><th>Clause</th><th>Other classifications</th></tr>')
            for d in DOSES:
                counts=Counter(k for s in states.values() for k,n in s['cells'].get(str(d),{}).get('unit_counts',{}).items() for _ in range(n))
                total=sum(counts.values())
                parts.append('<tr><td>'+str(d)+'%</td>'+''.join(f'<td>{counts[k]} ({100*counts[k]/total:.1f}%)</td>' if total else '<td>—</td>' for k in m.KINDS)+
                    '<td>'+escape(str({k:v for k,v in counts.items() if k not in m.KINDS}))+'</td></tr>')
            parts.append('</table>')
        for wid,s in states.items():
            anchor=family+'-'+m.clean_digest(wid)[:12]
            parts.append('<h2 id="'+anchor+'">'+escape(s['reference'])+' · '+title+'</h2><div class="clean"><h3>Clean Chinese</h3>')
            for v,t in s['clean'].items():parts.append('<p class="zh"><small>'+escape(v)+'</small>　'+escape(t)+'</p>')
            parts.append('</div><details><summary>English source and previous 30% baseline</summary>')
            parts.extend('<p>'+escape(v)+' '+escape(t)+'</p>' for v,t in s['english'].items())
            parts.extend('<p class="zh">'+escape(v)+'　'+escape(t)+'</p>' for v,t in s['baseline']['verses'].items())
            if s['baseline'].get('reason'):parts.append('<p>'+escape(s['baseline']['reason'])+'</p>')
            parts.append('</details>')
            if s.get('baseline_30_changed'):
                parts.append('<p><b>The 30% draft below differs from the previous baseline.</b> It is part of this newly reviewed nested family; the prior version has not been overwritten.</p>')
            parts.append('<div class="scroll"><div class="grid">');prior=set()
            for d in DOSES:
                c=s['cells'].get(str(d))
                if not c:continue
                parts.append('<article class="'+('pass' if c['status'] in PASS else 'held')+'"><h3>'+str(d)+'% target</h3>'+
                    f'<p><b>{c["actual_percent"]:.1f}% actual</b> · {c["affected_chars"]} source characters<br>'+escape(LABELS.get(c['status'],c['status']))+'</p>')
                parts.extend('<p class="zh"><small>'+escape(v)+'</small>　'+escape(t)+'</p>' for v,t in c['verses'].items())
                if c.get('review'):parts.append('<details class="review"><summary>Review findings</summary><p>'+escape(c['review']['reason'])+'</p><p>'+escape(str(c.get('checks',{})))+'</p></details>')
                if c.get('gender_agreement_audit'):
                    parts.append('<details class="review"><summary>Additional gender agreement audit</summary><p>'+
                        escape(c['gender_agreement_audit']['reason'])+'</p></details>')
                if c.get('reason'):parts.append('<p class="review">'+escape(c['reason'])+'</p>')
                if c.get('flags'):parts.append('<p class="review">Flags: '+escape(', '.join(c['flags']))+'</p>')
                parts.append('<details><summary>Edits — additions at this level in blue</summary><ul>')
                for e in c['edits']:
                    new=signature([e])[0] not in prior
                    text=e['verse']+' · '+e['before']+(' → '+e['after'] if family=='mistranslation' else ' [deleted]')
                    parts.append('<li'+(' class="new"' if new else '')+'>'+escape(text)+'</li>')
                parts.append('</ul></details></article>');prior=set(signature(c['edits']))
            parts.append('</div></div><p><small>New candidate proposals: '+str(s['proposed_count'])+'; batches: '+str(s['batches'])+
                '; ladder selections reviewed/recorded: '+str(len(s['history']))+'.</small></p>')
    return ''.join(parts)+'</body></html>'


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('input',type=Path);cli.add_argument('output',type=Path)
    args=cli.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(report(m.review.read(args.input)))
    print(args.output)
