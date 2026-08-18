#!/usr/bin/env python3
"""Assign each tier-1 QA item a RANDOMIZED 3-verse answer window.

Why this exists
---------------
`generate_passage_feature_profiles.py` uses a *deterministic* window: the
question's own reference +/- N verses, always centred on the reference.  That
makes window position a constant function of the reference, so anything the
window controls (how much surrounding context the respondent sees, where in the
window the answer sits) is perfectly confounded with the item.

This script instead picks, per item, a **uniformly random 3-verse window among
the windows that still contain everything the question needs**.  The answer
verse therefore lands at a random position (first / middle / last), decoupling
window position from item identity.

Two things it checks before randomizing
---------------------------------------
1. **Does the question need context beyond its own reference verse?**  Some
   gold answers live outside the verse the pipeline tagged (e.g. 2 Kings 7:3
   "Why did four leprous men go to the Arameans?" -- the reason is in 7:4).
   The required span is the union of the pipeline's `reference` span and the
   minimal span whose text actually contains the answer.
2. **Does the required span fit in 3 verses?**  Items needing more than 3 are
   EXCLUDED (recorded in `excluded`, with a reason) rather than silently given
   a window that cannot support their answer.

Verse indexing traps this handles
---------------------------------
* In NIV-style text the FIRST verse of a chapter prints as the CHAPTER number,
  not "1".  1 Kings 13 opens "13 By the word of the Lord ..." == 13:1, and a
  naive scan reads that as verse 13 -- which also occurs later in the chapter.
  Parsed with a sequential-expectation state machine instead.
* Two tier-1 passages cross a chapter boundary (2 Kings 6:24-7:20 and
  Judges 17:1-18:31).  Verses are flattened to passage ordinals, so 6:33 -> 7:1
  is an ordinary step and windows may span the seam.  Labels stay chapter:verse.

Output contains VERSE NUMBERS ONLY -- never verse text.

Usage
-----
    python3 QA_algorithm/scripts/anchor_irt/build_tier1_verse_windows.py \
        --qa-root "/path/to/v3/combo/qa_generation" \
        --spans   QA_algorithm/inputs/tier1_required_spans.json \
        --out     QA_algorithm/inputs/tier1_qa_verse_windows.json

    # regenerate the required-span annotation with an LLM instead of the
    # checked-in one (gpt-4.1-mini, temperature 0), and report disagreements:
    python3 ... --llm-spans --spans-out /tmp/llm_spans.json --compare-spans

    python3 ... --self-test
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WINDOW_SIZE = 3
DEFAULT_SEED = 20260803

# tier1 id -> passage filename under <qa_root>/fixtures/passages/tier1/
PASSAGE_FILES = {
    "t1_judg9": "judg_9_1-57.txt",
    "t1_judg17_18": "judg_17_1-18_31.txt",
    "t1_2kgs6_7": "2kgs_6_24-7_20.txt",
    "t1_1kgs13": "1kgs_13_1-34.txt",
    "t1_2kgs11": "2kgs_11_1-21.txt",
    "t1_2sam21": "2sam_21_15-22.txt",
    "t1_2chr26": "2chr_26_1-23.txt",
    "t1_acts19": "acts_19_11-20.txt",
    "t1_acts20": "acts_20_7-12.txt",
    "t1_acts23": "acts_23_12-35.txt",
}


class WindowError(Exception):
    pass


# --------------------------------------------------------------------------
# verse indexing
# --------------------------------------------------------------------------

VERSE_MARKER_RE = re.compile(r"(?<![\w\]\-–—])(\d{1,3})\s+")
REFERENCE_RE = re.compile(
    r"(\d+)\s*:\s*(\d+)(?:\s*[-–—]\s*(?:(\d+)\s*:\s*)?(\d+))?"
)


def build_verse_index(
    text: str, *, chapter_start: int, verse_start: int, chapter_end: int, verse_end: int
) -> list[str]:
    """Return ordered ['9:1', '9:2', ...] labels as they appear in the passage."""
    markers = [
        int(m.group(1))
        for m in VERSE_MARKER_RE.finditer(text)
        if 1 <= int(m.group(1)) <= 200
    ]

    out: list[tuple[int, int]] = []
    chapter = chapter_start
    expected = verse_start
    for num in markers:
        if not out and verse_start == 1 and num == chapter_start:
            out.append((chapter, 1))  # chapter number standing in for verse 1
            expected = 2
            continue
        if num == expected:
            out.append((chapter, num))
            expected += 1
            continue
        if num == chapter + 1 and chapter < chapter_end:
            chapter += 1  # new chapter; its number stands in for verse 1
            out.append((chapter, 1))
            expected = 2
            continue
        continue  # a number inside the prose (prices, ages, troop counts)

    if not out:
        raise WindowError("no verse markers recovered")
    if out[0] != (chapter_start, verse_start):
        raise WindowError(f"first verse {out[0]} != expected ({chapter_start},{verse_start})")
    if out[-1] != (chapter_end, verse_end):
        raise WindowError(f"last verse {out[-1]} != expected ({chapter_end},{verse_end})")
    if len(set(out)) != len(out):
        raise WindowError("duplicate verse ids in index")
    return [f"{c}:{v}" for c, v in out]


def parse_reference(ref: str, index: list[str]) -> list[str]:
    """'7:3' -> ['7:3'];  '26:4-5' -> ['26:4','26:5'];  ranges resolved via ordinals."""
    m = REFERENCE_RE.search(ref or "")
    if not m:
        raise WindowError(f"unparseable reference: {ref!r}")
    ch, v1 = int(m.group(1)), int(m.group(2))
    first = f"{ch}:{v1}"
    if first not in index:
        raise WindowError(f"reference {first} not in passage index")
    if m.group(4) is None:
        return [first]
    ch2 = int(m.group(3)) if m.group(3) else ch
    last = f"{ch2}:{int(m.group(4))}"
    if last not in index:
        raise WindowError(f"reference end {last} not in passage index")
    i, j = index.index(first), index.index(last)
    if j < i:
        i, j = j, i
    return index[i : j + 1]


# --------------------------------------------------------------------------
# window selection
# --------------------------------------------------------------------------


def candidate_windows(index: list[str], required: list[str]) -> list[list[str]]:
    """All in-bounds WINDOW_SIZE-verse windows containing the whole required span."""
    lo = index.index(required[0])
    hi = index.index(required[-1])
    span_len = hi - lo + 1
    if span_len > WINDOW_SIZE:
        return []
    out = []
    for start in range(hi - WINDOW_SIZE + 1, lo + 1):
        if start < 0 or start + WINDOW_SIZE > len(index):
            continue
        out.append(index[start : start + WINDOW_SIZE])
    return out


def pick_window(candidates: list[list[str]], *, key: str, seed: int) -> list[str]:
    """Uniform choice, seeded by (seed, key) so reruns are byte-identical."""
    digest = hashlib.sha256(f"{seed}|{key}".encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    return rng.choice(candidates)


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------


def item_question(item: dict) -> str:
    op = item.get("open") or {}
    return str(op.get("original_question") or item.get("question") or "").strip()


def normalize_question(q: str) -> str:
    """Whitespace/case-insensitive form used for identity. Punctuation is kept:
    'What did Micah steal?' and 'What did Micah steal' are different questions."""
    return re.sub(r"\s+", " ", (q or "").strip().lower())


def span_key(passage_id: str, question: str) -> str:
    """Annotation key. Content-addressed, so it survives appends, inserts and
    reorders of the QA file -- unlike a positional {passage_id}#{index} key,
    which silently re-points at a different question when items move.

    Deliberately does NOT include the occurrence number: the required span is a
    property of the QUESTION, so a repeated question reuses one annotation.
    """
    digest = hashlib.sha1(normalize_question(question).encode("utf-8")).hexdigest()
    return f"{passage_id}:{digest[:10]}"


def item_key(passage_id: str, question: str, occurrence: int) -> str:
    """Per-ITEM key, used to seed the window draw. Includes the occurrence index
    so two copies of the same question get independently drawn windows."""
    return f"{span_key(passage_id, question)}#{occurrence}"


def item_answer(item: dict) -> str:
    op = item.get("open") or {}
    return str(op.get("original_answer") or item.get("answer") or "").strip()


def load_tier1(
    qa_root: Path, qa_file: Path | None = None
) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """Load the tier-1 CSV plus QA items.

    Two accepted layouts:
      * default -- one file per passage, outputs/tier1_pipeline/{pid}_all_formats.json
      * --qa-file -- a single combined file (e.g. outputs/tier1_shortened.json)
        holding every passage's items, grouped here by each record's passage_id.
    """
    csv_path = qa_root / "fixtures" / "obscure_narrative_passages_tier1.csv"
    if not csv_path.exists():
        raise WindowError(f"tier1 csv not found: {csv_path}")
    meta = {r["id"]: r for r in csv.DictReader(csv_path.open(encoding="utf-8"))}

    items: dict[str, list[dict]] = {pid: [] for pid in meta}

    if qa_file is not None:
        if not qa_file.exists():
            raise WindowError(f"QA file not found: {qa_file}")
        data = json.loads(qa_file.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise WindowError(f"{qa_file} must be a JSON list of QA records")
        unknown: Counter[str] = Counter()
        for rec in data:
            if not isinstance(rec, dict):
                continue
            pid = rec.get("passage_id")
            if pid in items:
                items[pid].append(rec)
            else:
                unknown[str(pid)] += 1
        if unknown:
            raise WindowError(
                f"records reference unknown passage_id(s): {dict(unknown)}. "
                f"Add a row to {csv_path.name} and a passage .txt first."
            )
        return meta, items

    for pid in meta:
        qa_path = qa_root / "outputs" / "tier1_pipeline" / f"{pid}_all_formats.json"
        if not qa_path.exists():
            raise WindowError(f"QA output not found: {qa_path}")
        data = json.loads(qa_path.read_text(encoding="utf-8"))
        items[pid] = [i for i in data if isinstance(i, dict)]
    return meta, items


# --------------------------------------------------------------------------
# optional LLM required-span pass (temperature 0)
# --------------------------------------------------------------------------

LLM_INSTRUCTIONS = (
    "You are given a Bible passage with numbered verses, one question, and its "
    "gold answer. Return the MINIMAL contiguous span of verses whose text alone "
    "is sufficient for a reader to produce the gold answer. Do not include "
    "verses that merely provide background or name entities the question "
    "already names. Return JSON only: "
    '{\"start\": \"CH:VV\", \"end\": \"CH:VV\", \"reason\": \"one short clause\"}'
)


def llm_required_span(
    *, passage_text: str, question: str, answer: str, reference: str, model: str
) -> dict:
    from openai import OpenAI  # imported lazily; only needed with --llm-spans

    client = OpenAI()
    payload = json.dumps(
        {
            "instructions": LLM_INSTRUCTIONS,
            "passage": passage_text,
            "question": question,
            "gold_answer": answer,
            "pipeline_reference": reference,
        },
        ensure_ascii=False,
    )
    resp = client.responses.create(model=model, input=payload, temperature=0)
    text = getattr(resp, "output_text", "") or ""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    return json.loads(stripped[start : end + 1])


# --------------------------------------------------------------------------
# main build
# --------------------------------------------------------------------------


def build(
    *,
    qa_root: Path,
    spans: dict[str, Any],
    seed: int,
    qa_file: Path | None = None,
) -> tuple[dict, list[dict]]:
    """Returns (map, needs_annotation). Items whose span_key is already present
    in `spans` are reused untouched -- nothing is re-judged."""
    meta, items_by_passage = load_tier1(qa_root, qa_file)
    windows: list[dict] = []
    excluded: list[dict] = []
    needs_annotation: list[dict] = []
    seen_question: dict[str, str] = {}

    for pid, row in meta.items():
        passage_path = qa_root / "fixtures" / "passages" / "tier1" / PASSAGE_FILES[pid]
        index = build_verse_index(
            passage_path.read_text(encoding="utf-8"),
            chapter_start=int(row["chapter_start"]),
            verse_start=int(row["verse_start"]),
            chapter_end=int(row["chapter_end"]),
            verse_end=int(row["verse_end"]),
        )

        occurrence: Counter[str] = Counter()
        for idx, item in enumerate(items_by_passage[pid]):
            question = item_question(item)
            answer = item_answer(item)
            skey = span_key(pid, question)
            occ = occurrence[skey]
            occurrence[skey] += 1
            key = item_key(pid, question, occ)
            ann = spans.get(skey)
            base = {
                "key": key,
                "span_key": skey,
                "occurrence": occ,
                "passage_id": pid,
                "item_index": idx,
                "content_id": item.get("content_id"),
                "passage_reference": row["reference"],
                "reference": item.get("reference"),
            }

            if ann is None:
                # New question: cannot place a window until its required span is
                # judged. Emit a fill-in stub rather than guessing.
                stub_span = None
                stub_error = None
                try:
                    if item.get("reference"):
                        stub_span = parse_reference(item["reference"], index)
                    else:
                        stub_error = "item has no 'reference' field"
                except WindowError as exc:
                    stub_error = str(exc)
                needs_annotation.append(
                    {
                        **base,
                        "question": question,
                        "gold_answer": answer,
                        "suggested_required_span": stub_span,
                        "suggested_from": "pipeline reference span (UNVERIFIED)",
                        "error": stub_error,
                    }
                )
                excluded.append({**base, "reason": "no_required_span_annotation"})
                continue

            required = list(ann["required_span"])
            bad = [v for v in required if v not in index]
            if bad:
                excluded.append({**base, "reason": f"span_verse_not_in_passage:{bad}"})
                continue

            lo, hi = index.index(required[0]), index.index(required[-1])
            span_len = hi - lo + 1
            if span_len > WINDOW_SIZE:
                excluded.append(
                    {
                        **base,
                        "required_span": required,
                        "required_span_length": span_len,
                        "reason": "required_span_exceeds_window",
                    }
                )
                continue

            cands = candidate_windows(index, required)
            if not cands:
                excluded.append(
                    {**base, "required_span": required, "reason": "no_in_bounds_window"}
                )
                continue

            chosen = pick_window(cands, key=key, seed=seed)
            ref_span = (
                parse_reference(item["reference"], index)
                if item.get("reference")
                else None
            )

            dup_of = seen_question.get(question) if question else None
            if question and dup_of is None:
                seen_question[question] = key

            windows.append(
                {
                    **base,
                    "reference_span": ref_span,
                    "reference_inferred": bool(ann.get("reference_inferred")),
                    "required_span": required,
                    "required_span_length": span_len,
                    "requires_context_beyond_reference": bool(
                        ref_span is None or set(required) - set(ref_span)
                    ),
                    "context_note": ann.get("note"),
                    "answer_not_fully_in_passage": bool(
                        ann.get("answer_not_fully_in_passage")
                    ),
                    "window": chosen,
                    "window_ordinals": [index.index(v) for v in chosen],
                    "answer_position_in_window": chosen.index(required[0]),
                    "n_candidate_windows": len(cands),
                    "candidate_windows": cands,
                    "at_passage_edge": len(cands) < WINDOW_SIZE - span_len + 1,
                    "duplicate_question_of": dup_of,
                }
            )

    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_size": WINDOW_SIZE,
        "seed": seed,
        "key_scheme": "sha1(normalized question)[:10] + occurrence -- content-addressed, order-invariant",
        "span_source": spans.get("_meta", {}).get("source", "unknown"),
        "qa_root_name": qa_root.name,  # name only; absolute paths differ per machine
        "counts": {
            "windows": len(windows),
            "excluded": len(excluded),
            "needs_annotation": len(needs_annotation),
            "requires_context_beyond_reference": sum(
                1 for w in windows if w["requires_context_beyond_reference"]
            ),
            "duplicate_questions": sum(1 for w in windows if w["duplicate_question_of"]),
            "answer_position_in_window": dict(
                sorted(Counter(w["answer_position_in_window"] for w in windows).items())
            ),
            "n_candidate_windows": dict(
                sorted(Counter(w["n_candidate_windows"] for w in windows).items())
            ),
        },
        "windows": windows,
        "excluded": excluded,
    }, needs_annotation


# --------------------------------------------------------------------------
# verification
# --------------------------------------------------------------------------


def verify(result: dict, qa_root: Path, qa_file: Path | None = None) -> list[str]:
    """Return a list of problems; empty means clean."""
    problems: list[str] = []
    meta, _ = load_tier1(qa_root, qa_file)
    indexes = {
        pid: build_verse_index(
            (qa_root / "fixtures" / "passages" / "tier1" / PASSAGE_FILES[pid]).read_text(
                encoding="utf-8"
            ),
            chapter_start=int(row["chapter_start"]),
            verse_start=int(row["verse_start"]),
            chapter_end=int(row["chapter_end"]),
            verse_end=int(row["verse_end"]),
        )
        for pid, row in meta.items()
    }

    for w in result["windows"]:
        idx = indexes[w["passage_id"]]
        key = w["key"]
        if len(w["window"]) != WINDOW_SIZE:
            problems.append(f"{key}: window size {len(w['window'])}")
        if any(v not in idx for v in w["window"]):
            problems.append(f"{key}: window verse outside passage")
        ords = [idx.index(v) for v in w["window"]]
        if ords != list(range(ords[0], ords[0] + WINDOW_SIZE)):
            problems.append(f"{key}: window not contiguous")
        if not set(w["required_span"]).issubset(set(w["window"])):
            problems.append(f"{key}: window does not cover required span")
        if w["window"] not in w["candidate_windows"]:
            problems.append(f"{key}: chosen window not among candidates")

    # no verse text may leak into the map: every verse-bearing field must be
    # nothing but "chapter:verse" tokens.
    verse_token = re.compile(r"^\d+:\d+$")
    verse_fields = ("window", "required_span", "reference_span", "candidate_windows")
    for w in result["windows"]:
        for field in verse_fields:
            val = w.get(field)
            if val is None:
                continue
            flat = [x for sub in val for x in (sub if isinstance(sub, list) else [sub])]
            bad = [x for x in flat if not (isinstance(x, str) and verse_token.match(x))]
            if bad:
                problems.append(f"{w['key']}: non-verse token in {field}: {bad[:3]}")
    return problems


def self_test() -> int:
    """Unit tests for the parser and the window chooser, no data files needed."""
    fails = []

    # 1. chapter-number-as-verse-1
    text = "Header\n\n13 first verse. 2 second. 3 third."
    idx = build_verse_index(
        text, chapter_start=13, verse_start=1, chapter_end=13, verse_end=3
    )
    if idx != ["13:1", "13:2", "13:3"]:
        fails.append(f"chapter-as-v1 parse: {idx}")

    # 2. chapter crossing
    text = "24 a. 25 b. 26 c. 7 d. 2 e."
    idx = build_verse_index(
        text, chapter_start=6, verse_start=24, chapter_end=7, verse_end=2
    )
    if idx != ["6:24", "6:25", "6:26", "7:1", "7:2"]:
        fails.append(f"chapter-crossing parse: {idx}")

    # 3. prose numbers ignored
    text = "15 he paid 300 shekels for it. 16 next verse."
    idx = build_verse_index(
        text, chapter_start=21, verse_start=15, chapter_end=21, verse_end=16
    )
    if idx != ["21:15", "21:16"]:
        fails.append(f"prose-number rejection: {idx}")

    index = [f"1:{i}" for i in range(1, 11)]

    # 4. interior single verse -> 3 candidates, one per answer position
    c = candidate_windows(index, ["1:5"])
    if len(c) != 3 or c[0] != ["1:3", "1:4", "1:5"] or c[-1] != ["1:5", "1:6", "1:7"]:
        fails.append(f"interior candidates: {c}")

    # 5. first verse -> only the forward window
    if candidate_windows(index, ["1:1"]) != [["1:1", "1:2", "1:3"]]:
        fails.append("first-verse candidates")

    # 6. last verse -> only the backward window
    if candidate_windows(index, ["1:10"]) != [["1:8", "1:9", "1:10"]]:
        fails.append("last-verse candidates")

    # 7. span of 2 -> 2 candidates; span of 3 -> 1; span of 4 -> 0
    if len(candidate_windows(index, ["1:5", "1:6"])) != 2:
        fails.append("2-verse span candidates")
    if len(candidate_windows(index, ["1:5", "1:6", "1:7"])) != 1:
        fails.append("3-verse span candidates")
    if candidate_windows(index, ["1:5", "1:6", "1:7", "1:8"]) != []:
        fails.append("4-verse span should be excluded")

    # 8. determinism + uniformity of the seeded chooser
    c = candidate_windows(index, ["1:5"])
    if pick_window(c, key="k", seed=1) != pick_window(c, key="k", seed=1):
        fails.append("chooser not deterministic")
    draws = Counter(
        tuple(pick_window(c, key=f"k{i}", seed=1)) for i in range(3000)
    )
    if len(draws) != 3 or min(draws.values()) < 800:
        fails.append(f"chooser not ~uniform: {draws}")

    for f in fails:
        print(f"FAIL {f}")
    print("self-test:", "PASS" if not fails else f"{len(fails)} FAILURE(S)")
    return 1 if fails else 0


# --------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--qa-root", type=Path, help="path to the qa_generation folder")
    p.add_argument("--qa-file", type=Path, help="single combined QA json (e.g. outputs/tier1_shortened.json); default is one file per passage under outputs/tier1_pipeline/")
    p.add_argument("--spans", type=Path, help="required-span annotation JSON")
    p.add_argument("--out", type=Path, help="output map JSON")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--llm-spans", action="store_true", help="regenerate spans via LLM")
    p.add_argument("--spans-out", type=Path, help="where to write LLM-derived spans")
    p.add_argument("--compare-spans", action="store_true", help="report LLM vs checked-in disagreements")
    p.add_argument(
        "--only-new",
        action="store_true",
        help="with --llm-spans: reuse existing annotations, only judge unseen questions",
    )
    p.add_argument(
        "--report-missing",
        type=Path,
        help="write a fill-in stub for items that have no required-span annotation",
    )
    p.add_argument("--model", default=os.getenv("SPAN_MODEL", "gpt-4.1-mini"))
    p.add_argument("--self-test", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    if not args.qa_root or not args.spans or not args.out:
        print("--qa-root, --spans and --out are required", file=sys.stderr)
        return 2

    spans_doc = json.loads(args.spans.read_text(encoding="utf-8"))
    spans = {k: v for k, v in spans_doc.items() if not k.startswith("_")}
    spans["_meta"] = spans_doc.get("_meta", {})

    if args.llm_spans:
        meta, items_by_passage = load_tier1(args.qa_root, args.qa_file)
        derived: dict[str, Any] = {
            "_meta": {"source": f"llm:{args.model}", "temperature": 0}
        }
        n_skipped = 0
        for pid, row in meta.items():
            ptext = (
                args.qa_root / "fixtures" / "passages" / "tier1" / PASSAGE_FILES[pid]
            ).read_text(encoding="utf-8")
            idx = build_verse_index(
                ptext,
                chapter_start=int(row["chapter_start"]),
                verse_start=int(row["verse_start"]),
                chapter_end=int(row["chapter_end"]),
                verse_end=int(row["verse_end"]),
            )
            for item in items_by_passage[pid]:
                question = item_question(item)
                key = span_key(pid, question)
                if key in derived:
                    continue  # repeated question: one annotation covers it
                existing = spans.get(key, {})
                if args.only_new and existing:
                    derived[key] = existing  # already judged; do not re-spend
                    n_skipped += 1
                    continue
                ref = item.get("reference") or (existing.get("required_span") or [""])[0]
                try:
                    got = llm_required_span(
                        passage_text=ptext,
                        question=question,
                        answer=item_answer(item),
                        reference=ref,
                        model=args.model,
                    )
                    lo, hi = idx.index(got["start"]), idx.index(got["end"])
                    if hi < lo:
                        lo, hi = hi, lo
                    derived[key] = {
                        "required_span": idx[lo : hi + 1],
                        "note": got.get("reason"),
                        "question": question,
                    }
                except Exception as exc:  # keep going; record the failure
                    derived[key] = {**existing, "llm_error": str(exc)}
                print(f"  {key}: {derived[key].get('required_span')}", file=sys.stderr)

        if args.only_new:
            print(f"\nreused {n_skipped} existing annotations", file=sys.stderr)
        if args.spans_out:
            args.spans_out.write_text(
                json.dumps(derived, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        if args.compare_spans:
            shared = sorted(k for k in set(spans) & set(derived) if not k.startswith("_"))
            diff = [
                (k, spans[k]["required_span"], derived[k].get("required_span"))
                for k in shared
                if spans[k]["required_span"] != derived[k].get("required_span")
            ]
            print(f"\nspan disagreements: {len(diff)} of {len(shared)} compared")
            for k, a, b in diff:
                q = (spans[k].get("question") or "")[:60]
                print(f"  {k}: checked-in {a} vs llm {b}   [{q}]")
        spans = derived

    result, needs_annotation = build(
        qa_root=args.qa_root, spans=spans, seed=args.seed, qa_file=args.qa_file
    )
    problems = verify(result, args.qa_root, args.qa_file)
    result["verification"] = {"problems": problems, "clean": not problems}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    c = result["counts"]
    print(f"wrote {args.out}")
    print(f"  windows {c['windows']}, excluded {c['excluded']}")
    print(f"  requires context beyond reference: {c['requires_context_beyond_reference']}")
    print(f"  answer position in window: {c['answer_position_in_window']}")
    print(f"  candidate counts: {c['n_candidate_windows']}")
    print(f"  verification: {'clean' if not problems else problems}")

    if needs_annotation:
        print(f"\n  {len(needs_annotation)} item(s) have NO required-span annotation "
              f"and got no window:")
        for n in needs_annotation[:10]:
            print(f"    {n['key']}  ref={n['reference']}  {n['question'][:60]!r}")
        if len(needs_annotation) > 10:
            print(f"    ... and {len(needs_annotation) - 10} more")
        if args.report_missing:
            stub = {
                "_meta": {
                    "source": "STUB -- required_span values are the UNVERIFIED "
                    "pipeline reference span. Check each against the passage "
                    "(does the gold answer actually live there? is the verse "
                    "syntactically headless?) before merging into the spans file.",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
            for n in needs_annotation:
                stub[n["span_key"]] = {
                    "required_span": n["suggested_required_span"],
                    "question": n["question"],
                    "gold_answer": n["gold_answer"],
                    "reference": n["reference"],
                    "note": n.get("error") or "UNREVIEWED",
                }
            args.report_missing.parent.mkdir(parents=True, exist_ok=True)
            args.report_missing.write_text(
                json.dumps(stub, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"  wrote fill-in stub: {args.report_missing}")
        else:
            print("  (pass --report-missing PATH to emit a fill-in stub)")

    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
