"""Bank reuse, nested doses, and fail-closed grammar judgment contracts."""

import copy
import json
from types import SimpleNamespace

import pytest

from evaluation.scripts.variants.current import create_grammar_variants as grammar


TEXT = "章节标题\n" + "".join(
    f"{i} 他带着五个人走进城里{'很久' * (i % 3)}。\n" for i in range(1, 21)
)


def verdict(candidate, **overrides):
    return {
        **{field: "yes" for field in grammar.JUDGMENT_FIELDS},
        "error_span": candidate.strip(), "explanation": "Synthetic test judgment.",
        **overrides,
    }


@pytest.fixture(autouse=True)
def clear_protection(monkeypatch):
    monkeypatch.setattr(grammar, "EXTRA_PROTECTED", None)


def proposal(edited, error_type="test_structure"):
    return {"edited_clause": edited, "error_type": error_type, "explanation": "Synthetic generator explanation."}


def response_for(request, edits):
    return {"clauses": [
        {"unit_index": clause["unit_index"], "original_clause": clause["original_clause"],
         "candidates": edits(clause["original_clause"])[:request["max_candidates_per_clause"]]}
        for clause in request["clauses"]
    ]}


@pytest.fixture
def proposals(monkeypatch):
    calls = []
    def generate(self, request):
        calls.append(copy.deepcopy(request))
        # These fixtures exercise selection, not linguistic quality.
        return response_for(request, lambda original: [
            proposal(original.replace("带着五个人", "五个人带着")),
            proposal(original.replace("带着五个人走进城里", "带着走进城里五个人")),
        ])
    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", generate)
    return calls


def make_cache(tmp_path, calls, *, offline=False, model="test-model"):
    def evaluate(request):
        calls.append(request)
        return verdict(
            request["edited_clause"],
            grammar_worsened="yes" if "城里五个人" in request["edited_clause"] else "no",
        )
    return grammar.GrammarJudgmentCache(
        tmp_path / "judgments.json", model=model, evaluator=evaluate, offline=offline,
    )


def build(tmp_path, cache, text=TEXT, rate=0.30):
    return grammar.build_grammar_bank(
        text, bank_dir=tmp_path, seed=42, max_rate=rate, cache=cache, max_candidates=2,
    )


def test_nested_doses_preserve_exact_replacements_and_weight_by_clean_length(tmp_path, proposals):
    calls = []
    bank = build(tmp_path, make_cache(tmp_path, calls))
    assert bank["target_met"]
    assert len(calls) == 2 * len(bank["entries"])
    previous = {}
    for rate in (0, .05, .10, .15, .20, .30):
        text, meta = grammar.apply_grammar_errors(TEXT, rate=rate, seed=42, bank=bank)
        selected = {e["unit_index"]: e["corrupted_text"] for e in meta["affected_units"]}
        assert previous.items() <= selected.items()
        assert text == "".join(
            selected.get(i, unit["text"]) for i, unit in enumerate(grammar.passage_units(TEXT))
        )
        assert text.startswith("章节标题\n")
        assert meta["affected_content_chars"] == sum(e["content_chars"] for e in meta["affected_units"])
        assert meta["actual_affected_rate"] == meta["affected_content_chars"] / meta["total_content_chars"]
        assert meta["target_met"]
        if selected:
            # Prefix reaches the character target without adding an extra clause.
            assert meta["affected_content_chars"] >= round(meta["total_content_chars"] * rate)
            assert meta["affected_content_chars"] - meta["affected_units"][-1]["content_chars"] < round(meta["total_content_chars"] * rate)
        else:
            assert text == TEXT
        previous = selected
    # Dose selection itself never calls the judge.
    assert len(calls) == 2 * len(bank["entries"])


def test_bank_and_rejections_are_reused_offline_even_after_bank_file_is_lost(tmp_path, proposals):
    calls = []
    bank = build(tmp_path, make_cache(tmp_path, calls))
    generation_calls = len(proposals)
    calls.clear()
    cached = make_cache(tmp_path, calls, offline=True)
    assert build(tmp_path, cached) == bank
    (tmp_path / f"bank_{bank['bank_id']}.json").unlink()
    assert build(tmp_path, cached) == bank
    assert calls == []
    assert len(proposals) == generation_calls
    assert any(
        record["judgment"]["grammar_worsened"] == "no"
        for record in cached.data["judgments"].values()
    )


def test_extending_bank_keeps_previous_prefix_and_does_not_rejudge(tmp_path, proposals):
    calls = []
    cache = make_cache(tmp_path, calls)
    smaller = build(tmp_path, cache, rate=.10)
    original_calls = list(calls)
    larger = build(tmp_path, cache, rate=.30)
    assert larger["entries"][:len(smaller["entries"])] == smaller["entries"]
    assert len({json.dumps(c, sort_keys=True) for c in calls}) == len(calls)
    assert calls[:len(original_calls)] == original_calls


def test_exhausted_bank_can_export_larger_shortfall_without_rejudging(tmp_path, proposals):
    calls = []
    def reject(request):
        calls.append(request)
        return verdict(request["edited_clause"], grammar_worsened="no")
    cache = grammar.GrammarJudgmentCache(tmp_path / "judgments.json", model="test-model", evaluator=reject)
    assert build(tmp_path, cache, rate=.10)["exhausted"]
    calls.clear()
    extended = build(tmp_path, cache, rate=.30)
    text, meta = grammar.apply_grammar_bank(TEXT, rate=.30, seed=42, bank=extended)
    assert text == TEXT
    assert meta["target_met"] is False
    assert calls == []


def test_interrupted_generation_resumes_saved_judgments(tmp_path, proposals):
    first_calls = []
    def interrupt(request):
        first_calls.append(request)
        if len(first_calls) == 3:
            raise grammar.GrammarError("simulated transport failure")
        return verdict(request["edited_clause"], grammar_worsened="yes" if "城里五个人" in request["edited_clause"] else "no")
    cache = grammar.GrammarJudgmentCache(tmp_path / "judgments.json", model="test-model", evaluator=interrupt)
    with pytest.raises(grammar.GrammarError, match="transport"):
        build(tmp_path, cache)
    assert len(proposals) == 1
    resumed_calls = []
    assert build(tmp_path, make_cache(tmp_path, resumed_calls))["target_met"]
    assert all(request not in resumed_calls for request in first_calls[:2])
    assert len(proposals) == 1


@pytest.mark.parametrize("change", ["source", "model", "prompt", "protection"])
def test_changed_inputs_do_not_reuse_stale_bank(tmp_path, proposals, monkeypatch, change):
    build(tmp_path, make_cache(tmp_path, []))
    text = TEXT
    model = "test-model"
    if change == "source":
        text = TEXT.replace("城里", "村里")
    elif change == "model":
        model = "another-model"
    elif change == "prompt":
        monkeypatch.setattr(grammar, "JUDGE_PROMPT", grammar.JUDGE_PROMPT + " Revised rubric.")
    else:
        monkeypatch.setattr(grammar, "EXTRA_PROTECTED", grammar.re.compile("五个人"))
    cache = make_cache(tmp_path, [], offline=True, model=model)
    with pytest.raises(grammar.GrammarError, match="Missing cached"):
        build(tmp_path, cache, text=text)


@pytest.mark.parametrize("candidate,operations", [
    ("祭司站城门口在了。", [grammar.LLM_OPERATION]),
    ("祭司站城门口。", [grammar.LLM_OPERATION]),
    ("祭司站城门口在。", ["local_phrase_order_disorder"]),
    ("祭司站城门口在。", [grammar.LLM_OPERATION] * 2),
    ("祭司。站城门口在", [grammar.LLM_OPERATION]),
])
def test_hard_checks_reject_filler_deletions_legacy_and_stacked_edits(candidate, operations):
    assert not grammar.valid_structural_candidate("祭司站在城门口。", candidate, operations)


def test_unsafe_llm_proposals_do_not_reach_judge(tmp_path, monkeypatch):
    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", lambda self, request:
        response_for(request, lambda original: [proposal(original + "了")]))
    calls = []
    bank = build(tmp_path, make_cache(tmp_path, calls))
    assert bank["entries"] == []
    assert bank["hard_rejected_candidate_count"] == 20
    assert calls == []


def test_llm_candidates_need_no_vocabulary_match_or_mechanical_fallback(tmp_path, monkeypatch):
    text = "".join(f"{i} 他拿走了米迦的葡萄园。\n" for i in range(1, 11))
    generated = []
    def generate(self, request):
        generated.append(request)
        return response_for(request, lambda original: [
            proposal(original.replace("米迦的葡萄园", "葡萄园米迦的"), "possessive_modifier_displacement"),
        ])
    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", generate)
    monkeypatch.setattr(grammar, "corrupt_clause", lambda *a, **kw: pytest.fail("mechanical fallback"))
    calls = []
    def evaluate(request):
        calls.append(request)
        assert "葡萄园米迦的" in request["edited_clause"]
        assert set(request) == {"original_passage", "clause_start", "original_clause", "edited_clause"}
        return verdict(request["edited_clause"])
    cache = grammar.GrammarJudgmentCache(tmp_path / "judgments.json", model="test-model", evaluator=evaluate)
    bank = build(tmp_path, cache, text=text)
    assert bank["schema_version"] == 3
    assert bank["spec"]["edit_style"] == "llm_structural_v1"
    assert bank["target_met"]
    assert len(generated) == 1
    assert len(calls) == len(bank["entries"])
    for entry in bank["entries"]:
        assert entry["proposal"]["error_type"] == "possessive_modifier_displacement"
        assert entry["proposal"]["edited_clause"] == entry["corrupted_text"]
        assert entry["proposal_id"]
    for rate in (.10, .30):
        edited, meta = grammar.apply_grammar_bank(text, rate=rate, seed=42, bank=bank)
        assert grammar.Counter(text) == grammar.Counter(edited)
        assert meta["edit_style"] == grammar.EDIT_STYLE
        assert meta["generator"]["model"] == "test-model"
        assert meta["operation_count"] == meta["affected_unit_count"]
    assert len(generated) == 1
    assert len(calls) == len(bank["entries"])


def test_duplicate_and_unchanged_llm_candidates_are_skipped(tmp_path, monkeypatch):
    def generate(self, request):
        return response_for(request, lambda original: [
            proposal(original),
            proposal(original.replace("带着五个人", "五个人带着")),
            proposal(original.replace("带着五个人", "五个人带着")),
        ])
    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", generate)
    calls = []
    bank = grammar.build_grammar_bank(TEXT, bank_dir=tmp_path, seed=42, max_rate=.30,
        cache=make_cache(tmp_path, calls), max_candidates=3)
    assert bank["entries"] == []
    assert len(calls) == 20
    assert bank["duplicate_or_noop_candidate_count"] == 40
    assert all("带着五个人" in c["original_clause"] for c in calls)


def test_empty_llm_proposals_are_cached_and_never_fall_back(tmp_path, monkeypatch):
    generated = []
    def generate(self, request):
        generated.append(request)
        return response_for(request, lambda original: [])
    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", generate)
    monkeypatch.setattr(grammar, "corrupt_clause", lambda *a, **kw: pytest.fail("mechanical fallback"))
    calls = []
    bank = build(tmp_path, make_cache(tmp_path, calls))
    assert bank["exhausted"]
    assert len(generated) == 3
    assert calls == []
    (tmp_path / f"bank_{bank['bank_id']}.json").unlink()
    generated.clear()
    assert build(tmp_path, make_cache(tmp_path, calls, offline=True)) == bank
    assert generated == []


def test_protected_term_breaking_is_filtered_before_judge(tmp_path, monkeypatch):
    text = "1 他拿走了米迦的葡萄园。"
    monkeypatch.setattr(grammar, "EXTRA_PROTECTED", grammar.re.compile("米迦"))
    def generate(self, request):
        assert request["protected_terms"] == ["米迦"]
        return response_for(request, lambda original: [proposal(original.replace("米迦的", "米的迦"))])
    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", generate)
    calls = []
    bank = build(tmp_path, make_cache(tmp_path, calls), text=text)
    assert bank["hard_rejected_candidate_count"] == 1
    assert calls == []


@pytest.mark.parametrize("candidate", ["1 人物乙没带3个人来。", "1 人物甲带3个人来。", "1 人物甲没带4个人来。", "人物甲没带3个人来。1 "])
def test_protected_placeholders_numbers_negation_and_verse_marker(candidate):
    assert not grammar.candidate_preserves_protected("1 人物甲没带3个人来。", candidate)


@pytest.mark.parametrize("overrides", [
    {"grammar_worsened": "no"}, {"grammar_worsened": "uncertain"},
    {"meaning_preserved": "no"}, {"meaning_preserved": "uncertain"},
    {"local_error": "no"}, {"local_error": "uncertain"},
    {"structural_error": "no"}, {"structural_error": "uncertain"},
    {"lexical_integrity": "no"}, {"lexical_integrity": "uncertain"},
    {"error_span": ""}, {"error_span": "invented words"},
])
def test_only_specific_local_meaning_preserving_errors_are_accepted(overrides):
    assert not grammar.judgment_accepts(verdict("我也来了。", **overrides), "我也来了。")


def test_source_or_entry_mismatch_cannot_be_applied(tmp_path, proposals):
    bank = build(tmp_path, make_cache(tmp_path, []))
    with pytest.raises(grammar.GrammarError, match="different clean passage"):
        grammar.apply_grammar_bank(TEXT + " ", rate=.10, seed=42, bank=bank)
    changed = copy.deepcopy(bank)
    changed["entries"][0]["original_text"] = "different original"
    with pytest.raises(grammar.GrammarError, match="Invalid or unapproved"):
        grammar.apply_grammar_bank(TEXT, rate=.10, seed=42, bank=changed)


def test_bank_cannot_overstate_approved_coverage(tmp_path, proposals):
    bank = build(tmp_path, make_cache(tmp_path, []))
    bank["entries"] = []
    with pytest.raises(grammar.GrammarError, match="coverage does not match"):
        grammar.apply_grammar_bank(TEXT, rate=.30, seed=42, bank=bank)


def test_bank_cannot_reuse_approval_for_different_candidate(tmp_path, proposals):
    bank = build(tmp_path, make_cache(tmp_path, []))
    bank["entries"][0]["judgment_id"] = "approval-for-another-edit"
    with pytest.raises(grammar.GrammarError, match="different edit"):
        grammar.apply_grammar_bank(TEXT, rate=.30, seed=42, bank=bank)


def test_raw_and_decanonicalized_share_identical_bank_and_export_offline(tmp_path, proposals):
    source, output = tmp_path / "source", tmp_path / "grammar"
    source.mkdir()
    for name in ("passage_target.txt", "passage_target_decanonicalized.txt"):
        (source / name).write_text(TEXT, encoding="utf-8")
    (source / "qa_target.json").write_text('{"answer": "unchanged"}', encoding="utf-8")
    calls = []
    def evaluate(request):
        calls.append(request)
        return verdict(request["edited_clause"])
    banks = grammar.prepare_grammar_banks(source, output, seed=42, bank_rate=.30, model="test-model", max_candidates=2, offline=False, evaluator=evaluate)
    assert banks["passage_target.txt"] == banks["passage_target_decanonicalized.txt"]
    assert len(calls) == len(banks["passage_target.txt"]["entries"])
    calls.clear()
    reused = grammar.prepare_grammar_banks(source, output, seed=42, bank_rate=.30, model="test-model", max_candidates=2, offline=True, evaluator=evaluate)
    for rate in (.30, .10):
        path = grammar.create_variant(source_method_dir=source, output_dir=output, rate=rate, seed=42, force=False, banks=reused)
        assert grammar.create_variant(source_method_dir=source, output_dir=output, rate=rate, seed=42, force=False, banks=reused) == path
        assert json.loads((path / "qa_target.json").read_text()) == {"answer": "unchanged"}
        meta = json.loads((path / "grammar_metadata.json").read_text())
        assert meta["generation_mode"] == "validated_bank"
        assert meta["files"]["passage_target"]["target_met"]
        translation = json.loads((path / "passage_translation.json").read_text())
        assert translation["translations"] == [(path / "passage_target.txt").read_text()]
    assert calls == []
    (output / "10%" / "decanonicalized_metadata.json").unlink()
    with pytest.raises(grammar.GrammarError, match="does not match"):
        grammar.create_variant(source_method_dir=source, output_dir=output, rate=.10, seed=42, force=False, banks=reused)
    grammar.create_variant(source_method_dir=source, output_dir=output, rate=.10, seed=42, force=True, banks=reused)
    (output / "10%" / "passage_target.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(grammar.GrammarError, match="does not match"):
        grammar.create_variant(source_method_dir=source, output_dir=output, rate=.10, seed=42, force=False, banks=reused)


@pytest.mark.parametrize("finish,refusal,content", [
    ("length", None, "{}"), ("stop", "refused", "{}"),
    ("stop", None, "not json"), ("stop", None, "{}"),
])
def test_api_failures_never_become_successful_judgments(finish, refusal, content):
    def create(**kwargs):
        assert kwargs["response_format"]["json_schema"]["strict"] is True
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason=finish, message=SimpleNamespace(refusal=refusal, content=content),
        )])
    judge = grammar.GPTGrammarJudge("test-model")
    judge.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(grammar.GrammarError):
        judge({"original_clause": "我来了。", "edited_clause": "我了来。"})


def test_real_sdk_request_contract_without_network():
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")
    request_data = {"original_passage": "1 我来了。", "original_clause": "1 我来了。", "edited_clause": "1 我了来。", "clause_start": 0}
    expected = verdict(request_data["edited_clause"])
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "test-completion", "object": "chat.completion", "created": 0,
            "model": "gpt-4o-mini", "choices": [{
                "index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(expected)},
            }],
        })
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with openai.OpenAI(api_key="test-only-not-a-real-key", http_client=http, max_retries=0) as client:
            judge = grammar.GPTGrammarJudge("gpt-4o-mini")
            judge.client = client
            assert judge(request_data) == expected
    assert len(requests) == 1
    sent = requests[0]
    assert sent["model"] == "gpt-4o-mini"
    assert sent["messages"][0]["content"] == grammar.JUDGE_PROMPT
    assert json.loads(sent["messages"][1]["content"]) == request_data
    assert sent["response_format"]["json_schema"]["schema"] == grammar.JUDGE_SCHEMA


def cli_args(tmp_path, monkeypatch, extra=()):
    monkeypatch.setattr("sys.argv", [
        "create_grammar_variants.py", "--root", str(tmp_path), "--passage-dirs", "p",
        "--source-model-dir", "_base", "--rates", "10%", "30%", *extra,
    ])
    source = tmp_path / "p" / "_base" / "llm_prompt_high"
    source.mkdir(parents=True, exist_ok=True)
    (source / "passage_target.txt").write_text(TEXT, encoding="utf-8")
    return tmp_path / "p" / "grammar"


def test_cli_shortfall_fails_without_publishing_then_explicitly_exports(tmp_path, monkeypatch, proposals, capsys):
    output = cli_args(tmp_path, monkeypatch)
    monkeypatch.setattr(grammar.GPTGrammarJudge, "__call__", lambda self, request: verdict(request["edited_clause"], grammar_worsened="no"))
    assert grammar.main() == 1
    assert "approved coverage" in capsys.readouterr().err
    assert (output / "_grammar_bank" / "judgments.json").exists()
    assert not (output / "30%").exists()
    cli_args(tmp_path, monkeypatch, ["--offline", "--allow-shortfall"])
    assert grammar.main() == 0
    meta = json.loads((output / "30%" / "grammar_metadata.json").read_text())["files"]["passage_target"]
    assert meta["target_met"] is False
    assert meta["actual_affected_rate"] == 0
    assert meta["shortfall_content_chars"] > 0
    assert (output / "30%" / "passage_target.txt").read_text() == TEXT


def test_cli_old_outputs_fail_before_evaluation(tmp_path, monkeypatch, capsys):
    output = cli_args(tmp_path, monkeypatch)
    (output / "30%").mkdir(parents=True)
    monkeypatch.setattr(grammar, "prepare_grammar_banks", lambda *a, **kw: pytest.fail("must not evaluate"))
    assert grammar.main() == 1
    assert "not bank-based" in capsys.readouterr().err


def test_cli_particle_based_bank_outputs_fail_before_new_evaluation(tmp_path, monkeypatch, capsys):
    output = cli_args(tmp_path, monkeypatch)
    (output / "30%").mkdir(parents=True)
    (output / "30%" / "grammar_metadata.json").write_text(json.dumps({
        "schema_version": 2, "generation_mode": "validated_bank", "files": {},
    }))
    monkeypatch.setattr(grammar, "prepare_grammar_banks", lambda *a, **kw: pytest.fail("must not evaluate"))
    assert grammar.main() == 1
    assert "different grammar edit style" in capsys.readouterr().err


def test_cli_clean_only_and_explicit_legacy_need_no_api(tmp_path, monkeypatch):
    output = cli_args(tmp_path, monkeypatch, ["--rates", "0%"])
    monkeypatch.setattr(grammar, "prepare_grammar_banks", lambda *a, **kw: pytest.fail("must not evaluate"))
    assert grammar.main() == 0
    assert (output / "0%" / "passage_target.txt").read_text() == TEXT
    cli_args(tmp_path, monkeypatch, ["--legacy-unvalidated"])
    assert grammar.main() == 0
    meta = json.loads((output / "30%" / "grammar_metadata.json").read_text())
    assert meta["generation_mode"] == "legacy_unvalidated"


def test_cli_highest_rate_cannot_exceed_bank(tmp_path, monkeypatch, capsys):
    cli_args(tmp_path, monkeypatch, ["--bank-rate", "20%"])
    monkeypatch.setattr(grammar, "prepare_grammar_banks", lambda *a, **kw: pytest.fail("must not evaluate"))
    assert grammar.main() == 1
    assert "highest requested" in capsys.readouterr().err


def test_clean_copy_rejects_stale_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "passage_target.txt").write_text(TEXT, encoding="utf-8")
    grammar.create_clean_copy(source, tmp_path / "output", False)
    (source / "passage_target.txt").write_text(TEXT + "new text", encoding="utf-8")
    with pytest.raises(grammar.GrammarError, match="clean variant is stale"):
        grammar.create_clean_copy(source, tmp_path / "output", False)


@pytest.mark.parametrize("rate", ["nan", "inf", "-1", "101%"])
def test_invalid_rates_rejected(rate):
    with pytest.raises(grammar.GrammarError):
        grammar.parse_rates([rate])


def proposal_request():
    return {
        "original_passage": "1 他拿走了米迦的葡萄园。\n2 他拿走了米迦的葡萄园。",
        "generation_seed": 42, "max_candidates_per_clause": 2, "protected_terms": ["米迦"],
        "clauses": [
            {"unit_index": 0, "clause_start": 0, "original_clause": "1 他拿走了米迦的葡萄园。"},
            {"unit_index": 2, "clause_start": 16, "original_clause": "2 他拿走了米迦的葡萄园。"},
        ],
    }


@pytest.mark.parametrize("problem", [
    "missing_clause", "duplicate_id", "unknown_id", "wrong_original", "too_many",
    "extra_key", "invalid_candidate", "boolean_id",
])
def test_bad_generation_response_is_not_cached(tmp_path, problem):
    request = proposal_request()
    response = response_for(request, lambda original: [proposal(original.replace("米迦的葡萄园", "葡萄园米迦的"))])
    first = response["clauses"][0]
    if problem == "missing_clause":
        response["clauses"].pop()
    elif problem == "duplicate_id":
        response["clauses"][1]["unit_index"] = first["unit_index"]
    elif problem == "unknown_id":
        first["unit_index"] = 999
    elif problem == "wrong_original":
        first["original_clause"] = "rewritten source"
    elif problem == "too_many":
        first["candidates"] *= 3
    elif problem == "extra_key":
        response["unexpected"] = True
    elif problem == "invalid_candidate":
        first["candidates"][0]["explanation"] = None
    else:
        first["unit_index"] = False
    cache = grammar.GrammarProposalCache(tmp_path / "proposals.json", model="test-model", generator=lambda request: response)
    with pytest.raises(grammar.GrammarError):
        cache.generate(request)
    assert not cache.path.exists()


@pytest.mark.parametrize("change", ["model", "prompt", "limit", "source", "protection", "seed"])
def test_generation_cache_identity_prevents_stale_proposals(tmp_path, monkeypatch, change):
    request = proposal_request()
    generated = []
    def generate(request):
        generated.append(request)
        return response_for(request, lambda original: [])
    path = tmp_path / "proposals.json"
    cache = grammar.GrammarProposalCache(path, model="test-model", generator=generate)
    cache.generate(request)
    model = "test-model"
    if change == "model":
        model = "another-generator"
    elif change == "prompt":
        monkeypatch.setattr(grammar, "PROPOSAL_PROMPT", grammar.PROPOSAL_PROMPT + " Revised instructions.")
    elif change == "limit":
        request["max_candidates_per_clause"] += 1
    elif change == "source":
        request["original_passage"] += "new context"
    elif change == "protection":
        request["protected_terms"].append("葡萄园")
    else:
        request["generation_seed"] += 1
    offline = grammar.GrammarProposalCache(path, model=model, generator=generate, offline=True)
    with pytest.raises(grammar.GrammarError, match="Missing cached grammar proposals"):
        offline.generate(request)
    assert len(generated) == 1


def test_unfinished_generation_resumes_completed_batches(tmp_path, monkeypatch):
    calls = []
    def generate(self, request):
        calls.append(copy.deepcopy(request))
        if len(calls) == 2:
            raise grammar.GrammarError("simulated generator interruption")
        return response_for(request, lambda original: [])
    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", generate)
    with pytest.raises(grammar.GrammarError, match="interruption"):
        build(tmp_path, make_cache(tmp_path, []))
    saved_request = calls[0]
    calls.clear()
    def resume(self, request):
        calls.append(request)
        return response_for(request, lambda original: [])
    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", resume)
    assert build(tmp_path, make_cache(tmp_path, []))["exhausted"]
    assert len(calls) == 2
    assert saved_request not in calls


@pytest.mark.parametrize("span", ['"对说他"', '“对说他”', "'对说他'", "对说他"])
def test_cosmetic_error_span_quotes_do_not_discard_an_otherwise_approved_edit(span):
    candidate = "米迦对说他。"
    raw = verdict(candidate, error_span=span)
    assert grammar.judgment_accepts(raw, candidate)
    assert raw["error_span"] == span  # Raw evidence is not rewritten.
    assert not grammar.judgment_accepts({**raw, "structural_error": "no"}, candidate)


def test_error_span_repair_does_not_invent_a_matching_span():
    assert not grammar.judgment_accepts(verdict("米迦对说他。", error_span='"米迦对他说。"'), "米迦对说他。")


def test_real_generator_sdk_request_contract_without_network():
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")
    request_data = proposal_request()
    expected = response_for(request_data, lambda original: [proposal(original.replace("米迦的葡萄园", "葡萄园米迦的"))])
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "test-generation", "object": "chat.completion", "created": 0,
            "model": "gpt-4o-mini", "choices": [{
                "index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(expected)},
            }],
        })
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with openai.OpenAI(api_key="test-only-not-a-real-key", http_client=http, max_retries=0) as client:
            generator = grammar.GPTGrammarProposer("gpt-4o-mini")
            generator.client = client
            assert generator(request_data) == expected
    assert len(requests) == 1
    sent = requests[0]
    assert sent["messages"][0]["content"] == grammar.PROPOSAL_PROMPT
    assert json.loads(sent["messages"][1]["content"]) == request_data
    assert sent["response_format"]["json_schema"]["schema"] == grammar.PROPOSAL_SCHEMA
    assert sent["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize("finish,refusal,content", [
    ("length", None, "{}"), ("stop", "refused", "{}"),
    ("stop", None, "not json"), ("stop", None, "{}"),
])
def test_generator_api_failures_never_fall_back_to_mechanical_changes(finish, refusal, content):
    def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason=finish, message=SimpleNamespace(refusal=refusal, content=content),
        )])
    generator = grammar.GPTGrammarProposer("test-model")
    generator.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(grammar.GrammarError):
        generator(proposal_request())


def test_cli_configures_generator_separately_and_exports_llm_metadata(tmp_path, monkeypatch):
    output = cli_args(tmp_path, monkeypatch, [
        "--generator-model", "writer-test", "--judge-model", "judge-test", "--proposal-batch-size", "2",
    ])
    def generate(self, request):
        assert self.model == "writer-test"
        assert len(request["clauses"]) <= 2
        return response_for(request, lambda original: [proposal(original.replace("带着五个人", "五个人带着"))])
    def evaluate(self, request):
        assert self.model == "judge-test"
        return verdict(request["edited_clause"])
    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", generate)
    monkeypatch.setattr(grammar.GPTGrammarJudge, "__call__", evaluate)
    assert grammar.main() == 0
    meta = json.loads((output / "30%" / "grammar_metadata.json").read_text())
    assert meta["edit_style"] == "llm_structural_v1"
    assert meta["files"]["passage_target"]["generator"]["model"] == "writer-test"
    assert meta["files"]["passage_target"]["judge"]["model"] == "judge-test"


def test_cli_refuses_template_outputs_before_generating(tmp_path, monkeypatch, capsys):
    output = cli_args(tmp_path, monkeypatch)
    (output / "30%").mkdir(parents=True)
    (output / "30%" / "grammar_metadata.json").write_text(json.dumps({
        "generation_mode": "validated_bank", "edit_style": "structural_reordering_v1",
    }))
    monkeypatch.setattr(grammar, "prepare_grammar_banks", lambda *a, **kw: pytest.fail("must not generate"))
    assert grammar.main() == 1
    assert "different grammar edit style" in capsys.readouterr().err
