"""Auditable clean-source footprints for grammar dose measurement.

Reordering is one atomic replacement of the smallest contiguous reordered block,
after trimming identical prefix/suffix characters. This measures a source span,
not minimum moved-token count or edit distance. Form edits use disjoint diff
spans; an insertion anchors to the nearest preceding clean content character
(following if none), so extra grammatical material is not a zero-dose edit.
"""
from collections import Counter
from difflib import SequenceMatcher

from evaluation.scripts.variants.current import create_grammar_variants as g

POLICY = 'grammar_affected_source_spans_v1'
DOSE_BASIS = 'clean_content_characters_in_affected_source_spans'


def footprint(before, after, subtype):
    if not before or before == after:
        raise g.GrammarError('Source footprint requires a changed, nonempty clause')
    intervals = []
    if subtype == 'misordering':
        if Counter(before) != Counter(after):
            raise g.GrammarError('Misordering footprint requires identical character inventory')
        left = 0; right = 0
        while left < len(before) and before[left] == after[left]: left += 1
        while right < len(before) - left and before[-right - 1] == after[-right - 1]: right += 1
        intervals.append((left, len(before) - right, 'reordered_block'))
    else:
        for tag, i, j, k, end in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
            if tag == 'equal': continue
            if i != j:
                intervals.append((i, j, 'substitution' if tag == 'replace' else 'grammatical_deletion'))
            else:
                preceding = [p for p in range(i) if g.CONTENT_CHAR_PATTERN.fullmatch(before[p])]
                following = [p for p in range(i, len(before)) if g.CONTENT_CHAR_PATTERN.fullmatch(before[p])]
                if not preceding and not following:
                    raise g.GrammarError('Insertion has no clean content-character anchor')
                anchor = preceding[-1] if preceding else following[0]
                intervals.append((anchor, anchor + 1, 'insertion_source_anchor'))
    positions = sorted({p for start, end, _ in intervals for p in range(start, end)
                        if g.CONTENT_CHAR_PATTERN.fullmatch(before[p])})
    if not positions:
        raise g.GrammarError('Grammar edit has no countable source footprint')
    return dict(policy=POLICY, dose_basis=DOSE_BASIS, content_chars=len(positions),
                content_positions=positions,
                spans=[dict(start=s, end=e, source=before[s:e], kind=kind) for s, e, kind in intervals])


def annotate(candidate):
    """Keep the reviewed clause and its ID; attach a separately versioned dose."""
    value = footprint(candidate['before'], candidate['after'], candidate['subtype'])
    return dict(candidate, dose_footprint=value, dose_content_chars=value['content_chars'])


def selection_footprint(candidates):
    """Union absolute source positions so anchors/overlaps cannot double count."""
    positions = set()
    for c in candidates:
        fresh = footprint(c['before'], c['after'], c['subtype'])
        if fresh != c['dose_footprint'] or fresh['content_chars'] != c['dose_content_chars']:
            raise g.GrammarError('Stale source-span dose metadata')
        positions.update((c['verse'], c['start'] + p) for p in fresh['content_positions'])
    return dict(affected_chars=len(positions), source_positions=[dict(verse=v, offset=p) for v, p in sorted(positions)],
                dose_basis=DOSE_BASIS, policy=POLICY)
