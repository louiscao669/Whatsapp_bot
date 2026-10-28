"""Independent mistranslation review, cache reuse, and downstream approval gates."""

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.scripts.variants.banks import generate_mistranslation_banks as banks
from evaluation.scripts.variants.banks import mistranslation_validation as review
from evaluation.scripts.variants.current import create_mistranslation_variants as variants


TEXT = "1 他母亲说：歇息一下。\n2 他是罗马公民，没有死罪。\n3 尸首放在城门口。\n4 他母亲回家。\n"


def entry(source="他母亲", target="他妻子", mode="systematic"):
    return {"source": source, "target": target, "category": "role", "mode": mode, "rationale": "Generator rationale must not lead the judge."}


PROPOSALS = {"replacements": [
    entry(), entry("歇息", "休息", "contextual"), entry("罗马公民", "希腊公民"),
    entry("没有死罪", "有死罪", "contextual"), entry("尸首", "遗体"),
]}


def judgment(request, **overrides):
    return {"source_claim": "Original: " + request["source"],
            "replacement_claim": "Replacement: " + request["replacement"],
            "explanation": "Synthetic test judgment.",
            **{field: "yes" for field in review.JUDGMENT_FIELDS}, **overrides}


class FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        assert kwargs["model"] == "gpt-6-sol"
        assert "temperature" not in kwargs
        assert kwargs["text"]["format"]["strict"] is True
        request = json.loads(kwargs["input"])
        if kwargs["text"]["format"]["name"] == "mistranslation_proposals":
            result = copy.deepcopy(PROPOSALS)
        else:
            assert "rationale" not in request and "category" not in request
            result = judgment(request, meaning_changed="no" if request["source"] in ("歇息", "尸首") else "yes")
        return SimpleNamespace(status="completed", output=[], output_text=json.dumps(result, ensure_ascii=False),
                               model="gpt-6-sol", id=f"response-{len(self.calls)}", usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})


def build(path, client=None, **kwargs):
    return banks.build_reviewed_bank(passage=TEXT, chapter="p", cache_dir=path, client=client, **kwargs)


def test_fresh_generation_and_separate_judge_keep_only_approved_candidates(tmp_path):
    client = FakeClient()
    bank = build(tmp_path, client)
    assert len(client.calls) == 6  # One generator request, five independent reviews.
    assert {e["source"] for e in bank["replacements"]} == {"他母亲", "罗马公民", "没有死罪"}
    assert bank["generation"]["model"] == "gpt-6-sol"
    assert bank["validation"]["judge"]["model"] == "gpt-6-sol"
    assert bank["validation"]["accepted_count"] == 3
    assert bank["validation"]["rejected_count"] == 2
    review.validate_reviewed_bank(bank, TEXT)
    records = json.loads((tmp_path / "judgments.json").read_text())["records"]
    assert len(records) == 5
    assert all(record["usage"]["total_tokens"] == 120 for record in records.values())
    audit = json.loads(next(tmp_path.glob("review_*.json")).read_text())
    assert audit["status"] == "complete"
    assert sum(not c["accepted"] for c in audit["candidates"]) == 2
    assert build(tmp_path, offline=True) == bank
    assert len(client.calls) == 6


def test_existing_bank_review_preserves_generator_provenance_and_skips_generation(tmp_path):
    old = {**PROPOSALS, "generation": {"provider": "openai", "model": "gpt-4.1-mini"}}
    before = copy.deepcopy(old)
    client = FakeClient()
    bank = build(tmp_path, client, existing_bank=old)
    assert len(client.calls) == 5
    assert not (tmp_path / "proposals.json").exists()
    assert old == before
    assert bank["generation"]["model"] == "gpt-4.1-mini"
    assert bank["validation"]["judge"]["model"] == "gpt-6-sol"
    assert build(tmp_path, offline=True, existing_bank=old) == bank


def test_judge_sees_every_exact_match_in_context_without_generator_rationale():
    passage = "1 他母亲来到这里。\n2 他母亲回家。"
    request = review.review_request(passage, entry())
    assert len(request["occurrences"]) == 2
    assert set(request) == {"original_passage", "source", "replacement", "mode", "occurrences"}
    for occurrence in request["occurrences"]:
        assert passage[occurrence["start"]:occurrence["end"]] == "他母亲"
        assert "他妻子" in occurrence["edited_context"]


@pytest.mark.parametrize("field", review.JUDGMENT_FIELDS)
@pytest.mark.parametrize("decision", ["no", "uncertain"])
def test_every_failed_or_uncertain_criterion_prevents_acceptance(field, decision):
    assert not review.judgment_accepts(judgment({"source": "母亲", "replacement": "妻子"}, **{field: decision}))


def test_claims_and_explanation_are_required_even_with_all_yes():
    value = judgment({"source": "母亲", "replacement": "妻子"})
    assert not review.judgment_accepts({**value, "source_claim": ""})
    assert not review.judgment_accepts({**value, "replacement_claim": value["source_claim"]})
    with pytest.raises(review.MistranslationValidationError):
        review.judgment_accepts({"meaning_changed": "yes"})


def test_invalid_candidates_are_filtered_before_judging(tmp_path):
    client = FakeClient()
    bank = build(tmp_path, client, existing_bank={"replacements": [entry(), entry("不存在", "坏人"), entry("他母亲", "他母亲")]})
    assert len(client.calls) == 1
    assert bank["validation"]["hard_rejected_count"] == 2


@pytest.mark.parametrize("problem", ["incomplete", "refusal", "invalid_json", "missing_field", "wrong_enum"])
def test_api_errors_never_become_approvals_or_successful_cache_entries(tmp_path, problem):
    value = judgment({"source": "母亲", "replacement": "妻子"})
    if problem == "missing_field":
        value.pop("fluent")
    if problem == "wrong_enum":
        value["fluent"] = True
    response = SimpleNamespace(
        status="incomplete" if problem == "incomplete" else "completed",
        output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])] if problem == "refusal" else [],
        output_text="broken" if problem == "invalid_json" else json.dumps(value),
    )
    cache = review.StructuredResponseCache(tmp_path / "judgments.json", model="gpt-6-sol", prompt=review.JUDGE_PROMPT,
        schema=review.JUDGE_SCHEMA, name="mistranslation_judgment", max_output_tokens=8192,
        client=SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: response)))
    with pytest.raises(review.MistranslationValidationError):
        cache.get(review.review_request(TEXT, entry()))
    assert not cache.path.exists()


def test_interrupted_review_resumes_without_regenerating_or_rejudging(tmp_path):
    first = FakeClient()
    normal = first.create

    def fail(**kwargs):
        if len(first.calls) == 3:
            raise RuntimeError("simulated interruption")
        return normal(**kwargs)

    first.responses.create = fail
    with pytest.raises(RuntimeError, match="interruption"):
        build(tmp_path, first)
    second = FakeClient()
    bank = build(tmp_path, second)
    assert len(second.calls) == 3
    assert all(c["text"]["format"]["name"] == "mistranslation_judgment" for c in second.calls)
    assert len(bank["replacements"]) == 3


@pytest.mark.parametrize("change", ["source", "judge", "generator", "rubric", "limit"])
def test_changed_inputs_cannot_reuse_old_responses_offline(tmp_path, monkeypatch, change):
    build(tmp_path, FakeClient())
    kwargs = {"passage": TEXT, "chapter": "p", "cache_dir": tmp_path, "offline": True}
    if change == "source":
        kwargs["passage"] += "新内容。"
    elif change == "judge":
        kwargs["judge_model"] = "different-model"
    elif change == "generator":
        kwargs["model"] = "different-model"
    elif change == "rubric":
        monkeypatch.setattr(banks, "JUDGE_PROMPT", banks.JUDGE_PROMPT + "Changed rubric.")
    else:
        kwargs["max_items"] = 81
    with pytest.raises(review.MistranslationValidationError, match="Missing cached"):
        banks.build_reviewed_bank(**kwargs)


@pytest.mark.parametrize("change", ["target", "source_text", "decision", "judge", "bank_id"])
def test_renderer_refuses_stale_or_tampered_approvals(tmp_path, change):
    bank = build(tmp_path, FakeClient())
    text = TEXT
    if change == "target":
        bank["replacements"][0]["target"] = "他父亲"
    elif change == "source_text":
        text += "新内容。"
    elif change == "decision":
        bank["replacements"][0]["review"]["judgment"]["meaning_changed"] = "no"
    elif change == "judge":
        bank["validation"]["judge"]["model"] = "unrecorded-judge"
    else:
        bank["bank_id"] = "invalid"
    with pytest.raises(variants.MistranslationError):
        variants.apply_mistranslations(text, rate=.30, seed=1, bank=bank)


def setup_source(root):
    source = root / "p" / "_base" / "llm_prompt_high"
    source.mkdir(parents=True)
    for name in ("passage_target.txt", "passage_target_decanonicalized.txt"):
        (source / name).write_text(TEXT)
    (source / "qa_target.json").write_text('{"correct":"unchanged"}')
    return source


def cli(root, extra=()):
    return ["--root", str(root), "--passage-dirs", "p", "--source-model-dir", "_base", "--output-name", "sol.json", *extra]


def test_cli_defaults_to_sol_and_refuses_legacy_bank_reuse_before_api(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_TRANSLATION_MODEL", "gpt-4.1-mini")
    monkeypatch.delenv("OPENAI_MISTRANSLATION_GENERATOR_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MISTRANSLATION_JUDGE_MODEL", raising=False)
    parsed = banks.parse_args([])
    assert parsed.model == parsed.judge_model == "gpt-6-sol"
    source = setup_source(tmp_path)
    path = source.parent / "_shared" / "sol.json"
    path.parent.mkdir()
    path.write_text(json.dumps(PROPOSALS))
    before = path.read_bytes()
    assert banks.main(cli(tmp_path, ["--offline"])) == 1
    assert path.read_bytes() == before


def test_cli_generates_and_exports_approved_bank_then_replays_without_key(tmp_path, monkeypatch):
    openai = pytest.importorskip("openai")
    source = setup_source(tmp_path)
    client = FakeClient()
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    assert banks.main(cli(tmp_path)) == 0
    shared = source.parent / "_shared"
    bank = json.loads((shared / "sol.json").read_text())
    assert bank["schema_version"] == 2
    monkeypatch.delenv("OPENAI_API_KEY")
    before = len(client.calls)
    assert banks.main(cli(tmp_path, ["--offline"])) == 0
    assert banks.main(cli(tmp_path, ["--offline", "--force"])) == 0
    assert len(client.calls) == before
    output = tmp_path / "p" / "variants"
    variant = variants.create_variant(source_method_dir=source, output_dir=output, rate=.30, seed=1, bank=bank, force=False)
    meta = json.loads((variant / "mistranslation_metadata.json").read_text())
    assert meta["bank_validation"]["judge"]["model"] == "gpt-6-sol"
    assert meta["bank_id"] == bank["bank_id"]
    assert (variant / "qa_target.json").read_bytes() == (source / "qa_target.json").read_bytes()
    assert variants.create_variant(source_method_dir=source, output_dir=output, rate=.30, seed=1, bank=bank, force=False) == variant
    (variant / "passage_target.txt").write_text("stale output")
    with pytest.raises(variants.MistranslationError, match="stale"):
        variants.create_variant(source_method_dir=source, output_dir=output, rate=.30, seed=1, bank=bank, force=False)


def test_cli_review_only_preserves_old_bank_and_reports_all_rejected(tmp_path, monkeypatch):
    openai = pytest.importorskip("openai")
    source = setup_source(tmp_path)
    shared = source.parent / "_shared"
    shared.mkdir()
    old = shared / "old.json"
    old.write_text(json.dumps({"generation": {"model": "gpt-4.1-mini"}, "replacements": [entry("歇息", "休息")]}))
    before = old.read_bytes()
    client = FakeClient()
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    assert banks.main(cli(tmp_path, ["--review-existing-bank-name", "old.json"])) == 1
    assert old.read_bytes() == before
    assert not (shared / "sol.json").exists()
    assert len(client.calls) == 1
    assert next((shared / "_mistranslation_review").glob("review_*.json")).exists()


def test_require_judged_bank_refuses_unreviewed_input_before_export(tmp_path, monkeypatch):
    source = setup_source(tmp_path)
    shared = source.parent / "_shared"
    shared.mkdir()
    (shared / "mistranslation_bank_zh.json").write_text(json.dumps(PROPOSALS))
    monkeypatch.setattr("sys.argv", ["create_mistranslation_variants.py", "--root", str(tmp_path),
        "--passage-dirs", "p", "--source-model-dir", "_base", "--require-judged-bank"])
    assert variants.main() == 1
    assert not (tmp_path / "p" / "mistranslation").exists()


def test_reviewed_bank_cannot_authorize_a_different_decanonicalized_source(tmp_path):
    source = setup_source(tmp_path)
    bank = build(tmp_path / "cache", FakeClient())
    (source / "passage_target_decanonicalized.txt").write_text(TEXT + "额外的句子。")
    output = tmp_path / "variants"
    with pytest.raises(review.MistranslationValidationError, match="different clean passage"):
        variants.create_variant(source_method_dir=source, output_dir=output, rate=.30, seed=1, bank=bank, force=False)
    assert not output.exists()


def test_require_judged_bank_missing_source_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["create_mistranslation_variants.py", "--root", str(tmp_path),
        "--passage-dirs", "missing", "--source-model-dir", "_base", "--require-judged-bank"])
    assert variants.main() == 1


def test_real_sdk_responses_contract_with_mock_transport(tmp_path):
    openai, httpx = pytest.importorskip("openai"), pytest.importorskip("httpx")
    requests = []
    expected = judgment({"source": "他母亲", "replacement": "他妻子"})

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0, "status": "completed", "model": "gpt-6-sol",
            "output": [{"id": "msg_test", "type": "message", "status": "completed", "role": "assistant",
                        "content": [{"type": "output_text", "text": json.dumps(expected), "annotations": []}]}],
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                      "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 5}},
        })

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with openai.OpenAI(api_key="test-only-placeholder", http_client=http, max_retries=0) as client:
            cache = review.StructuredResponseCache(tmp_path / "judgments.json", model="gpt-6-sol", prompt=review.JUDGE_PROMPT,
                schema=review.JUDGE_SCHEMA, name="mistranslation_judgment", max_output_tokens=8192, client=client)
            _, actual = cache.get(review.review_request(TEXT, entry()))
    assert actual == expected
    assert requests[0]["model"] == "gpt-6-sol"
    assert "temperature" not in requests[0]
    assert requests[0]["text"]["format"]["schema"] == review.JUDGE_SCHEMA
    record = next(iter(json.loads(cache.path.read_text())["records"].values()))
    assert record["usage"]["output_tokens_details"]["reasoning_tokens"] == 5


class RefillClient(FakeClient):
    """Scripted batches exercise orchestration without making paid model calls."""

    def __init__(self, batches, rejected_pairs=None):
        super().__init__()
        self.batches = batches
        self.rejected_pairs = rejected_pairs or {("歇息", "休息"), ("尸首", "遗体")}

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        assert kwargs["model"] == "gpt-6-sol"
        assert kwargs["text"]["format"]["strict"] is True
        request = json.loads(kwargs["input"])
        if kwargs["text"]["format"]["name"] == "mistranslation_proposals":
            result = {"replacements": copy.deepcopy(self.batches[request.get("refill_round", 0)])}
            assert len(result["replacements"]) <= request["max_items"]
            assert kwargs["text"]["format"]["schema"] == banks.proposal_schema(request["max_items"])
        else:
            # Neither adaptive feedback nor other candidates may lead the judge.
            assert set(request) == {"original_passage", "source", "replacement", "mode", "occurrences"}
            rejected = (request["source"], request["replacement"]) in self.rejected_pairs
            result = judgment(request, meaning_changed="no" if rejected else "yes",
                              explanation="Equivalent wording, no changed fact." if rejected else "Changes one fact.")
        return SimpleNamespace(status="completed", output=[], output_text=json.dumps(result, ensure_ascii=False),
                               model="gpt-6-sol", id=f"response-{len(self.calls)}",
                               usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})


def proposal_calls(client):
    return [c for c in client.calls if c["text"]["format"]["name"] == "mistranslation_proposals"]


def test_refill_supplies_all_attempted_pairs_and_specific_rejections_then_reviews_only_new_pairs(tmp_path):
    initial = PROPOSALS["replacements"] + [entry("不存在", "坏人"), entry(mode="contextual")]
    client = RefillClient([
        initial,
        [entry(" 他母亲 ", " 他妻子 ", "contextual"), entry("歇息", "休息"),
         entry("不存在", "坏人"), entry("歇息", "工作", "contextual")],
        [entry("城门口", "山顶"), entry("回家", "离家"), entry("尸首", "伤者")],
    ])
    bank = build(tmp_path, client, max_items=7, target_candidates=7, max_refill_rounds=3)
    assert bank["refill"] == {"target_candidates": 7, "max_refill_rounds": 3, "refill_rounds_used": 2,
                              "target_met": True, "shortfall": 0, "stop_reason": "target_met"}
    assert len(bank["replacements"]) == 7
    assert bank["validation"]["rejected_count"] == 2
    assert bank["validation"]["hard_rejected_count"] == 1
    calls = proposal_calls(client)
    assert len(calls) == 3
    first = json.loads(calls[1]["input"])
    assert first["max_items"] == first["remaining_candidates"] == 4
    assert calls[1]["instructions"] == banks.REFILL_PROMPT
    history = {(e["source"], e["target"]): e for e in first["previously_attempted_pairs"]}
    assert len(history) == 6
    assert history[("他母亲", "他妻子")]["status"] == "accepted"
    assert history[("他母亲", "他妻子")]["rejection_reasons"] == []
    assert history[("不存在", "坏人")]["status"] == "hard_rejected"
    assert "exact substring" in " ".join(history[("不存在", "坏人")]["rejection_reasons"])
    rejection = history[("歇息", "休息")]
    assert rejection["status"] == "judge_rejected"
    assert "meaning_changed=no" in rejection["rejection_reasons"]
    assert "Equivalent wording" in " ".join(rejection["rejection_reasons"])
    second = json.loads(calls[2]["input"])
    assert second["max_items"] == 3
    assert len(second["previously_attempted_pairs"]) == 7
    assert any(e["source"] == "歇息" and e["target"] == "工作" for e in bank["replacements"])
    judged = [json.loads(c["input"]) for c in client.calls if c not in calls]
    pairs = [(r["source"], r["replacement"]) for r in judged]
    assert len(pairs) == len(set(pairs)) == 9
    audit = json.loads(Path(bank["validation"]["review_file"]).read_text())
    assert len(audit["duplicates"]) == 4
    assert [r["accepted_count"] for r in audit["rounds"]] == [3, 1, 3]
    review.validate_reviewed_bank(bank, TEXT)
    assert build(tmp_path, offline=True, max_items=7, target_candidates=7, max_refill_rounds=3) == bank
    cached = json.loads((tmp_path / "refill_proposals.json").read_text())["records"]
    assert len(cached) == 2
    assert all(key == review.digest({"identity": row["identity"], "request": row["request"]})
               for key, row in cached.items())


@pytest.mark.parametrize("first_batch", [[], [entry("不存在", "坏人")], [entry("歇息", "休息")]])
def test_refill_can_recover_when_initial_batch_has_no_approvals(tmp_path, first_batch):
    client = RefillClient([first_batch, [entry()]])
    bank = build(tmp_path, client, max_items=2, target_candidates=1)
    assert bank["refill"]["target_met"]
    assert bank["refill"]["refill_rounds_used"] == 1
    assert len(proposal_calls(client)) == 2


@pytest.mark.parametrize("target", [None, 2, 3])
def test_no_refill_without_target_or_when_initial_batch_already_meets_it(tmp_path, target):
    client = RefillClient([PROPOSALS["replacements"]])
    bank = build(tmp_path, client, target_candidates=target)
    assert len(proposal_calls(client)) == 1
    assert len(bank["replacements"]) == 3  # Target is a minimum; review the entire initial batch.
    if target is not None:
        assert bank["refill"]["refill_rounds_used"] == 0


@pytest.mark.parametrize("budget", [0, 1, 3])
def test_refill_budget_bounds_empty_and_duplicate_batches_without_relaxing_approval(tmp_path, budget):
    client = RefillClient([PROPOSALS["replacements"], [], [entry(mode="contextual")], [entry("歇息", "休息")]])
    bank = build(tmp_path, client, target_candidates=5, max_refill_rounds=budget)
    assert len(proposal_calls(client)) == 1 + budget
    assert len(client.calls) == 6 + budget  # Five unique judged pairs, no repeat reviews.
    assert bank["refill"]["refill_rounds_used"] == budget
    assert bank["refill"]["target_met"] is False
    assert bank["refill"]["shortfall"] == 2
    assert bank["refill"]["stop_reason"] == "round_limit_reached"
    assert len(bank["replacements"]) == 3
    review.validate_reviewed_bank(bank, TEXT)
    audit = json.loads(Path(bank["validation"]["review_file"]).read_text())
    assert audit["status"] == "target_not_met"


def test_all_rounds_rejected_raise_with_audit_and_can_replay_offline(tmp_path):
    client = RefillClient([[entry("歇息", "休息")], [], [entry("尸首", "遗体")]])
    kwargs = dict(max_items=1, target_candidates=1, max_refill_rounds=2)
    with pytest.raises(banks.BankGenerationError, match="0/1 after 3 batch"):
        build(tmp_path, client, **kwargs)
    assert len(client.calls) == 5
    audit = json.loads(next(tmp_path.glob("review_*.json")).read_text())
    assert audit["refill"]["shortfall"] == 1
    assert audit["rejected_count"] == 2
    with pytest.raises(banks.BankGenerationError, match="No candidates passed"):
        build(tmp_path, offline=True, **kwargs)


@pytest.mark.parametrize("fail_at", [1, 2])
def test_interruption_during_refill_resumes_without_repeating_completed_calls(tmp_path, fail_at):
    batches = [[entry("歇息", "休息")], [entry(), entry("城门口", "山顶")]]
    kwargs = dict(max_items=2, target_candidates=2, max_refill_rounds=1)
    client = RefillClient(batches)
    normal = client.create

    def fail(**request):
        # After the initial proposal+judge: fail at refill generation or second review.
        if len(client.calls) == (2 if fail_at == 1 else 4):
            raise RuntimeError("simulated refill interruption")
        return normal(**request)

    client.responses.create = fail
    with pytest.raises(RuntimeError, match="refill interruption"):
        build(tmp_path, client, **kwargs)
    before = copy.deepcopy(client.calls)
    resumed = RefillClient(batches)
    bank = build(tmp_path, resumed, **kwargs)
    combined = before + resumed.calls
    assert len(combined) == 5  # Two proposals and three unique reviews, only once each.
    assert len({(c["instructions"], c["input"]) for c in combined}) == 5
    assert bank["refill"]["target_met"]
    assert build(tmp_path, offline=True, **kwargs) == bank


def test_increasing_round_budget_reuses_prior_rounds_and_only_calls_new_batch(tmp_path):
    batches = [[entry()], [entry("歇息", "休息")], [entry("城门口", "山顶")]]
    first = RefillClient(batches)
    partial = build(tmp_path, first, max_items=1, target_candidates=2, max_refill_rounds=1)
    assert partial["refill"]["target_met"] is False
    second = RefillClient(batches)
    completed = build(tmp_path, second, max_items=1, target_candidates=2, max_refill_rounds=2)
    assert completed["configuration"] != partial["configuration"]
    assert len(second.calls) == 2
    assert json.loads(proposal_calls(second)[0]["input"])["refill_round"] == 2
    assert completed["refill"]["target_met"]
    assert completed["replacements"][0] == partial["replacements"][0]


def test_changed_refill_prompt_cannot_reuse_old_refill_responses(tmp_path, monkeypatch):
    batches = [[entry("歇息", "休息")], [entry()]]
    kwargs = dict(max_items=1, target_candidates=1, max_refill_rounds=1)
    build(tmp_path, RefillClient(batches), **kwargs)
    monkeypatch.setattr(banks, "REFILL_PROMPT", banks.REFILL_PROMPT + "Changed instructions.")
    with pytest.raises(review.MistranslationValidationError, match="Missing cached"):
        build(tmp_path, offline=True, **kwargs)


@pytest.mark.parametrize("options", [
    {"target_candidates": 0}, {"max_refill_rounds": -1},
    {"target_candidates": 2, "existing_bank": PROPOSALS},
])
def test_invalid_refill_options_fail_before_api(tmp_path, options):
    client = RefillClient([])
    with pytest.raises(banks.BankGenerationError):
        build(tmp_path, client, **options)
    assert client.calls == []


def test_cli_saves_partial_bank_but_exits_nonzero_on_creation_and_reuse_then_extends(tmp_path, monkeypatch, capsys):
    openai = pytest.importorskip("openai")
    source = setup_source(tmp_path)
    client = RefillClient([[entry()], [entry("歇息", "休息")], [entry("城门口", "山顶")]])
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    options = ["--max-items", "1", "--target-candidates", "2", "--max-refill-rounds", "1"]
    assert banks.main(cli(tmp_path, options)) == 1
    path = source.parent / "_shared" / "sol.json"
    partial = json.loads(path.read_text())
    assert partial["refill"]["shortfall"] == 1
    review.validate_reviewed_bank(partial, TEXT)
    assert "Target unmet: 1/2" in capsys.readouterr().err
    monkeypatch.delenv("OPENAI_API_KEY")
    before = len(client.calls)
    assert banks.main(cli(tmp_path, [*options, "--offline"])) == 1
    assert banks.main(cli(tmp_path, [*options, "--offline", "--force"])) == 1
    assert len(client.calls) == before
    assert json.loads(path.read_text()) == partial
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    extended = [*options[:-1], "2"]
    assert banks.main(cli(tmp_path, extended)) == 1  # Explicit overwrite required when changing settings.
    assert len(client.calls) == before
    assert banks.main(cli(tmp_path, [*extended, "--force"])) == 0
    assert len(client.calls) == before + 2
    completed = json.loads(path.read_text())
    assert completed["refill"]["target_met"]
    monkeypatch.delenv("OPENAI_API_KEY")
    assert banks.main(cli(tmp_path, [*extended, "--offline"])) == 0


def test_cli_rejects_refill_with_review_only_before_loading_any_passages(tmp_path, capsys):
    assert banks.main(cli(tmp_path, ["--target-candidates", "3", "--review-existing-bank-name", "old.json"])) == 1
    assert "review-only mode never generates" in capsys.readouterr().err


def test_feedback_explains_uncertainty_and_claim_validation_failures():
    value = judgment({"source": "母亲", "replacement": "妻子"}, fluent="uncertain", source_claim="", replacement_claim="")
    reasons = banks.judgment_rejection_reasons(value)
    assert "fluent=uncertain" in reasons
    assert "Missing nonempty source_claim." in reasons
    assert any("identical" in reason for reason in reasons)


@pytest.mark.parametrize("candidate, fragment", [
    (entry("他母亲", "他母亲"), "identical"),
    (entry("他母亲", "角色99"), "invents placeholder"),
    (entry("他母亲", "__PLACEHOLDER__"), "protected"),
    (entry("他母亲", "妻" * 31), "exceeds"),
    (entry("", "妻子"), "nonempty"),
    (entry("。", "！"), "content characters"),
])
def test_deterministic_rejections_explain_the_actual_failure(candidate, fragment):
    assert fragment in " ".join(banks.hard_rejection_reasons(candidate, TEXT))
    assert banks.normalize_replacement(candidate, TEXT) is None


@pytest.mark.parametrize("length, target, initial", [
    (173, 10, 15), (200, 10, 15), (201, 11, 17), (301, 16, 24),
    (1483, 75, 80), (1941, 98, 80),
])
def test_auto_target_scales_by_content_length_with_rounding_floor_and_batch_cap(length, target, initial):
    plan = banks.candidate_plan(passage="甲" * length, max_items=80, target_candidates="auto")
    assert plan["target_candidates"] == target
    assert plan["initial_max_items"] == initial
    assert plan["length_policy"]["content_characters"] == length


def test_auto_target_uses_renderer_content_metric_and_configurable_density():
    passage = "甲乙，丙丁。 \n戊！"
    assert banks.content_len(passage) == 5
    plan = banks.candidate_plan(passage=passage, max_items=80, target_candidates="auto",
                                chars_per_candidate=2, min_target_candidates=1)
    assert plan["target_candidates"] == 3
    assert plan["initial_max_items"] == 5
    fixed = banks.candidate_plan(passage=passage, max_items=80, target_candidates=20,
                                 chars_per_candidate=2, min_target_candidates=30)
    assert fixed["target_candidates"] == 20
    assert fixed["initial_max_items"] == 80  # Preserve explicitly requested fixed-mode behavior.
    assert fixed["length_policy"] is None


@pytest.mark.parametrize("options", [
    {"chars_per_candidate": 0}, {"min_target_candidates": 0},
    {"chars_per_candidate": -1}, {"target_candidates": "invalid"},
    {"target_candidates": "auto", "existing_bank": PROPOSALS},
])
def test_bad_auto_target_settings_fail_before_api(tmp_path, options):
    client = RefillClient([])
    with pytest.raises(banks.BankGenerationError):
        build(tmp_path, client, **options)
    assert client.calls == []


def test_auto_target_rejects_passages_without_content_before_api(tmp_path):
    client = RefillClient([])
    with pytest.raises(banks.BankGenerationError, match="no content characters"):
        banks.build_reviewed_bank(passage="。！ \n", chapter="empty", cache_dir=tmp_path,
                                   target_candidates="auto", client=client)
    assert client.calls == []


def test_auto_target_scales_initial_request_and_refills_to_resolved_target_then_replays(tmp_path):
    client = RefillClient([[entry(), entry("歇息", "休息")], [entry("城门口", "山顶")]])
    kwargs = dict(target_candidates="auto", chars_per_candidate=100, min_target_candidates=2)
    bank = build(tmp_path, client, **kwargs)
    assert bank["refill"]["target_candidates"] == 2
    assert bank["refill"]["target_met"]
    spec = bank["configuration"]
    assert spec["candidate_target_policy"]["content_characters"] == banks.content_len(TEXT)
    assert spec["candidate_target_policy"]["chars_per_candidate"] == 100
    assert spec["refill"]["target_candidates"] == 2
    assert spec["max_items"] == 80
    assert spec["initial_max_items"] == 3
    assert spec["generation_schema_sha256"] == review.digest(banks.proposal_schema(3))
    initial, refill = [json.loads(c["input"]) for c in proposal_calls(client)]
    assert initial["max_items"] == 3
    assert refill["max_items"] == refill["remaining_candidates"] == 1
    assert refill["target_candidates"] == 2
    assert build(tmp_path, offline=True, **kwargs) == bank
    review.validate_reviewed_bank(bank, TEXT)


def test_dry_run_prints_separate_length_targets_without_api_or_writes(tmp_path, monkeypatch, capsys):
    setup_source(tmp_path)
    second = tmp_path / "long" / "_base" / "llm_prompt_high"
    second.mkdir(parents=True)
    # Exercise the same raw-text fallback as a real run.
    (second / "passage_target.txt").write_text("甲" * 1001)
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    args = [*cli(tmp_path), "--passage-dirs", "p", "long", "--target-candidates", "auto", "--dry-run"]
    assert banks.main(args) == 0
    output = capsys.readouterr().out
    assert "plan p:" in output and "target=10 approved mappings; initial proposals <= 15" in output
    assert "plan long: 1001 content characters; target=51 approved mappings; initial proposals <= 77" in output
    after = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after


def test_cli_auto_target_preserves_resolved_policy_and_requires_same_settings_for_reuse(tmp_path, monkeypatch):
    openai = pytest.importorskip("openai")
    source = setup_source(tmp_path)
    client = RefillClient([[entry(), entry("歇息", "休息")], [entry("城门口", "山顶")]])
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    options = ["--target-candidates", "auto", "--chars-per-candidate", "100", "--min-target-candidates", "2"]
    assert banks.main(cli(tmp_path, options)) == 0
    bank_path = source.parent / "_shared" / "sol.json"
    bank = json.loads(bank_path.read_text())
    assert bank["refill"]["target_candidates"] == 2
    assert bank["configuration"]["candidate_target_policy"]["chars_per_candidate"] == 100
    monkeypatch.delenv("OPENAI_API_KEY")
    before = len(client.calls)
    assert banks.main(cli(tmp_path, [*options, "--offline"])) == 0
    assert banks.main(cli(tmp_path, [*options, "--offline", "--force"])) == 0
    assert len(client.calls) == before
    assert json.loads(bank_path.read_text()) == bank
    # Even a changed policy yielding the same count must not silently reuse the bank.
    assert banks.main(cli(tmp_path, [*options, "--chars-per-candidate", "101", "--offline"])) == 1
    assert json.loads(bank_path.read_text()) == bank


def test_cli_parses_auto_and_retains_numeric_targets():
    assert banks.parse_args(["--target-candidates", "auto"]).target_candidates == "auto"
    assert banks.parse_args(["--target-candidates", "20"]).target_candidates == 20
    with pytest.raises(SystemExit):
        banks.parse_args(["--target-candidates", "automatic"])


def test_concurrent_judgments_overlap_preserve_every_cache_record_and_keep_refill_order(tmp_path):
    # All five initial reviews must enter together; a cache lock held across the
    # network call would time out this barrier and fail the test.
    gate = threading.Barrier(5, timeout=5)
    client = RefillClient([PROPOSALS["replacements"], [entry("回家", "离家")]])
    normal = client.create
    completion_order = []
    calls_lock = threading.Lock()
    fast_done = threading.Event()

    def concurrent(**kwargs):
        request = json.loads(kwargs["input"])
        if kwargs["text"]["format"]["name"] == "mistranslation_judgment" and request["source"] != "回家":
            gate.wait()
            if request["source"] == "他母亲":  # First in stable order, last to complete.
                assert fast_done.wait(5)
            with calls_lock:
                result = normal(**kwargs)
                completion_order.append(request["source"])
                if request["source"] != "他母亲":
                    fast_done.set()
            return result
        with calls_lock:
            return normal(**kwargs)

    client.responses.create = concurrent
    bank = build(tmp_path, client, judge_workers=5, target_candidates=4)
    assert completion_order[0] != "他母亲"
    assert bank["replacements"][0]["source"] == "他母亲"
    assert bank["refill"]["target_met"]
    records = json.loads((tmp_path / "judgments.json").read_text())["records"]
    assert len(records) == 6
    assert sum(r["usage"]["total_tokens"] for r in records.values()) == 720
    refill_request = json.loads(proposal_calls(client)[1]["input"])
    assert len(refill_request["previously_attempted_pairs"]) == 5
    assert refill_request["previously_attempted_pairs"][0]["source"] == "他母亲"
    # Changing worker count is operational only: it changes neither requests nor bank IDs.
    assert build(tmp_path, offline=True, judge_workers=1, target_candidates=4) == bank
    assert build(tmp_path, offline=True, judge_workers=3, target_candidates=4) == bank


def test_concurrent_duplicate_cache_requests_make_one_model_call(tmp_path):
    client = FakeClient()
    cache = review.StructuredResponseCache(
        tmp_path / "judgments.json", model="gpt-6-sol", prompt=review.JUDGE_PROMPT,
        schema=review.JUDGE_SCHEMA, name="mistranslation_judgment", max_output_tokens=8192, client=client,
    )
    gate = threading.Barrier(8, timeout=5)
    request = review.review_request(TEXT, entry())

    def fetch():
        gate.wait()
        return cache.get(request)

    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: fetch(), range(8)))
    assert all(value == values[0] for value in values)
    assert len(client.calls) == 1
    assert len(json.loads(cache.path.read_text())["records"]) == 1


def test_concurrent_failure_keeps_completed_responses_and_resume_only_retries_missing_judgment(tmp_path):
    gate = threading.Barrier(5, timeout=5)
    client = RefillClient([PROPOSALS["replacements"]])
    normal = client.create
    lock = threading.Lock()

    def fail_one(**kwargs):
        request = json.loads(kwargs["input"])
        if kwargs["text"]["format"]["name"] == "mistranslation_judgment":
            gate.wait()
            if request["source"] == "罗马公民":
                raise RuntimeError("simulated concurrent API error")
        with lock:
            return normal(**kwargs)

    client.responses.create = fail_one
    with pytest.raises(RuntimeError, match="concurrent API error"):
        build(tmp_path, client, judge_workers=5)
    records = json.loads((tmp_path / "judgments.json").read_text())["records"]
    assert len(records) == 4
    assert all(r["request"]["source"] != "罗马公民" for r in records.values())
    resumed = RefillClient([PROPOSALS["replacements"]])
    bank = build(tmp_path, resumed, judge_workers=3)
    assert len(resumed.calls) == 1
    assert json.loads(resumed.calls[0]["input"])["source"] == "罗马公民"
    assert build(tmp_path, offline=True) == bank


def test_parallel_passages_use_separate_caches_and_finish_other_passages_after_one_failure(tmp_path, monkeypatch):
    openai = pytest.importorskip("openai")
    setup_source(tmp_path)
    second = tmp_path / "q" / "_base" / "llm_prompt_high"
    second.mkdir(parents=True)
    (second / "passage_target.txt").write_text(TEXT + "不同的背景。")
    gate = threading.Barrier(2, timeout=5)
    client = RefillClient([[entry()]])
    normal = client.create
    lock = threading.Lock()

    def overlapping_passages(**kwargs):
        if kwargs["text"]["format"]["name"] == "mistranslation_proposals":
            gate.wait()
        with lock:
            return normal(**kwargs)

    client.responses.create = overlapping_passages
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    args = [*cli(tmp_path), "--passage-dirs", "missing", "p", "q", "--passage-workers", "2", "--judge-workers", "3"]
    assert banks.main(args) == 1
    for name in ("p", "q"):
        shared = tmp_path / name / "_base" / "_shared"
        assert (shared / "sol.json").exists()
        assert len(json.loads((shared / "_mistranslation_review" / "judgments.json").read_text())["records"]) == 1
    assert len(client.calls) == 4
    monkeypatch.delenv("OPENAI_API_KEY")
    assert banks.main([*cli(tmp_path), "--passage-dirs", "p", "q", "--passage-workers", "1", "--offline"]) == 0
    assert len(client.calls) == 4


@pytest.mark.parametrize("flag, count", [("--judge-workers", "0"), ("--judge-workers", "9"),
                                         ("--passage-workers", "0"), ("--passage-workers", "9")])
def test_invalid_concurrency_is_rejected_before_work(tmp_path, flag, count, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid worker settings must not start passage processing")
    monkeypatch.setattr(banks, "process_passage", forbidden)
    assert banks.main([*cli(tmp_path), flag, count]) == 1


def test_invalid_direct_judge_workers_is_rejected_before_api(tmp_path):
    client = RefillClient([])
    with pytest.raises(banks.BankGenerationError, match="workers"):
        build(tmp_path, client, judge_workers=0)
    assert client.calls == []


@pytest.mark.parametrize("paths", [("p", "p"), ("p", "./p")])
def test_aliasing_passage_paths_are_rejected_before_competing_writes(tmp_path, paths, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Aliased paths must not start concurrent passage processing")
    monkeypatch.setattr(banks, "process_passage", forbidden)
    assert banks.main([*cli(tmp_path), "--passage-dirs", *paths, "--passage-workers", "2"]) == 1
