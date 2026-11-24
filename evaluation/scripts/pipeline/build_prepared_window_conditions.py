"""Generate Sol pilot variants at the dose assigned to each displayed QA window."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import re
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from evaluation.scripts.pipeline.prepare_clean_passage_conditions import (
    BASE, ROOT, RUN, grammar, mis, omission, read, save, validate_reviewed_bank,
)
from evaluation.scripts.pipeline.build_clean_passage_ladder import edit_span, omission_verses, replay
from eten_shared.experiment_plan import SLOTS
from pilot_import import load_tier1_metadata, parse_tier1_verses
from pilot_import_reviewed122 import SOL_RELEASE, SOL_SET, checked_json, load_bank, sol_wbw_release

FAMILIES = ('omission', 'mistranslation', 'grammar')
MARKER = re.compile(r'(?m)^\d+[ \t]+')
DEFAULT_SHIFTS = ROOT / 'evaluation/runs/sol_prepared_window_shift_audit_2026-11-12/shifts.json'


@dataclass(frozen=True)
class Edit:
    verse: str
    start: int
    before: str
    after: str


def passage_edits(pack, directory, excluded, metadata):
    clean = pack['conditions']['clean']
    text, verses = clean['text'], clean['verses']
    marks = list(MARKER.finditer(text))
    bounds = []
    for i, ((label, body), marker) in enumerate(zip(verses.items(), marks, strict=True)):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        segment = text[marker.end():end]
        begin = marker.end() + len(segment) - len(segment.lstrip())
        if text[begin:begin + len(body)] != body or segment.strip() != body:
            raise ValueError(f'Clean verse boundary differs in {label}')
        bounds.append((begin, begin + len(body), label))

    def local(start, before, after):
        if not text.startswith(before, start):
            raise ValueError('Source edit differs from the frozen passage')
        end = start + len(before)
        (lo, hi, label), = [b for b in bounds if b[0] < end and b[1] > start]
        left, right = max(start, lo), min(end, hi)
        prefix, suffix = text[start:left], text[right:end]
        if after and not (after.startswith(prefix) and after.endswith(suffix)):
            raise ValueError('Edit alters the printed verse boundary')
        replacement = after[len(prefix):len(after) - len(suffix)] if after else ''
        return Edit(label, left - lo, text[left:right], replacement)

    by_family = {f: {} for f in FAMILIES}
    grammar_id = pack['families']['grammar']['bank_id']
    gbank = read(directory / 'grammar/_grammar_bank' / f'bank_{grammar_id}.json')
    grammar.validate_grammar_bank(text, gbank)
    grammar_units = grammar.passage_units(text, unit_mode=gbank['spec'].get('unit_mode', 'clause'))
    grammar_entries = {e['unit_index']: e for e in gbank['entries']}
    grammar_indices = {e['unit_index']: i for i, e in enumerate(gbank['entries'])}
    omission_spans = {}
    for family, units in [('grammar', grammar_units), ('omission', omission.passage_units(text))]:
        cursor = 0
        for i, unit in enumerate(units):
            raw = unit['text']
            if family == 'grammar' and i in grammar_entries:
                entry = grammar_entries[i]
                edit = local(cursor, entry['original_text'], entry['corrupted_text'])
            elif family == 'omission' and unit['omittable'] and unit['content_chars']:
                edit = local(cursor, raw, '')
                omission_spans[i] = edit_span(cursor, raw, '')
            else:
                cursor += len(raw)
                continue
            if mis.content_len(edit.before) != unit['content_chars']:
                raise ValueError('Visible edit weight differs from its clause weight')
            by_family[family][i] = [edit]
            cursor += len(raw)
        if cursor != len(text):
            raise ValueError('Clause segmentation did not cover the clean passage')
    mbank = read(directory / '_base/_shared/mistranslation_bank_coverage_zh.json')
    validate_reviewed_bank(mbank, text)
    if mbank['bank_id'] != pack['families']['mistranslation']['bank_id']:
        raise ValueError('Wrong mistranslation bank')
    groups = mis.candidate_groups(mis.find_occurrences(text, mis.normalized_replacements(mbank)))
    for i, group in enumerate(groups):
        if (group['source'], group['target']) not in excluded:
            by_family['mistranslation'][i] = [
                local(o['start'], o['source'], o['target']) for o in group['occurrences']]

    def generate(family, dose, ids, labels):
        # Banks are validated against the complete frozen source. Render with the
        # native generator, then return only the verses in this independent window.
        kwargs = dict(rate=dose / 100, seed=pack['families'][family]['seed'])
        if family == 'omission':
            result, _ = omission.apply_omissions(text, selected_unit_indices=ids, **kwargs)
            spans = [omission_spans[i] for i in ids]
            if result != replay(text, spans):
                raise ValueError('Omission generator disagrees with its selected edits')
            generated = omission_verses(text, verses, spans)
        else:
            if family == 'grammar':
                result, _ = grammar.apply_grammar_bank(text, bank=gbank,
                    selected_bank_indices=[grammar_indices[i] for i in ids], **kwargs)
            else:
                result, _ = mis.apply_mistranslations(text, bank=mbank,
                    selected_group_indices=ids, **kwargs)
            generated = dict(parse_tier1_verses(result, metadata))
        return {label: generated[label] for label in labels}

    return by_family, generate


def choose(groups, clean, doses, tolerance, protect_verses, *, conflicts=(), fixed=None,
           baseline_chars=None):
    """Fit all doses jointly, first maximizing cells in band, then minimizing total error."""
    keys = list(groups)
    n, k = len(keys), len(doses)
    total = sum(map(mis.content_len, clean.values()))
    if not total or not doses:
        raise ValueError('Empty window or dose list')
    if not keys:
        return {dose: [] for dose in doses}
    weights = np.array([sum(mis.content_len(e.before) for e in groups[i]) for i in keys])
    cols = k * n + 2 * k
    errors, missed = k * n, k * n + k
    upper = np.ones(cols)
    upper[errors:missed] = 100 * total
    cost = np.zeros(cols)
    cost[errors:missed] = 1
    cost[missed:] = k * 100 * total + 1
    rows, limits = [], []

    def row():
        return np.zeros(cols)

    def limit(values, maximum):
        rows.append(values)
        limits.append(maximum)

    for j, dose in enumerate(doses):
        selection = slice(j * n, (j + 1) * n)
        for a, b in conflicts:
            values = row()
            values[j*n+a] = values[j*n+b] = 1
            limit(values, 1)
        if fixed and dose in fixed:
            for i, key in enumerate(keys):
                values = row()
                required = key in fixed[dose]
                values[j*n+i] = -1 if required else 1
                limit(values, -1 if required else 0)
        for sign in (1, -1):
            values = row()
            values[selection] = sign * 100 * weights
            values[errors + j] = -1
            limit(values, sign * dose * total)
        if baseline_chars:
            upper[errors + j] = abs(100 * baseline_chars[dose] - dose * total)
        values = row()
        values[errors + j] = 1
        values[missed + j] = -100 * total
        limit(values, tolerance * total)
        if j:
            for i in range(n):
                values = row()
                values[(j-1) * n + i], values[j * n + i] = 1, -1
                limit(values, 0)
    if protect_verses:
        for verse, text in clean.items():
            values = row()
            values[(k-1)*n:k*n] = [
                sum(mis.content_len(e.before) for e in groups[i] if e.verse == verse) for i in keys]
            limit(values, mis.content_len(text) - 1)
    integers = np.ones(cols)
    integers[errors:missed] = 0
    fit = milp(cost, integrality=integers, bounds=Bounds(np.zeros(cols), upper),
               constraints=LinearConstraint(np.array(rows), -np.inf, limits),
               options={'mip_rel_gap': 0})
    if not fit.success:
        raise RuntimeError(f'Window dose selection failed: {fit.message}')
    return {dose: [i for idx, i in enumerate(keys) if fit.x[j*n + idx] > .5]
            for j, dose in enumerate(doses)}


def render(clean, edits):
    result = {}
    for label, text in clean.items():
        start = 0
        pieces = []
        for e in sorted((e for e in edits if e.verse == label), key=lambda e: e.start):
            if e.start < start or not text.startswith(e.before, e.start):
                raise ValueError(f'Overlapping or stale selection in {label}')
            pieces.extend((text[start:e.start], e.after))
            start = e.start + len(e.before)
        result[label] = ''.join(pieces) + text[start:]
        if not mis.content_len(result[label]):
            raise ValueError(f'Omission would change the displayed verse window in {label}')
    return result


def build(layout, shifts_file, bank='prepared'):
    source_name = {'prepared': 'Prepared60', 'from-scratch': 'Hard77'}[bank]
    questions = [q for q in load_bank(SOL_SET) if q['source'] == source_name]
    moves = {}
    if layout != 'current':
        if bank != 'prepared':
            raise ValueError('Window shifts are defined only for the prepared bank')
        shifts = read(shifts_file)['shifts']
        moving = [s for s in shifts if layout in s['plans']]
        moves = {s['id']: s for s in moving}
        if not moves or len(moves) != len(moving) or moves.keys() - {q['id'] for q in questions}:
            raise ValueError('Window proposal differs from the prepared roster')
    manifest = read(SOL_RELEASE / 'manifest.json')
    conditions = list(dict.fromkeys(SLOTS))
    doses = defaultdict(list)
    for name in conditions:
        if name not in ('clean', 'wbw'):
            match = re.fullmatch(r'(omission|grammar|mistranslation)(\d+)', name)
            if not match:
                raise ValueError(f'Unknown condition {name}')
            doses[match[1]].append(int(match[2]))
    tolerance = manifest['coverage_tolerance_pp']
    excluded = {(e['source'], e['target']) for file in BASE.glob('t1_*/_base/_shared/mistranslation_bank_sol_length_zh.json')
                for e in read(file).get('curation', {}).get('excluded_pairs', [])}
    windows = []
    metadata = {m['id']: m for m in load_tier1_metadata(ROOT / 'evaluation')}
    wbw = sol_wbw_release({Path(file).stem for file in manifest['files']}) if bank == 'from-scratch' else {}
    for pid in sorted({q['passage_id'] for q in questions}):
        pack = checked_json(SOL_RELEASE / f'{pid}.json', manifest['files'][f'{pid}.json'])
        pool, generate = passage_edits(pack, RUN / 'release' / pid, excluded, metadata[pid])
        source = pack['conditions']['clean']['verses']
        seen = set()
        for q in (q for q in questions if q['passage_id'] == pid):
            labels = list(q['verses'])
            if q['verses'] != {v:source[v] for v in labels}:
                raise ValueError(f'Stale clean wording for {q["id"]}')
            if q['id'] in moves:
                move = moves[q['id']]
                if move['old'] != labels:
                    raise ValueError(f'Stale window proposal for {q["id"]}')
                labels = move['new']
            idx = list(source).index(labels[0])
            if list(source)[idx:idx+len(labels)] != labels:
                raise ValueError(f'Noncontiguous window for {q["id"]}')
            if bank == 'prepared' and (len(labels) != 3 or seen.intersection(labels)):
                raise ValueError(f'Expected disjoint three-verse prepared windows in {pid}')
            seen.update(labels)
            clean = {v:source[v] for v in labels}
            total = sum(map(mis.content_len, clean.values()))
            control = wbw[pid] if wbw else pack['conditions']['wbw']
            cells = {'clean': {'verses':clean}, 'wbw': {'verses':{
                v:control['verses'][v] for v in labels}}}
            for family, requests in doses.items():
                groups = {i: [e for e in group if e.verse in clean] for i, group in pool[family].items()}
                groups = {i: group for i, group in groups.items() if group}
                available = sum(mis.content_len(e.before) for group in groups.values() for e in group)
                requests = sorted(requests)
                plan = choose(groups, clean, requests, tolerance, family == 'omission')
                previous = set()
                for dose in requests:
                    ids = plan[dose]
                    if not previous.issubset(ids):
                        raise ValueError('Dose selections are not nested')
                    previous = set(ids)
                    edits = [e for i in ids for e in groups[i]]
                    affected = sum(mis.content_len(e.before) for e in edits)
                    status = 'within_target' if abs(100*affected-dose*total) <= tolerance*total else 'held'
                    text = generate(family, dose, ids, labels)
                    if text != render(clean, edits):
                        raise ValueError(f'Window replay differs from generator for {q["id"]} / {family}{dose}')
                    if family == 'omission' and total - sum(map(mis.content_len, text.values())) != affected:
                        raise ValueError('Rendered omission differs from the selected dose')
                    if status == 'within_target' and text == clean:
                        raise ValueError('Window has no visible defect')
                    cell = dict(status=status, target_percent=dose,
                        actual_percent=100*affected/total, affected_chars=affected, selected_ids=ids,
                        edits=[asdict(e) for e in edits], verses=text)
                    if status == 'held':
                        cell['eligible_groups'] = len(groups)
                        cell['eligible_content_chars'] = available
                        cell['reason'] = ('Insufficient eligible edit coverage in this excerpt.'
                                          if 100*available < (dose-tolerance)*total else
                                          'Available edit sizes do not fit the band in the nested plan.')
                    cells[family+str(dose)] = cell
            windows.append(dict(id=q['id'], passage_id=pid, verses=labels, question=q['question'],
                        reference=(q['reference'] if bank == 'from-scratch' else
                                   pack['reference'].rsplit(' ',1)[0]+' '+labels[0]+'–'+labels[-1]),
                        clean_content_chars=total, conditions=cells))
    counts = {f+str(d):dict(Counter(w['conditions'][f+str(d)]['status'] for w in windows))
              for f,ds in doses.items() for d in ds}
    return dict(bank=bank, layout=layout, source_release=SOL_RELEASE.name, condition_slots=SLOTS,
                tolerance_percentage_points=tolerance, windows=windows, counts=counts)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--bank', choices=('prepared','from-scratch'), default='prepared')
    cli.add_argument('--layout', choices=('current','keep','balance'), default='current')
    cli.add_argument('--shifts', type=Path, default=DEFAULT_SHIFTS)
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--report', type=Path, help='Write a window-by-window HTML dose review')
    args = cli.parse_args()
    draft = build(args.layout, args.shifts, args.bank)
    save(args.output, draft)
    if args.report:
        from evaluation.scripts.pipeline.report_window_doses import write_report
        write_report(draft, args.report)
    print(args.bank, args.layout, len(draft['windows']), draft['counts'])


if __name__ == '__main__':
    main()
