import os

import requests
from sqlalchemy import select

from app.database import get_session_factory
from app.models import AdminRole, AdminUser, utc_now


VALID_ADMIN_ROLES = {AdminRole.ADMIN.value, AdminRole.EXPERT.value}


class AdminAuthError(Exception):
    pass


def normalize_email(email):
    return (email or "").strip().lower()


def get_supabase_auth_config():
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        raise AdminAuthError("SUPABASE_URL and SUPABASE_ANON_KEY are required")

    return supabase_url.rstrip("/"), anon_key


def send_admin_login_otp(email):
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


def verify_admin_login_otp(email, token):
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
