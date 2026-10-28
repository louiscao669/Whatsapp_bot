"""Offline contract tests; fixtures are not human linguistic judgments."""
from copy import deepcopy
import json

import pytest

from evaluation.scripts.analysis import review_qa_items as review


def case(**updates):
    return dict(id="q1", question="Who left?", passage="Paul left. Peter stayed.",
                expected_answer="Paul", form="open", options={}, correct_option="",
                intended_target="", original_question="", original_answer="", **updates)


def content():
    row = {"id": "q1", "target": "Identify who left", "target_basis": "inferred",
           **{key: {"status": "pass", "evidence": "Supported by the supplied passage"}
              for key in review.CONTENT_FIELDS},
           "meaning_profile": {"answer_explicitness": "direct", "semantic_relation": "agent",
                               "answer_scope": "single_component", "passage_span": "one_sentence"}}
    row["target_preservation"]["status"] = "not_applicable"
    row["mcq_validity"]["status"] = "not_applicable"
    return row


def structure(concern=None):
    return {"id": "q1", "parse_summary": "A direct agent question.", "features": [] if not concern else [
        {"kind": "role_tracking", "quote": "Who left?", "required_operations": "Resolve the actor.",
         "concern": concern, "reason": "Synthetic structural evidence."}]}


def burden(score=0, assessment=None):
    return {"id": "q1", **{key: {"score": score if key == "processing" else 0,
                                  "evidence": "Synthetic burden evidence."}
                           for key in review.LANGUAGE_FIELDS},
            "structure_assessments": [] if not assessment else [
                {"feature_index": 0, "assessment": assessment, "reason": "Synthetic effect."}]}


def test_valid_item_passes_without_a_combined_difficulty_score():
    result = review.resolve(content(), structure(), burden())
    assert result["decision"] == "KEEP"
    c = content()
    c["meaning_profile"]["answer_explicitness"] = "inference"
    c["meaning_profile"]["answer_scope"] = "multiple_components"
    assert review.resolve(c, structure(), burden())["decision"] == "KEEP"


@pytest.mark.parametrize("dimension", review.LANGUAGE_FIELDS)
def test_one_failed_language_dimension_cannot_be_averaged_away(dimension):
    b = burden()
    b[dimension]["score"] = 2
    assert review.resolve(content(), structure(), b)["decision"] == "REWRITE"


@pytest.mark.parametrize("field", review.CONTENT_FIELDS)
def test_content_failure_cannot_be_overridden_by_easy_wording(field):
    c = content()
    c[field]["status"] = "fail"
    result = review.resolve(c, structure(), burden())
    assert result["decision"] == "HOLD_CONTENT"
    assert result["content_failures"] == [field]


def test_language_failure_is_preserved_even_when_content_also_fails():
    c = content()
    c["answer_support"]["status"] = "fail"
    result = review.resolve(c, structure(), burden(2))
    assert result["decision"] == "HOLD_CONTENT"
    assert result["language_status"] == "REWRITE"


def test_ordinary_structure_is_not_an_automatic_rejection():
    assert review.resolve(content(), structure("ordinary"), burden(1, "manageable"))["decision"] == "KEEP"


def test_structural_concern_with_passing_burden_requires_review_not_rewrite():
    r = review.resolve(content(), structure("potential_burden"), burden(1, "manageable"))
    assert r["decision"] == "REVIEW"
    assert r["structure_burden_disagreement"]
    assert not r["language_failures"]


def test_uncertainty_is_held_even_without_structural_concern():
    c = content()
    c["context_sufficiency"]["status"] = "uncertain"
    assert review.resolve(c, structure(), burden())["decision"] == "REVIEW"
    assert review.resolve(content(), structure("ordinary"), burden(1, "uncertain"))["decision"] == "REVIEW"


def test_all_three_stages_run_even_if_content_fails_and_no_verdict_is_leaked():
    seen = []
    c = content()
    c["answer_support"]["status"] = "fail"

    def judge(stage, payload):
        seen.append(stage)
        if stage == "content_validity":
            return {"items": [c]}
        assert payload["items"][0]["intended_target"] == c["target"]
        assert "answer_support" not in payload["items"][0]
        if stage == "structure":
            return {"items": [structure("ordinary")]}
        assert payload["items"][0]["structural_inspection"]["features"]
        return {"items": [burden(2, "avoidable_burden")]}

    result = review.review_batch([case()], judge)[0]
    assert seen == ["content_validity", "structure", "burden"]
    assert result["content_status"] == "HOLD"
    assert result["language_status"] == "REWRITE"


@pytest.mark.parametrize("items", [[], [content(), content()], [dict(content(), id="unrequested")]])
def test_missing_duplicate_or_unknown_response_ids_cannot_pass(items):
    with pytest.raises(ValueError, match="exactly once"):
        review.validate_stage("content_validity", {"items": items}, [case()])


def test_required_content_checks_cannot_be_skipped():
    c = content()
    c["answer_support"]["status"] = "not_applicable"
    with pytest.raises(ValueError, match="applicability"):
        review.validate_stage("content_validity", {"items": [c]}, [case()])


def test_mcq_key_and_full_options_are_required_and_preserved():
    c = case()
    c.update(form="mcq", options={"A": "Paul", "B": "Peter"}, correct_option="A")
    assert review.normalize_cases([c])[0]["options"] == c["options"]
    c["correct_option"] = "C"
    with pytest.raises(ValueError, match="valid key"):
        review.normalize_cases([c])


def test_structure_must_quote_respondent_text_not_expected_answer():
    s = structure("ordinary")
    s["features"][0]["quote"] = "Paul"
    with pytest.raises(ValueError, match="displayed wording"):
        review.validate_stage("structure", {"items": [s]}, [case()])


def test_burden_must_account_for_every_structural_feature():
    with pytest.raises(ValueError, match="every structural feature"):
        review.validate_stage("burden", {"items": [burden()]}, [case()], {"q1": structure("ordinary")})


def test_explicit_target_cannot_be_replaced_with_an_inferred_target():
    item = case()
    item["intended_target"] = "Identify who left"
    c = content()
    c["target_preservation"]["status"] = "pass"
    with pytest.raises(ValueError, match="explicit target"):
        review.validate_stage("content_validity", {"items": [c]}, [item])


def test_target_provenance_is_corrected_from_input_without_changing_raw_judgment():
    c = content()
    c["target_basis"] = "explicit"
    raw = {"items": [c]}
    normalized = review.validate_stage("content_validity", raw, [case()])["q1"]
    assert normalized == dict(c, target_basis="inferred")
    assert raw["items"][0]["target_basis"] == "explicit"


def test_structure_can_quote_visible_option_labels():
    item = case()
    item.update(form="mcq", options={"A": "Paul", "B": "Peter"}, correct_option="A")
    s = structure("ordinary")
    s["features"][0]["quote"] = "A. Paul"
    assert review.validate_stage("structure", {"items": [s]}, [item])["q1"] == s


@pytest.mark.parametrize("quote", ["A：Paul；B：Peter", "Paul／Peter", "A. Paul; B. Peter"])
def test_multiple_verbatim_options_can_be_quoted_together(quote):
    item = case()
    item.update(form="mcq", options={"A": "Paul", "B": "Peter"}, correct_option="A")
    assert review.quote_in_displayed_item(quote, item)


@pytest.mark.parametrize("quote", ["A：Peter；B：Paul", "Paul; John", "Paul … Peter", "Paul; He stayed"])
def test_joined_option_quotes_reject_wrong_labels_or_added_words(quote):
    item = case()
    item.update(form="mcq", options={"A": "Paul", "B": "Peter"}, correct_option="A")
    assert not review.quote_in_displayed_item(quote, item)


def test_original_answer_alone_can_support_a_target_preservation_check():
    item = case()
    item["original_answer"] = "Paul"
    c = content()
    c["target_preservation"]["status"] = "pass"
    assert review.validate_stage("content_validity", {"items": [c]}, [item])["q1"] == c


def test_repeats_disagreement_or_incompleteness_never_approves():
    rows = [{"id": "q1", "repeat": 1, "decision": "KEEP"},
            {"id": "q1", "repeat": 2, "decision": "REWRITE"}]
    result = review.aggregate([case()], rows, 2)[0]
    assert result["complete"] and not result["stable"] and result["decision"] == "REVIEW"
    assert review.aggregate([case()], rows[:1], 2)[0]["decision"] == "REVIEW"
    rows[1]["decision"] = "REVIEW_ERROR"
    assert not review.aggregate([case()], rows, 2)[0]["complete"]


def test_input_hash_changes_after_translation_options_or_window_change():
    original = case()
    for field in ("question", "passage", "expected_answer", "intended_target"):
        changed = deepcopy(original)
        changed[field] += " changed"
        assert review.digest(original) != review.digest(changed)


def test_judges_never_receive_prior_labels_or_scores():
    raw = dict(case(), provisional_label="bad", group="focus", difficulty=0, previous_decision="KEEP")
    normalized = review.normalize_cases([raw])[0]
    assert "provisional_label" not in normalized and "previous_decision" not in normalized


def test_output_schema_has_no_duplicate_language_or_leakage_verdicts():
    assert "answer_leakage" in review.ContentItem.model_fields
    assert "answer_leakage" not in review.BurdenItem.model_fields
    assert "context_sufficiency" not in review.BurdenItem.model_fields
    assert "naturalness" not in review.ContentItem.model_fields
    assert "decision" not in review.StructureItem.model_fields


def test_invalid_evidence_is_archived_and_retried_without_changing_request(tmp_path, monkeypatch):
    calls = []
    invalid = structure("ordinary")
    invalid["features"][0]["quote"] = "Words not in this question"
    path = tmp_path / "structure.json"

    def fake_request(client, model, stage, payload, prompt, output):
        calls.append((model, stage, deepcopy(payload), prompt))
        data = {"items": [invalid if len(calls) == 1 else structure()]}
        review.write_json(output, {"parsed": data})
        return data

    monkeypatch.setattr(review, "request_stage", fake_request)
    result = review.request_validated_stage(None, "model", "structure", {"items": [case()]},
                                            "unchanged rubric", path, [case()])
    assert result == {"items": [structure()]}
    assert calls[0] == calls[1]
    assert json.loads((tmp_path / "invalid/structure_attempt1.json").read_text())["parsed"]["items"] == [invalid]
    assert json.loads(path.read_text())["parsed"] == result


def test_invalid_response_retry_limit_never_returns_a_pass(tmp_path, monkeypatch):
    def fake_request(client, model, stage, payload, prompt, output):
        review.write_json(output, {"parsed": {"items": []}})
        return {"items": []}

    monkeypatch.setattr(review, "request_stage", fake_request)
    path = tmp_path / "structure.json"
    with pytest.raises(ValueError, match="exactly once"):
        review.request_validated_stage(None, "model", "structure", {"items": [case()]},
                                       "unchanged rubric", path, [case()], attempts=2)
    assert len(list((tmp_path / "invalid").glob("*.error.json"))) == 2
    assert not path.exists()
