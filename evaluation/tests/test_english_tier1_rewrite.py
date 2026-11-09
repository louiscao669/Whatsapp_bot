import json
from types import SimpleNamespace

import pytest

from evaluation.scripts.mcq.preparation.rewrite_tier1_distractors import load_items, main, rewrite_item


def test_fresh_source_uses_its_final_stem_and_own_window(tmp_path):
    path = tmp_path / "fresh.json"
    row = {"content_id": "sample:1", "question": "Original open question?", "answer": "earlier wording",
           "window_text": {"9": "Another scene.", "10": "A passage sentence."}, "window_verses": [10],
           "mcq": {"mcq_stem": "What happened?", "mcq_options": ["a", "b", "key", "d", "Cannot tell"],
                   "content": "<question>What happened?<question><answer>C<answer>",
                   "original_question": "Original open question?"}}
    path.write_text(json.dumps([row]))
    [item] = load_items("hard66", source_json=path)
    assert (item.question, item.answer, item.key) == ("What happened?", "key", "C")
    assert item.window == "10  A passage sentence."
    assert item.extras == ["Cannot tell"]

    pytest.importorskip("qa_generation.services.window_mcq")
    def generate(stem, answer, window, identifier, *, fixed_key):
        assert (stem, answer, window, identifier, fixed_key) == (
            item.question, item.answer, item.window, "sample:1", "C")
        return dict(correct="C", mcq_stem=stem, mcq_options=["first", "second", "key", "third"],
                    question_type="multiple_choice", original_question=stem, original_answer=answer,
                    review={"attempts": 1})
    updated, audit = rewrite_item(item, SimpleNamespace(generate=generate))
    assert updated["mcq"]["mcq_options"] == ["first", "second", "key", "third", "Cannot tell"]
    assert updated["mcq"]["original_question"] == row["question"]
    assert "E. Cannot tell" in updated["mcq"]["content"]
    assert updated["mcq"]["content"].endswith("<answer>C<answer>")
    assert audit["status"] == "accepted" and item.row == row


def test_archived_english_sources_have_resolved_windows_and_distinct_ids():
    for dataset in ("gold72", "hard66"):
        items = list(load_items(dataset))
        assert items and len(items) == len({i.identifier for i in items})
        assert all(item.window and item.verses and item.key for item in items)


def test_rewrite_exports_repaired_stem_in_matching_source_and_open_form(tmp_path):
    pytest.importorskip("qa_generation.services.window_mcq")
    source = tmp_path / "source.json"
    row = dict(content_id="sample:1", question="Why?", answer="An answer", window_text={"1": "A passage."},
               open={"content": "<question>Why?\n<question><answer>An answer<answer>"})
    prior = dict(status="flagged", verdict="multiple_answers", model="reviewer", question="Why?")
    row.update(stage="source answerability", reason="Two readings.", answerability=prior)
    source.write_text(json.dumps([row]))
    [item] = load_items("hard66", source_json=source)
    review = {"attempts": 1, "question_repair": {"initial_finding": prior},
              "answerability": {"status": "passed", "question": "What reason was given?"}}
    block = dict(mcq_stem="What reason was given?", mcq_options=["An answer", "b", "c", "d"], correct="A",
                 original_question="Why?", original_answer="An answer", question_type="multiple_choice", review=review)
    def generate(*args, answerability, fixed_key):
        assert answerability == prior
        return block
    updated, audit = rewrite_item(item, SimpleNamespace(generate=generate))
    assert updated["question"] == updated["mcq"]["mcq_stem"] == block["mcq_stem"]
    assert updated["mcq"]["content"].startswith("<question>What reason was given?\n\nA. An answer")
    assert updated["open"]["content"] == "<question>What reason was given?\n<question><answer>An answer<answer>"
    assert audit["question_repair"] == review["question_repair"]
    assert "stage" not in updated and "reason" not in updated and updated["answerability"] == review["answerability"]


def test_withheld_items_are_absent_from_accepted_files(tmp_path, monkeypatch):
    shared = pytest.importorskip("qa_generation.services.window_mcq")
    def reject(*args, **kwargs):
        raise shared.MCQReviewError("Another answer is defensible.")
    monkeypatch.setattr(shared, "WindowMCQWriter", lambda *args: SimpleNamespace(
        generate=reject, model="writer", judge_model="judge"))
    dest = tmp_path / "result"
    assert main(["--dataset", "gold72", "--item", "t1_1kgs13:kcyl", "--output-dir", str(dest)]) == 1
    assert json.loads((dest / "gold72/t1_1kgs13_all_formats.json").read_text()) == []
    audit = json.loads((dest / "audit.json").read_text())
    assert audit["counts"] == {"withheld": 1}
    assert audit["items"][0]["reason"] == "Another answer is defensible."
