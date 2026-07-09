import logging
import sys
from pathlib import Path

from telegram.ext import Application, CommandHandler, MessageHandler, filters

REPO_ROOT = Path(__file__).resolve().parents[4]
MESSAGE_BOT_ROOT = REPO_ROOT / "message-bot"
if str(MESSAGE_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(MESSAGE_BOT_ROOT))

from app.providers.telegram.config import telegram_bot_token
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
    upsert_telegram_contact(contact_input)
    await update.effective_message.reply_text(
        "You're enrolled. The study bot will send questions here."
    )


def build_application():
    app = Application.builder().token(telegram_bot_token()).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
    return app


def main():
    build_application().run_polling()


if __name__ == "__main__":
    main()
