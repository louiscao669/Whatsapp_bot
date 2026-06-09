import logging
import os
import sys
from datetime import timedelta

from dotenv import load_dotenv

from eten_shared.repo_paths import REPO_ROOT


def _strip_env_token(value):
    if not value:
        return None
    return value.strip().strip('"').strip("'")


def load_configurations(app):
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv()
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY") or os.getenv("APP_SECRET")
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")
    app.config["SUPABASE_URL"] = os.getenv("SUPABASE_URL")
    app.config["SUPABASE_ANON_KEY"] = os.getenv("SUPABASE_ANON_KEY")
    app.config["SUPABASE_SERVICE_ROLE_KEY"] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    app.config["SUPABASE_AUDIO_BUCKET"] = os.getenv("SUPABASE_AUDIO_BUCKET")
    app.config["ADMIN_AUTH_PROVIDER"] = os.getenv("ADMIN_AUTH_PROVIDER", "supabase")
    app.config["ADMIN_OTP_SECRET"] = os.getenv("ADMIN_OTP_SECRET")
    app.config["ADMIN_OTP_EXPIRY_MINUTES"] = os.getenv("ADMIN_OTP_EXPIRY_MINUTES", "10")
    app.config["ADMIN_OTP_CODE_LENGTH"] = os.getenv("ADMIN_OTP_CODE_LENGTH", "6")
    app.config["ADMIN_OTP_MAX_ATTEMPTS"] = os.getenv("ADMIN_OTP_MAX_ATTEMPTS", "5")
    app.config["SMTP_HOST"] = os.getenv("SMTP_HOST")
    app.config["SMTP_PORT"] = os.getenv("SMTP_PORT", "587")
    app.config["SMTP_USERNAME"] = os.getenv("SMTP_USERNAME")
    app.config["SMTP_FROM_EMAIL"] = os.getenv("SMTP_FROM_EMAIL")
    app.config["ADMIN_API_TOKEN"] = _strip_env_token(os.getenv("ADMIN_API_TOKEN"))
    app.config["EXPERT_API_TOKEN"] = _strip_env_token(os.getenv("EXPERT_API_TOKEN"))
    app.config["ADMIN_ALLOW_TOKEN_LOGIN"] = os.getenv("ADMIN_ALLOW_TOKEN_LOGIN", "true").lower() == "true"
    configure_session_security(app)


def configure_session_security(app):
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
    session_hours = int(os.getenv("ADMIN_SESSION_LIFETIME_HOURS", "8"))
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=session_hours)


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
