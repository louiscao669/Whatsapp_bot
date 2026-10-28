"""Prevent incomplete or stale inputs from entering the full rerun."""

import json
import hashlib
import os
from pathlib import Path
import subprocess

import pytest

from evaluation.scripts.analysis.current.check_full_conditions_5opt import (
    FAMILIES, RATES, check_inputs,
)

PID = "t1_acts20"


@pytest.fixture
def corpus(tmp_path):
    base = tmp_path / PID
    shared = base / "_base" / "_shared"
    shared.mkdir(parents=True)
    for suffix in ("qa_zh.json", "qa_zh_decanonicalized.json"):
        (shared / f"{PID}_base_{suffix}").write_text("[]")
    conditions = ["_base/llm_prompt_high", "omission/0%", "google_word_by_word"] + [
        f"{family}/{rate}%" for family in FAMILIES for rate in RATES
    ]
    for condition in conditions:
        path = base / condition
        path.mkdir(parents=True)
        text = "clean" if condition in ("_base/llm_prompt_high", "omission/0%") else condition
        for filename in ("passage_target.txt", "passage_target_decanonicalized.txt"):
            (path / filename).write_text(text)
        for filename in ("passage_translation.json", "qa_target_decanonicalized.json"):
            (path / filename).write_text("{}")
        family, _, label = condition.partition("/")
        if family not in FAMILIES or label == "0%":
            continue
        rate = int(label[:-1]) / 100
        file_meta = {"requested_rate": rate, "actual_rate": rate, "actual_affected_rate": rate}
        meta = {
            "generation_mode": "validated_bank", "edit_style": "llm_structural_v1",
            "bank_validation": {"status": "complete"},
            "files": {"passage_target": file_meta, "passage_target_decanonicalized": file_meta},
        }
        if family == "grammar":
            file_meta["output_sha256"] = hashlib.sha256(json.dumps(text, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        (path / f"{family}_metadata.json").write_text(json.dumps(meta))
    return tmp_path


def test_complete_grid_has_clean_once_and_twenty_conditions(corpus):
    result = check_inputs(corpus, [PID])
    assert result["ready"], result["errors"]
    assert len(result["cells"]) == 20


def test_missing_25_and_duplicate_doses_block_run(corpus):
    base = corpus / PID
    (base / "grammar/25%/passage_target.txt").unlink()
    (base / "omission/10%/passage_target_decanonicalized.txt").write_text("omission/5%")
    result = check_inputs(corpus, [PID])
    assert not result["ready"]
    assert any("grammar/25%: missing" in error for error in result["errors"])
    assert any("omission/10%: identical to 5%" in error for error in result["errors"])


def test_off_target_and_old_grammar_block_run(corpus):
    path = corpus / PID / "grammar/30%/grammar_metadata.json"
    meta = json.loads(path.read_text())
    meta["edit_style"] = "mechanical"
    meta["files"]["passage_target"]["actual_affected_rate"] = .18
    path.write_text(json.dumps(meta))
    result = check_inputs(corpus, [PID])
    assert not result["ready"]
    assert any("not an approved structural" in error for error in result["errors"])
    assert any("covers 18.00%" in error for error in result["errors"])


def test_grammar_provenance_detects_changed_text(corpus):
    (corpus / PID / "grammar/15%/passage_target.txt").write_text("unexpected edit")
    result = check_inputs(corpus, [PID])
    assert not result["ready"]
    assert any("output hash differs" in error for error in result["errors"])


def test_wbw_refreshes_existing_model_input_without_live_calls(corpus, tmp_path):
    repo = Path(__file__).resolve().parents[2]
    destination = corpus / PID / "llama321b_think" / "google_word_by_word"
    destination.mkdir(parents=True)
    (destination / "passage_target_decanonicalized.txt").write_text("stale")
    stub = tmp_path / "stub-python"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    env = {**os.environ, "OUT_ROOT": str(corpus), "PASSAGES": PID,
           "MODELS": "llama3.2:1b", "NO_THINK": "0", "SOURCE_CELL": ".",
           "REPLACE_INPUTS": "1", "DRY_RUN": "0", "SKIP_PREFLIGHT": "1",
           "OPENAI_API_KEY": "test-placeholder", "PYTHON_BIN": str(stub), "SLUG_SUFFIX": "_think"}
    subprocess.run(["bash", "evaluation/scripts/campaigns/current/run_tier1_wbw_models.sh"],
                   cwd=repo, env=env, check=True, capture_output=True, text=True)
    assert (destination / "passage_target_decanonicalized.txt").read_text() == "google_word_by_word"
