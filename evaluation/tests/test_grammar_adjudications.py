"""User rejections must override saved model approvals without changing evidence."""
from copy import deepcopy
from collections import Counter
import pytest

from evaluation.scripts.variants.current import grammar_adjudications as a
from evaluation.scripts.variants.current import grammar_source_spans as s
from evaluation.scripts.variants.current import mixed_grammar as m
from evaluation.scripts.variants.current import mixed_grammar_ladder as l
from evaluation.scripts.pipeline import build_mixed_grammar_windows as b


def rejected_edit(decision=None):
    d = decision or a.DECISIONS[0]
    subtype = 'misordering' if Counter(d['before']) == Counter(d['after']) else 'word_form'
    return s.annotate(dict(before=d['before'], after=d['after'], status='pass',
        subtype=subtype, verse='13:24', start=0,
        content_chars=m.g.content_len(d['before']), grammar={'evidence': 'original'}))


@pytest.mark.parametrize('decision', a.DECISIONS, ids=lambda d: d['id'])
def test_rejection_preserves_raw_verdict_and_does_not_mutate_or_rewrite(decision):
    old = rejected_edit(decision); snapshot = deepcopy(old)
    new = a.apply_candidate(old)
    assert old == snapshot
    assert new['status'] == 'needs_repair' and new['model_status'] == 'pass'
    assert new['grammar'] == old['grammar']
    assert new['after'] == old['after']
    assert new['manual_adjudications'][0]['manual_wording'] is False
    assert a.apply_candidate(new) == new


def test_same_phrase_in_a_different_source_is_not_automatically_rejected():
    assert not a.decisions_for(dict(before='他们发现一具狮子尸体。', after='他们一具狮子尸体发现。'))
    assert not a.decisions_for(dict(before=a.DECISIONS[0]['before'], after='驴和狮子都在尸体旁边站着。'))


@pytest.mark.parametrize('decision', a.DECISIONS, ids=lambda d: d['id'])
def test_all_selectors_block_stale_pass_even_before_status_is_updated(decision):
    old = rejected_edit(decision)
    assert old['status'] == 'pass'
    assert not m.choose_candidates([old], 100)['target_met']
    for basis in ('whole_clause', 'source_spans'):
        assert not l.combinations([old], 100, .15, 20, dose_basis=basis)


@pytest.mark.parametrize('decision', a.DECISIONS, ids=lambda d: d['id'])
def test_live_review_applies_manual_rejection_to_edit_and_complete_window(monkeypatch, decision):
    class Judge:
        def call(self, request): return 'grammar-id', {'explanation': 'unaltered'}
    class Meanings:
        def evaluate(self, request): return 'meaning-id', {'judgment': {'explanation': 'unaltered'}}
    monkeypatch.setattr(m, 'outcome', lambda *args: 'pass')
    edit = rejected_edit(decision)
    for request in (
        dict(original_clause=edit['before'], edited_clause=edit['after']),
        dict(original_clause='whole source', edited_clause='whole draft', selected_edits=[edit]),
    ):
        result = b.review(request, Judge(), Meanings())
        assert result['model_status'] == 'pass'
        assert result['status'] == 'needs_repair'
        assert result['grammar_review_id'] == 'grammar-id'
        assert 'Rejected by user' in b.reasons(result)
