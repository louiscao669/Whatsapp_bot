"""Render a self-contained review of the generated Chinese window variants."""
from html import escape
from pathlib import Path


def condition_label(key):
    family = key.rstrip('0123456789')
    return f'{family.capitalize()} {key[len(family):]}%'


def passage(verses):
    return ''.join(f'<p lang="zh"><small>{escape(label)}</small> {escape(text)}</p>'
                   for label, text in verses.items())


def write_report(draft, path: Path):
    windows = draft['windows']
    conditions = list(draft['counts'])
    held = {w['id'] for w in windows if any(
        w['conditions'][k]['status'] == 'held' for k in conditions)}
    title = f'{draft["bank"].capitalize()} QA window doses'
    refill = {(r['id'], k):r for r in draft.get('window_refill', []) for k in r['before']}
    headers = ''.join(f'<th scope="col">{condition_label(k)}</th>' for k in conditions)
    rows, details = [], []
    for i, window in enumerate(windows, 1):
        ref, question = escape(window['reference']), escape(window['question'])
        clean = window['conditions']['clean']['verses']
        row = [f'<tr data-held="{int(window["id"] in held)}"><th scope="row">{ref}</th>']
        details.append(f'<article><h2>{ref}</h2><p lang="zh">{question}</p>')
        for key in conditions:
            c = window['conditions'][key]
            is_held = c['status'] == 'held'
            status = 'Review' if is_held else 'Met'
            anchor = f'w{i}-{key}'
            rate = f'{c["actual_percent"]:.2f}%'
            row.append(f'<td class="{c["status"]}"><a href="#{anchor}">{rate} · {status}</a></td>')
            reason = ''
            if is_held:
                reason = (f'<p>{escape(c["reason"])} The eligible edits cover '
                          f'{c["eligible_content_chars"]} of {window["clean_content_chars"]} '
                          f'content characters in {c["eligible_groups"]} selectable groups.</p>')
            history = ''
            if (window['id'], key) in refill:
                run = refill[window['id'], key]
                history = (f'<p>Before generation {run["before"][key]:.2f}% · After {rate}. '
                           f'{escape(run["generation"])}'
                           + (f' · {run["approved"]} approved proposals for this family and window.'
                              if run['approved'] is not None else '.') + '</p>')
            details.append(f'<details id="{anchor}"><summary>{condition_label(key)} · {rate} · {status}</summary>{history}'
                           f'<p>{c["affected_chars"]} of {window["clean_content_chars"]} source content '
                           f'characters affected.</p>{reason}<div class="pair"><section><h3>Clean</h3>'
                           f'{passage(clean)}</section><section><h3>Generated</h3>{passage(c["verses"])}'
                           f'</section></div><a href="#windows">Return to all windows</a></details>')
        rows.append(''.join(row) + '</tr>')
        details.append('</article>')
    summary = ''.join(f'<li>{condition_label(k)} · {v.get("within_target", 0)} met, '
                      f'{v.get("held", 0)} for review</li>' for k, v in draft['counts'].items())
    content = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
*{{box-sizing:border-box}}body{{max-width:78rem;margin:auto;padding:1.2rem;color:#192827;
font:16px/1.55 system-ui,sans-serif}}h1,h2,h3{{line-height:1.2}}table{{border-collapse:collapse;width:100%}}
th,td{{padding:.5rem .6rem;text-align:left;border-bottom:1px solid #cfd9d5}}
thead th{{background:#e9efec}}tr:nth-child(even){{background:#f7f9f8}}
a{{color:#13564c}}.held a{{color:#862e0c;font-weight:650}}.scroll{{overflow:auto}}
article{{border-top:1px solid #cfd9d5;margin:1.4rem 0}}details{{padding:.4rem 0}}
summary,select{{cursor:pointer}}.pair{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}
.pair section{{padding:.2rem .85rem;background:#f3f6f4}}small{{color:#4b5e59}}
@media(max-width:700px){{.pair{{grid-template-columns:1fr}}}}
</style><main><h1>{title}</h1><p>{len(windows)} windows · {len(windows)-len(held)} meet every target
 · {len(held)} have at least one dose for review.</p><ul>{summary}</ul>
<p>A dose meets target within ±{draft['tolerance_percentage_points']} percentage points, using
 unrounded values. The denominator is the source content characters in the displayed window.
 Omission counts removed text, mistranslation counts replaced source phrases, and grammar counts
 the full clauses edited. Each verse retains some content. Dose checks measure exposure.
 Whether the excerpt supports the answer is a separate question.</p>
<h2 id="windows">Results by window</h2><label>Show <select id="filter"><option value="all">All windows</option>
<option value="1">Windows with a dose for review</option><option value="0">Windows meeting every target</option>
</select></label><p>Select a percentage to compare the generated passage with clean.</p>
<div class="scroll"><table><thead><tr><th>Window</th>{headers}</tr></thead><tbody>{''.join(rows)}</tbody>
</table></div>{''.join(details)}</main><script>
const filter = document.getElementById('filter');
filter.onchange = () => document.querySelectorAll('tr[data-held]').forEach(row => {{
  row.hidden = filter.value !== 'all' && row.dataset.held !== filter.value;
}});
function openVariant() {{
  const target = document.getElementById(location.hash.slice(1));
  if (target && target.tagName === 'DETAILS') {{ target.open = true; target.scrollIntoView(); }}
}}
addEventListener('hashchange', openVariant); openVariant();
</script></html>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
