import logging
import os
import sys
from importlib.util import module_from_spec, spec_from_file_location

from dotenv import load_dotenv

from eten_shared.repo_paths import REPO_ROOT


def _load_config_defaults():
    config_path = REPO_ROOT / "config.py"
    if not config_path.exists():
        return

    spec = spec_from_file_location("eten_runtime_config", config_path)
    if not spec or not spec.loader:
        return

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    for key, value in getattr(module, "CONFIG_DEFAULTS", {}).items():
        os.environ.setdefault(key, str(value))


def load_configurations(app):
    _load_config_defaults()
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv()
    app.config["ACCESS_TOKEN"] = os.getenv("ACCESS_TOKEN")
    app.config["APP_ID"] = os.getenv("APP_ID")
    app.config["APP_SECRET"] = os.getenv("APP_SECRET")
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY") or os.getenv("APP_SECRET")
    app.config["VERSION"] = os.getenv("VERSION")
    app.config["PHONE_NUMBER_ID"] = os.getenv("PHONE_NUMBER_ID")
    app.config["VERIFY_TOKEN"] = os.getenv("VERIFY_TOKEN")
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")
    app.config["SUPABASE_URL"] = os.getenv("SUPABASE_URL")
    app.config["SUPABASE_SERVICE_ROLE_KEY"] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    app.config["SUPABASE_AUDIO_BUCKET"] = os.getenv("SUPABASE_AUDIO_BUCKET")
    app.config["REMINDER_SCHEDULER_ENABLED"] = os.getenv("REMINDER_SCHEDULER_ENABLED", "true")
    app.config["REMINDER_POLL_INTERVAL_SECONDS"] = os.getenv("REMINDER_POLL_INTERVAL_SECONDS", "300")
    app.config["REMINDER_MAX_RETRIES"] = os.getenv("REMINDER_MAX_RETRIES", "3")
    app.config["REMINDER_RETRY_BACKOFF_MINUTES"] = os.getenv("REMINDER_RETRY_BACKOFF_MINUTES", "5,15,30")
    app.config["REMINDER_TEMPLATE_NAME"] = os.getenv("REMINDER_TEMPLATE_NAME")
    app.config["REMINDER_TEMPLATE_LANGUAGE"] = os.getenv("REMINDER_TEMPLATE_LANGUAGE", "en_US")
    app.config["REMINDER_TEMPLATE_BODY_PARAMS"] = os.getenv("REMINDER_TEMPLATE_BODY_PARAMS", "")
    app.config["REMINDER_TEMPLATE_FIRST_DELAY_HOURS"] = os.getenv("REMINDER_TEMPLATE_FIRST_DELAY_HOURS", "48")
    app.config["REMINDER_TEMPLATE_REPEAT_HOURS"] = os.getenv("REMINDER_TEMPLATE_REPEAT_HOURS", "48")
    app.config["REMINDER_TEMPLATE_MAX_COUNT"] = os.getenv("REMINDER_TEMPLATE_MAX_COUNT", "0")
    app.config["BATCH_NEXT_ASSIGN_HOUR"] = os.getenv("BATCH_NEXT_ASSIGN_HOUR", "8")
    app.config["BATCH_NEXT_ASSIGN_DEFAULT_TIMEZONE"] = os.getenv(
        "BATCH_NEXT_ASSIGN_DEFAULT_TIMEZONE",
        os.getenv("MESSAGE_BOT_DEFAULT_TIMEZONE", "UTC"),
    )


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
