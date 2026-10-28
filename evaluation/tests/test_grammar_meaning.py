"""Meaning vetoes, source-blind inputs, resumability, and evidence binding."""

import copy
import json

import pytest

from evaluation.scripts.variants.current import create_grammar_variants as g


ORIGINAL = "1 大卫和他的仆人下去与非利士人作战。"
BAD = "1 大卫和他的与非利士人仆人作战下去。"
GOOD = "1 大卫和他的下去仆人作战与非利士人。"


def request(candidate=GOOD):
    return {"original_passage": "标题\n" + ORIGINAL, "clause_start": 3,
            "original_clause": ORIGINAL, "edited_clause": candidate}


def reading(**overrides):
    return {"primary_reading": "David and his servants went down to fight the Philistines.",
            "participant_roles": "David and servants fight the Philistines.",
            "event_structure": "Movement followed by fighting.", "modifier_scope": "David's servants.",
            "interpretation_status": "clear", "alternative_readings": [], **overrides}


def judgment(**overrides):
    return {"explanation": "Test semantic comparison.", "risk_spans": [],
            **{field: "yes" for field in g.MEANING_FIELDS}, **overrides}


def test_reader_receives_edited_context_without_source_or_prior_rationale(tmp_path, fake_meaning_models):
    cache = g.GrammarMeaningCache(tmp_path, model="test")
    key, review = cache.evaluate(request())
    sent = fake_meaning_models["reading"][0]
    assert sent == {"passage": "标题\n" + GOOD, "focus_clause": GOOD, "clause_start": 3}
    assert ORIGINAL not in json.dumps(sent, ensure_ascii=False)
    comparison = fake_meaning_models["comparison"][0]
    assert comparison == {**request(), "candidate_reading": review["candidate_reading"]}
    assert g.meaning_review_accepts(review, GOOD)
    assert g.GrammarMeaningCache(tmp_path, model="test", offline=True).evaluate(request()) == (key, review)
    assert len(fake_meaning_models["reading"]) == len(fake_meaning_models["comparison"]) == 1


@pytest.mark.parametrize("field", g.MEANING_FIELDS)
@pytest.mark.parametrize("decision", ["no", "uncertain"])
def test_every_negative_or_uncertain_semantic_dimension_vetoes(field, decision):
    review = {"candidate_reading": reading(), "judgment": judgment(**{field: decision})}
    assert not g.meaning_review_accepts(review, GOOD)


@pytest.mark.parametrize("update", [
    {"interpretation_status": "ambiguous"},
    {"interpretation_status": "unrecoverable"},
    {"alternative_readings": [{"reading": "David continues fighting.", "evidence_span": "作战下去"}]},
])
def test_source_aware_approval_cannot_override_blind_ambiguity(update):
    review = {"candidate_reading": reading(**update), "judgment": judgment()}
    assert not g.meaning_review_accepts(review, BAD)


def test_identified_risk_cannot_be_hidden_by_all_yes_decisions():
    review = {"candidate_reading": reading(), "judgment": judgment(risk_spans=["作战下去"])}
    assert not g.meaning_review_accepts(review, BAD)


@pytest.mark.parametrize("stage", ["reader", "judge"])
def test_unsubstantiated_risk_span_fails_without_saving_approval(tmp_path, stage):
    cache = g.GrammarMeaningCache(tmp_path, model="test",
        reader=lambda req: reading(**({"alternative_readings": [
            {"reading": "Unsupported reading", "evidence_span": "invented evidence"},
        ]} if stage == "reader" else {})),
        evaluator=lambda req: judgment(risk_spans=["invented evidence"]))
    with pytest.raises(g.GrammarError, match="evidence"):
        cache.evaluate(request())
    assert not (tmp_path / "meaning_judgments.json").exists()


def test_interrupted_comparison_reuses_reading_but_offline_never_calls_models(tmp_path):
    calls = []
    def read(req):
        calls.append(req)
        return reading()
    def fail(req):
        raise g.GrammarError("transport interruption")
    with pytest.raises(g.GrammarError, match="transport"):
        g.GrammarMeaningCache(tmp_path, model="test", reader=read, evaluator=fail).evaluate(request())
    assert len(calls) == 1
    with pytest.raises(g.GrammarError, match="Missing cached meaning review"):
        g.GrammarMeaningCache(tmp_path, model="test", offline=True,
                             reader=read, evaluator=lambda req: pytest.fail("offline call")).evaluate(request())
    g.GrammarMeaningCache(tmp_path, model="test", reader=read,
                         evaluator=lambda req: judgment()).evaluate(request())
    assert len(calls) == 1


@pytest.mark.parametrize("prompt", ["MEANING_READER_PROMPT", "MEANING_JUDGE_PROMPT"])
def test_meaning_prompt_changes_invalidate_old_approvals(tmp_path, monkeypatch, fake_meaning_models, prompt):
    g.GrammarMeaningCache(tmp_path, model="test").evaluate(request())
    monkeypatch.setattr(g, prompt, getattr(g, prompt) + " Revised rubric.")
    with pytest.raises(g.GrammarError, match="Missing cached meaning"):
        g.GrammarMeaningCache(tmp_path, model="test", offline=True).evaluate(request())


def test_bad_source_offset_fails_before_model_calls(tmp_path, fake_meaning_models):
    with pytest.raises(g.GrammarError, match="offset"):
        g.GrammarMeaningCache(tmp_path, model="test").evaluate({**request(), "clause_start": 4})
    assert fake_meaning_models == {"reading": [], "comparison": []}


def build_bank(tmp_path, monkeypatch, fake_meaning_models):
    def propose(self, req):
        return {"clauses": [{"unit_index": c["unit_index"], "original_clause": c["original_clause"],
                            "candidates": [{"edited_clause": text, "error_type": "test",
                                            "explanation": "Test proposal."} for text in [BAD, GOOD]]}
                            for c in req["clauses"]]}
    monkeypatch.setattr(g.GPTGrammarProposer, "__call__", propose)
    def grammar_approval(req):
        return {**{field: "yes" for field in g.JUDGMENT_FIELDS},
                "explanation": "Grammar judge accepts both.", "error_span": req["edited_clause"]}
    def read(self, req):
        return reading(**({"interpretation_status": "ambiguous", "alternative_readings": [
            {"reading": "Continue fighting, not go down to fight.", "evidence_span": "作战下去"},
        ]} if req["focus_clause"] == BAD else {}))
    monkeypatch.setattr(g.GPTMeaningReader, "__call__", read)
    return g.build_grammar_bank(ORIGINAL, bank_dir=tmp_path, seed=42, max_rate=1,
        cache=g.GrammarJudgmentCache(tmp_path / "judgments.json", model="test", evaluator=grammar_approval))


def test_meaning_veto_skips_grammar_approved_candidate_and_exports_evidence(tmp_path, monkeypatch, fake_meaning_models):
    bank = build_bank(tmp_path, monkeypatch, fake_meaning_models)
    assert [e["corrupted_text"] for e in bank["entries"]] == [GOOD]
    assert bank["meaning_evaluated_candidate_count"] == 2
    assert bank["meaning_rejected_candidate_count"] == 1
    text, meta = g.apply_grammar_bank(ORIGINAL, rate=1, seed=42, bank=bank)
    assert text == GOOD
    assert meta["meaning_policy"] == g.MEANING_POLICY
    assert meta["affected_units"][0]["meaning_review"]["candidate_reading"]["interpretation_status"] == "clear"


@pytest.mark.parametrize("tamper", ["missing", "wrong_id", "rejected"])
def test_bank_cannot_replay_missing_rejected_or_unbound_meaning_evidence(tmp_path, monkeypatch, fake_meaning_models, tamper):
    bank = copy.deepcopy(build_bank(tmp_path, monkeypatch, fake_meaning_models))
    entry = bank["entries"][0]
    if tamper == "missing":
        del entry["meaning_review"]
    elif tamper == "wrong_id":
        entry["meaning_review_id"] = "another candidate"
    else:
        entry["meaning_review"]["judgment"]["participant_roles_preserved"] = "uncertain"
    with pytest.raises(g.GrammarError, match="[Mm]eaning"):
        g.apply_grammar_bank(ORIGINAL, rate=1, seed=42, bank=bank)
