#!/usr/bin/env python3
"""Simplify all supplied final-language QAs before compact verification.

Preserves input datasets and v2 runs. Detailed language diagnostics are a fallback,
not a prerequisite. Input is the same normalized case format as review_qa_items.py.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Literal

from pydantic import Field

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from evaluation.scripts.analysis import review_qa_items as review
from evaluation.scripts.analysis import rewrite_flagged_qa as old

CONFIG = ROOT / "evaluation/configs/qa_simplify_v3"


class Relation(review.StrictModel):
    id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    role: Literal["tested", "anchor", "removable", "uncertain"]
    reason: str = Field(min_length=1)


class Contract(review.StrictModel):
    id: str
    status: Literal["ready", "hold"]
    target: str = Field(min_length=1)
    basis: Literal["explicit", "inferred", "uncertain"]
    required_answer_components: list[str]
    relations: list[Relation]
    note: str = Field(min_length=1)


class Proposal(review.StrictModel):
    id: str
    status: Literal["revised", "unchanged", "declined"]
    question: str
    options: list[old.Option]
    removed_relation_ids: list[str]
    note: str = Field(min_length=1)


class Content(review.StrictModel):
    question_support: review.Check
    answer_support: review.Check
    answer_uniqueness: review.Check
    context_sufficiency: review.Check
    answer_leakage: review.Check
    mcq_validity: review.Check


class Verification(review.StrictModel):
    id: str
    contract_validity: old.Verdict
    same_target: old.Verdict
    removals_justified: old.Verdict
    same_language: old.Verdict
    option_meanings: list[old.OptionVerdict]
    content: Content
    naturalness: review.Rating
    processing: review.Rating
    context_economy: review.Rating


SCHEMAS = {"target": Contract, "simplify": Proposal, "verify": Verification}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def settings():
    config = read(CONFIG / "workflow.json")
    prompts = {s: (CONFIG / f"{s}.txt").read_text() for s in SCHEMAS}
    prompts.update({s: (review.CONFIG / f"{s}.txt").read_text() for s in ("structure", "burden")})
    return config, prompts


def validate_contract(data, case):
    value = Contract.model_validate(data).model_dump()
    if value["id"] != "item":
        raise ValueError("Contract ID mismatch")
    ids = [r["id"] for r in value["relations"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate relation IDs")
    for relation in value["relations"]:
        if relation["quote"] not in case["question"]:
            raise ValueError("Relation quote is not verbatim question wording")
    if case["intended_target"]:
        if value["basis"] != "explicit" or value["target"] != case["intended_target"]:
            raise ValueError("Explicit target must remain verbatim and explicit")
    elif value["basis"] == "explicit":
        raise ValueError("Inferred target cannot be labeled explicit")
    if value["status"] == "ready" and (
        value["basis"] == "uncertain" or not value["required_answer_components"]
        or any(not x.strip() for x in value["required_answer_components"])
        or not any(r["role"] == "tested" for r in value["relations"])
        or any(r["role"] == "uncertain" for r in value["relations"])
    ):
        raise ValueError("Ready contract needs an established target, components and relation roles")
    return value


def candidate_from(original, contract, data):
    proposal = Proposal.model_validate(data).model_dump()
    if proposal["id"] != "item":
        raise ValueError("Proposal ID mismatch")
    removed = proposal["removed_relation_ids"]
    removable = {r["id"] for r in contract["relations"] if r["role"] == "removable"}
    if len(removed) != len(set(removed)) or set(removed) - removable:
        raise ValueError("Only known removable relation IDs may be removed")
    if proposal["status"] == "declined":
        if proposal["question"] or proposal["options"] or removed:
            raise ValueError("Declined proposal contains a replacement")
        return None
    if [o["label"] for o in proposal["options"]] != list(original["options"]):
        raise ValueError("Every option label must remain once in original order")
    candidate = copy.deepcopy(original)
    candidate.update(question=proposal["question"], options={o["label"]: o["text"] for o in proposal["options"]})
    candidate = review.normalize_cases([candidate])[0]
    changed = old.displayed_hash(candidate) != old.displayed_hash(original)
    if proposal["status"] == "unchanged" and (changed or removed):
        raise ValueError("Unchanged proposal must exactly preserve displayed wording")
    if proposal["status"] == "revised" and not changed:
        raise ValueError("Revised proposal contains no change")
    if changed:
        candidate["original_question"] = original["original_question"] or original["question"]
        candidate["original_answer"] = original["original_answer"] or original["expected_answer"]
    return candidate


def validate_verification(data, original):
    value = Verification.model_validate(data).model_dump()
    if value["id"] != "item":
        raise ValueError("Verification ID mismatch")
    if [o["label"] for o in value["option_meanings"]] != list(original["options"]):
        raise ValueError("Every option needs one ordered meaning judgment")
    for key, check in value["content"].items():
        if key == "mcq_validity" and original["form"] == "open":
            if check["status"] != "not_applicable":
                raise ValueError("Open questions require mcq_validity not_applicable")
        elif check["status"] == "not_applicable":
            raise ValueError(f"Missing applicable content judgment: {key}")
    return value


def verification_passes(value, threshold=2):
    checks = [value[k] for k in ("contract_validity", "same_target", "removals_justified", "same_language")]
    checks += value["option_meanings"]
    checks += [v for k, v in value["content"].items() if not (k == "mcq_validity" and v["status"] == "not_applicable")]
    return all(v["status"] == "pass" for v in checks) and all(
        value[k]["score"] < threshold for k in review.LANGUAGE_FIELDS)


def accepted(checks, repeats, threshold=2):
    return (repeats >= 2 and len(checks) == repeats and
            {c["repeat"] for c in checks} == set(range(1, repeats + 1)) and
            all("error" not in c and verification_passes(c["verification"], threshold) for c in checks))


def diagnose(candidate, contract, call, attempt):
    # Diagnostic target is explicitly labeled; never written into case metadata.
    item = old.anonymous(candidate)
    item.update(intended_target=contract["target"], target_basis=contract["basis"])
    structure = review.validate_stage("structure", call("structure", {"items": [item]}, attempt, 0), [item])["item"]
    payload = dict(item, structural_inspection=structure)
    burden = review.validate_stage("burden", call("burden", {"items": [payload]}, attempt, 0), [item], {"item": structure})["item"]
    return dict(structure=structure, burden=burden)


def simplify_case(original, call, config):
    repeats, maximum = config["verification_repeats"], config["max_attempts"]
    threshold = config["language_rewrite_threshold"]
    if repeats < 2 or maximum < 1:
        raise ValueError("Require at least two verification passes and one proposal")
    result = dict(id=original["id"], original=copy.deepcopy(original), input_hash=review.digest(original),
                  status="REVIEW", accepted_case=None, contract=None, attempts=[])
    try:
        contract = validate_contract(call("target", {"original": old.anonymous(original)}, 0, 0), original)
        result["contract"] = contract
        if contract["status"] == "hold":
            result["status"] = "HOLD_TARGET"
            return result
        history, seen = [], set()
        for attempt in range(1, maximum + 1):
            step = dict(attempt=attempt)
            result["attempts"].append(step)
            proposal = call("simplify", dict(original=old.anonymous(original), contract=contract,
                                             previous_attempts=history), attempt, 0)
            step["proposal"] = proposal
            candidate = candidate_from(original, contract, proposal)
            if candidate is None:
                step["status"] = result["status"] = "DECLINED"
                return result
            step["candidate"] = candidate
            signature = old.displayed_hash(candidate)
            if signature in seen:
                step["status"] = "REPEATED_PROPOSAL"
                history.append(dict(candidate=old.anonymous(candidate), problem="This displayed wording has already failed verification; do not repeat it."))
                continue
            seen.add(signature)
            checks = []
            step["checks"] = checks
            for repeat in range(1, repeats + 1):
                try:
                    data = call("verify", dict(original=old.anonymous(original),
                                               candidate=old.anonymous(candidate), contract=contract), attempt, repeat)
                    checks.append(dict(repeat=repeat, verification=validate_verification(data, original)))
                except Exception as exc:
                    checks.append(dict(repeat=repeat, error=type(exc).__name__ + ": " + str(exc)[:400]))
            if any("error" in c for c in checks):
                step["status"] = result["status"] = "ERROR"
                return result
            if accepted(checks, repeats, threshold):
                step["status"] = result["status"] = "KEPT" if signature == old.displayed_hash(original) else "SIMPLIFIED"
                result["accepted_case"] = candidate
                return result
            step["status"] = "NOT_ACCEPTED"
            if any(c["verification"]["contract_validity"]["status"] != "pass" for c in checks):
                result["status"] = "HOLD_TARGET"
                return result  # A writer cannot fix a disputed design target.
            feedback = dict(candidate=old.anonymous(candidate), checks=checks)
            if any(c["verification"][k]["score"] >= threshold for c in checks for k in review.LANGUAGE_FIELDS):
                step["diagnostics"] = diagnose(candidate, contract, call, attempt)
                feedback["diagnostics"] = step["diagnostics"]
            history.append(feedback)
        return result
    except Exception as exc:
        result.update(status="ERROR", error=type(exc).__name__ + ": " + str(exc)[:400])
        return result


def write_report(output, results):
    lines = ["# Early QA simplification", "", "Model-screened results; original datasets unchanged. Inferred targets remain provisional.", "",
             "| Item | Status | Before | After |", "|---|---|---|---|"]
    escape = lambda s: s.replace("|", "\\|").replace("\n", "<br>")
    for r in results:
        lines.append(f"| {r['id']} | {r['status']} | {escape(r['original']['question'])} | {escape((r['accepted_case'] or {}).get('question', ''))} |")
    for r in results:
        lines += ["", "## " + r["id"], "", "Status: " + r["status"]]
        contract = r.get("contract")
        if contract:
            lines += ["", f"Target ({contract['basis']}): {contract['target']}", "", contract["note"], ""]
            lines += [f"- {x['id']} / {x['role']}: {x['quote']} — {x['reason']}" for x in contract["relations"]]
        for a in r["attempts"]:
            p = a.get("proposal", {})
            lines += ["", f"### Proposal {a['attempt']}: {a.get('status', 'ERROR')}", "", p.get("question", ""), "", p.get("note", "")]
            lines += [f"- {o['label']}. {o['text']}" for o in p.get("options", [])]
            for c in a.get("checks", []):
                if "error" in c:
                    lines += ["", c["error"]]
                    continue
                v = c["verification"]
                lines += ["", f"Verification {c['repeat']}: " + ("PASS" if verification_passes(v) else "REVIEW")]
                for k in ("contract_validity", "same_target", "removals_justified", "same_language"):
                    lines.append(f"- {k}: {v[k]['status']} — {v[k]['evidence']}")
                for k in review.LANGUAGE_FIELDS:
                    lines.append(f"- {k}: {v[k]['score']}/3 — {v[k]['evidence']}")
                for k, check in v["content"].items():
                    if check["status"] in ("fail", "uncertain"):
                        lines.append(f"- {k}: {check['status']} — {check['evidence']}")
        if r.get("error"):
            lines += ["", r["error"]]
    (output / "report.md").write_text("\n".join(lines) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--id", action="append", dest="ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    if args.workers < 1 or (args.limit is not None and args.limit < 1):
        parser.error("workers and limit must be positive")
    config, prompts = settings()
    model = args.model or config["model"]
    try:
        cases = review.normalize_cases([c for path in args.input for c in read(path)])
        if args.ids:
            if set(args.ids) - {c["id"] for c in cases}:
                raise ValueError("Unknown requested item ID")
            cases = [c for c in cases if c["id"] in args.ids]
        if args.limit is not None:
            cases = cases[:args.limit]
        if args.ids and set(args.ids) - {c["id"] for c in cases}:
            raise ValueError("Requested IDs do not fit within limit")
        output = args.output_dir.resolve()
        if any(p.resolve().is_relative_to(output) for p in args.input):
            raise ValueError("Output must not contain an input file")
        manifest = dict(version=config["version"], model=model, config=config,
                        input_hash=review.digest(cases),
                        input_files={str(p.resolve()): review.digest(read(p)) for p in args.input},
                        prompts={k: review.digest(v) for k, v in prompts.items()},
                        schemas={k: review.digest(v.model_json_schema()) for k, v in SCHEMAS.items()},
                        sources={p.name: review.digest(p.read_text()) for p in (Path(__file__), Path(old.__file__), Path(review.__file__))})
        marker = output / "manifest.json"
        if marker.exists():
            if read(marker) != manifest:
                raise ValueError("Different inputs/settings/code; use a new output directory")
        elif output.exists() and any(output.iterdir()):
            raise ValueError("Refusing unrelated nonempty output directory")
        review.write_json(marker, manifest)
        review.write_json(output / "cases.json", cases)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.error(str(exc))
    print(f"Prepared {len(cases)} forms for early simplification.", flush=True)
    if args.prepare_only:
        return 0
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    from openai import OpenAI

    def run_one(index, case):
        folder = output / "items" / f"item_{index:04d}"
        try:
            with OpenAI(max_retries=1, timeout=180) as client:
                def call(stage, payload, attempt, repeat):
                    path = folder / f"attempt_{attempt}" / f"r{repeat}_{stage}.json"
                    if stage in SCHEMAS:
                        return old.request_json(client, model, stage, payload, prompts[stage], path, SCHEMAS[stage])
                    return review.request_validated_stage(client, model, stage, payload, prompts[stage], path, payload["items"])
                result = simplify_case(case, call, config)
        except Exception as exc:
            result = dict(id=case["id"], original=case, input_hash=review.digest(case), status="ERROR",
                          accepted_case=None, contract=None, attempts=[], error=type(exc).__name__ + ": " + str(exc)[:400])
        review.write_json(folder / "result.json", result)
        print(case["id"] + ": " + result["status"], flush=True)
        return index, result

    indexed = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run_one, i, c) for i, c in enumerate(cases)]):
            i, result = future.result()
            indexed[i] = result
    results = [indexed[i] for i in range(len(cases))]
    summary = dict(total=len(results), statuses=dict(Counter(r["status"] for r in results)),
                   detailed_diagnostic_items=sum(any("diagnostics" in a for a in r["attempts"]) for r in results),
                   original_datasets_unchanged=True)
    review.write_json(output / "results.json", results)
    review.write_json(output / "ready_cases.json", [r["accepted_case"] for r in results if r["accepted_case"]])
    review.write_json(output / "rewritten_cases.json", [r["accepted_case"] for r in results if r["status"] == "SIMPLIFIED"])
    review.write_json(output / "summary.json", summary)
    write_report(output, results)
    print(json.dumps(summary), flush=True)
    return int(any(r["status"] == "ERROR" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
