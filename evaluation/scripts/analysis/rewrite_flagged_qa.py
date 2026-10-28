#!/usr/bin/env python3
"""Propose targeted QA revisions and accept only after repeated full rechecks.

Consumes one or more completed review_qa_items.py output directories. Saves final
outcomes and accepted cases; --keep-attempts also saves intermediate reviews.
Never edits source datasets.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from contextlib import nullcontext
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pydantic import Field

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from evaluation.scripts.analysis import review_qa_items as review

VERSION = "targeted_qa_rewrite_v1"


class Option(review.StrictModel):
    label: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Proposal(review.StrictModel):
    id: str
    status: Literal["revised", "declined"]
    question: str
    options: list[Option]
    note: str = Field(min_length=1)


class Verdict(review.StrictModel):
    status: Literal["pass", "fail", "uncertain"]
    evidence: str = Field(min_length=1)


class OptionVerdict(Verdict):
    label: str


class Preservation(review.StrictModel):
    id: str
    same_target: Verdict
    same_language: Verdict
    option_meanings: list[OptionVerdict]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings():
    config = read(review.CONFIG / "workflow.json")
    prompts = {stage: (review.CONFIG / f"{stage}.txt").read_text() for stage in config["stages"]}
    prompts["rewrite"] = (review.CONFIG / "targeted_rewrite.txt").read_text()
    prompts["preservation"] = (review.CONFIG / "rewrite_preservation.txt").read_text()
    return config, prompts


def load_reviews(directories, config, prompts):
    """Reject stale/mismatched evidence before spending any model calls."""
    records, seen = [], set()
    for directory in directories:
        directory = directory.resolve()
        manifest = read(directory / "manifest.json")
        cases = review.normalize_cases(read(directory / "cases.json"))
        results = read(directory / "results.json")
        id_map = read(directory / "id_map.json")
        anonymous_ids = {public: anon for anon, public in id_map.items()}
        if len(anonymous_ids) != len(id_map) or set(anonymous_ids) != {c["id"] for c in cases}:
            raise ValueError(f"Invalid baseline anonymization map: {directory}")
        if manifest["input_hash"] != review.digest(cases):
            raise ValueError(f"Changed cases in {directory}")
        if manifest["config_hash"] != review.digest(config) or manifest["prompt_hashes"] != {
            stage: review.digest(prompts[stage]) for stage in config["stages"]
        }:
            raise ValueError(f"Baseline criteria differ from the current reviewer: {directory}")
        by_id = {r["id"]: r for r in results}
        if len(by_id) != len(results) or set(by_id) != {c["id"] for c in cases}:
            raise ValueError(f"Review IDs do not exactly match cases: {directory}")
        for case in cases:
            cid = case["id"]
            if cid in seen:
                raise ValueError(f"Duplicate item across review directories: {cid}")
            seen.add(cid)
            result = by_id[cid]
            if result["input_hash"] != review.digest(case):
                raise ValueError(f"Stale review: {cid}")
            if result["complete"]:
                rows = result["reviews"]
                expected = set(range(1, manifest["repeats"] + 1))
                if len(rows) != len(expected) or {r["repeat"] for r in rows} != expected:
                    raise ValueError(f"Missing/duplicate baseline repeats: {cid}")
                for row in rows:
                    # The reviewer hashes anonymous model inputs before mapping
                    # row IDs back to public IDs; aggregate hashes use public IDs.
                    model_input_hash = review.digest(dict(case, id=anonymous_ids[cid]))
                    if row.get("input_hash") != model_input_hash or row["id"] != cid:
                        raise ValueError(f"Mismatched baseline repeat: {cid}")
                    # Never trust a stored final label in place of its evidence.
                    resolved = review.resolve(row["content_validity"], row["structural_inspection"],
                                              row["language_accessibility"], config["language_rewrite_threshold"])
                    if any(row[k] != v for k, v in resolved.items()):
                        raise ValueError(f"Baseline decision disagrees with evidence: {cid}")
            records.append(dict(case=case, baseline=result, source_review_dir=str(directory)))
    return records


def select_records(records, include_single=False, ids=None, limit=None):
    requested = set(ids or [])
    known = {r["case"]["id"] for r in records}
    if requested - known:
        raise ValueError("Unknown requested IDs: " + ", ".join(sorted(requested - known)))
    selected, inventory = [], []
    for record in records:
        cid, baseline = record["case"]["id"], record["baseline"]
        rows = baseline["reviews"]
        count = sum(r.get("language_status") == "REWRITE" for r in rows)
        if not baseline["complete"] or len(rows) < 2:
            reason = "incomplete_or_insufficient_baseline_review"
        elif not count or (not include_single and count != len(rows)):
            reason = "not_selected_by_rewrite_policy"
        elif requested and cid not in requested:
            reason = "outside_requested_ids"
        elif limit is not None and len(selected) >= limit:
            reason = "outside_limit"
        else:
            reason = "selected"
            selected.append(record)
        inventory.append(dict(id=cid, reason=reason, rewrite_votes=count, repeats=len(rows)))
    if requested - {r["case"]["id"] for r in selected}:
        raise ValueError("Requested IDs must meet the rewrite policy and fit within --limit")
    return selected, inventory


def feedback(row):
    return {
        "target": row["content_validity"]["target"],
        "target_basis": row["content_validity"]["target_basis"],
        "content_issues": {k: row["content_validity"][k] for k in review.CONTENT_FIELDS
                           if row["content_validity"][k]["status"] in ("fail", "uncertain")},
        "structure": row["structural_inspection"],
        "wording": row["language_accessibility"],
    }


def anonymous(case):
    return dict(copy.deepcopy(case), id="item")


def proposal_case(original, data):
    proposal = Proposal.model_validate(data).model_dump()
    if proposal["id"] != "item":
        raise ValueError("Proposal changed the requested ID")
    if proposal["status"] == "declined":
        if proposal["question"] or proposal["options"]:
            raise ValueError("A declined proposal must not contain replacement wording")
        return None
    if not proposal["question"].strip():
        raise ValueError("Replacement question is empty")
    labels = [o["label"] for o in proposal["options"]]
    if labels != list(original["options"]):
        raise ValueError("Proposal must preserve every option label and its order")
    if any(not o["text"].strip() for o in proposal["options"]):
        raise ValueError("Replacement option is empty")
    revised = copy.deepcopy(original)
    revised.update(question=proposal["question"].strip(),
                   options={o["label"]: o["text"].strip() for o in proposal["options"]})
    # Keep any earlier source intention; otherwise bind preservation to the
    # ORIGINAL input, never to a potentially drifted previous revision.
    revised["original_question"] = original["original_question"] or original["question"]
    revised["original_answer"] = original["original_answer"] or original["expected_answer"]
    return review.normalize_cases([revised])[0]


def validate_preservation(data, original):
    result = Preservation.model_validate(data).model_dump()
    if result["id"] != "item":
        raise ValueError("Preservation review changed the requested ID")
    if [x["label"] for x in result["option_meanings"]] != list(original["options"]):
        raise ValueError("Every original option needs one ordered meaning judgment")
    return result


def preservation_passes(data):
    return all(x["status"] == "pass" for x in
               [data["same_target"], data["same_language"], *data["option_meanings"]])


def displayed_hash(case):
    return review.digest({"question": case["question"], "options": case["options"]})


def audit_candidate(original, candidate, call, config, repeats):
    checks = []
    for repeat in range(1, repeats + 1):
        try:
            preservation = validate_preservation(call("preservation", {
                "original": anonymous(original), "proposed": anonymous(candidate),
            }, repeat), original)
            model_case = anonymous(candidate)

            def judge(stage, payload):
                return call(stage, payload, repeat)

            row = review.review_batch([model_case], judge, config["language_rewrite_threshold"])[0]
            checks.append(dict(repeat=repeat, preservation=preservation, review=row))
        except Exception as exc:
            checks.append(dict(repeat=repeat, error=type(exc).__name__ + ": " + str(exc)[:400]))
    return checks


def accepted(checks, repeats):
    return (repeats >= 2 and len(checks) == repeats and {r["repeat"] for r in checks} == set(range(1, repeats + 1))
            and all("error" not in r and preservation_passes(r["preservation"])
                    and r["review"]["decision"] == "KEEP"
                    and r["review"]["content_status"] == "PASS"
                    and r["review"]["language_status"] == "PASS" for r in checks))


def rewrite_record(record, call, config, max_attempts=2, repeats=2):
    """Bounded revision with a fixed original contract and blind rechecks.

    call(stage, payload, attempt, repeat) is injected for offline contract tests.
    Writer feedback is never included in the re-review payloads.
    """
    if max_attempts < 1 or repeats < 2:
        raise ValueError("Need at least one attempt and two recheck passes")
    original = record["case"]
    result = dict(id=original["id"], input_hash=review.digest(original), original=original,
                  source_review_dir=record["source_review_dir"], status="UNRESOLVED",
                  accepted_case=None, attempts=[])
    initial = [feedback(r) for r in record["baseline"]["reviews"]]
    # Remove public IDs nested within the baseline evidence as well.
    for f in initial:
        f["structure"] = dict(f["structure"], id="item")
        f["wording"] = dict(f["wording"], id="item")
    history, seen = [], {displayed_hash(original)}
    for attempt in range(1, max_attempts + 1):
        step = dict(attempt=attempt)
        result["attempts"].append(step)
        payload = dict(original=anonymous(original), initial_reviews=initial, previous_attempts=history)
        try:
            raw = call("rewrite", payload, attempt, 0)
        except Exception as exc:
            step.update(status="ERROR", error=type(exc).__name__ + ": " + str(exc)[:400])
            result["status"] = "ERROR"
            break
        step["proposal"] = raw
        try:
            candidate = proposal_case(original, raw)
        except ValueError as exc:
            step.update(status="INVALID_PROPOSAL", error=str(exc)[:400])
            history.append(dict(proposal=raw, problem=step["error"]))
            continue
        if candidate is None:
            step["status"] = result["status"] = "DECLINED"
            break
        step["candidate"] = candidate
        signature = displayed_hash(candidate)
        if signature in seen:
            step["status"] = "NO_CHANGE_OR_REPEAT"
            history.append(dict(proposed=anonymous(candidate), problem="Unchanged or previously proposed wording; the flagged issues still need a substantive edit."))
            continue
        seen.add(signature)
        checks = audit_candidate(original, candidate,
                                 lambda stage, data, repeat: call(stage, data, attempt, repeat),
                                 config, repeats)
        step["checks"] = checks
        if any("error" in r for r in checks):
            step["status"] = result["status"] = "ERROR"
            break
        if accepted(checks, repeats):
            step["status"] = result["status"] = "ACCEPTED"
            result["accepted_case"] = candidate
            break
        step["status"] = "NOT_ACCEPTED"
        history.append(dict(proposed=anonymous(candidate), rechecks=[
            dict(repeat=r["repeat"], preservation=r["preservation"], **feedback(r["review"])) for r in checks]))
    return result


def request_json(client, model, stage, payload, prompt, path, schema_class):
    schema = schema_class.model_json_schema()
    fingerprint = review.digest(dict(model=model, stage=stage, payload=payload, prompt=prompt, schema=schema))
    if path.exists():
        cached = read(path)
        if cached["request_hash"] != fingerprint:
            raise ValueError("Cached response belongs to different input or criteria")
        return cached["parsed"]
    response = client.responses.create(
        model=model, input=[{"role": "system", "content": prompt},
                            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        text={"format": {"type": "json_schema", "name": "qa_" + stage,
                         "strict": True, "schema": schema}},
    )
    if response.status != "completed" or not response.output_text:
        review.write_json(path.parent / "incomplete" / f"{path.stem}_{response.id}.json", response.model_dump())
        raise ValueError("Model did not complete a structured response")
    parsed = json.loads(response.output_text)
    review.write_json(path, dict(request_hash=fingerprint, model=response.model,
                                response_id=response.id, usage=response.usage.model_dump(), parsed=parsed))
    return parsed


def prepare_output(output, directories, manifest, selected, inventory):
    output = output.resolve()
    for source in directories:
        source = source.resolve()
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError("Output must be separate from every input review directory")
    marker = output / "manifest.json"
    if marker.exists():
        if read(marker) != manifest:
            raise ValueError("Output belongs to different inputs/settings; choose a new directory")
    elif output.exists() and any(output.iterdir()):
        raise ValueError("Refusing to write into an unrelated nonempty directory")
    review.write_json(marker, manifest)
    review.write_json(output / "selection.json", inventory)
    review.write_json(output / "selected_inputs.json", selected)


def compact_result(result):
    """Retain the final outcome without proposals or intermediate model traces."""
    final = {k: v for k, v in result.items() if k != "attempts"}
    steps = result.get("attempts", [])
    if steps:
        last = steps[-1]
        proposal = last.get("proposal", {})
        if isinstance(proposal, dict) and proposal.get("note"):
            final["note"] = proposal["note"]
        if last.get("error"):
            final["error"] = last["error"]
        if result["status"] == "ACCEPTED":
            checks = last.get("checks", [])
            final["validation"] = {
                "review_passes": len(checks),
                "all_checks_passed": accepted(checks, len(checks)),
                "validation_type": "model_review",
            }
    return final


def write_report(output, results):
    lines = ["# Targeted QA rewrite results", "",
             "Accepted means all model preservation, content, structure and burden checks passed in every repeat. "
             "It is not a human validation result. Original datasets were not edited.", "",
             "| Item | Status |", "|---|---|"]
    lines += [f"| {r['id']} | {r['status']} |" for r in results]
    for result in results:
        original = result["original"]
        lines += ["", "## " + result["id"], "", "Original: " + original["question"], ""]
        lines += [f"- {k}. {v}" for k, v in original["options"].items()]
        if result.get("error"):
            lines += ["", "Error: " + result["error"]]
        if "attempts" not in result:
            revised = result.get("accepted_case")
            if revised:
                lines += ["", "Accepted wording: " + revised["question"], ""]
                lines += [f"- {k}. {v}" for k, v in revised["options"].items()]
            if result.get("note"):
                lines += ["", result["note"]]
        for attempt in result.get("attempts", []):
            lines += ["", f"### Attempt {attempt['attempt']}: {attempt['status']}", ""]
            proposal = attempt.get("proposal", {})
            if not isinstance(proposal, dict):
                proposal = {}
            lines += [proposal.get("question", ""), "", proposal.get("note", "")]
            options = proposal.get("options")
            lines += [f"- {o['label']}. {o['text']}" for o in (options if isinstance(options, list) else [])
                      if isinstance(o, dict) and "label" in o and "text" in o]
            if attempt.get("error"):
                lines += ["", "Error: " + attempt["error"]]
            for check in attempt.get("checks", []):
                lines += ["", f"Pass {check['repeat']}:"]
                if "error" in check:
                    lines.append("- Error: " + check["error"])
                    continue
                row, preservation = check["review"], check["preservation"]
                lines.append("- Review: " + row["decision"])
                for key in ("same_target", "same_language"):
                    lines.append(f"- {key}: {preservation[key]['status']} — {preservation[key]['evidence']}")
                for option in preservation["option_meanings"]:
                    lines.append(f"- Option {option['label']} meaning: {option['status']} — {option['evidence']}")
                for key in review.LANGUAGE_FIELDS:
                    rating = row["language_accessibility"][key]
                    lines.append(f"- {key}: {rating['score']}/3 — {rating['evidence']}")
                for key in review.CONTENT_FIELDS:
                    check_row = row["content_validity"][key]
                    if check_row["status"] in ("fail", "uncertain"):
                        lines.append(f"- Content / {key}: {check_row['status']} — {check_row['evidence']}")
    (output / "report.md").write_text("\n".join(map(str, lines)) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-dir", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--writer-model")
    parser.add_argument("--judge-model")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--review-repeats", type=int, default=2)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--include-single-pass", action="store_true")
    parser.add_argument("--id", action="append", dest="ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--keep-attempts", action="store_true",
                        help="Keep intermediate proposals and review traces (default: final outcomes only)")
    args = parser.parse_args(argv)
    if args.max_attempts < 1 or args.review_repeats < 2 or args.workers < 1 or (args.limit is not None and args.limit < 1):
        parser.error("Need positive attempts/workers/limit and at least two review repeats")
    config, prompts = load_settings()
    try:
        records = load_reviews(args.review_dir, config, prompts)
        selected, inventory = select_records(records, args.include_single_pass, args.ids, args.limit)
        writer, judge = args.writer_model or config["model"], args.judge_model or config["model"]
        manifest = dict(version=VERSION, inputs_hash=review.digest(selected),
                        inventory_hash=review.digest(inventory), writer_model=writer, judge_model=judge,
                        max_attempts=args.max_attempts, review_repeats=args.review_repeats,
                        config_hash=review.digest(config), prompt_hashes={k: review.digest(v) for k, v in prompts.items()},
                        source_hashes={p.name: review.digest(p.read_text()) for p in (Path(__file__), Path(review.__file__))},
                        schema_hashes={c.__name__: review.digest(c.model_json_schema()) for c in (Proposal, Preservation)},
                        policy="accept only unanimous KEEP plus all preservation checks pass; export separately",
                        keep_attempts=args.keep_attempts)
        prepare_output(args.output_dir, args.review_dir, manifest, selected, inventory)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    print(f"Selected {len(selected)} question forms for targeted rewriting.", flush=True)
    if args.prepare_only:
        print("Prepared inputs only; no model calls or question edits.")
        return 0
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    from openai import OpenAI

    def run_one(index, record):
        folder = args.output_dir / "items" / f"item_{index:04d}"
        checkpoint = folder / "result.json"
        if not args.keep_attempts and checkpoint.exists():
            saved = read(checkpoint)
            if saved["input_hash"] != review.digest(record["case"]) or saved["original"] != record["case"]:
                raise ValueError("Saved outcome belongs to different input")
            if saved["status"] in ("ACCEPTED", "DECLINED", "UNRESOLVED"):
                return index, compact_result(saved)
        try:
            cache = nullcontext(folder) if args.keep_attempts else TemporaryDirectory(prefix="qa-rewrite-")
            with cache as cache_dir, OpenAI(max_retries=1, timeout=180) as client:
                def call(stage, payload, attempt, repeat):
                    path = Path(cache_dir) / f"attempt_{attempt}" / f"r{repeat}_{stage}.json"
                    if stage in ("rewrite", "preservation"):
                        return request_json(client, writer if stage == "rewrite" else judge, stage,
                                            payload, prompts[stage], path,
                                            Proposal if stage == "rewrite" else Preservation)
                    return review.request_validated_stage(client, judge, stage, payload, prompts[stage],
                                                          path, payload["items"])
                result = rewrite_record(record, call, config, args.max_attempts, args.review_repeats)
        except Exception as exc:
            result = dict(id=record["case"]["id"], input_hash=review.digest(record["case"]),
                          original=record["case"], source_review_dir=record["source_review_dir"],
                          status="ERROR", accepted_case=None, attempts=[],
                          error=type(exc).__name__ + ": " + str(exc)[:400])
        if not args.keep_attempts:
            result = compact_result(result)
        review.write_json(folder / "result.json", result)
        print(record["case"]["id"] + ": " + result["status"], flush=True)
        return index, result

    indexed = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, i, record) for i, record in enumerate(selected)]
        for future in as_completed(futures):
            index, result = future.result()
            indexed[index] = result
    results = [indexed[i] for i in range(len(selected))]
    accepted_cases = [r["accepted_case"] for r in results if r["status"] == "ACCEPTED"]
    summary = dict(selected=len(selected), statuses=dict(Counter(r["status"] for r in results)),
                   accepted=len(accepted_cases), unchanged_original_datasets=True)
    review.write_json(args.output_dir / "results.json", results)
    review.write_json(args.output_dir / "accepted_cases.json", accepted_cases)
    review.write_json(args.output_dir / "summary.json", summary)
    write_report(args.output_dir, results)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return int(any(r["status"] == "ERROR" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
