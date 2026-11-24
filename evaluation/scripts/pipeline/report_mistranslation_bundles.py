"""Render a readable local report for one anchored mistranslation bank."""
import argparse
from collections import Counter
from html import escape
import json
from pathlib import Path


def report(bank,audit,passage):
    stats=Counter(r['status'] for r in audit['candidates'])
    accepted=[r for r in audit['candidates'] if r['status']=='accepted']
    flagged=sum(bool(r['review']['judgment']['flags']) for r in accepted)
    a=bank['acquisition']
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Mistranslation candidate trial</title><style>body{font:16px/1.65 system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#203b42}article{padding:1rem;background:#f0f5f4;margin:1rem 0;border-radius:8px}pre{white-space:pre-wrap;font:inherit}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccdadd;padding:.5rem;text-align:left}.flag{color:#775500}</style>',
        '<h1>'+escape(bank['chapter'])+' · Mistranslation candidate trial</h1>',
        '<p>Local draft. No changes to the live study. Model proposals and independent reviews; no manually written stimulus edits.</p>',
        f'<p>Bound: {a["max_candidates"]} total proposals, up to {bank["configuration"]["max_batches"]} batches of '
        f'{bank["configuration"]["batch_size"]}. Each proposal contains up to four coordinated substitutions. '
        'Rejected and duplicate proposals count against the budget.</p>',
        f'<p>Used {a["proposed_count"]} proposals in {a["rounds_used"]} batches. '
        f'Pass without flags: {len(accepted)-flagged}; pass with flags: {flagged}; '
        f'held: {stats["held"]}; rejected: {stats["rejected"]}; duplicate: {stats["duplicate"]}.</p>',
        f'<p>Target: {100*a["target_rate"]:.1f}% source-span coverage. Numerical capacity: '
        f'{100*a["numeric_available_rate"]:.1f}%; highest combined-review pass: '
        f'{100*a["reviewed_available_rate"]:.1f}%. Stop: {escape(a["stop_reason"])}.</p>',
        '<p>Coverage counts clean characters in selected source spans. Identical span prefixes and suffixes '
        'are excluded before review; wording is unchanged by this normalization. This is not a percentage of all facts or clauses.</p>',
        '<h2>Clean window</h2><pre>'+escape(passage)+'</pre><h2>Combined selections</h2>']
    for c in bank['reviewed_combinations']:
        r=c['review'];parts.append(f'<article><h3>{100*c["actual_rate"]:.1f}% · {escape(r["status"])}</h3><pre>'+escape(c['text'])+'</pre>'
            '<p>'+escape(r['judgment']['explanation'])+'</p>')
        if r['judgment']['flags']:parts.append('<p class="flag">Flags: '+escape('; '.join(r['judgment']['flags']))+'</p>')
        parts.append('<details><summary>Selected substitutions</summary><ul>')
        for e in c['edits']:parts.append('<li>'+escape(e['source'])+' → '+escape(e['target'])+'</li>')
        parts.append('</ul></details></article>')
    if bank.get('failure_cuts'):
        parts.append('<h2>Retained fluency failures</h2><p>These earlier quoted failures prevent the contributing '
                     'bundles from being selected together. Unrelated changes do not clear them.</p><ul>')
        for c in bank['failure_cuts']:parts.append('<li>'+escape(c['quoted_failure'])+'</li>')
        parts.append('</ul>')
    parts.append('<h2>All candidate decisions</h2>')
    for i,row in enumerate(audit['candidates'],1):
        parts.append(f'<article><h3>{i}. Batch {row["round"]} · {escape(row["status"])}</h3><ul>')
        c=row.get('candidate')
        if c:
            for e in c['edits']:parts.append('<li>'+escape(e['source'])+' → '+escape(e['target'])+f' <small>(clean offset {e["start"]})</small></li>')
        else:
            for e in row['proposal']['edits']:parts.append('<li>'+escape(e['source'])+' → '+escape(e['target'])+'</li>')
        parts.append('</ul><p>'+escape(row.get('reason',''))+'</p>')
        r=row.get('review',{}).get('judgment',{})
        if r.get('flags'):parts.append('<p class="flag">Flags: '+escape('; '.join(r['flags']))+'</p>')
        parts.append('</article>')
    return ''.join(parts)+'</html>'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bank',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    bank=json.loads(args.bank.read_text());root=args.bank.parent
    audit=json.loads((root/'bundle_review.json').read_text())
    records=json.loads((root/'bundle_proposals.json').read_text())['records'].values()
    from evaluation.scripts.variants.banks.mistranslation_validation import digest
    passage=next(r['request']['passage'] for r in records if digest(r['request']['passage'])==bank['configuration']['source_sha256'])
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(report(bank,audit,passage))
