"""Meaningful checks on the extra gates and blinded v2 evaluation."""

import json
from types import SimpleNamespace

import pytest

from evaluation.scripts.variants.banks import mistranslation_conservative_judge as strict
from evaluation.scripts.variants.banks import mistranslation_validation as legacy
from evaluation.scripts.analysis import evaluate_mistranslation_judge_v2 as run


def judgment(**overrides):
    return {
        "source_claim": "There were eight animals.", "replacement_claim": "There were thirteen animals.",
        "explanation": "Count changed.", **{f: "yes" for f in legacy.JUDGMENT_FIELDS},
        "change_basis": "explicit_value_change", "change_dimension": "quantity",
        "difference_evidence": "八只羊 -> 十三只羊", "needs_repair": "no", **overrides,
    }


@pytest.mark.parametrize("basis", ["vague_contrast", "equivalent_or_uncertain"])
def test_vague_or_uncertain_basis_overrides_all_yes(basis):
    value = judgment(change_basis=basis)
    assert legacy.judgment_accepts(strict.legacy_view(value))
    assert not strict.conservative_judgment_accepts(value)
    assert "insufficient_change_basis" in strict.conservative_rejection_reasons(value)


@pytest.mark.parametrize("repair", ["yes", "uncertain"])
def test_needed_or_uncertain_repair_overrides_all_yes(repair):
    assert not strict.conservative_judgment_accepts(judgment(needs_repair=repair))


@pytest.mark.parametrize("dimension", sorted(strict.SCALAR_DIMENSIONS))
def test_scalar_change_cannot_evade_rule_through_action_basis(dimension):
    assert not strict.conservative_judgment_accepts(judgment(change_dimension=dimension, change_basis="different_action_or_referent"))


def test_valid_evidence_passes_but_original_rejections_still_apply():
    assert strict.conservative_judgment_accepts(judgment())
    assert not strict.conservative_judgment_accepts(judgment(fluent="no"))
    assert not strict.conservative_judgment_accepts(judgment(difference_evidence=" "))
    assert strict.conservative_judgment_accepts(judgment(change_basis="polarity_reversal"))
    assert strict.conservative_judgment_accepts(judgment(change_dimension="action", change_basis="different_action_or_referent"))


def test_missing_fields_fail_closed():
    value = judgment()
    del value["change_basis"]
    with pytest.raises(legacy.MistranslationValidationError):
        strict.conservative_judgment_accepts(value)


def test_fixture_fresh_cases_exclude_old_pairs_and_labels_stay_hidden():
    dataset, prompts, schemas = run.load_fixture(run.FIXTURE)
    fresh = [c for c in dataset["cases"] if c["cohort"] == "fresh"]
    assert len(fresh) == 32 and sum(c["expected"] == "accept" for c in fresh) == 16
    assert len(dataset["cases"]) == 38 and sum(c["repeat"] for c in fresh) == 4
    old_pairs = set()
    for name in ("mistranslation_judge_holdout_v1", "mistranslation_judge_followup_v1"):
        old = json.loads((run.FIXTURE.parent / name / "cases.json").read_text())
        old_pairs.update((c["source"], c["target"]) for c in old["cases"])
    assert not any((c["source"], c["target"]) in old_pairs for c in fresh)
    for case in dataset["cases"]:
        request = run.case_request(case)
        assert set(request) == {"original_passage", "source", "replacement", "mode", "occurrences"}
        assert case["expected_reason"] not in json.dumps(request, ensure_ascii=False)


def test_live_contract_records_extra_gate_and_repeat_cache_is_separate(tmp_path):
    dataset, prompts, schemas = run.load_fixture(run.FIXTURE)
    case = dataset["cases"][0]
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        assert kwargs["model"] == "gpt-6-sol"
        assert kwargs["text"]["format"]["schema"] == strict.CONSERVATIVE_SCHEMA
        assert json.loads(kwargs["input"]) == run.case_request(case)
        return SimpleNamespace(status="completed", output=[], output_text=json.dumps(judgment(change_basis="vague_contrast")),
                               id=f"response-{len(calls)}", model="gpt-6-sol", usage={"total_tokens": 7})

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    for trial in (1, 2):
        result = run.evaluate_case(case, "conservative", trial, prompts["conservative"], schemas["conservative"], tmp_path, "gpt-6-sol", client=client)
        assert result["criteria_only_accept"] and result["extra_gate_changed_decision"]
        assert result["decision"] == "reject"
        assert run.evaluate_case(case, "conservative", trial, prompts["conservative"], schemas["conservative"], tmp_path, "gpt-6-sol", offline=True) == result
    assert len(calls) == 2


def test_reports_score_fresh_and_known_cases_separately():
    dataset = {"cases": [
        {"id": "fresh", "family": "test", "expected": "reject", "cohort": "fresh", "repeat": False},
        {"id": "known", "family": "test", "expected": "reject", "cohort": "regression", "repeat": False},
    ], "promotion_gate": {"max_false_accepts": 0, "max_false_rejects": 1, "max_repeat_flips": 0}}
    records = [{"id": case_id, "arm": arm, "trial": 1, "decision": decision, "judgment": {"explanation": "test"}}
               for arm in run.ARMS for case_id, decision in [("fresh", "accept"), ("known", "reject")]]
    result = run.summarize(dataset, records, len(records), 1)
    assert result["fresh"]["conservative"]["false_accept"] == 1
    assert result["regression"]["conservative"]["false_accept"] == 0
