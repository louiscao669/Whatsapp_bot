"""Joint family balancing across windows with explicit, versioned dose bases."""
from collections import Counter, defaultdict
import random

from evaluation.scripts.variants.current import mixed_grammar as m
from evaluation.scripts.variants.current import create_grammar_variants as g
from evaluation.scripts.variants.current import grammar_source_spans as spans

POLICY = 'mixed_grammar_joint_window_mix_v1'


def combinations(candidates, total_chars, rate, tolerance_pp=2, seed=2026, *, dose_basis='whole_clause'):
    """Best dose-fit combination for each attainable (misselection, total) count.

    Every selected clause is counted once. Held candidates never participate.
    Seeded ties avoid always selecting the earliest source clause. No random
    sampling claim is made: family balance and dose fit take precedence.
    """
    if total_chars <= 0 or not 0 < rate <= 1 or tolerance_pp < 0 or dose_basis not in ('whole_clause', 'source_spans'):
        raise ValueError('Invalid dose')
    if dose_basis == 'source_spans':
        return span_combinations(candidates, total_chars, rate, tolerance_pp, seed)
    groups = defaultdict(list)
    for c in candidates:
        if m.adjudications.eligible(c):
            groups[(c['verse'], c['start'])].append(c)
    groups = list(groups.values())
    rng = random.Random(seed)
    rng.shuffle(groups)
    for group in groups:
        rng.shuffle(group)
    best = {}; visited = 0

    def visit(i, selected, chars):
        nonlocal visited
        visited += 1
        if visited > 1000000:
            raise g.GrammarError('Ladder selection search bound exceeded')
        if chars / total_chars > rate + tolerance_pp / 100 + 1e-9:
            return
        if i < len(groups):
            visit(i + 1, selected, chars)
            for c in groups[i]:
                visit(i + 1, selected + [c], chars + c['content_chars'])
            return
        if not selected or abs(chars / total_chars - rate) > tolerance_pp / 100 + 1e-9:
            return
        count = sum(c['subtype'] in m.MISSELECTION for c in selected)
        key = count, len(selected)
        score = (abs(chars / total_chars - rate), rng.random())
        if key not in best or score < best[key][0]:
            best[key] = (score, dict(selected=selected, affected_chars=chars,
                actual_percent=100 * chars / total_chars, target_percent=100 * rate,
                misselection_count=count, edit_count=len(selected),
                misselection_share=count / len(selected),
                subtype_counts=dict(Counter(c['subtype'] for c in selected)),
                dose_deviation_pp=100 * score[0], target_met=True))

    visit(0, [], 0)
    return [value[1] for _, value in sorted(best.items())]


def span_combinations(candidates, total_chars, rate, tolerance_pp, seed):
    """One reviewed candidate per clause; dose uses only its source footprint.

    DP retains each attainable (source chars, family count, edit count) state;
    broadening a candidate bank cannot cause exponential subset enumeration.
    """
    groups = defaultdict(list); rng = random.Random(seed)
    for c in candidates:
        if not m.adjudications.eligible(c): continue
        spans.selection_footprint([c])
        groups[(c['verse'], c['start'])].append(c)
    groups = list(groups.values()); rng.shuffle(groups)
    states = {(0, 0, 0): ([], 0.)}
    upper = (rate + tolerance_pp / 100) * total_chars
    for group in groups:
        rng.shuffle(group); new = dict(states)
        for (chars, ms, n), (selected, _) in states.items():
            for c in group:
                count = chars + c['dose_content_chars']
                if count > upper + 1e-9: continue
                key = count, ms + (c['subtype'] in m.MISSELECTION), n + 1
                tie = rng.random()
                if key not in new or tie < new[key][1]: new[key] = (selected + [c], tie)
        states = new
    best = {}
    for (chars, ms, n), (selected, tie) in states.items():
        if not n or abs(chars / total_chars - rate) > tolerance_pp / 100 + 1e-9: continue
        score = abs(chars / total_chars - rate), tie
        if (ms, n) in best and best[(ms, n)][0] <= score: continue
        union = spans.selection_footprint(selected)
        if union['affected_chars'] != chars:
            raise g.GrammarError('Overlapping source footprints in clause-exclusive selection')
        best[(ms, n)] = (score, dict(selected=selected, affected_chars=chars,
            actual_percent=100 * chars / total_chars, target_percent=100 * rate,
            misselection_count=ms, edit_count=n, misselection_share=ms / n,
            subtype_counts=dict(Counter(c['subtype'] for c in selected)),
            dose_deviation_pp=100 * score[0], target_met=True,
            dose_basis=spans.DOSE_BASIS, source_span_policy=spans.POLICY,
            affected_source_positions=union['source_positions']))
    return [v[1] for _, v in sorted(best.items())]


def balance_windows(options_by_window, share=.3, seed=2026, *, dose_basis='whole_clause'):
    """Closest pooled ratio among all dose-feasible windows, then dose accuracy.

    Never drop a feasible window to improve a mixture. This is per dose, not
    pooled over repeated appearances of the same candidate across six doses.
    """
    if not 0 <= share <= 1:
        raise ValueError('Invalid mixture')
    rng = random.Random(seed)
    states = {(0, 0): (0., {}, 0.)}
    unavailable = []
    for window_id, options in options_by_window.items():
        if not options:
            unavailable.append(window_id)
            continue
        new = {}
        for (ms, n), (cost, choices, _) in states.items():
            for option in options:
                key = ms + option['misselection_count'], n + option['edit_count']
                score = cost + option['dose_deviation_pp'], rng.random()
                old = new.get(key)
                if old is None or score < (old[0], old[2]):
                    new[key] = (score[0], {**choices, window_id: option}, score[1])
        states = new
    key, (_, choices, _) = min(states.items(), key=lambda pair: (
        abs(pair[0][0] / pair[0][1] - share) if pair[0][1] else 1,
        pair[1][0], pair[0][1], pair[1][2]))
    ms, n = key
    return dict(choices=choices, unavailable=unavailable,
                requested_misselection_share=share,
                actual_misselection_share=ms / n if n else None,
                misselection_count=ms, misordering_count=n - ms, edit_count=n,
                mixture_basis='selected_primary_error_instances_across_windows_at_each_dose',
                dose_basis=spans.DOSE_BASIS if dose_basis == 'source_spans' else 'clean_content_characters_in_selected_whole_clauses')
