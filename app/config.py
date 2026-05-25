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
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY") or os.getenv("APP_SECRET")
    app.config["VERSION"] = os.getenv("VERSION")
    app.config["PHONE_NUMBER_ID"] = os.getenv("PHONE_NUMBER_ID")
    app.config["VERIFY_TOKEN"] = os.getenv("VERIFY_TOKEN")
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")
    app.config["SUPABASE_URL"] = os.getenv("SUPABASE_URL")
    app.config["SUPABASE_ANON_KEY"] = os.getenv("SUPABASE_ANON_KEY")
    app.config["ADMIN_AUTH_PROVIDER"] = os.getenv("ADMIN_AUTH_PROVIDER", "supabase")
    app.config["ADMIN_OTP_SECRET"] = os.getenv("ADMIN_OTP_SECRET")
    app.config["ADMIN_OTP_EXPIRY_MINUTES"] = os.getenv("ADMIN_OTP_EXPIRY_MINUTES", "10")
    app.config["ADMIN_OTP_CODE_LENGTH"] = os.getenv("ADMIN_OTP_CODE_LENGTH", "6")
    app.config["ADMIN_OTP_MAX_ATTEMPTS"] = os.getenv("ADMIN_OTP_MAX_ATTEMPTS", "5")
    app.config["SMTP_HOST"] = os.getenv("SMTP_HOST")
    app.config["SMTP_PORT"] = os.getenv("SMTP_PORT", "587")
    app.config["SMTP_USERNAME"] = os.getenv("SMTP_USERNAME")
    app.config["SMTP_FROM_EMAIL"] = os.getenv("SMTP_FROM_EMAIL")
    app.config["SUPABASE_SERVICE_ROLE_KEY"] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    app.config["SUPABASE_AUDIO_BUCKET"] = os.getenv("SUPABASE_AUDIO_BUCKET")
    app.config["ADMIN_API_TOKEN"] = os.getenv("ADMIN_API_TOKEN")
    app.config["EXPERT_API_TOKEN"] = os.getenv("EXPERT_API_TOKEN")
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
    app.config["REMINDER_TEMPLATE_NAME"] = os.getenv("REMINDER_TEMPLATE_NAME")
    app.config["REMINDER_TEMPLATE_LANGUAGE"] = os.getenv(
        "REMINDER_TEMPLATE_LANGUAGE", "en_US"
    )
    app.config["REMINDER_TEMPLATE_BODY_PARAMS"] = os.getenv(
        "REMINDER_TEMPLATE_BODY_PARAMS", ""
    )
    app.config["REMINDER_TEMPLATE_FIRST_DELAY_HOURS"] = os.getenv(
        "REMINDER_TEMPLATE_FIRST_DELAY_HOURS", "48"
    )
    app.config["REMINDER_TEMPLATE_REPEAT_HOURS"] = os.getenv(
        "REMINDER_TEMPLATE_REPEAT_HOURS", "48"
    )
    app.config["REMINDER_TEMPLATE_MAX_COUNT"] = os.getenv(
        "REMINDER_TEMPLATE_MAX_COUNT", "0"
    )


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
