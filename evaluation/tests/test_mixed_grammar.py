"""Mixed grammar contracts. Synthetic approvals test logic, not Chinese validity."""
import json

import pytest

from evaluation.scripts.pipeline import build_mixed_grammar_windows as b
from evaluation.scripts.variants.current import mixed_grammar as m
from evaluation.scripts.variants.current import create_grammar_variants as g


def candidate(subtype='word_form', start=0, chars=10, status='pass'):
    return dict(verse='1:1', start=start, content_chars=chars, subtype=subtype, status=status)


def evidence(text, category='yes', semantic='preserved', grammar='yes'):
    return ({**{k: 'yes' for k in g.JUDGMENT_FIELDS}, 'grammar_worsened': grammar,
             'category_fits': category, 'error_span': text, 'explanation': 'Synthetic grammar judgment.'},
            {'candidate_reading': {'processing_difficulty': 'high', 'first_read_grammar': 'obvious',
              'first_read_span': text, 'primary_reading': 'Synthetic reading.', 'participant_roles': 'Roles.',
              'event_structure': 'Event.', 'modifier_scope': 'Scope.', 'interpretation_status': 'clear',
              'alternative_readings': []},
             'judgment': {**{k: 'yes' for k in g.MEANING_FIELDS}, 'semantic_status': semantic,
              'risk_spans': [text] if semantic != 'preserved' else [], 'explanation': 'Synthetic comparison.'}})


@pytest.mark.parametrize('before,after,subtype', [
    ('请你进来。', '请你的进来。', 'word_form'),
    ('他很勇敢。', '他很勇气。', 'word_form'),
    ('三把刀。', '三匹刀。', 'classifier_selection'),
    ('他带着兵器。', '他兵器带作战的着。', 'word_form'),
    ('他正在走路。', '他正在了走路。', 'verb_aspect_construction'),
    ('六百名但人带着作战的兵器，', '六百名但人兵器带作战的着，', 'misordering'),
])
def test_mechanical_gate_does_not_claim_semantic_approval(before, after, subtype):
    assert m.hard_failures(before, after, subtype) == []


@pytest.mark.parametrize('before,after,subtype,names,reason', [
    ('请你进来。', '请他进来。', 'word_form', [], 'participant_or_plural_marker_changed'),
    ('三把刀。', '四匹刀。', 'classifier_selection', [], 'number_changed'),
    ('他不来。', '他来。', 'word_form', [], 'negation_changed'),
    ('大卫来。', '大卫的来。', 'word_form', ['大卫来'], 'protected_name_changed'),
    ('他跑得快。', '他跑的快。', 'word_form', [], 'excluded_de_particle_substitution'),
    ('他来。', '他来了。', 'misordering', [], 'misordering_changed_character_inventory'),
    ('他来。', '他来！', 'word_form', [], 'punctuation_or_whitespace_changed'),
])
def test_hard_gates(before, after, subtype, names, reason):
    assert reason in m.hard_failures(before, after, subtype, names)


def test_operation_is_not_confused_with_error_family():
    assert m.edit_operations('你', '你的')[0]['operation'] == 'addition'
    assert m.edit_operations('跑得快', '跑快')[0]['operation'] == 'deletion'
    assert m.edit_operations('三把刀', '三匹刀')[0]['operation'] == 'substitution'


def test_variable_length_edits_keep_clean_offsets_and_reject_overlap():
    clean = {'1:1': '请你进来。三把刀。'}
    edits = [dict(verse='1:1', start=0, before='请你进来。', after='请你的进来。'),
             dict(verse='1:1', start=5, before='三把刀。', after='三匹刀。')]
    assert m.apply_candidates(clean, edits) == {'1:1': '请你的进来。三匹刀。'}
    assert clean['1:1'] == '请你进来。三把刀。'
    with pytest.raises(g.GrammarError, match='Overlapping or stale'):
        m.apply_candidates(clean, edits + [edits[0]])
    with pytest.raises(g.GrammarError, match='Unknown verse'):
        m.apply_candidates(clean, [dict(edits[0], verse='1:2')])


@pytest.mark.parametrize('category,semantic,grammar,status', [
    ('yes', 'preserved', 'yes', 'pass'), ('no', 'preserved', 'yes', 'needs_repair'),
    ('uncertain', 'preserved', 'yes', 'flagged'), ('yes', 'changed', 'yes', 'needs_repair'),
    ('yes', 'new_ambiguity', 'yes', 'flagged'), ('yes', 'preserved', 'no', 'needs_repair')])
def test_three_way_review(category, semantic, grammar, status):
    j, meaning = evidence('请你的进来。', category, semantic, grammar)
    assert m.outcome(j, meaning, '请你的进来。') == status


def test_selection_never_uses_flags_or_counts_same_clause_twice():
    pool = [candidate(chars=30), candidate('classifier_selection', chars=30),
            candidate('misordering', start=40, chars=30, status='flagged'),
            candidate('verb_aspect_construction', start=80, chars=30, status='needs_repair')]
    r = m.choose_candidates(pool, 100, tolerance_pp=0)
    assert r['target_met'] and len(r['selected']) == 1 and r['affected_chars'] == 30
    assert r['selected'][0]['status'] == 'pass'
    assert not m.choose_candidates(pool, 100, rate=.6, tolerance_pp=0)['target_met']


def test_mix_is_soft_preference_and_never_overrides_dose():
    pool = [candidate(chars=20), candidate('misordering', start=30, chars=30)]
    r = m.choose_candidates(pool, 100, tolerance_pp=0, misselection_share=1)
    assert r['actual_percent'] == 30 and r['misselection_share'] == 0
    pool += [candidate('word_form', start=30, chars=30)]
    assert m.choose_candidates(pool, 100, tolerance_pp=0, misselection_share=1)['misselection_share'] == 1


def test_all_eight_source_windows_map_existing_candidates_exactly():
    windows = [w for w in b.read(b.audit.MANIFEST)['windows'] if w['passage_id'] == 't1_1kgs13']
    assert len(windows) == 8
    count = 0
    for w in windows:
        units = m.clauses(w)
        assert sum(u['content_chars'] for u in units) == w['clean_content_chars']
        for u in units:
            assert w['conditions']['clean']['verses'][u['verse']][u['start']:u['start'] + len(u['text'])] == u['text']
        cs = b.candidates_from_proposals(w, units, {'candidates': []}, 'test')
        count += len(cs)
        assert m.apply_candidates(w['conditions']['clean']['verses'], cs) == w['conditions']['grammar30']['verses']
    assert count == 24


def test_all_active_legacy_edits_reconstruct_exactly_with_whole_clause_doses():
    manifest = b.read(b.audit.MANIFEST)
    windows = [w for w in manifest['windows'] if w['id'] not in manifest.get('held_for_review', [])]
    expanded = []
    assert len(windows) == 65
    for w in windows:
        units = m.clauses(w)
        cs = b.candidates_from_proposals(w, units, {'candidates': []}, 'preflight')
        assert m.apply_candidates(w['conditions']['clean']['verses'], cs) == w['conditions']['grammar30']['verses']
        for c in cs:
            assert any((c['verse'], c['start'], c['before'], c['content_chars']) ==
                       (u['verse'], u['start'], u['text'], u['content_chars']) for u in units)
            if c.get('dose_unit_expanded_to_enclosing_clause'):expanded.append((w, c))
    assert len(expanded) == 1
    w, c = expanded[0]
    assert w['id'] == 'acts_23_12-35/v25-26:1'
    assert c['before'] == '他又写了以下这封信：'
    assert c['after'] == '他又以下这封写了信：'
    assert c['content_chars'] == 9 and g.content_len(c['imported_edit']['before']) == 7
    assert not m.choose_candidates([dict(c, status='pass')], w['clean_content_chars'])['target_met']


def test_legacy_partial_edit_with_stale_source_is_rejected_before_generation():
    w = {'conditions': {'clean': {'verses': {'1:1': '他又写了这封信：'}},
                       'grammar30': {'edits': [dict(verse='1:1', start=2, before='写了那封信', after='那封写了信')]}}}
    with pytest.raises(g.GrammarError, match='stale source'):
        b.candidates_from_proposals(w, m.clauses(w), {'candidates': []}, 'preflight')


def proposal_request():
    return {'clauses': [{'unit_index': 0, 'text': '请你进来。'}], 'max_per_class': 2}


def proposals():
    return {'candidates': [{'unit_index': 0, 'original_clause': '请你进来。', 'edited_clause': '请你的进来。',
                           'subtype': 'word_form', 'explanation': 'Synthetic proposal.'}],
            'unavailable_classes': [{'subtype': t, 'reason': 'No safe opportunity.'} for t in m.MISSELECTION[1:]]}


@pytest.mark.parametrize('mutation', ['source', 'duplicate', 'missing_class', 'wrong_list'])
def test_bad_proposals_cannot_enter_review(mutation):
    data = proposals()
    if mutation == 'source': data['candidates'][0]['original_clause'] = '请他进来。'
    if mutation == 'duplicate': data['candidates'] *= 2
    if mutation == 'missing_class': data['unavailable_classes'] = []
    if mutation == 'wrong_list': data['candidates'] = None
    with pytest.raises(g.GrammarError): m.validate_proposals(data, proposal_request())


def test_cache_is_exact_and_offline_miss_never_sends(tmp_path):
    class Client:
        calls = 0
        def request_json(self, request, **kwargs):
            self.calls += 1
            return proposals()
    client = Client();path = tmp_path / 'cache.json'
    def cache(prompt='prompt', offline=False):
        return m.StructuredCache(path, 'test-model', prompt, m.WRITER_SCHEMA, 'writer', 1000, offline, client)
    first = cache().call(proposal_request())
    assert cache(offline=True).call(proposal_request()) == first
    with pytest.raises(g.GrammarError, match='offline'): cache('new prompt', True).call(proposal_request())
    assert client.calls == 1


@pytest.mark.parametrize('combined_status', ['preserved', 'new_ambiguity', 'changed'])
def test_window_review_controls_eligibility_without_qa_leak(tmp_path, monkeypatch, combined_status):
    window = {'id': 'test/v1:1', 'passage_id': 'test', 'verses': ['1:1'], 'clean_content_chars': 13,
              'question': 'SECRET_Q', 'answer_evidence': 'SECRET_A',
              'conditions': {'clean': {'verses': {'1:1': '请你进来。他拿三把刀。他独自走。'}}, 'grammar30': {'edits': []}}}
    monkeypatch.setattr(b.audit, 'reference', lambda w: 'Synthetic 1:1')
    def call(self, request):
        assert 'SECRET' not in json.dumps(request)
        if self.role == 'word_class_writer':
            assert set(request) == {'clean_passage', 'clauses', 'protected_names', 'max_candidates'}
            return 'word-class', {'candidates': [], 'unavailable_reason': 'No safe lexical substitution in this synthetic fixture.'}
        if self.role == 'writer':
            assert set(request) == {'clean_passage', 'clauses', 'protected_names', 'max_per_class'}
            return 'proposal', proposals()
        return 'judge', evidence(request['edited_clause'])[0]
    def meaning(self, request):
        status = combined_status if request['review_scope'] == 'complete_displayed_window' else 'preserved'
        return 'meaning', evidence(request['edited_clause'], semantic=status)[1]
    monkeypatch.setattr(m.StructuredCache, 'call', call)
    monkeypatch.setattr(g.GrammarMeaningCache, 'evaluate', meaning)
    args = b.parse_args(['--output', str(tmp_path), '--offline'])
    result = b.build_window(window, tmp_path, args, {'entities': []})
    assert result['selection']['affected_chars'] == 4
    assert result['selection']['actual_percent'] == pytest.approx(400/13)
    assert result['eligible_for_publication'] == (combined_status == 'preserved')
    assert result['published'] is False
    assert result['draft']['1:1'].startswith('请你的进来。')
    assert window['conditions']['clean']['verses']['1:1'].startswith('请你进来。')


def lexical_proposal():
    return dict(unit_index=0, original_clause='他很勇敢。', edited_clause='他很勇气。',
                source_form='勇敢', target_form='勇气', source_word_class='adjective',
                target_word_class='noun', explanation='Synthetic adjective-slot test.')


def test_explicit_lexical_proposals_require_actual_word_class_metadata():
    req = dict(clauses=[dict(unit_index=0, text='他很勇敢。')], max_candidates=2)
    response = dict(candidates=[lexical_proposal()], unavailable_reason='')
    assert m.validate_word_class_proposals(response, req) == response
    p = lexical_proposal()
    transition = {k: p[k] for k in ('source_form', 'target_form', 'source_word_class', 'target_word_class')}
    assert m.word_class_failures(p['original_clause'], p['edited_clause'], transition) == []
    response['unavailable_reason'] = 'No opportunity.'
    with pytest.raises(g.GrammarError, match='availability'):m.validate_word_class_proposals(response, req)


@pytest.mark.parametrize('before,after,transition,reason', [
    ('请你进来。', '请你的进来。', dict(source_form='你', target_form='你的', source_word_class='noun', target_word_class='adjective'),
     'marker_only_edit_is_not_lexical_word_class'),
    ('他很勇敢。', '他很胆大。', dict(source_form='勇敢', target_form='胆大', source_word_class='adjective', target_word_class='adjective'),
     'no_claimed_word_class_transition'),
    ('他很勇敢。', '他很勇气了。', dict(source_form='勇敢', target_form='勇气', source_word_class='adjective', target_word_class='noun'),
     'word_class_replacement_span_mismatch')])
def test_lexical_slots_cannot_be_filled_by_marker_edits_or_mismatched_spans(before, after, transition, reason):
    assert reason in m.word_class_failures(before, after, transition)


def test_selection_prefers_passing_lexical_diversity_without_overriding_gates():
    marker = candidate(chars=30)
    lexical = dict(candidate(chars=30, start=40), word_form_mechanism='lexical_word_class')
    assert m.choose_candidates([marker, lexical], 100, tolerance_pp=0)['selected'] == [lexical]
    for update in [dict(status='flagged'), dict(content_chars=40)]:
        assert m.choose_candidates([marker, dict(lexical, **update)], 100, tolerance_pp=0)['selected'] == [marker]


def test_cache_reuse_copies_records_without_overwriting_conflicts(tmp_path):
    old = tmp_path / 'old';new = tmp_path / 'new'
    data = dict(schema_version=1, records={'key': {'request': 'same', 'response': 'same'}})
    m.save(old / 'grammar_reviews.json', data)
    b.reuse_review_caches(old, new)
    assert b.read(new / 'grammar_reviews.json') == data
    data['records']['key']['response'] = 'different'
    m.save(new / 'grammar_reviews.json', data)
    with pytest.raises(g.GrammarError, match='Conflicting'):b.reuse_review_caches(old, new)


def test_lexical_proposal_receives_specialist_review_and_semantic_veto(tmp_path, monkeypatch):
    # The fake reviewer proves routing and vetoes; it is not a language judgment.
    window = {'id': 'test/v1:1', 'passage_id': 'test', 'verses': ['1:1'], 'clean_content_chars': 13,
              'question': 'SECRET_Q', 'answer_evidence': 'SECRET_A',
              'conditions': {'clean': {'verses': {'1:1': '他很勇敢。他拿三把刀。他独自走。'}}, 'grammar30': {'edits': []}}}
    monkeypatch.setattr(b.audit, 'reference', lambda w: 'Synthetic 1:1')
    seen = []
    def call(self, req):
        assert 'SECRET' not in json.dumps(req)
        if self.role == 'writer':
            return 'base', {'candidates': [], 'unavailable_classes': [{'subtype': t, 'reason': 'Synthetic empty base.'} for t in m.MISSELECTION]}
        if self.role == 'word_class_writer':
            return 'lexical', {'candidates': [lexical_proposal()], 'unavailable_reason': ''}
        assert self.prompt == m.WORD_CLASS_JUDGE_PROMPT
        assert req['word_form_mechanism'] == 'lexical_word_class'
        assert req['word_class_transition']['source_form'] == '勇敢'
        seen.append(req)
        return 'judge', evidence(req['edited_clause'])[0]
    monkeypatch.setattr(m.StructuredCache, 'call', call)
    monkeypatch.setattr(g.GrammarMeaningCache, 'evaluate', lambda self, req: ('meaning', evidence(req['edited_clause'], semantic='changed')[1]))
    args = b.parse_args(['--output', str(tmp_path), '--offline'])
    r = b.build_window(window, tmp_path, args, {'entities': []})
    assert len(seen) == 1 and r['candidates'][0]['status'] == 'needs_repair'
    assert not r['selected_ids'] and not r['eligible_for_publication']
