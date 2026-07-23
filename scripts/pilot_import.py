#!/usr/bin/env python3
"""Import the human-pilot QA and the 56 variant passages into the platform DB.

Two things get uploaded:

  * QA  -> one QAItem per (chapter, question), passage_id = "luke{ch}".
           question_type is CHAPTER-LEVEL: chosen once per chapter by a ~75%
           MCQ / 25% open quota policy (see choose_question_types). Every item
           in the pipeline carries both an open and an mcq form, so this is a
           selection, not a generation step -- it overrides the pipeline's
           auto_decision routing (which is ~all-open and wrong for the pilot).

  * Passage -> one ExperimentPassage per (chapter, condition). The QA is shared
           across a chapter's 7 conditions (the qa_target file is byte-identical
           across variants), so only the passage varies per cell.

The Chinese (decanonicalized) QA target file is identical across a chapter's
variants, so it is read once per chapter from the clean (omission/0%) dir.

Idempotent: re-running skips existing QA items and refreshes existing passages.

Usage:
  # dry run -- no DB, prints the plan + quota per chapter
  python scripts/pilot_import.py --eval-root /path/to/eten-whatsapp-bot/evaluation --dry-run

  # real import -- needs DATABASE_URL in the environment (or .env on the host)
  python scripts/pilot_import.py --eval-root /path/to/eten-whatsapp-bot/evaluation

Note: this uploads QA + passages only. Per-participant plan cells
(experiment_plan_cells) are written separately by the Latin-square plan builder.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from _bootstrap import use_platform

use_platform()

from eten_shared.models import ExperimentPassage, ExperimentPassageVerse, QAItem  # noqa: E402
from app.services.passage_import_service import parse_numbered_verses  # noqa: E402

# (condition key, relative dir under the answer-model folder, human-readable name)
CONDITIONS = [
    ("clean", "omission/0%", "Clean anchor"),
    ("omission10", "omission/10%", "Omission 10%"),
    ("omission20", "omission/20%", "Omission 20%"),
    ("omission30", "omission/30%", "Omission 30%"),
    ("mistranslation20", "mistranslation/20%", "Mistranslation 20%"),
    ("grammar30", "grammar/30%", "Grammar 30%"),
    ("wbw", "google_word_by_word", "Word-by-word (Google)"),
]
CHAPTERS = range(1, 9)
ANSWER_MODELS = ["1.7b", "1.5b", "llama 1b", "llama 3b"]  # search order; target files identical
LANGUAGE = "zh"
MCQ_FRACTION = 0.75


# ---------------------------------------------------------------- data loading

def _variant_dir(eval_root: Path, chapter: int, rel: str):
    for model in ANSWER_MODELS:
        d = eval_root / "outputs" / f"luke{chapter}" / model / rel
        if d.exists():
            return d
    return None


# Prefer the pseudonymized (natural-name) files produced by
# apply_pseudonym_remap.py; fall back to the raw decanonicalized (token) files.
_warned = set()

def _pick(d: Path, pseudo: str, decanon: str) -> Path:
    if (d / pseudo).exists():
        return d / pseudo
    if decanon not in _warned:
        print(f"  [warn] {pseudo} not found -> using {decanon} (token names). "
              f"Run apply_pseudonym_remap.py for the natural-name version.")
        _warned.add(decanon)
    return d / decanon


def _base_id(passage_id: str) -> str:
    """'uw-174365-open' / 'uw-174365-mcq' -> 'uw-174365'."""
    for suffix in ("-open", "-mcq"):
        if passage_id.endswith(suffix):
            return passage_id[: -len(suffix)]
    return passage_id


def load_chapter_qa(eval_root: Path, chapter: int) -> dict:
    """{base_id: {'open': rec, 'mcq': rec}} for a chapter (from the clean dir)."""
    d = _variant_dir(eval_root, chapter, "omission/0%")
    if d is None:
        raise FileNotFoundError(f"no clean-variant dir for Luke {chapter}")
    recs = json.loads(_pick(d, "qa_target_pseudonymized.json",
                            "qa_target_decanonicalized.json").read_text(encoding="utf-8"))
    by_id: dict = {}
    for r in recs:
        bid = _base_id(r["passage_id"])
        slot = "open" if r.get("q_type") == "open" else "mcq"
        by_id.setdefault(bid, {})[slot] = r
    return by_id


def load_passage(eval_root: Path, chapter: int, rel: str):
    d = _variant_dir(eval_root, chapter, rel)
    if d is None:
        return None, None
    text = _pick(d, "passage_target_pseudonymized.txt",
                 "passage_target_decanonicalized.txt").read_text(encoding="utf-8").strip()
    # first record's reference gives a human-readable chapter label
    ref = None
    qa = _pick(d, "qa_target_pseudonymized.json", "qa_target_decanonicalized.json")
    if qa.exists():
        recs = json.loads(qa.read_text(encoding="utf-8"))
        if recs:
            ref = recs[0].get("passage_reference")
    return text, ref


# ------------------------------------------------- chapter-level type selection

def _open_suitability_key(entry: dict, seed: int):
    """Lower = better OPEN candidate: short, keyword-matchable answer."""
    o = entry.get("open") or {}
    ans = str(o.get("A") or "")
    length = len(ans.split()) or len(ans)
    n_kw = len(o.get("required_keywords") or [])
    tiebreak = int(hashlib.md5(f"{seed}:{o.get('passage_id')}".encode()).hexdigest(), 16)
    return (length, -n_kw, tiebreak)


def choose_question_types(chapter_qa: dict, mcq_fraction: float = MCQ_FRACTION, seed: int = 2026) -> dict:
    """Assign each item 'open' or 'mcq' once for the whole chapter, targeting
    ~mcq_fraction MCQ. Keeps the best open-shaped items (short, keyword-matchable)
    as open; guarantees at least one open and one mcq per chapter."""
    ids = list(chapter_qa)
    n = len(ids)
    k_open = round(n * (1 - mcq_fraction))
    k_open = max(1, min(k_open, n - 1))
    ranked = sorted(ids, key=lambda bid: _open_suitability_key(chapter_qa[bid], seed))
    open_ids = set(ranked[:k_open])
    return {bid: ("open" if bid in open_ids else "mcq") for bid in ids}


# --------------------------------------------------------------- row builders

def build_qa_item(chapter: int, entry: dict, qtype: str) -> QAItem:
    rec = entry.get(qtype) or entry.get("open") or entry.get("mcq") or {}
    ref = rec.get("passage_reference")
    if qtype == "open":
        o = entry["open"]
        return QAItem(
            passage_id=f"luke{chapter}",
            passage_reference=ref,
            question_text=o["Q"],
            question_type="open",
            expected_answer=str(o.get("A") or ""),
            required_keywords=list(o.get("required_keywords") or []),
            optional_keywords=list(o.get("optional_keywords") or []),
            mcq_choices=[],
        )
    m = entry["mcq"]
    opts = m.get("A") or {}
    choices = [opts.get(k, "") for k in ("A", "B", "C", "D")]
    correct = (m.get("correct") or "A").strip()[:1]
    return QAItem(
        passage_id=f"luke{chapter}",
        passage_reference=ref,
        question_text=m["Q"],
        question_type="mcq",
        mcq_choices=choices,
        mcq_correct_choice=correct,
        expected_answer=opts.get(correct, ""),
        required_keywords=list(m.get("required_keywords") or []),
        optional_keywords=list(m.get("optional_keywords") or []),
    )


# ------------------------------------------------------------------- planning

def build_plan(eval_root: Path, mcq_fraction: float, seed: int):
    """Return (qa_rows, passage_rows, summary) without touching the DB."""
    qa_rows, passage_rows, summary = [], [], []
    for ch in CHAPTERS:
        chapter_qa = load_chapter_qa(eval_root, ch)
        types = choose_question_types(chapter_qa, mcq_fraction, seed)
        n_mcq = n_open = 0
        for bid, entry in chapter_qa.items():
            qtype = types[bid]
            if qtype not in entry:  # defensive: item missing its chosen form
                qtype = "open" if "open" in entry else "mcq"
            qa_rows.append(build_qa_item(ch, entry, qtype))
            n_mcq += qtype == "mcq"
            n_open += qtype == "open"
        pcount = 0
        for cond, rel, name in CONDITIONS:
            text, ref = load_passage(eval_root, ch, rel)
            if text is None:
                summary.append(f"  ! Luke {ch} {cond}: MISSING passage")
                continue
            passage_rows.append(dict(chapter=ch, condition=cond, name=name, language=LANGUAGE,
                                     passage_reference=ref, passage_text=text))
            pcount += 1
        summary.append(f"  Luke {ch}: {len(types):2d} QA ({n_mcq} mcq / {n_open} open), {pcount} passages")
    return qa_rows, passage_rows, summary


# ---------------------------------------------------------------------- upload

def upload(database_url, qa_rows, passage_rows):
    from sqlalchemy import delete, select

    from eten_shared.database import get_session_factory

    factory = get_session_factory(database_url)
    created = {
        "qa": 0,
        "qa_skip": 0,
        "passage": 0,
        "passage_skip": 0,
        "experiment_verse": 0,
        "passage_error": None,
    }

    # QA items and passages are committed in SEPARATE transactions so a passage
    # failure (e.g. experiment_passages table/column missing) surfaces clearly
    # and does not silently roll back the QA import.
    with factory() as db:
        for item in qa_rows:
            exists = db.scalar(
                select(QAItem).where(
                    QAItem.passage_id == item.passage_id,
                    QAItem.question_text == item.question_text,
                )
            )
            if exists:
                created["qa_skip"] += 1
                continue
            db.add(item)
            created["qa"] += 1
        db.commit()

    try:
        with factory() as db:
            for p in passage_rows:
                exists = db.scalar(
                    select(ExperimentPassage).where(
                        ExperimentPassage.chapter == p["chapter"],
                        ExperimentPassage.condition == p["condition"],
                        ExperimentPassage.language == p["language"],
                    )
                )
                if exists:
                    exists.name = p["name"]
                    exists.passage_reference = p["passage_reference"]
                    exists.passage_text = p["passage_text"]
                    created["passage_skip"] += 1
                    experiment_passage = exists
                else:
                    experiment_passage = ExperimentPassage(**p)
                    db.add(experiment_passage)
                    db.flush()
                    created["passage"] += 1

                parsed_verses = parse_numbered_verses(
                    p["passage_text"], allow_duplicate_numbers=True
                )
                db.execute(
                    delete(ExperimentPassageVerse).where(
                        ExperimentPassageVerse.experiment_passage_id
                        == experiment_passage.id
                    )
                )
                db.flush()
                db.add_all(
                    [
                        ExperimentPassageVerse(
                            experiment_passage_id=experiment_passage.id,
                            verse_number=verse.number,
                            position=position,
                            text=verse.text,
                        )
                        for position, verse in enumerate(parsed_verses, start=1)
                    ]
                )
                created["experiment_verse"] += len(parsed_verses)
            db.commit()
    except Exception as exc:  # noqa: BLE001 - surface the real cause to the user
        created["passage"] = 0
        created["passage_error"] = f"{type(exc).__name__}: {exc}"

    return created


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-root", required=True, type=Path,
                    help="path to eten-whatsapp-bot/evaluation")
    ap.add_argument("--mcq-fraction", type=float, default=MCQ_FRACTION)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    ap.add_argument("--dry-run", action="store_true", help="build + print the plan, no DB writes")
    args = ap.parse_args()

    qa_rows, passage_rows, summary = build_plan(args.eval_root, args.mcq_fraction, args.seed)

    print("Pilot import plan")
    print("\n".join(summary))
    total_mcq = sum(1 for r in qa_rows if r.question_type == "mcq")
    print(f"\nTOTAL: {len(qa_rows)} QA items "
          f"({total_mcq} mcq / {len(qa_rows) - total_mcq} open, "
          f"{total_mcq / max(len(qa_rows),1):.0%} mcq), {len(passage_rows)} passages")

    if args.dry_run:
        print("\n[dry-run] no database writes.")
        return

    result = upload(args.database_url, qa_rows, passage_rows)
    print(f"\nUploaded: {result['qa']} QA items ({result['qa_skip']} already present), "
          f"{result['passage']} passages ({result['passage_skip']} already present).")
    if result.get("passage_error"):
        print(f"\n*** PASSAGE IMPORT FAILED: {result['passage_error']}\n"
              f"    Likely the experiment_passages table or its 'name' column is missing.\n"
              f"    Re-run supabase/migrations/experiment_plan_cells.sql, then re-run this import.")
    print(f"Experiment passages contain {result['experiment_verse']} verse rows.")


if __name__ == "__main__":
    sys.exit(main())
