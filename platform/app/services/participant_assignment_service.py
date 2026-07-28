"""Admin-selected QA assignments with language-specific passage snapshots."""

import re

from sqlalchemy import select

from eten_shared.domain.qa_eligibility import qa_item_is_assignable
from eten_shared.domain.assignments import select_three_verse_window
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    OutboxNotification,
    OutboxStatus,
    Participant,
    ParticipantSession,
    PassageTranslation,
    PassageVerse,
    QAItem,
    SessionState,
    Reminder,
    ReminderStatus,
    new_id,
    utc_now,
)
from app.services.system_languages_service import canonical_language_code


class ParticipantAssignmentError(Exception):
    pass


# Cross-surface push: enqueued here, drained by the message-bot outbox poller,
# which delivers the freshly assigned question over the participant's messenger
# (Telegram/WhatsApp) so they don't have to message the bot first.
NEW_ASSIGNMENT_ASSIGNED_NOTIFICATION = "new_assignment_assigned"


def _enqueue_new_assignment_push(db, participant, assignment, assigned_count):
    """Queue a messenger push for a newly assigned (now-current) question.

    Supersedes any still-pending push of the same type for this participant so
    repeated admin assignments collapse into a single delivery.
    """

    stale = db.scalars(
        select(OutboxNotification).where(
            OutboxNotification.participant_id == participant.id,
            OutboxNotification.notification_type == NEW_ASSIGNMENT_ASSIGNED_NOTIFICATION,
            OutboxNotification.status == OutboxStatus.PENDING.value,
        )
    ).all()
    for notification in stale:
        notification.status = OutboxStatus.SUPERSEDED.value
        notification.failure_reason = "Superseded by a newer assignment"

    db.add(
        OutboxNotification(
            participant_id=participant.id,
            notification_type=NEW_ASSIGNMENT_ASSIGNED_NOTIFICATION,
            payload={
                "assignment_id": assignment.id,
                "batch_id": assignment.batch_id,
                "assigned_count": assigned_count,
            },
            status=OutboxStatus.PENDING.value,
        )
    )


# Accept both admin-authored references ("Luke 1:4") and pipeline references
# ("1:4" / "1:35(#2)"). QAItems are shared by regular and experiment flows,
# so a missing book prefix must not make an otherwise compatible verse vanish
# from the manual assignment screen.
_REFERENCE = re.compile(
    r"^(?:.+?\s+)?(?P<chapter>\d+):(?P<verse>\d+)", re.IGNORECASE
)


def parse_qa_chapter_verse(reference):
    match = _REFERENCE.match(str(reference or "").strip())
    if not match:
        return None
    return int(match.group("chapter")), int(match.group("verse"))


def qa_reference_sort_key(qa_item):
    reference = str(qa_item.passage_reference or qa_item.passage_id or "").strip()
    location = parse_qa_chapter_verse(reference)
    if not location:
        return (1, reference.casefold(), 0, 0, qa_item.id)
    chapter, verse = location
    book = reference.rsplit(None, 1)[0].casefold()
    return (0, book, chapter, verse, qa_item.id)


def _translation_options(db, language, chapter, target_verse):
    translations = db.scalars(
        select(PassageTranslation)
        .join(PassageVerse)
        .where(
            PassageTranslation.language == language,
            PassageVerse.chapter_number == chapter,
            PassageVerse.verse_number == str(target_verse),
        )
        .distinct()
        .order_by(PassageTranslation.name, PassageTranslation.created_at)
    ).all()
    return [
        {
            "id": translation.id,
            "name": translation.name,
            "label": translation.name or "Unnamed translation",
        }
        for translation in translations
    ]


def get_assignment_options(db, participant_id):
    participant = db.get(Participant, participant_id)
    if not participant:
        raise ParticipantAssignmentError("Participant not found")
    language = canonical_language_code(participant.target_language)
    if not language:
        raise ParticipantAssignmentError("Participant must have a language before assignment")

    assigned_ids = set(
        db.scalars(
            select(Assignment.qa_item_id).where(Assignment.participant_id == participant.id)
        ).all()
    )
    questions = []
    qa_items = sorted(db.scalars(select(QAItem)).all(), key=qa_reference_sort_key)
    for qa_item in qa_items:
        location = parse_qa_chapter_verse(qa_item.passage_reference or qa_item.passage_id)
        if qa_item.id in assigned_ids or not qa_item_is_assignable(qa_item) or not location:
            continue
        chapter, verse = location
        translations = _translation_options(db, language, chapter, verse)
        questions.append(
            {
                "id": qa_item.id,
                "passage": qa_item.passage_reference or qa_item.passage_id,
                "question": qa_item.question_text,
                "question_type": (qa_item.question_type or "open").strip().lower(),
                "chapter_number": chapter,
                "verse_number": verse,
                "translations": translations,
            }
        )
    return {"participant_language": language, "questions": questions}


def _passage_window(db, translation_id, chapter, target_verse, qa_item):
    verses = db.scalars(
        select(PassageVerse)
        .where(
            PassageVerse.translation_id == translation_id,
            PassageVerse.chapter_number == chapter,
        )
        .order_by(PassageVerse.position)
    ).all()
    selected = select_three_verse_window(verses, qa_item)
    if not selected:
        raise ParticipantAssignmentError(
            f"The selected translation does not contain chapter {chapter}, verse {target_verse}"
        )
    return selected


def assign_questions_with_passages(db, participant_id, selections):
    participant = db.get(Participant, participant_id)
    if not participant:
        raise ParticipantAssignmentError("Participant not found")
    if not isinstance(selections, list) or not selections:
        raise ParticipantAssignmentError("Select at least one question")

    open_assignment = db.scalar(
        select(Assignment).where(
            Assignment.participant_id == participant.id,
            Assignment.status != AssignmentStatus.COMPLETED.value,
        ).order_by(Assignment.assigned_at, Assignment.id)
    )

    language = canonical_language_code(participant.target_language)
    prepared = []
    seen_questions = set()
    for selection in selections:
        qa_item_id = str((selection or {}).get("qa_item_id") or "").strip()
        translation_id = str((selection or {}).get("translation_id") or "").strip()
        if not qa_item_id or not translation_id or qa_item_id in seen_questions:
            raise ParticipantAssignmentError("Each selected question needs one passage translation")
        seen_questions.add(qa_item_id)

        qa_item = db.get(QAItem, qa_item_id)
        translation = db.get(PassageTranslation, translation_id)
        location = parse_qa_chapter_verse(
            (qa_item.passage_reference or qa_item.passage_id) if qa_item else None
        )
        if not qa_item or not qa_item_is_assignable(qa_item) or not location:
            raise ParticipantAssignmentError("A selected question is unavailable for assignment")
        if not translation or translation.language != language:
            raise ParticipantAssignmentError("Passage translation must match participant language")
        chapter, target_verse = location
        verses = _passage_window(db, translation.id, chapter, target_verse, qa_item)
        prepared.append((qa_item, translation, chapter, verses))

    existing_assignments = db.scalars(
        select(Assignment)
        .where(Assignment.participant_id == participant.id)
        .order_by(Assignment.assigned_at, Assignment.id)
    ).all()
    batch_size = max(int(participant.preferred_batch_size or 3), 1)
    ordered_batch_ids = []
    for existing in existing_assignments:
        if existing.batch_id and existing.batch_id not in ordered_batch_ids:
            ordered_batch_ids.append(existing.batch_id)
    last_batch_id = ordered_batch_ids[-1] if ordered_batch_ids else None
    last_batch_count = (
        sum(1 for assignment in existing_assignments if assignment.batch_id == last_batch_id)
        if last_batch_id
        else batch_size
    )
    batch_id = last_batch_id if last_batch_count < batch_size else new_id()
    batch_count = last_batch_count if batch_id == last_batch_id else 0

    assignments = []
    for qa_item, translation, chapter, verses in prepared:
        if batch_count >= batch_size:
            batch_id = new_id()
            batch_count = 0
        assignment = Assignment(
            id=new_id(),
            participant_id=participant.id,
            qa_item_id=qa_item.id,
            passage_translation_id=translation.id,
            passage_chapter_number=chapter,
            passage_verse_numbers=[verse.verse_number for verse in verses],
            passage_text="\n".join(f"{verse.verse_number} {verse.text}" for verse in verses),
            batch_id=batch_id,
            status=AssignmentStatus.ASSIGNED.value,
            assigned_at=utc_now(),
        )
        db.add(assignment)
        assignments.append(assignment)
        batch_count += 1

    # Persist every new chain node before any existing/new assignment points
    # at it. With only scalar FK ids (no ORM relationship), SQLAlchemy may
    # otherwise emit the tail UPDATE before the target INSERT.
    db.flush()

    chain_tail = existing_assignments[-1] if existing_assignments else None
    if chain_tail and assignments and not chain_tail.next_assignment_id:
        chain_tail.next_assignment_id = assignments[0].id
    for current, following in zip(assignments, assignments[1:]):
        current.next_assignment_id = following.id
    db.flush()

    # An existing open assignment stays current. The new batch is persisted as
    # assigned and will be available after the participant reaches it.
    if open_assignment is None:
        participant_session = db.scalar(
            select(ParticipantSession).where(ParticipantSession.participant_id == participant.id)
        )
        if participant_session is None:
            participant_session = ParticipantSession(participant_id=participant.id)
            db.add(participant_session)
        participant_session.current_assignment_id = assignments[0].id
        participant_session.current_batch_id = assignments[0].batch_id
        participant_session.state = SessionState.AWAITING_RESPONSE.value
        participant_session.last_prompt_sent_at = utc_now()
        # These questions are immediately current, so push the first one to the
        # participant's messenger instead of waiting for them to say hello.
        _enqueue_new_assignment_push(db, participant, assignments[0], len(assignments))
    db.flush()
    return assignments


def skip_participant_assignment(db, participant_id, assignment_id):
    """Skip one unanswered chain node and splice its neighbors together."""

    participant = db.get(Participant, participant_id)
    if not participant:
        raise ParticipantAssignmentError("Participant not found")
    assignment = db.get(Assignment, assignment_id)
    if not assignment or assignment.participant_id != participant.id:
        raise ParticipantAssignmentError("Assignment not found")
    if assignment.status == AssignmentStatus.COMPLETED.value:
        raise ParticipantAssignmentError("Answered assignments cannot be skipped")
    if assignment.status == AssignmentStatus.SKIPPED.value:
        return assignment

    successor = db.get(Assignment, assignment.next_assignment_id) \
        if assignment.next_assignment_id else None
    while successor and successor.status == AssignmentStatus.SKIPPED.value:
        successor = db.get(Assignment, successor.next_assignment_id) \
            if successor.next_assignment_id else None
    if successor and successor.participant_id != participant.id:
        successor = None

    predecessors = db.scalars(
        select(Assignment).where(
            Assignment.participant_id == participant.id,
            Assignment.next_assignment_id == assignment.id,
        )
    ).all()
    for predecessor in predecessors:
        predecessor.next_assignment_id = successor.id if successor else None

    assignment.status = AssignmentStatus.SKIPPED.value
    assignment.completed_at = utc_now()
    assignment.next_assignment_id = None

    reminders = db.scalars(
        select(Reminder).where(
            Reminder.assignment_id == assignment.id,
            Reminder.status == ReminderStatus.PENDING.value,
        )
    ).all()
    for reminder in reminders:
        reminder.status = ReminderStatus.CANCELLED.value
        reminder.failure_reason = "Assignment skipped by administrator"
        reminder.updated_at = utc_now()

    pending_notifications = db.scalars(
        select(OutboxNotification).where(
            OutboxNotification.participant_id == participant.id,
            OutboxNotification.status == OutboxStatus.PENDING.value,
        )
    ).all()
    for notification in pending_notifications:
        payload = notification.payload or {}
        if payload.get("assignment_id") == assignment.id:
            notification.status = OutboxStatus.CANCELLED.value
            notification.failure_reason = "Assignment skipped by administrator"

    participant_session = db.scalar(
        select(ParticipantSession).where(
            ParticipantSession.participant_id == participant.id
        )
    )
    if participant_session and participant_session.current_assignment_id == assignment.id:
        participant_session.current_assignment_id = successor.id if successor else None
        participant_session.current_batch_id = successor.batch_id if successor else None
        participant_session.state = (
            SessionState.AWAITING_RESPONSE.value if successor else SessionState.IDLE.value
        )
        if successor:
            _enqueue_new_assignment_push(db, participant, successor, 1)

    db.flush()
    return assignment
