def journey_view(history_summary):
    completed_batches = int((history_summary or {}).get("total_batches_answered") or 0)
    return {
        "chapters": [
            {
                "title": "Luke 1",
                "status": "complete" if completed_batches > 0 else "continue",
                "progress": 1 if completed_batches > 0 else 0.4,
            },
            {
                "title": "Luke 2",
                "status": "continue",
                "progress": 0.2 if completed_batches > 0 else 0,
            },
        ]
    }
