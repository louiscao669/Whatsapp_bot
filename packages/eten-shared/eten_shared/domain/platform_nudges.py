"""Platform-engagement experiment: per-participant nudge-platform sequences.

Each participant carries `nudge_platform_sequence`, a list mapping batch
ordinal (0-based, in completion order) -> the platform their batch-ready
nudge should point at: "dashboard" or "messenger".

The experiment uses a 4-period crossover over 8 batches (period = 2 batches):
ABBA = dashboard, dashboard, messenger, messenger, messenger, messenger,
dashboard, dashboard; BAAB is the mirror. Participants without a sequence
fall back to messenger nudging (current behavior).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.models import Assignment, AssignmentStatus

PLATFORM_DASHBOARD = "dashboard"
PLATFORM_MESSENGER = "messenger"

DEFAULT_PERIOD_SIZE = 2
DEFAULT_NUM_PERIODS = 4

CROSSOVER_VARIANTS = {
    "ABBA": ("A", "B", "B", "A"),
    "BAAB": ("B", "A", "A", "B"),
}


def sequence_for_variant(
    variant: str,
    *,
    period_size: int = DEFAULT_PERIOD_SIZE,
    num_periods: int = DEFAULT_NUM_PERIODS,
):
    """Expand a crossover variant name into a per-batch platform list.

    A = dashboard-nudged, B = messenger-nudged.
    """

    periods = CROSSOVER_VARIANTS.get((variant or "").upper())
    if not periods:
        raise ValueError(
            f"Unknown crossover variant {variant!r}; expected one of "
            f"{sorted(CROSSOVER_VARIANTS)}"
        )
    sequence = []
    for label in periods[:num_periods]:
        platform = PLATFORM_DASHBOARD if label == "A" else PLATFORM_MESSENGER
        sequence.extend([platform] * period_size)
    return sequence


def assign_nudge_platform_sequence(participant, variant: str, **kwargs):
    sequence = sequence_for_variant(variant, **kwargs)
    participant.nudge_platform_sequence = sequence
    return sequence


def completed_batch_count(db: Session, participant) -> int:
    """Number of distinct batches this participant has fully left behind.

    Counts distinct batch_ids among COMPLETED assignments that have no
    remaining non-completed sibling (i.e. finished batches).
    """

    rows = db.execute(
        select(Assignment.batch_id, Assignment.status).where(
            Assignment.participant_id == participant.id,
            Assignment.batch_id.is_not(None),
        )
    ).all()
    completed = {b for b, s in rows if s == AssignmentStatus.COMPLETED.value}
    open_ = {b for b, s in rows if s != AssignmentStatus.COMPLETED.value}
    return len(completed - open_)


def nudge_platform_for_next_batch(db: Session, participant) -> str:
    """Platform the participant's NEXT batch nudge should point at.

    Uses the number of finished batches as the ordinal into the sequence.
    Falls back to messenger when no sequence is assigned or the sequence is
    exhausted (post-experiment behavior).
    """

    sequence = list(participant.nudge_platform_sequence or [])
    if not sequence:
        return PLATFORM_MESSENGER
    ordinal = completed_batch_count(db, participant)
    if ordinal >= len(sequence):
        return PLATFORM_MESSENGER
    platform = sequence[ordinal]
    return (
        PLATFORM_DASHBOARD
        if platform == PLATFORM_DASHBOARD
        else PLATFORM_MESSENGER
    )
