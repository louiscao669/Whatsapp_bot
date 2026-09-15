#!/usr/bin/env python3
"""Audit-gate wiring test for rewrite_distractors_gold72_en.py (relevance + falseness).

Real data, real loop, stubbed auditors and rewriter: no langchain, no ollama, no API key and
no spend. `--self-test` covers the decision rules; this covers the WIRING -- where each gate
runs, when it retries, that ONE regeneration sees BOTH objections, and that the letters in
the report index the shipped options rather than the auditor's pre-shuffle order.

Run via tests_falseness_gate.py.
"""
import importlib, json, os, sys, tempfile, types
from pathlib import Path

PREP = Path(__file__).resolve().parent
REPO = PREP.parents[3]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(PREP))

calls = {"rel": 0, "fal": 0, "rewrite": 0, "feedback": []}
MODE = {"all3": False}        # flip to make the relevance stub reject ALL THREE
DONE = "REGENERATED"          # marker the stub rewriter stamps on its output


class FV:
    def __init__(self, st, why="stub", q=None, fix=None):
        self.answer_status, self.reason, self.quote, self.suggested_fix = st, why, q, fix


class RV:
    def __init__(self, ok, why="stub", fix=None):
        self.is_possible_answer, self.reason, self.suggested_fix = ok, why, fix


def _others(options, correct):
    return [L for L in "ABCD" if L != correct and options.get(L)]


def fake_falseness(chain, question, options, correct, window):
    """Flags the FIRST distractor as supported until the rewriter has regenerated."""
    calls["fal"] += 1
    ls = _others(options, correct)
    if DONE in options[ls[0]]:
        return {L: FV("unsupported") for L in ls}
    return {ls[0]: FV("supported", "window says exactly this", "13 stub verse"),
            ls[1]: FV("unsupported"), ls[2]: FV("contradicted")}


def fake_relevance(chain, question, options, correct, window):
    """Flags the SECOND distractor as not-an-answer until the rewriter has regenerated.

    Deliberately a DIFFERENT letter from the falseness stub: that is what proves one
    regeneration round carries both objections rather than one clobbering the other.
    """
    calls["rel"] += 1
    ls = _others(options, correct)
    if MODE["all3"]:
        return {L: RV(False, "judge thinks the stem asks something else") for L in ls}
    if DONE in options[ls[1]]:
        return {L: RV(True) for L in ls}
    return {ls[0]: RV(True), ls[1]: RV(False, "biographical fact, not a reason"),
            ls[2]: RV(True)}


rc = types.ModuleType("relevance_chain")
rc.build_falseness_chain = lambda *a, **k: "FAL"
rc.build_relevance_chain = lambda *a, **k: "REL"
rc.audit_falseness = fake_falseness
rc.audit_distractors = fake_relevance
rc.failing_letters = lambda a: sorted(L for L, v in a.items() if not v.is_possible_answer)
rc.audit_feedback = lambda a: "\n".join(
    f"- {L} is not a possible answer to the question: {v.reason}"
    for L, v in sorted(a.items()) if not v.is_possible_answer)
sys.modules["relevance_chain"] = rc

import evaluation.scripts.mcq.preparation.rewrite_distractors as rd
rd.build_client = lambda p: "CLIENT"


def fake_rewrite(client, model, item, question, window, ents=None, temperature=0.4,
                 feedback=None, effort=None):
    calls["rewrite"] += 1
    if feedback:
        calls["feedback"].append(feedback)
    c = item["correct"]
    out = {L: (f"{DONE} {L}" if feedback else f"fresh {L}") for L in "ABCD"}
    out[c] = item[c]
    out["correct"] = c
    return out


rd.rewrite_distractors = fake_rewrite
en = importlib.import_module("evaluation.scripts.mcq.preparation.rewrite_distractors_gold72_en")


def run(argv, label):
    calls.update(rel=0, fal=0, rewrite=0, feedback=[])
    tmp = tempfile.mkdtemp()
    rep = os.path.join(tmp, "r.json")
    sys.argv = ["x",
                "--qa-dir", str(REPO / "evaluation/datasets/qa/tier1_gold72_canonical_5opt"),
                "--passage-dir", str(REPO / "evaluation/datasets/passages/tier1_bsb"),
                "--windows", str(REPO / "QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json"),
                "--out-dir", os.path.join(tmp, "out"), "--report", rep,
                "--no-verify", "--limit", "3"] + argv
    print(f"\n===== {label} =====")
    assert en.main() == 0
    return json.load(open(rep)), dict(calls)


def check_letters(rows, block, key):
    """The reported letters must index row['after'], not the auditor's pre-shuffle order."""
    for r in rows:
        b = r[block]
        assert len(b["failed"]) == len(b["failed_text"]) == 1, b
        L = b["failed"][0]
        assert L in "ABCD", f"{block}: letter not remapped: {L!r}"
        assert r["after"]["ABCD".index(L)] == b["failed_text"][0], (
            f"{block}: reported {L} -> {r['after']['ABCD'.index(L)]!r} but flagged "
            f"{b['failed_text'][0]!r}")
        assert L != r["key"], f"{block}: the key must never be audited"
        assert b["verdicts"][L][key] in (False, "supported"), b["verdicts"][L]


# --- A. verify-only, both gates forced on: audit and report, never regenerate ---------
rows, c = run(["--verify-only", "--falseness-check", "--relevance-check"],
              "verify-only + both gates forced")
assert c["rewrite"] == 0, f"verify-only must not call the rewriter (got {c['rewrite']})"
assert c["rel"] == 3 and c["fal"] == 3, c
assert all(r["source"] == "passthrough" for r in rows)
assert all(r["falseness"]["rounds"] == 1 and r["relevance"]["rounds"] == 1 for r in rows)
check_letters(rows, "falseness", "answer_status")
check_letters(rows, "relevance", "is_possible_answer")
assert all(r["relevance"]["n_effective_distractors"] == 2 for r in rows)
assert all(r["falseness"]["failed"] != r["relevance"]["failed"] for r in rows), \
    "the two gates flag different options; the report must keep them apart"
print("  [PASS] both gates audit and report without regenerating")
print("  [PASS] each gate's letters are remapped to the shipped order independently")

# --- B. verify-only at the auto default: both off, no spend ----------------------------
rows, c = run(["--verify-only"], "verify-only, auto default")
assert c["rel"] == 0 and c["fal"] == 0, c
assert all("falseness" not in r and "relevance" not in r for r in rows)
print("  [PASS] auto default keeps verify-only free of API calls")

# --- C. full rewrite: both auto-on, ONE regeneration carries BOTH objections -----------
rows, c = run([], "rewrite, both gates + shared retry")
assert all(r["source"] == "llm" for r in rows)
assert c["rewrite"] == 6, f"3 x (1 rewrite + 1 shared regeneration), got {c['rewrite']}"
assert c["rel"] == 6 and c["fal"] == 6, f"3 items x 2 rounds per gate, got {c}"
assert len(c["feedback"]) == 3, "exactly one regeneration per item"
for fb in c["feedback"]:
    assert "is TRUE for this passage" in fb, "falseness objection missing from feedback"
    assert "is not a possible answer" in fb, "relevance objection missing from feedback"
assert all(r["falseness"]["failed"] == [] and r["relevance"]["failed"] == [] for r in rows)
assert all(r["falseness"]["rounds"] == 2 and r["relevance"]["rounds"] == 2 for r in rows)
print("  [PASS] one regeneration round receives both gates' objections")
print("  [PASS] both flags clear after the shared retry")

# --- D. gates independently disablable -------------------------------------------------
rows, c = run(["--no-relevance-check"], "falseness only")
assert c["rel"] == 0 and c["fal"] == 6 and c["rewrite"] == 6, c
assert all("relevance" not in r and "falseness" in r for r in rows)
rows, c = run(["--no-falseness-check", "--no-relevance-check"], "both disabled")
assert c["rel"] == 0 and c["fal"] == 0 and c["rewrite"] == 3, c
assert all("relevance" not in r and "falseness" not in r for r in rows)
print("  [PASS] each gate disables independently; with both off the old path is restored")

# --- E. all three rejected: item left untouched, flagged for a human ------------------
# The kjsg regression. Three simultaneously-irrelevant distractors means the judge and the
# item disagree about what the question asks; rewriting then strands the key as the only
# option of its type. The driver must stop rather than "fix" it.
MODE["all3"] = True
rows, c = run([], "relevance rejects all three")
MODE["all3"] = False
assert c["rewrite"] == 3, f"one initial rewrite per item, then STOP, got {c['rewrite']}"
assert c["fal"] == 0, "bail out before spending a falseness call too"
assert len(rows) == 3 and all(r["action"] == "skipped-for-review" for r in rows), rows
assert all("relevance_reasons" in r and len(r["relevance_reasons"]) == 3 for r in rows)
assert all("after" not in r and "key_separable_by_length" not in r for r in rows), \
    "a reviewed item is never shuffled or rewritten"
print("  [PASS] all-three rejection stops the rewrite and flags the item for review")

# --- F. the key must not become pickable by length alone -----------------------------
_ksl = en.key_separable_by_length
rd.cjk_len = lambda x: len(str(x or "").split())
assert _ksl({"A": "By driving Ishbi Benob away without killing him.",
             "B": "By taking David away before the attack happened at all.",
             "C": "Ishbi Benob",
             "D": "By confronting the Philistine but sparing his life."}, "C", 3)
assert not _ksl({"A": "As one undivided force.", "B": "By assigned divisions.",
                 "C": "Without organized divisions.", "D": "As an untrained militia."},
                "B", 3)
print("  [PASS] key-separable-by-length guard catches the kjsg shape")

print("\n9/9 integration checks passed (no API calls made)")
