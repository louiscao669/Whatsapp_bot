#!/usr/bin/env python3
"""Import the human-pilot QA and the 56 variant passages into the platform DB.

Two things get uploaded:

  * QA  -> QAItems from each chapter's qa_target_pseudonymized.json. By default,
           one form per underlying question is chosen using the pilot's ~75% MCQ /
           25% open policy. ``--question-forms both`` imports both deliverable forms.

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
# [CHANGED 2026-07-27b] Two matched adequacy ladders; see build_experiment_plan.SLOTS and
# HUMAN_PILOT_DESIGN_2026-07-27.md §4. Keys MUST match SLOTS and export CONDITION_TO_EVAL.
CONDITIONS = [
    ("clean", "omission/0%", "Clean anchor"),
    ("omission15", "omission/15%", "Omission 15%"),
    ("omission30", "omission/30%", "Omission 30%"),
    ("mistranslation15", "mistranslation/15%", "Mistranslation 15%"),
    ("mistranslation30", "mistranslation/30%", "Mistranslation 30%"),
    ("grammar30", "grammar/30%", "Grammar 30%"),
    ("wbw", "google_word_by_word", "Word-by-word (Google)"),
]
CHAPTERS = range(1, 9)
ANSWER_MODELS = ["1.7b", "1.5b", "llama 1b", "llama 3b"]  # search order; target files identical
LANGUAGE = "zh"
MCQ_FRACTION = 0.75
# [NEW 2026-07-27b] Item exclusions, mirroring evaluation/scripts/regen_mcq_tier01.py. The
# delivered qa_target_pseudonymized.json files still CONTAIN these records --
# promote_mcq_rewrites.py patches, it never deletes -- so the importer must filter them or the
# retired forms reach participants.
MCQ_REWRITES_FILENAME = "mcq_rewrites.json"   # lives at <eval_root>/mcq_rewrites.json
EXCLUDED_OPEN_STEMS = {"uw-174382"}           # unscoped question; MCQ form is kept


# ---------------------------------------------------------------- data loading

def _variant_dir(eval_root: Path, chapter: int, rel: str):
    for model in ANSWER_MODELS:
        d = eval_root / "outputs" / f"luke{chapter}" / model / rel
        if d.exists():
            return d
    return None


def validate_eval_root(eval_root: Path) -> None:
    """Fail fast with a diagnostic instead of a bare 'no clean-variant dir for Luke 1'.

    That error is almost always a wrong --eval-root (it must point at the *evaluation*
    directory, i.e. the one containing 'outputs/'), not genuinely missing variants."""
    if not eval_root.exists():
        sys.exit(f"--eval-root does not exist: {eval_root}\n"
                 f"  it must point at the 'evaluation' directory, e.g. "
                 f"{Path(__file__).resolve().parents[1] / 'evaluation'}")
    if not (eval_root / "outputs").is_dir():
        hint = ""
        if (eval_root / "evaluation" / "outputs").is_dir():
            hint = f"\n  did you mean: --eval-root {eval_root / 'evaluation'}"
        sys.exit(f"--eval-root has no 'outputs/' subdirectory: {eval_root}{hint}")
    probed = [eval_root / "outputs" / "luke1" / m / "omission/0%" for m in ANSWER_MODELS]
    if not any(p.exists() for p in probed):
        listing = sorted(p.name for p in (eval_root / "outputs").iterdir())[:8]
        sys.exit(
            f"no clean-variant dir (omission/0%) for Luke 1 under {eval_root / 'outputs'}\n"
            f"  probed answer-model dirs: {[str(p) for p in probed]}\n"
            f"  outputs/ contains: {listing}")


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


def allowed_forms(chapter_qa: dict, rewrites: set) -> dict:
    """{base_id: {'open','mcq'}} -- which FORMS of each item may be delivered.

    [NEW 2026-07-27b] Mirrors the exclusions the LLM grid already applies in
    regen_mcq_tier01.py, which the importer previously did not know about:

      * an MCQ form is deliverable only if it has an entry in mcq_rewrites.json.
        The two retired MCQs (build_rewrites_v2.EXCLUDED_IDS) have no rewrite, so their
        ORIGINAL guessable distractors would otherwise be delivered verbatim.
      * the ambiguous open form (EXCLUDED_OPEN_STEMS) is never deliverable; its MCQ form
        is fine, because the options pin the answer.

    An item with no allowed form is dropped entirely.
    """
    out = {}
    for bid, entry in chapter_qa.items():
        forms = set()
        if "mcq" in entry and f"{bid}-mcq" in rewrites:
            forms.add("mcq")
        if "open" in entry and bid not in EXCLUDED_OPEN_STEMS:
            forms.add("open")
        out[bid] = forms
    return out


def choose_question_types(chapter_qa: dict, mcq_fraction: float = MCQ_FRACTION, seed: int = 2026,
                          allowed: dict = None) -> dict:
    """Assign each item 'open' or 'mcq' once for the whole chapter, targeting
    ~mcq_fraction MCQ. Keeps the best open-shaped items (short, keyword-matchable)
    as open; guarantees at least one open and one mcq per chapter.

    ``allowed`` (from allowed_forms) constrains the choice: items with a single allowed
    form are FORCED to it and excluded from the quota, items with none are omitted from
    the result entirely. Without it the old unconstrained behaviour is preserved.
    """
    if allowed is None:
        allowed = {bid: {"open", "mcq"} for bid in chapter_qa}

    forced = {bid: next(iter(f)) for bid, f in allowed.items() if len(f) == 1}
    free = [bid for bid, f in allowed.items() if len(f) == 2]

    # the quota applies to the freely-assignable items, adjusted for what the forced ones
    # already contribute, so a chapter's MCQ fraction stays on target.
    n_total = len(free) + len(forced)
    target_open = round(n_total * (1 - mcq_fraction))
    k_open = target_open - sum(1 for q in forced.values() if q == "open")
    k_open = max(0, min(k_open, len(free)))
    ranked = sorted(free, key=lambda bid: _open_suitability_key(chapter_qa[bid], seed))
    open_ids = set(ranked[:k_open])

    types = dict(forced)
    types.update({bid: ("open" if bid in open_ids else "mcq") for bid in free})
    # guarantee both formats survive in the chapter when the pool allows it
    if types and free:
        if all(q == "mcq" for q in types.values()):
            types[ranked[0]] = "open"
        elif all(q == "open" for q in types.values()):
            types[ranked[-1]] = "mcq"
    return types


# --------------------------------------------------------------- row builders

def build_qa_item(chapter: int, entry: dict, qtype: str, *, form_group_id=None,
                  automatic_form=None) -> QAItem:
    rec = entry.get(qtype) or entry.get("open") or entry.get("mcq") or {}
    ref = rec.get("passage_reference")
    if qtype == "open":
        o = entry["open"]
        return QAItem(
            passage_id=f"luke{chapter}",
            passage_reference=ref,
            question_text=o["Q"],
            question_type="open",
            form_group_id=form_group_id,
            automatic_form=automatic_form,
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
        form_group_id=form_group_id,
        automatic_form=automatic_form,
        mcq_choices=choices,
        mcq_correct_choice=correct,
        expected_answer=opts.get(correct, ""),
        required_keywords=list(m.get("required_keywords") or []),
        optional_keywords=list(m.get("optional_keywords") or []),
    )


# ------------------------------------------------------------------- planning

def load_mcq_rewrites(eval_root: Path) -> set:
    """Ids with a hand-written distractor rewrite. An MCQ without one is retired."""
    path = eval_root / MCQ_REWRITES_FILENAME
    if not path.exists():
        sys.exit(f"missing {path} -- required to tell rewritten MCQs from retired ones.\n"
                 f"  run evaluation/build_rewrites_v2.py first")
    return set(json.loads(path.read_text(encoding="utf-8")))


def build_plan(eval_root: Path, mcq_fraction: float, seed: int, question_forms="mixed"):
    """Return (qa_rows, passage_rows, summary) without touching the DB."""
    rewrites = load_mcq_rewrites(eval_root)
    qa_rows, passage_rows, summary = [], [], []
    dropped = []
    imported_mcq_ids = set()
    for ch in CHAPTERS:
        chapter_qa = load_chapter_qa(eval_root, ch)
        allowed = allowed_forms(chapter_qa, rewrites)
        types = choose_question_types(chapter_qa, mcq_fraction, seed, allowed=allowed)
        n_mcq = n_open = 0
        for bid, entry in chapter_qa.items():
            if question_forms == "mixed":
                selected_forms = [types[bid]] if bid in types else []
            elif question_forms == "both":
                selected_forms = [form for form in ("mcq", "open")
                                  if form in allowed.get(bid, set())]
            else:
                selected_forms = ([question_forms]
                                  if question_forms in allowed.get(bid, set()) else [])

            if not selected_forms:                 # no deliverable requested form
                dropped.append((ch, bid, "no allowed form"))
                continue
            automatic_form = (
                types.get(bid) if question_forms in {"mixed", "both"} else question_forms
            )
            for qtype in selected_forms:
                qa_rows.append(build_qa_item(
                    ch, entry, qtype, form_group_id=bid, automatic_form=automatic_form
                ))
                if qtype == "mcq":
                    imported_mcq_ids.add(f"{bid}-mcq")
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
        summary.append(
            f"  Luke {ch}: {n_mcq + n_open:2d} QA "
            f"({n_mcq} mcq / {n_open} open), {pcount} passages"
        )

    if dropped:
        summary.append("")
        summary.append(f"  dropped {len(dropped)} retired item(s) with no deliverable form:")
        summary.extend(f"    luke{ch} {bid} ({why})" for ch, bid, why in dropped)

    # [NEW 2026-07-27b] Pool-alignment guard: every MCQ actually being imported must carry a
    # rewrite. Without this the retired MCQs slip through as original guessable distractors,
    # and the human item pool silently diverges from the LLM grid's (which H-T7 compares).
    if imported_mcq_ids - rewrites:
        sys.exit("ABORT: MCQ rows without a distractor rewrite would be imported: "
                 + ", ".join(sorted(imported_mcq_ids - rewrites)))
    summary.append("")
    summary.append(f"  pool check: {len(imported_mcq_ids)} MCQ item(s), all rewritten OK")
    return qa_rows, passage_rows, summary


def prune_stale_qa(db, qa_rows):
    """[NEW 2026-07-27b] Delete imported QAItems that the current plan no longer contains
    in that form.

    Needed because the importer skips on (passage_id, question_text) and BOTH forms of an
    item share the same question text -- so an item imported earlier as a retired MCQ is
    skipped, not corrected, by a re-run.

    Deleting a QAItem CASCADEs to assignments and participant responses, so rows with any
    response are reported and kept rather than silently destroying collected data.
    """
    from sqlalchemy import func, select
    from eten_shared.models import Assignment, ParticipantResponse, QAItem

    wanted = {(r.passage_id, r.question_text, r.question_type) for r in qa_rows}
    by_text = {(r.passage_id, r.question_text) for r in qa_rows}
    deleted, blocked = [], []
    for existing in db.scalars(select(QAItem)).all():
        key = (existing.passage_id, existing.question_text)
        if key not in by_text:
            continue                      # not part of the pilot pool at all -- leave alone
        if (existing.passage_id, existing.question_text, existing.question_type) in wanted:
            continue                      # correct form already imported
        n_resp = db.scalar(select(func.count(ParticipantResponse.id))
                           .where(ParticipantResponse.qa_item_id == existing.id)) or 0
        n_assign = db.scalar(select(func.count(Assignment.id))
                             .where(Assignment.qa_item_id == existing.id)) or 0
        if n_resp or n_assign:
            blocked.append((existing.id, existing.passage_id, existing.question_type,
                            n_assign, n_resp))
            continue
        db.delete(existing)
        deleted.append((existing.passage_id, existing.question_type,
                        existing.question_text[:40]))
    return deleted, blocked


# ---------------------------------------------------------------------- upload

def upload(database_url, qa_rows, passage_rows, prune=False):
    from sqlalchemy import delete, select

    from eten_shared.database import get_session_factory

    factory = get_session_factory(database_url)
    created = {
        "qa": 0,
        "qa_skip": 0,
        "qa_pruned": 0,
        "passage": 0,
        "passage_skip": 0,
        "experiment_verse": 0,
        "passage_error": None,
    }

    # QA items and passages are committed in SEPARATE transactions so a passage
    # failure (e.g. experiment_passages table/column missing) surfaces clearly
    # and does not silently roll back the QA import.
    with factory() as db:
        if prune:
            deleted, blocked = prune_stale_qa(db, qa_rows)
            created["qa_pruned"] = len(deleted)
            for pid, qtype, text in deleted:
                print(f"  [prune] deleted stale {qtype.upper():4} {pid}: {text}")
            for iid, pid, qtype, na, nr in blocked:
                print(f"  [prune] KEPT {qtype.upper()} {pid} ({iid}): "
                      f"{na} assignment(s), {nr} response(s) would CASCADE -- delete manually "
                      f"if you are sure")
            db.flush()
        for item in qa_rows:
            exists = db.scalar(
                select(QAItem).where(
                    QAItem.passage_id == item.passage_id,
                    QAItem.question_text == item.question_text,
                    QAItem.question_type == item.question_type,
                )
            )
            if exists:
                exists.form_group_id = item.form_group_id
                exists.automatic_form = item.automatic_form
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
    ap.add_argument(
        "--question-forms",
        choices=("mixed", "both", "mcq", "open"),
        default="mixed",
        help=("forms to import: mixed keeps the existing ~75/25 selection; both imports "
              "both available forms; mcq/open imports only that form (default: mixed)"),
    )
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    ap.add_argument("--dry-run", action="store_true", help="build + print the plan, no DB writes")
    ap.add_argument("--prune-stale-qa", action="store_true",
                    help="delete already-imported QAItems whose form is now retired (an earlier "
                         "import could deliver a retired MCQ with its ORIGINAL distractors). "
                         "The (passage_id, question_text) skip means a plain re-run will NOT "
                         "replace them, because both forms of an item share the same question "
                         "text. Refuses if the row has assignments/responses (FK CASCADE).")
    args = ap.parse_args()

    args.eval_root = args.eval_root.expanduser().resolve()
    validate_eval_root(args.eval_root)
    print(f"eval-root: {args.eval_root}")

    qa_rows, passage_rows, summary = build_plan(
        args.eval_root, args.mcq_fraction, args.seed, args.question_forms
    )

    print("Pilot import plan")
    print("\n".join(summary))
    total_mcq = sum(1 for r in qa_rows if r.question_type == "mcq")
    print(f"\nTOTAL: {len(qa_rows)} QA items "
          f"({total_mcq} mcq / {len(qa_rows) - total_mcq} open, "
          f"{total_mcq / max(len(qa_rows),1):.0%} mcq), {len(passage_rows)} passages")

    if args.dry_run:
        print("\n[dry-run] no database writes.")
        return

    result = upload(args.database_url, qa_rows, passage_rows, prune=args.prune_stale_qa)
    print(f"\nUploaded: {result['qa']} QA items ({result['qa_skip']} already present), "
          f"{result['passage']} passages ({result['passage_skip']} already present).")
    if result.get("passage_error"):
        print(f"\n*** PASSAGE IMPORT FAILED: {result['passage_error']}\n"
              f"    Likely the experiment_passages table or its 'name' column is missing.\n"
              f"    Re-run supabase/migrations/experiment_plan_cells.sql, then re-run this import.")
    print(f"Experiment passages contain {result['experiment_verse']} verse rows.")


if __name__ == "__main__":
    sys.exit(main())
