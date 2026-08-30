from eten_shared.participant_identity import delivery_address
import asyncio
import logging
import sys
from pathlib import Path

from telegram import Bot
from telegram.error import RetryAfter, TelegramError

REPO_ROOT = Path(__file__).resolve().parents[4]
MESSAGE_BOT_ROOT = REPO_ROOT / "message-bot"
if str(MESSAGE_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(MESSAGE_BOT_ROOT))

from app.providers.telegram.config import telegram_bot_token
from app.providers.telegram.store import active_telegram_contacts

logging.basicConfig(
    filename="telegram_log.csv",
    level=logging.INFO,
    format="%(asctime)s,%(message)s",
)


async def send_message(bot, chat_id, text):
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        logging.info("%s,SUCCESS", chat_id)
        return True
    except RetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        return await send_message(bot, chat_id, text)
    except TelegramError as exc:
        logging.info("%s,FAILED,%s", chat_id, exc)
        return False


async def run_campaign(text: str | None = None):
    bot = Bot(token=telegram_bot_token())
    contacts = active_telegram_contacts()
    default_text = (
        "Hi {name}, this is a message from the Notre Dame SaNDwich Lab Bible translation research team. ..."
    )

    for index, contact in enumerate(contacts, 1):
        name = contact.display_name or "there"
        body = (text or default_text).format(name=name)
        ok = await send_message(bot, delivery_address(contact), body)
        print(
            f"[{index}/{len(contacts)}] {delivery_address(contact)}: "
            f"{'sent' if ok else 'FAILED'}"
        )
        await asyncio.sleep(1)


def main():
    asyncio.run(run_campaign())


if __name__ == "__main__":
    main()
