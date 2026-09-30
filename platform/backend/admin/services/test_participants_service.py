"""Create and delete test participants from the admin platform.

A test participant is an ordinary ``Participant`` flagged in
``dashboard_preferences`` (see ``eten_shared.experiment_plan``). Creating one
optionally writes the same Latin-square pilot plan the CLI writes, so the
returned ``/pilot/<id>`` link works immediately. The flag keeps test runs out
of the real Latin-square block order and out of the pilot exports; deletion is
limited to flagged participants so this action can never remove real data.

A test participant can also be restricted to question types (e.g. only ``why``
stems of hard66): stored as ``dashboard_preferences["wh_types"]`` and applied by the
selector as a hard filter for that participant alone (``participant_wh_filter``).
"""

from sqlalchemy import delete, func, select

from eten_shared.experiment_plan import (
    DEFAULT_QA_SET,
    QA_SETS,
    SLOTS,
    TEST_PARTICIPANT_KEY,
    ExperimentPlanError,
    available_qa_sets,
    is_test_participant,
    next_test_block_index,
    qa_set_wh_type_counts,
    write_participant_plan,
)
from eten_shared.wh_type import PARTICIPANT_WH_TYPES_KEY, WH_TYPES, parse_wh_types
from eten_shared.models import (
    Assignment,
    Participant,
    ParticipantResponse,
)
from backend.admin.services.system_languages_service import (
    canonical_language_code,
    upsert_system_language,
)

DEFAULT_LANGUAGE = "zh"
DEFAULT_NAME_PREFIX = "TEST"
MAX_NAME_LENGTH = 255


class TestParticipantError(Exception):
    __test__ = False  # not a pytest test class

    pass


def _display_name(value, block_index):
    name = " ".join(str(value or "").split())
    if not name:
        name = f"{DEFAULT_NAME_PREFIX} participant (block {block_index})"
    elif not name.upper().startswith(DEFAULT_NAME_PREFIX):
        # Keep test rows recognisable anywhere the name alone is shown.
        name = f"{DEFAULT_NAME_PREFIX} {name}"
    return name[:MAX_NAME_LENGTH]


def test_participant_options(db):
    """Question sets that currently have imported questions (for the admin form),
    with how many questions of each stem type each set holds."""
    return {
        "default_qa_set": DEFAULT_QA_SET,
        "wh_types": list(WH_TYPES),
        "qa_sets": [
            {
                "key": key,
                "label": label,
                "windows": count,
                "wh_counts": {t: n for t, n in qa_set_wh_type_counts(db, key).items()
                              if t in WH_TYPES},
            }
            for key, label, count in available_qa_sets(db)
        ],
    }


def _parse_wh_types(value):
    """["why"] / "why,how" / None -> sorted list; unknown names refused."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        value = ",".join(str(v) for v in value)
    try:
        return sorted(parse_wh_types(str(value)))
    except ValueError as exc:
        raise TestParticipantError(f"Question types: {exc}") from None


def create_test_participant(db, *, display_name=None, language=None, build_plan=True,
                            qa_set=None, wh_types=None):
    """Stage a flagged participant (+ plan). Caller commits; rollback on error.

    ``wh_types`` (e.g. ["why"]) restricts the participant to questions whose stem asks
    those interrogatives. Plan cells whose window group holds no such question are
    skipped at serving time, so the participant sees fewer than 8 conditions.
    """

    qa_set = (qa_set or DEFAULT_QA_SET).strip()
    if qa_set not in QA_SETS:
        raise TestParticipantError(f"Unknown question set '{qa_set}'")
    wh_list = _parse_wh_types(wh_types)
    if wh_list and not build_plan:
        raise TestParticipantError("A question-type restriction needs a pilot plan")

    language_code = canonical_language_code(language or DEFAULT_LANGUAGE)
    if not language_code:
        raise TestParticipantError("Language is required")

    block_index = next_test_block_index(db, qa_set if build_plan else None)
    participant = Participant(
        display_name=_display_name(display_name, block_index),
        target_language=language_code,
        consented=False,  # the pilot link walks the tester through consent
        dashboard_preferences={
            TEST_PARTICIPANT_KEY: True,
            **({PARTICIPANT_WH_TYPES_KEY: wh_list} if wh_list else {}),
        },
    )
    db.add(participant)
    db.flush()

    plan = []
    if build_plan:
        try:
            cells = write_participant_plan(
                db, participant, block_index, language_code, qa_set=qa_set
            )
        except ExperimentPlanError as exc:
            raise TestParticipantError(f"Could not build the pilot plan: {exc}") from exc
        plan = [
            {"sequence_index": seq, "group": chapter, "condition": condition}
            for chapter, condition, seq in sorted(cells, key=lambda c: c[2])
        ]

    wh_question_count = None
    if wh_list:
        counts = qa_set_wh_type_counts(db, qa_set)
        wh_question_count = sum(counts[t] for t in wh_list)
        if not wh_question_count:
            raise TestParticipantError(
                f"'{qa_set}' has no {'/'.join(wh_list)} questions imported"
            )

    # Last: its CREATE TABLE IF NOT EXISTS check committed the open transaction in
    # the SQLite tests (leaving a half-built participant on failure), so nothing
    # that might still fail may come after it.
    upsert_system_language(db, language_code, source="participant")

    return {
        "participant_id": participant.id,
        "display_name": participant.display_name,
        "language": language_code,
        "block_index": block_index if build_plan else None,
        "qa_set": qa_set if build_plan else None,
        "wh_types": wh_list,
        "wh_question_count": wh_question_count,
        "slot_count": len(SLOTS),
        "plan": plan,
        "pilot_path": f"/pilot/{participant.id}" if build_plan else None,
    }


def delete_test_participant(db, participant_id):
    """Delete a flagged participant and everything that cascades from it.

    Refuses for real participants. Uses a bulk DELETE so the database's
    ON DELETE CASCADE foreign keys remove sessions, plan cells, assignments,
    responses, receipts and trials in one statement.
    """

    participant = db.get(Participant, participant_id)
    if participant is None:
        raise TestParticipantError("Participant not found")
    if not is_test_participant(participant):
        raise TestParticipantError("Only test participants can be deleted here")

    removed = {
        "assignments": db.scalar(
            select(func.count()).select_from(Assignment).where(
                Assignment.participant_id == participant_id
            )
        ) or 0,
        "responses": db.scalar(
            select(func.count()).select_from(ParticipantResponse).where(
                ParticipantResponse.participant_id == participant_id
            )
        ) or 0,
    }
    db.expunge(participant)
    db.execute(delete(Participant).where(Participant.id == participant_id))
    db.flush()
    return {"participant_id": participant_id, **removed}
