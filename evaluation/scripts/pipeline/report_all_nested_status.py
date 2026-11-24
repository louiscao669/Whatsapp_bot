"""Compact status matrix and held-item reasons for a full nested draft run."""
import argparse
from collections import Counter
from html import escape
from pathlib import Path

from evaluation.scripts.pipeline import build_nested_window_defects as n


def render(result):
    families=('omission','mistranslation');states=result['families']
    p=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>66 windows · Nested defect review status</title>',
       '<style>body{max-width:1450px;margin:30px auto;padding:0 20px;font:16px/1.5 system-ui;color:#20343e}table{border-collapse:collapse;width:100%}th,td{border:1px solid #d4dfe3;padding:9px;text-align:left;vertical-align:top}th{background:#edf2f4}.scroll{overflow:auto}.pass{background:#e9f4ed}.pass_with_flags{background:#edf3fa}.held,.rejected,.held_dose{background:#fff0e5}small{font-size:12px;color:#465963}details{border-bottom:1px solid #ccd6dc;padding:14px 0}summary{cursor:pointer}a{color:#12637a}</style>',
       '<h1>66 from-scratch windows · Nested defect review</h1>',
       '<p>30%, 40%, 50%, and 60% omission and mistranslation. Local drafts; not published.</p>',
       '<p><b>Pass with flags is accepted</b>: all required checks passed, but effects such as semantic distortion, '
       'contradictions or recoverable information were recorded. <b>Held</b> is not accepted: the dose is outside ±2 '
       'percentage points, a required check failed, or the reviewer was uncertain. A complete usable ladder needs '
       'all four levels to pass. The table describes each retained nested sequence; isolated passing '
       'versions from incompatible sequences are not combined. Rates count clean Chinese content '
       'characters in edited source spans.</p>',
       '<p><a href="sol_nested_defects_all66.html">Read all passages, edits and complete reviewer explanations</a></p>',
       '<h2>Counts by defect and dose</h2><table><tr><th>Defect</th><th>Dose</th><th>Pass</th><th>Pass with flags</th><th>Held</th><th>Pending</th></tr>']
    for family in families:
        for dose in n.DOSES:
            counts=Counter(s['cells'].get(str(dose),{}).get('status','pending') for s in states[family]['windows'].values())
            p.append('<tr><td>'+family.title()+'</td><td>'+str(dose)+'%</td>'+''.join('<td>'+str(x)+'</td>' for x in
                (counts['pass'],counts['pass_with_flags'],sum(counts[k] for k in ('held','held_dose','rejected')),
                 sum(v for k,v in counts.items() if k not in n.PASS|{'held','held_dose','rejected'})))+'</tr>')
    p.append('</table><h2>Every window</h2><div class="scroll"><table><thead><tr><th rowspan="2">Window</th>'+
        ''.join('<th colspan="4">'+f.title()+'</th>' for f in families)+'</tr><tr>'+
        ''.join('<th>'+str(d)+'%</th>' for _ in families for d in n.DOSES)+'</tr></thead><tbody>')
    held=[]
    for wid,s in states['omission']['windows'].items():
        p.append('<tr><td>'+escape(s['reference'])+'</td>')
        for family in families:
            state=states[family]['windows'][wid]
            for dose in n.DOSES:
                c=state['cells'].get(str(dose),{});status=c.get('status','pending')
                label={'pass':'Pass','pass_with_flags':'Pass + flags','held_dose':'Held: dose','held':'Held: uncertain',
                       'rejected':'Held: failed check'}.get(status,'Pending')
                anchor=family+'-'+n.m.clean_digest(wid)[:12]
                p.append('<td class="'+escape(status)+'"><a href="sol_nested_defects_all66.html#'+anchor+'">'+label+
                    '</a>'+('<br><small>'+f'{c["actual_percent"]:.1f}% actual</small>' if c else '')+'</td>')
                if status in {'held','held_dose','rejected'}:
                    alternative=False
                    for h in state.get('history',[]):
                        previous=h.get(str(dose),{})
                        if previous.get('status') not in n.PASS or abs(previous.get('actual_percent',-100)-dose)>2:continue
                        known=n.remembered_review(state['history'],previous)
                        if known and known.get('checks') and all(v=='yes' for v in known['checks'].values()):
                            alternative=True;break
                    held.append((state['reference'],family,dose,c,alternative))
        p.append('</tr>')
    p.append('</tbody></table></div><h2>Held versions and reasons</h2>')
    if not held:p.append('<p>No held versions in the recorded results.</p>')
    for reference,family,dose,c,alternative in held:
        reason=(c.get('reason','Outside target tolerance') if c['status']=='held_dose' else
                c.get('review',{}).get('reason') or c.get('reason','No completed review recorded.'))
        checks={k:v for k,v in c.get('checks',{}).items() if v!='yes'}
        p.append('<details><summary>'+escape(reference)+' · '+family+' '+str(dose)+'% · '+f'{c["actual_percent"]:.1f}% actual</summary>'+
            '<p>'+escape(reason)+'</p>'+('<p>Required checks: '+escape(str(checks))+'</p>' if checks else '')+
            ('<p>A version at this dose passed in another reviewed sequence. It cannot be substituted here without rechecking the entire nested ladder.</p>' if alternative else '')+'</details>')
    return ''.join(p)+'</html>'


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('input',type=Path);cli.add_argument('output',type=Path)
    args=cli.parse_args();args.output.write_text(render(n.m.review.read(args.input)),encoding='utf-8')
