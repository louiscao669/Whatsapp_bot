import copy

import pytest

from evaluation.scripts.campaigns.current import run_hard66_full_ladder as hard66
from evaluation.scripts.campaigns.current.run_hard66_full_ladder import (
    CANNOT_TELL, item_window, reviewed_rows, save_input,
)


def pair(identifier, **flags):
    common = {"Q": "谁？", "reference": "18:18", "window_verses": [18, 19], **flags}
    return [
        {**common, "passage_id": f"uw-t1_test:{identifier}-open", "q_type": "open", "A": "The priest"},
        {**common, "passage_id": f"uw-t1_test:{identifier}-mcq", "q_type": "mcq",
         "A": {"A": "祭司", "B": "王", "C": "儿子", "D": "母亲"}, "correct": "A"},
    ]


def test_preserves_review_exclusions_and_mcq_only_item():
    source = pair("kept", status="ok") + pair("removed", status="exclude") + pair("onlymcq", force_form="mcq")
    before = copy.deepcopy(source)
    rows, omitted = reviewed_rows(source)
    assert source == before
    assert len(rows) == 3 and len(omitted) == 3
    assert sum(row["q_type"] == "open" for row in rows) == 1
    assert all(row["A"]["E"] == CANNOT_TELL for row in rows if row["q_type"] == "mcq")
    assert rows[0]["A"] == "The priest"


def test_honors_chapter_qualified_window_extension():
    row = pair("x", window_start="18:17")[0]
    assert item_window(row, [(17, 17), (18, 17), (18, 18), (18, 19)]) == [(18, 17), (18, 18), (18, 19)]


def test_missing_reviewed_verse_fails_instead_of_falling_back():
    with pytest.raises(ValueError, match="Invalid reviewed window"):
        item_window(pair("x")[0], [(18, 18)])


def test_different_qa_cannot_replace_resumable_campaign_inputs(tmp_path):
    path = tmp_path / "qa.json"
    save_input(path, pair("original"))
    save_input(path, pair("original"))
    with pytest.raises(ValueError, match="use a new --run-root"):
        save_input(path, pair("changed"))


def test_window_tuples_compare_to_saved_json_arrays_on_resume(tmp_path):
    path = tmp_path / "release.json"
    report = {"window_extensions": [{"after": [(26, 1), (26, 2), (26, 3)]}]}
    save_input(path, report)
    save_input(path, report)


def test_launcher_forwards_grammar_exclusion_to_evaluation(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hard66.sys, "argv", ["hard66", "--exclude-grammar", "--run-root", str(tmp_path)])
    monkeypatch.setattr(hard66, "prepare", lambda *args: {"question_forms": 129})
    launched = []
    monkeypatch.setattr(hard66.os, "execv", lambda executable, command: launched.append(command))
    hard66.main()
    assert len(launched) == 1
    assert "--exclude-grammar" in launched[0]
    assert launched[0][launched[0].index("--phase") + 1] == "evaluate"
    assert "14 conditions, 420 cells, 5418 responses; grammar excluded" in capsys.readouterr().out
