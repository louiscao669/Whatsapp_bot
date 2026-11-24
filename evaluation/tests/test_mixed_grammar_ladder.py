"""Dose and pooled family constraints; synthetic candidates are not language evidence."""
import pytest

from evaluation.scripts.variants.current import mixed_grammar_ladder as l
from evaluation.scripts.pipeline import build_mixed_grammar_ladder as b
from evaluation.scripts.variants.current import create_grammar_variants as g


def c(subtype, start=0, chars=5, status='pass'):
    return dict(subtype=subtype, verse='1:1', start=start, content_chars=chars, status=status)


def test_low_dose_balances_across_windows_without_requiring_two_edits_per_window():
    options = l.combinations([c('word_form'), c('misordering')], 100, .05, tolerance_pp=0)
    result = l.balance_windows({str(i): options for i in range(10)}, .3)
    assert result['misselection_count'] == 3
    assert result['misordering_count'] == 7
    assert all(v['edit_count'] == 1 and v['actual_percent'] == 5 for v in result['choices'].values())


def test_never_drop_feasible_window_or_use_held_candidate_for_ratio():
    only_ms = l.combinations([c('word_form'), c('misordering', status='flagged')], 100, .05, 0)
    either = l.combinations([c('word_form'), c('misordering')], 100, .05, 0)
    result = l.balance_windows({'a': only_ms, 'b': only_ms, 'c': either, 'd': []}, .3)
    assert set(result['choices']) == {'a', 'b', 'c'}
    assert result['unavailable'] == ['d']
    assert result['misselection_count'] == 2 and result['misordering_count'] == 1


def test_whole_clause_dose_cannot_be_relaxed_or_double_counted():
    assert l.combinations([c('word_form', chars=8)], 100, .05, 2) == []
    assert l.combinations([c('word_form'), c('misordering')], 100, .10, 0) == []
    choices = l.combinations([c('word_form'), c('misordering', start=10)], 100, .10, 0)
    assert len(choices) == 1 and choices[0]['affected_chars'] == 10


def test_seed_replay_and_dose_fit_after_ratio():
    options = l.combinations([c('word_form'), c('misordering'), c('misordering', 20, 6)], 100, .05, 2)
    assert all(o['actual_percent'] == 5 for o in options)
    a = l.balance_windows({str(i): options for i in range(8)}, .3, 123)
    assert a == l.balance_windows({str(i): options for i in range(8)}, .3, 123)
    assert a['misselection_count'] == 2 and a['misordering_count'] == 6


def test_extra_proposals_must_match_source_and_candidate_bound():
    request = dict(eligible_clauses=[dict(unit_index=1, text='他在读书。')], max_candidates=1)
    row = dict(unit_index=1, original_clause='他在读书。', edited_clause='他读书在。', explanation='Synthetic.')
    b.validate_extra(dict(candidates=[row], unavailable_reason=''), request)
    with pytest.raises(g.GrammarError, match='source mismatch'):
        b.validate_extra(dict(candidates=[dict(row, original_clause='她在读书。')], unavailable_reason=''), request)
    with pytest.raises(g.GrammarError, match='bound'):
        b.validate_extra(dict(candidates=[row, row], unavailable_reason=''), request)


def test_defaults_match_authorized_trial():
    args = b.parse_args([])
    assert args.passage == 't1_1kgs13' and args.rates == [5, 10, 15, 20, 25, 30]
    assert args.misselection_share == .3 and args.tolerance_pp == 2


def test_expansion_excludes_completed_trial_and_held_officer_window():
    manifest = b.b.read(b.b.audit.MANIFEST)
    rows = b.select_windows(manifest, 'all', ['t1_1kgs13'])
    assert len(rows) == 57
    assert all(w['passage_id'] != 't1_1kgs13' for w in rows)
    assert not set(w['id'] for w in rows).intersection(manifest.get('held_for_review', []))
    assert len(b.select_windows(manifest, 't1_1kgs13')) == 8


def test_expansion_cannot_overwrite_trial_report(tmp_path):
    with pytest.raises(SystemExit):
        b.parse_args(['--passage', 'all', '--output', str(tmp_path)])
