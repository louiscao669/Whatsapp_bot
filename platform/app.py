import logging
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PLATFORM_PORT", "7860"))
    logging.info("Platform starting on port %s", port)
    app.run(host="0.0.0.0", port=port)
