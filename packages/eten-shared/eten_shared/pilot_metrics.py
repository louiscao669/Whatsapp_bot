"""Human-pilot results: one row per question trial, and the summaries over them.

PostgreSQL is the source of truth and every number here is recomputed from
source records (trials, answer receipts, responses) at query time. Nothing is
cached and no aggregate is ever stored as a mutable participant column, so a
late scoring pass or an expert correction simply changes the next export.

Two rules the definitions turn on:

* **Answered means an accepted answer receipt**, not a scored response. The
  receipt is the immutable intake record; scoring happens afterwards and may
  lag by minutes, so counting scored rows would under-report response volume.
* **Unscored is missing data, never wrong.** Unscored rows are excluded from
  accuracy denominators; an accuracy with a zero denominator is ``None``, not
  ``0.0``.
"""

from typing import Iterable, List, Optional, Sequence

from sqlalchemy import select

from .mcq import choice_response_letter, is_choice_scored_item
from .models import (
    AnswerReceipt,
    ParticipantResponse,
    PilotQuestionTrial,
    PilotSession,
    QAItem,
)
from .pilot_trials import question_bucket


def _iso(value):
    return value.isoformat() if value is not None else None


def _percentile(sorted_values: Sequence[float], fraction: float) -> Optional[float]:
    """Linear-interpolation percentile (same convention as numpy's default)."""

    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return float(sorted_values[low] * (1 - weight) + sorted_values[high] * weight)


def _timing_summary(values: Iterable[Optional[int]]) -> dict:
    present = sorted(float(v) for v in values if v is not None)
    return {
        "n": len(present),
        "p25": _percentile(present, 0.25),
        "median": _percentile(present, 0.50),
        "p75": _percentile(present, 0.75),
    }


#: ``scoring_metadata.status`` values that mean "no verdict yet". Mirrors
#: ``scripts/export_pilot_responses._item_payload`` so the two pilot exports
#: agree on what counts as missing data.
UNRESOLVED_SCORING_STATUSES = frozenset(
    {"unresolved", "unusable_reply", "queued", "scorer_disabled"}
)


def resolve_correctness(bucket, response, scoring_metadata):
    """``(is_scored, is_correct, score_value)`` for one response.

    The two buckets carry their verdict differently and neither can be read as
    the other:

    * **open** -- the LLM judge writes ``correctness_score`` on the 0/0.5/1
      scale. No score means the judge has not run (the outbox is not drained,
      or scoring is disabled), which is missing data.
    * **mcq** -- a cleanly parsed letter is scored at *intake*, where the
      existing pipeline records only the ``is_correct`` label and leaves
      ``correctness_score`` NULL. Reading "no numeric score" as unscored would
      therefore discard almost every MCQ answer, so the label is honoured as a
      resolved verdict; only an explicit pending/unresolved marker is unscored.
    """

    if response is None:
        return False, None, None
    status = (scoring_metadata or {}).get("status")
    score = response.correctness_score
    if bucket == "open":
        if score is None:
            return False, None, None
        return True, score == 1, float(score)
    # --- mcq / tf ---------------------------------------------------------
    label = (response.is_correct or "").strip().lower()
    if label == "pending" or status in UNRESOLVED_SCORING_STATUSES:
        return False, None, None
    if score is not None:
        return True, score == 1, float(score)
    if label.startswith("yes"):
        return True, True, 1.0
    if label.startswith("no"):
        return True, False, 0.0
    return False, None, None


def collect_pilot_rows(db, participant_ids=None) -> List[dict]:
    """One dict per pilot question trial, joined to its receipt and response.

    Answer text and ``submitted_at`` come from ``answer_receipts`` (immutable,
    exactly one per assignment). The verdict comes from the latest
    ``participant_responses`` row for the assignment, which the existing
    scoring pipeline writes after the receipt is accepted -- so it is routinely
    absent for freshly submitted trials, and that absence is reported as
    unscored rather than filled in.
    """

    stmt = (
        select(PilotQuestionTrial, QAItem, PilotSession)
        .join(QAItem, PilotQuestionTrial.qa_item_id == QAItem.id)
        .join(PilotSession, PilotQuestionTrial.pilot_session_id == PilotSession.id)
        .order_by(
            PilotQuestionTrial.participant_id,
            PilotQuestionTrial.sequence_index,
        )
    )
    if participant_ids:
        stmt = stmt.where(PilotQuestionTrial.participant_id.in_(list(participant_ids)))

    rows = []
    for trial, qa_item, pilot_session in db.execute(stmt).all():
        receipt = db.scalar(
            select(AnswerReceipt).where(AnswerReceipt.assignment_id == trial.assignment_id)
        )
        response = db.scalars(
            select(ParticipantResponse)
            .where(ParticipantResponse.assignment_id == trial.assignment_id)
            .order_by(ParticipantResponse.received_at.desc(), ParticipantResponse.id)
        ).first()
        meta = dict(trial.trial_metadata or {})
        scoring_metadata = dict(getattr(response, "scoring_metadata", None) or {})
        raw_answer = receipt.raw_answer if receipt else None
        selected_choice = None
        if raw_answer is not None and is_choice_scored_item(qa_item):
            selected_choice = choice_response_letter(qa_item, raw_answer)
        bucket = question_bucket(qa_item)
        is_scored, is_correct, score_value = resolve_correctness(
            bucket, response, scoring_metadata
        )

        rows.append(
            {
                # --- identity / provenance -------------------------------
                "assignment_id": trial.assignment_id,
                "participant_id": trial.participant_id,
                "pilot_session_id": trial.pilot_session_id,
                "qa_item_id": trial.qa_item_id,
                "question_version": meta.get("question_version"),
                "question_type": trial.question_type,
                "question_bucket": bucket,
                "sequence_index": trial.sequence_index,
                "condition": trial.condition,
                "defect_type": meta.get("defect_type"),
                "defect_rate": meta.get("defect_rate"),
                "passage_id": meta.get("passage_id"),
                "window_key": meta.get("window_key"),
                # --- timing ----------------------------------------------
                "started_at": _iso(trial.started_at),
                "submitted_at": _iso(trial.submitted_at),
                "active_time_ms": trial.active_time_ms,
                "focused_time_ms": trial.focused_time_ms,
                "passage_onscreen_ms": trial.passage_onscreen_ms,
                "wall_clock_time_ms": trial.wall_clock_time_ms,
                "visibility_change_count": trial.visibility_change_count,
                "focus_change_count": trial.focus_change_count,
                "reload_count": trial.reload_count,
                # --- outcome ---------------------------------------------
                "status": trial.status,
                "submission_id": trial.submission_id,
                "answer_receipt_id": receipt.id if receipt else None,
                "has_receipt": receipt is not None,
                "raw_answer": raw_answer,
                "selected_choice": selected_choice,
                "correctness_score": (
                    None if response is None else response.correctness_score
                ),
                "is_scored": is_scored,
                "is_correct": is_correct,
                "is_correct_label": None if response is None else response.is_correct,
                "score_value": score_value,
                "scoring_method": scoring_metadata.get("method"),
                "scoring_version": scoring_metadata.get("scale")
                or scoring_metadata.get("version"),
                "scored_at": _iso(getattr(response, "scored_at", None)),
                "consent_version": pilot_session.consent_version,
                "consented_at": _iso(pilot_session.consented_at),
            }
        )
    return rows


def _ratio(numerator, denominator):
    """Rate, or ``None`` when the denominator is zero (never a silent 0.0)."""

    if not denominator:
        return None
    return numerator / denominator


def summarize_pilot_rows(rows: Sequence[dict]) -> dict:
    """Accuracy, volume and timing over a set of trials. Pure, so it is unit
    testable and reusable for every grouping."""

    presented = list(rows)
    started = [r for r in presented if r["started_at"] is not None]
    answered = [r for r in presented if r["has_receipt"]]
    # Incomplete = STARTED but no accepted receipt. A derived reporting state:
    # the pilot never expires a question, so an abandoned one simply stays
    # started forever and shows up here.
    incomplete = [r for r in started if not r["has_receipt"]]

    open_rows = [r for r in answered if r["question_bucket"] == "open"]
    mcq_rows = [r for r in answered if r["question_bucket"] == "mcq"]
    open_scored = [r for r in open_rows if r["is_scored"]]
    mcq_scored = [r for r in mcq_rows if r["is_scored"]]
    correct_open = [r for r in open_scored if r["is_correct"]]
    correct_mcq = [r for r in mcq_scored if r["is_correct"]]
    open_scores = [float(r["score_value"]) for r in open_scored]

    return {
        "questions_presented": len(presented),
        "questions_started": len(started),
        "questions_answered": len(answered),
        "questions_incomplete": len(incomplete),
        "completion_rate": _ratio(len(answered), len(presented)),
        "open_count": len(open_rows),
        "open_scored_count": len(open_scored),
        "open_unscored": len(open_rows) - len(open_scored),
        "correct_open": len(correct_open),
        "accuracy_open": _ratio(len(correct_open), len(open_scored)),
        "open_score_mean": (sum(open_scores) / len(open_scores)) if open_scores else None,
        "open_score_scale": "0/0.5/1",
        "mcq_count": len(mcq_rows),
        "mcq_scored_count": len(mcq_scored),
        "mcq_unscored": len(mcq_rows) - len(mcq_scored),
        "correct_mcq": len(correct_mcq),
        "accuracy_mcq": _ratio(len(correct_mcq), len(mcq_scored)),
        "active_time_ms": _timing_summary(r["active_time_ms"] for r in answered),
        # The bracket around active time: focused is a lower bound, active an
        # upper bound. Reported side by side so a result can be checked against
        # both rather than resting on one definition of "reading".
        "focused_time_ms": _timing_summary(r["focused_time_ms"] for r in answered),
        "passage_onscreen_ms": _timing_summary(
            r["passage_onscreen_ms"] for r in answered
        ),
        "wall_clock_time_ms": _timing_summary(r["wall_clock_time_ms"] for r in answered),
        "active_time_ms_open": _timing_summary(r["active_time_ms"] for r in open_rows),
        "active_time_ms_mcq": _timing_summary(r["active_time_ms"] for r in mcq_rows),
        "focused_time_ms_open": _timing_summary(r["focused_time_ms"] for r in open_rows),
        "focused_time_ms_mcq": _timing_summary(r["focused_time_ms"] for r in mcq_rows),
        "wall_clock_time_ms_open": _timing_summary(
            r["wall_clock_time_ms"] for r in open_rows
        ),
        "wall_clock_time_ms_mcq": _timing_summary(
            r["wall_clock_time_ms"] for r in mcq_rows
        ),
    }


def _group(rows, key):
    grouped = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(row)
    return grouped


def compute_pilot_metrics(db, participant_ids=None, rows=None) -> dict:
    """The full pilot report: overall plus every required breakdown."""

    rows = list(rows) if rows is not None else collect_pilot_rows(db, participant_ids)

    def breakdown(key, label):
        return [
            {label: value, **summarize_pilot_rows(group)}
            for value, group in sorted(
                _group(rows, key).items(), key=lambda kv: (kv[0] is None, str(kv[0]))
            )
        ]

    by_question = []
    for qa_item_id, group in sorted(
        _group(rows, "qa_item_id").items(), key=lambda kv: str(kv[0])
    ):
        first = group[0]
        by_question.append(
            {
                "qa_item_id": qa_item_id,
                "question_version": first["question_version"],
                "question_type": first["question_type"],
                "question_bucket": first["question_bucket"],
                "passage_id": first["passage_id"],
                "window_key": first["window_key"],
                **summarize_pilot_rows(group),
            }
        )

    return {
        "overall": summarize_pilot_rows(rows),
        "by_participant": breakdown("participant_id", "participant_id"),
        "by_condition": breakdown("condition", "condition"),
        "by_question_type": breakdown("question_bucket", "question_type"),
        "by_question": by_question,
        "trials": rows,
    }
