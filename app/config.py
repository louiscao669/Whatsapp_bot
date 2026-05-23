import sys
import os
from dotenv import load_dotenv
import logging


def load_configurations(app):
    load_dotenv()
    app.config["ACCESS_TOKEN"] = os.getenv("ACCESS_TOKEN")
    app.config["YOUR_PHONE_NUMBER"] = os.getenv("YOUR_PHONE_NUMBER")
    app.config["APP_ID"] = os.getenv("APP_ID")
    app.config["APP_SECRET"] = os.getenv("APP_SECRET")
    app.config["VERSION"] = os.getenv("VERSION")
    app.config["PHONE_NUMBER_ID"] = os.getenv("PHONE_NUMBER_ID")
    app.config["VERIFY_TOKEN"] = os.getenv("VERIFY_TOKEN")
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")
    app.config["SUPABASE_URL"] = os.getenv("SUPABASE_URL")
    app.config["SUPABASE_SERVICE_ROLE_KEY"] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    app.config["SUPABASE_AUDIO_BUCKET"] = os.getenv("SUPABASE_AUDIO_BUCKET")
    app.config["REMINDER_SCHEDULER_ENABLED"] = os.getenv(
        "REMINDER_SCHEDULER_ENABLED", "true"
    )
    app.config["REMINDER_POLL_INTERVAL_SECONDS"] = os.getenv(
        "REMINDER_POLL_INTERVAL_SECONDS", "300"
    )
    app.config["REMINDER_MAX_RETRIES"] = os.getenv("REMINDER_MAX_RETRIES", "3")
    app.config["REMINDER_RETRY_BACKOFF_MINUTES"] = os.getenv(
        "REMINDER_RETRY_BACKOFF_MINUTES", "5,15,30"
    )


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
