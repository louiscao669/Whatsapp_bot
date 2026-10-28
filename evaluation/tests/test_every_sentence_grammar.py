"""Sentence coverage, semantic filtering and resumable isolated export."""

import copy
import json

import pytest

from evaluation.scripts.variants.current import create_every_sentence_grammar as every
from evaluation.scripts.variants.current import create_grammar_variants as grammar


TEXT = '1 他带着五个人走进城里。他带着五个人走进城里！\n2 他带着五个人走进城里。'


def test_sentence_segmentation_preserves_quotes_verses_and_all_text():
    text = '标题\n1 他说：“不要惊慌！他还活着！”\n2 然后保罗上楼，\n3 擘开饼，吃了。\n'
    units = grammar.passage_units(text, unit_mode="sentence")
    assert ''.join(unit['text'] for unit in units) == text
    eligible = [unit for unit in units if unit['affectable']]
    assert len(eligible) == 4
    assert eligible[1]['text'] == '他还活着！”'
    assert eligible[2]['boundary'] == 'verse_end_fragment'
    assert [unit['verse'] for unit in eligible] == [1, 1, 2, 3]
    assert not units[0]['affectable']  # Heading is not passage content.
    assert len([u for u in grammar.passage_units('他进城。他回家。', unit_mode='sentence')
                if u['affectable']]) == 2


def fake_models(monkeypatch, *, reject_last=False):
    calls = []

    def proposer(self, request):
        assert 'complete sentence' in request['unit_instructions']
        calls.append(request)
        return {'clauses': [
            {'unit_index': unit['unit_index'], 'original_clause': unit['original_clause'],
             'candidates': [{'edited_clause': unit['original_clause'].replace('带着五个人', '五个人带着'),
                             'error_type': 'synthetic', 'explanation': 'Synthetic move.'}]}
            for unit in request['clauses']]}

    def judge(self, request):
        answer = {field: 'yes' for field in grammar.JUDGMENT_FIELDS}
        if reject_last and request['original_clause'].startswith('2 '):
            answer['meaning_preserved'] = 'no'
        return {**answer, 'error_span': request['edited_clause'], 'explanation': 'Synthetic review.'}

    monkeypatch.setattr(grammar.GPTGrammarProposer, '__call__', proposer)
    monkeypatch.setattr(grammar.GPTGrammarJudge, '__call__', judge)
    return calls


def setup(tmp_path):
    source = tmp_path / 'source/p/_base/llm_prompt_high'
    source.mkdir(parents=True)
    for filename in ('passage_target.txt', 'passage_target_decanonicalized.txt'):
        (source / filename).write_text(TEXT)
    (source / 'qa_target.json').write_text('{"unchanged": true}')
    return ['--source-root', str(tmp_path / 'source'), '--output-root', str(tmp_path / 'out'),
            '--passage-dirs', 'p', '--judge-model', 'test', '--generator-model', 'test',
            '--retry-rounds', '1', '--workers', '1']


def test_all_sentences_required_export_and_offline_resume(tmp_path, monkeypatch, fake_meaning_models):
    calls = fake_models(monkeypatch)
    args = setup(tmp_path)
    assert every.main(args) == 0
    output = tmp_path / 'out/p/grammar'
    audit = json.loads((output / 'sentence_review.json').read_text())['files']['passage_target.txt']
    assert audit['complete'] and audit['approved_sentence_units'] == audit['total_sentence_units'] == 3
    assert all(row['original'] != row['edited'] for row in audit['sentences'])
    assert (output / '100%/qa_target.json').read_text() == '{"unchanged": true}'
    assert grammar.Counter((output / '100%/passage_target.txt').read_text()) == grammar.Counter(TEXT)
    before = len(calls)
    assert every.main(args + ['--offline']) == 0
    assert len(calls) == before
    # Identical raw and decanonicalized sources reuse exactly the same reviews.
    assert len(fake_meaning_models['reading']) == 3


def test_unresolved_sentence_cannot_be_exported_as_full_coverage(tmp_path, monkeypatch, fake_meaning_models):
    fake_models(monkeypatch, reject_last=True)
    args = setup(tmp_path)
    assert every.main(args) == 1
    output = tmp_path / 'out/p/grammar'
    assert not (output / '100%').exists()
    audit = json.loads((output / 'sentence_review.json').read_text())['files']['passage_target.txt']
    assert not audit['complete'] and audit['approved_sentence_units'] == 2
    assert audit['sentences'][-1]['status'] == 'unresolved'
    assert audit['sentences'][-1]['edited'] is None
    assert (output / 'draft_passage_target.txt').exists()


def test_sentence_judge_rechecks_old_severity_rejections_without_changing_them(tmp_path, monkeypatch):
    request = {'original_passage': '但大卫疲惫不堪。', 'clause_start': 0,
               'original_clause': '但大卫疲惫不堪。', 'edited_clause': '但疲惫不堪大卫。'}
    prompts = []

    def respond(self, request, **kwargs):
        # Synthetic decisions verify prompt routing and cache isolation, not Chinese grammar.
        prompts.append(kwargs['prompt'])
        result = {field: 'yes' for field in grammar.JUDGMENT_FIELDS}
        if kwargs['prompt'] == grammar.JUDGE_PROMPT:
            result['structural_error'] = 'no'
        return {**result, 'error_span': '疲惫不堪大卫', 'explanation': 'Synthetic policy decision.'}

    monkeypatch.setattr(grammar.GPTStructuredClient, 'request_json', respond)
    path = tmp_path / 'judgments.json'
    strict = grammar.GrammarJudgmentCache(path, model='test')
    strict_id, rejected = strict.evaluate(request)
    sentence = grammar.GrammarJudgmentCache(path, model='test', unit_mode='sentence')
    sentence_id, approved = sentence.evaluate(request)
    assert not grammar.judgment_accepts(rejected, request['edited_clause'])
    assert grammar.judgment_accepts(approved, request['edited_clause'])
    assert strict_id != sentence_id
    assert prompts == [grammar.JUDGE_PROMPT, grammar.SENTENCE_JUDGE_PROMPT]
    for mode, expected in [('clause', (strict_id, rejected)), ('sentence', (sentence_id, approved))]:
        assert grammar.GrammarJudgmentCache(path, model='test', unit_mode=mode,
                                           offline=True).evaluate(request) == expected
    assert len(prompts) == 2


@pytest.mark.parametrize('failure', [None, 'grammatical', 'meaning'])
def test_single_error_export_uses_sentence_prompts_and_keeps_both_checks(
    tmp_path, monkeypatch, fake_meaning_models, failure,
):
    args = setup(tmp_path)
    source = tmp_path / 'source/p/_base/llm_prompt_high'
    for filename in ('passage_target.txt', 'passage_target_decanonicalized.txt'):
        (source / filename).write_text('1 但大卫疲惫不堪。')
    prompts = []

    def respond(self, request, **kwargs):
        prompts.append(kwargs['prompt'])
        if kwargs['role'] == 'generator':
            return {'clauses': [
                {'unit_index': unit['unit_index'], 'original_clause': unit['original_clause'],
                 'candidates': [{'edited_clause': '1 但疲惫不堪大卫。',
                                 'error_type': 'synthetic single move',
                                 'explanation': 'Synthetic fallback for pipeline testing.'}]}
                for unit in request['clauses']]}
        answer = {field: 'yes' for field in grammar.JUDGMENT_FIELDS}
        if failure == 'grammatical':
            answer['grammar_worsened'] = 'no'
        return {**answer, 'error_span': '疲惫不堪大卫', 'explanation': 'Synthetic decision.'}

    monkeypatch.setattr(grammar.GPTStructuredClient, 'request_json', respond)
    compare = grammar.GPTMeaningJudge.__call__

    def check_meaning(self, request):
        answer = compare(self, request)
        if failure == 'meaning':
            answer['event_structure_preserved'] = 'no'
        return answer

    monkeypatch.setattr(grammar.GPTMeaningJudge, '__call__', check_meaning)
    assert every.main(args) == (0 if failure is None else 1)
    output = tmp_path / 'out/p/grammar'
    assert (output / '100%/passage_target.txt').exists() == (failure is None)
    assert set(prompts) == {grammar.SENTENCE_PROPOSAL_PROMPT, grammar.SENTENCE_JUDGE_PROMPT}
    bank = json.loads(next((output / '_grammar_bank').glob('bank_*.json')).read_text())
    assert bank['spec']['rearrangement_policy'] == grammar.SENTENCE_REARRANGEMENT_POLICY
    assert bank['spec']['proposer']['prompt_sha256'] == grammar.json_digest(grammar.SENTENCE_PROPOSAL_PROMPT)
    assert bank['spec']['judge']['prompt_sha256'] == grammar.json_digest(grammar.SENTENCE_JUDGE_PROMPT)
    before = len(prompts)
    assert every.main(args + ['--offline']) == (0 if failure is None else 1)
    assert len(prompts) == before


def test_sentence_bank_refuses_judge_with_clause_severity_policy(tmp_path):
    with pytest.raises(grammar.GrammarError, match='judge policy'):
        grammar.build_grammar_bank('但大卫疲惫不堪。', bank_dir=tmp_path, seed=1,
                                   max_rate=1, unit_mode='sentence',
                                   cache=grammar.GrammarJudgmentCache(
                                       tmp_path / 'judgments.json', model='test', offline=True))


@pytest.mark.parametrize('missing_bank', [False, True])
@pytest.mark.parametrize('reject_stage', ['grammar', 'meaning'])
def test_retry_preserves_old_approvals_and_only_calls_models_for_unresolved_sentences(
    tmp_path, monkeypatch, fake_meaning_models, missing_bank, reject_stage,
):
    calls = fake_models(monkeypatch, reject_last=reject_stage == 'grammar')
    compare = grammar.GPTMeaningJudge.__call__

    def reject_meaning(self, request):
        result = compare(self, request)
        if request['original_clause'].startswith('2 '):
            result['participant_roles_preserved'] = 'no'
        return result

    args = setup(tmp_path)
    with monkeypatch.context() as old:
        # Reproduce the earlier strict policy and an interrupted final-bank write.
        old.setattr(grammar, 'SENTENCE_PROPOSAL_PROMPT', grammar.PROPOSAL_PROMPT)
        old.setattr(grammar, 'SENTENCE_JUDGE_PROMPT', grammar.JUDGE_PROMPT)
        old.setattr(grammar, 'SENTENCE_REARRANGEMENT_POLICY', grammar.REARRANGEMENT_POLICY)
        if reject_stage == 'meaning':
            old.setattr(grammar.GPTMeaningJudge, '__call__', reject_meaning)
        assert every.main(args) == 1
    original_root = tmp_path / 'out'
    original_path = next((original_root / 'p/grammar/_grammar_bank').glob('bank_*.json'))
    original = json.loads(original_path.read_text())
    assert len(original['entries']) == 2
    if missing_bank:
        original_path.unlink()
    snapshot_before = {str(p.relative_to(original_root)): p.read_bytes()
                       for p in original_root.rglob('*') if p.is_file()}
    calls = fake_models(monkeypatch)
    fake_meaning_models['reading'].clear()
    retry_args = list(args)
    retry_args[retry_args.index('--output-root') + 1] = str(tmp_path / 'retry')
    retry_args += ['--resume-from', str(original_root)]
    assert every.main(retry_args) == 0
    requested = [unit for request in calls for unit in request['clauses']]
    assert len(requested) == 1
    assert requested[0]['original_clause'].startswith('2 ')
    assert len(fake_meaning_models['reading']) == 1
    assert calls[0]['previous_attempts'][0]['attempts']
    new_path = next((tmp_path / 'retry/p/grammar/_grammar_bank').glob('bank_*.json'))
    result = json.loads(new_path.read_text())
    assert result['entries'][:2] == original['entries']
    assert result['spec']['preserved_bank']['spec'] == original['spec']
    assert result['spec']['preserved_bank'].get('recovered_from_cached_reviews', False) == missing_bank
    assert every.sentence_audit(TEXT, result)['approved_sentence_units'] == 3
    calls.clear()
    assert every.main(retry_args + ['--offline']) == 0
    assert calls == []
    assert snapshot_before == {str(p.relative_to(original_root)): p.read_bytes()
                               for p in original_root.rglob('*') if p.is_file()}
    tampered = copy.deepcopy(result)
    tampered['entries'][0]['corrupted_text'] = tampered['entries'][0]['original_text']
    with pytest.raises(grammar.GrammarError, match='Previously approved'):
        grammar.validate_grammar_bank(TEXT, tampered)


def test_retry_refuses_changed_semantic_policy_before_any_model_call(tmp_path, monkeypatch, fake_meaning_models):
    fake_models(monkeypatch, reject_last=True)
    args = setup(tmp_path)
    assert every.main(args) == 1
    original_path = next((tmp_path / 'out/p/grammar/_grammar_bank').glob('bank_*.json'))
    original = json.loads(original_path.read_text())
    calls = fake_models(monkeypatch)
    with pytest.raises(grammar.GrammarError, match='incompatible source or meaning checks'):
        grammar.build_grammar_bank(TEXT, bank_dir=tmp_path / 'new', seed=original['spec']['seed'],
            max_rate=1, unit_mode='sentence', preserved_bank=original,
            cache=grammar.GrammarJudgmentCache(tmp_path / 'new/judgments.json',
                                               model='different-model', unit_mode='sentence'))
    assert calls == []
