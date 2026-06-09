from flask import Blueprint, current_app, jsonify, request

from app.admin_nav import SPA_NAV_EXPORTS, SPA_NAV_PAGES, nav_pages_for_role
from app.services.admin_auth_service import (
    AdminAuthError,
    get_allowed_admin_user,
    normalize_email,
    send_admin_login_otp,
    verify_admin_login_otp,
)
from app.services.admin_session_service import (
    clear_admin_session,
    create_admin_session,
    get_current_admin_user,
    get_role_for_token,
)

auth_blueprint = Blueprint("api_auth", __name__)


def _json_body():
    return request.get_json(silent=True) or {}


@auth_blueprint.route("/otp/request", methods=["POST"])
def request_otp():
    body = _json_body()
    email = normalize_email(body.get("email", ""))
    if not email:
        return jsonify({"error": "validation_error", "message": "Email is required"}), 400

    try:
        send_admin_login_otp(email)
    except AdminAuthError as exc:
        return jsonify({"error": "auth_error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": "auth_error", "message": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "email": email,
            "message": "Check your email for a login code.",
        }
    )


@auth_blueprint.route("/otp/verify", methods=["POST"])
def verify_otp():
    body = _json_body()
    email = normalize_email(body.get("email", ""))
    code = (body.get("code") or body.get("otp_token") or "").strip()
    if not email or not code:
        return (
            jsonify(
                {
                    "error": "validation_error",
                    "message": "Email and verification code are required",
                }
            ),
            400,
        )

    try:
        verified_email, _ = verify_admin_login_otp(email, code)
    except Exception as exc:
        return jsonify({"error": "auth_error", "message": str(exc)}), 401

    admin_user = get_allowed_admin_user(verified_email)
    if not admin_user:
        return (
            jsonify(
                {
                    "error": "forbidden",
                    "message": "This email is not approved for admin access.",
                }
            ),
            403,
        )

    create_admin_session(
        admin_user["role"],
        email=admin_user["email"],
        display_name=admin_user.get("display_name"),
    )
    return jsonify(_serialize_user(admin_user))


@auth_blueprint.route("/token", methods=["POST"])
def token_login():
    if not current_app.config.get("ADMIN_ALLOW_TOKEN_LOGIN", True):
        return jsonify({"error": "forbidden", "message": "Token login is disabled"}), 403

    body = _json_body()
    token = (body.get("token") or "").strip()
    if not token:
        return jsonify({"error": "validation_error", "message": "Token is required"}), 400

    role = get_role_for_token(token)
    if not role:
        return jsonify({"error": "auth_error", "message": "Invalid token"}), 401

    create_admin_session(role)
    user = get_current_admin_user()
    return jsonify(_serialize_user(user))


@auth_blueprint.route("/logout", methods=["POST"])
def logout():
    clear_admin_session()
    return jsonify({"ok": True})


@auth_blueprint.route("/me", methods=["GET"])
def me():
    user = get_current_admin_user()
    if not user:
        return jsonify({"error": "unauthorized", "message": "Not logged in"}), 401
    return jsonify(_serialize_user(user))


def _serialize_user(user):
    from app.services.admin_session_service import normalize_role

    role = normalize_role(user["role"])
    return {
        "ok": True,
        "user": {
            "role": role,
            "email": user.get("email"),
            "display_name": user.get("display_name"),
        },
        "nav": {
            "spa": nav_pages_for_role(role, SPA_NAV_PAGES),
            "exports": nav_pages_for_role(role, SPA_NAV_EXPORTS),
        },
    }
