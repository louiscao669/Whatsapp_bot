#!/usr/bin/env python3
"""Review final QA wording with separate content and accessibility checks.

Input: a JSON array of {id, passage, question, expected_answer, form,
options?, correct_option?, intended_target?, original_question?, original_answer?}.
Passage must be the clean context shown to the participant. No corpus is mutated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "evaluation/configs/qa_review_v2"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Check(StrictModel):
    status: Literal["pass", "fail", "uncertain", "not_applicable"]
    evidence: str = Field(min_length=1)


class MeaningProfile(StrictModel):
    answer_explicitness: Literal["direct", "nearby_connection", "inference", "uncertain"]
    semantic_relation: str = Field(min_length=1)
    answer_scope: Literal["single_component", "multiple_components", "uncertain"]
    passage_span: Literal["one_sentence", "nearby", "wider", "uncertain"]


CONTENT_FIELDS = (
    "target_preservation", "question_support", "answer_support",
    "answer_uniqueness", "context_sufficiency", "answer_leakage", "mcq_validity",
)


class ContentItem(StrictModel):
    id: str
    target: str = Field(min_length=1)
    target_basis: Literal["explicit", "inferred", "uncertain"]
    target_preservation: Check
    question_support: Check
    answer_support: Check
    answer_uniqueness: Check
    context_sufficiency: Check
    answer_leakage: Check
    mcq_validity: Check
    meaning_profile: MeaningProfile


class ContentResponse(StrictModel):
    items: list[ContentItem]


class Feature(StrictModel):
    kind: Literal["nested_modifier", "delayed_query", "role_tracking", "reference_chain",
                  "layered_speech", "negation_scope", "option_overlap"]
    quote: str = Field(min_length=1)
    required_operations: str = Field(min_length=1)
    concern: Literal["ordinary", "potential_burden"]
    reason: str = Field(min_length=1)


class StructureItem(StrictModel):
    id: str
    parse_summary: str = Field(min_length=1)
    features: list[Feature]


class StructureResponse(StrictModel):
    items: list[StructureItem]


class Rating(StrictModel):
    score: int = Field(ge=0, le=3)
    evidence: str = Field(min_length=1)


class FeatureAssessment(StrictModel):
    feature_index: int = Field(ge=0)
    assessment: Literal["manageable", "avoidable_burden", "uncertain"]
    reason: str = Field(min_length=1)


class BurdenItem(StrictModel):
    id: str
    naturalness: Rating
    processing: Rating
    context_economy: Rating
    structure_assessments: list[FeatureAssessment]


class BurdenResponse(StrictModel):
    items: list[BurdenItem]


SCHEMAS = {"content_validity": ContentResponse, "structure": StructureResponse,
           "burden": BurdenResponse}
LANGUAGE_FIELDS = ("naturalness", "processing", "context_economy")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_cases(records: list[dict]) -> list[dict]:
    if not isinstance(records, list) or not records:
        raise ValueError("Input must be a nonempty JSON array")
    cases = []
    seen = set()
    for record in records:
        for field in ("id", "question", "passage", "expected_answer", "form"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"Missing nonempty string: {field}")
        if record["id"] in seen:
            raise ValueError(f"Duplicate input ID: {record['id']}")
        seen.add(record["id"])
        form = record["form"]
        if form not in ("open", "mcq"):
            raise ValueError(f"Unsupported form: {form}")
        options = record.get("options") or {}
        if not isinstance(options, dict) or any(
            not isinstance(k, str) or not k or not isinstance(v, str) or not v.strip()
            for k, v in options.items()
        ):
            raise ValueError("Options must map nonempty labels to nonempty strings")
        key = record.get("correct_option") or ""
        if form == "mcq" and (len(options) < 2 or key not in options):
            raise ValueError(f"MCQ needs at least two options and a valid key: {record['id']}")
        if form == "open" and (options or key):
            raise ValueError("Open item must not contain options or a key")
        item = {k: record[k] for k in ("id", "question", "passage", "expected_answer", "form")}
        item.update(options=options, correct_option=key)
        for field in ("intended_target", "original_question", "original_answer"):
            value = record.get(field) or ""
            if not isinstance(value, str):
                raise ValueError(f"{field} must be a string")
            item[field] = value
        cases.append(item)
    return cases


def quote_in_displayed_item(quote, case):
    quote = " ".join(quote.split())
    options = case["options"]
    displayed = [case["question"], *options.values(),
                 "\n".join(f"{key}. {text}" for key, text in options.items())]
    if any(quote in " ".join(text.split()) for text in displayed):
        return True
    # An option-overlap feature may quote multiple complete alternatives joined
    # by punctuation. Require every quoted option to match verbatim, and every
    # supplied label to match its own option. Do not accept ellipses/paraphrases.
    chunks = []
    for label, text in options.items():
        text = " ".join(text.split())
        chunks.append((label, re.escape(text)))
        chunks.append((label, re.escape(label) + r"\s*[.:：、]\s*" + re.escape(text)))
    separators = re.compile(r"\s*(?:[;；/／|]|versus|vs\.?|and)\s*")

    def consume(remaining, seen):
        for label, pattern in chunks:
            match = re.match(pattern, remaining)
            if not match:
                continue
            tail = remaining[match.end():]
            if not tail and len(seen | {label}) >= 2:
                return True
            separator = separators.match(tail)
            if separator and consume(tail[separator.end():], seen | {label}):
                return True
        return False

    return consume(quote, set())


def validate_stage(stage: str, data: dict, cases: list[dict], structures=None) -> dict:
    parsed = SCHEMAS[stage].model_validate(data).model_dump()
    ids = [x["id"] for x in parsed["items"]]
    if sorted(ids) != sorted(x["id"] for x in cases):
        raise ValueError(f"{stage}: each requested ID must occur exactly once")
    by_id = {x["id"]: x for x in cases}
    for row in parsed["items"]:
        case = by_id[row["id"]]
        if stage == "content_validity":
            can_compare = bool(case["intended_target"] or case["original_question"]
                               or case["original_answer"])
            for name in CONTENT_FIELDS:
                na_allowed = ((name == "target_preservation" and not can_compare)
                              or (name == "mcq_validity" and case["form"] == "open"))
                if (row[name]["status"] == "not_applicable") != na_allowed:
                    raise ValueError(f"{row['id']}: invalid applicability for {name}")
            if case["intended_target"] and row["target_basis"] != "explicit":
                raise ValueError("An explicit target must not be silently inferred or replaced")
            if not case["intended_target"] and row["target_basis"] == "explicit":
                # Whether a design target was supplied is an input fact. Some
                # responses call a target inferred from original Q/A "explicit".
                # Correct only this provenance label; retain the raw response,
                # target text, uncertainty, and all substantive judgments.
                row["target_basis"] = "inferred"
        elif stage == "structure":
            for feature in row["features"]:
                if not quote_in_displayed_item(feature["quote"], case):
                    raise ValueError(f"{row['id']}: structural quote is not in displayed wording")
        elif stage == "burden":
            indices = [x["feature_index"] for x in row["structure_assessments"]]
            if sorted(indices) != list(range(len(structures[row["id"]]["features"]))):
                raise ValueError(f"{row['id']}: every structural feature needs one assessment")
    return {x["id"]: x for x in parsed["items"]}


def resolve(content: dict, structure: dict, burden: dict, threshold: int = 2) -> dict:
    """One deterministic admission decision; no averaging or deletion."""
    failures = [name for name in CONTENT_FIELDS if content[name]["status"] == "fail"]
    uncertainties = [name for name in CONTENT_FIELDS if content[name]["status"] == "uncertain"]
    if content["target_basis"] == "uncertain":
        uncertainties.append("target")
    content_status = "HOLD" if failures else "REVIEW" if uncertainties else "PASS"
    burden_failures = [name for name in LANGUAGE_FIELDS if burden[name]["score"] >= threshold]
    concerns = [i for i, f in enumerate(structure["features"]) if f["concern"] == "potential_burden"]
    unresolved = [x["feature_index"] for x in burden["structure_assessments"]
                  if x["assessment"] == "uncertain"]
    # A structural concern on an otherwise passing item is a review hold, not an
    # established wording defect. Clear burden failures require a rewrite.
    disagreement = bool((concerns or any(x["assessment"] == "avoidable_burden"
                                        for x in burden["structure_assessments"]))
                        and not burden_failures)
    language_status = ("REWRITE" if burden_failures else "REVIEW"
                       if unresolved or disagreement else "PASS")
    decision = ("HOLD_CONTENT" if content_status == "HOLD" else "REWRITE"
                if language_status == "REWRITE" else "REVIEW"
                if "REVIEW" in (content_status, language_status) else "KEEP")
    return {"decision": decision, "content_status": content_status,
            "language_status": language_status, "content_failures": failures,
            "content_uncertainties": uncertainties, "language_failures": burden_failures,
            "structural_concerns": concerns, "unresolved_features": unresolved,
            "structure_burden_disagreement": disagreement}


def request_stage(client, model, stage, payload, prompt, path):
    schema = SCHEMAS[stage].model_json_schema()
    request_hash = digest({"model": model, "stage": stage, "prompt": prompt,
                           "payload": payload, "schema": schema})
    if path.exists():
        saved = json.loads(path.read_text())
        if saved["request_hash"] != request_hash:
            raise ValueError("Cached review belongs to different wording, context or prompts")
        return saved["parsed"]
    response = client.responses.create(
        model=model,
        input=[{"role": "system", "content": prompt},
               {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        text={"format": {"type": "json_schema", "name": f"qa_{stage}",
                         "strict": True, "schema": schema}},
    )
    if getattr(response, "status", None) != "completed" or not response.output_text:
        raise ValueError("Judge did not complete a structured review")
    parsed = json.loads(response.output_text)
    write_json(path, {"request_hash": request_hash, "model": response.model,
                     "response_id": response.id, "usage": response.usage.model_dump(),
                     "parsed": parsed})
    return parsed


def request_validated_stage(client, model, stage, payload, prompt, path, cases, attempts=3):
    """Retry invalid evidence/schema output without changing the judging rubric.

    Preserve rejected responses rather than editing model evidence to make it
    pass. Valid cached stages remain usable, including after a failed batch.
    """
    structures = ({row["id"]: row["structural_inspection"] for row in payload["items"]}
                  if stage == "burden" else None)
    for attempt in range(attempts):
        parsed = request_stage(client, model, stage, payload, prompt, path)
        try:
            validate_stage(stage, parsed, cases, structures)
        except ValueError as exc:
            archive_dir = path.parent / "invalid"
            archive_dir.mkdir(parents=True, exist_ok=True)
            index = 1
            while (archive_dir / f"{path.stem}_attempt{index}.json").exists():
                index += 1
            archive = archive_dir / f"{path.stem}_attempt{index}.json"
            path.replace(archive)
            write_json(archive.with_suffix(".error.json"), {
                "validation_error": str(exc), "stage": stage,
                "repair": "Repeat identical model request; no prompt, rubric, or evidence editing.",
            })
            if attempt + 1 == attempts:
                raise
        else:
            return parsed


def review_batch(cases, judge, threshold=2):
    """Three calls: content, structural evidence, whole-item burden."""
    content = validate_stage("content_validity", judge("content_validity", {"items": cases}), cases)
    language_items = []
    for case in cases:
        # Passing only the target (not content verdicts) avoids asking language
        # judges to reconfirm the content decision or repeat its responsibilities.
        row = {k: v for k, v in case.items() if k not in ("original_question", "original_answer")}
        row["intended_target"] = case["intended_target"] or content[case["id"]]["target"]
        row["target_basis"] = content[case["id"]]["target_basis"]
        language_items.append(row)
    structure = validate_stage("structure", judge("structure", {"items": language_items}), cases)
    burden_payload = {"items": [dict(row, structural_inspection=structure[row["id"]])
                                for row in language_items]}
    burden = validate_stage("burden", judge("burden", burden_payload), cases, structure)
    return [dict(id=c["id"], input_hash=digest(c),
                 content_validity=content[c["id"]], structural_inspection=structure[c["id"]],
                 language_accessibility=burden[c["id"]],
                 **resolve(content[c["id"]], structure[c["id"]], burden[c["id"]], threshold))
            for c in cases]


def aggregate(cases, rows, repeats):
    result = []
    for case in cases:
        reviews = sorted((x for x in rows if x["id"] == case["id"]), key=lambda x: x["repeat"])
        votes = [x["decision"] for x in reviews]
        complete = (len(reviews) == repeats and len({x["repeat"] for x in reviews}) == repeats
                    and "REVIEW_ERROR" not in votes)
        stable = complete and len(set(votes)) == 1
        decision = votes[0] if stable else "REVIEW"
        result.append({"id": case["id"], "input_hash": digest(case), "decision": decision,
                       "complete": complete, "stable": stable, "votes": votes,
                       "reviews": reviews})
    return result


def write_report(path, cases, results, manifest):
    by_id = {x["id"]: x for x in cases}
    lines = ["# QA review: content validity and language accessibility", "",
             f"Version: {manifest['version']}. Model: {manifest['model']}. "
             f"Stage: {manifest['review_stage']}. Repeats: {manifest['repeats']}.", "",
             "Model judgments are screening evidence, not measured human difficulty. "
             "Disagreement or incomplete review requires review. No questions were edited or removed.", "",
             "| Item | Decision | Repeated decisions |", "|---|---|---|"]
    lines += [f"| {r['id']} | {r['decision']} | {', '.join(r['votes'])} |" for r in results]
    for result in results:
        case = by_id[result["id"]]
        lines += ["", "## " + case["id"], "", case["question"], ""]
        lines += [f"{k}. {v}" for k, v in case["options"].items()]
        for row in result["reviews"]:
            lines += ["", f"**Run {row['repeat']}: {row['decision']}**", ""]
            if row["decision"] == "REVIEW_ERROR":
                lines += ["Incomplete judge output: " + row["error"]]
                continue
            for name in CONTENT_FIELDS:
                c = row["content_validity"][name]
                lines += [f"- Content / {name}: {c['status']} — {c['evidence']}"]
            for f in row["structural_inspection"]["features"]:
                lines += [f"- Structure / {f['kind']}: {f['concern']} — {f['quote']}: {f['reason']}"]
            for name in LANGUAGE_FIELDS:
                rating = row["language_accessibility"][name]
                lines += [f"- Language / {name}: {rating['score']}/3 — {rating['evidence']}"]
            if row["structure_burden_disagreement"]:
                lines += ["- Structural concern without a failed burden dimension: review required."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--review-stage", choices=("final_source", "final_translation", "after_revision"),
                        default="final_translation")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--retry-failed-only", action="store_true",
                        help="Repair only already-finished failed batches; do not write aggregate reports")
    args = parser.parse_args()
    if min(args.repeats, args.batch_size, args.workers) < 1:
        parser.error("Repeats, batch size and workers must be positive")
    config = json.loads((CONFIG / "workflow.json").read_text())
    prompts = {stage: (CONFIG / f"{stage}.txt").read_text() for stage in config["stages"]}
    cases = normalize_cases(json.loads(args.input.read_text()))
    model = args.model or config["model"]
    manifest = dict(version=config["version"], model=model, input_hash=digest(cases),
                    repeats=args.repeats, batch_size=args.batch_size, review_stage=args.review_stage,
                    config_hash=digest(config), prompt_hashes={k: digest(v) for k, v in prompts.items()})
    output = args.output_dir
    # Never overwrite the supplied input, including accidentally naming it after
    # an output artifact within the selected directory.
    if args.input.resolve().is_relative_to(output.resolve()):
        parser.error("Input must be outside the output directory")
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        parser.error("Output directory belongs to a different review; choose a new directory")
    write_json(manifest_path, manifest)
    write_json(output / "cases.json", cases)
    ids = {f"q{i:04}": case["id"] for i, case in enumerate(cases)}
    anonymous = [dict(case, id=key) for key, case in zip(ids, cases)]
    write_json(output / "id_map.json", ids)
    jobs = []
    for repeat in range(1, args.repeats + 1):
        shuffled = anonymous.copy()
        random.Random(27102026 + repeat).shuffle(shuffled)
        for start in range(0, len(shuffled), args.batch_size):
            jobs.append((repeat, start // args.batch_size, shuffled[start:start + args.batch_size]))
    if args.prepare_only:
        print(f"Prepared {len(cases)} items, {len(jobs) * 3} planned judge calls; no model calls.")
        return 0
    if args.retry_failed_only:
        failed_jobs = []
        for job in jobs:
            repeat, batch, _ = job
            path = output / "batches" / f"r{repeat}_b{batch}.json"
            if path.exists() and any(row["decision"] == "REVIEW_ERROR"
                                     for row in json.loads(path.read_text())):
                failed_jobs.append(job)
        jobs = failed_jobs
        print(f"Retrying {len(jobs)} already-finished failed batches; preserving valid cached stages.", flush=True)
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    from openai import OpenAI

    def run_job(job):
        repeat, batch, items = job
        try:
            with OpenAI(max_retries=1, timeout=180) as client:
                def judge(stage, payload):
                    return request_validated_stage(
                        client, model, stage, payload, prompts[stage],
                        output / "responses" / f"r{repeat}_b{batch}_{stage}.json", items)
                reviewed = review_batch(items, judge, config["language_rewrite_threshold"])
        except Exception as exc:
            # Preserve an explicit hold for every affected item. Do not silently
            # turn absent, refused, malformed or incomplete responses into passes.
            reviewed = [{"id": x["id"], "decision": "REVIEW_ERROR",
                         "error": type(exc).__name__ + ": " + str(exc)[:400]} for x in items]
        for row in reviewed:
            row["id"] = ids[row["id"]]
            row["repeat"] = repeat
        write_json(output / "batches" / f"r{repeat}_b{batch}.json", reviewed)
        print(f"Repeat {repeat}, batch {batch}: {dict(Counter(x['decision'] for x in reviewed))}", flush=True)
        return reviewed

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_job, job) for job in jobs]
        for future in as_completed(futures):
            rows.extend(future.result())
    if args.retry_failed_only:
        return int(any(row["decision"] == "REVIEW_ERROR" for row in rows))
    results = aggregate(cases, rows, args.repeats)
    write_json(output / "results.json", results)
    summary = {"items": len(cases), "decisions": dict(Counter(x["decision"] for x in results)),
               "incomplete": sum(not x["complete"] for x in results),
               "disagreements": sum(x["complete"] and not x["stable"] for x in results),
               "completed_at": time.time()}
    write_json(output / "summary.json", summary)
    write_report(output / "report.md", cases, results, manifest)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 1 if summary["incomplete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
