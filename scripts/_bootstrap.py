"""Add monorepo package paths for CLI scripts."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WHATSAPP_BOT_ROOT = REPO_ROOT / "whatsapp-bot"
PLATFORM_ROOT = REPO_ROOT / "platform"
SHARED_ROOT = REPO_ROOT / "packages" / "eten-shared"


def use_whatsapp_bot():
    for path in (SHARED_ROOT, WHATSAPP_BOT_ROOT):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def use_platform():
    for path in (SHARED_ROOT, PLATFORM_ROOT):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
