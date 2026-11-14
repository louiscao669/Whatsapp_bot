"""Background & eligibility questionnaire: between consent and the first question.

Order on ``/pilot``: consent -> Section A (eligibility) -> B -> Section C
consent prompt (+ C items if agreed) -> first study question. The server
enforces the order: :func:`questionnaire_blocks_questions` is checked by
``get_pilot_state`` so no study material is served before the questionnaire is
complete, whatever the client does.

Screen-out (administration note v1.0): a participant reviews the selections
that make them ineligible and may correct them before confirming. On
confirmation, they see a thank-you screen. Their ineligible answers are never stored, only an
anonymous per-version count is incremented, and -- for a real participant --
the participant record is deleted (``ON DELETE CASCADE`` removes the plan,
sessions and provider contacts with it). The email lives outside this database
(researcher-held mapping), so removing it there stays a manual step.

Flagged TEST participants are the one exception: they are not deleted, so a
tester can see the screen-out and then remove the participant from the admin
page. Their answers are still not stored.

Participants who already answered study questions before this feature existed
are not sent back through it (``legacy``); nothing about them changes.
"""

import os

from eten_shared.experiment_plan import is_test_participant
from eten_shared.models import (
    AnswerReceipt,
    Participant,
    PilotQuestionnaireResponse,
    PilotScreenoutCount,
    utc_now,
)
from eten_shared.pilot_questionnaire import (
    DEFAULT_LANGUAGE,
    INSTRUMENT_VERSION,
    STEPS,
    QuestionnaireValidationError,
    eligibility_exclusions,
    next_step,
    public_instrument,
    validate_section_answers,
)
from sqlalchemy import delete, select, update

#: dashboard_preferences flag set on a TEST participant who screened out.
SCREENED_OUT_KEY = "questionnaire_screened_out"

COMPLETE = "complete"
NOT_REQUIRED = "not_required"
SCREENED_OUT = "screened_out"


class QuestionnaireError(Exception):
    """Bad questionnaire request (400)."""


class QuestionnaireNotFoundError(QuestionnaireError):
    """Unknown participant (404)."""


def questionnaire_enabled() -> bool:
    return os.getenv("PILOT_QUESTIONNAIRE_ENABLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def questionnaire_language() -> str:
    return os.getenv("PILOT_QUESTIONNAIRE_LANGUAGE", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE


def _participant(db, participant_id, *, for_update=False):
    query = select(Participant).where(Participant.id == (participant_id or "").strip())
    if for_update:
        query = query.with_for_update()
    participant = db.scalars(query).first()
    if participant is None:
        raise QuestionnaireNotFoundError("Participant not found")
    return participant


def _response_row(db, participant):
    return db.scalars(
        select(PilotQuestionnaireResponse).where(
            PilotQuestionnaireResponse.participant_id == participant.id
        )
    ).first()


def _has_answered_questions(db, participant) -> bool:
    return (
        db.scalars(
            select(AnswerReceipt.id).where(AnswerReceipt.participant_id == participant.id).limit(1)
        ).first()
        is not None
    )


def questionnaire_status(db, participant) -> str:
    """``eligibility`` / ``background`` / ``religion`` (the
    step to show next), or ``complete``, ``screened_out``, ``not_required``."""

    prefs = participant.dashboard_preferences or {}
    if prefs.get(SCREENED_OUT_KEY):
        return SCREENED_OUT
    row = _response_row(db, participant)
    if row is not None:
        upcoming = next_step(row.status)
        return upcoming or COMPLETE
    if not questionnaire_enabled() or _has_answered_questions(db, participant):
        return NOT_REQUIRED
    return STEPS[0]


def questionnaire_blocks_questions(db, participant) -> bool:
    return questionnaire_status(db, participant) not in (COMPLETE, NOT_REQUIRED)


def get_questionnaire_state(db, participant_id):
    participant = _participant(db, participant_id)
    status = questionnaire_status(db, participant)
    payload = {
        "status": status,
        "required": status not in (COMPLETE, NOT_REQUIRED),
        "consented": bool(participant.consented),
    }
    instrument = public_instrument(questionnaire_language())
    # UI strings always travel, so the client can render the screen-out page.
    payload["ui"] = instrument["ui"]
    payload["language"] = instrument["language"]
    if payload["required"] and status != SCREENED_OUT:
        payload["instrument"] = instrument
        row = _response_row(db, participant) if participant.consented else None
        if row is not None:
            payload["answers"] = {
                step: getattr(row, f"{step}_answers") or {}
                for step in STEPS[:STEPS.index(status)]
                if step != "religion" or row.religion_consent
            }
            payload["religion_consent"] = row.religion_consent
    return payload


def _increment_screenouts(db):
    updated = db.execute(
        update(PilotScreenoutCount)
        .where(PilotScreenoutCount.instrument_version == INSTRUMENT_VERSION)
        .values(screenouts=PilotScreenoutCount.screenouts + 1)
    ).rowcount
    if not updated:
        db.add(PilotScreenoutCount(instrument_version=INSTRUMENT_VERSION, screenouts=1))
    db.flush()


def _screen_out(db, participant):
    _increment_screenouts(db)
    db.execute(delete(PilotQuestionnaireResponse).where(
        PilotQuestionnaireResponse.participant_id == participant.id
    ))
    if is_test_participant(participant):
        prefs = dict(participant.dashboard_preferences or {})
        prefs[SCREENED_OUT_KEY] = True
        participant.dashboard_preferences = prefs
        db.flush()
        return {"status": SCREENED_OUT, "deleted": False}
    participant_id = participant.id
    db.expunge(participant)
    db.execute(delete(Participant).where(Participant.id == participant_id))
    db.flush()
    return {"status": SCREENED_OUT, "deleted": True}


def submit_questionnaire_section(
    db, participant_id, section_id, answers, *, religion_consent=None, edit=False,
    confirmed_exclusions=None,
):
    """Save one section. Returns the next status; never a score or a verdict
    beyond eligibility (which the participant has to be told)."""

    participant = _participant(db, participant_id, for_update=True)
    if not participant.consented:
        raise QuestionnaireError("Consent is required before the questionnaire")
    participant.last_seen_at = utc_now()  # admin "Last seen"; see service._seen

    status = questionnaire_status(db, participant)
    if status in (COMPLETE, NOT_REQUIRED, SCREENED_OUT):
        # A retried final submit, or a stale tab: report where things stand.
        return {"status": status}
    if section_id not in STEPS:
        raise QuestionnaireError(f"Unknown questionnaire section '{section_id}'")
    previously_saved = STEPS.index(section_id) < STEPS.index(status)
    if previously_saved and edit is not True:
        # Unmarked repeat submissions are network retries.
        return {"status": status}
    if not previously_saved and section_id != status:
        raise QuestionnaireError(f"Expected section '{status}', got '{section_id}'")

    try:
        if section_id == "religion":
            if not isinstance(religion_consent, bool):
                raise QuestionnaireError(
                    "Section C requires an explicit boolean 'religion_consent'"
                )
            if not religion_consent and any(
                value not in (None, "") for value in (answers or {}).values()
            ):
                raise QuestionnaireError("Section C answers sent after declining Section C")
            cleaned = validate_section_answers(section_id, answers if religion_consent else {})
        else:
            cleaned = validate_section_answers(section_id, answers)
    except QuestionnaireValidationError as exc:
        raise QuestionnaireError(str(exc)) from exc

    row = _response_row(db, participant)
    if section_id == "eligibility":
        exclusions = eligibility_exclusions(cleaned)
        if exclusions:
            if confirmed_exclusions != exclusions:
                return {"status": status, "confirm_exclusions": exclusions}
            return _screen_out(db, participant)
        if row is None:
            row = PilotQuestionnaireResponse(
                participant_id=participant.id, instrument_version=INSTRUMENT_VERSION,
                language=questionnaire_language(), eligible_at=utc_now(),
            )
            db.add(row)
        row.eligibility_answers = cleaned
    elif section_id == "background":
        row.background_answers = cleaned
    elif section_id == "religion":
        row.religion_consent = religion_consent
        row.religion_answers = cleaned if religion_consent else None
        row.instrument_version = INSTRUMENT_VERSION
        row.completed_at = utc_now()
    if not previously_saved:
        row.status = section_id
    db.flush()
    return {"status": next_step(row.status) or COMPLETE}


def _iso(value):
    return value.isoformat() if value is not None else None


def get_questionnaire_results(db, participant_ids=None):
    """Admin/export view: one row per participant with a questionnaire, plus
    the anonymous screen-out counts."""

    query = select(PilotQuestionnaireResponse)
    if participant_ids:
        query = query.where(PilotQuestionnaireResponse.participant_id.in_(participant_ids))
    rows = []
    for row in db.scalars(query.order_by(PilotQuestionnaireResponse.created_at)).all():
        # Readers who had saved C and were waiting for the retired quiz already
        # finished the shortened survey at their last questionnaire save.
        completed_at = row.completed_at or (row.updated_at if row.status == "religion" else None)
        rows.append(
            {
                "participant_id": row.participant_id,
                "instrument_version": row.instrument_version,
                "language": row.language,
                "status": row.status,
                "complete": completed_at is not None,
                "eligible_at": _iso(row.eligible_at),
                "completed_at": _iso(completed_at),
                "eligibility": row.eligibility_answers or {},
                "background": row.background_answers,
                "religion_consent": row.religion_consent,
                "religion": row.religion_answers,
                "familiarity": row.familiarity_answers,
                "familiarity_correct": row.familiarity_correct,
                "familiarity_answered": row.familiarity_answered,
                "familiarity_score": row.familiarity_score,
            }
        )
    screenouts = {
        count.instrument_version: count.screenouts
        for count in db.scalars(select(PilotScreenoutCount)).all()
    }
    return {"responses": rows, "screenouts": screenouts}
