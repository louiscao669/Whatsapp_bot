#!/usr/bin/env python3
"""Falseness-gate wiring test for rewrite_distractors.run() (the Luke driver).

Builds a synthetic outputs tree so the real loop runs offline. Asserts the gate is
wired, retries once, clears the flag when the regeneration works, and SURFACES an item
it cannot fix instead of shipping it. Run via tests_falseness_gate.py.
"""
import importlib, json, os, subprocess, sys, tempfile, types
from pathlib import Path
PREP = Path(__file__).resolve().parent
REPO = PREP.parents[3]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(PREP))

calls = {"rel": 0, "fal": 0, "rewrite": 0}

class FV:
    def __init__(self, st, why="stub", q=None, fix=None):
        self.answer_status, self.reason, self.quote, self.suggested_fix = st, why, q, fix
class RV:
    def __init__(self, ok=True):
        self.is_possible_answer, self.reason, self.suggested_fix = ok, "stub", None

rc = types.ModuleType("relevance_chain")
rc.build_relevance_chain = lambda *a, **k: "REL"
rc.build_falseness_chain = lambda *a, **k: "FAL"
rc.build_equivalence_chain = lambda *a, **k: "EQ"
rc.check_equivalent = lambda *a, **k: False
def audit_distractors(chain, q, opts, correct, window):
    calls["rel"] += 1
    return {L: RV(True) for L in "ABCD" if L != correct}
def audit_falseness(chain, q, opts, correct, window):
    calls["fal"] += 1
    letters = [L for L in "ABCD" if L != correct]
    if "REGEN" in opts[letters[0]]:
        return {L: FV("unsupported") for L in letters}
    return {letters[0]: FV("supported", "the window states this", "13 stub"),
            letters[1]: FV("contradicted"), letters[2]: FV("unsupported")}
rc.audit_distractors = audit_distractors
rc.audit_falseness = audit_falseness
from audit_verdicts import (falseness_failing_letters, falseness_feedback,
                            falseness_status_counts)
rc.failing_letters = lambda a: sorted(L for L, v in a.items() if not v.is_possible_answer)
rc.audit_feedback = lambda a: ""
sys.modules["relevance_chain"] = rc

import evaluation.scripts.mcq.preparation.rewrite_distractors as rd
rd.build_client = lambda p: "C"
def fake_rewrite(client, model, item, question, window, ents=None, temperature=0.4,
                 feedback=None, effort=None):
    calls["rewrite"] += 1
    if feedback:
        assert "is TRUE for this passage" in feedback, f"bad feedback: {feedback!r}"
    c = item["correct"]
    out = {L: (f"REGEN {L}" if feedback else f"d{L}") for L in "ABCD"}
    out[c] = item[c]; out["correct"] = c
    return out
rd.rewrite_distractors = fake_rewrite
rd.ask_letter = lambda *a, **k: "A"

tmp = Path(tempfile.mkdtemp())
d = tmp / "luke1" / "1.7b" / "omission" / "0%"
d.mkdir(parents=True)
(d / "passage_target_pseudonymized.txt").write_text(
    "\n".join(f"{i} 第{i}节的经文内容。" for i in range(1, 21)), encoding="utf-8")
items = [{"passage_id": f"it{i}", "q_type": "mcq", "Q": f"问题{i}？",
          "passage_reference": "1:5-7",
          "A": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}, "correct": "B"}
         for i in range(3)]
(d / "qa_target_pseudonymized.json").write_text(json.dumps(items, ensure_ascii=False),
                                                encoding="utf-8")

class A: pass
a = A()
for k, v in dict(root=str(tmp), chapters=[1], model_dir="1.7b", remap_dir=str(tmp/"nope"),
                 provider="openai", model="gpt-5.6-terra", rewrite_temperature=0.4,
                 rewrite_effort="medium", answer_provider="ollama",
                 answer_model="qwen2.5:1.5b", answer_temperature=0.0, k=1,
                 domain_hint="h", no_domain_hint=True, relevance_check=True,
                 relevance_provider="openai", relevance_model="gpt-5.6-sol",
                 relevance_effort="medium", relevance_retries=1,
                 falseness_check=True, falseness_provider=None, falseness_model=None,
                 falseness_effort="medium", rewrite_correct=False, length_tolerance=3,
                 shuffle_seed="s", in_place=False, out_dir=str(tmp/"rep"),
                 save_mcq="", overwrite_mcq=False, de_novo=False).items():
    setattr(a, k, v)

rd.run(a)
summary = json.load(open(tmp / "rep" / "rewrite_summary.json"))
report = json.load(open(tmp / "rep" / "rewrite_report.json"))

assert a.falseness_model == "gpt-5.6-sol", "falseness model should default to the relevance one"
assert a.falseness_provider == "openai"
assert calls["fal"] == 6, f"3 items x 2 audit rounds, got {calls['fal']}"
assert calls["rewrite"] == 6, f"3 items x (rewrite + regen), got {calls['rewrite']}"
assert all(r["falseness_failed_after_retries"] == [] for r in report), "retry must clear it"
assert all(r["falseness_audited"] for r in report)
assert all(r["relevance_rounds"] == 2 for r in report)
assert summary["n_items_with_supported_distractor"] == 0
assert summary["n_supported_distractors"] == 0
assert summary["n_items_unaudited_for_falseness"] == 0
assert summary["distractor_status_counts"] == {"supported": 0, "contradicted": 0,
                                               "unsupported": 9}, summary["distractor_status_counts"]
assert summary["falseness_model"] == "openai:gpt-5.6-sol"
assert "falseness_warning" not in summary
print("  [PASS] run() wires the gate, retries once, and clears the flag")

# --- gate off: no audits, no falseness keys in the summary ---
calls["fal"] = calls["rewrite"] = 0
a.falseness_check = False
a.falseness_provider = a.falseness_model = None
a.out_dir = str(tmp / "rep2")
rd.run(a)
s2 = json.load(open(tmp / "rep2" / "rewrite_summary.json"))
r2 = json.load(open(tmp / "rep2" / "rewrite_report.json"))
assert calls["fal"] == 0 and calls["rewrite"] == 3
assert s2["falseness_model"] is None and s2["n_items_unaudited_for_falseness"] is None
assert all(r["falseness_failed_after_retries"] == [] and not r["falseness_audited"]
           for r in r2)
print("  [PASS] --no-falseness-check leaves run() on the old path")

# --- retries exhausted: the item is reported, not silently shipped ---
rc.audit_falseness = lambda *a_, **k_: {"A": FV("supported", "always fails"),
                                        "C": FV("unsupported"), "D": FV("unsupported")}
calls["fal"] = 0
a.falseness_check = True
a.falseness_provider = a.falseness_model = None
a.out_dir = str(tmp / "rep3")
rd.run(a)
s3 = json.load(open(tmp / "rep3" / "rewrite_summary.json"))
assert s3["n_items_with_supported_distractor"] == 3, s3["n_items_with_supported_distractor"]
assert s3["n_supported_distractors"] == 3
assert "falseness_warning" in s3 and "two defensible answers" in s3["falseness_warning"]
print("  [PASS] an item the gate cannot fix is surfaced in the summary, not hidden")
print("\n3/3 run() integration checks passed (no API calls made)")
