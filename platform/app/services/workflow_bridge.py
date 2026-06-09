"""Platform bridge to shared participant assignment logic (no WhatsApp)."""

from eten_shared.domain.assignments import (
    AssignmentAssignError,
    assign_qa_item_to_participant,
    get_or_create_participant_session,
)

__all__ = [
    "AssignmentAssignError",
    "assign_qa_item_to_participant",
    "get_or_create_participant_session",
]
