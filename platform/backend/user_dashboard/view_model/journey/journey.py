def journey_view(history_summary, streak=None):
    journey_chapters = list((history_summary or {}).get("journey_chapters") or [])
    if journey_chapters:
        return {
            "chapters": journey_chapters,
            "summary": _journey_summary(history_summary, journey_chapters, streak),
        }

    completed_batches = int((history_summary or {}).get("total_batches_answered") or 0)
    fallback = {
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
    fallback["summary"] = _journey_summary(history_summary, fallback["chapters"], streak)
    return fallback


def _journey_summary(history_summary, chapters, streak=None):
    target = _active_target(chapters)
    batches = [batch for chapter in chapters for batch in chapter.get("batches", [])]
    completed_batches = (
        sum(1 for batch in batches if batch.get("status") == "complete")
        if batches
        else int((history_summary or {}).get("total_batches_answered") or 0)
    )
    current_batch = target["batch"]
    current_question = _target_question(current_batch)
    return {
        "current_path": _batch_label(current_batch, target["batch_index"]),
        "batches_done": completed_batches,
        "current_chapter": _question_chapter_label(
            current_question,
            target["chapter"],
            target["chapter_index"],
        ),
        "next_reward": _next_reward_label(streak),
        "overall_progress": _overall_progress(chapters),
        "active_chapter_index": target["chapter_index"],
        "active_batch_index": target["batch_index"],
    }


def _active_target(chapters):
    for chapter_index, chapter in enumerate(chapters):
        batches = list(chapter.get("batches") or [])
        if not batches and chapter.get("status") != "complete":
            return {
                "chapter": chapter,
                "chapter_index": chapter_index,
                "batch": None,
                "batch_index": 0,
            }
        for batch_index, batch in enumerate(batches):
            if batch.get("status") != "complete":
                return {
                    "chapter": chapter,
                    "chapter_index": chapter_index,
                    "batch": batch,
                    "batch_index": batch_index,
                }

    chapter_index = max(0, len(chapters) - 1)
    chapter = chapters[chapter_index] if chapters else {}
    batches = list(chapter.get("batches") or [])
    batch_index = max(0, len(batches) - 1)
    return {
        "chapter": chapter,
        "chapter_index": chapter_index,
        "batch": batches[batch_index] if batches else None,
        "batch_index": batch_index,
    }


def _batch_label(batch, index):
    return (batch or {}).get("label") or f"Batch {index + 1}"


def _chapter_label(chapter, index):
    if chapter and chapter.get("chapter"):
        return f"Chapter {chapter['chapter']}"
    title = str((chapter or {}).get("title") or "")
    digits = "".join(character for character in title if character.isdigit())
    return f"Chapter {digits or index + 1}"


def _target_question(batch):
    questions = list((batch or {}).get("questions") or [])
    for question in questions:
        if question.get("status") == "current":
            return question
    for question in questions:
        if question.get("status") == "complete":
            continue
        return question
    return questions[-1] if questions else {}


def _question_chapter_label(question, fallback_chapter, fallback_index):
    if question and question.get("chapter_label"):
        return question["chapter_label"]
    if question and question.get("chapter"):
        return f"Chapter {question['chapter']}"
    return _chapter_label(fallback_chapter, fallback_index)


def _next_reward_label(streak):
    milestone = dict((streak or {}).get("next_milestone") or {})
    return (
        milestone.get("title")
        or milestone.get("reward_summary")
        or "Daily streak"
    )


def _overall_progress(chapters):
    batches = [batch for chapter in chapters for batch in chapter.get("batches", [])]
    if batches:
        questions = [
            question
            for batch in batches
            for question in batch.get("questions", [])
        ]
        if not questions:
            return 0
        completed = sum(1 for question in questions if question.get("status") == "complete")
        return completed / len(questions)
    if not chapters:
        return 0
    return sum(float(chapter.get("progress") or 0) for chapter in chapters) / len(chapters)
