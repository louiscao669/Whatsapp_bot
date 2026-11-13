import json
from types import SimpleNamespace

import pytest

from evaluation.scripts.pipeline import translate_reviewed122_zh as translator
from evaluation.scripts.pipeline import verify_reviewed122_zh as verifier
from evaluation.scripts.pipeline.report_reviewed122_zh import stem_change


def test_writer_uses_only_source_and_windows_and_resumes_without_calls(tmp_path):
    row = {"id": "sample", "question": "Who left first?", "choices": ["one", "two", "three", "four"],
           "correct": "C", "source": "Hard77", "verses": {"1:2": "English verse."}}
    window = {"1:2": "第一人离开了。"}
    bad = {"question": "谁先离开了？", "choices": dict.fromkeys("ABCD", "同一人")}
    good = {"question": "谁先离开了？", "choices": dict(zip("ABCD", ["一人", "两人", "三人", "四人"]))}
    calls = []

    def post(url, **kwargs):
        assert url == translator.URL + "/api/chat"
        assert kwargs["allow_redirects"] is False
        calls.append(kwargs["json"])
        if kwargs["json"]["format"] == translator.FACTS_SCHEMA:
            raw = {"items": [{"id": 1, "choices": dict(zip("ABCD", row["choices"]))}]}
        elif kwargs["json"]["format"] == verifier.FIDELITY_SCHEMA:
            raw = {"items": [{"id": 1, "issues": []}]}
        else:
            raw = bad if len(calls) == 2 else good
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
            "done": True, "message": {"content": json.dumps(raw)}})

    session = SimpleNamespace(post=post)
    output = translator.translate_item(session, row, window, "recipe", tmp_path)
    task = json.loads(calls[1]["messages"][1]["content"])
    assert task == {"english_verses": row["verses"], "chinese_verses": window, "question": row["question"],
                    "choices": dict(zip("ABCD", row["choices"]))}
    assert len(calls) == 4 and output["correct"] == "C" and output["choices"][2] == "三人"
    assert output["verses"] == window and row["verses"] != window
    assert output == translator.translate_item(session, row, window, "recipe", tmp_path)
    assert len(calls) == 4

    checkpoint, = (tmp_path / "translations").glob("*.json")
    data = translator.read(checkpoint)
    data["completion_digest"] = "stale"
    translator.write(checkpoint, data)
    with pytest.raises(ValueError, match="Invalid translation checkpoint"):
        translator.translate_item(None, row, window, "recipe", tmp_path)


@pytest.mark.parametrize("about_traits", [False, True])
def test_detail_feedback_rewrites_or_restores_a_qualifier_before_output(tmp_path, about_traits):
    question = "What kind of men did he hire?" if about_traits else "How did he spend the silver?"
    four = ["Worthless and reckless men", "Experienced men", "Cautious men", "Young men"] if about_traits else [
        "He hired worthless and reckless men to follow him.", "He paid the leaders.", "He bought offerings.",
        "He bought a house."]
    row = {"id": "example", "question": question, "choices": four, "correct": "A", "verses": {"1": four[0]}}
    window = {"1": "他用银子雇了一些无赖狂徒跟随他。"}
    stem = "他雇了什么样的人？" if about_traits else "他用银子做了什么？"
    if about_traits:
        initial, accepted = "一些人。", "一些无赖狂徒。"
        others = ["有经验的人。", "谨慎的人。", "年轻人。"]
    else:
        initial, accepted = "他雇了一群游手好闲、胆大妄为的人跟随他。", "他雇了一些人跟随他。"
        others = ["他付钱给首领。", "他买了祭品。", "他买了一所房子。"]
    issue = "A: restore the distinguishing traits" if about_traits else "A: drop the incidental traits"
    calls = []

    def post(url, **kwargs):
        payload = kwargs["json"]
        calls.append(payload["format"])
        fixing = len(calls) > 3
        answer = accepted if fixing else initial
        if payload["format"] == translator.FACTS_SCHEMA:
            task, = json.loads(payload["messages"][1]["content"])
            assert set(task) == {"id", "question", "choices"}
            focused = [four[0] if about_traits else "He hired men to follow him.", *four[1:]]
            # Over-shortening would collapse the four trait choices into the same claim.
            facts = dict.fromkeys("ABCD", "Men") if about_traits else dict(zip("ABCD", focused))
            result = {"items": [{"id": 1, "choices": facts}]}
        elif payload["format"] == translator.SCHEMA:
            writer_task = json.loads(payload["messages"][1]["content"])
            assert writer_task["choices"]["A"] == (four[0] if about_traits else "He hired men to follow him.")
            if fixing:
                assert issue in payload["messages"][-1]["content"]
            result = {"question": stem, "choices": dict(zip("ABCD", [answer, *others]))}
        else:
            task, = json.loads(payload["messages"][1]["content"])
            assert task["question"] == stem and task["choices"]["A"] == answer
            assert list(task["english_choices"].values()) == four and "correct" not in task
            result = {"items": [{"id": 1, "issues": [] if fixing else [issue]}]}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
            "done": True, "message": {"content": json.dumps(result)}})

    draft = translator.translate_item(SimpleNamespace(post=post), row, window, "recipe", tmp_path)
    assert draft["choices"] == [accepted, *others] and draft["correct"] == "A"
    assert calls == [translator.FACTS_SCHEMA] + [translator.SCHEMA, verifier.FIDELITY_SCHEMA] * 2


def test_question_type_check_distinguishes_a_reason_from_an_action():
    assert stem_change("Why was she taken there?", "她被带到那里的原因是什么？") is None
    assert stem_change("Why was she taken there?", "她犯了什么罪？")
    assert stem_change("Who should be honored?", "应该怎样尊重那个人？")


@pytest.mark.parametrize("check", ["blind", "fidelity"])
def test_review_uses_the_generated_wording_and_discloses_source_only_for_fidelity(tmp_path, check):
    row = {"id": "sample", "verses": {"1:2": "经文"}, "question": "谁先离开？",
           "choices": ["甲", "乙", "丙", "丁"], "correct": "B"}
    source = {"question": "Who left first?", "choices": ["a", "b", "c", "d"]}
    def post(url, **kwargs):
        task, = json.loads(kwargs["json"]["messages"][1]["content"])
        chinese = task["chinese"] if check == "fidelity" else task
        assert chinese["question"] == row["question"] and "correct" not in task and "correct" not in chinese
        assert chinese["choices"]["B"] == "乙"
        if check == "blind":
            assert "english" not in task
            verdict = {"id": 1, "supported": ["B"], "reason": "经文支持乙。"}
        else:
            assert task["english"]["question"] == source["question"]
            assert "correct" not in task["english"]
            verdict = {"id": 1, "issues": []}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
            "done": True, "message": {"content": json.dumps({"items": [verdict]})}})

    recipe = {"options": {}, "schema": {}, "prompt": "test", "check": check}
    result = verifier.run_check(SimpleNamespace(post=post), tmp_path, [(1, row)], recipe, {"sample": source})
    assert result[0]["id"] == row["id"]
    assert (tmp_path / f"{check}_audit.json").exists()
