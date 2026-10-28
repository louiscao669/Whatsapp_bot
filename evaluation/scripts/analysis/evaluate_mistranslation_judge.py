#!/usr/bin/env python3
"""Blind, resumable comparison of frozen mistranslation judge prompts."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import random
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.variants.banks.mistranslation_validation import (
    JUDGE_SCHEMA, StructuredResponseCache, digest, judgment_accepts,
    review_request, write_atomic,
)

FIXTURE = REPO_ROOT / "evaluation/configs/mistranslation_judge_holdout_v1"
ARMS = ("baseline", "revised")


def load_fixture(directory: Path):
    dataset = json.loads((directory / "cases.json").read_text())
    prompts = {arm: (directory / f"{arm}_prompt.txt").read_text() for arm in ARMS}
    seen = set()
    requests = set()
    for case in dataset["cases"]:
        case_id = case["id"]
        if not case_id.replace("_", "").isalnum() or case_id in seen:
            raise ValueError(f"Invalid or duplicated case id: {case_id}")
        seen.add(case_id)
        if case["expected"] not in ("accept", "reject") or not case["expected_reason"]:
            raise ValueError(f"Missing reference decision: {case_id}")
        request = case_request(case)
        key = digest(request)
        if key in requests:
            raise ValueError(f"Duplicate judge input: {case_id}")
        requests.add(key)
        if any(case["source"] in prompt and case["target"] in prompt for prompt in prompts.values()):
            raise ValueError(f"Potential prompt-example overlap: {case_id}")
    return dataset, prompts


def case_request(case: dict) -> dict:
    # The only input construction path: no expected label, rationale, family,
    # test id, other examples, or prior judgments reach the model.
    return review_request(case["passage"], {
        "source": case["source"], "target": case["target"], "mode": case["mode"],
    })


def evaluate_case(case, arm, trial, prompt, output, model, offline=False, client=None):
    # Each repeat has a separate cache so a repeat is a new response, not a
    # reread of trial 1. Separate files also avoid concurrent cache writes.
    path = output / "cache" / arm / f"trial_{trial}" / f"{case['id']}.json"
    judge = StructuredResponseCache(
        path, model=model, prompt=prompt, schema=JUDGE_SCHEMA,
        name="mistranslation_judgment", max_output_tokens=8192,
        offline=offline, client=client,
    )
    key, judgment = judge.get(case_request(case))
    record = judge.data["records"][key]
    return {
        "id": case["id"], "arm": arm, "trial": trial,
        "decision": "accept" if judgment_accepts(judgment) else "reject",
        "judgment": judgment, "judgment_id": key,
        "response_id": record["response_id"], "response_model": record["response_model"],
        "usage": record["usage"], "cache_file": str(path),
    }


def metrics(cases, records):
    reference = {case["id"]: case for case in cases}
    primary = [r for r in records if r["trial"] == 1 and "error" not in r]
    counts = Counter()
    families = defaultdict(Counter)
    wrong = []
    for record in primary:
        case = reference[record["id"]]
        expected, actual = case["expected"], record["decision"]
        label = ("true_accept" if actual == "accept" else "true_reject") if expected == actual else (
            "false_accept" if actual == "accept" else "false_reject"
        )
        counts[label] += 1
        families[case["family"]][label] += 1
        if expected != actual:
            wrong.append({"id": case["id"], "expected": expected, "actual": actual,
                          "explanation": record["judgment"]["explanation"]})
    accept_n = counts["true_accept"] + counts["false_reject"]
    reject_n = counts["true_reject"] + counts["false_accept"]
    repeat_groups = defaultdict(list)
    for record in records:
        if "error" not in record and reference[record["id"]]["repeat"]:
            repeat_groups[record["id"]].append(record)
    flips = [case_id for case_id, group in repeat_groups.items()
             if len({r["decision"] for r in group}) > 1]
    return {
        **{k: counts[k] for k in ("true_accept", "true_reject", "false_accept", "false_reject")},
        "scored_cases": len(primary), "expected_cases": len(cases),
        "accuracy": (counts["true_accept"] + counts["true_reject"]) / len(primary) if primary else None,
        "false_accept_rate": counts["false_accept"] / reject_n if reject_n else None,
        "false_reject_rate": counts["false_reject"] / accept_n if accept_n else None,
        "families": {k: dict(v) for k, v in sorted(families.items())},
        "misclassifications": sorted(wrong, key=lambda row: row["id"]),
        "repeat_decisions": {k: [r["decision"] for r in sorted(v, key=lambda row: row["trial"])]
                             for k, v in sorted(repeat_groups.items())},
        "repeat_flips": sorted(flips),
        "errors": sum("error" in r for r in records),
    }


def summarize(dataset, records, expected_jobs, repeats):
    summary = {arm: metrics(dataset["cases"], [r for r in records if r["arm"] == arm]) for arm in ARMS}
    complete = len(records) == expected_jobs and all("error" not in r for r in records)
    gate = dataset["evaluation_plan"]["promotion_gate"]
    usage = Counter()
    for record in records:
        u = record.get("usage") or {}
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            usage[field] += u.get(field, 0)
        usage["reasoning_tokens"] += (u.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
        usage["cached_input_tokens"] += (u.get("input_tokens_details") or {}).get("cached_tokens", 0)
    revised = summary["revised"]
    gate_evaluated = complete and repeats >= 3 and any(c["repeat"] for c in dataset["cases"])
    summary.update(
        complete=complete, completed_responses=sum("error" not in r for r in records),
        planned_responses=expected_jobs, usage=dict(usage),
        revised_passes_screening_gate=bool(
            revised["false_accept"] <= gate["max_false_accepts"]
            and revised["false_reject"] <= gate["max_false_rejects"]
            and len(revised["repeat_flips"]) <= gate["max_repeat_flips"]
        ) if gate_evaluated else None,
    )
    return summary


def render_report(dataset, summary, records, manifest, output):
    e = lambda value: escape(str(value))
    lookup = {(r["id"], r["arm"]): r for r in records if r["trial"] == 1}
    rows = []
    for case in dataset["cases"]:
        cells = []
        for arm in ARMS:
            result = lookup.get((case["id"], arm), {})
            decision = result.get("decision", "ERROR" if "error" in result else "PENDING")
            match = decision == case["expected"]
            reasons = result.get("judgment", {})
            details = "<br>".join(f"{e(k)}: {e(v)}" for k, v in reasons.items())
            repeats = summary[arm]["repeat_decisions"].get(case["id"], [])
            cells.append(f'<td class="{"ok" if match else "bad"}"><b>{e(decision)}</b>'
                         f'<details><summary>Judge explanation</summary>{details or e(result.get("error", "Pending"))}</details>'
                         + (f'<small>Trials: {e(", ".join(repeats))}</small>' if repeats else "") + '</td>')
        rows.append(f'<tr><td><b>{e(case["id"])}</b><br><small>{e(case["family"])}</small>'
                    f'<p>{e(case["passage"])}</p><p class="edit">{e(case["source"])} → {e(case["target"])}</p></td>'
                    f'<td><b>{e(case["expected"])}</b><p>{e(case["expected_reason"])}</p></td>' + ''.join(cells) + '</tr>')
    score_rows = []
    for arm in ARMS:
        m = summary[arm]
        accuracy = f'{m["accuracy"]:.1%}' if m["accuracy"] is not None else '—'
        score_rows.append(f'<tr><td>{e(arm)}</td><td>{accuracy}</td><td>{m["false_accept"]}</td>'
                          f'<td>{m["false_reject"]}</td><td>{len(m["repeat_flips"])}</td><td>{m["errors"]}</td></tr>')
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mistranslation judge held-out evaluation</title><style>
body{font:16px/1.55 system-ui,sans-serif;max-width:1400px;margin:40px auto;padding:0 24px;color:#202b38;background:#f7f8fa}
h1{font-size:30px}table{border-collapse:collapse;width:100%;background:white;margin:24px 0}th,td{padding:14px;border:1px solid #dce1e7;text-align:left;vertical-align:top}
th{background:#e9edf3}small{color:#566477}p{margin:10px 0}.ok>b{color:#087349}.bad>b{color:#b22d30}.edit{font-size:18px;font-weight:600}details{font-size:14px;margin-top:10px}summary{cursor:pointer}.note{background:#fff3d5;padding:16px;border-radius:8px}a{color:#1856aa}</style>
<h1>Mistranslation judge: held-out evaluation</h1>'''
    html += f'<p>Model: <b>{e(manifest["model"])}</b> · {len(dataset["cases"])} primary cases · {summary["completed_responses"]}/{summary["planned_responses"]} responses</p>'
    html += '<p class="note">Synthetic cases and expected labels authored by the assistant before model calls. '
    html += 'Labels have not been independently validated by a human. This measures agreement with the stated rubric on a small challenge set, not production accuracy. '
    html += 'Expected labels and reasons were not sent to the judge. The prompts were frozen before evaluation; production configuration was not changed.</p>'
    html += f'<p><b>Dataset provenance:</b> {e(dataset["provenance"])}</p><p>{e(dataset["held_out_scope"])}</p>'
    accept_count = sum(c["expected"] == "accept" for c in dataset["cases"])
    reject_count = len(dataset["cases"]) - accept_count
    repeat_count = sum(c["repeat"] for c in dataset["cases"])
    html += f'<table><tr><th>Prompt</th><th>Primary accuracy</th><th>False acceptances / {reject_count} reject cases</th><th>False rejections / {accept_count} accept cases</th><th>Cases with repeat flips / {repeat_count}</th><th>API errors</th></tr>' + ''.join(score_rows) + '</table>'
    gate_result = summary["revised_passes_screening_gate"]
    html += f'<p>Predeclared screening gate: no false acceptances, at most one false rejection, no repeated-case decision flips. Revised prompt passed: <b>{e(gate_result if gate_result is not None else "not evaluated — requires a complete run with repeat trials")}</b>.</p>'
    html += f'<p>Total tokens: {summary["usage"].get("total_tokens", 0):,}. <a href="results.json">Raw results</a> · <a href="dataset.json">Frozen dataset and labels</a> · <a href="baseline_prompt.txt">Baseline prompt</a> · <a href="revised_prompt.txt">Revised prompt</a></p>'
    html += f'<p>Primary accuracy uses only trial 1. {repeat_count} cases were selected for {manifest["configuration"]["repeats"]} independent trials before the run. Repeated results are not extra independent test examples. All cases and disagreements are displayed below.</p>'
    html += '<table><tr><th style="width:35%">Passage and candidate</th><th style="width:21%">Expected decision</th><th>Baseline</th><th>Revised</th></tr>' + ''.join(rows) + '</table>'
    html += '<p>Evaluation design reference: <a href="https://developers.openai.com/api/docs/guides/evaluation-best-practices">OpenAI Docs — evaluation best practices</a>. After using these outcomes to revise the prompt, treat this set as regression/development data and use fresh held-out cases for independent confirmation.</p></html>'
    (output / "report.html").write_text(html)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-sol")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8 or not 1 <= args.repeats <= 5:
        parser.error("Use 1-8 workers and 1-5 repeats.")
    dataset, prompts = load_fixture(args.fixture)
    configuration = {"dataset_sha256": digest(dataset), "prompt_sha256": {k: digest(v) for k, v in prompts.items()},
                     "schema_sha256": digest(JUDGE_SCHEMA), "model": args.model, "repeats": args.repeats,
                     "api": "responses", "max_output_tokens": 8192, "temperature": "model default",
                     "reasoning_effort": "model default", "order_seed": 20261022}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["configuration"] != configuration:
            raise ValueError("Frozen run settings changed. Use a new output directory.")
    else:
        manifest = {"configuration": configuration, "model": args.model,
                    "frozen_at_utc": datetime.now(timezone.utc).isoformat()}
        write_atomic(manifest_path, manifest)
    write_atomic(args.output_dir / "dataset.json", dataset)
    for arm, prompt in prompts.items():
        (args.output_dir / f"{arm}_prompt.txt").write_text(prompt)
    jobs = [(case, arm, trial) for case in dataset["cases"] for arm in ARMS
            for trial in range(1, (args.repeats if case["repeat"] else 1) + 1)]
    random.Random(configuration["order_seed"]).shuffle(jobs)
    print(f'Frozen {len(dataset["cases"])} cases, {len(jobs)} planned responses; model={args.model}', flush=True)
    if args.prepare_only:
        return 0
    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate_case, case, arm, trial, prompts[arm], args.output_dir, args.model, args.offline): (case, arm, trial)
                   for case, arm, trial in jobs}
        for future in as_completed(futures):
            case, arm, trial = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                # API errors stay errors: never turn them into judge rejections.
                result = {"id": case["id"], "arm": arm, "trial": trial, "error": f"{type(exc).__name__}: {exc}"}
            records.append(result)
            print(f'{len(records)}/{len(jobs)} {arm} {case["id"]} trial={trial}: {result.get("decision", "ERROR")}', flush=True)
            write_atomic(args.output_dir / "results.json", {
                "manifest": manifest, "records": sorted(records, key=lambda r: (r["id"], r["arm"], r["trial"])),
                "summary": summarize(dataset, records, len(jobs), args.repeats),
            })
    summary = summarize(dataset, records, len(jobs), args.repeats)
    write_atomic(args.output_dir / "summary.json", summary)
    render_report(dataset, summary, records, manifest, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
