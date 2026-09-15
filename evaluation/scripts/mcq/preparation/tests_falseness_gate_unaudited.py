#!/usr/bin/env python3
"""An auditor that always errors must report NOTHING MEASURED, never a clean bill of health.

Both gates fail OPEN on transport errors: an empty audit is "no opinion", so the item is kept
rather than lost to a flake. The danger is the SUMMARY -- counting unaudited items in the
denominator printed "0/1 items carry a distractor ... 0.0% dead" for an item no judge had
ever seen. Observed live on 2026-09-13 when the API was unreachable.
"""
import importlib, io, json, os, sys, tempfile, types, contextlib
from pathlib import Path

PREP = Path(__file__).resolve().parent
REPO = PREP.parents[3]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(PREP))

rc = types.ModuleType("relevance_chain")
rc.build_relevance_chain = rc.build_falseness_chain = lambda *a, **k: "CHAIN"
rc.audit_distractors = rc.audit_falseness = lambda *a, **k: {}      # every call "errors"
rc.failing_letters = lambda a: []
rc.audit_feedback = lambda a: ""
sys.modules["relevance_chain"] = rc

import evaluation.scripts.mcq.preparation.rewrite_distractors as rd
rd.build_client = lambda p: "CLIENT"
en = importlib.import_module("evaluation.scripts.mcq.preparation.rewrite_distractors_gold72_en")

tmp = tempfile.mkdtemp()
sys.argv = ["x",
            "--qa-dir", str(REPO / "evaluation/datasets/qa/tier1_gold72_canonical_5opt"),
            "--passage-dir", str(REPO / "evaluation/datasets/passages/tier1_bsb"),
            "--windows", str(REPO / "QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json"),
            "--report", os.path.join(tmp, "r.json"), "--limit", "3",
            "--verify-only", "--no-verify", "--relevance-check", "--falseness-check"]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc_ = en.main()
out = buf.getvalue()
assert rc_ == 0, "an unreachable auditor must not crash the run"
assert "NO VERDICTS" in out, out
assert out.count("NOT AUDITED") == 2, "both gates must declare themselves unmeasured"
assert "NOT a pass" in out
for bad in ("0/3 (0.0%)", "0/1 item(s) carry", "0/3 item(s) carry"):
    assert bad not in out, f"unaudited items must not be counted as clean: {bad!r}\n{out}"
rows = json.load(open(os.path.join(tmp, "r.json")))
assert all(not r["relevance"]["audited"] and not r["falseness"]["audited"] for r in rows)
print("  [PASS] an unreachable auditor reports NOTHING MEASURED, not 0 defects")
print("  [PASS] the run completes rather than crashing on the empty-audit path")
print("\n2/2 checks passed (no API calls made)")
