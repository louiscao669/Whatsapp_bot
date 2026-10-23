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

Test participants are MCQ-only by default (``dashboard_preferences["question_forms"]``,
see ``eten_shared.question_forms``); pass ``question_forms="all"`` to include open items.

A test participant can also be limited to one quality dimension -- ``adequacy``
(clean + omission + mistranslation) or ``fluency`` (clean + grammar30 + wbw) -- see
``eten_shared.experiment_plan.QUALITY_DIMENSIONS``. Only that dimension's plan cells
are written; the choice is stored as ``dashboard_preferences["quality_dimensions"]``.

Finer still, ``conditions`` picks individual conditions (e.g. ``["clean",
"mistranslation15", "mistranslation30"]``); it overrides ``quality_dimensions`` and is
stored as ``dashboard_preferences["conditions"]``.
"""

from sqlalchemy import delete, func, select

from eten_shared.experiment_plan import (
    CONDITION_LABELS,
    DEFAULT_QA_SET,
    PARTICIPANT_CONDITIONS_KEY,
    PARTICIPANT_QUALITY_DIMENSIONS_KEY,
    QA_SETS,
    QUALITY_DIMENSIONS,
    SLOTS,
    TEST_PARTICIPANT_KEY,
    ExperimentPlanError,
    available_qa_sets,
    dimension_conditions,
    is_test_participant,
    next_test_block_index,
    parse_conditions,
    parse_quality_dimensions,
    qa_set_wh_type_counts,
    write_participant_plan,
)
from eten_shared.question_forms import (
    PARTICIPANT_QUESTION_FORMS_KEY,
    QUESTION_FORMS,
    TEST_PARTICIPANT_DEFAULT_FORMS,
    parse_question_forms,
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
        "question_forms": list(QUESTION_FORMS),
        "default_question_forms": sorted(TEST_PARTICIPANT_DEFAULT_FORMS),
        "quality_dimensions": {k: list(v) for k, v in QUALITY_DIMENSIONS.items()},
        "conditions": [{"key": k, "label": v} for k, v in CONDITION_LABELS.items()],
        "qa_sets": [
            {
                "key": key,
                "label": label,
                "windows": count,
                "wh_counts": {t: n for t, n in qa_set_wh_type_counts(db, key).items()
                              if t in WH_TYPES},
                "mcq_wh_counts": {t: n for t, n in qa_set_wh_type_counts(
                                      db, key, question_types={"mcq"}).items()
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


def _parse_question_forms(value):
    """None/"" -> the test default (MCQ-only); "all" / ["mcq","open"] -> both."""
    try:
        forms = parse_question_forms(value)
    except ValueError as exc:
        raise TestParticipantError(f"Question forms: {exc}") from None
    return sorted(forms or TEST_PARTICIPANT_DEFAULT_FORMS)


def _parse_quality_dimensions(value):
    try:
        return parse_quality_dimensions(value)
    except ValueError as exc:
        raise TestParticipantError(f"Quality dimension: {exc}") from None


def _parse_conditions(value):
    try:
        return parse_conditions(value)
    except ValueError as exc:
        raise TestParticipantError(f"Conditions: {exc}") from None


def create_test_participant(db, *, display_name=None, language=None, build_plan=True,
                            qa_set=None, wh_types=None, question_forms=None,
                            quality_dimensions=None, conditions=None):
    """Stage a flagged participant (+ plan). Caller commits; rollback on error.

    ``wh_types`` (e.g. ["why"]) restricts the participant to questions whose stem asks
    those interrogatives. Plan cells whose window group holds no such question are
    skipped at serving time, so the participant sees fewer than 8 conditions.

    ``quality_dimensions`` (["adequacy"] or ["fluency"]; none or both = all) keeps only
    that dimension's plan cells. ``conditions`` (e.g. ["clean", "mistranslation30"])
    picks individual conditions instead and overrides ``quality_dimensions``; choosing
    every condition, or none, means the full plan.

    ``question_forms`` defaults to MCQ-only; "all" (or ["mcq", "open"]) serves both.
    The choice is always stored explicitly, so later changes to the default do not
    change an existing participant.
    """

    qa_set = (qa_set or DEFAULT_QA_SET).strip()
    if qa_set not in QA_SETS:
        raise TestParticipantError(f"Unknown question set '{qa_set}'")
    wh_list = _parse_wh_types(wh_types)
    form_list = _parse_question_forms(question_forms)
    if wh_list and not build_plan:
        raise TestParticipantError("A question-type restriction needs a pilot plan")
    dim_list = _parse_quality_dimensions(quality_dimensions)
    if set(dim_list) == set(QUALITY_DIMENSIONS):
        dim_list = []  # both ticked = the full plan
    if dim_list and not build_plan:
        raise TestParticipantError("A quality-dimension restriction needs a pilot plan")
    cond_list = _parse_conditions(conditions)
    if cond_list:
        dim_list = []  # explicit conditions win over the dimension shortcut
    elif dim_list:
        cond_list = [c for c in dict.fromkeys(SLOTS) if c in dimension_conditions(dim_list)]
    if set(cond_list) == set(SLOTS):
        cond_list = []  # every condition = the full plan
    if cond_list and not build_plan:
        raise TestParticipantError("A condition restriction needs a pilot plan")

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
            **({PARTICIPANT_QUALITY_DIMENSIONS_KEY: dim_list} if dim_list else {}),
            **({PARTICIPANT_CONDITIONS_KEY: cond_list} if cond_list else {}),
            PARTICIPANT_QUESTION_FORMS_KEY: form_list,
        },
    )
    db.add(participant)
    db.flush()

    plan = []
    if build_plan:
        try:
            cells = write_participant_plan(
                db, participant, block_index, language_code, qa_set=qa_set,
                conditions=set(cond_list) or None,
            )
        except ExperimentPlanError as exc:
            raise TestParticipantError(f"Could not build the pilot plan: {exc}") from exc
        plan = [
            {"sequence_index": seq, "group": chapter, "condition": condition}
            for chapter, condition, seq in sorted(cells, key=lambda c: c[2])
        ]

    wh_question_count = None
    if wh_list:
        counts = qa_set_wh_type_counts(db, qa_set, question_types=set(form_list))
        wh_question_count = sum(counts[t] for t in wh_list)
        if not wh_question_count:
            raise TestParticipantError(
                f"'{qa_set}' has no {'/'.join(wh_list)} questions imported"
                f" (in {'/'.join(form_list)} form)"
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
        "question_forms": form_list,
        "quality_dimensions": dim_list,
        "conditions": cond_list,
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
