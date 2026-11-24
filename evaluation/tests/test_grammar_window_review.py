"""Bind grammar review to displayed text without sending QA or changing passages."""
import copy
import json

import pytest

from evaluation.scripts.pipeline import review_grammar_windows as audit
from evaluation.scripts.variants.current import create_grammar_variants as g


def test_individual_review_preserves_other_displayed_edits():
    clean = '甲向老师道谢。乙把书放下。'
    shown = '甲向道谢老师。乙书放下把。'
    window = {'conditions': {
        'clean': {'verses': {'1:1': clean}},
        'grammar30': {'verses': {'1:1': shown}, 'edits': [
            {'verse': '1:1', 'start': 0, 'before': clean[:7], 'after': shown[:7]},
            {'verse': '1:1', 'start': 7, 'before': clean[7:], 'after': shown[7:]},
        ]},
    }}
    requests, combined = audit.edit_requests(window)
    displayed = audit.render_passage({'1:1': shown})[0]
    for unit in requests:
        assert g.meaning_reader_request(unit['request'])['passage'] == displayed
    assert requests[0]['request']['original_passage'].endswith('乙书放下把。\n')
    assert requests[1]['request']['original_passage'].startswith('1:1　甲向道谢老师。')
    assert combined['original_passage'] == '1:1　' + clean + '\n'
    assert g.meaning_reader_request(combined)['passage'] == displayed


@pytest.mark.parametrize('all_active,expected', [(False, (8, 24)), (True, (65, 184))])
def test_selected_edits_use_exact_current_windows_without_qa(all_active, expected):
    raw = audit.MANIFEST.read_bytes()
    manifest = json.loads(raw)
    windows = audit.select_windows(manifest, all_active)
    assert not set(w['id'] for w in windows) & set(manifest['held_for_review'])
    total = 0
    for window in windows:
        snapshot = copy.deepcopy(window)
        units, combined = audit.edit_requests(window)
        displayed = audit.render_passage(window['conditions']['grammar30']['verses'])[0]
        for request in [*(u['request'] for u in units), combined]:
            assert set(request) == {'original_passage', 'clause_start', 'original_clause',
                                    'edited_clause', 'review_scope'}
            assert g.meaning_reader_request(request)['passage'] == displayed
            assert g.valid_structural_candidate(request['original_clause'], request['edited_clause'], [g.LLM_OPERATION])
        assert window == snapshot
        total += len(units)
    assert (len(windows), total) == expected
    assert audit.MANIFEST.read_bytes() == raw


def test_corrupt_offset_stops_before_any_review_call():
    window = next(w for w in audit.read(audit.MANIFEST)['windows'] if w['passage_id'] == 't1_1kgs13')
    window['conditions']['grammar30']['edits'][0]['start'] += 1
    with pytest.raises(ValueError, match='does not match displayed window'):
        audit.edit_requests(window)


def test_unrecorded_changes_stop_before_review():
    window = next(w for w in audit.read(audit.MANIFEST)['windows'] if w['passage_id'] == 't1_1kgs13')
    verse = window['verses'][0]
    window['conditions']['grammar30']['verses'][verse] += '遗漏的变化'
    with pytest.raises(ValueError, match='unrecorded grammar changes'):
        audit.edit_requests(window)


def test_wrong_bank_size_stops_before_review():
    manifest = audit.read(audit.MANIFEST)
    manifest['held_for_review'] = []
    with pytest.raises(ValueError, match='Expected'):
        audit.select_windows(manifest, all_active=True)


def test_report_includes_all_edits_and_complete_window_findings(tmp_path):
    data = audit.read(audit.DEFAULT_RUN / 'results.json')
    path = tmp_path / 'report.html'
    audit.render_report(data, path)
    html = path.read_text()
    assert html.count('data-status="pass"') == 24
    assert html.count('Combined-window findings') == 8
    assert 'Complete-window comparisons' in html
    assert 'status-filter' in html
