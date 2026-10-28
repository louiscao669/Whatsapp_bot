#!/usr/bin/env python3
"""Extend a curated bank with independently judged, non-overlapping new spans."""
from __future__ import annotations

import copy
import math
import re
from pathlib import Path

from evaluation.scripts.variants.banks import generate_mistranslation_banks as gen
from evaluation.scripts.variants.banks.mistranslation_validation import (
    JUDGE_PROMPT, JUDGE_SCHEMA, StructuredResponseCache, digest, judgment_accepts,
    validate_reviewed_bank, write_atomic,
)
from evaluation.scripts.variants.current import create_mistranslation_variants as variants

PROMPT = gen.GENERATION_PROMPT + """
Extend an existing, independently approved bank to cover NEW source spans.
The coverage goal is measured in original source characters, not candidate count.
All previously accepted edits must remain usable. Propose sources whose EVERY
occurrence is outside occupied_spans (zero-based character offsets into passage).
Do not propose another target for an already covered source. Focus on specific
facts in the uncovered parts of the passage. Never pad an edit with unchanged
words to inflate coverage. It is acceptable to return fewer strong candidates.
previously_attempted_pairs includes approvals, judge rejections, deterministic
rejections, and user exclusions, with reasons. Never repeat a listed pair.
Do not replace vague quantities with another potentially overlapping quantity
(many/some/several), remove uncertainty, or change a generic object into a subtype.
Prefer clearly incompatible facts, while keeping natural Chinese and the same
syntactic role. Do not weaken these requirements to reach the coverage goal.
"""


def covered_spans(text: str, entries: list[dict]) -> list[dict]:
    return variants.find_occurrences(text, variants.normalized_replacements({"replacements": entries}))


def available_coverage(text: str, entries: list[dict]) -> float:
    return sum(row["source_content_chars"] for row in covered_spans(text, entries)) / gen.content_len(text)


def new_span_reasons(item: dict, text: str, entries: list[dict]) -> list[str]:
    reasons = gen.hard_rejection_reasons(item, text)
    if reasons:
        return reasons
    occupied = covered_spans(text, entries)
    for match in re.finditer(re.escape(item["source"].strip()), text):
        if any(variants.overlaps(*match.span(), row["start"], row["end"]) for row in occupied):
            return ["Source overlaps an already approved span; propose an uncovered fact instead."]
    return []


def extend_bank(*, passage: str, parent: dict, cache_dir: Path, output: Path,
                exclusions: list[dict], target_rate: float = .32, max_rounds: int = 6,
                max_items: int = 40, workers: int = 4, offline: bool = False, client=None) -> dict:
    validate_reviewed_bank(parent, passage)
    if not 0 < target_rate <= 1 or max_rounds < 1 or max_items < 1:
        raise ValueError("Invalid coverage extension limits")
    gen.validate_workers(1, workers)
    judge = StructuredResponseCache(cache_dir / "judgments.json", model="gpt-6-sol",
        prompt=JUDGE_PROMPT, schema=JUDGE_SCHEMA, name="mistranslation_judgment",
        max_output_tokens=8192, offline=offline, client=client)
    if judge.identity != parent["validation"]["judge"]:
        raise ValueError("Existing approvals must use the same judge identity")
    accepted = copy.deepcopy(parent["replacements"])
    history = [{"source": e["source"], "target": e["target"], "status": "accepted",
                "rejection_reasons": []} for e in accepted]
    history.extend({"source": e["source"], "target": e["target"], "status": "user_excluded",
                    "rejection_reasons": [e["reason"]]} for e in exclusions)
    old_review = Path(parent["validation"]["review_file"])
    if old_review.is_file():
        import json
        for row in json.loads(old_review.read_text()).get("previously_attempted_pairs", []):
            if (row["source"], row["target"]) not in {(h["source"], h["target"]) for h in history}:
                history.append(row)
    attempted = {(h["source"], h["target"]) for h in history}
    audit = {"parent_bank_id": parent["bank_id"], "target_rate": target_rate,
             "rounds": [], "candidates": [], "status": "in_progress"}
    audit_path = cache_dir / "coverage_review.json"
    spec = {**copy.deepcopy(parent["configuration"]), "coverage_extension": {
        "version": 1, "parent_bank_id": parent["bank_id"], "target_rate": target_rate,
        "prompt_sha256": digest(PROMPT), "excluded_pairs": exclusions,
        "max_rounds": max_rounds, "max_items": max_items,
    }}

    def save_bank():
        coverage = available_coverage(passage, accepted)
        bank = copy.deepcopy(parent)
        bank.pop("refill", None)
        bank.update(configuration=spec, replacements=accepted,
                    bank_id=digest({"configuration": spec, "replacements": accepted}))
        bank["generation"]["coverage_refills"] = copy.deepcopy(audit["rounds"])
        bank["validation"].update(accepted_count=len(accepted), review_file=str(audit_path),
            rejected_count=sum(not c["accepted"] for c in audit["candidates"]),
            parent_review_file=parent["validation"]["review_file"])
        bank["coverage_extension"] = {"actual_available_rate": coverage,
            "target_rate": target_rate, "target_met": coverage >= target_rate,
            "rounds_used": len(audit["rounds"]), "retained_parent_candidates": len(parent["replacements"])}
        validate_reviewed_bank(bank, passage)
        write_atomic(output, bank)
        audit["actual_available_rate"] = coverage
        write_atomic(audit_path, audit)
        return bank

    for round_index in range(max_rounds):
        coverage = available_coverage(passage, accepted)
        if coverage >= target_rate:
            break
        missing = math.ceil(target_rate * gen.content_len(passage)) - sum(
            row["source_content_chars"] for row in covered_spans(passage, accepted))
        limit = min(max_items, max(8, math.ceil(missing / 2)))
        proposer = StructuredResponseCache(cache_dir / "proposals.json", model="gpt-6-sol",
            prompt=PROMPT, schema=gen.proposal_schema(limit), name="mistranslation_proposals",
            max_output_tokens=32768, offline=offline, client=client)
        print(f"{parent['chapter']}: coverage {coverage:.2%}; refill {round_index + 1}/{max_rounds}, up to {limit} candidates", flush=True)
        proposal_id, raw = proposer.get({"passage": passage, "chapter": parent["chapter"],
            "max_items": limit, "remaining_source_characters": missing,
            "occupied_spans": [{"start": r["start"], "end": r["end"], "source": r["source"]}
                               for r in covered_spans(passage, accepted)],
            "previously_attempted_pairs": history})
        audit["rounds"].append({"proposal_id": proposal_id, "identity": proposer.identity,
                                "proposed_count": len(raw["replacements"])})
        fresh = []
        for item in raw["replacements"]:
            pair = gen.replacement_pair(item)
            if pair in attempted:
                continue
            attempted.add(pair)
            reasons = new_span_reasons(item, passage, accepted)
            if reasons:
                history.append({"source": pair[0], "target": pair[1], "status": "hard_rejected", "rejection_reasons": reasons})
                audit["candidates"].append({**item, "accepted": False, "rejection_reasons": reasons})
            else:
                fresh.append(gen.normalize_replacement(item, passage))
        for entry, judgment_id, judgment in gen.review_candidates(fresh, passage=passage, judge=judge, workers=workers):
            reasons = gen.judgment_rejection_reasons(judgment)
            if not reasons:
                reasons = new_span_reasons(entry, passage, accepted)
            approved = judgment_accepts(judgment) and not reasons
            reviewed = {**entry, "review": {"judgment_id": judgment_id, "judgment": judgment}}
            audit["candidates"].append({**reviewed, "accepted": approved, "rejection_reasons": reasons})
            history.append({"source": entry["source"], "target": entry["target"],
                            "status": "accepted" if approved else "rejected", "rejection_reasons": reasons})
            if approved:
                accepted.append(reviewed)
            write_atomic(audit_path, audit)
        save_bank()
    audit["status"] = "complete" if available_coverage(passage, accepted) >= target_rate else "target_not_met"
    bank = save_bank()
    if not bank["coverage_extension"]["target_met"]:
        raise ValueError(f"Coverage target unmet for {parent['chapter']}: {bank['coverage_extension']['actual_available_rate']:.2%}; partial bank saved")
    return bank
