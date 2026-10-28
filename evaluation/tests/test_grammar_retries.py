"""Retry feedback, historical bank continuity, and the standard nested CLI."""

import copy
import json
from collections import Counter

import pytest

from evaluation.scripts.variants.current import create_grammar_variants as g


TEXT = "\n".join(f"{i} 他带着五个人走进城里。" for i in range(1, 5))


def edit(original, variant="A"):
    return original.replace("带着五个人", "五个人带着") if variant == "A" else original.replace(
        "带着五个人走进城里", "带着走进城里五个人")


def proposal(original, variant="A"):
    return {"edited_clause": edit(original, variant), "error_type": "synthetic",
            "explanation": "Synthetic test rearrangement, not a linguistic approval."}


def verdict(candidate, **kwargs):
    return {**{field: "yes" for field in g.JUDGMENT_FIELDS}, "error_span": candidate,
            "explanation": "Test grammar decision.", **kwargs}


@pytest.fixture
def models(monkeypatch, fake_meaning_models):
    monkeypatch.setattr(g, "EXTRA_PROTECTED", None)
    calls = {"generation": [], "grammar": []}

    def generate(self, request):
        calls["generation"].append(copy.deepcopy(request))
        clauses = []
        for clause in request["clauses"]:
            original = clause["original_clause"]
            number = int(original.split()[0])
            if request.get("retry_round", 0):
                candidates = [proposal(original, "B")]
            else:
                candidates = [] if number == 2 else [proposal(original)]
            clauses.append({"unit_index": clause["unit_index"], "original_clause": original,
                            "candidates": candidates})
        return {"clauses": clauses}

    def judge(self, request):
        calls["grammar"].append(copy.deepcopy(request))
        rejected = request["original_clause"].startswith("3 ") and "五个人带着" in request["edited_clause"]
        return verdict(request["edited_clause"], structural_error="no" if rejected else "yes")

    original_reader = g.GPTMeaningReader.__call__

    def read(self, request):
        reading = original_reader(self, request)
        if request["focus_clause"].startswith("4 ") and "五个人带着" in request["focus_clause"]:
            reading["interpretation_status"] = "unrecoverable"
        return reading

    monkeypatch.setattr(g.GPTGrammarProposer, "__call__", generate)
    monkeypatch.setattr(g.GPTGrammarJudge, "__call__", judge)
    monkeypatch.setattr(g.GPTMeaningReader, "__call__", read)
    return calls


def build(path, *, rounds=2, rate=1, offline=False, batch_size=8):
    return g.build_grammar_bank(TEXT, bank_dir=path, seed=42, max_rate=rate,
        cache=g.GrammarJudgmentCache(path / "judgments.json", model="test", offline=offline),
        retry_rounds=rounds, proposal_batch_size=batch_size)


def test_retry_only_unapproved_clauses_and_supplies_each_failure_reason(tmp_path, models):
    first = build(tmp_path, rounds=0)
    assert len(first["entries"]) == 1
    initial_calls = copy.deepcopy(models)
    expanded = build(tmp_path, rounds=2)
    assert expanded["target_met"]
    assert expanded["entries"][:1] == first["entries"]
    assert expanded["bank_id"] == first["bank_id"]
    assert len(models["generation"]) == 2
    retry = models["generation"][-1]
    assert retry["retry_round"] == 1
    assert {c["original_clause"].split()[0] for c in retry["clauses"]} == {"2", "3", "4"}
    feedback = {item["unit_index"]: item["attempts"] for item in retry["previous_attempts"]}
    assert {a["outcome"] for attempts in feedback.values() for a in attempts} == {
        "no_candidate", "grammar_rejected", "meaning_rejected"}
    semantic = next(a for attempts in feedback.values() for a in attempts if a["outcome"] == "meaning_rejected")
    assert semantic["feedback"]["candidate_reading"]["interpretation_status"] == "unrecoverable"
    assert models["grammar"][:len(initial_calls["grammar"])] == initial_calls["grammar"]
    assert len({json.dumps(req, sort_keys=True) for req in models["grammar"]}) == len(models["grammar"])
    before = copy.deepcopy(models)
    assert build(tmp_path, offline=True) == expanded
    assert models == before


def test_old_script_hash_does_not_discard_approved_bank(tmp_path, models):
    first = build(tmp_path, rounds=0)
    original_path = tmp_path / f"bank_{first['bank_id']}.json"
    first["spec"]["generator_sha256"] = "historical-script-hash"
    first["bank_id"] = g.json_digest(first["spec"])
    first.pop("retry_rounds_attempted")  # Exactly the historical bank shape.
    legacy_path = tmp_path / f"bank_{first['bank_id']}.json"
    legacy_path.write_text(json.dumps(first))
    original_path.unlink()
    expanded = build(tmp_path)
    assert expanded["bank_id"] == first["bank_id"]
    assert expanded["entries"][:1] == first["entries"]
    assert len(list(tmp_path.glob("bank_*.json"))) == 1
    assert len(models["generation"]) == 2  # No regenerated first pass.


def test_interrupted_retry_resumes_saved_requests_and_reviews(tmp_path, models, monkeypatch, fake_meaning_models):
    first = build(tmp_path, rounds=0, batch_size=2)
    original = g.GPTMeaningJudge.__call__
    attempts = []

    def interrupt(self, request):
        attempts.append(request["edited_clause"])
        if len(attempts) == 2:
            raise g.GrammarError("simulated retry interruption")
        return original(self, request)

    monkeypatch.setattr(g.GPTMeaningJudge, "__call__", interrupt)
    with pytest.raises(g.GrammarError, match="retry interruption"):
        build(tmp_path, batch_size=2)
    assert json.loads((tmp_path / f"bank_{first['bank_id']}.json").read_text()) == first
    grammar_before = copy.deepcopy(models["grammar"])
    readings_before = copy.deepcopy(fake_meaning_models["reading"])
    monkeypatch.setattr(g.GPTMeaningJudge, "__call__", original)
    resumed = build(tmp_path, batch_size=2)
    assert resumed["target_met"]
    assert resumed["entries"][:1] == first["entries"]
    # Completed grammar checks and source-blind readings are not repeated.
    assert all(models["grammar"].count(req) == 1 for req in grammar_before)
    assert all(fake_meaning_models["reading"].count(req) == 1 for req in readings_before)
    for record in json.loads((tmp_path / "proposals.json").read_text())["proposals"].values():
        key = g.json_digest({"generator": record["generator"], "request": record["request"]})
        assert key in json.loads((tmp_path / "proposals.json").read_text())["proposals"]


def test_retry_round_budget_is_bounded_and_can_be_extended(tmp_path, models, monkeypatch):
    original = g.GPTGrammarProposer.__call__

    def empty_until_second_round(self, request):
        response = original(self, request)
        if request.get("retry_round") == 1:
            for clause in response["clauses"]:
                clause["candidates"] = []
        return response

    monkeypatch.setattr(g.GPTGrammarProposer, "__call__", empty_until_second_round)
    short = build(tmp_path, rounds=1)
    assert not short["target_met"]
    assert short["retry_rounds_attempted"] == 1
    before = copy.deepcopy(models)
    assert build(tmp_path, rounds=1, offline=True) == short
    assert models == before
    complete = build(tmp_path, rounds=2)
    assert complete["target_met"]
    assert complete["entries"][:len(short["entries"])] == short["entries"]
    assert len(models["generation"]) == len(before["generation"]) + 1
    assert build(tmp_path, rounds=0, offline=True) == complete


def test_retry_does_not_rejudge_repeated_candidates_or_bypass_meaning_gate(tmp_path, models, monkeypatch):
    original = g.GPTGrammarProposer.__call__

    def repeat(self, request):
        response = original(self, request)
        for clause in response["clauses"]:
            clause["candidates"] = [proposal(clause["original_clause"])]
        return response

    monkeypatch.setattr(g.GPTGrammarProposer, "__call__", repeat)
    result = build(tmp_path)
    assert not result["target_met"]
    assert {e["original_text"].split()[0] for e in result["entries"]} == {"1", "2"}
    assert len(models["grammar"]) == 4
    assert result["meaning_rejected_candidate_count"] == 1
    assert result["duplicate_or_noop_candidate_count"] == 4


def test_lost_retry_bank_rebuilds_from_exact_caches_without_calls(tmp_path, models):
    result = build(tmp_path)
    (tmp_path / f"bank_{result['bank_id']}.json").unlink()
    before = copy.deepcopy(models)
    assert build(tmp_path, offline=True) == result
    assert models == before


def test_lower_coverage_then_extension_preserves_retry_prefix(tmp_path, models):
    # Initial pass only approves 25%; reaching 50% requires a retry. Later
    # extension must reuse the partially consumed retry batch and its approvals.
    lower = build(tmp_path, rate=.5)
    before = copy.deepcopy(models)
    higher = build(tmp_path, rate=1)
    assert higher["entries"][:len(lower["entries"])] == lower["entries"]
    assert models["generation"] == before["generation"]


def test_same_weight_entries_respect_exact_saved_anchors():
    bank = {"entries": [{"content_chars": w} for w in [10, 10, 10, 10, 10, 10]],
            "total_content_chars": 100, "max_rate": .6}
    plan = g.plan_nested_selections(bank, [.1, .2, .3, .4, .5, .6],
                                   fixed_selections={.3: [1, 3, 5]})
    assert plan[.3] == [1, 3, 5]
    for low, high in zip([.1, .2, .3, .4, .5], [.2, .3, .4, .5, .6]):
        assert set(plan[low]) < set(plan[high])


def test_actual_passage_weights_improve_twenty_percent_and_keep_thirty():
    bank = {"entries": [{"content_chars": w} for w in [13, 16, 12, 17, 24, 12, 9, 8, 11, 12, 9]],
            "total_content_chars": 302, "max_rate": .6}
    plan = g.plan_nested_selections(bank, [0, .1, .2, .3, .4], fixed_selections={.3: list(range(6))})
    actual = sum(bank["entries"][i]["content_chars"] for i in plan[.2]) / 302
    assert actual == 58 / 302  # 19.2%, replacing the old 82 / 302 = 27.2%.
    assert plan[.3] == list(range(6))
    assert len(bank["entries"]) == 11


@pytest.mark.parametrize("anchors", [{.2: [0, 1, 2]}, {.1: [0], .2: [1, 2]}])
def test_saved_out_of_tolerance_or_nonnested_outputs_fail_explicitly(anchors):
    bank = {"entries": [{"content_chars": 10} for _ in range(6)],
            "total_content_chars": 100, "max_rate": .6}
    with pytest.raises(g.GrammarError, match="outside tolerance|not distinct and nested"):
        g.plan_nested_selections(bank, [.1, .2, .3], fixed_selections=anchors)


def test_standard_cli_replans_lower_rates_preserves_export_and_reruns_offline(tmp_path, models, monkeypatch):
    text = "\n".join(f"{i} 他带着五个人走进城里。" for i in range(1, 21))
    source = tmp_path / "p/_base/llm_prompt_high"
    source.mkdir(parents=True)
    for filename in ["passage_target.txt", "passage_target_decanonicalized.txt"]:
        (source / filename).write_text(text)
    (source / "qa_target.json").write_text('{"answer": "preserved"}')
    output = tmp_path / "p/grammar"
    seed = 2026 + g.seed_offset("p")
    old = g.prepare_grammar_banks(source, output, seed=seed, bank_rate=.3, model="test",
                                  max_candidates=3, offline=False)
    g.create_variant(source_method_dir=source, output_dir=output, rate=.3, seed=seed,
                     force=False, banks=old)
    original_thirty = (output / "30%/passage_target.txt").read_bytes()
    command = ["grammar", "--root", str(tmp_path), "--passage-dirs", "p",
               "--source-model-dir", "_base", "--judge-model", "test", "--bank-rate", "60%",
               "--rates", "0%", "10%", "20%", "30%", "40%", "50%", "60%"]
    monkeypatch.setattr("sys.argv", command)
    assert g.main() == 0
    assert (output / "30%/passage_target.txt").read_bytes() == original_thirty
    previous = set()
    for name in ["10%", "20%", "30%", "40%", "50%", "60%"]:
        variant = output / name
        meta = json.loads((variant / "grammar_metadata.json").read_text())["files"]["passage_target"]
        selected = {e["unit_index"] for e in meta["affected_units"]}
        assert previous < selected
        assert abs(meta["actual_affected_rate"] - float(name[:-1]) / 100) <= .02
        assert Counter((variant / "passage_target.txt").read_text()) == Counter(text)
        assert (variant / "qa_target.json").read_bytes() == (source / "qa_target.json").read_bytes()
        previous = selected
    report = json.loads((output / "dose_selection.json").read_text())
    assert report["files"]["passage_target.txt"]["doses"][3]["preserved_existing_selection"]
    before = copy.deepcopy(models)
    monkeypatch.setattr("sys.argv", command + ["--offline"])
    assert g.main() == 0
    assert models == before


@pytest.mark.parametrize("extra", [["--retry-rounds", "-1"], ["--coverage-tolerance-pp", "nan"]])
def test_invalid_retry_or_tolerance_fails_before_model_calls(tmp_path, models, monkeypatch, extra):
    monkeypatch.setattr("sys.argv", ["grammar", "--root", str(tmp_path), *extra])
    assert g.main() == 1
    assert models == {"generation": [], "grammar": []}


@pytest.mark.parametrize('tolerance,expected_exit', [(2, 0), (1, 1), (0, 1)])
def test_highest_rate_undershoot_uses_same_tolerance_as_selection(tmp_path, models, monkeypatch, tolerance, expected_exit):
    # Fourteen source clauses total 302 characters. The generator can approve
    # 178 characters (58.94%), enough for 60% +/-2 but not +/-1 or exact 60%.
    weights = [13, 16, 12, 17, 24, 12, 9, 8, 11, 12, 9, 24, 11, 124]
    text = '1 ' + ''.join('甲' * (weight - 1) + '乙。' for weight in weights)
    source = tmp_path / 'p/_base/llm_prompt_high'
    source.mkdir(parents=True)
    (source / 'passage_target.txt').write_text(text)
    (source / 'qa_target.json').write_text('{"answer": "unchanged"}')

    def generate(self, request):
        groups = []
        for clause in request['clauses']:
            original = clause['original_clause']
            body = original.removeprefix('1 ')
            candidates = []
            if len(body) - 1 < 100:
                changed = ('1 ' if original.startswith('1 ') else '') + '乙' + body[:-2] + '。'
                candidates = [{'edited_clause': changed, 'error_type': 'synthetic',
                               'explanation': 'Test candidate, not a linguistic judgment.'}]
            groups.append({**{k: clause[k] for k in ['unit_index', 'original_clause']},
                           'candidates': candidates})
        return {'clauses': groups}

    monkeypatch.setattr(g.GPTGrammarProposer, '__call__', generate)
    monkeypatch.setattr(g.GPTGrammarJudge, '__call__', lambda self, request: verdict(request['edited_clause']))
    command = ['grammar', '--root', str(tmp_path), '--passage-dirs', 'p',
               '--source-model-dir', '_base', '--judge-model', 'test', '--bank-rate', '60%',
               '--rates', '0%', '10%', '20%', '30%', '40%', '50%', '60%',
               '--coverage-tolerance-pp', str(tolerance)]
    monkeypatch.setattr('sys.argv', command)
    assert g.main() == expected_exit
    output = tmp_path / 'p/grammar'
    bank = json.loads(next((output / '_grammar_bank').glob('bank_*.json')).read_text())
    assert bank['affected_content_chars'] == 178
    assert bank['total_content_chars'] == 302
    assert bank['target_met'] is False
    if expected_exit:
        assert not (output / '0%').exists()
        assert not (output / '60%').exists()
    else:
        report = json.loads((output / 'dose_selection.json').read_text())
        assert all(dose['within_tolerance'] for dose in report['files']['passage_target.txt']['doses'])
        meta = json.loads((output / '60%/grammar_metadata.json').read_text())['files']['passage_target']
        assert meta['actual_affected_rate'] == 178 / 302
        assert meta['target_met'] is False
        assert meta['shortfall_content_chars'] == 3
        monkeypatch.setattr('sys.argv', command + ['--offline'])
        assert g.main() == 0
