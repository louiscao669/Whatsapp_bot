import hashlib
import hmac
import os
import secrets
import smtplib
from datetime import timezone, timedelta
from email.message import EmailMessage

import requests
from sqlalchemy import select

from app.database import get_session_factory
from app.models import AdminLoginCode, AdminRole, AdminUser, utc_now


VALID_ADMIN_ROLES = {AdminRole.ADMIN.value, AdminRole.EXPERT.value}


class AdminAuthError(Exception):
    pass


def normalize_email(email):
    return (email or "").strip().lower()


def get_admin_auth_provider():
    return os.getenv("ADMIN_AUTH_PROVIDER", "supabase").strip().lower()


def get_otp_secret():
    return os.getenv("ADMIN_OTP_SECRET") or os.getenv("FLASK_SECRET_KEY") or os.getenv("APP_SECRET")


def hash_otp_code(email, code):
    otp_secret = get_otp_secret()
    if not otp_secret:
        raise AdminAuthError("ADMIN_OTP_SECRET, FLASK_SECRET_KEY, or APP_SECRET is required for SMTP OTP login")

    message = f"{normalize_email(email)}:{code.strip()}".encode("utf-8")
    return hmac.new(otp_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def generate_otp_code():
    code_length = int(os.getenv("ADMIN_OTP_CODE_LENGTH", "6"))
    upper_bound = 10 ** code_length
    return f"{secrets.randbelow(upper_bound):0{code_length}d}"


def get_otp_expiry():
    return utc_now() + timedelta(minutes=int(os.getenv("ADMIN_OTP_EXPIRY_MINUTES", "10")))


def normalize_datetime(value):
    if value and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def get_supabase_auth_config():
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        raise AdminAuthError("SUPABASE_URL and SUPABASE_ANON_KEY are required")

    return supabase_url.rstrip("/"), anon_key


def send_supabase_login_otp(email):
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise AdminAuthError("Email is required")

    supabase_url, anon_key = get_supabase_auth_config()
    response = requests.post(
        f"{supabase_url}/auth/v1/otp",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json",
        },
        json={
            "email": normalized_email,
            "create_user": False,
        },
        timeout=10,
    )
    response.raise_for_status()
    return normalized_email


def get_smtp_config():
    host = os.getenv("SMTP_HOST")
    from_email = os.getenv("SMTP_FROM_EMAIL")
    if not host or not from_email:
        raise AdminAuthError("SMTP_HOST and SMTP_FROM_EMAIL are required for SMTP OTP login")

    return {
        "host": host,
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("SMTP_USERNAME"),
        "password": os.getenv("SMTP_PASSWORD"),
        "from_email": from_email,
        "from_name": os.getenv("SMTP_FROM_NAME", "WhatsApp QA Bot"),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() == "true",
    }


def send_email_via_smtp(to_email, subject, body):
    config = get_smtp_config()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{config['from_name']} <{config['from_email']}>"
    message["To"] = to_email
    message.set_content(body)

    with smtplib.SMTP(config["host"], config["port"], timeout=15) as smtp:
        if config["use_tls"]:
            smtp.starttls()
        if config["username"] and config["password"]:
            smtp.login(config["username"], config["password"])
        smtp.send_message(message)


def store_smtp_login_code(email, code):
    session_factory = get_session_factory()
    with session_factory() as db:
        login_code = AdminLoginCode(
            email=normalize_email(email),
            code_hash=hash_otp_code(email, code),
            expires_at=get_otp_expiry(),
        )
        db.add(login_code)
        db.commit()


def send_smtp_login_otp(email):
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise AdminAuthError("Email is required")

    code = generate_otp_code()
    store_smtp_login_code(normalized_email, code)
    subject = os.getenv("ADMIN_OTP_EMAIL_SUBJECT", "Your WhatsApp QA admin login code")
    body = (
        f"Your WhatsApp QA admin login code is: {code}\n\n"
        f"This code expires in {os.getenv('ADMIN_OTP_EXPIRY_MINUTES', '10')} minutes."
    )
    send_email_via_smtp(normalized_email, subject, body)
    return normalized_email


def send_admin_login_otp(email):
    if get_admin_auth_provider() == "smtp":
        return send_smtp_login_otp(email)

    return send_supabase_login_otp(email)


def verify_supabase_login_otp(email, token):
    normalized_email = normalize_email(email)
    if not normalized_email or not token:
        raise AdminAuthError("Email and verification code are required")

    supabase_url, anon_key = get_supabase_auth_config()
    response = requests.post(
        f"{supabase_url}/auth/v1/verify",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json",
        },
        json={
            "email": normalized_email,
            "token": token.strip(),
            "type": "email",
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    user_email = normalize_email(payload.get("user", {}).get("email") or normalized_email)
    return user_email, payload


def get_latest_valid_smtp_code(db, email):
    codes = db.scalars(
        select(AdminLoginCode)
        .where(
            AdminLoginCode.email == normalize_email(email),
            AdminLoginCode.consumed_at.is_(None),
        )
        .order_by(AdminLoginCode.created_at.desc())
    ).all()

    now = utc_now()
    for code in codes:
        expires_at = normalize_datetime(code.expires_at)
        if expires_at and expires_at >= now:
            return code

    return None


def verify_smtp_login_otp(email, token):
    normalized_email = normalize_email(email)
    if not normalized_email or not token:
        raise AdminAuthError("Email and verification code are required")

    max_attempts = int(os.getenv("ADMIN_OTP_MAX_ATTEMPTS", "5"))
    session_factory = get_session_factory()
    with session_factory() as db:
        login_code = get_latest_valid_smtp_code(db, normalized_email)
        if not login_code:
            raise AdminAuthError("Invalid or expired verification code")

        if login_code.attempts >= max_attempts:
            raise AdminAuthError("Too many verification attempts")

        login_code.attempts += 1
        expected_hash = hash_otp_code(normalized_email, token)
        if not hmac.compare_digest(login_code.code_hash, expected_hash):
            db.commit()
            raise AdminAuthError("Invalid or expired verification code")

        login_code.consumed_at = utc_now()
        db.commit()
        return normalized_email, {"provider": "smtp"}


def verify_admin_login_otp(email, token):
    if get_admin_auth_provider() == "smtp":
        return verify_smtp_login_otp(email, token)

    return verify_supabase_login_otp(email, token)


def get_allowed_admin_user(email):
    normalized_email = normalize_email(email)
    session_factory = get_session_factory()
    with session_factory() as db:
        admin_user = db.scalars(
            select(AdminUser).where(AdminUser.email == normalized_email)
        ).first()
        if (
            not admin_user
            or not admin_user.active
            or admin_user.role not in VALID_ADMIN_ROLES
        ):
            return None

        admin_user.last_login_at = utc_now()
        db.commit()
        return {
            "email": admin_user.email,
            "role": admin_user.role,
            "display_name": admin_user.display_name,
        }
