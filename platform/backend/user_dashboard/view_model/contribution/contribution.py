SECONDS_SAVED_PER_QUESTION = 11 * 60


def contribution_view(history_summary, events):
    total_questions = int((history_summary or {}).get("total_questions_answered") or 0)
    contribution_count = sum(
        1
        for event in events or []
        if int(event.get("amount") or 0) > 0
    )
    saved_hours = round((total_questions * SECONDS_SAVED_PER_QUESTION) / 3600, 1)
    completion_score = min(1.0, total_questions / 50) if total_questions else 0
    return {
        "total_questions_answered": total_questions,
        "contribution_count": contribution_count,
        "total_translation_hours_saved": saved_hours,
        "completion_score": completion_score,
    }
