"""Offline control-flow contracts; synthetic verdicts do not test language quality."""
import copy
import json

import pytest

from evaluation.scripts.analysis import simplify_qa_items as s


def case(mcq=False):
    return s.review.normalize_cases([dict(id="sample", question="After the bell, who left?",
        passage="The bell rang. Mara left. Levi stayed.", expected_answer="Mara", form="mcq" if mcq else "open",
        options={"A": "Mara", "B": "Levi", "E": "Cannot tell"} if mcq else {},
        correct_option="A" if mcq else "")])[0]


def contract(c):
    return dict(id="item", status="ready", target=c["intended_target"] or "Identify who left.",
        basis="explicit" if c["intended_target"] else "inferred", required_answer_components=["Mara"],
        relations=[dict(id="event", quote="who left", meaning="Agent of leaving", role="tested", reason="Requested information"),
                   dict(id="bell", quote="After the bell", meaning="Preceding bell", role="removable", reason="Only one leaving event")],
        note="Synthetic contract")


def proposal(c, question="Who left?", status="revised"):
    return dict(id="item", status=status, question=question,
        options=[dict(label=k, text=v) for k, v in c["options"].items()],
        removed_relation_ids=["bell"] if status == "revised" else [], note="Synthetic proposal")


def verification(c, score=0):
    check = lambda: dict(status="pass", evidence="Synthetic evidence")
    content = {k: check() for k in s.Content.model_fields}
    if c["form"] == "open":
        content["mcq_validity"]["status"] = "not_applicable"
    return dict(id="item", **{k: check() for k in ("contract_validity", "same_target", "same_language", "removals_justified")},
        option_meanings=[dict(label=k, **check()) for k in c["options"]], content=content,
        **{k: dict(score=score if k == "context_economy" else 0, evidence="Synthetic rating",
                  quotes=["Who left?"] if score and k == "context_economy" else []) for k in s.review.LANGUAGE_FIELDS})


def fake(stage, payload, attempt, repeat):
    if stage == "target": return contract(payload["original"])
    if stage == "simplify": return proposal(payload["original"])
    if stage == "verify": return verification(payload["original"])
    if stage == "structure":
        return {"items": [dict(id="item", parse_summary="Synthetic parse", features=[])]}
    if stage == "burden":
        return {"items": [dict(id="item", structure_assessments=[], **{
            k: dict(score=2 if k == "context_economy" else 0, evidence="Synthetic diagnosis") for k in s.review.LANGUAGE_FIELDS})]}
    raise AssertionError(stage)


def config():
    return s.settings()[0]


def test_early_simplification_precedes_verification_and_skips_detailed_diagnostics():
    c = case(True)
    original = copy.deepcopy(c)
    calls = []
    def call(stage, payload, attempt, repeat):
        calls.append(stage)
        if stage == "verify":
            assert set(payload) == {"original", "candidate", "contract"}
            assert payload["original"]["id"] == payload["candidate"]["id"] == "item"
        return fake(stage, payload, attempt, repeat)
    r = s.simplify_case(c, call, config())
    assert calls == ["target", "simplify", "verify", "verify"]
    assert r["status"] == "SIMPLIFIED" and r["accepted_case"]["question"] == "Who left?"
    assert c == original and r["accepted_case"]["intended_target"] == ""
    assert r["accepted_case"]["original_question"] == original["question"]
    for k in ("expected_answer", "correct_option", "options", "passage", "form"):
        assert r["accepted_case"][k] == c[k]


def test_already_clear_or_unchanged_proposal_is_still_verified():
    def call(stage, payload, attempt, repeat):
        if stage == "simplify": return proposal(payload["original"], payload["original"]["question"], "unchanged")
        return fake(stage, payload, attempt, repeat)
    r = s.simplify_case(case(), call, config())
    assert r["status"] == "KEPT" and r["accepted_case"] == case()
    assert len(r["attempts"][0]["checks"]) == 2


def test_residual_burden_triggers_diagnostics_then_bounded_feedback_rewrite():
    calls = []
    def call(stage, payload, attempt, repeat):
        calls.append(stage)
        if stage == "simplify" and attempt == 2:
            assert payload["original"]["question"] == case()["question"]
            assert payload["previous_attempts"][0]["diagnostics"]["burden"]["context_economy"]["score"] == 2
            return proposal(payload["original"], "Who went away?")
        if stage == "verify" and attempt == 1: return verification(payload["original"], 2)
        return fake(stage, payload, attempt, repeat)
    r = s.simplify_case(case(), call, config())
    assert r["status"] == "SIMPLIFIED" and len(r["attempts"]) == 2
    assert calls == ["target", "simplify", "verify", "verify", "structure", "burden", "simplify", "verify", "verify"]


def test_identical_failed_candidate_is_not_rejudged_until_it_passes():
    calls = []
    def call(stage, payload, attempt, repeat):
        calls.append(stage)
        if stage == "verify": return verification(payload["original"], 2)
        return fake(stage, payload, attempt, repeat)
    r = s.simplify_case(case(), call, config())
    assert r["status"] == "REVIEW" and r["accepted_case"] is None
    assert calls.count("verify") == 2 and r["attempts"][-1]["status"] == "REPEATED_PROPOSAL"


@pytest.mark.parametrize("field", ["same_target", "removals_justified", "same_language"])
def test_failed_or_uncertain_preservation_never_accepts(field):
    def call(stage, payload, attempt, repeat):
        value = fake(stage, payload, attempt, repeat)
        if stage == "verify" and repeat == 2: value[field]["status"] = "uncertain"
        return value
    r = s.simplify_case(case(), call, config())
    assert r["status"] == "REVIEW" and r["accepted_case"] is None


def test_disputed_contract_stops_without_writer_redefining_target():
    def call(stage, payload, attempt, repeat):
        value = fake(stage, payload, attempt, repeat)
        if stage == "verify": value["contract_validity"]["status"] = "uncertain"
        return value
    r = s.simplify_case(case(), call, config())
    assert r["status"] == "HOLD_TARGET" and len(r["attempts"]) == 1


def test_held_contract_never_reaches_writer():
    def call(stage, payload, attempt, repeat):
        assert stage == "target"
        return dict(contract(payload["original"]), status="hold")
    assert s.simplify_case(case(), call, config())["status"] == "HOLD_TARGET"


@pytest.mark.parametrize("kind", ["missing_option", "changed_distractor", "missing_content", "timeout"])
def test_fail_closed_on_missing_checks_distractor_change_or_call_failure(kind):
    def call(stage, payload, attempt, repeat):
        value = fake(stage, payload, attempt, repeat)
        if stage == "verify":
            if kind == "timeout": raise TimeoutError("synthetic timeout")
            if kind == "missing_option": value["option_meanings"].pop()
            if kind == "changed_distractor": value["option_meanings"][1]["status"] = "fail"
            if kind == "missing_content": value["content"]["answer_uniqueness"]["status"] = "not_applicable"
        return value
    r = s.simplify_case(case(True), call, config())
    assert r["accepted_case"] is None
    assert r["status"] == ("REVIEW" if kind == "changed_distractor" else "ERROR")


@pytest.mark.parametrize("mutation", ["fake_explicit", "bad_quote", "duplicate_relation", "uncertain_ready", "empty_components"])
def test_contract_invariants(mutation):
    c, d = case(), contract(case())
    if mutation == "fake_explicit": d["basis"] = "explicit"
    if mutation == "bad_quote": d["relations"][0]["quote"] = "not in question"
    if mutation == "duplicate_relation": d["relations"].append(d["relations"][0])
    if mutation == "uncertain_ready": d["relations"][1]["role"] = "uncertain"
    if mutation == "empty_components": d["required_answer_components"] = []
    with pytest.raises(ValueError): s.validate_contract(d, c)


def test_explicit_target_cannot_be_replaced():
    c = dict(case(), intended_target="Identify the person leaving after the bell, preserving the sequence.")
    d = contract(c)
    assert s.validate_contract(d, c) == d
    d["target"] = "Identify a person."
    with pytest.raises(ValueError): s.validate_contract(d, c)


@pytest.mark.parametrize("mutation", ["remove_tested", "extra_field", "reorder_choices", "lying_unchanged", "empty_question"])
def test_proposal_cannot_evade_fixed_contract(mutation):
    c = case(True)
    p = proposal(c)
    if mutation == "remove_tested": p["removed_relation_ids"] = ["event"]
    if mutation == "extra_field": p["expected_answer"] = "Levi"
    if mutation == "reorder_choices": p["options"].reverse()
    if mutation == "lying_unchanged": p["status"] = "unchanged"
    if mutation == "empty_question": p["question"] = ""
    with pytest.raises(ValueError): s.candidate_from(c, contract(c), p)


def test_cannot_accept_missing_or_duplicate_repeat():
    good = dict(repeat=1, verification=verification(case()))
    assert not s.accepted([good], 1)
    assert not s.accepted([good, good], 2)


@pytest.mark.parametrize("quotes", [[], ["The bell rang."], ["After the bell, who left?"]])
def test_burden_evidence_cannot_score_passage_or_old_wording(quotes):
    c = case()
    candidate = s.candidate_from(c, contract(c), proposal(c))
    verdict = verification(c, 2)
    verdict["context_economy"]["quotes"] = quotes
    with pytest.raises(ValueError): s.validate_verification(verdict, c, candidate)


def test_burden_evidence_must_be_in_current_candidate():
    c = case()
    candidate = s.candidate_from(c, contract(c), proposal(c))
    assert s.validate_verification(verification(c, 2), c, candidate)["context_economy"]["score"] == 2


def test_cli_caches_live_boundary_and_binds_input_and_output(tmp_path, monkeypatch):
    import openai
    source = tmp_path / "inputs.json"
    source.write_text(json.dumps([case()]))
    output = tmp_path / "run"
    calls = []
    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def request(client, model, stage, payload, prompt, path, schema):
        if path.exists(): return s.read(path)["parsed"]
        calls.append(stage)
        value = fake(stage, payload, 1, 1)
        s.review.write_json(path, dict(parsed=value))
        return value
    monkeypatch.setattr(openai, "OpenAI", Client)
    monkeypatch.setattr(s.old, "request_json", request)
    args = ["--input", str(source), "--output-dir", str(output)]
    assert s.main(args) == 0 and len(calls) == 4
    assert s.main(args) == 0 and len(calls) == 4
    assert s.read(output / "summary.json")["statuses"] == {"SIMPLIFIED": 1}
    assert len(s.read(output / "rewritten_cases.json")) == 1
    original = s.read(source)
    original[0]["question"] = "Which person left?"
    source.write_text(json.dumps(original))
    with pytest.raises(SystemExit): s.main(args)


def test_prepare_only_makes_no_model_calls_and_rejects_output_containing_inputs(tmp_path):
    source = tmp_path / "inputs.json"
    source.write_text(json.dumps([case()]))
    assert s.main(["--input", str(source), "--output-dir", str(tmp_path / "run"), "--prepare-only"]) == 0
    with pytest.raises(SystemExit): s.main(["--input", str(source), "--output-dir", str(tmp_path), "--prepare-only"])
