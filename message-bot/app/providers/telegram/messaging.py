from __future__ import annotations

from telegram.error import RetryAfter, TelegramError

from app.providers.whatsapp.schedule_policy import (
    BATCH_NEXT_START_NOW_REPLY,
    BATCH_NEXT_WAIT_REPLY,
    format_batch_next_assign_hour,
)
from eten_shared.domain.batch_size_nudges import (
    BATCH_SIZE_NUDGE_ACCEPT_REPLY,
    BATCH_SIZE_NUDGE_DECLINE_REPLY,
)
from eten_shared.mcq import (
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_TF,
    format_choices_for_display,
)


def assignment_prompt_text(prompt):
    parts = []
    if prompt.passage_reference:
        parts.append(f"Passage: {prompt.passage_reference}")

    question_type = (getattr(prompt, "question_type", None) or "open").strip().lower()
    if question_type in {QUESTION_TYPE_MCQ, QUESTION_TYPE_TF} and getattr(prompt, "mcq_choices", None):
        if prompt.audio_url:
            parts.append("Listen to the audio, then choose your answer:")
            parts.append(prompt.audio_url)
        elif question_type == QUESTION_TYPE_TF:
            parts.append("Choose your answer (reply A or B):")
        else:
            parts.append("Choose your answer (reply A, B, C, or D):")
        parts.append(prompt.question_text)
        parts.append(format_choices_for_display(list(prompt.mcq_choices), question_type))
        return "\n\n".join(parts)

    if prompt.audio_url:
        parts.append("Listen to the audio, then reply with your answer:")
        parts.append(prompt.audio_url)
    else:
        parts.append("Reply with your answer:")

    parts.append(prompt.question_text)
    return "\n\n".join(parts)


def batch_complete_message(completed_batch_size, currency_awards=(), currency_balance=None):
    question_label = "question" if completed_batch_size == 1 else "questions"
    message = (
        "Thanks, your answer was recorded. Batch complete: "
        f"you finished {completed_batch_size} {question_label}."
    )
    earned = sum(
        award.get("amount", 0)
        for award in currency_awards
        if award.get("amount", 0) > 0
    )
    if earned and currency_balance is not None:
        coin_label = "coin" if earned == 1 else "coins"
        message += f"\n\n+{earned} {coin_label} earned. Balance: {currency_balance}."
    return message


def badge_message(badge):
    return f"Badge earned: {badge['title']}\n{badge['description']}"


def next_batch_choice_message():
    return (
        "Would you like to start a new batch now, or wait until tomorrow at "
        f"{format_batch_next_assign_hour()}?\n\n"
        f"Reply `{BATCH_NEXT_START_NOW_REPLY}` to start now, or "
        f"`{BATCH_NEXT_WAIT_REPLY}` to wait."
    )


def batch_size_nudge_message(nudge):
    action_word = "increase" if nudge.action == "increase" else "reduce"
    if nudge.action == "increase":
        body = (
            "You've completed your batches within 24 hours for 3 days in a row. "
            f"Do you want to increase your next batch size to {nudge.proposed_size}?"
        )
    else:
        body = (
            "It looks like this batch size may be hard to finish within 24 hours. "
            f"Do you want to reduce your next batch size to {nudge.proposed_size}?"
        )
    return (
        f"{body}\n\n"
        f"Reply `{BATCH_SIZE_NUDGE_ACCEPT_REPLY}` to {action_word}, or "
        f"`{BATCH_SIZE_NUDGE_DECLINE_REPLY}` for not now."
    )


def no_assignment_message(response_recorded):
    if response_recorded:
        return "Thanks, your answer was recorded. No more questions are available right now."
    return "Thanks for checking in. No questions are available right now."


async def send_text(bot, chat_id, text):
    try:
        return await bot.send_message(chat_id=chat_id, text=text)
    except RetryAfter as exc:
        import asyncio

        await asyncio.sleep(exc.retry_after)
        return await send_text(bot, chat_id, text)


async def send_assignment_prompt(bot, chat_id, prompt):
    return await send_text(bot, chat_id, assignment_prompt_text(prompt))


async def send_workflow_result(bot, chat_id, workflow_result):
    for badge in workflow_result.awarded_badges:
        await send_text(bot, chat_id, badge_message(badge))

    if workflow_result.status_message:
        await send_text(bot, chat_id, workflow_result.status_message)
        return

    if workflow_result.batch_completed:
        await send_text(
            bot,
            chat_id,
            batch_complete_message(
                workflow_result.completed_batch_size,
                workflow_result.currency_awards,
                workflow_result.currency_balance,
            ),
        )
        if workflow_result.batch_size_nudge:
            await send_text(bot, chat_id, batch_size_nudge_message(workflow_result.batch_size_nudge))
        await send_text(bot, chat_id, next_batch_choice_message())

    if workflow_result.prompt:
        await send_assignment_prompt(bot, chat_id, workflow_result.prompt)
        return

    if workflow_result.batch_completed:
        return

    await send_text(
        bot,
        chat_id,
        no_assignment_message(response_recorded=bool(workflow_result.response_id)),
    )
