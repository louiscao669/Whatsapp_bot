"""Flask session helpers for admin / expert login."""

import hmac
from functools import wraps

from flask import current_app, jsonify, request, session

ROLE_CONFIG = {
    "admin": "ADMIN_API_TOKEN",
    "expert": "EXPERT_API_TOKEN",
}


def normalize_role(role):
    if role is None:
        return None
    normalized = str(role).strip().lower()
    return normalized or None


def get_bearer_token():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip()
    return ""


def role_token_valid(role, token):
    if not token:
        return False
    config_key = ROLE_CONFIG[role]
    expected_token = current_app.config.get(config_key)
    if not expected_token:
        return False
    return hmac.compare_digest(token, expected_token)


def get_role_for_token(token):
    for role in ROLE_CONFIG:
        if role_token_valid(role, token):
            return role
    return None


def create_admin_session(role, email=None, display_name=None):
    session.clear()
    session["admin_role"] = normalize_role(role)
    if email:
        session["admin_email"] = email
    if display_name:
        session["admin_display_name"] = display_name


def clear_admin_session():
    session.clear()


def get_request_admin_role():
    role = normalize_role(session.get("admin_role"))
    if role:
        return role

    token = get_bearer_token()
    if not token:
        return None

    return get_role_for_token(token)


def get_current_admin_user():
    role = get_request_admin_role()
    if not role:
        return None
    return {
        "role": role,
        "email": session.get("admin_email"),
        "display_name": session.get("admin_display_name"),
    }


def require_roles(*allowed_roles):
    """JSON API guard: session cookie or Bearer token."""

    allowed = frozenset(normalize_role(role) for role in allowed_roles)

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            role = get_request_admin_role()
            if role in allowed:
                return view(*args, **kwargs)

            return jsonify({"error": "unauthorized", "message": "Unauthorized"}), 401

        return wrapped

    return decorator
