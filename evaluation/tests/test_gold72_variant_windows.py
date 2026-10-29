import pytest

from evaluation.scripts.mcq.diagnostics.run_gold72_small_models_variants import (
    omission, omission_verse_index,
)


def omit_matching(clean, snippets):
    units = omission.passage_units(clean)
    selected = [i for i, u in enumerate(units) if any(s in u['text'] for s in snippets)]
    assert len(selected) == len(snippets)
    return omission.apply_omissions(clean, rate=0.3, seed=0, selected_unit_indices=selected)


def test_deleted_marker_does_not_merge_surviving_text_into_previous_verse():
    clean = '1 前一节。\n\n2 删除开头，保留结尾。\n\n3 后一节。'
    variant, metadata = omit_matching(clean, ['删除开头'])
    indexed = omission_verse_index(clean, variant, metadata, [9])
    assert indexed[9, 1] == '1 前一节。'
    assert indexed[9, 2] == '保留结尾。'
    assert indexed[9, 3] == '3 后一节。'
    assert '2 ' not in indexed[9, 2]


def test_entire_deleted_window_stays_empty_without_restoring_context():
    clean = '1 前一节。\n\n2 全节删除。\n\n3 后一节。'
    variant, metadata = omit_matching(clean, ['全节删除'])
    indexed = omission_verse_index(clean, variant, metadata, [9])
    assert indexed[9, 2] == ''


def test_deleted_chapter_marker_does_not_confuse_repeated_verse_numbers():
    clean = '17 第一章开头。\n\n2 第一章第二节。\n\n18 第二章开头，仍有内容。\n\n2 第二章第二节。'
    variant, metadata = omit_matching(clean, ['第二章开头'])
    indexed = omission_verse_index(clean, variant, metadata, [17, 18])
    assert indexed[17, 2] == '2 第一章第二节。'
    assert indexed[18, 1] == '仍有内容。'
    assert indexed[18, 2] == '2 第二章第二节。'


def test_mismatched_omission_record_or_variant_is_rejected():
    clean = '1 前一节。\n\n2 全节删除。\n\n3 后一节。'
    variant, metadata = omit_matching(clean, ['全节删除'])
    with pytest.raises(AssertionError, match='Saved omission variant'):
        omission_verse_index(clean, variant + '意外新增文字', metadata, [9])
    metadata['omitted_units'][0]['text'] = '错误记录'
    with pytest.raises(AssertionError, match='record mismatch'):
        omission_verse_index(clean, variant, metadata, [9])
