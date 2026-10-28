import json

import pytest

from evaluation.scripts.campaigns.current import run_sentence_grammar_nothink as campaign
from evaluation.scripts.variants.current import create_every_sentence_grammar as every
from evaluation.tests.test_every_sentence_grammar import TEXT, fake_models, setup


def fixture_inputs(tmp_path, monkeypatch):
    fake_models(monkeypatch, reject_last=True)
    args = setup(tmp_path)
    assert every.main(args) == 1
    previous = tmp_path / "source"
    base = previous / "p/_base/llm_prompt_high"
    for name in ["passage_translation.json", "decanonicalized_metadata.json"]:
        (base / name).write_text("{}")
    (base / "passage_source_decanonicalized.txt").write_text("Original passage")
    shared = previous / "p/_base/_shared"
    shared.mkdir()
    rows = [
        {"id": "uw-p:q-open", "q_type": "open", "Q": "谁进城？", "A": "他", "passage_reference": "Test 1:1-2"},
        {"id": "uw-p:q-mcq", "q_type": "mcq", "Q": "谁进城？", "A": dict(zip("ABCDE", ["他", "你", "我", "她", "不知道"])),
         "correct": "A", "passage_reference": "Test 1:1-2"},
    ]
    for suffix in ["qa_zh.json", "qa_zh_decanonicalized.json"]:
        (shared / f"p_base_{suffix}").write_text(json.dumps(rows))
    inputs = previous / "_inputs"
    inputs.mkdir()
    (inputs / "windows.json").write_text(json.dumps({"windows": [{"content_id": "p:q", "window": ["1:1", "1:2"]}]}))
    (previous / "release.json").write_text(json.dumps({"input_hashes": {}}))
    return tmp_path / "out", previous, tmp_path / "evaluation"


def test_mcq_partial_campaign_keeps_saved_edits_coverage_and_resumes(tmp_path, monkeypatch, fake_meaning_models):
    source, previous, output = fixture_inputs(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="use --include-partial"):
        campaign.prepare(source, previous, output, ["p"], qa_formats=["mcq"])
    manifest = campaign.prepare(source, previous, output, ["p"], include_partial=True, qa_formats=["mcq"])
    assert manifest["total_responses"] == manifest["window_checks"] == 1
    assert manifest["coverage"]["p"]["sentence_coverage"] == 2 / 3
    method = "grammar/max_approved"
    assert manifest["cells"][0][-1] == method
    assert not (output / "p/grammar/100%").exists()
    staged = output / "p" / method
    assert (staged / "passage_target.txt").read_bytes() == (source / "p/grammar/draft_passage_target.txt").read_bytes()
    assert (staged / "passage_target.txt").read_text().endswith(TEXT.split("\n")[-1])
    assert [r["q_type"] for r in json.loads((staged / "qa_target.json").read_text())] == ["mcq"]
    assert campaign.prepare(source, previous, output, ["p"], include_partial=True, qa_formats=["mcq"]) == manifest


def test_partial_campaign_rejects_draft_changes(tmp_path, monkeypatch, fake_meaning_models):
    source, previous, output = fixture_inputs(tmp_path, monkeypatch)
    (source / "p/grammar/draft_passage_target.txt").write_text(TEXT)
    with pytest.raises(ValueError, match="failed bank verification"):
        campaign.prepare(source, previous, output, ["p"], include_partial=True, qa_formats=["mcq"])
