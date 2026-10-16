"""Contracts shared by analysis, scoring, and passage-variant commands."""

from pathlib import Path

import pytest

from evaluation.scripts._common import (
    all_format_variants,
    longest_shared_span,
    outputs_root,
)
from evaluation.scripts.variants._common import (
    format_rate,
    parse_verse_blocks,
    seed_offset,
    write_json,
)


@pytest.mark.parametrize("chapter", [0, 1, 24, "0", "1", "24"])
def test_numeric_seed_offsets_preserve_historical_chapters(chapter):
    assert seed_offset(chapter) == int(chapter)


def test_named_seed_offsets_are_stable():
    assert seed_offset("tier1/t1_judg9") == 75657


@pytest.mark.parametrize(
    "text", ["", "A heading only", "Title\n1 First。2 Second！", "1 One\n3 Three"]
)
def test_verse_parsing_preserves_every_character(text):
    assert "".join(block["text"] for block in parse_verse_blocks(text)) == text


def test_verse_parsing_keeps_heading_separate():
    assert parse_verse_blocks("Title\n1 First。2 Second！") == [
        {"kind": "heading", "verse": None, "text": "Title\n"},
        {"kind": "verse", "verse": 1, "text": "1 First。"},
        {"kind": "verse", "verse": 2, "text": "2 Second！"},
    ]


def test_variant_json_remains_unicode_and_newline_terminated(tmp_path):
    target = tmp_path / "nested" / "variant.json"
    write_json(target, {"text": "你好"})
    assert target.read_text(encoding="utf-8") == '{\n  "text": "你好"\n}\n'
    assert [format_rate(x) for x in (0, 0.05, 0.125)] == ["0%", "5%", "12.5%"]


def test_output_root_prefers_environment_then_repository(tmp_path, monkeypatch):
    override = tmp_path / "override"
    override.mkdir()
    repo = tmp_path / "project"
    output = repo / "evaluation" / "outputs"
    output.mkdir(parents=True)
    script = repo / "evaluation" / "scripts" / "analysis" / "current" / "report.py"
    monkeypatch.setenv("EVAL_OUTPUTS_ROOT", str(override))
    assert Path(outputs_root(script)) == override
    monkeypatch.setenv("EVAL_OUTPUTS_ROOT", str(tmp_path / "missing"))
    assert Path(outputs_root(script)) == output


def test_all_formats_keep_identity_and_leave_original_untouched():
    item = {"id": "q1", "reference": "1:2", "open": {"Q": "Why?"}, "mcq": {"Q": "Who?"}}
    variants = all_format_variants(item)
    assert [v["content_id"] for v in variants] == ["q1-open", "q1-mcq"]
    assert [v["passage_id"] for v in variants] == ["uw-q1-open", "uw-q1-mcq"]
    assert [v["Q"] for v in variants] == ["Why?", "Who?"]
    assert all(v["reference"] == "1:2" for v in variants)
    assert "q_type" not in item


@pytest.mark.parametrize(
    "option,window,expected",
    [("", "abc", 0), ("abc", "xabcx", 3), ("abcd", "xabzcd", 2), ("你好", "你", 1)],
)
def test_overlap_measures_contiguous_spans(option, window, expected):
    assert longest_shared_span(option, window) == expected
