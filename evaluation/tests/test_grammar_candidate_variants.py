"""Candidate pool expansion and nested selection without live model calls."""

import copy
import json
from itertools import product

import pytest

from evaluation.scripts.variants.current import create_grammar_candidate_variants as candidates
from evaluation.scripts.variants.current import create_grammar_variants as grammar


RATES = [0, .05, .10, .15, .20, .30]
TEXT = "".join(f"{i} 他带着五个人走进城里。\n" for i in range(1, 21))


def weight_bank(weights, total):
    return {"entries": [{"content_chars": w} for w in weights], "total_content_chars": total, "max_rate": .30}


@pytest.fixture
def fake_models(monkeypatch, fake_meaning_models):
    calls = {"generation": [], "judgment": []}
    monkeypatch.setattr(grammar, "EXTRA_PROTECTED", None)

    def propose(self, request):
        calls["generation"].append(copy.deepcopy(request))
        return {"clauses": [
            {"unit_index": clause["unit_index"], "original_clause": clause["original_clause"], "candidates": [{
                "edited_clause": clause["original_clause"].replace("带着五个人", "五个人带着"),
                "error_type": "synthetic", "explanation": "Synthetic test proposal.",
            }]}
            for clause in request["clauses"]
        ]}

    def judge(self, request):
        calls["judgment"].append(copy.deepcopy(request))
        return {**{field: "yes" for field in grammar.JUDGMENT_FIELDS},
                "error_span": request["edited_clause"].strip(), "explanation": "Synthetic test approval."}

    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", propose)
    monkeypatch.setattr(grammar.GPTGrammarJudge, "__call__", judge)
    return calls


def build_pool(path, *, count, rate=.30, offline=False):
    return grammar.build_grammar_bank(
        TEXT, bank_dir=path, seed=42, max_rate=rate,
        cache=grammar.GrammarJudgmentCache(path / "judgments.json", model="test", offline=offline),
        min_approved_candidates=count,
    )


def test_count_extends_beyond_coverage_and_reuses_prior_approvals(tmp_path, fake_models):
    original = build_pool(tmp_path, count=0)
    assert len(original["entries"]) < 10
    original_calls = copy.deepcopy(fake_models)
    expanded = build_pool(tmp_path, count=10)
    assert len(expanded["entries"]) == 10
    assert expanded["actual_affected_rate"] > .30
    assert expanded["entries"][:len(original["entries"])] == original["entries"]
    assert fake_models["judgment"][:len(original_calls["judgment"])] == original_calls["judgment"]
    for records in fake_models.values():
        assert len({json.dumps(record, sort_keys=True) for record in records}) == len(records)
    calls_after_extension = copy.deepcopy(fake_models)
    assert build_pool(tmp_path, count=10, offline=True) == expanded
    assert fake_models == calls_after_extension
    # A lower requested minimum must not truncate the existing approved bank.
    assert build_pool(tmp_path, count=5, offline=True) == expanded


def test_candidate_count_is_minimum_and_does_not_remove_coverage_requirement(tmp_path, fake_models):
    bank = build_pool(tmp_path, count=1)
    assert len(bank["entries"]) > 1
    assert bank["target_met"]


def test_count_extension_preserves_previous_higher_coverage(tmp_path, fake_models):
    larger = build_pool(tmp_path, count=0, rate=.50)
    extended = build_pool(tmp_path, count=15, rate=.30)
    assert extended["max_rate"] == .50
    assert extended["entries"][:len(larger["entries"])] == larger["entries"]


def test_raising_rate_within_existing_surplus_does_not_shrink_or_rebuild_pool(tmp_path, fake_models):
    original = build_pool(tmp_path, count=15, rate=.30)
    before = copy.deepcopy(fake_models)
    raised = build_pool(tmp_path, count=0, rate=.50, offline=True)
    assert raised["max_rate"] == .50
    assert raised["entries"] == original["entries"]
    assert fake_models == before


def test_impossible_count_fails_before_model_calls(tmp_path, fake_models):
    with pytest.raises(grammar.GrammarError, match="only 20 clauses"):
        build_pool(tmp_path, count=21)
    assert fake_models == {"generation": [], "judgment": []}


def test_acts19_existing_weights_support_five_levels_without_more_candidates():
    bank = weight_bank([20, 13, 7, 33, 14], 281)
    plan = candidates.plan_nested_selections(bank, RATES)
    assert plan[0] == []
    previous = set()
    for rate in RATES[1:]:
        selected = set(plan[rate])
        assert previous < selected
        actual = sum(bank["entries"][i]["content_chars"] for i in selected) / 281
        assert abs(actual - rate) <= .02
        previous = selected
    assert set(plan[.30]) == set(range(5))
    assert plan[.15] != plan[.20]
    assert candidates.plan_nested_selections(bank, list(reversed(RATES))) == plan


def test_acts20_requires_more_than_four_approved_clauses():
    with pytest.raises(grammar.GrammarError, match="Only 4 approved clauses"):
        candidates.plan_nested_selections(weight_bank([18, 7, 9, 17], 164), RATES)


def test_expanded_pool_uses_subset_at_30_and_nests_all_lower_levels():
    bank = weight_bank([18, 7, 9, 17, 8, 9], 164)
    plan = candidates.plan_nested_selections(bank, RATES)
    assert set(plan[.30]) < set(range(6))
    assert 0 not in plan[.30]  # The original large edit is replaced by smaller ones.
    for low, high in zip(RATES, RATES[1:]):
        assert set(plan[low]) < set(plan[high])
    for rate, indices in plan.items():
        assert abs(sum(bank["entries"][i]["content_chars"] for i in indices) / 164 - rate) <= .02


def test_planner_matches_exhaustive_feasibility_and_lower_dose_priority():
    weights = [4, 6, 7, 9, 11, 13]
    rates = [.05, .10, .20, .30]
    bank = weight_bank(weights, 100)
    feasible = []
    for starts in product(range(len(rates) + 1), repeat=len(weights)):
        totals = [sum(w for w, start in zip(weights, starts) if start <= level) for level in range(len(rates))]
        if all(b > a for a, b in zip([0] + totals, totals)) and all(abs(n - rate * 100) <= 2 for n, rate in zip(totals, rates)):
            feasible.append(tuple((abs(n - rate * 100), n) for n, rate in zip(totals, rates)))
    plan = candidates.plan_nested_selections(bank, rates)
    actual = tuple((abs(sum(weights[i] for i in plan[rate]) - rate * 100), sum(weights[i] for i in plan[rate])) for rate in rates)
    assert actual == min(feasible)


def test_no_feasible_tolerance_or_search_budget_fails_explicitly():
    bank = weight_bank([20, 20, 20, 20, 20], 164)
    with pytest.raises(grammar.GrammarError, match="No distinct nested selection"):
        candidates.plan_nested_selections(bank, RATES)
    with pytest.raises(grammar.GrammarError, match="work limit"):
        candidates.plan_nested_selections(weight_bank([7, 8, 9, 9, 17], 164), RATES, max_search_nodes=1)


def setup_source(root):
    source = root / "p" / "_base" / "llm_prompt_high"
    source.mkdir(parents=True, exist_ok=True)
    for name in ("passage_target.txt", "passage_target_decanonicalized.txt"):
        (source / name).write_text(TEXT, encoding="utf-8")
    (source / "qa_target.json").write_text('{"answer": "unchanged"}', encoding="utf-8")
    return source


def args(root, count=10):
    return ["--root", str(root), "--passage-dirs", "p", "--target-candidates", str(count),
            "--judge-model", "test", "--generator-model", "test"]


def test_cli_reuses_old_caches_exports_nested_outputs_and_reruns_offline(tmp_path, fake_models, fake_meaning_models):
    source = setup_source(tmp_path)
    previous = tmp_path / "p" / "previous"
    seed = 2026 + grammar.seed_offset("p")
    old_banks = grammar.prepare_grammar_banks(source, previous, seed=seed, bank_rate=.30, model="test", max_candidates=3, offline=False)
    cache_before = {p.name: p.read_bytes() for p in (previous / "_grammar_bank").iterdir()}
    command = args(tmp_path) + ["--reuse-cache-model-dir", "previous"]
    assert candidates.main(command) == 0
    output = tmp_path / "p" / "grammar_candidate_test"
    assert cache_before == {p.name: p.read_bytes() for p in (previous / "_grammar_bank").iterdir()}
    assert len(fake_models["judgment"]) == 10  # Raw/decanonicalized sources share approvals.
    assert len(fake_meaning_models["reading"]) == len(fake_meaning_models["comparison"]) == 10
    for filename in ("meaning_readings.json", "meaning_judgments.json"):
        assert (output / "_grammar_bank" / filename).is_file()
    report = json.loads((output / "dose_selection.json").read_text())
    assert report["target_candidates"] == 10
    assert report["files"]["passage_target.txt"]["approved_candidate_count"] == 10
    previous_units = set()
    outputs = set()
    for rate in RATES[1:]:
        variant = output / grammar.format_rate(rate)
        meta = json.loads((variant / "grammar_metadata.json").read_text())["files"]["passage_target"]
        current_units = {e["unit_index"] for e in meta["affected_units"]}
        assert previous_units < current_units
        assert abs(meta["actual_affected_rate"] - rate) <= .02
        assert meta["selection_method"] == "planned_nested_subsets_v1"
        text = (variant / "passage_target.txt").read_text()
        assert grammar.Counter(text) == grammar.Counter(TEXT)
        assert (variant / "qa_target.json").read_bytes() == (source / "qa_target.json").read_bytes()
        assert (variant / "passage_target_decanonicalized.txt").read_text() == text
        outputs.add(text)
        previous_units = current_units
    assert len(outputs) == 5
    calls = copy.deepcopy(fake_models)
    assert candidates.main(command + ["--offline"]) == 0
    assert fake_models == calls
    assert len(old_banks["passage_target.txt"]["entries"]) < 10


def test_candidate_shortfall_saves_bank_but_does_not_export(tmp_path, fake_models, monkeypatch, capsys):
    setup_source(tmp_path)
    original = grammar.GPTGrammarProposer.__call__

    def limited(self, request):
        response = original(self, request)
        for clause in response["clauses"]:
            if int(clause["original_clause"].split()[0]) > 7:
                clause["candidates"] = []
        return response

    monkeypatch.setattr(grammar.GPTGrammarProposer, "__call__", limited)
    assert candidates.main(args(tmp_path)) == 1
    assert "approved 7/10" in capsys.readouterr().err
    output = tmp_path / "p" / "grammar_candidate_test"
    assert list((output / "_grammar_bank").glob("bank_*.json"))
    assert not (output / "0%").exists()
    assert not (output / "30%").exists()
    calls = copy.deepcopy(fake_models)
    assert candidates.main(args(tmp_path) + ["--offline"]) == 1
    assert fake_models == calls


def test_cache_merge_does_not_overwrite_conflicting_evidence(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    for root, value in ((source, "one"), (target, "two")):
        (root / "proposals.json").write_text(json.dumps({"schema_version": 1, "proposals": {"same-key": value}}))
    before = (target / "proposals.json").read_bytes()
    with pytest.raises(grammar.GrammarError, match="Conflicting cached"):
        candidates.reuse_caches(source, target)
    assert (target / "proposals.json").read_bytes() == before


@pytest.mark.parametrize("extra", [
    ["--target-candidates", "4"], ["--target-candidates", "0"],
    ["--coverage-tolerance-pp", "nan"], ["--coverage-tolerance-pp", "-1"],
    ["--rates", "0%"], ["--max-candidates-per-clause", "0"],
])
def test_bad_cli_parameters_fail_without_model_calls(tmp_path, fake_models, extra):
    setup_source(tmp_path)
    assert candidates.main(args(tmp_path) + extra) == 1
    assert fake_models == {"generation": [], "judgment": []}
