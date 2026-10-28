import copy
import json
from types import SimpleNamespace

import pytest

from evaluation.scripts.campaigns.current.run_overnight_ladder import campaign_cells, weighted_plan, verify_cell, RESULTS
from evaluation.scripts.variants.banks.extend_mistranslation_coverage import extend_bank, available_coverage, new_span_reasons
from evaluation.scripts.variants.current import create_mistranslation_variants as mis
from evaluation.scripts.variants.current import create_omission_variants as omission
from evaluation.tests.test_mistranslation_validation import FakeClient, build, entry, judgment, TEXT


class RefillClient(FakeClient):
    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        request = json.loads(kwargs["input"])
        if kwargs["text"]["format"]["name"] == "mistranslation_proposals":
            result = {"replacements": [entry(), entry("罗马", "希腊"),
                entry("城门口", "山坡上"), entry("回家", "出城", "contextual")]}
        else:
            result = judgment(request)
        return SimpleNamespace(status="completed", output=[], output_text=json.dumps(result), model="gpt-6-sol", id="test", usage={})


def test_coverage_refill_retains_approvals_exclusions_and_reuses_cache(tmp_path):
    parent = build(tmp_path / "parent", FakeClient())
    original = copy.deepcopy(parent)
    client = RefillClient()
    kwargs = dict(passage=TEXT, parent=parent, cache_dir=tmp_path / "extend",
        output=tmp_path / "bank.json", exclusions=[{"source": "城门口", "target": "山坡上", "reason": "user excluded"}],
        target_rate=available_coverage(TEXT, parent["replacements"]) + .01, max_rounds=2)
    bank = extend_bank(**kwargs, client=client)
    assert parent == original
    assert bank["replacements"][:-1] == parent["replacements"]
    assert bank["replacements"][-1]["source"] == "回家"
    assert bank["coverage_extension"]["target_met"]
    assert len(client.calls) == 2  # One proposal, one new non-overlapping candidate review.
    assert extend_bank(**kwargs, offline=True) == bank
    assert new_span_reasons(entry("罗马", "希腊"), TEXT, parent["replacements"])


def test_nested_omissions_hit_all_six_doses_without_duplicate_text():
    text = "".join(f"{i} 他走进城里。\n" for i in range(1, 41))
    units = omission.passage_units(text)
    indices = [i for i,u in enumerate(units) if u["omittable"]]
    weights = [units[i]["content_chars"] for i in indices]
    plan = weighted_plan(weights, sum(weights))
    previous = set()
    outputs = set()
    for rate, selection in plan.items():
        selected = {indices[i] for i in selection}
        assert previous < selected
        result, meta = omission.apply_omissions(text, rate=rate, seed=1, selected_unit_indices=sorted(selected))
        assert abs(meta["actual_rate"] - rate) < .001
        outputs.add(result)
        previous = selected
    assert len(outputs) == 6


def test_nested_mistranslations_keep_systematic_occurrences_together():
    text = "母亲在家。母亲回家。父亲出城。"
    bank = {"replacements": [entry("母亲", "妻子"), entry("父亲", "哥哥")]}
    groups = mis.candidate_groups(mis.find_occurrences(text, mis.normalized_replacements(bank)))
    mother_index = next(i for i,g in enumerate(groups) if g["source"] == "母亲")
    result, meta = mis.apply_mistranslations(text, rate=.3, seed=1, bank=bank, selected_group_indices=[mother_index])
    assert result.count("妻子") == 2 and "母亲" not in result
    assert meta["substitution_occurrence_count"] == 2
    with pytest.raises(mis.MistranslationError):
        mis.apply_mistranslations(text, rate=.3, seed=1, bank=bank, selected_group_indices=[0,0])


def test_campaign_finishes_every_clean_cell_before_omission():
    cells = list(campaign_cells())
    assert len(cells) == 600 and len(set(cells)) == 600
    stages = [r[0] for r in cells]
    assert stages[:30] == ["clean"] * 30
    assert stages[30:210] == ["omission"] * 180
    assert stages[210:390] == ["mistranslation"] * 180
    assert stages[390:570] == ["grammar"] * 180
    assert stages[570:] == ["wbw"] * 30


def test_excluding_grammar_retains_all_other_cells_and_order():
    cells = list(campaign_cells(exclude_grammar=True))
    assert cells == [cell for cell in campaign_cells() if cell[0] != "grammar"]
    assert len(cells) == 420 and len(set(cells)) == 420
    assert len({cell[3] for cell in cells}) == 14
    assert {cell[1] for cell in cells} == {"llama3.2:1b", "qwen2.5:1.5b", "qwen3:1.7b"}


def test_cell_verification_rejects_duplicates_and_retains_model_errors(tmp_path):
    rows = [{"id": "q-open", "q_type": "open", "generation_error": "empty model answer"},
            {"id": "q-mcq", "q_type": "mcq"}]
    expected = {(r["id"], r["q_type"]) for r in rows}
    for name in RESULTS:
        (tmp_path/name).write_text(json.dumps({"items":rows} if name.startswith("scores") else rows))
    assert verify_cell(tmp_path, expected)["generation_error_count"] == 1
    (tmp_path/RESULTS[0]).write_text(json.dumps([rows[0],rows[0]]))
    with pytest.raises(ValueError, match="Incomplete or duplicate"):
        verify_cell(tmp_path, expected)


@pytest.mark.parametrize("effort", [{}, {"thinking_chars": 12}, {"thinking_chars": 0}])
def test_no_think_verification_requires_recorded_zero_thinking(tmp_path, effort):
    rows = [{"id": "q", "q_type": "open", "answer_effort": effort}]
    for name in RESULTS:
        (tmp_path / name).write_text(json.dumps({"items": rows} if name.startswith("scores") else rows))
    if effort.get("thinking_chars") == 0:
        assert verify_cell(tmp_path, {("q", "open")}, no_think=True)["generation_error_count"] == 0
    else:
        with pytest.raises(ValueError, match="No-thinking verification failed"):
            verify_cell(tmp_path, {("q", "open")}, no_think=True)


def test_no_think_campaign_routes_flag_and_rejects_mixed_resume(tmp_path, monkeypatch):
    from evaluation.scripts.campaigns.current import run_overnight_ladder as ladder
    from evaluation.agents import generate_chinese_answers as answers
    pid, model, method = "t1_2sam21", "qwen3:1.7b", "grammar/100%"
    (tmp_path / pid / method).mkdir(parents=True)
    monkeypatch.setattr(answers, "load_qa_items", lambda path: [])
    monkeypatch.setattr(answers, "public_questions", lambda rows: [{"id": "q", "q_type": "open"}])
    captured = []

    def run(command, **kwargs):
        captured.append(command)
        destination = tmp_path / pid / "qwen317b_nothink" / method
        rows = [{"id": "q", "q_type": "open", "answer_effort": {"thinking_chars": 0}}]
        for name in RESULTS:
            (destination / name).write_text(json.dumps({"items": rows} if name.startswith("scores") else rows))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ladder.subprocess, "run", run)
    cells = [("grammar", model, pid, method)]
    ladder.evaluate(tmp_path, selected_cells=cells, no_think=True)
    assert len(captured) == 1 and "--ollama-no-think" in captured[0]
    ladder.evaluate(tmp_path, selected_cells=cells, no_think=True)
    assert len(captured) == 1
    with pytest.raises(ValueError, match="Cannot mix thinking modes"):
        ladder.evaluate(tmp_path, selected_cells=cells)
