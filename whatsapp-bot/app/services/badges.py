from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from eten_shared.models import ParticipantBadge, ParticipantEvent


@dataclass(frozen=True)
class BadgeDefinition:
    badge_type: str
    title: str
    description: str
    completed_count_threshold: Optional[int] = None
    requires_batch_completed: bool = False


BADGE_DEFINITIONS = (
    BadgeDefinition(
        badge_type="first_response",
        title="First Answer",
        description="Submitted your first answer.",
        completed_count_threshold=1,
    ),
    BadgeDefinition(
        badge_type="completed_first_batch",
        title="First Batch Complete",
        description="Completed your first question batch.",
        requires_batch_completed=True,
    ),
    BadgeDefinition(
        badge_type="completed_5_questions",
        title="Five Questions",
        description="Completed 5 validation questions.",
        completed_count_threshold=5,
    ),
    BadgeDefinition(
        badge_type="completed_10_questions",
        title="Ten Questions",
        description="Completed 10 validation questions.",
        completed_count_threshold=10,
    ),
    BadgeDefinition(
        badge_type="completed_25_questions",
        title="Twenty-Five Questions",
        description="Completed 25 validation questions.",
        completed_count_threshold=25,
    ),
)


def get_existing_badge_types(db, participant):
    return set(
        db.scalars(
            select(ParticipantBadge.badge_type).where(
                ParticipantBadge.participant_id == participant.id
            )
        ).all()
    )


def badge_requirement_met(definition, participant, batch_completed=False):
    if definition.requires_batch_completed and not batch_completed:
        return False

    if definition.completed_count_threshold is not None:
        return participant.completed_count >= definition.completed_count_threshold

    return definition.requires_batch_completed and batch_completed


def award_badge(db, participant, definition):
    badge = ParticipantBadge(
        participant_id=participant.id,
        badge_type=definition.badge_type,
        title=definition.title,
        description=definition.description,
        badge_metadata={
            "completed_count": participant.completed_count,
        },
    )
    db.add(badge)
    db.flush()

    db.add(
        ParticipantEvent(
            participant_id=participant.id,
            event_type="badge_awarded",
            source="workflow",
            event_metadata={
                "badge_id": badge.id,
                "badge_type": badge.badge_type,
                "title": badge.title,
                "completed_count": participant.completed_count,
            },
        )
    )
    return badge


def evaluate_and_award_badges(db, participant, batch_completed=False):
    existing_badge_types = get_existing_badge_types(db, participant)
    awarded_badges = []

    for definition in BADGE_DEFINITIONS:
        if definition.badge_type in existing_badge_types:
            continue

        if not badge_requirement_met(definition, participant, batch_completed):
            continue

        badge = award_badge(db, participant, definition)
        awarded_badges.append(badge)
        existing_badge_types.add(definition.badge_type)

    return awarded_badges
