"""Draft the Sol prepared pilot conditions at the dose assigned to each displayed excerpt."""
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
from eten_shared.experiment_plan import SLOTS
from pilot_import_reviewed122 import SOL_RELEASE, SOL_SET, checked_json, load_bank

FAMILIES = ('omission', 'mistranslation', 'grammar')
MARKER = re.compile(r'(?m)^\d+[ \t]+')
DEFAULT_SHIFTS = ROOT / 'evaluation/runs/sol_prepared_window_shift_audit_2026-11-12/shifts.json'


@dataclass(frozen=True)
class Edit:
    verse: str
    start: int
    before: str
    after: str


def passage_edits(pack, directory, excluded):
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
    for family, units in [('grammar', grammar_units), ('omission', omission.passage_units(text))]:
        cursor = 0
        for i, unit in enumerate(units):
            raw = unit['text']
            if family == 'grammar' and i in grammar_entries:
                entry = grammar_entries[i]
                edit = local(cursor, entry['original_text'], entry['corrupted_text'])
            elif family == 'omission' and unit['omittable'] and unit['content_chars']:
                edit = local(cursor, raw, '')
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
    return by_family


def choose(groups, clean, doses, tolerance, protect_verses):
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
        for sign in (1, -1):
            values = row()
            values[selection] = sign * 100 * weights
            values[errors + j] = -1
            limit(values, sign * dose * total)
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


def build(layout, shifts_file):
    prepared = [q for q in load_bank(SOL_SET) if q['source'] == 'Prepared60']
    moves = {}
    if layout != 'current':
        shifts = read(shifts_file)['shifts']
        moving = [s for s in shifts if layout in s['plans']]
        moves = {s['id']: s for s in moving}
        if not moves or len(moves) != len(moving) or moves.keys() - {q['id'] for q in prepared}:
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
    for pid in sorted({q['passage_id'] for q in prepared}):
        pack = checked_json(SOL_RELEASE / f'{pid}.json', manifest['files'][f'{pid}.json'])
        pool = passage_edits(pack, RUN / 'release' / pid, excluded)
        source = pack['conditions']['clean']['verses']
        seen = set()
        for q in (q for q in prepared if q['passage_id'] == pid):
            labels = list(q['verses'])
            if q['verses'] != {v:source[v] for v in labels}:
                raise ValueError(f'Stale clean wording for {q["id"]}')
            if q['id'] in moves:
                move = moves[q['id']]
                if move['old'] != labels:
                    raise ValueError(f'Stale window proposal for {q["id"]}')
                labels = move['new']
            idx = list(source).index(labels[0])
            if len(labels) != 3 or list(source)[idx:idx+3] != labels or seen.intersection(labels):
                raise ValueError(f'Expected disjoint three-verse prepared windows in {pid}')
            seen.update(labels)
            clean = {v:source[v] for v in labels}
            total = sum(map(mis.content_len, clean.values()))
            cells = {'clean': {'verses':clean}, 'wbw': {'verses':{
                v:pack['conditions']['wbw']['verses'][v] for v in labels}}}
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
                    text = render(clean, edits)
                    if family == 'omission' and total - sum(map(mis.content_len, text.values())) != affected:
                        raise ValueError('Rendered omission differs from the selected dose')
                    if status == 'within_target' and text == clean:
                        raise ValueError('Window has no visible defect')
                    cell = dict(status=status, target_percent=dose,
                        actual_percent=100*affected/total, affected_chars=affected, selected_ids=ids,
                        edits=[asdict(e) for e in edits], verses=text)
                    if status == 'held':
                        cell['reason'] = ('Insufficient eligible edit coverage in this excerpt.'
                                          if 100*available < (dose-tolerance)*total else
                                          'Available edit sizes do not fit the band in the nested plan.')
                    cells[family+str(dose)] = cell
            windows.append(dict(id=q['id'], passage_id=pid, verses=labels, question=q['question'],
                        reference=pack['reference'].rsplit(' ',1)[0]+' '+labels[0]+'–'+labels[-1],
                        clean_content_chars=total, conditions=cells))
    counts = {f+str(d):dict(Counter(w['conditions'][f+str(d)]['status'] for w in windows))
              for f,ds in doses.items() for d in ds}
    return dict(layout=layout, source_release=SOL_RELEASE.name, condition_slots=SLOTS,
                tolerance_percentage_points=tolerance, windows=windows, counts=counts)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--layout', choices=('current','keep','balance'), default='current')
    cli.add_argument('--shifts', type=Path, default=DEFAULT_SHIFTS)
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    draft = build(args.layout, args.shifts)
    save(args.output, draft)
    print(args.layout, len(draft['windows']), draft['counts'])


if __name__ == '__main__':
    main()
