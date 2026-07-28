import logging
import sys
from pathlib import Path

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
MESSAGE_BOT_ROOT = REPO_ROOT / "message-bot"
if str(MESSAGE_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(MESSAGE_BOT_ROOT))

from app.providers.telegram.config import (
    default_target_language_label,
    telegram_bot_token,
)
from app.engagement.dashboard_nudge import dashboard_link_reply, is_dashboard_command
from app.engagement.outbox import start_outbox_poller
from app.engagement.reminders import start_reminder_scheduler
from app.messaging.workflow import (
    record_telegram_choice_answer,
    record_telegram_text_message,
    record_telegram_voice_message,
)
from app.providers.telegram.messaging import (
    MCQ_CALLBACK_PREFIX,
    parse_mcq_callback_data,
    send_workflow_result,
)
from app.providers.telegram.store import (
    LANGUAGE_CONFIRMED,
    LANGUAGE_PENDING,
    LANGUAGE_REJECTED,
    confirm_telegram_default_language,
    contact_input_from_update,
    language_confirmation_status,
    language_is_confirmed,
    opt_out_telegram_contact,
    reject_telegram_default_language,
    upsert_telegram_contact,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

YES_RESPONSES = {"yes", "y", "yeah", "yep", "correct", "i do", "是", "会"}
NO_RESPONSES = {"no", "n", "nope", "not yet", "不是", "不会"}
NON_ANSWER_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hi there",
    "hello there",
    "你好",
    "您好",
}


def is_non_answer_greeting(message_text):
    """Return whether text should resume the workflow instead of answering.

    A participant commonly sends a greeting after a bot restart to see whether
    it is alive. Consuming that greeting as the answer to an open assignment
    silently completes the question with meaningless response data.
    """

    return (message_text or "").strip().lower() in NON_ANSWER_GREETINGS


def language_question():
    return (
        f"Thanks for joining the Notre Dame SaNDwich Lab Bible translation research. Do you speak "
        f"{default_target_language_label()}?\n\n"
        "Reply yes or no."
    )


async def send_initial_workflow_prompt(context, contact, message_id=None):
    workflow_result = record_telegram_text_message(
        chat_id=contact.external_user_id,
        display_name=contact.display_name,
        message_id=message_id,
        message_text="",
        record_response=False,
    )
    await send_workflow_result(context.bot, contact.external_user_id, workflow_result)


async def start(update, context):
    contact_input = contact_input_from_update(update)
    participant, contact, created = upsert_telegram_contact(contact_input)
    logging.info(
        "Telegram opt-in: chat_id=%s participant_id=%s username=%s created=%s",
        contact.external_user_id,
        participant.id,
        contact.username,
        created,
    )

    if not language_is_confirmed(contact):
        await update.effective_message.reply_text(language_question())
        return

    await update.effective_message.reply_text(
        "You're enrolled. Reply /stop at any time to opt out."
    )
    await send_initial_workflow_prompt(context, contact, contact_input.message_id)


async def stop(update, context):
    contact_input = contact_input_from_update(update)
    opted_out = opt_out_telegram_contact(contact_input)
    if opted_out:
        await update.effective_message.reply_text(
            "You have been opted out. Reply /start to join again."
        )
    else:
        await update.effective_message.reply_text(
            "I don't have you enrolled yet. Reply /start to join."
        )


async def dashboard(update, context):
    contact_input = contact_input_from_update(update)
    participant, contact, _ = upsert_telegram_contact(contact_input)
    await update.effective_message.reply_text(dashboard_link_reply(participant))


async def unknown_text(update, context):
    contact_input = contact_input_from_update(update)
    participant, contact, _ = upsert_telegram_contact(contact_input)
    message_text = update.effective_message.text or ""
    normalized_text = message_text.strip().lower()

    # Let participants pull their dashboard link at any point in the chat.
    if is_dashboard_command(message_text):
        await update.effective_message.reply_text(dashboard_link_reply(participant))
        return

    status = language_confirmation_status(contact)
    if status != LANGUAGE_CONFIRMED:
        if normalized_text in YES_RESPONSES:
            participant, contact = confirm_telegram_default_language(contact_input)
            await update.effective_message.reply_text(
                f"Thanks. We'll use {default_target_language_label()} for your study questions."
            )
            await send_initial_workflow_prompt(context, contact, contact_input.message_id)
            return

        if normalized_text in NO_RESPONSES:
            reject_telegram_default_language(contact_input)
            await update.effective_message.reply_text(
                "Thanks. We won't start study questions yet. A study coordinator can update your language setting."
            )
            return

        if status in {LANGUAGE_PENDING, LANGUAGE_REJECTED}:
            await update.effective_message.reply_text(language_question())
            return

    workflow_result = record_telegram_text_message(
        chat_id=contact.external_user_id,
        display_name=contact.display_name or participant.display_name,
        message_id=contact_input.message_id,
        message_text=message_text,
        # Greetings are health checks/resume requests, not study answers. The
        # workflow will re-send the current prompt without completing it.
        record_response=not is_non_answer_greeting(message_text),
    )
    await send_workflow_result(context.bot, contact.external_user_id, workflow_result)


async def voice_message(update, context):
    """Participant answered with a voice note (or an audio file).

    Mirrors the WhatsApp audio path: download from the Telegram Bot API,
    store in Supabase, transcribe with Whisper, keyword-score the transcript.
    """
    contact_input = contact_input_from_update(update)
    participant, contact, _ = upsert_telegram_contact(contact_input)

    status = language_confirmation_status(contact)
    if status != LANGUAGE_CONFIRMED:
        # Language onboarding needs a yes/no text reply first.
        await update.effective_message.reply_text(language_question())
        return

    message = update.effective_message
    voice = message.voice or message.audio
    if voice is None:
        return

    try:
        telegram_file = await context.bot.get_file(voice.file_id)
        audio_bytes = bytes(await telegram_file.download_as_bytearray())
    except Exception:
        logging.exception(
            "Failed to download Telegram voice file %s for chat %s",
            voice.file_id,
            contact.external_user_id,
        )
        await message.reply_text(
            "Sorry, I couldn't receive your voice message. "
            "Please try sending it again, or type your answer instead."
        )
        return

    workflow_result = record_telegram_voice_message(
        chat_id=contact.external_user_id,
        display_name=contact.display_name or participant.display_name,
        message_id=contact_input.message_id,
        file_id=voice.file_id,
        audio_bytes=audio_bytes,
        file_unique_id=getattr(voice, "file_unique_id", None),
        mime_type=getattr(voice, "mime_type", None),
        duration_seconds=getattr(voice, "duration", None),
        record_response=True,
    )
    await send_workflow_result(context.bot, contact.external_user_id, workflow_result)


async def mcq_button_tap(update, context):
    """Participant tapped an inline-keyboard answer button on an MCQ/TF question."""
    query = update.callback_query
    parsed = parse_mcq_callback_data(query.data or "")
    if parsed is None:
        await query.answer()
        return
    assignment_id, choice_index = parsed

    # Stop Telegram's button spinner immediately. The durable database commit and
    # next-question delivery continue below.
    await query.answer("Submitting…")

    contact_input = contact_input_from_update(update)

    try:
        workflow_result = record_telegram_choice_answer(
            chat_id=contact_input.chat_id,
            display_name=contact_input.display_name,
            message_id=contact_input.message_id,
            assignment_id=assignment_id,
            choice_index=choice_index,
        )
    except Exception:
        logging.exception(
            "Failed to record inline-keyboard answer for chat %s assignment %s",
            contact_input.chat_id,
            assignment_id,
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Sorry, something went wrong recording your answer. Please try again.",
        )
        return

    if workflow_result is None:
        # Stale tap: the button belongs to a question that is no longer current.
        await context.bot.send_message(
            chat_id=query.message.chat_id, text="This question was already answered."
        )
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    # Remove the buttons so the same question can't be tapped twice.
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await send_workflow_result(context.bot, contact_input.chat_id, workflow_result)


def build_application():
    app = Application.builder().token(telegram_bot_token()).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_message))
    app.add_handler(
        CallbackQueryHandler(mcq_button_tap, pattern=rf"^{MCQ_CALLBACK_PREFIX}:")
    )
    return app


def main():
    start_reminder_scheduler()
    # Drain cross-surface pushes (new assignments, dashboard-answer sync) on the
    # Telegram deployment too — otherwise the outbox only runs in the WhatsApp
    # Flask app and Telegram participants never receive proactive questions.
    start_outbox_poller()
    # Telegram retains updates while a polling process is offline. Replaying
    # those messages on restart can consume several currently assigned
    # questions in seconds. Drop that backlog; participants can resend a real
    # answer after the service is available again.
    build_application().run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
