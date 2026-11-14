"""Provision one real reader and their full Chinese Sol study plan in one transaction."""

from uuid import UUID

from sqlalchemy import select

from eten_shared.domain.assignments import experiment_assignment_enabled
from eten_shared.experiment_plan import (
    LANGUAGE, SOL_SCRATCH_SET, SLOTS, ExperimentPlanError, is_test_participant,
    scratch_rotation_counts, write_next_scratch_plan,
)
from eten_shared.models import ExperimentPlanCell, Participant
from eten_shared.question_discovery.experiment_selection import participant_wh_filter, remaining_cell_items
from eten_shared.question_forms import participant_question_forms


def enroll_study_participant(db, request_id, label):
    try:
        pid = UUID(str(request_id))
        if pid.version != 4:
            raise ValueError
    except ValueError:
        raise ValueError("A valid enrollment request ID is required.") from None
    if not isinstance(label, str) or len(label.strip()) > 200:
        raise ValueError("Use a participant label of at most 200 characters.")
    pid = str(pid)
    label = label.strip()
    counts = scratch_rotation_counts(db, for_update=True)
    participant = db.get(Participant, pid)
    created = participant is None
    if created:
        if not experiment_assignment_enabled():
            raise ExperimentPlanError("Enable ENABLE_EXPERIMENT_ASSIGNMENT on the platform to serve study plans.")
        participant = Participant(id=pid, target_language=LANGUAGE, consented=False)
        db.add(participant)
        db.flush()
        write_next_scratch_plan(db, participant, counts)
        # Use the same eligibility rules as the web pilot, including audio and
        # stem filters. Roll back the entire enrollment if the bank is incomplete.
        cells = db.scalars(select(ExperimentPlanCell).where(ExperimentPlanCell.participant_id == pid))
        strict_keep = participant_wh_filter(participant)
        form_keep = participant_question_forms(participant)
        group_sizes = [
            len(remaining_cell_items(db, cell, participant, set(), strict_keep, form_keep))
            for cell in cells
        ]
        if len(group_sizes) != len(SLOTS) or not all(group_sizes) or sum(group_sizes) != 66:
            raise ExperimentPlanError(
                f"The study can serve {sum(group_sizes)} of 66 questions. Check the Sol from-scratch "
                "bank and the question audio and type filters before enrolling."
            )
        number = participant.dashboard_preferences["study_enrollment_number"]
        participant.display_name = label or f"Study participant {number}"
        participant.dashboard_preferences = {**participant.dashboard_preferences, "study_web_enrollment": True}
    elif not (participant.dashboard_preferences or {}).get("study_web_enrollment") or is_test_participant(participant):
        raise ExperimentPlanError("This request ID is already in use.")
    prefs = participant.dashboard_preferences
    return {
        "participant_id": pid, "display_name": participant.display_name, "qa_set": SOL_SCRATCH_SET,
        "enrollment_number": prefs["study_enrollment_number"], "rotation": prefs["study_rotation"],
        "pilot_path": f"/pilot/{pid}",
    }, created
