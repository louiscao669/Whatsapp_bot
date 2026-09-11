"""Dashboard journey services."""

from ._common import *  # noqa: F401,F403

def get_luke_chapter_activity(db, participant_id, chapter_count=24):
    from .serialization import _luke_chapter_from_reference

    rows = db.execute(
        select(QAItem.passage_reference, func.count(ParticipantResponse.id))
        .join(QAItem, QAItem.id == ParticipantResponse.qa_item_id)
        .where(ParticipantResponse.participant_id == participant_id)
        .group_by(QAItem.passage_reference)
    ).all()
    counts = {chapter: 0 for chapter in range(1, chapter_count + 1)}
    for passage_reference, response_count in rows:
        chapter = _luke_chapter_from_reference(passage_reference)
        if chapter in counts:
            counts[chapter] += int(response_count or 0)

    max_count = max(counts.values(), default=0)
    output = []
    for chapter, count in counts.items():
        if count <= 0:
            level = 0
        elif max_count <= 1:
            level = 1
        else:
            level = min(4, max(1, round((count / max_count) * 4)))
        output.append(
            {
                "book": "Luke",
                "chapter": chapter,
                "answered_questions": count,
                "level": level,
            }
        )
    return output


def get_luke_journey_chapters(db, participant_id):
    from .serialization import _luke_chapter_from_reference
    from .serialization import _serialize_dashboard_question
    from .serialization import _serialize_completed_question_review

    participant = db.get(Participant, participant_id)
    preferred_batch_size = max(int(getattr(participant, "preferred_batch_size", 3) or 3), 1)
    chest_reward_events = {
        event.source_event_id: event
        for event in db.scalars(
            select(ParticipantCurrencyEvent).where(
                ParticipantCurrencyEvent.participant_id == participant_id,
                ParticipantCurrencyEvent.reason == "batch_chest_reward",
                ParticipantCurrencyEvent.source_event_id.is_not(None),
            )
        ).all()
    }
    rows = db.execute(
        select(Assignment, QAItem)
        .join(QAItem, QAItem.id == Assignment.qa_item_id)
        .where(Assignment.participant_id == participant_id)
        .order_by(Assignment.assigned_at.asc(), Assignment.id.asc())
    ).all()
    batches = []
    batch_index = {}
    for assignment, qa_item in rows:
        chapter_number = _luke_chapter_from_reference(qa_item.passage_reference)
        if not chapter_number:
            continue
        batch_id = assignment.batch_id or f"single-{assignment.id}"
        batch = batch_index.get(batch_id)
        if not batch:
            batch = {
                "batch_id": batch_id,
                "label": f"Batch {len(batches) + 1}",
                "target_size": preferred_batch_size,
                "questions": [],
            }
            batch_index[batch_id] = batch
            batches.append(batch)
        complete = assignment.status == AssignmentStatus.COMPLETED.value
        terminal = assignment.status in {
            AssignmentStatus.COMPLETED.value,
            AssignmentStatus.SKIPPED.value,
            AssignmentStatus.EXPIRED.value,
        }
        question = {
            **_serialize_dashboard_question(
                db,
                participant,
                assignment,
                qa_item,
                question_index=len(batch["questions"]),
            ),
            "status": "complete" if terminal else "current",
            "timed_out": assignment.status == AssignmentStatus.EXPIRED.value,
        }
        if complete:
            question["review"] = _serialize_completed_question_review(
                db, participant, assignment, qa_item
            )
        batch["questions"].append(question)

    if not batches:
        return []

    completed_questions = 0
    total_questions = 0
    active_batch_index = None
    for index, batch in enumerate(batches):
        total_questions += len(batch["questions"])
        batch_completed = all(
            question["status"] == "complete" for question in batch["questions"]
        )
        if batch_completed:
            batch["status"] = "complete"
            completed_questions += len(batch["questions"])
        elif active_batch_index is None:
            active_batch_index = index
            batch["status"] = "active"
            batch["target_size"] = max(preferred_batch_size, len(batch["questions"]))
            found_current = False
            for question in batch["questions"]:
                if question["status"] == "complete":
                    completed_questions += 1
                elif not found_current:
                    question["status"] = "current"
                    found_current = True
                else:
                    question["status"] = "locked"
            while len(batch["questions"]) < batch["target_size"]:
                batch["questions"].append(
                    {
                        "assignment_id": None,
                        "qa_item_id": None,
                        "chapter": None,
                        "chapter_label": None,
                        "passage_reference": None,
                        "question": f"Question {len(batch['questions']) + 1}",
                        "status": "locked",
                        "placeholder": True,
                    }
                )
        else:
            batch["status"] = "locked"
            for question in batch["questions"]:
                if question["status"] != "complete":
                    question["status"] = "locked"
        reward_event = chest_reward_events.get(batch["batch_id"])
        batch["reward"] = {
            "type": "chest",
            "min": CHEST_REWARD_MIN,
            "max": CHEST_REWARD_MAX,
            "currency": "diamonds",
            "claimed": bool(reward_event),
            "claimable": batch["status"] == "complete" and not reward_event,
            "amount": reward_event.amount if reward_event else None,
        }
    if active_batch_index is None:
        active_batch_index = max(0, len(batches) - 1)

    return [
        {
            "title": "Question Path",
            "batches": batches,
            "progress": completed_questions / total_questions if total_questions else 0,
            "status": (
                "complete"
                if total_questions and completed_questions == total_questions
                else "continue"
            ),
            "current_batch_index": active_batch_index,
        }
    ]


