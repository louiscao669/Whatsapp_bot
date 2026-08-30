"""Human-pilot study logic: one question at a time, timed by page visibility.

What this module deliberately does NOT do, because the pilot measures reading
comprehension under translation defects and anything else is a confound:

* no rewards, wallet, streak, badge or leaderboard writes;
* no correctness feedback to the participant while the study runs;
* no countdown, no deadline, no expiry -- ``expire_dashboard_question`` and
  ``AssignmentStatus.EXPIRED`` are never touched from here;
* no periodic heartbeat and no general engagement analytics -- the only events
  written are the three question-timing events in
  ``eten_shared.pilot_trials.PILOT_TIMING_EVENTS``, each scoped to one
  assignment.

What it reuses, unchanged: the designed (Latin-square) assignment selector and
its variant-passage delivery, the idempotent answer-receipt intake, and the
downstream 0/0.5/1 open scorer + MCQ letter pipeline that run *after* a receipt
is accepted.
"""

import os
import re
from datetime import timezone

from sqlalchemy import func, select

from eten_shared.repo_paths import REPO_ROOT
from eten_shared.answer_receipts import create_answer_receipt
from eten_shared.domain.assignments import (
    create_assignment_for_qa_item,
    get_or_create_participant_session,
    record_participant_event,
    automatic_assignment_enabled,
    experiment_assignment_enabled,
    assignment_passage_snapshot,
    surrounding_passage_text,
)
from eten_shared.mcq import (
    choice_letters_for_type,
    is_choice_scored_item,
    question_type_value,
)
from eten_shared.models import (
    AnswerReceipt,
    Assignment,
    AssignmentStatus,
    ExperimentPlanCell,
    Participant,
    PassageVerse,
    PilotQuestionTrial,
    PilotSession,
    PilotTrialStatus,
    QAItem,
    ResponseType,
    utc_now,
)
from eten_shared.pilot_metrics import compute_pilot_metrics
from eten_shared.pilot_trials import (
    PILOT_EVENT_SOURCE,
    PILOT_PROVIDER,
    PILOT_TIMING_EVENTS,
    QUESTION_HIDDEN_EVENT,
    QUESTION_SUBMITTED_EVENT,
    QUESTION_VISIBLE_EVENT,
    PilotActiveTimeError,
    build_trial_metadata,
    question_bucket,
    validate_active_time_ms,
    validate_count,
)

# The dashboard already owns the one correct way to turn a plan cell into an
# assignment (resolve the condition's variant passage, refuse to fall back to
# the condition-invariant QA text, reset the batch at a cell boundary).
# Importing it keeps the pilot and the dashboard delivering byte-identical
# passages for the same cell; forking that logic would silently split the
# experiment across two surfaces.
from app.user_dashboard.service import (  # noqa: E402
    _experiment_assignment_kwargs,
    _select_next_dashboard_qa_item,
)


class PilotError(Exception):
    """Bad request from the pilot client (400)."""


class PilotNotFoundError(PilotError):
    """Unknown participant / assignment, or one that is not this participant's (404)."""


#: Consent version stamped on a pilot session. Bump when the consent text
#: changes so responses can be attributed to the text a participant agreed to.
DEFAULT_CONSENT_VERSION = os.getenv("PILOT_CONSENT_VERSION", "pilot-2026-08-18")


def _iso(value):
    return value.isoformat() if value is not None else None


def _as_utc(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _participant(db, participant_id):
    participant = db.scalars(
        select(Participant).where(Participant.id == (participant_id or "").strip())
    ).first()
    if not participant:
        raise PilotNotFoundError("Participant not found")
    return participant


def get_or_create_pilot_session(db, participant, consent_version=None) -> PilotSession:
    """The participant's single pilot run, created on first contact.

    Consent is captured at enrolment (``participants.consented``), not in this
    UI; the pilot only records *which version* of the consent text was in force
    and when that consent was observed, so an export can be filtered by it.
    """

    pilot_session = db.scalars(
        select(PilotSession).where(PilotSession.participant_id == participant.id)
    ).first()
    if pilot_session is None:
        pilot_session = PilotSession(
            participant_id=participant.id,
            consent_version=consent_version or DEFAULT_CONSENT_VERSION,
            consented_at=utc_now() if participant.consented else None,
            started_at=utc_now(),
            session_metadata={},
        )
        db.add(pilot_session)
        db.flush()
        return pilot_session
    if consent_version and pilot_session.consent_version != consent_version:
        pilot_session.consent_version = consent_version
        pilot_session.consented_at = utc_now()
    elif pilot_session.consented_at is None and participant.consented:
        pilot_session.consented_at = utc_now()
    return pilot_session


CONSENT_DIR = REPO_ROOT / "platform" / "pilot" / "consent"


def get_consent_state(db, participant_id):
    """What the consent screen needs: whether to show, and the text to show.

    ``required`` is false once the participant has agreed, so a reload mid-study
    does not re-prompt. A participant who declined is NOT re-prompted either --
    they are shown the declined state, because re-asking someone who refused is
    pressure, not consent.
    """

    participant = _participant(db, participant_id)
    version = DEFAULT_CONSENT_VERSION
    return {
        "required": not participant.consented and participant.consent_declined_at is None,
        "consented": bool(participant.consented),
        "declined": participant.consent_declined_at is not None,
        "version": version,
        "text": _consent_text(version),
    }


def _consent_text(version):
    path = CONSENT_DIR / f"consent_en_{version}.md"
    if not path.is_file():
        raise PilotError(
            f"Consent text {path.name} is missing; refusing to show a consent "
            "screen without the approved wording."
        )
    return path.read_text(encoding="utf-8")


def record_consent(db, participant_id, agreed, version=None):
    """Write the participant's decision.

    Agreement is idempotent. A decline is terminal for this flow: it clears
    nothing that was already agreed, and a later agreement is only possible by
    an administrator resetting the record, which is deliberate -- withdrawing
    and re-entering a study is an enrolment decision, not a UI one.
    """

    participant = _participant(db, participant_id)
    version = version or DEFAULT_CONSENT_VERSION
    if _consent_text(version) is None:  # pragma: no cover - guarded above
        raise PilotError("Unknown consent version")

    if agreed:
        if not participant.consented:
            participant.consented = True
            participant.consented_at = utc_now()
            participant.consent_version = version
            participant.consent_declined_at = None
        get_or_create_pilot_session(db, participant, version)
    else:
        if not participant.consented and participant.consent_declined_at is None:
            participant.consent_declined_at = utc_now()
            participant.consent_version = version
    db.flush()
    return {
        "consented": bool(participant.consented),
        "declined": participant.consent_declined_at is not None,
        "version": participant.consent_version,
    }


def _answered_assignment_ids(db, participant):
    return set(
        db.scalars(
            select(AnswerReceipt.assignment_id).where(
                AnswerReceipt.participant_id == participant.id
            )
        ).all()
    )


def _open_pilot_assignments(db, participant):
    """Unanswered assignments in the pilot's presentation order.

    Order is the *existing* plan order -- the plan cell's ``sequence_index``
    first (the Latin square's per-participant condition order), then the
    assignment chain's own creation order. Nothing here is hardcoded; the pilot
    presents whatever the assignment system already decided.
    """

    answered = _answered_assignment_ids(db, participant)
    rows = db.execute(
        select(Assignment, ExperimentPlanCell)
        .outerjoin(
            ExperimentPlanCell, Assignment.experiment_cell_id == ExperimentPlanCell.id
        )
        .where(
            Assignment.participant_id == participant.id,
            Assignment.status == AssignmentStatus.ASSIGNED.value,
        )
    ).all()
    candidates = [(a, cell) for a, cell in rows if a.id not in answered]
    # Sorted in Python rather than SQL so NULL cell ordering is explicit and
    # identical on SQLite (tests) and PostgreSQL (production).
    candidates.sort(
        key=lambda pair: (
            pair[1].sequence_index if pair[1] is not None else 1_000_000,
            _as_utc(pair[0].assigned_at),
            pair[0].id,
        )
    )
    return [assignment for assignment, _cell in candidates]


def _mint_next_assignment(db, participant):
    """Ask the existing selector for the participant's next planned question."""

    if not (automatic_assignment_enabled() or experiment_assignment_enabled()):
        return None
    qa_item, cell = _select_next_dashboard_qa_item(db, participant)
    if qa_item is None:
        return None
    participant_session = get_or_create_participant_session(db, participant)
    prompt = create_assignment_for_qa_item(
        db,
        participant,
        participant_session,
        qa_item,
        assignment_source=PILOT_PROVIDER,
        **_experiment_assignment_kwargs(db, participant_session, cell, qa_item),
    )
    if prompt is None:
        return None
    return db.get(Assignment, prompt.assignment_id)


def _next_sequence_index(db, pilot_session):
    highest = db.scalar(
        select(func.max(PilotQuestionTrial.sequence_index)).where(
            PilotQuestionTrial.pilot_session_id == pilot_session.id
        )
    )
    return 0 if highest is None else int(highest) + 1


def _get_or_create_trial(db, pilot_session, participant, assignment, qa_item):
    trial = db.scalars(
        select(PilotQuestionTrial).where(
            PilotQuestionTrial.assignment_id == assignment.id
        )
    ).first()
    if trial is not None:
        return trial
    metadata = build_trial_metadata(db, assignment, qa_item)
    trial = PilotQuestionTrial(
        pilot_session_id=pilot_session.id,
        participant_id=participant.id,
        assignment_id=assignment.id,
        qa_item_id=qa_item.id,
        sequence_index=_next_sequence_index(db, pilot_session),
        question_type=question_type_value(qa_item),
        condition=metadata.get("condition"),
        status=PilotTrialStatus.ASSIGNED.value,
        active_time_ms=0,
        visibility_change_count=0,
        reload_count=0,
        trial_metadata=metadata,
    )
    db.add(trial)
    db.flush()
    return trial


def _trial_for_assignment(db, participant, assignment_id):
    """Resolve one of *this* participant's trials, or 404.

    A participant may only ever touch their own assignment: an id belonging to
    someone else is reported as not found (not as forbidden), so the endpoint
    leaks nothing about other participants' assignments.
    """

    assignment_id = (assignment_id or "").strip()
    if not assignment_id:
        raise PilotError("Assignment is required")
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or assignment.participant_id != participant.id:
        raise PilotNotFoundError("Assignment not found")
    trial = db.scalars(
        select(PilotQuestionTrial).where(
            PilotQuestionTrial.assignment_id == assignment.id
        )
    ).first()
    if trial is None or trial.participant_id != participant.id:
        raise PilotNotFoundError("Assignment not found")
    return assignment, trial


def _record_timing_event(
    db,
    participant,
    trial,
    event_type,
    *,
    client_event_at=None,
    server_received_at=None,
):
    """One auditable question-timing event. Scoped to a single assignment."""

    if event_type not in PILOT_TIMING_EVENTS:
        raise PilotError(f"Unsupported pilot event type: {event_type}")
    record_participant_event(
        db,
        participant,
        event_type,
        {
            "participant_id": participant.id,
            "pilot_session_id": trial.pilot_session_id,
            "assignment_id": trial.assignment_id,
            "qa_item_id": trial.qa_item_id,
            "client_event_at": client_event_at,
            "server_received_at": _iso(server_received_at or utc_now()),
            "active_time_ms": trial.active_time_ms,
            "visibility_change_count": trial.visibility_change_count,
        },
        source=PILOT_EVENT_SOURCE,
    )


def _progress(db, participant, pilot_session):
    presented = db.scalar(
        select(func.count(PilotQuestionTrial.id)).where(
            PilotQuestionTrial.pilot_session_id == pilot_session.id
        )
    )
    answered = db.scalar(
        select(func.count(PilotQuestionTrial.id)).where(
            PilotQuestionTrial.pilot_session_id == pilot_session.id,
            PilotQuestionTrial.status == PilotTrialStatus.SUBMITTED.value,
        )
    )
    return {"questions_presented": int(presented or 0), "questions_answered": int(answered or 0)}


def _normalized(text):
    return " ".join(str(text or "").split())


def _window_verse_texts(db, assignment):
    """The delivered window's verses, one string each, in reading order."""

    translation_id = assignment.passage_translation_id
    verse_numbers = [str(n).strip() for n in (assignment.passage_verse_numbers or [])]
    if not translation_id or not verse_numbers:
        return []
    verses = db.scalars(
        select(PassageVerse)
        .where(
            PassageVerse.translation_id == translation_id,
            PassageVerse.verse_number.in_(verse_numbers),
        )
        .order_by(PassageVerse.position)
    ).all()
    return [v.text.strip() for v in verses if v.text and v.text.strip()]


def _strip_verse_prefix(line, verse_numbers):
    match = re.match(r"^(\d+)\s+(.+)$", line.strip())
    if match and match.group(1) in verse_numbers:
        return match.group(2).strip()
    return line.strip()


def _passage_lines(db, assignment, qa_item, delivered_text):
    """The delivered passage split one verse per line, for readability.

    Splitting is only ever a re-rendering of the text that was actually
    delivered -- never a re-fetch. The guard matters: an experiment assignment
    carries the CONDITION's variant passage, so recovering verses from the
    clean translation whenever they happened to line up would quietly serve
    undefective text to someone in a defect arm. So:

      1. a multi-line snapshot is split as delivered (the variant path already
         stores one verse per line, with a verse-number prefix);
      2. a single joined blob is split into the window's verses ONLY when those
         verses reassemble to exactly the delivered text;
      3. otherwise it stays one paragraph, because any split would be a guess.
    """

    raw = str(assignment.passage_text or "").strip()
    verse_numbers = {str(n).strip() for n in (assignment.passage_verse_numbers or [])}

    raw_lines = [line for line in raw.splitlines() if line.strip()]
    if len(raw_lines) > 1:
        return [_strip_verse_prefix(line, verse_numbers) for line in raw_lines]

    verses = _window_verse_texts(db, assignment)
    if verses and _normalized(" ".join(verses)) == _normalized(delivered_text):
        return verses

    return [delivered_text] if delivered_text else []


def _serialize_question(db, participant, assignment, qa_item, trial):
    """The participant-facing question payload.

    Carries no correctness signal of any kind: no expected answer, no correct
    choice, no score, no wallet, no streak. Only what is needed to read the
    passage and answer.
    """

    question_type = question_type_value(qa_item)
    letters = choice_letters_for_type(question_type)
    choices = [
        {"letter": letters[index], "text": text}
        for index, text in enumerate(qa_item.mcq_choices or [])
        if index < len(letters)
    ]
    passage_text = (
        assignment_passage_snapshot(assignment)
        or surrounding_passage_text(db, assignment)
        or qa_item.passage_text
    )
    return {
        "assignment_id": assignment.id,
        "trial_id": trial.id,
        "qa_item_id": qa_item.id,
        "sequence_index": trial.sequence_index,
        "question_number": trial.sequence_index + 1,
        "question_type": question_type,
        "answer_mode": question_bucket(qa_item),
        "question": qa_item.question_text,
        "choices": choices,
        "passage_reference": qa_item.passage_reference,
        "passage_text": passage_text,
        # Same delivered text, split one verse per line for readability.
        "passage_lines": _passage_lines(db, assignment, qa_item, passage_text),
        "status": trial.status,
        "started_at": _iso(trial.started_at),
        # Server-side checkpoint so a reload resumes from the durable total
        # rather than from whatever the tab happens to remember.
        "active_time_ms": trial.active_time_ms,
        "focused_time_ms": trial.focused_time_ms,
        "passage_onscreen_ms": trial.passage_onscreen_ms,
        "visibility_change_count": trial.visibility_change_count,
        "focus_change_count": trial.focus_change_count,
        "reload_count": trial.reload_count,
    }


def _timing_payload(trial):
    return {
        "assignment_id": trial.assignment_id,
        "status": trial.status,
        "active_time_ms": trial.active_time_ms,
        "focused_time_ms": trial.focused_time_ms,
        "passage_onscreen_ms": trial.passage_onscreen_ms,
        "visibility_change_count": trial.visibility_change_count,
        "focus_change_count": trial.focus_change_count,
        "reload_count": trial.reload_count,
    }


def _apply_client_timing(trial, values):
    """Fold one client timing report into the trial, monotonically.

    Every duration and counter may only ever RISE, so a stale beacon, a
    duplicate unload or a reload restoring an older snapshot can never shrink
    something the participant actually spent. Each field is validated
    independently; a client that omits one simply leaves it untouched.
    """

    for field, reported in (
        ("active_time_ms", values.get("active_time_ms")),
        ("focused_time_ms", values.get("focused_time_ms")),
        ("passage_onscreen_ms", values.get("passage_onscreen_ms")),
    ):
        if reported is None:
            continue
        try:
            validated = validate_active_time_ms(reported)
        except PilotActiveTimeError as exc:
            raise PilotError(f"{field}: {exc}") from exc
        setattr(trial, field, max(int(getattr(trial, field) or 0), validated))

    for field, reported in (
        ("visibility_change_count", values.get("visibility_change_count")),
        ("focus_change_count", values.get("focus_change_count")),
        ("reload_count", values.get("reload_count")),
    ):
        if reported is None:
            continue
        setattr(
            trial, field, max(int(getattr(trial, field) or 0), validate_count(reported))
        )


def get_pilot_state(db, participant_id, consent_version=None):
    """The current question, or the completion state after the final one.

    Presenting a question creates its trial row (status ``assigned``) but does
    NOT start any clock: ``started_at`` is stamped only when the client reports
    the question actually visible. Exactly one question is ever returned, and
    no future question is included, so nothing downstream can preload or
    pre-time the next item.
    """

    participant = _participant(db, participant_id)
    pilot_session = get_or_create_pilot_session(db, participant, consent_version)

    assignment = None
    open_assignments = _open_pilot_assignments(db, participant)
    if open_assignments:
        assignment = open_assignments[0]
    else:
        assignment = _mint_next_assignment(db, participant)

    qa_item = None
    if assignment is not None:
        qa_item = assignment.qa_item or db.get(QAItem, assignment.qa_item_id)

    session_payload = {
        "pilot_session_id": pilot_session.id,
        "participant_id": participant.id,
        "consent_version": pilot_session.consent_version,
        "consented_at": _iso(pilot_session.consented_at),
    }

    if assignment is None or qa_item is None:
        if pilot_session.completed_at is None:
            pilot_session.completed_at = utc_now()
        return {
            "state": "complete",
            "session": session_payload,
            "question": None,
            "progress": _progress(db, participant, pilot_session),
        }

    trial = _get_or_create_trial(db, pilot_session, participant, assignment, qa_item)
    # Re-entering an unfinished study reopens it.
    pilot_session.completed_at = None
    return {
        "state": "question",
        "session": session_payload,
        "question": _serialize_question(db, participant, assignment, qa_item, trial),
        "progress": _progress(db, participant, pilot_session),
    }


def mark_pilot_question_viewed(
    db,
    participant_id,
    assignment_id,
    *,
    client_event_at=None,
    reload_count=None,
):
    """First visible render: stamp the server-authoritative ``started_at``.

    Idempotent by design. The client fires this every time the question becomes
    visible (including after a reload), so a repeat call must never move
    ``started_at`` -- doing so would silently reset the wall-clock measurement
    of anyone who switched tabs.
    """

    participant = _participant(db, participant_id)
    assignment, trial = _trial_for_assignment(db, participant, assignment_id)

    started_now = False
    now = utc_now()
    if trial.status == PilotTrialStatus.ASSIGNED.value:
        trial.status = PilotTrialStatus.STARTED.value
    if trial.started_at is None:
        trial.started_at = now
        started_now = True
    if assignment.started_at is None:
        # Mirrors the dashboard: an assignment opened without a delivery record
        # treats its first visible render as the delivery moment too.
        assignment.delivered_at = assignment.delivered_at or now
        assignment.started_at = now
    if reload_count is not None:
        trial.reload_count = max(trial.reload_count or 0, validate_count(reload_count))

    _record_timing_event(
        db,
        participant,
        trial,
        QUESTION_VISIBLE_EVENT,
        client_event_at=client_event_at,
        server_received_at=now,
    )
    return {
        "assignment_id": assignment.id,
        "status": trial.status,
        "started_at": _iso(trial.started_at),
        "started_now": started_now,
        "active_time_ms": trial.active_time_ms,
        "focused_time_ms": trial.focused_time_ms,
        "passage_onscreen_ms": trial.passage_onscreen_ms,
        "visibility_change_count": trial.visibility_change_count,
        "focus_change_count": trial.focus_change_count,
        "reload_count": trial.reload_count,
    }


def record_pilot_activity_checkpoint(
    db,
    participant_id,
    assignment_id,
    *,
    event_type,
    active_time_ms,
    focused_time_ms=None,
    passage_onscreen_ms=None,
    visibility_change_count=None,
    focus_change_count=None,
    reload_count=None,
    client_event_at=None,
):
    """Durable checkpoint of accumulated visible time (no heartbeat involved).

    Called only on ``visibilitychange`` / ``pagehide`` and at submit, via
    ``sendBeacon`` or a keepalive fetch. Values are **monotonic**: a checkpoint
    may only raise the stored total, so a late-arriving beacon, a duplicate
    unload or a reload that restores a stale draft can never shrink time the
    participant actually spent.
    """

    if event_type not in (QUESTION_VISIBLE_EVENT, QUESTION_HIDDEN_EVENT):
        raise PilotError("event_type must be question_visible or question_hidden")

    participant = _participant(db, participant_id)
    assignment, trial = _trial_for_assignment(db, participant, assignment_id)

    try:
        validate_active_time_ms(active_time_ms)
    except PilotActiveTimeError as exc:
        raise PilotError(str(exc)) from exc

    if trial.status == PilotTrialStatus.SUBMITTED.value:
        # The answer is in; timing for this question is closed. Accepting more
        # would let a background tab keep accruing "reading" time after submit.
        return {**_timing_payload(trial), "accepted": False}

    now = utc_now()
    if trial.started_at is None and event_type == QUESTION_VISIBLE_EVENT:
        trial.started_at = now
        if assignment.started_at is None:
            assignment.delivered_at = assignment.delivered_at or now
            assignment.started_at = now
    if trial.status == PilotTrialStatus.ASSIGNED.value and trial.started_at is not None:
        trial.status = PilotTrialStatus.STARTED.value

    _apply_client_timing(
        trial,
        {
            "active_time_ms": active_time_ms,
            "focused_time_ms": focused_time_ms,
            "passage_onscreen_ms": passage_onscreen_ms,
            "visibility_change_count": visibility_change_count,
            "focus_change_count": focus_change_count,
            "reload_count": reload_count,
        },
    )

    _record_timing_event(
        db,
        participant,
        trial,
        event_type,
        client_event_at=client_event_at,
        server_received_at=now,
    )
    return {**_timing_payload(trial), "accepted": True}


def _submission_payload(trial, receipt, *, duplicate):
    return {
        **_timing_payload(trial),
        "submission_id": trial.submission_id,
        "receipt_id": receipt.id,
        "submitted_at": _iso(trial.submitted_at),
        "wall_clock_time_ms": trial.wall_clock_time_ms,
        "duplicate": duplicate,
    }


def submit_pilot_answer(
    db,
    participant_id,
    assignment_id,
    *,
    submission_id,
    answer,
    active_time_ms,
    focused_time_ms=None,
    passage_onscreen_ms=None,
    visibility_change_count=None,
    focus_change_count=None,
    reload_count=None,
    client_event_at=None,
):
    """Accept one immutable answer receipt and close the question's timing.

    Order matters and is load-bearing:

    1. validate, including the client's ``active_time_ms``;
    2. create the receipt (idempotent on ``submission_id`` *and* on
       ``assignment_id``) -- this is the moment the answer is accepted, and
       ``answer_receipts.created_at`` is the authoritative ``submitted_at``;
    3. only then stamp the trial.

    Scoring is NOT done here. It runs after the receipt is drained into a
    response, so no judge latency can leak into ``active_time_ms`` (measured
    client-side, already final before this request was sent) or into
    ``submitted_at`` (the receipt's own creation time).
    """

    submission_id = (submission_id or "").strip()
    answer_text = (answer or "").strip()
    if not submission_id:
        raise PilotError("Submission ID is required")
    if not answer_text:
        raise PilotError("Answer is required")

    participant = _participant(db, participant_id)
    assignment, trial = _trial_for_assignment(db, participant, assignment_id)
    qa_item = assignment.qa_item or db.get(QAItem, assignment.qa_item_id)
    if qa_item is None:
        raise PilotNotFoundError("Question not found")

    if is_choice_scored_item(qa_item):
        valid_letters = choice_letters_for_type(question_type_value(qa_item))
        if answer_text.upper() not in valid_letters:
            raise PilotError(f"Choose {', '.join(valid_letters)}.")
        answer_text = answer_text.upper()

    try:
        validate_active_time_ms(active_time_ms)
    except PilotActiveTimeError as exc:
        raise PilotError(str(exc)) from exc

    existing_receipt = db.scalar(
        select(AnswerReceipt).where(AnswerReceipt.assignment_id == assignment.id)
    )
    if existing_receipt is not None:
        # Duplicate click or a retried request: hand back the original result
        # untouched. Re-stamping would let a second click overwrite the timing
        # of the submission that actually counted.
        return _submission_payload(trial, existing_receipt, duplicate=True)

    try:
        receipt, created = create_answer_receipt(
            db,
            participant_id=participant.id,
            assignment=assignment,
            provider=PILOT_PROVIDER,
            provider_update_id=submission_id,
            response_type=ResponseType.TEXT.value,
            raw_answer=answer_text,
        )
    except ValueError as exc:
        raise PilotError(str(exc)) from exc

    if not created:
        return _submission_payload(trial, receipt, duplicate=True)

    _apply_client_timing(
        trial,
        {
            "active_time_ms": active_time_ms,
            "focused_time_ms": focused_time_ms,
            "passage_onscreen_ms": passage_onscreen_ms,
            "visibility_change_count": visibility_change_count,
            "focus_change_count": focus_change_count,
            "reload_count": reload_count,
        },
    )
    trial.status = PilotTrialStatus.SUBMITTED.value
    trial.submission_id = submission_id
    trial.answer_receipt_id = receipt.id
    # Authoritative submission time: when the receipt was accepted. NOT
    # assignments.completed_at, which is written later by the scoring drain.
    trial.submitted_at = receipt.created_at
    started_at = _as_utc(trial.started_at) or _as_utc(assignment.started_at)
    submitted_at = _as_utc(receipt.created_at)
    if started_at is not None and submitted_at is not None:
        trial.wall_clock_time_ms = max(
            int((submitted_at - started_at).total_seconds() * 1000), 0
        )

    _record_timing_event(
        db,
        participant,
        trial,
        QUESTION_SUBMITTED_EVENT,
        client_event_at=client_event_at,
        server_received_at=submitted_at,
    )
    return _submission_payload(trial, receipt, duplicate=False)


def get_pilot_results(db, participant_ids=None):
    """Recomputed-from-source pilot report (see ``eten_shared.pilot_metrics``)."""

    return compute_pilot_metrics(db, participant_ids=participant_ids)
