import logging
import sys
from pathlib import Path

from telegram.ext import Application, CommandHandler, MessageHandler, filters

REPO_ROOT = Path(__file__).resolve().parents[4]
MESSAGE_BOT_ROOT = REPO_ROOT / "message-bot"
if str(MESSAGE_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(MESSAGE_BOT_ROOT))

from app.providers.telegram.config import (
    default_target_language_label,
    telegram_bot_token,
)
from app.engagement.dashboard_nudge import dashboard_link_reply, is_dashboard_command
from app.engagement.reminders import start_reminder_scheduler
from app.messaging.workflow import record_telegram_text_message
from app.providers.telegram.messaging import send_workflow_result
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


def language_question():
    return (
        f"Thanks for joining the [Study Name]. Do you speak "
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
        record_response=True,
    )
    await send_workflow_result(context.bot, contact.external_user_id, workflow_result)


def build_application():
    app = Application.builder().token(telegram_bot_token()).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
    return app


def main():
    start_reminder_scheduler()
    build_application().run_polling()


if __name__ == "__main__":
    main()
