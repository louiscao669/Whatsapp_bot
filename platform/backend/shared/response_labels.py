"""Response labels shared by admin and participant-facing views."""

OPEN_RESPONSE_STATUS_LABELS = {
    "pending": "Pending",
    "yes (auto)": "Auto-correct",
    "no (auto)": "Auto-incorrect",
    "yes (expert)": "Expert-correct",
    "no (expert)": "Expert-incorrect",
}


def open_response_status_label(is_correct: str) -> str:
    value = (is_correct or "").strip().lower()
    return OPEN_RESPONSE_STATUS_LABELS.get(value, is_correct or "Unknown")


def format_choice_correctness_label(is_correct: str) -> str:
    value = (is_correct or "").strip().lower()
    if value.startswith("yes"):
        return "correct"
    return "incorrect"
