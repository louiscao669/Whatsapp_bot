#!/usr/bin/env python3
"""Import the hard-66 ("strong-66") question set as a SECOND pilot set, with real names.

It lives next to gold72 in the same database, so one participant can be served gold72
and another hard66:

  * passages / windows / QA are imported under ``hard66/<source id>`` passage ids
    (``hard66/t1_judg9``), so nothing collides with gold72's rows for the same passage;
  * windows use groups 101..108 (``eten_shared.experiment_plan.QA_SETS["hard66"]``) and
    sequence indexes from 10000, and a plan built with ``--qa-set hard66`` points its cells
    at those groups. The selector matches ``ExperimentWindow.group_index == cell.chapter``,
    so no delivery code changes.

Sources (the outputs live only on the Mac):

  * passages: gold72's REAL-NAME condition variants,
    ``<eval-root>/outputs/tier1_bsb_unblinded_5opt_think`` -- the same 10 BSB passages and
    7 conditions the gold72 arm reads (incl. the 2026-09-16 translation fixes). hard66 and
    gold72 therefore read identical text; only the questions differ.
  * questions: ``<eval-root>/datasets/qa/tier1_hard66_canonical/<passage>.json`` -- the
    hard-66 Chinese QA with the pseudonyms swapped back to the real names as spelled in
    the gold72 passages, English fragments translated, and ambiguous distractors
    replaced. Every change is listed per item in ``review_note`` and in
    ``Bible Translation/HARD66_CANONICAL_REVIEW_2026-09-26.csv``. Records carry
    ``status`` (``exclude`` = not imported), ``force_form`` and ``window_start``.

Usage (from the repo root, on the Mac):
  python human_pilot/pilot_import_hard66.py --dry-run
  python human_pilot/pilot_import_hard66.py --replace          # swap out an earlier hard66 import
  python human_pilot/pilot_import_hard66.py --cannot-tell      # add E, as gold72 has

``--replace`` deletes the previous hard66 QA items, windows and passages first (deleting a
QA item cascades to its assignments/responses) and REFUSES if any of those responses
belong to a participant not flagged as test.

Then create a participant on hard66 in the admin ("Create test participant", question
set = hard66) or: python human_pilot/build_experiment_plan.py --participant-ids <id> --qa-set hard66
"""

import argparse
import json
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
PASSAGES_ROOT = "tier1_bsb_unblinded_5opt_think"      # gold72's real-name variants
QA_DIR = Path("datasets") / "qa" / "tier1_hard66_canonical"
PREFIX = QA_SETS[QA_SET]["passage_prefix"]            # "hard66/"
GROUP_OFFSET = QA_SETS[QA_SET]["group_offset"]        # 100
SEQUENCE_OFFSET = 10000                               # windows.sequence_index is globally unique
ID_PREFIX = "hard66:"                                 # QAItem.id namespace (String(36))
CANNOT_TELL = "根据这段文字无法判断"                   # gold72's E option, verbatim


def load_questions(eval_root: Path):
    """{passage_id: {base_id: {'open': rec, 'mcq': rec}}} from the real-name QA files."""
    qa_dir = eval_root / QA_DIR
    files = sorted(qa_dir.glob("t1_*.json"))
    if not files:
        raise FileNotFoundError(f"no real-name hard-66 QA files in {qa_dir}")
    out = {}
    for path in files:
        for record in json.loads(path.read_text(encoding="utf-8")):
            base_id = pi._tier1_base_id(record["passage_id"])
            form = "open" if record["q_type"] == "open" else "mcq"
            out.setdefault(path.stem, {}).setdefault(base_id, {})[form] = record
    return out


def window_labels(record, clean_labels):
    """The item's window as chapter-qualified labels present in the clean passage.

    ``window_verses`` are verse numbers in the chapter of ``reference``;
    ``window_start`` (review override) extends the window back to that label.
    """
    chapter = str(record["reference"]).split(":")[0]
    labels = [f"{chapter}:{verse}" for verse in record["window_verses"]]
    labels = [label for label in labels if label in clean_labels]
    start = record.get("window_start")
    if labels and start in clean_labels and clean_labels.index(start) < clean_labels.index(labels[0]):
        labels = clean_labels[clean_labels.index(start):clean_labels.index(labels[-1]) + 1]
    return labels


def build(eval_root: Path, mcq_fraction: float, seed: int, cannot_tell: bool):
    pi.TIER1_ROOT = PASSAGES_ROOT  # variant loaders read this module global
    metadata = pi.load_tier1_metadata(eval_root)
    order = {m["id"]: i for i, m in enumerate(metadata)}

    passage_rows, missing, clean_labels = [], [], {}
    for ordinal, passage in enumerate(metadata, start=1):
        for condition, rel, name in pi.CONDITIONS:
            text = pi.load_tier1_passage(eval_root, passage["id"], rel)
            if text is None:
                missing.append((passage["id"], condition, rel))
                continue
            verses = pi.parse_tier1_verses(text, passage)  # fail before any DB write
            if condition == "clean":
                clean_labels[passage["id"]] = [label for label, _ in verses]
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

    notes, planned, allowed = [], [], {}
    questions = load_questions(eval_root)
    n_source = sum(len(items) for items in questions.values())
    for source_id, items in questions.items():
        if source_id not in clean_labels:
            notes.append(f"  ! {source_id}: no clean real-name passage -- {len(items)} items skipped")
            continue
        for base_id, entry in items.items():
            record = entry.get("mcq") or entry.get("open")
            if record.get("status") == "exclude":
                notes.append(f"  - excluded by review: {base_id}")
                continue
            labels = window_labels(record, clean_labels[source_id])
            if not labels:
                notes.append(f"  ! {base_id}: window {record['window_verses']} not in passage -- skipped")
                continue
            if cannot_tell and "mcq" in entry:
                entry["mcq"] = {**entry["mcq"], "A": {**entry["mcq"]["A"], "E": CANNOT_TELL}}
            forms = {record["force_form"]} if record.get("force_form") else {"open", "mcq"}
            allowed[base_id] = forms & set(entry)
            planned.append({"source_id": source_id, "base_id": base_id, "entry": entry,
                            "labels": labels,
                            "ordinals": [clean_labels[source_id].index(l) for l in labels]})
    planned.sort(key=lambda r: (order[r["source_id"]], r["ordinals"][0]))

    types = pi.choose_question_types({r["base_id"]: r["entry"] for r in planned},
                                     mcq_fraction, seed, allowed)
    qa_rows, window_rows = [], []
    for row in pi.partition_tier1_windows(planned):
        qa_item = pi.build_tier1_qa_item(
            PREFIX + row["source_id"], row["entry"], types[row["base_id"]],
            base_id=ID_PREFIX + row["base_id"],
        )
        qa_item.id = ID_PREFIX + qa_item.id
        if len(qa_item.id) > 36:
            raise ValueError(f"QA id too long for qa_items.id: {qa_item.id}")
        qa_rows.append(qa_item)
        window_rows.append(dict(
            qa_item_id=qa_item.id,
            source_passage_id=PREFIX + row["source_id"],
            content_id=PREFIX + row["base_id"].removeprefix("uw-"),
            window_key="|".join(row["labels"]),
            group_index=GROUP_OFFSET + row["group_index"],
            sequence_index=SEQUENCE_OFFSET + row["sequence_index"],
            window_ordinals=row["ordinals"],
            verse_numbers=row["labels"],
        ))

    # Every window must keep at least one verse in every condition: delivery refuses a
    # question with no passage (ExperimentPassageMissingError). A window that an omission
    # variant deletes entirely is widened by one neighbouring verse at a time (next, then
    # previous) -- the deleted verse stays deleted, the question just keeps some context.
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
            window.update(verse_numbers=labels, window_key="|".join(labels),
                          window_ordinals=[clean.index(label) for label in labels])
    empty = [
        (window["content_id"], condition)
        for window in window_rows
        for condition in _empty_conditions(window["source_passage_id"], window["verse_numbers"])
    ]

    n_mcq = sum(q.question_type == "mcq" for q in qa_rows)
    per_passage = Counter(w["source_passage_id"] for w in window_rows)
    summary = [f"  {pid}: {n:2d} windows" for pid, n in per_passage.items()]
    summary += [
        "",
        f"  items: {n_source} in source, {len(qa_rows)} importable",
        f"  groups: {dict(sorted(Counter(w['group_index'] for w in window_rows).items()))}",
        f"  forms: {n_mcq} mcq / {len(qa_rows) - n_mcq} open"
        + (" (mcq include E: 根据这段文字无法判断)" if cannot_tell else ""),
        f"  passage variants: {len(passage_rows)} ({len(metadata)} passages x "
        f"{len(pi.CONDITIONS)} conditions, from {PASSAGES_ROOT})",
    ]
    if missing:
        summary.append(f"  MISSING_VARIANTS: {len(missing)} (first: {missing[:3]})")
    if empty:
        summary.append(f"  EMPTY_WINDOWS: {len(empty)} window/condition pairs have no verse")
    return (qa_rows, window_rows, passage_rows,
            summary + ([""] + notes if notes else []), missing + empty)


def replace_previous(database_url):
    """Delete an earlier hard66 import (QA -> cascades; windows; passages)."""
    from sqlalchemy import delete, select

    from eten_shared.database import get_session_factory
    from eten_shared.experiment_plan import is_test_participant
    from eten_shared.models import (
        ExperimentPassage, ExperimentWindow, Participant, ParticipantResponse, QAItem,
    )

    factory = get_session_factory(database_url)
    with factory() as db:
        qa_ids = list(db.scalars(select(QAItem.id).where(QAItem.passage_id.like(f"{PREFIX}%"))))
        owners = set(db.scalars(
            select(ParticipantResponse.participant_id).where(ParticipantResponse.qa_item_id.in_(qa_ids))
        )) if qa_ids else set()
        real = [pid for pid in owners if not is_test_participant(db.get(Participant, pid))]
        if real:
            sys.exit(f"REFUSING --replace: {len(real)} non-test participant(s) answered hard66 "
                     f"questions ({real[:3]}). Their responses would be deleted.")
        db.execute(delete(ExperimentWindow).where(ExperimentWindow.source_passage_id.like(f"{PREFIX}%")))
        for qa_id in qa_ids:  # ORM delete so the cascade reaches assignments/responses
            db.delete(db.get(QAItem, qa_id))
        n_passages = len(list(db.scalars(
            select(ExperimentPassage.id).where(ExperimentPassage.source_passage_id.like(f"{PREFIX}%"))
        )))
        for passage in db.scalars(
            select(ExperimentPassage).where(ExperimentPassage.source_passage_id.like(f"{PREFIX}%"))
        ).all():
            db.delete(passage)
        db.commit()
    print(f"--replace: removed {len(qa_ids)} QA items (+ their test-participant answers) "
          f"and {n_passages} passages of the previous hard66 import")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-root", type=Path, default=REPO_ROOT / "evaluation")
    ap.add_argument("--mcq-fraction", type=float, default=pi.MCQ_FRACTION)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--cannot-tell", action="store_true",
                    help=f"add option E ({CANNOT_TELL}) to every MCQ, as gold72 has")
    ap.add_argument("--replace", action="store_true",
                    help="delete the previous hard66 import first (test-participant answers only)")
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    eval_root = args.eval_root.expanduser().resolve()
    if not (eval_root / "outputs" / PASSAGES_ROOT).is_dir():
        sys.exit(f"missing {eval_root / 'outputs' / PASSAGES_ROOT} -- run this on the machine "
                 "that has the tier-1 outputs (the Mac)")

    qa_rows, window_rows, passage_rows, summary, problems = build(
        eval_root, args.mcq_fraction, args.seed, args.cannot_tell
    )
    print(f"hard-66 pilot import  (real names; passages from {PASSAGES_ROOT}; groups "
          f"{GROUP_OFFSET + GROUPS[0]}..{GROUP_OFFSET + GROUPS[-1]}; prefix '{PREFIX}')")
    print("\n".join(summary))

    if args.dry_run:
        print("\n[dry-run] no database writes.")
        return
    if problems:
        sys.exit(f"REFUSING TO WRITE: {len(problems)} missing variants / empty windows.")
    if args.replace:
        replace_previous(args.database_url)

    result = pi.upload(args.database_url, qa_rows, window_rows, passage_rows)
    print(f"\nUploaded: {result['qa']} QA items ({result['qa_skip']} already present), "
          f"{result['passage']} passages ({result['passage_skip']} already present), "
          f"{result['window']} windows ({result['window_skip']} refreshed), "
          f"{result['experiment_verse']} verse rows.")
    if result["qa_skip"]:
        print("  NOTE: existing QA items are NOT rewritten by a plain re-run -- use --replace "
              "to pick up question text changes.")
    if result.get("passage_error"):
        sys.exit(f"*** PASSAGE IMPORT FAILED: {result['passage_error']}")


if __name__ == "__main__":
    sys.exit(main())
