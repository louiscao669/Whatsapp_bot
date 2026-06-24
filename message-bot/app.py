import logging
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("MESSAGE_BOT_PORT") or os.getenv("WHATSAPP_BOT_PORT", "7861"))
    logging.info("Message bot starting on port %s", port)
    app.run(host="0.0.0.0", port=port)
