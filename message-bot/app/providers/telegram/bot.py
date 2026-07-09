import logging
import sys
from pathlib import Path

from telegram.ext import Application, CommandHandler, MessageHandler, filters

REPO_ROOT = Path(__file__).resolve().parents[4]
MESSAGE_BOT_ROOT = REPO_ROOT / "message-bot"
if str(MESSAGE_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(MESSAGE_BOT_ROOT))

from app.providers.telegram.config import telegram_bot_token
from app.engagement.reminders import start_reminder_scheduler
from app.messaging.workflow import record_telegram_text_message
from app.providers.telegram.messaging import send_workflow_result
from app.providers.telegram.store import (
    contact_input_from_update,
    opt_out_telegram_contact,
    upsert_telegram_contact,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


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

    if created:
        message = (
            "Thanks for joining the [Study Name]. You'll receive messages here. "
            "Reply /stop at any time to opt out."
        )
    else:
        message = "You're enrolled. Reply /stop at any time to opt out."
    await update.effective_message.reply_text(message)
    workflow_result = record_telegram_text_message(
        chat_id=contact.external_user_id,
        display_name=contact.display_name,
        message_id=contact_input.message_id,
        message_text="",
        record_response=False,
    )
    await send_workflow_result(context.bot, contact.external_user_id, workflow_result)


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


async def unknown_text(update, context):
    contact_input = contact_input_from_update(update)
    participant, contact, _ = upsert_telegram_contact(contact_input)
    message_text = update.effective_message.text or ""
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
    return app


def main():
    start_reminder_scheduler()
    build_application().run_polling()


if __name__ == "__main__":
    main()
