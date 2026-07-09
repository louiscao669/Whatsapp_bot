import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]
MESSAGE_BOT_ROOT = REPO_ROOT / "message-bot"
SHARED_PACKAGE_ROOT = REPO_ROOT / "packages" / "eten-shared"

for path in (MESSAGE_BOT_ROOT, SHARED_PACKAGE_ROOT, REPO_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

load_dotenv(REPO_ROOT / ".env")
load_dotenv()


def telegram_bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN. Set it in the repo .env file.")
    return token


def default_target_language() -> str:
    return (
        os.getenv("TELEGRAM_DEFAULT_TARGET_LANGUAGE")
        or os.getenv("MESSAGE_BOT_DEFAULT_TARGET_LANGUAGE")
        or "eng"
    ).strip() or "eng"


def default_target_language_label() -> str:
    return (
        os.getenv("TELEGRAM_DEFAULT_TARGET_LANGUAGE_LABEL")
        or os.getenv("MESSAGE_BOT_DEFAULT_TARGET_LANGUAGE_LABEL")
        or default_target_language()
    ).strip() or default_target_language()
