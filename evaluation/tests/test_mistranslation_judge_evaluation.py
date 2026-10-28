"""Checks that the judge evaluation is blind, resumable, and scored honestly."""

import json
from types import SimpleNamespace

from evaluation.scripts.analysis import evaluate_mistranslation_judge as evaluation
from evaluation.scripts.variants.banks.mistranslation_validation import JUDGMENT_FIELDS


def test_fixture_is_balanced_novel_and_only_meaning_section_changes():
    dataset, prompts = evaluation.load_fixture(evaluation.FIXTURE)
    cases = dataset["cases"]
    assert len(cases) == 48
    assert sum(c["expected"] == "accept" for c in cases) == 24
    assert sum(c["repeat"] for c in cases) == 8
    assert len({c["family"] for c in cases}) == 12
    assert "meaning_changed: a substantive difference" in prompts["baseline"]
    assert prompts["baseline"].split("meaning_changed:")[0] == prompts["revised"].split("meaning_changed:")[0]
    assert prompts["baseline"].split("\nfluent:")[1] == prompts["revised"].split("\nfluent:")[1]


def test_requests_never_include_reference_labels_or_reasons():
    dataset, _ = evaluation.load_fixture(evaluation.FIXTURE)
    for case in dataset["cases"]:
        request = evaluation.case_request(case)
        assert set(request) == {"original_passage", "source", "replacement", "mode", "occurrences"}
        assert case["expected_reason"] not in json.dumps(request, ensure_ascii=False)
        assert case["id"] not in json.dumps(request, ensure_ascii=False)


def test_confusion_matrix_uses_primary_only_and_errors_are_not_rejections():
    cases = [{"id": str(i), "expected": expected, "family": "test", "repeat": True}
             for i, expected in enumerate(["accept", "reject", "accept", "reject", "reject"])]
    records = [{"id": str(i), "trial": 1, "decision": decision, "judgment": {"explanation": "test"}}
               for i, decision in enumerate(["accept", "reject", "reject", "accept"])]
    records += [{"id": "4", "trial": 1, "error": "API failed"},
                {"id": "0", "trial": 2, "decision": "reject", "judgment": {"explanation": "test"}}]
    m = evaluation.metrics(cases, records)
    assert all(m[k] == 1 for k in ("true_accept", "true_reject", "false_accept", "false_reject"))
    assert m["accuracy"] == 0.5
    assert m["false_accept_rate"] == m["false_reject_rate"] == 0.5
    assert m["scored_cases"] == 4 and m["expected_cases"] == 5
    assert m["errors"] == 1
    assert m["repeat_flips"] == ["0"]


def test_repeats_call_model_again_but_resume_uses_each_trial_cache(tmp_path):
    dataset, prompts = evaluation.load_fixture(evaluation.FIXTURE)
    case = dataset["cases"][0]
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        assert json.loads(kwargs["input"]) == evaluation.case_request(case)
        assert kwargs["model"] == "gpt-6-sol"
        judgment = {"source_claim": case["source"], "replacement_claim": case["target"],
                    "explanation": "Test response", **{k: "yes" for k in JUDGMENT_FIELDS}}
        return SimpleNamespace(status="completed", output=[], output_text=json.dumps(judgment),
                               id=f"call-{len(calls)}", model="gpt-6-sol", usage={"total_tokens": 5})

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    first = evaluation.evaluate_case(case, "baseline", 1, prompts["baseline"], tmp_path, "gpt-6-sol", client=client)
    repeat = evaluation.evaluate_case(case, "baseline", 2, prompts["baseline"], tmp_path, "gpt-6-sol", client=client)
    assert len(calls) == 2 and first["response_id"] != repeat["response_id"]
    for trial, expected in [(1, first), (2, repeat)]:
        assert evaluation.evaluate_case(case, "baseline", trial, prompts["baseline"], tmp_path, "gpt-6-sol", offline=True) == expected
    assert len(calls) == 2
