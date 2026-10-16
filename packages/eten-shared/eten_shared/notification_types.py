"""Outbox message types shared by producers and the message-bot worker."""

DASHBOARD_ANSWER_SYNCED_TYPE = "dashboard_answer_synced"
NEW_ASSIGNMENT_ASSIGNED_TYPE = "new_assignment_assigned"
ANSWER_LLM_SCORE_REQUESTED_TYPE = "answer_llm_score_requested"
ANSWER_POSTPROCESS_REQUESTED_TYPE = "answer_postprocess_requested"
MCQ_CHOICE_RESOLUTION_REQUESTED_TYPE = "mcq_choice_resolution_requested"

# Each scoring job belongs to a response and must survive later answers.
PER_RESPONSE_NOTIFICATION_TYPES = frozenset(
    {
        ANSWER_LLM_SCORE_REQUESTED_TYPE,
        ANSWER_POSTPROCESS_REQUESTED_TYPE,
        MCQ_CHOICE_RESOLUTION_REQUESTED_TYPE,
    }
)
