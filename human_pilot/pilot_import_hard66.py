#!/usr/bin/env python3
"""Import the hard-66 ("strong-66", ``tier1_strong``) question set as a SECOND pilot set.

It lives next to gold72 in the same database, so one participant can be served gold72
and another hard66:

  * passages / windows / QA are imported under ``hard66/<source id>`` passage ids
    (``hard66/t1_judg9``), so nothing collides with gold72's rows for the same passage;
  * windows use groups 101..108 (``eten_shared.experiment_plan.QA_SETS["hard66"]``) and
    sequence indexes from 10000, and a plan built with ``--qa-set hard66`` points its cells
    at those groups. The selector already matches ``ExperimentWindow.group_index ==
    cell.chapter``, so no delivery code changes.

Source data (both must exist; the outputs live only on the Mac):

  * condition variants: ``<eval-root>/outputs/tier1_strong/<passage>/{omission,
    mistranslation}/{0,15,30}%``, ``grammar/30%``, ``google_word_by_word``;
  * question windows:   ``<eval-root>/datasets/pseudonymized/qa/tier1_strong/*.json``
    (each item's own ``window_verses`` -- the 2-5 verses it was written for).

Differences from the gold72 arm you should know before comparing the two:
  * hard66 is the PSEUDONYMIZED corpus with 4-option MCQs; the current gold72 import is
    the unblinded (canonical-name) 5-option corpus. Names and option count differ.
  * the audit (STRONG66_ITEM_AUDIT_2026-09-10) flags 27/66 items. ``--exclude-flagged``
    drops them, except the 5 WINDOW items, which were broken only by whole-passage
    context and are fine when delivered in their own window (as the pilot does).

Usage (from the repo root, on the Mac):
  python human_pilot/pilot_import_hard66.py --dry-run
  python human_pilot/pilot_import_hard66.py                       # write to DATABASE_URL
  python human_pilot/pilot_import_hard66.py --exclude-flagged "…/STRONG66_ITEM_AUDIT_2026-09-10.csv"

Then create a participant on hard66, either in the admin ("Create test participant",
question set = hard66) or:
  python human_pilot/build_experiment_plan.py --participant-ids <id> --qa-set hard66
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "human_pilot"))
from _bootstrap import use_platform  # noqa: E402

use_platform()

import pilot_import as pi  # noqa: E402
from eten_shared.experiment_plan import GROUPS, QA_SETS  # noqa: E402

QA_SET = "hard66"
OUTPUTS_ROOT = "tier1_strong"
QA_DIR = Path("datasets") / "pseudonymized" / "qa" / "tier1_strong"
PREFIX = QA_SETS[QA_SET]["passage_prefix"]            # "hard66/"
GROUP_OFFSET = QA_SETS[QA_SET]["group_offset"]        # 100
SEQUENCE_OFFSET = 10000                               # windows.sequence_index is globally unique
ID_PREFIX = "hard66:"                                 # QAItem.id namespace (String(36))
KEEP_FLAGS = {"", "WINDOW"}                           # audit flags that --exclude-flagged keeps


def load_items(eval_root: Path):
    """The 66 source items with their window_verses, in file order."""
    qa_dir = eval_root / QA_DIR
    files = sorted(qa_dir.glob("*_all_formats.json"))
    if not files:
        raise FileNotFoundError(f"no hard-66 QA files in {qa_dir}")
    items = []
    for path in files:
        items.extend(json.loads(path.read_text(encoding="utf-8")))
    return items


def load_flagged(path: Path) -> set:
    with path.open(encoding="utf-8", newline="") as fh:
        return {
            f"{row['passage']}:{row['id']}"
            for row in csv.DictReader(fh)
            if (row.get("flag") or "").strip() not in KEEP_FLAGS
        }


def load_variant(eval_root: Path, source_id: str, rel: str, notes: list):
    """A tier1_strong variant passage, repairing a leaked name placeholder when safe.

    One cell (t1_acts20 mistranslation/30%) carries ``人物甲`` where every other cell
    has the pseudonym. The same cell in ``tier1_bsb`` (same base translation, same
    seed) has the name. When the two texts are identical apart from the placeholder
    span(s), the tier1_bsb text is used; otherwise the placeholder error stands.
    """
    try:
        return pi.load_tier1_passage(eval_root, source_id, rel)
    except ValueError as exc:
        if "placeholder" not in str(exc):
            raise
        directory = pi._tier1_variant_dir(eval_root, source_id, rel)
        broken = (directory / "passage_target_decanonicalized.txt").read_text(encoding="utf-8").strip()
        saved_root, pi.TIER1_ROOT = pi.TIER1_ROOT, "tier1_bsb"
        try:
            reference = pi.load_tier1_passage(eval_root, source_id, rel)
        finally:
            pi.TIER1_ROOT = saved_root
        pattern = "".join(
            "(.{1,12}?)" if pi._UNRESOLVED_STYLE_PLACEHOLDER.fullmatch(part) else re.escape(part)
            for part in re.split(f"({pi._UNRESOLVED_STYLE_PLACEHOLDER.pattern})", broken)
            if part
        )
        if reference and re.fullmatch(pattern, reference, flags=re.S | re.I):
            notes.append(f"  ~ {source_id} {rel}: leaked name placeholder repaired from "
                         "the identical tier1_bsb cell")
            return reference
        raise


def window_labels(item, clean_labels):
    """Chapter-qualified labels of the item's window that exist in the clean passage.

    ``window_verses`` are verse numbers in the chapter of ``reference``. A verse the
    translation merged into its neighbour (t1_judg17_18 17:1-2) has no label of its
    own; it is dropped (the neighbour carries its text) and the window is topped up
    with the following verse(s) so it keeps its width -- a one-verse window would
    vanish entirely in an omission variant that deletes that verse.
    """
    chapter = str(item["reference"]).split(":")[0]
    wanted = [f"{chapter}:{verse}" for verse in item["window_verses"]]
    present = [label for label in wanted if label in clean_labels]
    if present and len(present) < len(wanted):
        position = clean_labels.index(present[-1]) + 1
        while len(present) < len(wanted) and position < len(clean_labels):
            present.append(clean_labels[position])
            position += 1
    return wanted, present


def build(eval_root: Path, mcq_fraction: float, seed: int, flagged: set):
    pi.TIER1_ROOT = OUTPUTS_ROOT  # variant loaders read this module global
    metadata = pi.load_tier1_metadata(eval_root)
    meta_by_id = {m["id"]: m for m in metadata}
    order = {m["id"]: i for i, m in enumerate(metadata)}

    clean_labels = {}
    for passage in metadata:
        text = pi.load_tier1_passage(eval_root, passage["id"], "omission/0%")
        if text is None:
            raise FileNotFoundError(f"no clean hard-66 variant for {passage['id']}")
        clean_labels[passage["id"]] = [label for label, _ in pi.parse_tier1_verses(text, passage)]

    notes, rows = [], []
    for item in load_items(eval_root):
        passage_id = item["passage_id"]
        if passage_id not in meta_by_id:
            notes.append(f"  ! {item['content_id']}: passage {passage_id} not in the tier-1 catalog")
            continue
        if item["content_id"] in flagged:
            notes.append(f"  - excluded (audit flag): {item['content_id']}")
            continue
        labels = clean_labels[passage_id]
        wanted, present = window_labels(item, labels)
        if not present:
            notes.append(f"  ! {item['content_id']}: none of {wanted} in the passage -- skipped")
            continue
        if present != wanted:
            notes.append(f"  ~ {item['content_id']}: window {wanted} -> {present} "
                         "(merged verse in the translation)")
        rows.append({"item": item, "labels": present,
                     "ordinals": [labels.index(label) for label in present]})

    # One QA per exact window (the table enforces it); keep the first.
    seen, unique = set(), []
    for row in rows:
        key = (row["item"]["passage_id"], tuple(row["labels"]))
        if key in seen:
            notes.append(f"  - duplicate window, dropped: {row['item']['content_id']}")
            continue
        seen.add(key)
        unique.append(row)
    unique.sort(key=lambda r: (order[r["item"]["passage_id"]], r["ordinals"][0]))

    # Chinese QA (both forms) from each passage's clean cell.
    translated = {pid: pi.load_tier1_qa(eval_root, pid) for pid in meta_by_id}
    entries, planned = {}, []
    for row in unique:
        base_id = f"uw-{row['item']['content_id']}"
        entry = translated[row["item"]["passage_id"]].get(base_id)
        if not entry or "open" not in entry or "mcq" not in entry:
            notes.append(f"  ! {base_id}: no translated open+mcq record -- skipped")
            continue
        entries[base_id] = entry
        planned.append({**row, "base_id": base_id, "entry": entry})

    types = pi.choose_question_types(entries, mcq_fraction, seed)
    grouped = pi.partition_tier1_windows(planned)
    qa_rows, window_rows = [], []
    for row in grouped:
        source_id = row["item"]["passage_id"]
        qtype = types[row["base_id"]]
        qa_item = pi.build_tier1_qa_item(
            PREFIX + source_id, row["entry"], qtype, base_id=ID_PREFIX + row["base_id"]
        )
        qa_item.id = ID_PREFIX + qa_item.id
        if len(qa_item.id) > 36:
            raise ValueError(f"QA id too long for qa_items.id: {qa_item.id}")
        qa_rows.append(qa_item)
        window_rows.append(dict(
            qa_item_id=qa_item.id,
            source_passage_id=PREFIX + source_id,
            content_id=PREFIX + row["item"]["content_id"],
            window_key="|".join(row["labels"]),
            group_index=GROUP_OFFSET + row["group_index"],
            sequence_index=SEQUENCE_OFFSET + row["sequence_index"],
            window_ordinals=row["ordinals"],
            verse_numbers=row["labels"],
        ))

    passage_rows, missing = [], []
    for ordinal, passage in enumerate(metadata, start=1):
        for condition, rel, name in pi.CONDITIONS:
            text = load_variant(eval_root, passage["id"], rel, notes)
            if text is None:
                missing.append((passage["id"], condition, rel))
                continue
            pi.parse_tier1_verses(text, passage)  # fail before any DB write
            passage_rows.append(dict(
                source_passage_id=PREFIX + passage["id"],
                chapter=GROUP_OFFSET + ordinal,
                condition=condition,
                name=f"hard66 · {passage['reference']} — {name}",
                language=pi.LANGUAGE,
                passage_reference=passage["reference"],
                passage_text=text,
                passage_metadata=passage,
            ))

    # Every window must keep at least one verse in every condition: delivery refuses a
    # question with no passage (ExperimentPassageMissingError). hard66 windows are 2-5
    # verses, so omission/30% can delete all of one. Such a window is widened by one
    # neighbouring verse at a time (next, then previous) until every condition keeps
    # some text -- the answer verse stays deleted in the omission cell, as intended.
    labels_by_variant = {
        (row["source_passage_id"], row["condition"]): {
            label for label, _ in pi.parse_tier1_verses(row["passage_text"], row["passage_metadata"])
        }
        for row in passage_rows
    }

    def _empty_conditions(source_id, labels):
        return [
            condition for condition, _rel, _name in pi.CONDITIONS
            if (source_id, condition) in labels_by_variant
            and not set(labels) & labels_by_variant[(source_id, condition)]
        ]

    for window in window_rows:
        source_id = window["source_passage_id"]
        clean = clean_labels[source_id.removeprefix(PREFIX)]
        before = list(window["verse_numbers"])
        labels = list(before)
        while _empty_conditions(source_id, labels):
            last, first = clean.index(labels[-1]), clean.index(labels[0])
            if last + 1 < len(clean):
                labels.append(clean[last + 1])
            elif first > 0:
                labels.insert(0, clean[first - 1])
            else:
                break
        if labels != before:
            notes.append(f"  ~ {window['content_id']}: window {before} -> {labels} "
                         f"(was empty in {', '.join(_empty_conditions(source_id, before))})")
            window.update(
                verse_numbers=labels,
                window_key="|".join(labels),
                window_ordinals=[clean.index(label) for label in labels],
            )

    empty = [
        (window["content_id"], condition)
        for window in window_rows
        for condition, _rel, _name in pi.CONDITIONS
        if (window["source_passage_id"], condition) in labels_by_variant
        and not set(window["verse_numbers"]) & labels_by_variant[(window["source_passage_id"], condition)]
    ]
    for content_id, condition in empty:
        notes.append(f"  ! {content_id}: every window verse is missing in {condition}")

    n_mcq = sum(q.question_type == "mcq" for q in qa_rows)
    per_passage = Counter(w["source_passage_id"] for w in window_rows)
    summary = [f"  {pid}: {n:2d} windows" for pid, n in per_passage.items()]
    summary += [
        "",
        f"  items: {len(load_items(eval_root))} in source, {len(qa_rows)} importable",
        f"  groups: {dict(sorted(Counter(w['group_index'] for w in window_rows).items()))}",
        f"  forms: {n_mcq} mcq / {len(qa_rows) - n_mcq} open",
        f"  passage variants: {len(passage_rows)} ({len(metadata)} passages x "
        f"{len(pi.CONDITIONS)} conditions)",
    ]
    if missing:
        summary.append(f"  MISSING_VARIANTS: {len(missing)} (first: {missing[:3]})")
    if empty:
        summary.append(f"  EMPTY_WINDOWS: {len(empty)} window/condition pairs have no verse")
    return qa_rows, window_rows, passage_rows, summary + ([""] + notes if notes else []), missing + empty


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-root", type=Path, default=REPO_ROOT / "evaluation")
    ap.add_argument("--mcq-fraction", type=float, default=pi.MCQ_FRACTION)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--exclude-flagged", type=Path, default=None,
                    help="STRONG66_ITEM_AUDIT csv; drop items with an audit flag other "
                         "than WINDOW")
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    eval_root = args.eval_root.expanduser().resolve()
    if not (eval_root / "outputs" / OUTPUTS_ROOT).is_dir():
        sys.exit(f"missing {eval_root / 'outputs' / OUTPUTS_ROOT} -- run this on the machine "
                 "that has the tier1_strong outputs (the Mac)")
    flagged = load_flagged(args.exclude_flagged) if args.exclude_flagged else set()

    qa_rows, window_rows, passage_rows, summary, missing = build(
        eval_root, args.mcq_fraction, args.seed, flagged
    )
    print(f"hard-66 pilot import  (outputs/{OUTPUTS_ROOT}, groups "
          f"{GROUP_OFFSET + GROUPS[0]}..{GROUP_OFFSET + GROUPS[-1]}, passage prefix '{PREFIX}')")
    print("\n".join(summary))

    if args.dry_run:
        print("\n[dry-run] no database writes.")
        return
    if missing:
        sys.exit(f"REFUSING TO WRITE: {len(missing)} condition variants are missing.")

    result = pi.upload(args.database_url, qa_rows, window_rows, passage_rows)
    print(f"\nUploaded: {result['qa']} QA items ({result['qa_skip']} already present), "
          f"{result['passage']} passages ({result['passage_skip']} already present), "
          f"{result['window']} windows ({result['window_skip']} refreshed), "
          f"{result['experiment_verse']} verse rows.")
    if result.get("passage_error"):
        sys.exit(f"*** PASSAGE IMPORT FAILED: {result['passage_error']}")


if __name__ == "__main__":
    sys.exit(main())
