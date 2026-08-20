"""Shared helpers for human-pilot question trials.

Everything in here is pure (no Flask, no request context) so the ``/pilot``
Flask service, the metrics query and the CLI export all agree on one definition
of a trial's provenance, its timing validation and its question bucket.
"""

import hashlib
import json
from typing import Optional, Tuple

from sqlalchemy import select

from .mcq import is_choice_scored_item, question_type_value
from .models import ExperimentPlanCell, ExperimentWindow, SourceChannel

#: ``answer_receipts.provider`` / ``participant_responses.source_channel`` value
#: for answers collected through ``/pilot``. Distinct from ``user_dashboard`` so
#: pilot rows can be separated from ordinary dashboard traffic in analysis.
PILOT_PROVIDER = SourceChannel.PILOT.value

#: ``participant_events.source`` for the three pilot timing events.
PILOT_EVENT_SOURCE = "pilot"

QUESTION_VISIBLE_EVENT = "question_visible"
QUESTION_HIDDEN_EVENT = "question_hidden"
QUESTION_SUBMITTED_EVENT = "question_submitted"

#: The only event types the pilot writes. These are scoped to the ACTIVE pilot
#: question (each carries an assignment_id); they are question timing records,
#: not general browsing analytics, and nothing else may be added here.
PILOT_TIMING_EVENTS = (
    QUESTION_VISIBLE_EVENT,
    QUESTION_HIDDEN_EVENT,
    QUESTION_SUBMITTED_EVENT,
)

#: Upper bound for a single question's accumulated visible time (6 hours). A
#: client-reported value above this is a broken clock, not a reading session.
MAX_ACTIVE_TIME_MS = 6 * 60 * 60 * 1000


class PilotActiveTimeError(ValueError):
    """Client-reported ``active_time_ms`` was missing, negative or absurd."""


def validate_active_time_ms(value, *, allow_none=False) -> Optional[int]:
    """Coerce a client-reported duration to a non-negative, sane integer.

    Client timing is untrusted input: a hostile or broken client could send a
    negative, fractional, NaN or year-long duration. Anything outside
    ``[0, MAX_ACTIVE_TIME_MS]`` is rejected rather than clamped, so a bad value
    surfaces as an error instead of silently becoming a plausible one.
    """

    if value is None:
        if allow_none:
            return None
        raise PilotActiveTimeError("active_time_ms is required")
    if isinstance(value, bool):
        raise PilotActiveTimeError("active_time_ms must be a number")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise PilotActiveTimeError("active_time_ms must be a number") from exc
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        raise PilotActiveTimeError("active_time_ms must be finite")
    if numeric < 0:
        raise PilotActiveTimeError("active_time_ms must be non-negative")
    if numeric > MAX_ACTIVE_TIME_MS:
        raise PilotActiveTimeError("active_time_ms is implausibly large")
    return int(round(numeric))


def validate_count(value, *, maximum=1_000_000) -> int:
    """Coerce a client-reported counter (visibility changes, reloads)."""

    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return 0
    if numeric < 0:
        return 0
    return min(numeric, maximum)


def question_bucket(qa_item) -> str:
    """``"mcq"`` for every choice-scored item (mcq *and* tf), else ``"open"``.

    The pilot reports two question types; ``tf`` is scored by the same
    letter-vs-key pipeline as ``mcq``, so it is analysed in that bucket. The
    unbucketed ``qa_items.question_type`` is still snapshotted on the trial.
    """

    return "mcq" if is_choice_scored_item(qa_item) else "open"


def question_version(qa_item) -> str:
    """A stable content fingerprint for the exact question a participant saw.

    ``qa_items`` carries no version counter and its rows are editable by the
    review tools, so a later edit would otherwise silently rewrite history. A
    12-hex-char digest over the answerable content gives an immutable version
    identifier that changes if and only if the question content changes, with
    no writes to the shared QA tables.
    """

    payload = json.dumps(
        {
            "question_text": qa_item.question_text or "",
            "question_type": question_type_value(qa_item),
            "expected_answer": qa_item.expected_answer or "",
            "mcq_choices": list(qa_item.mcq_choices or []),
            "mcq_correct_choice": qa_item.mcq_correct_choice or "",
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


#: condition -> (defect_type, defect_rate). Mirrors
#: ``scripts/export_pilot_responses.CONDITION_TO_EVAL`` (which expresses the
#: rate as the eval tree's directory name); kept as a float here because the
#: pilot report groups by numeric dose. ``clean`` is the shared 0% anchor of
#: both adequacy ladders; ``wbw`` is a family of its own with no dose.
CONDITION_DEFECTS = {
    "clean": ("omission", 0.0),
    "omission15": ("omission", 0.15),
    "omission30": ("omission", 0.30),
    "mistranslation15": ("mistranslation", 0.15),
    "mistranslation30": ("mistranslation", 0.30),
    "grammar30": ("grammar", 0.30),
    "wbw": ("google_word_by_word", None),
    # --- retired 2026-07-27b, still accepted so old rows keep exporting ---
    "omission10": ("omission", 0.10),
    "omission20": ("omission", 0.20),
    "mistranslation20": ("mistranslation", 0.20),
}


def defect_for_condition(condition) -> Tuple[Optional[str], Optional[float]]:
    if not condition:
        return None, None
    return CONDITION_DEFECTS.get(str(condition), (None, None))


def build_trial_metadata(db, assignment, qa_item) -> dict:
    """Immutable experimental provenance for one presented question.

    Snapshotted at presentation time from the existing experiment tables
    (``experiment_plan_cells`` for the condition/order, ``experiment_windows``
    for the tier-1 window). Documented keys:

    ``question_version``   content fingerprint of the question (see above)
    ``question_type``      raw ``qa_items.question_type`` (open/mcq/tf)
    ``passage_id``         ``qa_items.passage_id`` (source passage)
    ``passage_reference``  human-readable reference, for spot-checking
    ``window_key``         ``experiment_windows.window_key`` (3-verse window)
    ``experiment_window_id`` / ``experiment_cell_id`` FKs for re-joining
    ``condition``          plan-cell condition actually delivered
    ``defect_type`` / ``defect_rate``  derived from the condition
    ``cell_sequence_index`` the plan's condition order (NOT the pilot's
                            presentation order, which is ``sequence_index``)
    ``cell_group``         plan-cell ``chapter`` = balanced window group
    """

    cell = None
    if assignment.experiment_cell_id:
        cell = db.get(ExperimentPlanCell, assignment.experiment_cell_id)
    window = db.scalar(
        select(ExperimentWindow).where(ExperimentWindow.qa_item_id == qa_item.id)
    )
    condition = cell.condition if cell else None
    defect_type, defect_rate = defect_for_condition(condition)
    return {
        "question_version": question_version(qa_item),
        "question_type": question_type_value(qa_item),
        "passage_id": qa_item.passage_id,
        "passage_reference": qa_item.passage_reference,
        "window_key": window.window_key if window else None,
        "experiment_window_id": window.id if window else None,
        "experiment_cell_id": cell.id if cell else None,
        "condition": condition,
        "defect_type": defect_type,
        "defect_rate": defect_rate,
        "cell_sequence_index": cell.sequence_index if cell else None,
        "cell_group": cell.chapter if cell else None,
    }
