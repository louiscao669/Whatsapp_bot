from __future__ import annotations

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
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
    choice_letters_for_type,
    format_choices_for_display,
)
from eten_shared.answer_receipts import record_assignment_delivery
from eten_shared.database import get_session_factory

MCQ_CALLBACK_PREFIX = "mcq"
MCQ_BUTTON_LABEL_MAX_CHARS = 60


def prompt_question_type(prompt):
    return (getattr(prompt, "question_type", None) or "open").strip().lower()


def prompt_is_choice_question(prompt):
    return (
        prompt_question_type(prompt) in {QUESTION_TYPE_MCQ, QUESTION_TYPE_TF}
        and bool(getattr(prompt, "mcq_choices", None))
    )


def mcq_callback_data(assignment_id, choice_index):
    return f"{MCQ_CALLBACK_PREFIX}:{assignment_id}:{choice_index}"


def parse_mcq_callback_data(data):
    """Return (assignment_id, choice_index) or None when not an MCQ callback."""
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != MCQ_CALLBACK_PREFIX:
        return None
    assignment_id, raw_index = parts[1], parts[2]
    if not assignment_id or not raw_index.isdigit():
        return None
    choice_index = int(raw_index)
    if choice_index > 3:
        return None
    return assignment_id, choice_index


def build_mcq_keyboard(prompt):
    """Inline keyboard with one labeled button per choice, or None for open
    questions. Callback data carries the assignment id so stale taps on an
    older question message can be rejected."""
    if not prompt_is_choice_question(prompt):
        return None

    question_type = prompt_question_type(prompt)
    letters = choice_letters_for_type(question_type)
    rows = []
    for index, choice in enumerate(list(prompt.mcq_choices)):
        if index >= len(letters):
            break
        label = f"{letters[index]}. {choice}"
        if len(label) > MCQ_BUTTON_LABEL_MAX_CHARS:
            label = label[: MCQ_BUTTON_LABEL_MAX_CHARS - 1] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=mcq_callback_data(prompt.assignment_id, index),
                )
            ]
        )
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


def assignment_prompt_text(prompt, include_audio_url=True, with_keyboard=False):
    """Build the prompt text. When ``include_audio_url`` is False the raw audio
    link is omitted — used as the caption when the recording is delivered as an
    actual voice message instead of a link. When ``with_keyboard`` is True the
    choice instruction mentions the tap buttons (typed replies still work)."""

    parts = []
    if getattr(prompt, "passage_text", None):
        parts.append(prompt.passage_text)

    question_type = prompt_question_type(prompt)
    if question_type in {QUESTION_TYPE_MCQ, QUESTION_TYPE_TF} and getattr(prompt, "mcq_choices", None):
        letters_hint = "A or B" if question_type == QUESTION_TYPE_TF else "A, B, C, or D"
        if prompt.audio_url:
            parts.append("Listen to the audio, then choose your answer:")
            if include_audio_url:
                parts.append(prompt.audio_url)
        elif with_keyboard:
            parts.append("Tap your answer below:")
        else:
            parts.append(f"Choose your answer (reply {letters_hint}):")
        parts.append(prompt.question_text)
        parts.append(format_choices_for_display(list(prompt.mcq_choices), question_type))
        return "\n\n".join(parts)

    if prompt.audio_url:
        parts.append("Listen to the audio, then reply with your answer:")
        if include_audio_url:
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


async def send_text(bot, chat_id, text, reply_markup=None):
    try:
        return await bot.send_message(
            chat_id=chat_id, text=text, reply_markup=reply_markup
        )
    except RetryAfter as exc:
        import asyncio

        await asyncio.sleep(exc.retry_after)
        return await send_text(bot, chat_id, text, reply_markup=reply_markup)


async def _send_question_voice(bot, chat_id, audio_url, caption, reply_markup=None):
    """Deliver the question recording as a Telegram voice note.

    Telegram voice notes must be OGG/OPUS; if the recording is another format,
    fall back to a titled audio file, and finally to a text message with the
    link so the participant can always reach the question.
    """

    import asyncio

    for _ in range(2):
        try:
            return await bot.send_voice(
                chat_id=chat_id,
                voice=audio_url,
                caption=caption,
                reply_markup=reply_markup,
            )
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
        except TelegramError:
            break

    try:
        return await bot.send_audio(
            chat_id=chat_id,
            audio=audio_url,
            caption=caption,
            reply_markup=reply_markup,
        )
    except TelegramError:
        return await send_text(
            bot, chat_id, f"{caption}\n\n{audio_url}", reply_markup=reply_markup
        )


async def send_assignment_prompt(bot, chat_id, prompt):
    keyboard = build_mcq_keyboard(prompt)
    reply_markup = keyboard or ForceReply(
        selective=False,
        input_field_placeholder="Type your answer",
    )
    if prompt.audio_url:
        caption = assignment_prompt_text(
            prompt, include_audio_url=False, with_keyboard=bool(keyboard)
        )
        return await _send_question_voice(
            bot, chat_id, prompt.audio_url, caption, reply_markup=reply_markup
        )
    return await send_text(
        bot,
        chat_id,
        assignment_prompt_text(prompt, with_keyboard=bool(keyboard)),
        reply_markup=reply_markup,
    )


async def send_workflow_result(bot, chat_id, workflow_result):
    for badge in workflow_result.awarded_badges:
        await send_text(bot, chat_id, badge_message(badge))

    if workflow_result.status_message:
        await send_text(bot, chat_id, workflow_result.status_message)
        return

    if workflow_result.batch_completed and not workflow_result.engagement_deferred:
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

    if workflow_result.prompt:
        sent = await send_assignment_prompt(bot, chat_id, workflow_result.prompt)
        message_id = getattr(sent, "message_id", None)
        if message_id is not None:
            session_factory = get_session_factory()
            with session_factory() as db:
                record_assignment_delivery(
                    db,
                    participant_id=workflow_result.participant_id,
                    assignment_id=workflow_result.prompt.assignment_id,
                    provider="telegram",
                    provider_message_id=message_id,
                )
                db.commit()
        return sent

    if workflow_result.batch_completed and not workflow_result.engagement_deferred:
        return

    await send_text(
        bot,
        chat_id,
        no_assignment_message(response_recorded=bool(workflow_result.response_id)),
    )
