#!/usr/bin/env python3
"""Read-only input checks for the six-dose, three-family Tier 1 rerun."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

PASSAGES = {
    "t1_judg9": "judg_9_1-57.txt",
    "t1_judg17_18": "judg_17_1-18_31.txt",
    "t1_2kgs6_7": "2kgs_6_24-7_20.txt",
    "t1_1kgs13": "1kgs_13_1-34.txt",
    "t1_2kgs11": "2kgs_11_1-21.txt",
    "t1_2chr26": "2chr_26_1-23.txt",
    "t1_2sam21": "2sam_21_15-22.txt",
    "t1_acts19": "acts_19_11-20.txt",
    "t1_acts20": "acts_20_7-12.txt",
    "t1_acts23": "acts_23_12-35.txt",
}
RATES = (5, 10, 15, 20, 25, 30)
FAMILIES = ("omission", "mistranslation", "grammar")
REQUIRED = (
    "passage_target.txt", "passage_target_decanonicalized.txt",
    "passage_translation.json", "qa_target_decanonicalized.json",
)


def check_inputs(root: Path, passages: list[str], *, tolerance_pp: float = 2.0) -> dict:
    if not math.isfinite(tolerance_pp) or not 0 <= tolerance_pp <= 100:
        raise ValueError("Coverage tolerance must be between 0 and 100 percentage points.")
    errors = []
    cells = []
    for pid in passages:
        if pid not in PASSAGES:
            errors.append(f"Unknown passage: {pid}")
            continue
        base = root / pid
        for suffix in ("qa_zh.json", "qa_zh_decanonicalized.json"):
            path = base / "_base" / "_shared" / f"{pid}_base_{suffix}"
            if not path.is_file() or not path.stat().st_size:
                errors.append(f"{pid}: missing shared QA {path.name}")
        conditions = ["omission/0%", "google_word_by_word"] + [
            f"{family}/{rate}%" for family in FAMILIES for rate in RATES
        ]
        seen = {family: {} for family in FAMILIES}
        previous = {}
        for condition in conditions:
            cell = base / condition
            label = f"{pid}/{condition}"
            record = {"passage": pid, "condition": condition}
            cells.append(record)
            missing = [name for name in REQUIRED if not (cell / name).is_file()
                       or not (cell / name).stat().st_size]
            if missing:
                errors.append(f"{label}: missing {', '.join(missing)}")
                continue
            try:
                for name in REQUIRED:
                    if name.endswith(".json"):
                        json.loads((cell / name).read_text(encoding="utf-8"))
                if condition == "omission/0%":
                    for name in REQUIRED[:2]:
                        if (cell / name).read_bytes() != (base / "_base" / "llm_prompt_high" / name).read_bytes():
                            errors.append(f"{label}: clean text differs from the shared source ({name})")
                    continue
                if condition == "google_word_by_word":
                    continue
                family, rate_label = condition.split("/")
                nominal = int(rate_label[:-1])
                metadata = json.loads((cell / f"{family}_metadata.json").read_text(encoding="utf-8"))
                if family == "grammar" and (
                    metadata.get("generation_mode") != "validated_bank"
                    or metadata.get("edit_style") != "llm_structural_v1"
                ):
                    errors.append(f"{label}: not an approved structural grammar variant")
                if family == "mistranslation" and metadata.get("bank_validation", {}).get("status") != "complete":
                    errors.append(f"{label}: missing completed bank validation")
                record["actual_percent"] = {}
                for name in REQUIRED[:2]:
                    file_meta = metadata["files"][Path(name).stem]
                    actual = float(file_meta["actual_affected_rate" if family == "grammar" else "actual_rate"]) * 100
                    record["actual_percent"][name] = actual
                    if not math.isfinite(actual) or abs(actual - nominal) > tolerance_pp + 1e-8:
                        errors.append(f"{label}: {name} covers {actual:.2f}% (outside ±{tolerance_pp:g} pp)")
                    if abs(float(file_meta["requested_rate"]) * 100 - nominal) > 1e-8:
                        errors.append(f"{label}: metadata has a different requested rate ({name})")
                    text = (cell / name).read_text(encoding="utf-8")
                    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    # Grammar provenance hashes JSON-encoded strings, not file bytes.
                    metadata_digest = hashlib.sha256(json.dumps(text, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest() if family == "grammar" else digest
                    if file_meta.get("output_sha256", metadata_digest) != metadata_digest:
                        errors.append(f"{label}: output hash differs from metadata ({name})")
                    key = (name, digest)
                    if key in seen[family]:
                        errors.append(f"{label}: identical to {seen[family][key]} ({name})")
                    seen[family][key] = rate_label
                    previous_key = (family, name)
                    if actual <= previous.get(previous_key, 0):
                        errors.append(f"{label}: coverage does not increase ({name})")
                    previous[previous_key] = actual
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"{label}: invalid or missing input metadata: {exc}")
    return {"ready": not errors, "coverage_tolerance_pp": tolerance_pp,
            "passages": passages, "conditions_per_passage": 20, "cells": cells, "errors": errors}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs/tier1_bsb_unblinded_5opt_think"))
    parser.add_argument("--passages", nargs="+", default=list(PASSAGES))
    parser.add_argument("--coverage-tolerance-pp", type=float, default=2.0)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--qa-dir", type=Path)
    parser.add_argument("--passage-dir", type=Path)
    args = parser.parse_args(argv)
    report = check_inputs(args.root, args.passages, tolerance_pp=args.coverage_tolerance_pp)
    for pid in args.passages:
        if pid not in PASSAGES:
            continue
        paths = []
        if args.qa_dir:
            paths.append(args.qa_dir / f"{pid}_all_formats.json")
        if args.passage_dir:
            paths.append(args.passage_dir / PASSAGES[pid])
        for path in paths:
            if not path.is_file() or not path.stat().st_size:
                report["errors"].append(f"Missing campaign input: {path}")
    report["ready"] = not report["errors"]
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{'READY' if report['ready'] else 'NOT READY'}: {len(args.passages)} passages × 20 conditions")
    for error in report["errors"][:25]:
        print(f"  {error}")
    if len(report["errors"]) > 25:
        print(f"  ... {len(report['errors']) - 25} more issues; use --report for the full list.")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
