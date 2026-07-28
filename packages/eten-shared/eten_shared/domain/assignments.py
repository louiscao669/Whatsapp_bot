"""Participant assignment DB logic shared by the message bot and platform."""

import os
import re
import hashlib
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from eten_shared.domain.batch_schedules import cancel_pending_next_batch_schedules
from eten_shared.domain.batch_size_nudges import clamp_batch_size
from eten_shared.domain.qa_eligibility import qa_item_is_assignable
from eten_shared.question_discovery import get_qa_item_distribution_metrics
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    ExperimentPassageVerse,
    Participant,
    ParticipantEvent,
    ParticipantSession,
    PassageTranslation,
    PassageVerse,
    QAItem,
    SessionState,
    new_id,
    utc_now,
)
from eten_shared.languages import canonical_language_code
from eten_shared.recordings import (
    get_latest_question_recording,
    participant_language_code,
    participant_question_audio_satisfied,
    question_recording_playback_url,
)



def record_participant_event(db: Session, participant, event_type, metadata=None, *, source="workflow"):
    event = ParticipantEvent(
        participant_id=participant.id,
        event_type=event_type,
        source=source,
        event_metadata=metadata or {},
    )
    db.add(event)
    return event


@dataclass
class AssignmentPrompt:
    assignment_id: str
    qa_item_id: str
    audio_url: Optional[str]
    question_text: str
    passage_reference: Optional[str] = None
    passage_text: Optional[str] = None
    question_type: str = "open"
    mcq_choices: tuple = ()


class AssignmentAssignError(Exception):
    pass


def automatic_assignment_enabled() -> bool:
    """Return whether automatic QA selection is enabled for this deployment."""
    return os.getenv("ENABLE_AUTOMATIC_ASSIGNMENT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def experiment_assignment_enabled() -> bool:
    """Return whether DESIGNED (Latin-square) assignment is enabled for this deployment.

    Opt-in flag for the human pilot only; when true, callers should route through
    ``question_discovery.experiment_selection.select_next_experiment_cell_item`` instead
    of the coverage-optimizing ``select_next_qa_item``. Defaults off so the production
    coverage path is unaffected. See DESIGNED_ASSIGNMENT_EXTENSION_2026-07-20.md §6.
    """
    return os.getenv("ENABLE_EXPERIMENT_ASSIGNMENT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def try_complete_assignment(db: Session, assignment) -> bool:
    """Atomically mark an assignment completed; first commit wins.

    Guards against the same assignment being answered simultaneously on two
    surfaces (dashboard + messenger). Returns True when THIS caller completed
    the assignment, False when another writer got there first.
    """

    now = utc_now()
    result = db.execute(
        update(Assignment)
        .where(
            Assignment.id == assignment.id,
            Assignment.status != AssignmentStatus.COMPLETED.value,
        )
        .values(
            status=AssignmentStatus.COMPLETED.value,
            completed_at=now,
            attempt_count=Assignment.attempt_count + 1,
        )
    )
    if result.rowcount == 0:
        db.expire(assignment)
        return False

    # Refresh the in-session object so callers see the completed state.
    assignment.status = AssignmentStatus.COMPLETED.value
    assignment.completed_at = now
    return True


def get_or_create_participant_session(db: Session, participant):
    participant_session = db.scalars(
        select(ParticipantSession).where(
            ParticipantSession.participant_id == participant.id
        )
    ).first()

    if participant_session is None:
        participant_session = ParticipantSession(
            participant_id=participant.id,
            state=SessionState.ONBOARDING.value,
        )
        db.add(participant_session)
        db.flush()

    return participant_session


def get_incomplete_assignment(db: Session, participant, batch_id=None):
    statement = (
        select(Assignment)
        .where(
            Assignment.participant_id == participant.id,
            Assignment.status == AssignmentStatus.ASSIGNED.value,
        )
        .order_by(Assignment.assigned_at, Assignment.id)
    )
    if batch_id:
        in_batch = db.scalars(statement.where(Assignment.batch_id == batch_id)).first()
        if in_batch:
            return in_batch

    return db.scalars(statement).first()


def get_chained_assignment(db: Session, participant, assignment_id):
    """Resolve one prepared chain node without scanning the assignment queue."""

    if not assignment_id:
        return None
    assignment = db.get(Assignment, assignment_id)
    if (
        assignment
        and assignment.participant_id == participant.id
        and assignment.status == AssignmentStatus.ASSIGNED.value
    ):
        return assignment
    return None


PASSAGE_CONTEXT_WINDOW = 2
PASSAGE_DELIVERY_VERSE_COUNT = 3

# These source references point one verse before the verse containing the
# answer. Keep the source reference intact for traceability, but constrain the
# randomized window so both verses are delivered.
ANSWER_VERSE_OFFSETS = {
    "uw-174342": 1,
    "uw-174343": 1,
    "uw-174344": 1,
    "uw-174404": 1,
}

_QA_VERSE_REFERENCE = re.compile(
    r"^(?:.+?\s+)?(?P<chapter>\d+):(?P<verse>\d+)(?:\(#(?P<occurrence>\d+)\))?",
    re.IGNORECASE,
)


def _qa_verse_location(qa_item):
    match = _QA_VERSE_REFERENCE.match(
        str(qa_item.passage_reference or qa_item.passage_id or "").strip()
    )
    if not match:
        return None
    chapter = int(match.group("chapter"))
    # ``(#2)`` identifies a second QA item for the same source verse; it does
    # not identify a duplicate PassageVerse row.
    return chapter, match.group("verse")


def _window_random_value(qa_item):
    stable_key = str(getattr(qa_item, "id", "") or qa_item.passage_reference or "")
    return int.from_bytes(hashlib.sha256(stable_key.encode("utf-8")).digest()[:8], "big")


def _answer_verse_offset(qa_item):
    item_id = str(getattr(qa_item, "id", "") or "")
    item_stem = item_id.rsplit("-", 1)[0]
    return ANSWER_VERSE_OFFSETS.get(item_stem, 0)


def select_three_verse_window(verses, qa_item):
    """Choose a stable pseudo-random three-verse window for one QA item.

    The referenced verse is distributed among the first, middle, and last
    positions. Known off-by-one source references are restricted to windows
    that also contain the actual answer verse.
    """

    verses = list(verses or [])
    if not verses:
        return []
    location = _qa_verse_location(qa_item)
    if not location:
        return []
    _, target_number = location
    target_index = next(
        (index for index, verse in enumerate(verses) if verse.verse_number == target_number),
        None,
    )
    if target_index is None:
        return []

    window_size = min(PASSAGE_DELIVERY_VERSE_COUNT, len(verses))
    max_start = len(verses) - window_size
    answer_offset = _answer_verse_offset(qa_item)
    answer_index = target_index + answer_offset
    valid_starts = [
        start
        for start in range(max_start + 1)
        if start <= target_index < start + window_size
        and start <= answer_index < start + window_size
    ]
    if not valid_starts:
        return []

    random_value = _window_random_value(qa_item)
    if answer_offset:
        start = valid_starts[random_value % len(valid_starts)]
    else:
        desired_position = random_value % window_size
        desired_start = target_index - desired_position
        start = min(valid_starts, key=lambda candidate: (abs(candidate - desired_start), candidate))
    return verses[start : start + window_size]


def experiment_passage_assignment_kwargs(db: Session, experiment_passage, qa_item):
    """Build the verse linkage for one designed-experiment assignment.

    The QA reference identifies the target verse within the condition-specific
    ExperimentPassageVerse rows. The assignment stores that verse and a small
    context snapshot. Older experiment rows without verse children safely fall
    back to their whole-passage snapshot.
    """

    fallback = {"passage_text": experiment_passage.passage_text}
    location = _qa_verse_location(qa_item)
    if not location:
        return fallback

    chapter, stored_number = location
    target = db.scalar(
        select(ExperimentPassageVerse).where(
            ExperimentPassageVerse.experiment_passage_id == experiment_passage.id,
            ExperimentPassageVerse.verse_number == stored_number,
        )
    )
    if target is None:
        return fallback

    chapter_verses = db.scalars(
        select(ExperimentPassageVerse)
        .where(
            ExperimentPassageVerse.experiment_passage_id == experiment_passage.id,
        )
        .order_by(ExperimentPassageVerse.position)
    ).all()
    verses = select_three_verse_window(chapter_verses, qa_item)
    if not verses:
        return fallback

    return {
        "passage_chapter_number": chapter,
        "passage_verse_numbers": [verse.verse_number for verse in verses],
        "passage_text": " ".join(
            verse.text.strip() for verse in verses if verse.text and verse.text.strip()
        ),
    }


def passage_translation_assignment_kwargs(db: Session, translation, qa_item):
    """Build a randomized three-verse assignment snapshot from a translation."""

    location = _qa_verse_location(qa_item)
    if not location:
        return {}
    chapter, _ = location
    chapter_verses = db.scalars(
        select(PassageVerse)
        .where(
            PassageVerse.translation_id == translation.id,
            PassageVerse.chapter_number == chapter,
        )
        .order_by(PassageVerse.position)
    ).all()
    verses = select_three_verse_window(chapter_verses, qa_item)
    if not verses:
        return {}
    return {
        "passage_translation_id": translation.id,
        "passage_chapter_number": chapter,
        "passage_verse_numbers": [verse.verse_number for verse in verses],
        "passage_text": " ".join(
            verse.text.strip() for verse in verses if verse.text and verse.text.strip()
        ),
    }


def automatic_passage_assignment_kwargs(db: Session, participant, qa_item):
    """Resolve the deterministic production translation for an automatic assignment."""

    location = _qa_verse_location(qa_item)
    language = canonical_language_code(getattr(participant, "target_language", None))
    if not location or not language:
        return {}
    chapter, target_number = location
    translation = db.scalars(
        select(PassageTranslation)
        .join(PassageVerse)
        .where(
            PassageTranslation.language == language,
            PassageVerse.chapter_number == chapter,
            PassageVerse.verse_number == target_number,
        )
        .distinct()
        .order_by(PassageTranslation.name, PassageTranslation.created_at, PassageTranslation.id)
    ).first()
    if not translation:
        return {}
    return passage_translation_assignment_kwargs(db, translation, qa_item)


def surrounding_passage_text(db: Session, assignment, window: int = PASSAGE_CONTEXT_WINDOW):
    """Return the assignment's exact passage snapshot as a flowing paragraph.

    New assignments store their randomized three-verse window in
    ``passage_verse_numbers``. Keeping selection at assignment creation makes
    Telegram and dashboard rendering identical and preserves historical
    assignments as delivered. ``window`` remains for caller compatibility.
    """

    translation_id = getattr(assignment, "passage_translation_id", None)
    verse_numbers = list(getattr(assignment, "passage_verse_numbers", None) or [])
    if not translation_id or not verse_numbers:
        return None

    verses = db.scalars(
        select(PassageVerse)
        .where(
            PassageVerse.translation_id == translation_id,
            PassageVerse.verse_number.in_(verse_numbers),
        )
        .order_by(PassageVerse.position)
    ).all()
    texts = [verse.text.strip() for verse in verses if verse.text and verse.text.strip()]
    if not texts:
        return None
    return " ".join(texts)


def build_assignment_prompt(db: Session, assignment, qa_item, participant):
    language = participant_language_code(participant)
    recording = get_latest_question_recording(db, qa_item.id, language)
    audio_url = question_recording_playback_url(recording) or qa_item.audio_url
    return AssignmentPrompt(
        assignment_id=assignment.id,
        qa_item_id=qa_item.id,
        audio_url=audio_url,
        question_text=qa_item.question_text,
        passage_reference=qa_item.passage_reference,
        # Prepared chain nodes already contain the exact immutable passage
        # snapshot. Avoid another verse-table query on the answer fast path.
        passage_text=assignment.passage_text
        or surrounding_passage_text(db, assignment)
        or qa_item.passage_text,
        question_type=qa_item.question_type or "open",
        mcq_choices=tuple(qa_item.mcq_choices or ()),
    )


def resume_incomplete_assignment(db: Session, participant, participant_session, assignment):
    qa_item = db.get(QAItem, assignment.qa_item_id)
    if not qa_item:
        return None

    participant_session.current_assignment_id = assignment.id
    participant_session.current_batch_id = assignment.batch_id
    participant_session.state = SessionState.AWAITING_RESPONSE.value
    return build_assignment_prompt(db, assignment, qa_item, participant)


def get_preferred_batch_size(participant):
    size = clamp_batch_size(participant.preferred_batch_size)
    if participant.preferred_batch_size != size:
        participant.preferred_batch_size = size
    return size


def count_completed_assignments_in_batch(db: Session, participant, batch_id):
    if not batch_id:
        return 0

    return len(
        db.scalars(
            select(Assignment).where(
                Assignment.participant_id == participant.id,
                Assignment.batch_id == batch_id,
                Assignment.status == AssignmentStatus.COMPLETED.value,
            )
        ).all()
    )


def complete_current_batch_if_needed(db: Session, participant, participant_session):
    batch_id = participant_session.current_batch_id
    completed_count = count_completed_assignments_in_batch(db, participant, batch_id)
    preferred_batch_size = get_preferred_batch_size(participant)

    if not batch_id or completed_count < preferred_batch_size:
        return False, completed_count

    participant_session.current_batch_id = None
    participant_session.current_assignment_id = None
    participant_session.state = SessionState.IDLE.value
    record_participant_event(
        db,
        participant,
        "batch_completed",
        {
            "batch_id": batch_id,
            "completed_count": completed_count,
            "preferred_batch_size": preferred_batch_size,
        },
    )
    return True, completed_count


def create_assignment_for_qa_item(
    db: Session,
    participant,
    participant_session,
    qa_item,
    completed_batch_size=0,
    assignment_source="auto",
    experiment_cell_id=None,
    passage_text=None,
    passage_translation_id=None,
    passage_chapter_number=None,
    passage_verse_numbers=None,
):
    if (
        not experiment_cell_id
        and not passage_text
        and not passage_translation_id
        and not passage_verse_numbers
    ):
        passage_kwargs = automatic_passage_assignment_kwargs(db, participant, qa_item)
        passage_text = passage_kwargs.get("passage_text")
        passage_translation_id = passage_kwargs.get("passage_translation_id")
        passage_chapter_number = passage_kwargs.get("passage_chapter_number")
        passage_verse_numbers = passage_kwargs.get("passage_verse_numbers")

    batch_id = participant_session.current_batch_id or new_id()
    previous_assignment = db.get(
        Assignment, participant_session.current_assignment_id
    ) if participant_session.current_assignment_id else None
    assignment = Assignment(
        id=new_id(),
        participant_id=participant.id,
        qa_item_id=qa_item.id,
        batch_id=batch_id,
        status=AssignmentStatus.ASSIGNED.value,
        assigned_at=utc_now(),
        experiment_cell_id=experiment_cell_id,
        passage_translation_id=passage_translation_id,
        passage_chapter_number=passage_chapter_number,
        passage_verse_numbers=list(passage_verse_numbers or []),
        # Designed assignment: the participant must read the CONDITION's variant
        # passage, not the shared QAItem text. build_assignment_prompt prefers
        # assignment.passage_text, so stamp it here. None => production behavior.
        passage_text=passage_text,
    )
    db.add(assignment)
    db.flush()

    if previous_assignment and not previous_assignment.next_assignment_id:
        previous_assignment.next_assignment_id = assignment.id

    participant_session.current_assignment_id = assignment.id
    participant_session.current_batch_id = batch_id
    participant_session.state = SessionState.AWAITING_RESPONSE.value
    participant_session.last_prompt_sent_at = utc_now()

    record_participant_event(
        db,
        participant,
        "assignment_created",
        {
            "assignment_id": assignment.id,
            "qa_item_id": qa_item.id,
            "batch_id": batch_id,
            "passage_id": qa_item.passage_id,
            "completed_batch_size": completed_batch_size,
            "preferred_batch_size": get_preferred_batch_size(participant),
            "distribution_metrics": get_qa_item_distribution_metrics(db, qa_item),
            "assignment_source": assignment_source,
            "experiment_cell_id": experiment_cell_id,
        },
    )

    return build_assignment_prompt(db, assignment, qa_item, participant)


def assign_qa_item_to_participant(db: Session, participant, participant_session, qa_item):
    cancel_pending_next_batch_schedules(
        db,
        participant.id,
        reason="Manual assignment superseded scheduled next batch",
    )

    if participant_session.state not in (
        SessionState.IDLE.value,
        SessionState.ONBOARDING.value,
    ):
        raise AssignmentAssignError(
            "Participant must be idle or onboarding before a new question can be assigned "
            f"(current state: {participant_session.state})."
        )

    batch_completed, completed_batch_size = complete_current_batch_if_needed(
        db, participant, participant_session
    )
    if batch_completed:
        raise AssignmentAssignError(
            "Participant just completed a batch. Submit assign again to give them this question."
        )

    if not qa_item.active:
        raise AssignmentAssignError("This question is inactive.")

    if not qa_item_is_assignable(qa_item):
        raise AssignmentAssignError(
            "This question was removed during QA review and cannot be assigned."
        )

    if not participant_question_audio_satisfied(db, qa_item.id, participant):
        language = participant_language_code(participant)
        raise AssignmentAssignError(
            f"No expert question recording for language '{language}'. "
            "Record the question at /record before assigning, or set "
            "REQUIRE_QUESTION_AUDIO=false to allow text-only questions."
        )

    existing_assignment = db.scalars(
        select(Assignment).where(
            Assignment.participant_id == participant.id,
            Assignment.qa_item_id == qa_item.id,
        )
    ).first()
    if existing_assignment:
        raise AssignmentAssignError(
            "This participant already has an assignment for this question."
        )

    if participant_session.current_assignment_id:
        current_assignment = db.get(Assignment, participant_session.current_assignment_id)
        if (
            current_assignment
            and current_assignment.status != AssignmentStatus.COMPLETED.value
        ):
            raise AssignmentAssignError(
                "Participant already has an open assignment. Wait for their response first."
            )

    prompt = create_assignment_for_qa_item(
        db,
        participant,
        participant_session,
        qa_item,
        completed_batch_size=completed_batch_size,
        assignment_source="admin",
    )
    return prompt
