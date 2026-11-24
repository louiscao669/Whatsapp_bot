"""Source-footprint arithmetic, not claims about synthetic Chinese validity."""
import pytest

from evaluation.scripts.variants.current import grammar_source_spans as s
from evaluation.scripts.variants.current import mixed_grammar_ladder as l
from evaluation.scripts.variants.current import create_grammar_variants as g
from evaluation.scripts.pipeline import build_mixed_grammar_ladder as b


def candidate(before, after, subtype='misordering', start=0):
    return s.annotate(dict(before=before, after=after, subtype=subtype, start=start,
                           verse='1:1', status='pass', content_chars=g.content_len(before)))


def test_adjacent_two_character_phrase_swap_counts_four_not_two_or_clause():
    c = candidate('他认真阅读这封书信。', '他阅读认真这封书信。')
    assert c['content_chars'] == 9
    assert c['dose_content_chars'] == 4
    assert c['dose_footprint']['spans'][0]['source'] == '认真阅读'


def test_moved_particle_counts_minimal_reordered_block():
    c = candidate('他带着兵器。', '他带兵器着。')
    assert c['dose_content_chars'] == 3
    assert c['dose_footprint']['spans'][0]['source'] == '着兵器'


def test_disjoint_form_changes_do_not_count_unchanged_middle():
    c = candidate('甲走很远乙来。', '丙走很远丁来。', 'word_form')
    assert c['dose_content_chars'] == 2
    assert [a['source'] for a in c['dose_footprint']['spans']] == ['甲', '乙']


def test_source_length_not_replacement_length_and_punctuation_excluded():
    assert candidate('他很勇敢。', '他很勇气。', 'word_form')['dose_content_chars'] == 1
    assert candidate('他回答。', '他答案。', 'word_form')['dose_content_chars'] == 2
    c = candidate('甲，乙。', '丙，丁。', 'word_form')
    assert c['dose_content_chars'] == 2


def test_insertions_anchor_original_content_and_deletions_count_removed_marker():
    c = candidate('请你进来。', '请你的进来。', 'word_form')
    assert c['dose_content_chars'] == 1
    assert c['dose_footprint']['spans'][0]['source'] == '你'
    assert c['dose_footprint']['spans'][0]['kind'] == 'insertion_source_anchor'
    assert candidate('他跑得快。', '他跑快。', 'word_form')['dose_content_chars'] == 1
    assert candidate('“你来。”', '“的你来。”', 'word_form')['dose_content_chars'] == 1


def test_union_deduplicates_and_detects_stale_metadata():
    c = candidate('请你进来。', '请你的进来。', 'word_form', 20)
    assert s.selection_footprint([c, c])['affected_chars'] == 1
    c['dose_content_chars'] = 4
    with pytest.raises(g.GrammarError, match='Stale'):
        s.selection_footprint([c])


def test_inventory_changed_is_not_a_reordering_footprint():
    with pytest.raises(g.GrammarError, match='inventory'):
        s.footprint('他来了。', '他来。', 'misordering')


def test_selector_uses_source_spans_and_cannot_select_same_clause_twice():
    a = candidate('他认真阅读这封书信。', '他阅读认真这封书信。')
    opts = l.combinations([a], 100, .04, 0, dose_basis='source_spans')
    assert opts[0]['affected_chars'] == 4
    assert not l.combinations([a], 100, .09, 0, dose_basis='source_spans')
    assert not l.combinations([a, a], 100, .08, 0, dose_basis='source_spans')
    a['status'] = 'flagged'
    assert not l.combinations([a], 100, .04, 0, dose_basis='source_spans')


def test_source_selector_requires_explicit_verified_footprints():
    a = dict(before='他来。', after='来他。', subtype='misordering', status='pass',
             verse='1:1', start=0, content_chars=2)
    with pytest.raises(KeyError):
        l.combinations([a], 100, .02, 0, dose_basis='source_spans')


def test_default_and_prompt_do_not_silently_reuse_whole_clause_metric():
    args = b.parse_args([])
    assert args.dose_basis == 'source_spans'
    assert args.output != args.candidate_run
    assert args.max_span_extra == 6 and args.span_refill_rounds == 2
    assert 'particularly the shortest ones' not in b.SPAN_MISORDER_PROMPT
