"""Offline revision contracts; synthetic verdicts are not linguistic evidence."""
import copy
import json
import sys
from types import SimpleNamespace

import pytest

from evaluation.scripts.analysis import review_qa_items as review
from evaluation.scripts.analysis import rewrite_flagged_qa as rewrite


def case(mcq=False):
    return dict(id="gold:example:mcq" if mcq else "gold:example:open", form="mcq" if mcq else "open",
                question="Who left?", passage="Paul left. Peter stayed.", expected_answer="Paul",
                options={"A": "Paul", "B": "Peter", "E": "Cannot determine"} if mcq else {},
                correct_option="A" if mcq else "", intended_target="",
                original_question="", original_answer="")


def content(c):
    row = dict(id=c["id"], target="Identify who left.",
               target_basis="explicit" if c["intended_target"] else "inferred",
               meaning_profile=dict(answer_explicitness="direct", semantic_relation="agent",
                                    answer_scope="single_component", passage_span="one_sentence"))
    row.update({k: dict(status="pass", evidence="Synthetic supported verdict.") for k in review.CONTENT_FIELDS})
    if not any(c[k] for k in ("intended_target", "original_question", "original_answer")):
        row["target_preservation"]["status"] = "not_applicable"
    if c["form"] == "open":
        row["mcq_validity"]["status"] = "not_applicable"
    return row


def structure(c):
    return dict(id=c["id"], parse_summary="Direct question.", features=[])


def burden(c, score=0):
    return dict(id=c["id"], structure_assessments=[], **{
        k: dict(score=score if k == "processing" else 0, evidence="Synthetic burden evidence.")
        for k in review.LANGUAGE_FIELDS})


def record(mcq=False, scores=(2, 2), content_hold=False):
    c = case(mcq)
    rows = []
    for i, score in enumerate(scores, 1):
        cv, st, bu = content(c), structure(c), burden(c, score)
        if content_hold:
            cv["question_support"]["status"] = "fail"
        rows.append(dict(id=c["id"], repeat=i, input_hash=review.digest(c), content_validity=cv,
                         structural_inspection=st, language_accessibility=bu, **review.resolve(cv, st, bu)))
    return dict(case=c, baseline=review.aggregate([c], rows, len(rows))[0], source_review_dir="/baseline")


def proposal(c, text="Which person left?"):
    return dict(id="item", status="revised", question=text,
                options=[dict(label=k, text=v) for k, v in c["options"].items()],
                note="Address the synthetic wording issue.")


def preservation(c):
    passing = dict(status="pass", evidence="Synthetic equivalence verdict.")
    return dict(id="item", same_target=passing.copy(), same_language=passing.copy(),
                option_meanings=[dict(label=k, **passing) for k in c["options"]])


def fake_call(stage, payload, attempt, repeat):
    if stage == "rewrite":
        return proposal(payload["original"], "Which person left?" if attempt == 1 else "Who departed?")
    if stage == "preservation":
        return preservation(payload["original"])
    c = payload["items"][0]
    return {"items": [{"content_validity": content, "structure": structure, "burden": burden}[stage](c)]}


def test_selects_language_rewrite_even_when_content_hold_takes_priority():
    r = record(content_hold=True)
    assert r["baseline"]["decision"] == "HOLD_CONTENT"
    assert rewrite.select_records([r])[0] == [r]


def test_single_pass_requires_explicit_selection_and_incomplete_never_selected():
    r = record(scores=(2, 0))
    assert rewrite.select_records([r])[0] == []
    assert rewrite.select_records([r], include_single=True)[0] == [r]
    r["baseline"]["complete"] = False
    assert rewrite.select_records([r], include_single=True)[0] == []


def test_content_only_failure_is_not_a_wording_rewrite_request():
    assert rewrite.select_records([record(scores=(0, 0), content_hold=True)])[0] == []


def test_unknown_or_ineligible_requested_id_does_not_silently_select_other_items():
    with pytest.raises(ValueError, match="Unknown"):
        rewrite.select_records([record()], ids=["missing"])
    with pytest.raises(ValueError, match="rewrite policy"):
        rewrite.select_records([record(scores=(0, 0))], ids=[case()["id"]])


@pytest.mark.parametrize("field,value", [("expected_answer", "Peter"), ("correct_option", "B"),
                                         ("passage", "Peter left."), ("intended_target", "Identify who stayed.")])
def test_writer_cannot_edit_protected_fields(field, value):
    c = case(True)
    p = dict(proposal(c), **{field: value})
    with pytest.raises(ValueError):
        rewrite.proposal_case(c, p)


@pytest.mark.parametrize("labels", [["A", "B"], ["A", "B", "B"], ["B", "A", "E"], ["A", "B", "X"]])
def test_missing_duplicate_reordered_or_new_options_are_rejected(labels):
    c = case(True)
    p = proposal(c)
    p["options"] = [dict(label=k, text="Some text") for k in labels]
    with pytest.raises(ValueError, match="every option label"):
        rewrite.proposal_case(c, p)


def test_revised_case_preserves_answer_key_context_and_earlier_source_intention():
    c = case(True)
    c.update(original_question="Identify the person who left.", original_answer="Paul", intended_target="Agent of leaving")
    before = copy.deepcopy(c)
    result = rewrite.proposal_case(c, proposal(c))
    for field in c:
        if field not in ("question", "options"):
            assert result[field] == c[field]
    assert c == before


def test_option_only_revision_is_permitted_but_answer_reference_is_fixed():
    c = case(True)
    p = proposal(c, c["question"])
    p["options"][0]["text"] = "Paul, the one who left"
    result = rewrite.proposal_case(c, p)
    assert result["question"] == c["question"]
    assert result["expected_answer"] == "Paul"
    assert rewrite.displayed_hash(result) != rewrite.displayed_hash(c)
    # This proposal could leak through an option; parsing alone does not admit it.


def test_full_loop_accepts_only_after_all_two_pass_checks_and_keeps_judges_blind():
    r = record()
    before = copy.deepcopy(r)
    calls = []

    def call(stage, payload, attempt, repeat):
        calls.append((stage, copy.deepcopy(payload), attempt, repeat))
        if stage not in ("rewrite", "preservation"):
            assert "initial_reviews" not in payload and "previous_attempts" not in payload
            assert "note" not in payload["items"][0]
        return fake_call(stage, payload, attempt, repeat)

    result = rewrite.rewrite_record(r, call, {"language_rewrite_threshold": 2})
    assert result["status"] == "ACCEPTED" and len(calls) == 9
    assert r == before
    assert result["accepted_case"]["original_question"] == r["case"]["question"]


@pytest.mark.parametrize("stage,field,status", [
    ("preservation", "same_target", "fail"), ("preservation", "same_language", "fail"),
    ("preservation", "same_target", "uncertain"), ("content_validity", "answer_support", "fail"),
    ("content_validity", "answer_uniqueness", "uncertain"),
])
def test_a_failure_or_uncertainty_in_one_repeat_prevents_acceptance(stage, field, status):
    def call(s, payload, attempt, repeat):
        result = fake_call(s, payload, attempt, repeat)
        if s == stage and repeat == 2:
            (result if s == "preservation" else result["items"][0])[field]["status"] = status
        return result
    result = rewrite.rewrite_record(record(), call, {"language_rewrite_threshold": 2}, max_attempts=1)
    assert result["status"] == "UNRESOLVED" and result["accepted_case"] is None


def test_a_changed_distractor_meaning_cannot_pass_on_unchanged_correct_answer():
    def call(stage, payload, attempt, repeat):
        data = fake_call(stage, payload, attempt, repeat)
        if stage == "preservation":
            data["option_meanings"][1]["status"] = "fail"
        return data
    result = rewrite.rewrite_record(record(True), call, {"language_rewrite_threshold": 2}, max_attempts=1)
    assert result["status"] == "UNRESOLVED"


def test_missing_option_equivalence_is_an_error_not_a_pass():
    c = case(True)
    p = preservation(c)
    p["option_meanings"].pop()
    with pytest.raises(ValueError, match="Every original option"):
        rewrite.validate_preservation(p, c)


def test_a_second_attempt_receives_failure_evidence_but_stays_bound_to_original():
    def call(stage, payload, attempt, repeat):
        if stage == "rewrite" and attempt == 2:
            assert payload["original"]["question"] == "Who left?"
            assert payload["previous_attempts"][0]["rechecks"][0]["wording"]["processing"]["score"] == 2
        if stage == "content_validity":
            assert payload["items"][0]["original_question"] == "Who left?"
        result = fake_call(stage, payload, attempt, repeat)
        if stage == "burden" and attempt == 1:
            result["items"][0]["processing"]["score"] = 2
        return result
    result = rewrite.rewrite_record(record(), call, {"language_rewrite_threshold": 2})
    assert result["status"] == "ACCEPTED" and len(result["attempts"]) == 2
    assert result["accepted_case"]["question"] == "Who departed?"


def test_unchanged_proposal_does_not_get_another_chance_to_pass_by_judge_noise():
    calls = []
    def call(stage, payload, attempt, repeat):
        calls.append(stage)
        return proposal(payload["original"], payload["original"]["question"])
    result = rewrite.rewrite_record(record(), call, {"language_rewrite_threshold": 2})
    assert calls == ["rewrite", "rewrite"]
    assert result["status"] == "UNRESOLVED" and result["accepted_case"] is None


def test_model_decline_is_preserved_without_judging_a_nonexistent_revision():
    def call(stage, payload, attempt, repeat):
        assert stage == "rewrite"
        return dict(id="item", status="declined", question="", options=[], note="Needs a different window.")
    result = rewrite.rewrite_record(record(), call, {"language_rewrite_threshold": 2})
    assert result["status"] == "DECLINED"


def test_transport_failure_cannot_export_an_accepted_revision():
    def call(stage, payload, attempt, repeat):
        if stage == "burden":
            raise TimeoutError("Synthetic timeout")
        return fake_call(stage, payload, attempt, repeat)
    result = rewrite.rewrite_record(record(), call, {"language_rewrite_threshold": 2})
    assert result["status"] == "ERROR" and result["accepted_case"] is None


def test_one_check_or_duplicate_repeats_cannot_satisfy_acceptance():
    c = case()
    p = rewrite.proposal_case(c, proposal(c))
    checks = rewrite.audit_candidate(c, p, lambda s, d, r: fake_call(s, d, 1, r),
                                     {"language_rewrite_threshold": 2}, 2)
    assert not rewrite.accepted(checks[:1], 1)
    checks[1]["repeat"] = 1
    assert not rewrite.accepted(checks, 2)


def test_invalid_proposal_is_reportable_and_cannot_change_dataset(tmp_path):
    result = rewrite.rewrite_record(record(), lambda *args: ["not a proposal object"],
                                    {"language_rewrite_threshold": 2})
    assert result["status"] == "UNRESOLVED" and result["accepted_case"] is None
    rewrite.write_report(tmp_path, [result])
    assert "INVALID_PROPOSAL" in (tmp_path / "report.md").read_text()


def baseline_directory(path):
    config, prompts = rewrite.load_settings()
    r = record()
    cases = [r["case"]]
    id_map = {"q0000": cases[0]["id"]}
    for row in r["baseline"]["reviews"]:
        row["input_hash"] = review.digest(dict(cases[0], id="q0000"))
    manifest = dict(input_hash=review.digest(cases), config_hash=review.digest(config), repeats=2,
                    prompt_hashes={k: review.digest(prompts[k]) for k in config["stages"]})
    for name, value in (("cases.json", cases), ("results.json", [r["baseline"]]),
                        ("manifest.json", manifest), ("id_map.json", id_map)):
        review.write_json(path / name, value)
    return path


def test_stale_source_cases_are_rejected_before_generation(tmp_path):
    source = baseline_directory(tmp_path / "source")
    cases = rewrite.read(source / "cases.json")
    cases[0]["question"] = "Who stayed?"
    review.write_json(source / "cases.json", cases)
    with pytest.raises(ValueError, match="Changed cases"):
        rewrite.load_reviews([source], *rewrite.load_settings())


def test_stored_decisions_cannot_override_their_underlying_scores(tmp_path):
    source = baseline_directory(tmp_path / "source")
    results = rewrite.read(source / "results.json")
    results[0]["reviews"][0]["language_status"] = "PASS"
    review.write_json(source / "results.json", results)
    with pytest.raises(ValueError, match="disagrees with evidence"):
        rewrite.load_reviews([source], *rewrite.load_settings())


def test_output_location_and_manifest_protect_originals(tmp_path):
    source = baseline_directory(tmp_path / "source")
    with pytest.raises(ValueError, match="separate"):
        rewrite.prepare_output(source, [source], {}, [], [])
    output = tmp_path / "output"
    rewrite.prepare_output(output, [source], {"version": 1}, [], [])
    with pytest.raises(ValueError, match="different inputs"):
        rewrite.prepare_output(output, [source], {"version": 2}, [], [])


def test_prepare_only_does_not_construct_a_model_client(tmp_path, monkeypatch):
    source = baseline_directory(tmp_path / "source")
    class NeverClient:
        def __init__(self, **kwargs):
            pytest.fail("Prepare-only must not construct an API client")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=NeverClient))
    output = tmp_path / "prepared"
    assert rewrite.main(["--review-dir", str(source), "--output-dir", str(output), "--prepare-only"]) == 0
    assert len(rewrite.read(output / "selected_inputs.json")) == 1
    assert not (output / "accepted_cases.json").exists()


def test_missing_credentials_are_reported_without_exporting_acceptances(tmp_path, monkeypatch):
    source = baseline_directory(tmp_path / "source")
    class BrokenClient:
        def __init__(self, **kwargs):
            raise ValueError("Synthetic missing credentials")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=BrokenClient))
    output = tmp_path / "output"
    assert rewrite.main(["--review-dir", str(source), "--output-dir", str(output)]) == 1
    assert rewrite.read(output / "accepted_cases.json") == []
    assert rewrite.read(output / "summary.json")["statuses"] == {"ERROR": 1}


def test_cli_rechecks_exports_and_resumes_from_bound_cache(tmp_path, monkeypatch):
    source = baseline_directory(tmp_path / "source")
    output = tmp_path / "output"
    calls = []
    class Client:
        def __init__(self, **kwargs):
            self.responses = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def create(self, **kwargs):
            stage = kwargs["text"]["format"]["name"].removeprefix("qa_")
            payload = json.loads(kwargs["input"][1]["content"])
            calls.append(stage)
            data = fake_call(stage, payload, 1, 1)
            return SimpleNamespace(status="completed", output_text=json.dumps(data), model="synthetic",
                                   id=f"response{len(calls)}", usage=SimpleNamespace(model_dump=lambda: {}))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Client))
    argv = ["--review-dir", str(source), "--output-dir", str(output), "--workers", "1"]
    assert rewrite.main(argv) == 0
    assert len(calls) == 9
    assert rewrite.read(output / "summary.json")["accepted"] == 1
    assert rewrite.read(output / "accepted_cases.json")[0]["expected_answer"] == "Paul"
    assert rewrite.read(source / "cases.json")[0]["question"] == "Who left?"
    assert rewrite.main(argv) == 0
    assert len(calls) == 9, "A resumed run must reuse exactly matching cached responses"


def test_rewrite_response_schema_forbids_unexpected_edit_fields():
    schema = rewrite.Proposal.model_json_schema()
    assert schema["additionalProperties"] is False
    assert "correct_option" not in schema["properties"]
