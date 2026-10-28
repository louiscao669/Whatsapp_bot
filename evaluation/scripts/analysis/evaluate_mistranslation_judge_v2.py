#!/usr/bin/env python3
"""Compare current, previous revised, and conservative judge contracts blindly."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import random
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.analysis.evaluate_mistranslation_judge import case_request, metrics
from evaluation.scripts.variants.banks import mistranslation_conservative_judge as strict
from evaluation.scripts.variants.banks import mistranslation_validation as legacy

FIXTURE = REPO_ROOT / "evaluation/configs/mistranslation_judge_holdout_v2"
ARMS = ("current", "previous", "conservative")


def load_fixture(directory):
    dataset = json.loads((directory / "cases.json").read_text())
    prompts = {arm: (directory / f"{arm}_prompt.txt").read_text() for arm in ARMS}
    schemas = {arm: json.loads((directory / ("conservative_schema.json" if arm == "conservative" else "legacy_schema.json")).read_text())
               for arm in ARMS}
    if schemas["current"] != legacy.JUDGE_SCHEMA or schemas["conservative"] != strict.CONSERVATIVE_SCHEMA:
        raise ValueError("Frozen schema and executable acceptance contract differ.")
    seen, requests = set(), set()
    for case in dataset["cases"]:
        if not case["id"].replace("_", "").isalnum() or case["id"] in seen:
            raise ValueError("Invalid or duplicate case id.")
        seen.add(case["id"])
        if case["expected"] not in {"accept", "reject"} or case["cohort"] not in {"fresh", "regression"}:
            raise ValueError("Invalid reference label or cohort.")
        request = case_request(case)
        key = legacy.digest(request)
        if key in requests:
            raise ValueError("Duplicate case request.")
        requests.add(key)
        if case["cohort"] == "fresh" and any(case["source"] in p and case["target"] in p for p in prompts.values()):
            raise ValueError(f'Fresh case appears in a prompt: {case["id"]}')
    return dataset, prompts, schemas


def evaluate_case(case, arm, trial, prompt, schema, output, model, offline=False, client=None):
    cache = legacy.StructuredResponseCache(
        output / "cache" / arm / f"trial_{trial}" / f'{case["id"]}.json',
        model=model, prompt=prompt, schema=schema, name="mistranslation_judgment",
        max_output_tokens=8192, offline=offline, client=client,
    )
    key, judgment = cache.get(case_request(case))
    record = cache.data["records"][key]
    base = strict.legacy_view(judgment) if arm == "conservative" else judgment
    criteria_accept = legacy.judgment_accepts(base)
    reasons = strict.conservative_rejection_reasons(judgment) if arm == "conservative" else (
        [] if criteria_accept else ["legacy_criteria_or_claims_failed"]
    )
    accepted = not reasons
    return {
        "id": case["id"], "arm": arm, "trial": trial,
        "decision": "accept" if accepted else "reject",
        "criteria_only_accept": criteria_accept,
        "extra_gate_changed_decision": criteria_accept and not accepted,
        "rejection_reasons": reasons, "judgment": judgment, "judgment_id": key,
        "response_id": record["response_id"], "response_model": record["response_model"],
        "usage": record["usage"], "cache_file": str(cache.path),
    }


def summarize(dataset, records, planned, repeats):
    summary = {}
    for cohort in ("fresh", "regression"):
        cases = [c for c in dataset["cases"] if c["cohort"] == cohort]
        ids = {c["id"] for c in cases}
        summary[cohort] = {arm: metrics(cases, [r for r in records if r["arm"] == arm and r["id"] in ids]) for arm in ARMS}
    usage = Counter()
    for record in records:
        u = record.get("usage") or {}
        for k in ("input_tokens", "output_tokens", "total_tokens"):
            usage[k] += u.get(k, 0)
        usage["reasoning_tokens"] += (u.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
        usage["cached_input_tokens"] += (u.get("input_tokens_details") or {}).get("cached_tokens", 0)
    complete = len(records) == planned and all("error" not in r for r in records)
    fresh = summary["fresh"]["conservative"]
    gate = dataset["promotion_gate"]
    summary.update(
        complete=complete, completed_responses=sum("error" not in r for r in records),
        planned_responses=planned, usage=dict(usage),
        extra_gate_changed_decisions=[{"id": r["id"], "trial": r["trial"], "reasons": r["rejection_reasons"]}
                                      for r in records if r.get("extra_gate_changed_decision")],
        screening_gate_passed=(
            fresh["false_accept"] <= gate["max_false_accepts"]
            and fresh["false_reject"] <= gate["max_false_rejects"]
            and len(fresh["repeat_flips"]) <= gate["max_repeat_flips"]
        ) if complete and repeats >= 3 else None,
    )
    return summary


def render_report(dataset, prompts, summary, records, manifest, output):
    e = lambda v: escape(str(v))
    lookup = {(r["id"], r["arm"]): r for r in records if r["trial"] == 1}
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conservative mistranslation judge test</title><style>
body{font:16px/1.6 system-ui,sans-serif;max-width:1500px;margin:40px auto;padding:0 24px;color:#243246;background:#f7f8fb}
h1{font-size:32px;line-height:1.2}h2{margin-top:34px}table{border-collapse:collapse;width:100%;background:white;margin:20px 0}th,td{padding:12px;border:1px solid #dce2eb;text-align:left;vertical-align:top}th{background:#eaf0f8}.note{background:#fff2cd;padding:18px;border-radius:10px}.ok{color:#087047}.bad{color:#b32d29}small{color:#54637a}details{margin-top:12px}summary{cursor:pointer}a{color:#1756a2}pre{white-space:pre-wrap;font-size:13px}p{margin:10px 0}</style>
<h1>Conservative mistranslation judge: fresh test and regression checks</h1>'''
    html += f'<p>All arms: <b>{e(manifest["configuration"]["model"])}</b> · {summary["completed_responses"]}/{summary["planned_responses"]} responses</p>'
    html += '<p class="note">Expected labels were authored by the assistant and frozen before calls, without independent human validation. Scores are agreement with this conservative policy, not proven production accuracy. Labels, reasons, case IDs and prior judgments were hidden from every model request. Production prompts and banks are unchanged.</p>'
    html += f'<p>{e(dataset["design"])}</p><p><b>Policy:</b> {e(dataset["strict_policy"])}</p>'
    html += '<p>Current = production prompt. Previous = first revised prompt tested earlier. Conservative = new strict scalar rule, extra structured evidence and code gates, plus literal-context fluency rule.</p>'
    for cohort in ("fresh", "regression"):
        cases = [c for c in dataset["cases"] if c["cohort"] == cohort]
        n_reject = sum(c["expected"] == "reject" for c in cases)
        n_accept = len(cases) - n_reject
        html += f'<h2>{e(cohort.title())} cases — {len(cases)}</h2><table><tr><th>Judge</th><th>Reference-label agreement</th><th>False approvals / {n_reject}</th><th>False rejections / {n_accept}</th><th>Repeat flips</th><th>API errors</th></tr>'
        for arm in ARMS:
            m = summary[cohort][arm]
            correct = m["true_accept"] + m["true_reject"]
            html += f'<tr><td>{arm}</td><td>{correct}/{m["scored_cases"]}</td><td>{m["false_accept"]}</td><td>{m["false_reject"]}</td><td>{e(m["repeat_flips"])}</td><td>{m["errors"]}</td></tr>'
        html += '</table><table><tr><th style="width:29%">Passage and substitution</th><th style="width:20%">Expected decision</th><th>Current</th><th>Previous</th><th>Conservative</th></tr>'
        for case in cases:
            html += f'<tr><td><b>{e(case["id"])}</b><br><small>{e(case["family"])}</small><p>{e(case["passage"])}</p><b>{e(case["source"])} → {e(case["target"])}</b></td><td><b>{e(case["expected"])}</b><p>{e(case["expected_reason"])}</p></td>'
            for arm in ARMS:
                row = lookup.get((case["id"], arm), {})
                decision = row.get("decision", "ERROR" if "error" in row else "PENDING")
                status = 'ok' if decision == case["expected"] else 'bad'
                details = '<br>'.join(f'{e(k)}: {e(v)}' for k, v in row.get("judgment", {}).items())
                repeat_decisions = summary[cohort][arm]["repeat_decisions"].get(case["id"])
                html += f'<td><b class="{status}">{e(decision)}</b><details><summary>Judgment and gate</summary>{details}<p>{e(row.get("rejection_reasons", row.get("error", "")))}</p></details>'
                if repeat_decisions:
                    html += f'<small>Trials: {e(repeat_decisions)}</small>'
                html += '</td>'
            html += '</tr>'
        html += '</table>'
    html += f'<p>Fresh-case screening gate passed: <b>{e(summary["screening_gate_passed"])}</b>. Gate: zero false approvals, at most one false rejection, no decision flips on repeated fresh cases. Passing is not a guarantee of broader reliability.</p>'
    html += f'<p>Extra code gates overrode all-yes criteria in {len(summary["extra_gate_changed_decisions"])} responses (including repeat trials).</p>'
    html += f'<p>Total tokens: {summary["usage"].get("total_tokens", 0):,}. <a href="results.json">Raw results</a> · <a href="dataset.json">Frozen labels</a> · <a href="manifest.json">Run manifest</a></p>'
    html += '<h2>Frozen prompts</h2>'
    for arm, prompt in prompts.items():
        html += f'<details><summary>{e(arm)} prompt</summary><pre>{e(prompt)}</pre></details>'
    html += '<p>Reference-label differences from older experiments: ' + e(dataset["expected_label_change_note"]) + '</p>'
    html += '<p>Once used for prompt revision, these results become development/regression data. Future independent confirmation needs fresh cases and human review. Method reference: <a href="https://developers.openai.com/api/docs/guides/evaluation-best-practices">OpenAI Docs — evaluation best practices</a>.</p></html>'
    (output / "report.html").write_text(html)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-sol")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8 or not 1 <= args.repeats <= 5:
        parser.error("Use 1-8 workers and 1-5 repeats.")
    dataset, prompts, schemas = load_fixture(args.fixture)
    configuration = {
        "dataset_sha256": legacy.digest(dataset), "model": args.model,
        "prompt_sha256": {k: legacy.digest(v) for k, v in prompts.items()},
        "schema_sha256": {k: legacy.digest(v) for k, v in schemas.items()},
        "conservative_gate_source_sha256": legacy.digest(Path(strict.__file__).read_text()),
        "legacy_source_sha256": legacy.digest(Path(legacy.__file__).read_text()),
        "repeats": args.repeats, "order_seed": 20261023, "api": "responses",
        "temperature": "model default", "reasoning_effort": "model default", "max_output_tokens": 8192,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["configuration"] != configuration:
            raise ValueError("Frozen run inputs/acceptance code changed; use a new output directory.")
    else:
        manifest = {"configuration": configuration, "frozen_at_utc": datetime.now(timezone.utc).isoformat()}
        legacy.write_atomic(manifest_path, manifest)
    legacy.write_atomic(args.output_dir / "dataset.json", dataset)
    for arm, prompt in prompts.items():
        (args.output_dir / f"{arm}_prompt.txt").write_text(prompt)
        legacy.write_atomic(args.output_dir / f"{arm}_schema.json", schemas[arm])
    jobs = [(case, arm, trial) for case in dataset["cases"] for arm in ARMS
            for trial in range(1, (args.repeats if case["repeat"] else 1) + 1)]
    random.Random(configuration["order_seed"]).shuffle(jobs)
    print(f'Frozen {len(dataset["cases"])} cases; {len(jobs)} planned responses ({args.model}).', flush=True)
    if args.prepare_only:
        return 0
    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate_case, case, arm, trial, prompts[arm], schemas[arm], args.output_dir, args.model, args.offline): (case, arm, trial)
                   for case, arm, trial in jobs}
        for future in as_completed(futures):
            case, arm, trial = futures[future]
            try:
                record = future.result()
            except Exception as exc:
                record = {"id": case["id"], "arm": arm, "trial": trial, "error": f'{type(exc).__name__}: {exc}'}
            records.append(record)
            print(f'{len(records)}/{len(jobs)} {arm} {case["id"]} trial={trial}: {record.get("decision", "ERROR")}', flush=True)
            legacy.write_atomic(args.output_dir / "results.json", {
                "manifest": manifest, "records": sorted(records, key=lambda r: (r["id"], r["arm"], r["trial"])),
                "summary": summarize(dataset, records, len(jobs), args.repeats),
            })
    summary = summarize(dataset, records, len(jobs), args.repeats)
    legacy.write_atomic(args.output_dir / "summary.json", summary)
    render_report(dataset, prompts, summary, records, manifest, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
