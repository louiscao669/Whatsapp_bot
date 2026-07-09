import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MESSAGE_BOT_ROOT = REPO_ROOT / "message-bot"
if str(MESSAGE_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(MESSAGE_BOT_ROOT))

from app.providers.telegram.sender import main


if __name__ == "__main__":
    main()
