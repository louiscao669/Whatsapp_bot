#!/usr/bin/env python3
"""Repair export defects in the Tier 1 QA files.

The ``tier1_QAs_easy`` export carries three defects that are invisible until
they distort a scored run:

  1. RECORDS WITH NO content_id -- one judg9 record had the literal string
     "None". content_id is the key the curated verse-window table uses, so such
     a record matches no window; and having no ``reference`` either, it also
     falls past the --answer-verse-window fallback to the WHOLE passage. In the
     2026-08-04 run it received all 57 verses while every other item got 3, and
     scored 1.0 on a factually wrong answer.

  2. content_id COLLISIONS, with exact duplicates mixed in. t1_2chr26:rxf3 and
     t1_acts20:jxkk each cover THREE records: two identical, and one asking a
     genuinely different question ("What did Uzziah build in the wilderness?"
     vs "Why did Uzziah build towers and cisterns?").

     These need opposite treatment. The identical copies are export artifacts --
     asked twice, counted twice in the denominator, double-weighted in an IRT
     fit -- and are dropped. The distinct question is real content and is
     re-keyed to "<content_id>#2", never dropped.

     Re-keying is not cosmetic. translate_llm_qa_to_chinese.py mints
     passage_id as "uw-<content_id>-<q_type>", so two different questions were
     producing the same id, and match_standard in scoring can then pair a
     generated answer with the wrong standard answer. Colliding ids also make
     per-item IRT parameters unattributable.

  3. MISSING reference -- t1_judg9:o93q has reference: null. Harmless while the
     curated windows cover it (they key on content_id), but with WINDOWS=""
     it degrades to whole-passage context.

Defect 3 is repaired from ``tier1_qa_verse_windows.json``, which carries a
hand-checked ``reference`` per content_id -- an authoritative source, not an
inference. Anything it cannot resolve is reported and left alone.

Usage (from repo root):

    python evaluation/scripts/data_prep/clean_tier1_qa.py            # report only
    python evaluation/scripts/data_prep/clean_tier1_qa.py --write
    python evaluation/scripts/data_prep/clean_tier1_qa.py --self-test

After --write, rebuild the blinded inputs:

    bash evaluation/scripts/campaigns/build_tier1_pseudonymized.sh
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_QA_DIR = Path("evaluation/datasets/qa/tier1_QAs_easy")
DEFAULT_WINDOWS = Path("QA_algorithm/inputs/tier1_qa_verse_windows.json")


class CleanError(Exception):
    pass


def has_content_id(item: dict) -> bool:
    value = item.get("content_id")
    return bool(value) and str(value).strip() not in {"", "None", "null"}


def question_stem(item: dict) -> str:
    for key in ("open", "mcq"):
        content = (item.get(key) or {}).get("content") or ""
        match = re.search(r"<question>\s*(.*?)\s*<question>", content, re.S)
        if match:
            return match.group(1).strip()
    return str(item.get("question") or "").strip()


def load_reference_index(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("windows") if isinstance(data, dict) else data
    index = {}
    for record in records or []:
        content_id = str(record.get("content_id") or "").strip()
        reference = str(record.get("reference") or "").strip()
        if content_id and reference:
            index.setdefault(content_id, reference)
    return index


def base_content_id(content_id: str) -> str:
    """Drop a re-keying suffix: 't1_2chr26:rxf3#2' -> 't1_2chr26:rxf3'."""
    return str(content_id or "").split("#", 1)[0]


def clean_items(
    items: list[dict], reference_index: dict[str, str]
) -> tuple[list[dict], list[str]]:
    kept: list[dict] = []
    log: list[str] = []
    # content_id -> question stems already kept under it, in order.
    seen_questions: dict[str, list[str]] = {}

    for item in items:
        if not has_content_id(item):
            log.append(
                f"    drop   no content_id ({item.get('content_id')!r})"
                f"  Q={question_stem(item)[:52]!r}"
            )
            continue

        content_id = str(item["content_id"]).strip()
        stem = question_stem(item)
        previous = seen_questions.setdefault(content_id, [])

        if stem in previous:
            # Same id, same question: a true export duplicate. Asked twice,
            # counted twice, double-weighted in any per-item fit.
            log.append(f"    dedup  {content_id}  Q={stem[:52]!r}")
            continue

        previous.append(stem)
        if len(previous) > 1:
            # Same id, DIFFERENT question: real content that must keep its own
            # identity. Dropping it loses a question; leaving it collides in
            # passage_id ("uw-<content_id>-<q_type>") so scoring can match an
            # answer to the wrong rubric.
            new_id = f"{content_id}#{len(previous)}"
            item = {**item, "content_id": new_id}
            log.append(f"    rekey  {content_id} -> {new_id}  Q={stem[:52]!r}")
            content_id = new_id

        if not item.get("reference"):
            # Look up under the base id: a re-keyed sibling shares the verse.
            reference = reference_index.get(base_content_id(content_id))
            if reference:
                item = {**item, "reference": reference}
                log.append(f"    ref    {content_id} <- {reference!r} (from verse windows)")
            else:
                log.append(f"    WARN   {content_id} has no reference and none available")
        kept.append(item)

    return kept, log


def self_test() -> int:
    def q(text):
        return {"open": {"content": f"<question>{text}<question><answer>a<answer>"}}

    items = [
        {"content_id": "t1_x:aaa", "reference": "1:1", **q("first")},
        {"content_id": "None", **q("dropped")},
        {"content_id": "t1_x:bbb", "reference": None, **q("needs a reference")},
        {"content_id": "t1_x:aaa", "reference": "1:1", **q("first")},      # true duplicate
        {"content_id": "t1_x:aaa", "reference": "1:1", **q("different!")},  # collision
        {"content_id": "t1_x:ccc", "reference": None, **q("unresolvable")},
    ]
    kept, log = clean_items(items, {"t1_x:bbb": "2:5", "t1_x:aaa": "1:1"})
    ids = [i["content_id"] for i in kept]
    stems = [question_stem(i) for i in kept]
    checks = [
        ("None dropped", "None" not in ids),
        ("true duplicate removed", stems.count("first") == 1),
        ("colliding question KEPT", "different!" in stems),
        ("colliding question re-keyed", "t1_x:aaa#2" in ids),
        ("original keeps its id", "t1_x:aaa" in ids),
        ("all ids unique", len(ids) == len(set(ids))),
        ("four items kept", len(kept) == 4),
        ("reference backfilled", kept[1]["reference"] == "2:5"),
        ("existing reference untouched", kept[0]["reference"] == "1:1"),
        ("base id resolves for re-keyed", base_content_id("t1_x:aaa#2") == "t1_x:aaa"),
        ("unresolvable reported", any("WARN" in line for line in log)),
        ("unresolvable still kept", "t1_x:ccc" in ids),
    ]
    failed = 0
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        failed += not ok
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--qa-dir", type=Path, default=DEFAULT_QA_DIR)
    parser.add_argument("--glob", default="*_all_formats.json")
    parser.add_argument("--windows", type=Path, default=DEFAULT_WINDOWS)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply the repairs. Without it the script only reports.",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()

    paths = sorted(args.qa_dir.glob(args.glob))
    if not paths:
        print(f"error: no QA files matching {args.glob} in {args.qa_dir}", file=sys.stderr)
        return 2

    reference_index = load_reference_index(args.windows)
    print(f"reference index: {len(reference_index)} content_id(s) from {args.windows}\n")

    total_before = total_after = 0
    changed_files = 0
    warnings = 0
    for path in paths:
        items = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            print(f"  skip {path.name}: not a JSON array")
            continue
        kept, log = clean_items(items, reference_index)
        total_before += len(items)
        total_after += len(kept)
        warnings += sum(1 for line in log if "WARN" in line)
        if log:
            changed_files += 1
            print(f"  {path.name}  {len(items)} -> {len(kept)}")
            print("\n".join(log))
            if args.write:
                path.write_text(
                    json.dumps(kept, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8",
                )

    print(f"\n{changed_files} file(s) with defects; items {total_before} -> {total_after}")
    if warnings:
        print(f"{warnings} item(s) still missing a reference -- add them to the "
              f"verse-window table or set reference by hand.")
    if not args.write:
        print("\nreport only. Re-run with --write to apply, then rebuild:")
        print("  bash evaluation/scripts/campaigns/build_tier1_pseudonymized.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
