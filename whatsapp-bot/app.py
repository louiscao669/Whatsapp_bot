import logging
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("WHATSAPP_BOT_PORT", "7861"))
    logging.info("WhatsApp bot starting on port %s", port)
    app.run(host="0.0.0.0", port=port)
