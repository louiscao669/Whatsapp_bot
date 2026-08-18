#!/usr/bin/env python3
"""Export human-pilot responses to ``scores_target_*``-shaped JSON (prereq #5).

Turns the designed-assignment answers (each stamped with an ``experiment_cell_id`` →
chapter + condition) into the same JSON the LLM eval analyzers already read, laid out under
the eval tree so they can be consumed with no code change:

    <eval-root>/outputs/luke{ch}/{subdir}/{defect}/{level}/scores_target_human.json

Condition → (defect, level) mapping mirrors the LLM grid, so e.g. Luke 3 / omission30
lands in ``luke3/human/omission/30%/`` and is picked up by
``report_synthetic_perturbations.py --model-subdir human --score-file scores_target_human.json``
and ``fit_item_sensitivity.py --axis defect --models human``.

Split modes:
  * ``--split-by condition`` (default): one file per (chapter, condition), pooling all
    participants who saw that cell. ``subdir = "human"``. Feeds dose-ordering / perturbation
    report (H-T1/H-T3).
  * ``--split-by participant``: one file per (participant, chapter, condition), ``subdir`` =
    a per-participant slug. Preserves the respondent dimension for ability separability
    (H-T4) — each participant is a "respondent" like an LLM answer-model.

Scoring [CHANGED 2026-08-12 -- now the LLM judge, on the grid's scale]:
  * MCQ  → ``direct_correct`` via ``choice_response_is_correct`` (letter vs key).
  * open → ``llm_score`` = ``correctness_score``, written by the LLM judge in
    ``engagement/outbox.py`` on the 0 / 0.5 / 1 scale; ``llm_label`` from ``is_correct``.

    Previously this was the keyword-match fraction. Because the offline proxy
    benchmarks (omission/mistranslation dose-response, the sᵢ ladders) were
    produced by ``judge_open`` on 0/0.5/1, scoring humans by keyword put the two
    legs on different scales and confounded every human-vs-proxy delta with the
    scorer. Both legs now share one rubric, model and temperature.

    Rows still awaiting the judge export ``llm_score = None`` and are counted in
    ``open_unscored``; drain the outbox before treating an export as complete.
The scored answer is the participant's text, or the Whisper ``transcript_text`` for voice.

Audio: the transcript is exported as the answer. Raw participant audio is access-tiered, so
NO ``media_url`` is written. ``--include-audio-ref`` adds only an opaque ``audio_ref``
(``media_id``, the provider's id — not a storage locator) + the platform's authenticated
``audio_proxy_path`` (``/api/v1/media/participant-response/<response_id>``). That route is
admin/expert-only, tier-checked and access-logged — NOT a public URL and not fetchable
without an admin session. For bulk audio pulls use ``audio_export_service`` (ZIP) instead.

Usage (from repo root; needs DATABASE_URL or .env):
  python scripts/export_pilot_responses.py --dry-run
  python scripts/export_pilot_responses.py --split-by participant --require-reviewed
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _bootstrap import use_message_bot  # noqa: E402

use_message_bot()

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from eten_shared.database import get_session_factory  # noqa: E402
from eten_shared.mcq import choice_response_is_correct, is_choice_scored_item  # noqa: E402
from eten_shared.models import (  # noqa: E402
    Assignment,
    AssignmentStatus,
    ExperimentPlanCell,
    Participant,
    ParticipantResponse,
    QAItem,
)

# condition key (experiment_passages.condition / plan cell) -> (defect dir, level dir|None)
# [CHANGED 2026-07-27b] Two matched adequacy ladders; keys MUST match
# build_experiment_plan.SLOTS / pilot_import.CONDITIONS. "clean" maps to omission/0%, which is
# the shared 0% dose for BOTH families — the mistranslation ladder re-uses it as its anchor
# (there is no mistranslation/0% cell at window=3). Retired keys are kept as aliases so a
# response collected under the old slate still exports instead of being silently dropped.
CONDITION_TO_EVAL = {
    "clean": ("omission", "0%"),
    "omission15": ("omission", "15%"),
    "omission30": ("omission", "30%"),
    "mistranslation15": ("mistranslation", "15%"),
    "mistranslation30": ("mistranslation", "30%"),
    "grammar30": ("grammar", "30%"),
    "wbw": ("google_word_by_word", None),
    # --- retired 07-27b, accepted for backwards compatibility ---
    "omission10": ("omission", "10%"),
    "omission20": ("omission", "20%"),
    "mistranslation20": ("mistranslation", "20%"),
}
REVIEWED_STATES = {"auto", "reviewed"}


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_") or "unknown"


def _answer_text(resp: dict) -> str:
    return (resp.get("response_text") or resp.get("transcript_text")
            or resp.get("normalized_text") or "")


def _item_payload(rec: dict, index: int, include_audio_ref: bool) -> dict:
    qtype = rec["question_type"] or "open"
    answer = _answer_text(rec)
    item = {
        "item_index": index,
        "id": rec["qa_item_id"],
        "passage_id": rec["passage_id"],
        "passage_reference": rec.get("passage_reference"),
        "q_type": qtype,
        "question": rec.get("question_text"),
        "standard_answer": rec.get("expected_answer"),
        "generated_answer": answer,
        "respondent": rec.get("participant_slug"),
        "response_modality": rec.get("response_type"),
        "review_status": rec.get("review_status"),
        "generation_error": None,
    }
    meta = rec.get("scoring_metadata") or {}
    if qtype == "mcq":
        # [CHANGED 2026-08-12] An MCQ reply that never resolved to a letter is
        # UNSCORED, not wrong. Previously choice_response_is_correct returned
        # False for unparseable replies, so "I think the second one" and a
        # genuinely wrong answer were indistinguishable in the export.
        if rec.get("is_correct") == "pending" or meta.get("status") in {
            "unresolved", "unusable_reply", "queued", "scorer_disabled"
        }:
            item["direct_correct"] = None
            item["llm_score"] = None
            item["llm_label"] = "pending"
        else:
            item["direct_correct"] = bool(rec.get("mcq_correct"))
            item["llm_score"] = 1.0 if rec.get("mcq_correct") else 0.0
            item["llm_label"] = "correct" if rec.get("mcq_correct") else "incorrect"
        item["scoring_method"] = meta.get("method") or "exact_letter"
        item["resolved_letter"] = meta.get("resolved_letter")
    else:
        score = rec.get("correctness_score")
        item["direct_correct"] = None
        item["llm_score"] = float(score) if score is not None else None
        item["llm_label"] = rec.get("is_correct")
        # Provenance so a mixed export cannot be read as uniformly judged: rows
        # scored before 2026-08-12 carry the retired keyword fraction, which is
        # NOT on the 0/0.5/1 scale and must not be pooled with judged rows.
        item["scoring_method"] = meta.get("method")
        item["scoring_scale"] = meta.get("scale")
        item["judge_rationale"] = meta.get("rationale")
    if include_audio_ref and rec.get("response_type") == "audio":
        # Opaque provider media id (Meta/Telegram) + the platform's authenticated proxy
        # route (admin/expert only, tier-checked, access-logged). NOT a public URL and
        # NOT directly fetchable without an admin session. Add ?download=1 to download.
        item["audio_ref"] = rec.get("media_id")
        item["audio_proxy_path"] = f"/api/v1/media/participant-response/{rec.get('response_id')}"
    return item


def _summary(items: list) -> dict:
    mcq = [it for it in items if it["q_type"] == "mcq"]
    opn = [it for it in items if it["q_type"] != "mcq"]
    open_scored = [it["llm_score"] for it in opn if it.get("llm_score") is not None]
    # Open rows the judge has not reached yet (outbox not drained) or that an
    # expert still owes a verdict on. A nonzero count means this export is
    # partial, not that those answers were wrong.
    open_unscored = [it for it in opn if it.get("llm_score") is None]
    # Any open row not scored on the 0/0.5/1 scale -- e.g. legacy keyword rows.
    off_scale = [
        it for it in opn
        if it.get("llm_score") is not None and it.get("scoring_scale") not in (None, "0/0.5/1")
    ]
    legacy_keyword = [
        it for it in opn
        if it.get("llm_score") is not None and it.get("scoring_method") is None
    ]
    # MCQ rows whose reply never resolved to a letter. Excluded from
    # mcq_scored_count so accuracy denominators count only answered items --
    # an unresolved reply is missing data, not a wrong answer.
    mcq_scored = [it for it in mcq if it.get("direct_correct") is not None]
    mcq_unscored = [it for it in mcq if it.get("direct_correct") is None]
    mcq_llm_resolved = [
        it for it in mcq if it.get("scoring_method") == "llm_choice_resolution"
    ]
    return {
        "total": len(items),
        "mcq_count": len(mcq),
        "mcq_correct": sum(1 for it in mcq if it.get("direct_correct")),
        "mcq_scored_count": len(mcq_scored),
        "mcq_unscored": len(mcq_unscored),
        # How many MCQ replies needed the LLM fallback. A high rate is a signal
        # about instructions/delivery, not just a scoring detail -- worth
        # watching during the dry run.
        "mcq_llm_resolved": len(mcq_llm_resolved),
        "mcq_accuracy": (
            sum(1 for it in mcq_scored if it.get("direct_correct")) / len(mcq_scored)
            if mcq_scored else None
        ),
        "open_count": len(opn),
        "open_llm_score_mean": (sum(open_scored) / len(open_scored)) if open_scored else None,
        "open_scored_count": len(open_scored),
        "open_unscored": len(open_unscored),
        "open_off_scale": len(off_scale),
        "open_legacy_unjudged": len(legacy_keyword),
        "open_scale": "0/0.5/1",
        "answer_confidence_mean": None,
        "insufficient_information_rate": None,
        "evidence_supported_rate": None,
        "generation_errors": 0,
        "respondents": sorted({it.get("respondent") for it in items if it.get("respondent")}),
        "source": "human_pilot",
    }


def assemble(records: list, split_by: str, subdir: str, include_audio_ref: bool) -> dict:
    """records -> {relative_path: payload}. Pure (no DB), so it is unit-testable."""
    groups = defaultdict(list)
    for rec in records:
        if split_by == "participant":
            key = (rec["passage_id"], rec["condition"], rec["participant_slug"])
        else:
            key = (rec["passage_id"], rec["condition"])
        groups[key].append(rec)

    out = {}
    for key, recs in groups.items():
        passage_id, condition = key[0], key[1]
        if condition not in CONDITION_TO_EVAL:
            continue
        defect, level = CONDITION_TO_EVAL[condition]
        model_dir = key[2] if split_by == "participant" else subdir
        # deterministic item order: qa_item id then respondent (stable re-exports)
        recs = sorted(recs, key=lambda r: (str(r["qa_item_id"]), str(r.get("participant_slug"))))
        items = [_item_payload(r, i + 1, include_audio_ref) for i, r in enumerate(recs)]
        if str(passage_id).startswith("t1_"):
            parts = ["outputs", "tier1", str(passage_id), model_dir, defect]
        else:
            parts = ["outputs", str(passage_id), model_dir, defect]
        if level is not None:
            parts.append(level)
        rel = "/".join(parts) + "/scores_target_human.json"
        out[rel] = {"summary": _summary(items), "items": items,
                    "passage_id": passage_id, "condition": condition,
                    "defect": defect, "level": level}
    return out


def fetch_records(db: Session, require_reviewed: bool) -> list:
    """One row per completed experiment assignment: its latest response + cell + item."""
    stmt = (
        select(Assignment, ExperimentPlanCell, QAItem, Participant)
        .join(ExperimentPlanCell, Assignment.experiment_cell_id == ExperimentPlanCell.id)
        .join(QAItem, Assignment.qa_item_id == QAItem.id)
        .join(Participant, Assignment.participant_id == Participant.id)
        .where(
            Assignment.experiment_cell_id.is_not(None),
            Assignment.status == AssignmentStatus.COMPLETED.value,
        )
    )
    records = []
    for assignment, cell, qa_item, participant in db.execute(stmt).all():
        resp = db.scalars(
            select(ParticipantResponse)
            .where(ParticipantResponse.assignment_id == assignment.id)
            .order_by(ParticipantResponse.received_at.desc())
        ).first()
        if resp is None:
            continue
        if require_reviewed and (resp.review_status not in REVIEWED_STATES):
            continue
        response_text = resp.response_text or ""
        mcq_correct = None
        if is_choice_scored_item(qa_item):
            mcq_correct = choice_response_is_correct(
                qa_item, response_text or (resp.transcript_text or ""))
        records.append({
            "chapter": cell.chapter, "condition": cell.condition,
            "participant_slug": _slug(participant.display_name or participant.id),
            "qa_item_id": qa_item.id, "passage_id": qa_item.passage_id,
            "passage_reference": qa_item.passage_reference,
            "question_type": qa_item.question_type, "question_text": qa_item.question_text,
            "expected_answer": qa_item.expected_answer,
            "response_id": resp.id, "response_type": resp.response_type,
            "response_text": resp.response_text, "transcript_text": resp.transcript_text,
            "normalized_text": resp.normalized_text,
            "correctness_score": resp.correctness_score, "is_correct": resp.is_correct,
            "review_status": resp.review_status,
            "scoring_metadata": resp.scoring_metadata,
            "backtranslated_text": resp.backtranslated_text,
            "media_id": resp.media_id, "mcq_correct": mcq_correct,
        })
    return records


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-root", type=Path, default=REPO_ROOT / "evaluation",
                    help="write under <eval-root>/outputs/luke*/...")
    ap.add_argument("--split-by", choices=["condition", "participant"], default="condition")
    ap.add_argument("--subdir", default="human", help="model-subdir for --split-by condition")
    ap.add_argument("--require-reviewed", action="store_true",
                    help="only export responses whose review_status is auto/reviewed")
    ap.add_argument("--include-audio-ref", action="store_true",
                    help="add opaque audio_ref (media_id) + authenticated proxy path for audio "
                         "answers (NO public/Supabase URL)")
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from app.config import load_configurations  # noqa: E402
    from flask import Flask

    app = Flask(__name__)
    load_configurations(app)
    database_url = args.database_url or app.config.get("DATABASE_URL")
    if not database_url:
        sys.exit("No DATABASE_URL (set it in the environment or .env).")
    factory = get_session_factory(database_url)

    with factory() as db:
        records = fetch_records(db, args.require_reviewed)
    payloads = assemble(records, args.split_by, args.subdir, args.include_audio_ref)

    print(f"Collected {len(records)} responses -> {len(payloads)} score files "
          f"(split-by={args.split_by}{', reviewed-only' if args.require_reviewed else ''}).")
    for rel in sorted(payloads):
        s = payloads[rel]["summary"]
        open_mean = s["open_llm_score_mean"]
        print(f"  {rel}: {s['total']} items ({s['mcq_correct']}/{s['mcq_count']} mcq, "
              f"open mean {open_mean:.3f})" if open_mean is not None else
              f"  {rel}: {s['total']} items ({s['mcq_correct']}/{s['mcq_count']} mcq, no open)")

    if args.dry_run:
        print("\n[dry-run] no files written.")
        return
    for rel, payload in payloads.items():
        path = args.eval_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload.pop("passage_id", None); payload.pop("condition", None)
        payload.pop("defect", None); payload.pop("level", None)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {len(payloads)} files under {args.eval_root / 'outputs'}.")


if __name__ == "__main__":
    main()
