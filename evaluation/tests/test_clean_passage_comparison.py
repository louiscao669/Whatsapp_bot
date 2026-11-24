import json

import pytest

from evaluation.scripts.pipeline import compare_clean_passages as comparison


def test_reader_gets_both_orders_without_model_names_or_answer_fields(tmp_path, monkeypatch):
    pid = "t1_acts20"
    directory = tmp_path / pid
    directory.mkdir()
    (directory / "candidate.txt").write_text("7 新译文。")
    monkeypatch.setattr(comparison, "freeze_source", lambda *args: {"english":"7 They gathered.", "baseline":"7 旧译文。"})
    seen = []
    def evaluate(client, run, name, model, messages, schema):
        task = json.loads(messages[1]["content"])
        assert set(task) == {"English","A","B","focus_verses"}
        assert model == comparison.JUDGE and comparison.WRITER not in messages[1]["content"]
        seen.append(task)
        return json.dumps({"assessed_verses":["20:7"],"material_issues":[],"focus_verses":[],
                           "preference":"A" if "新译文。" in task["A"].values() else "B","reason":"Reviewed."})
    monkeypatch.setattr(comparison,"api_call",evaluate)
    meta = dict(id=pid, chapter_start=20, chapter_end=20, verse_start=7, verse_end=7, reference="Acts 20:7")
    comparison.review(None,tmp_path,meta)
    assert seen[0]["A"] == seen[1]["B"] and seen[0]["B"] == seen[1]["A"]
    assert [v["preference"] for v in comparison.read(directory/"unblinded.json")] == ["candidate"]*2


@pytest.mark.parametrize("new_error,expected", [(False,True),(True,False)])
def test_scaling_requires_verified_details_and_no_new_material_error(tmp_path,new_error,expected):
    for pid in comparison.PILOT:
        directory = tmp_path/pid
        if pid in comparison.TARGETS:
            label = comparison.TARGETS[pid]
            comparison.save(directory/"aligned.json", {k:{label:v} for k,v in
                [("source","English"),("baseline","旧译"),("candidate","译文：点明目标，高声传报。")]})
        findings = [{"affected":"candidate"}] if new_error else [{"affected":"both"}]
        comparison.save(directory/"unblinded.json",[
            {"order":{"A":"baseline","B":"candidate"},"issues":findings},
            {"order":{"A":"candidate","B":"baseline"},"issues":findings}])
    with pytest.raises(ValueError,match="exact Chinese quotation"):
        comparison.decide_pilot(tmp_path,"不存在","高声传报")
    comparison.decide_pilot(tmp_path,"点明目标","高声传报")
    assert comparison.read(tmp_path/"pilot_decision.json")["expand"] is expected
