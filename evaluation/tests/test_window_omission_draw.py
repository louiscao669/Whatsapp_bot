from itertools import combinations

from evaluation.scripts.pipeline.build_prepared_window_conditions import Edit
from evaluation.scripts.pipeline.draw_window_omissions import high_options, low_options, mask_for_edits


def test_nested_draw_enumerates_all_and_only_eligible_combinations():
    weights = [15, 6, 7, 8, 9, 10, 11, 12, 22]
    verses = ['1', '2', '2', '2', '2', '3', '3', '3', '3']
    clauses = [Edit(v, 0, '甲' * w, '') for v, w in zip(verses, weights)]
    eligible_low, eligible_high = {}, {}
    for size in range(len(clauses) + 1):
        for members in combinations(range(len(clauses)), size):
            if {v for i, v in enumerate(verses) if i not in members} != set(verses):
                continue
            mask = sum(1 << i for i in members)
            weight = sum(weights[i] for i in members)
            if 13 <= weight <= 17:
                eligible_low[mask] = set(members)
            if 28 <= weight <= 32:
                eligible_high[mask] = set(members)
    nested = {mask: {low for low, subset in eligible_low.items() if subset <= members}
              for mask, members in eligible_high.items()}
    expected = {mask for mask, subsets in nested.items() if subsets}
    found = list(high_options(clauses, 100, 2))
    assert len(expected) > 1
    assert sorted(found) == sorted(expected)
    for mask in found:
        assert set(low_options(clauses, mask, 100, 2)) == nested[mask]


def test_shared_clause_requires_overlapping_content_in_the_same_verse():
    clauses = [Edit('1', 0, '甲，', ''), Edit('1', 2, '乙。', ''), Edit('2', 0, '丙。', '')]
    edits = [dict(verse='1', start=1, before='，乙')]
    assert mask_for_edits(clauses, edits) == 2
