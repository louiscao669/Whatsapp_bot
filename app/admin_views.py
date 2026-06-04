import csv
import html
import hmac
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, Response, current_app, jsonify, redirect, request, session, url_for
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database import get_session_factory
from app.services.chatbot_workflow import (
    AssignmentAssignError,
    assign_qa_item_to_participant,
    get_or_create_participant_session,
)
from app.services.audio_export_service import (
    build_zip_archive,
    fetch_response_audio_bytes,
    get_audio_export_chapters,
    zip_download_filename,
)
from app.services.admin_media_service import (
    expert_may_access_participant_response,
    load_participant_response_media,
    load_qa_keyword_recording_media,
    load_qa_recording_media,
    log_media_access,
)
from app.services.media_storage_service import (
    delete_storage_uri,
    is_supabase_storage_configured,
    parse_storage_uri,
    store_qa_recording_audio,
)
from app.services.uw_qa_import_service import (
    QAImportError,
    import_qa_entries,
    normalize_language_code,
    parse_entries_from_json_text,
)
from app.services.admin_auth_service import (
    AdminAuthError,
    get_allowed_admin_user,
    normalize_email,
    send_admin_login_otp,
    verify_admin_login_otp,
)
from app.models import (
    Assignment,
    Participant,
    ParticipantResponse,
    ParticipantSession,
    QAItem,
    QAItemRecording,
    SystemLanguage,
    utc_now,
)
from app.services.mcq_service import (
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_TF,
    choice_letters_for_type,
    choice_response_letter,
)
from app.services.qa_keywords_service import get_all_language_keywords_for_qa_items
from app.services.qa_review_service import (
    bulk_clear_chapter_reviewed,
    bulk_mark_chapter_reviewed,
    clear_qa_item_reviewed,
    group_qa_items_by_chapter,
    load_review_qa_items,
    load_recordable_qa_items,
    mark_qa_item_reviewed,
    qa_item_is_recordable,
    qa_item_is_removed,
    remove_qa_item_from_review,
    restore_qa_item_from_removed,
    revert_qa_item_to_original,
    review_qa_tab_for_item,
    update_qa_item_review_text,
)


admin_blueprint = Blueprint("admin", __name__, url_prefix="/admin")


EXPORT_COLUMNS = [
    "response_id",
    "received_at",
    "participant_id",
    "participant_wa_id",
    "participant_display_name",
    "qa_item_id",
    "passage_id",
    "passage_reference",
    "passage_text",
    "language",
    "question_text",
    "expected_answer",
    "required_keywords",
    "assignment_id",
    "batch_id",
    "question_type",
    "response_type",
    "response_text",
    "media_id",
    "media_url",
    "transcript_text",
    "normalized_text",
    "correctness_score",
    "matched_keywords",
    "missing_keywords",
    "is_correct",
    "flag_reason",
    "review_status",
]


ROLE_CONFIG = {
    "admin": "ADMIN_API_TOKEN",
    "expert": "EXPERT_API_TOKEN",
}

ADMIN_NAV_PAGES = [
    {"label": "Analytics", "path": "/admin/analytics", "roles": ("admin", "expert")},
    {"label": "QA Items", "path": "/admin/qa-items", "roles": ("admin",)},
    {"label": "Review Response", "path": "/admin/review", "roles": ("admin", "expert")},
    {"label": "Review QA", "path": "/admin/review-qa", "roles": ("admin", "expert")},
    {"label": "Record", "path": "/admin/record", "roles": ("admin", "expert")},
    {"label": "Participants", "path": "/admin/participants", "roles": ("admin",)},
]

ADMIN_NAV_EXPORTS = [
    {"label": "Export audio", "path": "/admin/export/audio", "roles": ("admin",)},
    {"label": "Export responses (CSV)", "path": "/admin/export/responses.csv", "roles": ("admin",)},
    {"label": "Export flagged (CSV)", "path": "/admin/export/flagged.csv", "roles": ("admin",)},
]


def _passage_sort_key(qa_item):
    reference = (qa_item.passage_reference or qa_item.passage_id or "").strip()
    normalized = re.sub(r"\s+", " ", reference)
    match = re.search(r"^(.*?)(\d+):(\d+)\s*$", normalized)
    if not match:
        return (1, normalized.lower(), float("inf"), float("inf"), qa_item.created_at, qa_item.id)

    book_part = re.sub(r"[^a-z0-9]+", " ", match.group(1).lower()).strip()
    chapter = int(match.group(2))
    verse = int(match.group(3))
    return (0, book_part, chapter, verse, qa_item.created_at, qa_item.id)


def sort_qa_items_by_passage_asc(qa_items):
    return sorted(qa_items, key=_passage_sort_key)


def get_bearer_token():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip()

    return ""


def role_token_valid(role, token):
    config_key = ROLE_CONFIG[role]
    expected_token = current_app.config.get(config_key)
    return bool(expected_token) and hmac.compare_digest(token, expected_token)


def get_role_for_token(token):
    for role in ROLE_CONFIG:
        if role_token_valid(role, token):
            return role

    return None


def session_role_allowed(allowed_roles):
    role = session.get("admin_role")
    return role in allowed_roles


def token_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session_role_allowed(allowed_roles):
                return f(*args, **kwargs)

            configured_roles = [
                role
                for role in allowed_roles
                if current_app.config.get(ROLE_CONFIG[role])
            ]
            if not configured_roles:
                if request.method == "GET" and not request.path.endswith(".csv"):
                    return redirect(url_for("admin.admin_login", next=request.path))

                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Required admin token is not configured",
                            "missing": [ROLE_CONFIG[role] for role in allowed_roles],
                        }
                    ),
                    503,
                )

            token = get_bearer_token()
            if any(role_token_valid(role, token) for role in configured_roles):
                return f(*args, **kwargs)

            if request.method == "GET" and not request.path.endswith(".csv"):
                return redirect(url_for("admin.admin_login", next=request.path))

            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        return decorated_function

    return decorator


def admin_token_required(f):
    return token_required("admin")(f)


def expert_token_required(f):
    return token_required("expert")(f)


def admin_or_expert_token_required(f):
    return token_required("admin", "expert")(f)


def request_admin_role():
    role = session.get("admin_role")
    if role:
        return role

    token = get_bearer_token()
    if role_token_valid("admin", token):
        return "admin"
    if role_token_valid("expert", token):
        return "expert"
    return None


def participant_response_media_url(response_id, download=False):
    return url_for(
        "admin.stream_participant_response_media",
        response_id=response_id,
        download=1 if download else None,
    )


def qa_recording_media_url(recording_id, download=False):
    return url_for(
        "admin.stream_qa_recording_media",
        recording_id=recording_id,
        download=1 if download else None,
    )


def qa_keyword_recording_media_url(recording_id, download=False):
    return url_for(
        "admin.stream_qa_keyword_recording_media",
        recording_id=recording_id,
        download=1 if download else None,
    )


def media_stream_cache_headers():
    return {
        "Cache-Control": "private, no-store",
        "Pragma": "no-cache",
    }


@admin_blueprint.route("/media/participant-response/<response_id>", methods=["GET"])
@admin_or_expert_token_required
def stream_participant_response_media(response_id):
    role = request_admin_role()
    if not role:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    response, content, content_type = load_participant_response_media(response_id)
    if not response:
        return jsonify({"status": "error", "message": "Response not found"}), 404

    if role == "expert" and not expert_may_access_participant_response(response):
        return jsonify({"status": "error", "message": "Forbidden"}), 403

    if not content:
        return jsonify({"status": "error", "message": "Audio not available"}), 404

    log_media_access(
        "participant_response",
        response_id,
        role,
        session.get("admin_email"),
    )

    as_download = request.args.get("download") in {"1", "true", "yes"}
    headers = media_stream_cache_headers()
    if as_download:
        headers["Content-Disposition"] = (
            f'attachment; filename="response_{response_id}.ogg"'
        )
    else:
        headers["Content-Disposition"] = "inline"

    return Response(content, mimetype=content_type, headers=headers)


@admin_blueprint.route("/media/qa-recording/<recording_id>", methods=["GET"])
@admin_or_expert_token_required
def stream_qa_recording_media(recording_id):
    role = request_admin_role()
    if not role:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    recording, content, content_type = load_qa_recording_media(recording_id)
    if not recording:
        return jsonify({"status": "error", "message": "Recording not found"}), 404

    if not content:
        return jsonify({"status": "error", "message": "Audio not available"}), 404

    log_media_access(
        "qa_recording",
        recording_id,
        role,
        session.get("admin_email"),
    )

    as_download = request.args.get("download") in {"1", "true", "yes"}
    headers = media_stream_cache_headers()
    filename_suffix = recording.recording_type or "recording"
    if as_download:
        headers["Content-Disposition"] = (
            f'attachment; filename="{filename_suffix}_{recording_id}.ogg"'
        )
    else:
        headers["Content-Disposition"] = "inline"

    return Response(content, mimetype=content_type, headers=headers)


@admin_blueprint.route("/media/qa-keyword-recording/<recording_id>", methods=["GET"])
@admin_or_expert_token_required
def stream_qa_keyword_recording_media(recording_id):
    role = request_admin_role()
    if not role:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    recording, content, content_type = load_qa_keyword_recording_media(recording_id)
    if not recording:
        return jsonify({"status": "error", "message": "Recording not found"}), 404

    if not content:
        return jsonify({"status": "error", "message": "Audio not available"}), 404

    log_media_access(
        "qa_keyword_recording",
        recording_id,
        role,
        session.get("admin_email"),
    )

    as_download = request.args.get("download") in {"1", "true", "yes"}
    headers = media_stream_cache_headers()
    if as_download:
        headers["Content-Disposition"] = (
            f'attachment; filename="keyword_{recording_id}.ogg"'
        )
    else:
        headers["Content-Disposition"] = "inline"

    return Response(content, mimetype=content_type, headers=headers)


def render_login_page(error_message="", info_message="", email="", code_sent=False):
    error_html = (
        f'<p style="color: #b00020;">{html.escape(error_message)}</p>'
        if error_message
        else ""
    )
    info_html = (
        f'<p style="color: #006400;">{html.escape(info_message)}</p>'
        if info_message
        else ""
    )
    next_url = html.escape(request.values.get("next", "/admin/analytics"))
    email_value = html.escape(email or request.values.get("email", ""))
    code_form = ""
    if code_sent:
        code_form = f"""
  <form method="post">
    <input type="hidden" name="next" value="{next_url}">
    <input type="hidden" name="email" value="{email_value}">
    <label for="otp_token">Verification code</label>
    <input id="otp_token" name="otp_token" inputmode="numeric" autocomplete="one-time-code" required>
    <button type="submit">Verify code</button>
  </form>
"""

    token_login_form = ""
    if current_app.config.get("ADMIN_ALLOW_TOKEN_LOGIN", True):
        token_login_form = f"""
  <hr>
  <p>Token fallback for development or emergency access:</p>
  <form method="post">
    <input type="hidden" name="next" value="{next_url}">
    <label for="token">Admin or expert token</label>
    <input id="token" name="token" type="password" autocomplete="current-password">
    <button type="submit" name="action" value="token_login">Log in with token</button>
  </form>
"""

    return Response(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Admin Login</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; max-width: 36rem; }}
    label {{ display: block; margin: 1rem 0 0.25rem; }}
    input {{ width: 100%; padding: 0.5rem; }}
    button {{ margin-top: 1rem; padding: 0.5rem 1rem; }}
    hr {{ margin: 2rem 0; }}
  </style>
</head>
<body>
  <h1>Admin Login</h1>
  {error_html}
  {info_html}
  <form method="post">
    <input type="hidden" name="next" value="{next_url}">
    <label for="email">Email</label>
    <input id="email" name="email" type="email" value="{email_value}" autocomplete="email" required>
    <button type="submit" name="action" value="send_code">Send login code</button>
  </form>
  {code_form}
  {token_login_form}
</body>
</html>""",
        mimetype="text/html",
    )


def create_admin_session(role, email=None, display_name=None):
    session.clear()
    session["admin_role"] = role
    if email:
        session["admin_email"] = email
    if display_name:
        session["admin_display_name"] = display_name


def get_safe_next_url():
    next_url = request.form.get("next") or request.args.get("next") or "/admin/analytics"
    if not next_url.startswith("/admin/"):
        return "/admin/analytics"

    return next_url


@admin_blueprint.route("/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_login_page()

    if request.form.get("token"):
        if not current_app.config.get("ADMIN_ALLOW_TOKEN_LOGIN", True):
            return render_login_page("Token login is disabled."), 403

        token = request.form.get("token", "")
        role = get_role_for_token(token)
        if not role:
            return render_login_page("Invalid token"), 401

        create_admin_session(role)
        return redirect(get_safe_next_url())

    email = normalize_email(request.form.get("email", ""))
    otp_token = request.form.get("otp_token", "").strip()
    if not otp_token:
        try:
            send_admin_login_otp(email)
        except AdminAuthError as exc:
            return render_login_page(str(exc), email=email), 400
        except Exception as exc:
            return render_login_page(str(exc), email=email), 400

        return render_login_page(
            info_message="Check your email for a login code.",
            email=email,
            code_sent=True,
        )

    try:
        verified_email, _ = verify_admin_login_otp(email, otp_token)
    except Exception as exc:
        return render_login_page(str(exc), email=email, code_sent=True), 401

    admin_user = get_allowed_admin_user(verified_email)
    if not admin_user:
        return render_login_page(
            "This email is not approved for admin access.",
            email=verified_email,
        ), 403

    create_admin_session(
        admin_user["role"],
        email=admin_user["email"],
        display_name=admin_user.get("display_name"),
    )
    return redirect(get_safe_next_url())


@admin_blueprint.route("/logout", methods=["GET", "POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin.admin_login"))


@admin_blueprint.route("/", methods=["GET"])
def admin_index():
    role = session.get("admin_role")
    if role == "expert":
        return redirect("/admin/review")
    if role == "admin":
        return redirect("/admin/analytics")
    return redirect(url_for("admin.admin_login", next=request.path))


def serialize_datetime(value):
    if not value:
        return ""
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%Y-%m-%d : %H:%M:%S")


def format_display_datetime(value, *, label="UTC"):
    """Human-readable timestamp with an explicit timezone label."""
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    utc_value = value.astimezone(timezone.utc)
    formatted = utc_value.strftime("%Y-%m-%d : %H:%M:%S")
    return f"{formatted} {label}" if label else formatted


def format_correctness_score(value):
    if value is None:
        return ""
    return f"{round(float(value), 3):.3f}"


def serialize_json(value):
    return json.dumps(value or [], ensure_ascii=False)


def response_to_row(response):
    participant = response.participant
    qa_item = response.qa_item
    assignment = response.assignment
    question_type = (qa_item.question_type if qa_item else "").strip().lower()
    choice_scored = question_type in {"mcq", "tf"}

    return {
        "response_id": response.id,
        "received_at": serialize_datetime(response.received_at),
        "participant_id": participant.id if participant else "",
        "participant_wa_id": participant.wa_id if participant else "",
        "participant_display_name": participant.display_name if participant else "",
        "qa_item_id": qa_item.id if qa_item else "",
        "passage_id": qa_item.passage_id if qa_item else "",
        "passage_reference": qa_item.passage_reference if qa_item else "",
        "passage_text": qa_item.passage_text if qa_item else "",
        "language": canonical_language_code(participant.target_language if participant else ""),
        "question_text": qa_item.question_text if qa_item else "",
        "expected_answer": qa_item.expected_answer if qa_item else "",
        "required_keywords": serialize_json(qa_item.required_keywords if qa_item else []),
        "assignment_id": assignment.id if assignment else "",
        "batch_id": assignment.batch_id if assignment else "",
        "question_type": qa_item.question_type if qa_item else "",
        "response_type": response.response_type,
        "response_text": response.response_text or "",
        "media_id": "" if choice_scored else (response.media_id or ""),
        "media_url": "" if choice_scored else (response.media_url or ""),
        "transcript_text": "" if choice_scored else (response.transcript_text or ""),
        "normalized_text": "" if choice_scored else (response.normalized_text or ""),
        "correctness_score": (
            "" if choice_scored else format_correctness_score(response.correctness_score)
        ),
        "matched_keywords": (
            "" if choice_scored else serialize_json(response.matched_keywords)
        ),
        "missing_keywords": (
            "" if choice_scored else serialize_json(response.missing_keywords)
        ),
        "is_correct": response.is_correct,
        "flag_reason": response.flag_reason or "",
        "review_status": response.review_status,
    }


def get_responses(flagged_only=False):
    statement = (
        select(ParticipantResponse)
        .options(
            selectinload(ParticipantResponse.participant),
            selectinload(ParticipantResponse.qa_item),
            selectinload(ParticipantResponse.assignment),
        )
        .order_by(ParticipantResponse.received_at.desc())
    )
    if flagged_only:
        statement = statement.where(ParticipantResponse.is_correct == "pending")

    session_factory = get_session_factory()
    with session_factory() as db:
        return db.scalars(statement).all()


def build_csv_response(responses, filename):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for response in responses:
        writer.writerow(response_to_row(response))

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def render_admin_nav(current_path):
    role = session.get("admin_role")
    if not role:
        return ""

    primary_page_links = []
    workflow_page_links = []
    for page in ADMIN_NAV_PAGES:
        if role not in page["roles"]:
            continue
        active_class = " active" if current_path == page["path"] else ""
        link_html = (
            f'<a class="nav-link{active_class}" href="{html.escape(page["path"])}">'
            f'{html.escape(page["label"])}</a>'
        )
        if page["path"] in {"/admin/review", "/admin/review-qa", "/admin/record"}:
            workflow_page_links.append(link_html)
        else:
            primary_page_links.append(link_html)

    export_links = []
    for export in ADMIN_NAV_EXPORTS:
        if role not in export["roles"]:
            continue
        export_links.append(
            f'<a class="nav-link nav-export" href="{html.escape(export["path"])}">'
            f'{html.escape(export["label"])}</a>'
        )

    user_label = session.get("admin_display_name") or session.get("admin_email") or role
    logout_url = html.escape(url_for("admin.admin_logout"))
    languages_url = html.escape(url_for("admin.system_languages_dashboard"))
    languages_active = " active" if current_path == "/admin/system-languages" else ""
    exports_html = ""
    if export_links:
        exports_html = f'<div class="nav-exports">{"".join(export_links)}</div>'

    return f"""
  <header class="admin-header">
    <nav class="admin-nav" aria-label="Admin sections">
      {"".join(primary_page_links)}
    </nav>
    <nav class="admin-nav admin-nav-secondary" aria-label="Review and recording">
      {"".join(workflow_page_links)}
    </nav>
    {exports_html}
    <div class="admin-meta">
      <span class="admin-user">{html.escape(str(user_label))}</span>
      <span class="admin-role">({html.escape(role)})</span>
      <a class="nav-link nav-languages-floating{languages_active}" href="{languages_url}">Languages</a>
      <a class="nav-link nav-logout" href="{logout_url}">Log out</a>
    </div>
  </header>
"""


def render_admin_page(title, sections, current_path=None):
    section_html = "\n".join(sections)
    nav_html = render_admin_nav(current_path or request.path)
    return Response(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; }}
    .admin-header {{ margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid #ddd; }}
    .admin-nav {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem; }}
    .admin-nav-secondary {{ margin-top: -0.25rem; padding-top: 0.25rem; }}
    .response-count-dashboard {{ margin: 1.5rem 0; }}
    .response-count-dashboard .chart-summary {{ margin: 0 0 1rem; color: #444; font-size: 0.95rem; line-height: 1.45; }}
    .response-count-chart {{ display: flex; flex-direction: column; gap: 1rem; }}
    .response-count-row {{
      display: grid;
      grid-template-columns: minmax(11rem, 16rem) minmax(14rem, 1fr) minmax(4.5rem, 6rem);
      gap: 0.75rem 1rem;
      align-items: center;
    }}
    .response-count-label {{ min-width: 0; }}
    .response-count-label .passage {{ font-weight: 600; font-size: 0.9rem; margin-bottom: 0.15rem; }}
    .response-count-label .question {{ font-size: 0.85rem; color: #444; }}
    .response-count-label .question a {{ color: #5b21b6; }}
    .response-count-bar-area {{
      position: relative;
      height: 1rem;
      min-width: 12rem;
      background: #ececec;
      border: 1px solid #ccc;
      border-radius: 4px;
      overflow: visible;
    }}
    .response-count-bar-fill {{
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      min-width: 3px;
      border-radius: 3px 0 0 3px;
      background: #2e7d32;
      z-index: 1;
    }}
    .response-count-bar-fill.below-target {{ background: #e65100; }}
    .response-count-bar-fill.zero {{ min-width: 0; width: 0 !important; }}
    .response-count-min-marker {{
      position: absolute;
      top: -0.2rem;
      bottom: -0.2rem;
      width: 2px;
      background: #c62828;
      z-index: 2;
      transform: translateX(-1px);
    }}
    .response-count-min-marker::before {{
      content: "min";
      position: absolute;
      top: -0.95rem;
      left: 50%;
      transform: translateX(-50%);
      font-size: 0.7rem;
      font-weight: 700;
      color: #c62828;
      white-space: nowrap;
      background: #fafafa;
      padding: 0 0.2rem;
    }}
    .response-count-value {{ font-size: 0.95rem; font-weight: 600; text-align: right; white-space: nowrap; }}
    .response-count-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 1rem 1.5rem;
      font-size: 0.85rem;
      color: #444;
      margin-bottom: 0.25rem;
    }}
    .response-count-legend span {{ display: inline-flex; align-items: center; gap: 0.4rem; }}
    .response-count-legend .swatch-bar {{ width: 1.25rem; height: 0.75rem; border-radius: 3px; background: #2e7d32; display: inline-block; }}
    .response-count-legend .swatch-bar.below {{ background: #e65100; }}
    .response-count-legend .swatch-min {{ width: 0; height: 1rem; border-left: 2px solid #c62828; display: inline-block; }}
    .review-passage-toggle {{
      border: none;
      background: none;
      padding: 0;
      font: inherit;
      color: #5b21b6;
      cursor: pointer;
      text-align: left;
      text-decoration: underline;
      text-underline-offset: 2px;
    }}
    .review-passage-toggle:hover {{ color: #4c1d95; }}
    .review-passage-toggle[aria-expanded="true"] {{ font-weight: 600; }}
    .review-data-row.is-expanded td {{ border-bottom-color: transparent; }}
    .review-passage-detail td {{
      background: #ececec;
      border-top: none;
      padding: 0.65rem 0.75rem;
    }}
    .review-passage-detail-text {{
      font-size: 0.95rem;
      line-height: 1.45;
      color: #222;
      white-space: pre-wrap;
    }}
    .review-passage-empty {{ color: #666; font-style: italic; }}
    .review-qa-tabs, .qa-item-detail-tabs {{
      display: flex; gap: 0.5rem; margin: 0 0 1.25rem; flex-wrap: wrap;
    }}
    .review-qa-tabs .nav-link.active, .qa-item-detail-tabs .nav-link.active {{
      background: #111; color: #fff; border-color: #111;
    }}
    .qa-stats-grid {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
      gap: 0.65rem; margin: 0 0 1.25rem;
    }}
    .qa-stats-card {{
      padding: 0.65rem 0.75rem; background: #f8f8f8; border: 1px solid #e0e0e0;
      border-radius: 6px;
    }}
    .qa-stats-card strong {{ display: block; font-size: 1.35rem; margin-bottom: 0.15rem; }}
    .qa-stats-card span {{ font-size: 0.85rem; color: #444; }}
    .qa-stats-bar-chart {{ margin: 0 0 1.25rem; max-width: 28rem; }}
    .qa-stats-bar-row {{
      display: grid; grid-template-columns: 1.75rem 1fr 2.5rem; gap: 0.5rem;
      align-items: center; margin-bottom: 0.45rem; font-size: 0.9rem;
    }}
    .qa-stats-bar-track {{
      height: 1.25rem; background: #ececec; border-radius: 3px; overflow: hidden;
    }}
    .qa-stats-bar-fill {{
      height: 100%; background: #4a6fa5; border-radius: 3px; min-width: 2px;
    }}
    .qa-stats-bar-fill.is-correct {{ background: #2d6a4f; }}
    .review-qa-chapter {{ margin-bottom: 2rem; }}
    .review-qa-chapter-header {{
      display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
      gap: 0.75rem 1rem; margin-bottom: 0.75rem;
    }}
    .review-qa-chapter-header h3 {{ margin: 0; font-size: 1.05rem; }}
    .review-qa-chapter-actions {{ display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }}
    .review-qa-chapter-count {{ font-size: 0.85rem; color: #555; }}
    .review-qa-item {{
      margin-bottom: 1rem; padding: 1rem; background: #fff;
      border: 1px solid #ddd; border-radius: 6px;
    }}
    .review-qa-item-meta {{ font-size: 0.85rem; color: #555; margin-bottom: 0.75rem; }}
    .review-qa-passage-detail {{
      margin: -0.35rem 0 0.75rem;
      padding: 0.65rem 0.75rem;
      background: #ececec;
      border-radius: 4px;
    }}
    .review-qa-item label {{ display: block; margin: 0.5rem 0 0.25rem; font-weight: 600; }}
    .review-qa-item textarea {{ width: 100%; min-height: 4rem; padding: 0.5rem; font: inherit; }}
    .review-qa-item input[type="text"] {{ width: 100%; padding: 0.5rem; font: inherit; margin-bottom: 0.5rem; }}
    .review-qa-mcq-block {{ margin: 0.75rem 0; padding: 0.75rem; background: #f8f8f8; border-radius: 4px; }}
    .review-qa-mcq-block .review-qa-answer-heading {{
      display: block; margin: 0.5rem 0 0.35rem; font-weight: 600;
    }}
    .review-qa-choice-row {{
      display: flex; flex-wrap: wrap; align-items: flex-end; gap: 0.65rem 1rem;
      margin: 0 0 0.5rem;
    }}
    .review-qa-choice-slot {{
      display: flex; flex-direction: column; gap: 0.3rem; flex: 1 1 9rem; min-width: 7rem;
    }}
    .review-qa-choice-slot .review-qa-choice-label {{
      display: block; margin: 0; font-weight: 600; white-space: nowrap;
    }}
    .review-qa-mcq-block .review-qa-choice-input {{
      width: 100%; min-width: 3.25rem; max-width: 5.5rem; aspect-ratio: 1;
      padding: 0.35rem 0.4rem; font: inherit; margin: 0;
      border: 1px solid #bbb; border-radius: 3px; background: #fff; box-sizing: border-box;
      resize: none; overflow: auto;
    }}
    .review-qa-correct-picker {{
      display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.75rem;
      margin-top: 0.35rem;
    }}
    .review-qa-correct-picker label {{ margin: 0; }}
    .review-qa-correct-picker select {{
      min-width: 5rem; max-width: 8rem; padding: 0.4rem 0.35rem; font: inherit; margin: 0;
    }}
    .review-qa-item-actions {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem; }}
    .review-qa-reviewed-table td {{ vertical-align: top; }}
    .review-qa-reviewed-table .review-qa-item-actions {{ margin-top: 0; flex-direction: row; flex-wrap: wrap; align-items: center; }}
    .review-qa-removed-table td {{ vertical-align: top; }}
    .nav-exports {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem; }}
    .nav-link {{
      display: inline-block;
      padding: 0.4rem 0.75rem;
      border: 1px solid #ccc;
      border-radius: 4px;
      background: #f8f8f8;
      color: #111;
      text-decoration: none;
      font-size: 0.95rem;
    }}
    .nav-link:hover {{ background: #eee; }}
    .nav-link.active {{ background: #111; color: #fff; border-color: #111; }}
    .nav-export {{ font-size: 0.85rem; }}
    .admin-meta {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; font-size: 0.9rem; color: #444; }}
    .nav-logout {{ margin-left: auto; }}
    .nav-languages-floating {{
      position: fixed;
      top: 1rem;
      right: 1rem;
      z-index: 1000;
    }}
    .back-link {{ display: inline-block; margin-bottom: 1rem; }}
    .detail-panel {{ margin-bottom: 2rem; padding: 1rem; background: #fafafa; border: 1px solid #e5e5e5; border-radius: 6px; }}
    .detail-panel h2 {{ margin: 0 0 0.75rem; font-size: 1.1rem; }}
    .detail-list {{ display: grid; grid-template-columns: 12rem 1fr; gap: 0.35rem 1rem; margin: 0; }}
    .detail-list dt {{ font-weight: 600; margin: 0; }}
    .detail-list dd {{ margin: 0; }}
    .response-audio {{ display: flex; flex-direction: column; gap: 0.35rem; min-width: 12rem; }}
    .response-audio audio {{ width: min(320px, 100%); height: 2rem; }}
    .response-audio .audio-meta {{ font-size: 0.82rem; color: #555; word-break: break-all; }}
    .response-audio .audio-links {{ display: flex; flex-wrap: wrap; gap: 0.5rem; font-size: 0.85rem; }}
    .recording-takes {{ display: flex; flex-direction: column; gap: 0.75rem; min-width: 12rem; }}
    .recording-take {{
      display: flex; flex-direction: column; gap: 0.35rem;
      padding: 0.5rem 0.6rem; border: 1px solid #e0e0e0; border-radius: 6px; background: #fafafa;
    }}
    .recording-take-header {{ display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; flex-wrap: wrap; }}
    .recording-take-label {{ font-size: 0.85rem; font-weight: 600; color: #333; }}
    .recording-take-actions {{ display: flex; flex-wrap: wrap; gap: 0.35rem; }}
    .recording-take-actions .nav-link-remove {{ color: #9b1c1c; border-color: #e8b4b4; }}
    table thead th {{ overflow: visible; position: relative; vertical-align: bottom; }}
    .th-info-wrap {{ position: relative; display: inline-flex; align-items: center; gap: 0.35rem; white-space: nowrap; }}
    .th-info-btn {{
      display: inline-flex; align-items: center; justify-content: center;
      width: 1rem; height: 1rem; border-radius: 50%;
      border: 1px solid #666; font-size: 0.68rem; font-weight: 700; font-style: italic;
      color: #444; background: #fff; cursor: help; padding: 0; line-height: 1;
    }}
    .th-info-tooltip {{
      display: none; position: absolute; left: 0; top: calc(100% + 0.35rem); z-index: 200;
      min-width: 12rem; max-width: 18rem; padding: 0.5rem 0.6rem;
      border-radius: 4px; background: #222; color: #fff;
      font-size: 0.78rem; font-weight: 400; font-style: normal; line-height: 1.35;
      text-align: left; white-space: normal; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    }}
    .th-info-wrap:hover .th-info-tooltip,
    .th-info-wrap:focus-within .th-info-tooltip {{ display: block; }}
    .review-keywords {{ line-height: 1.45; }}
    .review-answer-text {{ max-width: 28rem; line-height: 1.45; white-space: pre-wrap; word-break: break-word; }}
    .review-transcript-details {{ margin-top: 0.15rem; }}
    .review-transcript-summary {{
      display: inline-flex; align-items: center; gap: 0.35rem;
      cursor: pointer; font-size: 0.85rem; font-weight: 600; color: #333;
      list-style: none; user-select: none;
    }}
    .review-transcript-summary::-webkit-details-marker {{ display: none; }}
    .review-transcript-summary::before {{
      content: "▸"; font-size: 0.75rem; color: #666; transition: transform 0.12s ease;
    }}
    .review-transcript-details[open] .review-transcript-summary::before {{
      transform: rotate(90deg);
    }}
    .review-transcript-panel {{
      margin-top: 0.35rem; padding: 0.5rem 0.6rem; max-width: 28rem;
      border-radius: 4px; background: #f5f5f5; border: 1px solid #e0e0e0;
      font-size: 0.85rem; line-height: 1.45; color: #333;
      white-space: pre-wrap; word-break: break-word;
    }}
    .audio-export-toolbar {{ display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-bottom: 1rem; }}
    .audio-export-group {{ margin-bottom: 0.75rem; border: 1px solid #e0e0e0; border-radius: 6px; background: #fff; }}
    .audio-export-group.audio-export-chapter {{ margin-bottom: 1.25rem; }}
    .audio-export-group.audio-export-qa {{ margin-left: 1rem; border-style: dashed; background: #fafafa; }}
    .audio-export-group-header {{ display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; padding: 0.75rem 1rem; }}
    .audio-export-group-header label {{ display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin: 0; flex: 1 1 12rem; }}
    .audio-export-group.is-collapsed > .audio-export-group-body {{ display: none; }}
    .audio-export-group-body {{ padding: 0 1rem 0.75rem; }}
    .group-toggle {{ min-width: 1.25rem; padding: 0.1rem 0.25rem; font-size: 0.65rem; line-height: 1; }}
    .audio-export-responses {{ margin: 0; padding-left: 1rem; list-style: none; }}
    .audio-export-responses li {{ margin-bottom: 0.65rem; }}
    .audio-export-response-row {{ display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; align-items: center; }}
    .audio-export-response-row .export-filename {{ font-family: monospace; font-size: 0.85rem; color: #333; }}
    .audio-export-response-row.is-disabled {{ opacity: 0.55; }}
    .admin-form label {{ display: block; margin: 0.75rem 0 0.25rem; font-weight: 600; }}
    .json-label-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.75rem; margin-top: 0.75rem; }}
    .json-label-row label {{ margin: 0; }}
    .json-input-wrap {{ position: relative; margin-top: 0.25rem; }}
    .json-input-hint {{
      position: absolute;
      inset: 0;
      padding: 0.5rem;
      font-family: monospace;
      font-size: 0.8rem;
      line-height: 1.35;
      color: #666;
      opacity: 0.5;
      pointer-events: none;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      z-index: 0;
    }}
    .json-input-hint.is-hidden {{ display: none; }}
    .json-input-wrap textarea {{
      position: relative;
      z-index: 1;
      width: 100%;
      min-height: 12rem;
      padding: 0.5rem;
      font-family: monospace;
      background: transparent;
    }}
    .admin-form input[type="file"] {{ margin: 0.25rem 0 0.75rem; }}
    .admin-form .checkbox {{ font-weight: normal; }}
    .admin-form button {{ margin-top: 0.75rem; }}
    .admin-form select {{ width: 100%; max-width: 28rem; padding: 0.5rem; }}
    .admin-form input[type="number"] {{ width: 100%; max-width: 10rem; padding: 0.5rem; }}
    .admin-form .field-hint {{ margin: 0.25rem 0 0.75rem; font-size: 0.9rem; color: #555; font-weight: normal; }}
    .admin-form .settings-section {{ margin-top: 1.25rem; padding-top: 1.25rem; border-top: 1px solid #e5e5e5; }}
    .admin-form .settings-section h3 {{ margin: 0 0 0.75rem; font-size: 1rem; }}
    .admin-form .keyword-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1rem; margin-bottom: 0.5rem; }}
    .admin-form .keyword-row input[type="text"] {{ flex: 1; min-width: 12rem; max-width: 28rem; padding: 0.5rem; }}
    .admin-form .keyword-remove {{ font-size: 0.9rem; color: #555; font-weight: normal; }}
    .admin-form .keyword-add {{ margin-top: 0.5rem; }}
    .admin-form .keyword-add input[type="text"] {{ width: 100%; max-width: 28rem; padding: 0.5rem; }}
    .keyword-record-panel {{ font-size: 0.9rem; }}
    .keyword-record-section {{ margin-bottom: 0.75rem; }}
    .keyword-record-section h4 {{ margin: 0 0 0.35rem; font-size: 0.85rem; }}
    .keyword-record-list {{ list-style: none; padding: 0; margin: 0; }}
    .keyword-record-item {{ margin-bottom: 0.75rem; padding-bottom: 0.5rem; border-bottom: 1px solid #eee; }}
    .keyword-record-item:last-child {{ border-bottom: none; }}
    .keyword-record-label {{ font-weight: 600; display: block; margin-bottom: 0.25rem; }}
    .keyword-record-empty {{ color: #666; font-style: italic; }}
    .record-answer-panel .keyword-record-item {{
      display: flex; flex-wrap: wrap; align-items: flex-start; gap: 0.5rem 1rem;
    }}
    .record-answer-panel .keyword-record-label {{
      flex: 1 1 10rem; margin: 0; min-width: 8rem;
    }}
    .record-answer-panel .record-answer-controls {{
      display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.75rem;
      flex: 1 1 12rem; min-width: 10rem;
    }}
    .record-answer-panel .record-answer-controls audio {{ max-width: 14rem; }}
    .keyword-translations {{ margin-bottom: 0.5rem; }}
    .keyword-translation-list {{ list-style: none; padding: 0; margin: 0 0 0.35rem; }}
    .keyword-translation-item {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem; }}
    .keyword-translation-text {{ flex: 1; }}
    .keyword-translation-form {{ display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; }}
    .keyword-translation-form input[type="text"] {{ flex: 1; min-width: 10rem; padding: 0.35rem 0.5rem; }}
    .keyword-translation-empty {{ color: #666; font-style: italic; font-size: 0.85rem; margin-bottom: 0.35rem; }}
    .status-banner {{ padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 1rem; }}
    .status-banner.success {{ background: #e8f5e9; color: #1b5e20; }}
    .status-banner.error {{ background: #ffebee; color: #b71c1c; }}
    .btn-danger {{ background: #b00020; color: #fff; border-color: #b00020; }}
    .btn-danger:hover {{ background: #8c0019; }}
    .actions {{ white-space: nowrap; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    code {{ background: #f5f5f5; padding: 0.1rem 0.25rem; }}
  </style>
</head>
<body>
  {nav_html}
  <h1>{html.escape(title)}</h1>
  {section_html}
</body>
</html>""",
        mimetype="text/html",
    )


def table_column_key(column):
    return column[0]


def table_column_label(column):
    return column[1]


def table_column_header_is_html(column):
    return len(column) > 2 and bool(column[2])


def render_table(columns, rows, html_safe_keys=None):
    safe_html_keys = set(html_safe_keys or ())
    header_parts = []
    for column in columns:
        label = table_column_label(column)
        if table_column_header_is_html(column):
            header_parts.append(f"<th>{label}</th>")
        else:
            header_parts.append(f"<th>{html.escape(label)}</th>")
    header = "".join(header_parts)
    body_rows = []
    for row in rows:
        cells = []
        for column in columns:
            key = table_column_key(column)
            value = row.get(key, "")
            if value is None:
                value = ""
            if key in safe_html_keys:
                cell_content = str(value)
            else:
                cell_content = html.escape(str(value))
            cells.append(f"<td>{cell_content}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    body = "\n".join(body_rows) or (
        f"<tr><td colspan=\"{len(columns)}\">No records found.</td></tr>"
    )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def truncate_text(value, max_length=120):
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def render_status_banner(message, level="success"):
    if not message:
        return ""
    return f'<p class="status-banner {html.escape(level)}">{html.escape(message)}</p>'


def get_uw_json_import_example():
    example_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "supabase",
        "seeds",
        "data",
        "uw_luke_1_2_174314.json",
    )
    if os.path.exists(example_path):
        with open(example_path, encoding="utf-8") as example_file:
            return example_file.read().strip()

    return json.dumps(
        {
            "content_id": "174314",
            "reference_id": 128899,
            "version": "1.0.2",
            "title": "Luke 1:2",
            "passage_text": "even as those who from the beginning were eyewitnesses and servants of the word delivered them to us,",
            "media_type": "Text",
            "index_reference": "42001002",
            "language": "eng",
            "review_level": "None",
            "content": (
                "<p><strong>Who were the “eyewitnesses” that Luke mentions?</strong></p>"
                "<p>The “eyewitnesses” were the ones who were with the apostles "
                "from the beginning of Jesus’ ministry.</p>"
            ),
            "associations": {
                "passage": [
                    {
                        "start_ref": "42001002",
                        "start_ref_usfm": "LUK 1:2",
                        "end_ref": "42001002",
                        "end_ref_usfm": "LUK 1:2",
                    }
                ],
                "resource": [],
                "acai": [],
            },
        },
        indent=2,
    )


QA_JSON_INPUT_HINT = (
    '[{"passage_id": "luke-2-3", "passage_reference": "Luke 2:3", '
    '"passage_text": "...", "question_type": "open", "question_text": "...", '
    '"content": "<question>Stem\\\\n\\\\nA. ...\\\\nB. ...\\\\nC. ...\\\\nD. ...'
    '<question><answer>B<answer>", "question_type": "mcq"}'
)


def parse_qa_import_form_defaults():
    min_responses_raw = request.form.get("import_min_responses_required", "").strip()
    review_priority_raw = request.form.get("import_review_priority", "").strip()

    try:
        min_responses_required = int(min_responses_raw or "3")
    except ValueError as exc:
        raise ValueError("Min responses required must be a whole number") from exc

    if min_responses_required < 1:
        raise ValueError("Min responses required must be at least 1")

    try:
        review_priority = int(review_priority_raw or "0")
    except ValueError as exc:
        raise ValueError("Review priority must be a whole number") from exc

    return {
        "min_responses_required": min_responses_required,
        "review_priority": review_priority,
        "active": request.form.get("import_active") == "1",
    }


def render_qa_import_form():
    json_template = get_uw_json_import_example()
    template_js = json.dumps(json_template)
    hint_html = html.escape(QA_JSON_INPUT_HINT)
    return f"""
  <section class="detail-panel admin-form">
    <h2>Add questions (JSON)</h2>
    <form method="post" action="{html.escape(url_for('admin.qa_items_import'))}" enctype="multipart/form-data">
      <div class="settings-section">
        <h3>Defaults for imported questions</h3>
        <p class="field-hint">These apply to every entry in this upload.</p>
        <label for="import_min_responses_required">Min responses required</label>
        <input
          id="import_min_responses_required"
          name="import_min_responses_required"
          type="number"
          min="1"
          step="1"
          value="3"
          required
        >
        <label for="import_review_priority">Review priority</label>
        <input
          id="import_review_priority"
          name="import_review_priority"
          type="number"
          step="1"
          value="0"
          required
        >
        <p class="field-hint">Higher values are preferred sooner when auto-assigning the next question.</p>
        <label class="checkbox">
          <input type="checkbox" name="import_active" value="1" checked>
          Active (include in auto-assignment)
        </label>
      </div>
      <label for="json_file">Upload JSON file</label>
      <input id="json_file" type="file" name="json_file" accept=".json,application/json">
      <div class="json-label-row">
        <label for="json_text">Or paste JSON</label>
        <button type="button" class="nav-link" id="paste_json_template">Paste template</button>
      </div>
      <div class="json-input-wrap">
        <div class="json-input-hint" id="json_text_hint" aria-hidden="true">{hint_html}</div>
        <textarea id="json_text" name="json_text" spellcheck="false"></textarea>
      </div>
      <script>
        (function () {{
          const textarea = document.getElementById("json_text");
          const hint = document.getElementById("json_text_hint");
          const template = {template_js};

          function syncHint() {{
            const hasValue = textarea.value.trim().length > 0;
            hint.classList.toggle("is-hidden", hasValue);
            hint.setAttribute("aria-hidden", hasValue ? "true" : "false");
          }}

          textarea.addEventListener("input", syncHint);
          document.getElementById("paste_json_template").addEventListener("click", function () {{
            textarea.value = template;
            syncHint();
            textarea.focus();
          }});
          syncHint();
        }})();
      </script>
      <label class="checkbox">
        <input type="checkbox" name="skip_existing" value="1" checked>
        Skip entries whose <code>passage_id</code> already exists
      </label>
      <button type="submit">Import questions</button>
    </form>
  </section>
"""


def render_qa_items_table(rows):
    header = (
        '<th><input type="checkbox" id="qa-items-select-all" aria-label="Select all QA items"></th>'
        "<th>Passage</th><th>Question</th><th>Question type</th><th>Review status</th>"
        "<th>Responses</th><th>Flagged</th><th>Avg score</th>"
        "<th>Min required</th><th>Review priority</th><th>Active</th><th>Actions</th>"
    )
    body_rows = []
    for row in rows:
        detail_url = html.escape(url_for("admin.qa_item_detail", qa_item_id=row["id"]))
        assign_url = html.escape(f"{url_for('admin.qa_item_detail', qa_item_id=row['id'])}#assign")
        delete_url = html.escape(url_for("admin.qa_item_delete", qa_item_id=row["id"]))
        question_label = html.escape(truncate_text(row["question"], 100))
        body_rows.append(
            f"<tr>"
            f'<td><input type="checkbox" class="qa-item-selector" value="{html.escape(str(row["id"]))}" aria-label="Select QA item"></td>'
            f"<td>{html.escape(str(row.get('passage', '')))}</td>"
            f'<td><a href="{detail_url}">{question_label}</a></td>'
            f"<td>{html.escape(str(row.get('question_type', 'open')))}</td>"
            f"<td>{html.escape(str(row.get('review_status', '')))}</td>"
            f"<td>{html.escape(str(row.get('response_count', '')))}</td>"
            f"<td>{html.escape(str(row.get('flagged_count', '')))}</td>"
            f"<td>{html.escape(str(row.get('average_score', '')))}</td>"
            f"<td>{html.escape(str(row.get('min_responses', '')))}</td>"
            f"<td>{html.escape(str(row.get('review_priority', '')))}</td>"
            f"<td>{html.escape(str(row.get('active', '')))}</td>"
            f'<td class="actions">'
            f'<a href="{assign_url}" class="nav-link">Assign</a>'
            f'<form method="post" action="{delete_url}" style="display:inline" '
            f'onsubmit="return confirm(\'Delete this question and all related assignments/responses?\');">'
            f'<button type="submit" class="nav-link btn-danger">Delete</button>'
            f"</form></td>"
            f"</tr>"
        )

    body = "\n".join(body_rows) or '<tr><td colspan="12">No records found.</td></tr>'
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def render_qa_items_bulk_actions(participants):
    assign_options = ['<option value="">Select participant for assignment</option>']
    for participant in participants:
        label = participant.display_name or participant.wa_id
        language = participant.target_language or "any"
        assign_options.append(
            f'<option value="{html.escape(participant.id)}">'
            f"{html.escape(label)} ({html.escape(participant.wa_id)}, {html.escape(language)})"
            f"</option>"
        )

    action_url = html.escape(url_for("admin.qa_items_bulk_action"))
    return f"""
<section class="admin-form" id="qa-items-bulk-section" style="display:none">
  <form method="post" action="{action_url}" id="qa-items-bulk-form">
    <input type="hidden" name="selected_qa_item_ids" id="selected_qa_item_ids" value="">
    <label for="bulk_participant_id">Participant (for assign)</label>
    <select id="bulk_participant_id" name="participant_id">
      {"".join(assign_options)}
    </select>
    <div class="actions">
      <button type="submit" name="action" value="assign">Assign selected</button>
      <button
        type="submit"
        name="action"
        value="delete"
        class="btn-danger"
        data-confirm="Delete selected questions and all related assignments/responses?"
      >Delete selected</button>
    </div>
  </form>
</section>
"""


def render_qa_items_bulk_script():
    return """
<script>
  (function () {
    function initQaItemsBulkActions() {
      const bulkForm = document.getElementById("qa-items-bulk-form");
      const bulkSection = document.getElementById("qa-items-bulk-section");
      const hiddenInput = document.getElementById("selected_qa_item_ids");
      const rowCheckboxes = Array.from(document.querySelectorAll(".qa-item-selector"));
      const selectAllCheckbox = document.getElementById("qa-items-select-all");
      if (!bulkForm || !bulkSection || !hiddenInput || !selectAllCheckbox || rowCheckboxes.length === 0) {
        return;
      }

      function selectedIds() {
        return rowCheckboxes
          .filter(function (checkbox) { return checkbox.checked; })
          .map(function (checkbox) { return checkbox.value; });
      }

      function syncSelectAllState() {
        const selectedCount = selectedIds().length;
        bulkSection.style.display = selectedCount > 1 ? "" : "none";
        selectAllCheckbox.checked = selectedCount === rowCheckboxes.length;
        selectAllCheckbox.indeterminate =
          selectedCount > 0 && selectedCount < rowCheckboxes.length;
      }

      rowCheckboxes.forEach(function (checkbox) {
        checkbox.addEventListener("change", syncSelectAllState);
      });

      selectAllCheckbox.addEventListener("change", function () {
        rowCheckboxes.forEach(function (checkbox) {
          checkbox.checked = selectAllCheckbox.checked;
        });
        syncSelectAllState();
      });

      bulkForm.addEventListener("submit", function (event) {
        const selected = selectedIds();
        if (selected.length === 0) {
          event.preventDefault();
          alert("Select at least one QA item.");
          return;
        }
        hiddenInput.value = selected.join(",");
        const submitter = event.submitter;
        const confirmMessage = submitter ? submitter.getAttribute("data-confirm") : "";
        if (confirmMessage && !window.confirm(confirmMessage)) {
          event.preventDefault();
        }
      });

      syncSelectAllState();
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initQaItemsBulkActions);
    } else {
      initQaItemsBulkActions();
    }
  })();
</script>
"""


def format_keyword_list(keywords):
    if not keywords:
        return ""
    return ", ".join(str(keyword) for keyword in keywords)


def render_review_keywords_header():
    tooltip = "Bold keywords are required for a correct answer. Non-bold keywords are optional."
    safe_tooltip = html.escape(tooltip)
    return (
        '<span class="th-info-wrap">'
        "Keywords "
        f'<button type="button" class="th-info-btn" aria-label="{safe_tooltip}" '
        f'title="{safe_tooltip}">i</button>'
        f'<span class="th-info-tooltip" role="tooltip">{safe_tooltip}</span>'
        "</span>"
    )


def render_review_keywords_cell(qa_item, language_keywords_row=None):
    if not qa_item:
        return '<span class="audio-meta">—</span>'

    if language_keywords_row:
        required = [
            str(keyword).strip()
            for keyword in (language_keywords_row.required_keywords or [])
            if str(keyword).strip()
        ]
        optional = [
            str(keyword).strip()
            for keyword in (language_keywords_row.optional_keywords or [])
            if str(keyword).strip()
        ]
    else:
        required = [
            str(keyword).strip()
            for keyword in (qa_item.required_keywords or [])
            if str(keyword).strip()
        ]
        optional = [
            str(keyword).strip()
            for keyword in (qa_item.optional_keywords or [])
            if str(keyword).strip()
        ]

    if not required and not optional:
        return '<span class="audio-meta">—</span>'

    parts = [f"<strong>{html.escape(keyword)}</strong>" for keyword in required]
    parts.extend(html.escape(keyword) for keyword in optional)
    return f'<span class="review-keywords">{", ".join(parts)}</span>'


def review_transcript_placeholder(response):
    existing = (response.transcript_text or "").strip()
    if existing:
        return existing
    return (
        "[Transcript pending — automatic transcription from audio is not available yet. "
        "This placeholder will be replaced with the inferred transcript.]"
    )


def render_review_transcript_toggle(response):
    transcript_text = review_transcript_placeholder(response)
    safe_text = html.escape(transcript_text)
    return (
        '<details class="review-transcript-details">'
        '<summary class="review-transcript-summary">Transcript</summary>'
        f'<div class="review-transcript-panel" role="note">{safe_text}</div>'
        "</details>"
    )


def render_review_answer_cell(response):
    response_type = (response.response_type or "").lower()
    if response_type == "audio":
        audio_html = render_response_audio_cell(response)
        if audio_html:
            return (
                '<div class="review-answer-block">'
                f"{audio_html}"
                f"{render_review_transcript_toggle(response)}"
                "</div>"
            )

    text = (response.transcript_text or response.response_text or "").strip()
    if text:
        return f'<div class="review-answer-text">{html.escape(text)}</div>'

    if response_type == "audio":
        audio_html = render_response_audio_cell(response) or '<span class="audio-meta">—</span>'
        return (
            '<div class="review-answer-block">'
            f"{audio_html}"
            f"{render_review_transcript_toggle(response)}"
            "</div>"
        )

    return '<span class="audio-meta">—</span>'


def render_response_audio_cell(response):
    if (response.response_type or "").lower() != "audio":
        return ""

    media_url = response.media_url or ""
    media_id = response.media_id or ""
    if not media_url:
        if media_id:
            return (
                '<div class="response-audio">'
                f'<span class="audio-meta">No stored file (Meta media id: {html.escape(media_id)})</span>'
                "</div>"
            )
        return ""

    if not is_supabase_storage_configured() or not parse_storage_uri(media_url):
        reason = (
            "Storage not configured"
            if not is_supabase_storage_configured()
            else "No stored file"
        )
        return (
            '<div class="response-audio">'
            f'<span class="audio-meta">{html.escape(reason)}</span>'
            "</div>"
        )

    playback_url = participant_response_media_url(response.id)
    download_url = participant_response_media_url(response.id, download=True)
    safe_playback_url = html.escape(playback_url, quote=True)
    safe_download_url = html.escape(download_url, quote=True)
    return (
        '<div class="response-audio">'
        f'<audio controls preload="none" src="{safe_playback_url}"></audio>'
        '<div class="audio-links">'
        f'<a href="{safe_playback_url}" target="_blank" rel="noopener">Open</a>'
        f'<a href="{safe_download_url}">Download</a>'
        "</div>"
        "</div>"
    )


def compute_qa_item_metrics(qa_item, responses):
    total_responses = len(responses)
    flagged_count = sum(
        1 for response in responses if response.is_correct in {"pending", "no (expert)"}
    )
    scored_responses = [
        response.correctness_score
        for response in responses
        if response.correctness_score is not None
    ]
    average_score = (
        format_correctness_score(sum(scored_responses) / len(scored_responses))
        if scored_responses
        else ""
    )
    return {
        "total_responses": total_responses,
        "flagged_count": flagged_count,
        "flag_rate": round(flagged_count / total_responses, 3) if total_responses else "",
        "average_score": average_score,
        "scored_count": len(scored_responses),
        "meets_min_responses": total_responses >= qa_item.min_responses_required,
        "responses_needed": max(qa_item.min_responses_required - total_responses, 0),
    }


OPEN_RESPONSE_STATUS_LABELS = {
    "pending": "Pending",
    "yes (auto)": "Auto-correct",
    "no (auto)": "Auto-incorrect",
    "yes (expert)": "Expert-correct",
    "no (expert)": "Expert-incorrect",
}


def open_response_status_label(is_correct: str) -> str:
    value = (is_correct or "").strip().lower()
    return OPEN_RESPONSE_STATUS_LABELS.get(value, is_correct or "Unknown")


def qa_item_detail_tab_url(qa_item_id, tab, selected_languages=None):
    params = {"tab": tab}
    if selected_languages:
        params["languages"] = selected_languages
    return url_for("admin.qa_item_detail", qa_item_id=qa_item_id, **params)


def render_qa_item_detail_tabs(qa_item_id, active_tab, selected_languages):
    valid_tabs = {"overview", "stats"}
    active_tab = active_tab if active_tab in valid_tabs else "overview"
    tabs = [
        ("overview", "Overview"),
        ("stats", "Response statistics"),
    ]
    links = []
    for tab_id, label in tabs:
        active_class = " active" if tab_id == active_tab else ""
        href = html.escape(
            qa_item_detail_tab_url(qa_item_id, tab_id, selected_languages)
        )
        links.append(
            f'<a class="nav-link{active_class}" href="{href}">{html.escape(label)}</a>'
        )
    return (
        f'<nav class="qa-item-detail-tabs" aria-label="QA item tabs">{"".join(links)}</nav>'
    )


def compute_qa_item_response_stats(qa_item, responses):
    question_type = (qa_item.question_type or QUESTION_TYPE_OPEN).strip().lower()
    total = len(responses)
    stats = {
        "question_type": question_type,
        "total_responses": total,
        "summary_cards": [],
        "bar_chart": [],
    }

    if question_type == QUESTION_TYPE_OPEN:
        counts = {label: 0 for label in OPEN_RESPONSE_STATUS_LABELS.values()}
        for response in responses:
            label = open_response_status_label(response.is_correct)
            counts[label] = counts.get(label, 0) + 1
        stats["summary_cards"] = [
            (label, counts.get(label, 0)) for label in OPEN_RESPONSE_STATUS_LABELS.values()
        ]
        if counts.get("Unknown", 0):
            stats["summary_cards"].append(("Unknown", counts["Unknown"]))
        return stats

    correct = 0
    incorrect = 0
    for response in responses:
        if format_choice_correctness_label(response.is_correct) == "correct":
            correct += 1
        else:
            incorrect += 1
    stats["summary_cards"] = [("Correct", correct), ("Incorrect", incorrect)]

    if question_type == QUESTION_TYPE_MCQ:
        letters = list(choice_letters_for_type(QUESTION_TYPE_MCQ))
        distribution = {letter: 0 for letter in letters}
        unparsed = 0
        for response in responses:
            letter = format_choice_response_answer_display(qa_item, response)
            if letter in distribution:
                distribution[letter] += 1
            else:
                unparsed += 1
        stats["bar_chart"] = [(letter, distribution[letter]) for letter in letters]
        if unparsed:
            stats["bar_chart"].append(("—", unparsed))
        correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
        stats["bar_chart_correct_letter"] = correct_letter

    return stats


def render_qa_stats_summary_cards(cards):
    if not cards:
        return '<p class="field-hint">No responses in the selected language scope.</p>'
    items = []
    for label, count in cards:
        items.append(
            f"""
      <div class="qa-stats-card">
        <strong>{html.escape(str(count))}</strong>
        <span>{html.escape(label)}</span>
      </div>"""
        )
    return f'<div class="qa-stats-grid">{"".join(items)}</div>'


def render_qa_stats_bar_chart(bar_rows, correct_letter=None):
    if not bar_rows:
        return ""
    max_count = max(count for _, count in bar_rows) or 1
    rows = []
    for letter, count in bar_rows:
        width_pct = round(100 * count / max_count, 1) if max_count else 0
        fill_class = "qa-stats-bar-fill"
        if correct_letter and letter == correct_letter:
            fill_class += " is-correct"
        rows.append(
            f"""
      <div class="qa-stats-bar-row">
        <span>{html.escape(letter)}</span>
        <div class="qa-stats-bar-track">
          <div class="{fill_class}" style="width:{width_pct}%"></div>
        </div>
        <span>{html.escape(str(count))}</span>
      </div>"""
        )
    return (
        '<div class="qa-stats-bar-chart" role="img" '
        'aria-label="Answer choice distribution">'
        f'{"".join(rows)}</div>'
    )


def build_qa_item_participant_response_rows(qa_item, responses, *, include_audio=False):
    choice_scored = qa_item_is_choice_scored(qa_item)
    rows = []
    for response in responses:
        participant = response.participant
        participant_label = ""
        if participant:
            participant_label = participant.display_name or participant.wa_id
        if choice_scored:
            correctness = format_choice_correctness_label(response.is_correct)
            answer_value = format_choice_response_answer_display(qa_item, response)
        else:
            correctness = open_response_status_label(response.is_correct)
            answer_value = truncate_text(
                response.transcript_text or response.response_text or "",
                80,
            )
        row = {
            "participant": participant_label,
            "language": response_language_for_qa(response),
            "received_at": serialize_datetime(response.received_at),
            "response_type": response.response_type,
            "answer": answer_value,
            "correctness": correctness,
        }
        if include_audio and not choice_scored:
            row["recording"] = render_response_audio_cell(response)
        rows.append(row)
    return rows, choice_scored


def render_qa_item_stats_panel(qa_item, responses):
    stats = compute_qa_item_response_stats(qa_item, responses)
    question_type = stats["question_type"]
    summary_html = render_qa_stats_summary_cards(stats["summary_cards"])

    chart_html = ""
    if question_type == QUESTION_TYPE_MCQ:
        chart_html = (
            '<h3>Answer distribution</h3>'
            + render_qa_stats_bar_chart(
                stats["bar_chart"],
                correct_letter=stats.get("bar_chart_correct_letter"),
            )
        )

    participant_rows, choice_scored = build_qa_item_participant_response_rows(
        qa_item, responses
    )
    participant_columns = [
        ("participant", "Participant"),
        ("language", "Language"),
        ("received_at", "Response time"),
        ("response_type", "Type"),
        ("answer", "Answer"),
        ("correctness", "Correctness"),
    ]
    participants_table = render_table(participant_columns, participant_rows)

    type_hint = html.escape(question_type)
    return f"""
  <section class="detail-panel">
    <h2>Response statistics</h2>
    <p class="field-hint">Question type: <strong>{type_hint}</strong> · {stats["total_responses"]} response(s) in the selected language scope.</p>
    {summary_html}
    {chart_html}
    <h3>Participants ({len(participant_rows)})</h3>
    {participants_table}
  </section>
"""


def canonical_language_code(language_value):
    value = (language_value or "").strip()
    if not value:
        return ""
    try:
        return normalize_language_code(value).lower()
    except QAImportError:
        return value.lower()


def participant_language_for_qa(participant):
    participant_language = canonical_language_code(
        participant.target_language if participant else ""
    )
    return participant_language


def response_language_for_qa(response):
    participant = response.participant
    return participant_language_for_qa(participant)


def ensure_system_languages_table(db):
    SystemLanguage.__table__.create(bind=db.get_bind(), checkfirst=True)


def upsert_system_language(db, language_code, source):
    normalized = canonical_language_code(language_code)
    if not normalized:
        return
    ensure_system_languages_table(db)
    entry = db.get(SystemLanguage, normalized)
    if entry is None:
        entry = SystemLanguage(code=normalized)
        db.add(entry)
        db.flush()
    if source == "participant":
        entry.seen_in_participants = True
    if source == "recording":
        entry.seen_in_recordings = True


def sync_system_languages_registry(db):
    ensure_system_languages_table(db)
    participant_languages = db.scalars(select(Participant.target_language)).all()
    for language in participant_languages:
        upsert_system_language(db, language, "participant")

    recording_languages = db.scalars(select(QAItemRecording.language)).all()
    for language in recording_languages:
        upsert_system_language(db, language, "recording")

    db.flush()


def get_registered_system_languages(db):
    ensure_system_languages_table(db)
    return db.scalars(select(SystemLanguage.code).order_by(SystemLanguage.code)).all()


def parse_selected_languages(raw_values, fallback_language):
    parsed = []
    seen = set()
    for raw_value in raw_values or []:
        normalized = canonical_language_code(raw_value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        parsed.append(normalized)

    if parsed:
        return parsed

    fallback = canonical_language_code(fallback_language)
    return [fallback] if fallback else []


def get_qa_item_responses(qa_item_id):
    statement = (
        select(ParticipantResponse)
        .where(ParticipantResponse.qa_item_id == qa_item_id)
        .options(
            selectinload(ParticipantResponse.participant),
            selectinload(ParticipantResponse.qa_item),
        )
        .order_by(ParticipantResponse.received_at.desc())
    )
    session_factory = get_session_factory()
    with session_factory() as db:
        return db.scalars(statement).all()


def get_qa_item_assignments(qa_item_id):
    statement = (
        select(Assignment)
        .where(Assignment.qa_item_id == qa_item_id)
        .options(selectinload(Assignment.participant))
        .order_by(Assignment.assigned_at.desc())
    )
    session_factory = get_session_factory()
    with session_factory() as db:
        return db.scalars(statement).all()


def render_qa_item_language_filter(
    qa_item_id, language_options, selected_languages, active_tab="overview"
):
    safe_options = []
    selected_lookup = set(selected_languages or [])
    for language in language_options:
        safe_language = html.escape(language)
        selected_attr = " selected" if language in selected_lookup else ""
        safe_options.append(
            f'<option value="{safe_language}"{selected_attr}>{safe_language}</option>'
        )
    details_url = html.escape(url_for("admin.qa_item_detail", qa_item_id=qa_item_id))
    safe_tab = html.escape(active_tab if active_tab in {"overview", "stats"} else "overview")
    return f"""
  <section class="detail-panel admin-form">
    <h2>Target Language(s)</h2>
    <p class="field-hint">This filters all information on both tabs: overview, statistics, assignments, and responses.</p>
    <form method="get" action="{details_url}">
      <input type="hidden" name="tab" value="{safe_tab}">
      <label for="qa_item_detail_languages">Language</label>
      <div class="actions">
        <label>
          <input type="checkbox" id="qa-item-language-select-all">
          Select all
        </label>
      </div>
      <select id="qa_item_detail_languages" name="languages" multiple size="8">
        {"".join(safe_options)}
      </select>
      <button type="submit">Apply language</button>
    </form>
    <script>
      (function () {{
        const select = document.getElementById("qa_item_detail_languages");
        const selectAll = document.getElementById("qa-item-language-select-all");
        if (!select || !selectAll) return;

        function selectedCount() {{
          return Array.from(select.options).filter(function (option) {{ return option.selected; }}).length;
        }}

        function syncSelectAll() {{
          const total = select.options.length;
          const selected = selectedCount();
          selectAll.checked = total > 0 && selected === total;
          selectAll.indeterminate = selected > 0 && selected < total;
        }}

        select.addEventListener("change", syncSelectAll);
        selectAll.addEventListener("change", function () {{
          const shouldSelect = selectAll.checked;
          Array.from(select.options).forEach(function (option) {{
            option.selected = shouldSelect;
          }});
          syncSelectAll();
        }});
        syncSelectAll();
      }})();
    </script>
  </section>
"""


def format_assignment_label(assignment):
    qa_item = assignment.qa_item
    passage = ""
    question = ""
    if qa_item:
        passage = qa_item.passage_reference or qa_item.passage_id
        question = truncate_text(qa_item.question_text, 60)
    if passage and question:
        return f"{passage} — {question}"
    return passage or question or assignment.qa_item_id


def review_passage_sort_key(response):
    qa_item = response.qa_item
    received_at = response.received_at or datetime.min.replace(tzinfo=timezone.utc)
    received_sort = -received_at.timestamp()
    reference = (
        (qa_item.passage_reference or qa_item.passage_id).strip() if qa_item else ""
    )
    normalized = re.sub(r"\s+", " ", reference)
    match = re.search(r"^(.*?)(\d+):(\d+)\s*$", normalized)
    if not match:
        return (1, normalized.lower(), float("inf"), float("inf"), received_sort)

    book_part = re.sub(r"[^a-z0-9]+", " ", match.group(1).lower()).strip()
    chapter = int(match.group(2))
    verse = int(match.group(3))
    return (0, book_part, chapter, verse, received_sort)


def render_expert_review_language_filter(selected_language, language_options):
    safe_options = [
        f'<option value="{html.escape(language)}"></option>'
        for language in (language_options or [])
    ]
    return f"""
  <section class="detail-panel admin-form">
    <h2>Filter by language</h2>
    <form method="get" action="{html.escape(url_for('admin.expert_review_dashboard'))}">
      <label for="review_language">Language</label>
      <input
        id="review_language"
        name="language"
        type="text"
        list="review-language-options"
        placeholder="e.g. eng"
        value="{html.escape(selected_language)}"
      >
      <datalist id="review-language-options">
        {"".join(safe_options)}
      </datalist>
      <button type="submit">Apply language</button>
    </form>
  </section>
"""


def render_review_passage_toggle_script():
    return """
  <script>
    (function () {
      document.querySelectorAll(".review-passage-toggle").forEach(function (button) {
        button.addEventListener("click", function () {
          var detail = document.getElementById(button.getAttribute("aria-controls"));
          if (!detail) return;
          var dataRow = detail.previousElementSibling;
          var expanded = button.getAttribute("aria-expanded") === "true";
          button.setAttribute("aria-expanded", expanded ? "false" : "true");
          detail.hidden = expanded;
          if (dataRow && dataRow.classList.contains("review-data-row")) {
            dataRow.classList.toggle("is-expanded", !expanded);
          }
        });
      });
    })();
  </script>
"""


def review_passage_detail_id(qa_item_id, prefix="review-qa-passage"):
    return f"{prefix}-{qa_item_id}"


def render_review_passage_toggle(label, detail_id):
    safe_label = html.escape(str(label or "").strip())
    safe_detail_id = html.escape(detail_id)
    if not safe_label:
        return ""
    return (
        f'<button type="button" class="review-passage-toggle" '
        f'aria-expanded="false" aria-controls="{safe_detail_id}">{safe_label}</button>'
    )


def render_review_passage_detail_content(passage_text):
    if (passage_text or "").strip():
        return (
            f'<div class="review-passage-detail-text">'
            f"{html.escape(str(passage_text).strip())}</div>"
        )
    return '<span class="review-passage-empty">No passage text on file.</span>'


def render_expert_review_table(columns, rows, html_safe_keys=None):
    safe_html_keys = set(html_safe_keys or ())
    header_parts = []
    for column in columns:
        label = table_column_label(column)
        if table_column_header_is_html(column):
            header_parts.append(f"<th>{label}</th>")
        else:
            header_parts.append(f"<th>{html.escape(label)}</th>")
    header = "".join(header_parts)
    col_count = len(columns)
    body_rows = []
    for row in rows:
        response_id = html.escape(str(row.get("response_id", "")))
        detail_id = f"review-passage-{response_id}"
        cells = []
        for column in columns:
            key = table_column_key(column)
            value = row.get(key, "")
            if value is None:
                value = ""
            if key == "passage":
                label = html.escape(str(value))
                if label:
                    cell_content = render_review_passage_toggle(label, detail_id)
                else:
                    cell_content = ""
            elif key in safe_html_keys:
                cell_content = str(value)
            else:
                cell_content = html.escape(str(value))
            cells.append(f"<td>{cell_content}</td>")
        body_rows.append(f'<tr class="review-data-row">{"".join(cells)}</tr>')

        if (row.get("passage_text") or "").strip():
            detail_body = render_review_passage_detail_content(row.get("passage_text"))
        else:
            detail_body = render_review_passage_detail_content(None)
        body_rows.append(
            f'<tr id="{detail_id}" class="review-passage-detail" hidden>'
            f'<td colspan="{col_count}">'
            f"{detail_body}"
            f"</td></tr>"
        )

    body = "\n".join(body_rows) or (
        f'<tr><td colspan="{col_count}">No records found.</td></tr>'
    )
    return f"""
  <table class="review-table">
    <thead><tr>{header}</tr></thead>
    <tbody>{body}</tbody>
  </table>
  {render_review_passage_toggle_script()}
"""


def review_qa_tab_url(tab):
    return url_for("admin.review_qa_dashboard", tab=tab)


def render_review_qa_tabs(active_tab):
    valid_tabs = {"unreviewed", "reviewed", "removed"}
    active_tab = active_tab if active_tab in valid_tabs else "unreviewed"
    tabs = [
        ("unreviewed", "Unreviewed QAs"),
        ("reviewed", "Reviewed QAs"),
        ("removed", "Removed QAs"),
    ]
    links = []
    for tab_id, label in tabs:
        active_class = " active" if tab_id == active_tab else ""
        links.append(
            f'<a class="nav-link{active_class}" href="{html.escape(review_qa_tab_url(tab_id))}">'
            f"{html.escape(label)}</a>"
        )
    return f'<nav class="review-qa-tabs" aria-label="Review QA tabs">{"".join(links)}</nav>'


def qa_item_is_choice_scored(qa_item) -> bool:
    return (qa_item.question_type or "open").strip().lower() in {"mcq", "tf"}


def format_choice_response_answer_display(qa_item, response) -> str:
    stored = (response.response_text or "").strip().upper()
    if len(stored) == 1 and stored in {"A", "B", "C", "D"}:
        return stored
    analysis_text = response.transcript_text or response.response_text or ""
    letter = choice_response_letter(qa_item, analysis_text)
    return letter or "—"


def format_choice_correctness_label(is_correct: str) -> str:
    value = (is_correct or "").strip().lower()
    if value.startswith("yes"):
        return "correct"
    return "incorrect"


def mcq_choice_text_for_letter(qa_item, letter: str) -> str:
    letter = (letter or "").strip().upper()
    if not letter or letter == "—":
        return "—"
    question_type = (qa_item.question_type or "open").strip().lower()
    valid_letters = choice_letters_for_type(question_type)
    if letter not in valid_letters:
        return "—"
    choices = list(qa_item.mcq_choices or [])
    index = valid_letters.index(letter)
    if index >= len(choices):
        return "—"
    text = str(choices[index]).strip()
    return text or "—"


def format_participant_expected_answer(qa_item) -> str:
    if qa_item_is_choice_scored(qa_item):
        letter = (qa_item.mcq_correct_choice or "").strip().upper()
        return mcq_choice_text_for_letter(qa_item, letter)
    return (qa_item.expected_answer or "").strip() or "—"


def format_participant_user_answer(qa_item, response) -> str:
    if qa_item_is_choice_scored(qa_item):
        letter = format_choice_response_answer_display(qa_item, response)
        return mcq_choice_text_for_letter(qa_item, letter)
    text = (response.transcript_text or response.response_text or "").strip()
    return truncate_text(text, 200) if text else "—"


def format_participant_correctness_status(qa_item, response) -> str:
    if qa_item_is_choice_scored(qa_item):
        return format_choice_correctness_label(response.is_correct)
    return open_response_status_label(response.is_correct)


def build_participant_response_history_rows(responses):
    rows = []
    for response in responses:
        qa_item = response.qa_item
        if not qa_item:
            continue
        qa_url = html.escape(url_for("admin.qa_item_detail", qa_item_id=qa_item.id))
        question_label = html.escape(truncate_text(qa_item.question_text, 100))
        rows.append(
            {
                "passage": qa_item.passage_reference or qa_item.passage_id or "",
                "question": f'<a href="{qa_url}">{question_label}</a>',
                "question_type": (qa_item.question_type or "open").strip().lower(),
                "expected_answer": format_participant_expected_answer(qa_item),
                "user_answer": format_participant_user_answer(qa_item, response),
                "correctness_status": format_participant_correctness_status(
                    qa_item, response
                ),
            }
        )
    return rows


def render_qa_item_expected_answer_html(qa_item):
    """Read-only expected answer block for /admin/qa-items/<id>."""
    question_type = (qa_item.question_type or "open").strip().lower()
    if question_type not in {"mcq", "tf"}:
        return f"<p>{html.escape(qa_item.expected_answer or '')}</p>"

    choice_slots = 4 if question_type == "mcq" else 2
    choices = list(qa_item.mcq_choices or [])
    letter = (qa_item.mcq_correct_choice or "").strip().upper() or "—"
    choice_lines = []
    for index in range(choice_slots):
        label = chr(ord("A") + index)
        raw = choices[index] if index < len(choices) else ""
        text = html.escape(str(raw).strip()) if str(raw).strip() else "—"
        choice_lines.append(f"{label}: {text}")

    return (
        f"<p>Expected Answer: {html.escape(letter)}</p>"
        f'<p class="qa-choice-list">{"<br>".join(choice_lines)}</p>'
    )


def review_qa_choice_label_text(letter: str, correct_letter: str) -> str:
    if letter == correct_letter:
        return f"{letter} (Correct):"
    return f"{letter}:"


def format_qa_item_review_status_label(qa_item, *, include_timestamp=False) -> str:
    """QA text review state (Review QA workflow), not participant response review."""
    tab = review_qa_tab_for_item(qa_item)
    if tab == "removed":
        if include_timestamp and qa_item.review_removed_at:
            return f"Removed ({format_display_datetime(qa_item.review_removed_at)})"
        return "Removed"
    if tab == "reviewed":
        if include_timestamp and qa_item.qa_reviewed_at:
            return f"Reviewed ({format_display_datetime(qa_item.qa_reviewed_at)})"
        return "Reviewed"
    return "Unreviewed"


def format_review_qa_standard_answer(qa_item) -> str:
    """Single-line standard answer for reviewed/removed tables."""
    question_type = (qa_item.question_type or "open").strip().lower()
    if question_type not in {"mcq", "tf"}:
        answer = (qa_item.expected_answer or "").strip() or "…"
        return f"Standard Answer: {answer}"

    choice_slots = 4 if question_type == "mcq" else 2
    choices = list(qa_item.mcq_choices or [])
    correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
    parts = []
    for index in range(choice_slots):
        letter = chr(ord("A") + index)
        raw = choices[index] if index < len(choices) else ""
        text = str(raw).strip() or "…"
        star = "*" if letter == correct_letter else ""
        parts.append(f"{star}{letter}: {text}")
    return "Standard Answer: " + " ; ".join(parts)


def render_review_qa_mcq_fields(qa_item):
    question_type = (qa_item.question_type or "open").strip().lower()
    choice_slots = 4 if question_type == "mcq" else 2
    choices = list(qa_item.mcq_choices or [])
    while len(choices) < choice_slots:
        choices.append("")
    correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
    choice_slots_html = []
    for index in range(4):
        letter = chr(ord("A") + index)
        value = html.escape(choices[index] if index < len(choices) else "")
        hidden = "" if index < choice_slots else ' style="display:none"'
        label_text = html.escape(review_qa_choice_label_text(letter, correct_letter))
        choice_slots_html.append(
            f"""
        <div class="review-qa-choice-slot review-qa-choice-field" data-choice-letter="{letter}"{hidden}>
          <label class="review-qa-choice-label" for="mcq_choice_{index}_{html.escape(qa_item.id)}">{label_text}</label>
          <input
            class="review-qa-choice-field review-qa-choice-input"
            data-choice-letter="{letter}"
            id="mcq_choice_{index}_{html.escape(qa_item.id)}"
            name="mcq_choice_{index}"
            type="text"
            value="{value}"
          >
        </div>"""
        )
    correct_options = ['<option value="">Select…</option>']
    for index in range(4):
        letter = chr(ord("A") + index)
        selected = " selected" if correct_letter == letter else ""
        correct_options.append(
            f'<option value="{letter}" data-for-letters="{letter}"{selected}>{letter}</option>'
        )
    open_selected = " selected" if question_type == "open" else ""
    mcq_selected = " selected" if question_type == "mcq" else ""
    tf_selected = " selected" if question_type == "tf" else ""
    return f"""
    <label for="question_type_{html.escape(qa_item.id)}">Question type</label>
    <select id="question_type_{html.escape(qa_item.id)}" name="question_type" class="review-qa-question-type">
      <option value="open"{open_selected}>Open</option>
      <option value="mcq"{mcq_selected}>MCQ (4 choices)</option>
      <option value="tf"{tf_selected}>True / false</option>
    </select>
    <div class="review-qa-mcq-block" data-qa-item-id="{html.escape(qa_item.id)}">
      <span class="review-qa-answer-heading">Answer</span>
      <div class="review-qa-choice-row">
        {''.join(choice_slots_html)}
      </div>
      <div class="review-qa-correct-picker review-qa-choice-field" data-choice-letter="">
        <label for="mcq_correct_{html.escape(qa_item.id)}">Correct choice</label>
        <select id="mcq_correct_{html.escape(qa_item.id)}" name="mcq_correct_choice" class="review-qa-correct-choice">
          {''.join(correct_options)}
        </select>
      </div>
    </div>
    <div class="review-qa-open-answer-block">
      <label for="answer_{html.escape(qa_item.id)}">Answer</label>
      <textarea id="answer_{html.escape(qa_item.id)}" name="expected_answer">{html.escape(qa_item.expected_answer)}</textarea>
    </div>"""


def render_review_qa_type_toggle_script():
    return """
  <script>
    (function () {
      function syncCorrectChoiceLabels(article) {
        const select = article.querySelector(".review-qa-correct-choice");
        const correct = select ? (select.value || "").trim().toUpperCase() : "";
        article.querySelectorAll(".review-qa-choice-slot").forEach(function (slot) {
          const letter = slot.getAttribute("data-choice-letter");
          const label = slot.querySelector(".review-qa-choice-label");
          if (!label || !letter) return;
          label.textContent = letter === correct ? letter + " (Correct):" : letter + ":";
        });
      }
      function syncReviewQaType(select) {
        const article = select.closest(".review-qa-item");
        if (!article) return;
        const type = select.value;
        const isChoice = type === "mcq" || type === "tf";
        const slotCount = type === "tf" ? 2 : 4;
        const mcqBlock = article.querySelector(".review-qa-mcq-block");
        const openBlock = article.querySelector(".review-qa-open-answer-block");
        if (mcqBlock) mcqBlock.style.display = isChoice ? "block" : "none";
        if (openBlock) openBlock.style.display = isChoice ? "none" : "block";
        article.querySelectorAll(".review-qa-choice-field").forEach(function (el) {
          const letter = el.getAttribute("data-choice-letter");
          const picker = el.classList.contains("review-qa-correct-picker");
          if (picker) {
            el.style.display = isChoice ? "" : "none";
            return;
          }
          if (!letter) return;
          const show = isChoice && letter.charCodeAt(0) < 65 + slotCount;
          el.style.display = show ? "" : "none";
        });
        const correctSelect = article.querySelector(".review-qa-correct-choice");
        if (correctSelect) {
          correctSelect.querySelectorAll("option[data-for-letters]").forEach(function (opt) {
            const letter = opt.getAttribute("data-for-letters");
            opt.hidden = !(isChoice && letter.charCodeAt(0) < 65 + slotCount);
          });
        }
        syncCorrectChoiceLabels(article);
      }
      document.querySelectorAll(".review-qa-question-type").forEach(function (select) {
        syncReviewQaType(select);
        select.addEventListener("change", function () { syncReviewQaType(select); });
      });
      document.querySelectorAll(".review-qa-correct-choice").forEach(function (select) {
        select.addEventListener("change", function () {
          const article = select.closest(".review-qa-item");
          if (article) syncCorrectChoiceLabels(article);
        });
      });
    })();
  </script>
"""


def render_review_qa_item_form(qa_item, tab):
    passage_label = qa_item.passage_reference or qa_item.passage_id or ""
    detail_id = review_passage_detail_id(qa_item.id)
    passage_toggle = render_review_passage_toggle(passage_label, detail_id)
    update_url = html.escape(url_for("admin.review_qa_update", qa_item_id=qa_item.id))
    revert_url = html.escape(url_for("admin.review_qa_revert", qa_item_id=qa_item.id))
    remove_url = html.escape(url_for("admin.review_qa_remove", qa_item_id=qa_item.id))
    mark_url = html.escape(url_for("admin.review_qa_mark_reviewed", qa_item_id=qa_item.id))
    safe_tab = html.escape(tab)
    safe_detail_id = html.escape(detail_id)
    return f"""
  <article class="review-qa-item">
    <div class="review-qa-item-meta">{passage_toggle}</div>
    <div id="{safe_detail_id}" class="review-qa-passage-detail" hidden>
      {render_review_passage_detail_content(qa_item.passage_text)}
    </div>
    <form method="post" action="{update_url}">
      <input type="hidden" name="tab" value="{safe_tab}">
      <label for="question_{html.escape(qa_item.id)}">Question</label>
      <textarea id="question_{html.escape(qa_item.id)}" name="question_text" required>{html.escape(qa_item.question_text)}</textarea>
      {render_review_qa_mcq_fields(qa_item)}
      <div class="review-qa-item-actions">
        <button type="submit">Save</button>
      </div>
    </form>
    <div class="review-qa-item-actions">
      <form method="post" action="{mark_url}" style="display:inline">
        <input type="hidden" name="tab" value="{safe_tab}">
        <button type="submit" class="nav-link">Mark as reviewed</button>
      </form>
      <form method="post" action="{revert_url}" style="display:inline">
        <input type="hidden" name="tab" value="{safe_tab}">
        <button type="submit" class="nav-link">Revert to original</button>
      </form>
      <form method="post" action="{remove_url}" style="display:inline"
            onsubmit="return confirm('Remove this QA from assignment? It will move to Removed QAs.');">
        <input type="hidden" name="tab" value="{safe_tab}">
        <button type="submit" class="nav-link btn-danger">Remove</button>
      </form>
    </div>
  </article>
"""


def render_review_qa_reviewed_rows(qa_item):
    detail_id = review_passage_detail_id(qa_item.id)
    passage_label = qa_item.passage_reference or qa_item.passage_id or ""
    passage_cell = render_review_passage_toggle(passage_label, detail_id)
    return_url = html.escape(
        url_for("admin.review_qa_return_unreviewed", qa_item_id=qa_item.id)
    )
    remove_url = html.escape(url_for("admin.review_qa_remove", qa_item_id=qa_item.id))
    safe_detail_id = html.escape(detail_id)
    return f"""
      <tr class="review-data-row">
        <td>{passage_cell}</td>
        <td>
          <div>{html.escape(qa_item.question_text)}</div>
          <div class="field-hint">{html.escape((qa_item.question_type or "open"))}</div>
        </td>
        <td>{html.escape(format_review_qa_standard_answer(qa_item))}</td>
        <td>
          <div class="review-qa-item-actions">
            <form method="post" action="{return_url}" style="display:inline">
              <input type="hidden" name="tab" value="reviewed">
              <button type="submit" class="nav-link">Return to unreviewed</button>
            </form>
            <form method="post" action="{remove_url}" style="display:inline"
                  onsubmit="return confirm('Remove this QA from assignment? It will move to Removed QAs.');">
              <input type="hidden" name="tab" value="reviewed">
              <button type="submit" class="nav-link btn-danger">Remove</button>
            </form>
          </div>
        </td>
      </tr>
      <tr id="{safe_detail_id}" class="review-passage-detail" hidden>
        <td colspan="4">{render_review_passage_detail_content(qa_item.passage_text)}</td>
      </tr>"""


def render_review_qa_reviewed_chapter(chapter, items):
    rows = "".join(render_review_qa_reviewed_rows(item) for item in items)
    return f"""
  <section class="review-qa-chapter">
    {render_review_qa_chapter_header(chapter, items, "reviewed")}
    <table class="review-qa-reviewed-table review-table">
      <thead>
        <tr>
          <th>Passage</th>
          <th>Question</th>
          <th>Standard Answer</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </section>"""


def render_review_qa_chapter_header(chapter, items, tab):
    count = len(items)
    count_label = html.escape(f"{count} question{'s' if count != 1 else ''}")
    bulk_url = html.escape(url_for("admin.review_qa_bulk"))
    safe_tab = html.escape(tab)
    safe_chapter = html.escape(chapter)
    actions_html = ""

    if tab == "unreviewed" and count:
        actions_html = f"""
      <form method="post" action="{bulk_url}" class="review-qa-chapter-actions"
            onsubmit="return confirm('Mark all {count} question(s) in {safe_chapter} as reviewed?');">
        <input type="hidden" name="tab" value="{safe_tab}">
        <input type="hidden" name="chapter" value="{safe_chapter}">
        <input type="hidden" name="action" value="mark_reviewed">
        <button type="submit" class="nav-link">Mark chapter as reviewed</button>
      </form>"""
    elif tab == "reviewed" and count:
        actions_html = f"""
      <form method="post" action="{bulk_url}" class="review-qa-chapter-actions"
            onsubmit="return confirm('Return all {count} question(s) in {safe_chapter} to Unreviewed QAs? Text is unchanged.');">
        <input type="hidden" name="tab" value="{safe_tab}">
        <input type="hidden" name="chapter" value="{safe_chapter}">
        <input type="hidden" name="action" value="clear_reviewed">
        <button type="submit" class="nav-link">Return chapter to unreviewed</button>
      </form>"""

    return f"""
  <div class="review-qa-chapter-header">
    <div>
      <h3>{safe_chapter}</h3>
      <span class="review-qa-chapter-count">{count_label}</span>
    </div>
    {actions_html}
  </div>"""


def render_review_qa_active_panel(chapters, tab):
    empty_messages = {
        "unreviewed": "No unreviewed QA items.",
        "reviewed": "No reviewed QA items yet.",
    }
    if not chapters:
        return f"<p>{empty_messages.get(tab, 'No QA items.')}</p>"
    if tab == "reviewed":
        return (
            "".join(
                render_review_qa_reviewed_chapter(chapter, items)
                for chapter, items in chapters
            )
            + render_review_passage_toggle_script()
        )
    sections = []
    for chapter, items in chapters:
        item_html = "".join(render_review_qa_item_form(item, tab) for item in items)
        sections.append(
            f"""
  <section class="review-qa-chapter">
    {render_review_qa_chapter_header(chapter, items, tab)}
    {item_html}
  </section>"""
        )
    return (
        "".join(sections)
        + render_review_passage_toggle_script()
        + render_review_qa_type_toggle_script()
    )


def render_review_qa_removed_table(qa_items):
    if not qa_items:
        return "<p>No removed QA items.</p>"
    rows = []
    for qa_item in qa_items:
        restore_url = html.escape(url_for("admin.review_qa_restore", qa_item_id=qa_item.id))
        detail_id = review_passage_detail_id(qa_item.id)
        passage_label = qa_item.passage_reference or qa_item.passage_id or ""
        passage_cell = render_review_passage_toggle(passage_label, detail_id)
        safe_detail_id = html.escape(detail_id)
        meta_parts = []
        if qa_item.qa_reviewed_at:
            meta_parts.append(
                f"reviewed {format_display_datetime(qa_item.qa_reviewed_at)}"
            )
        rows.append(
            f"""
      <tr class="review-data-row">
        <td>{passage_cell}</td>
        <td>{html.escape(qa_item.question_text)}</td>
        <td>{html.escape(format_review_qa_standard_answer(qa_item))}</td>
        <td>{html.escape(" · ".join(part for part in meta_parts if part))}</td>
        <td>
          <form method="post" action="{restore_url}" style="display:inline">
            <input type="hidden" name="tab" value="removed">
            <button type="submit" class="nav-link">Restore</button>
          </form>
        </td>
      </tr>
      <tr id="{safe_detail_id}" class="review-passage-detail" hidden>
        <td colspan="5">{render_review_passage_detail_content(qa_item.passage_text)}</td>
      </tr>"""
        )
    return f"""
  <table class="review-qa-removed-table review-table">
    <thead>
      <tr>
        <th>Passage</th>
        <th>Question</th>
        <th>Standard Answer</th>
        <th>Metadata</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
  {render_review_passage_toggle_script()}
"""


def render_expert_review_actions(response_id, selected_language):
    correct_url = html.escape(url_for("admin.expert_review_decision", response_id=response_id))
    return f"""
<form method="post" action="{correct_url}" class="actions">
  <input type="hidden" name="language" value="{html.escape(selected_language)}">
  <button type="submit" name="decision" value="correct" class="nav-link">Mark correct</button>
  <button type="submit" name="decision" value="incorrect" class="nav-link btn-danger">Mark incorrect</button>
</form>
"""


CORRECT_IS_CORRECT_VALUES = frozenset({"yes (auto)", "yes (expert)"})
INCORRECT_IS_CORRECT_VALUES = frozenset({"no (expert)"})
UNDER_REVIEW_IS_CORRECT_VALUES = frozenset({"pending"})


def get_participant_response_stats(db, participant_ids):
    """Count submitted responses per participant by correctness bucket."""
    if not participant_ids:
        return {}

    stats = {
        participant_id: {"total": 0, "correct": 0, "incorrect": 0, "under_review": 0}
        for participant_id in participant_ids
    }
    rows = db.execute(
        select(
            ParticipantResponse.participant_id,
            ParticipantResponse.is_correct,
            func.count(),
        )
        .where(ParticipantResponse.participant_id.in_(participant_ids))
        .group_by(ParticipantResponse.participant_id, ParticipantResponse.is_correct)
    )
    for participant_id, is_correct, count in rows:
        bucket = stats.get(participant_id)
        if not bucket:
            continue
        count = int(count or 0)
        bucket["total"] += count
        value = (is_correct or "").strip()
        if value in CORRECT_IS_CORRECT_VALUES:
            bucket["correct"] += count
        elif value in INCORRECT_IS_CORRECT_VALUES:
            bucket["incorrect"] += count
        elif value in UNDER_REVIEW_IS_CORRECT_VALUES:
            bucket["under_review"] += count
        else:
            bucket["under_review"] += count
    return stats


def get_participant_workload(participants):
    if not participants:
        return {}, {}

    participant_ids = [participant.id for participant in participants]
    session_factory = get_session_factory()
    with session_factory() as db:
        assignments = db.scalars(
            select(Assignment)
            .where(Assignment.participant_id.in_(participant_ids))
            .options(selectinload(Assignment.qa_item))
            .order_by(Assignment.assigned_at.desc())
        ).all()
        participant_sessions = db.scalars(
            select(ParticipantSession)
            .where(ParticipantSession.participant_id.in_(participant_ids))
            .options(
                selectinload(ParticipantSession.current_assignment).selectinload(
                    Assignment.qa_item
                )
            )
        ).all()

    assignments_by_participant = {participant_id: [] for participant_id in participant_ids}
    for assignment in assignments:
        assignments_by_participant.setdefault(assignment.participant_id, []).append(assignment)

    sessions_by_participant = {
        participant_session.participant_id: participant_session
        for participant_session in participant_sessions
    }
    return assignments_by_participant, sessions_by_participant


def build_assigned_questions_summary(assignments):
    if not assignments:
        return ""

    labels = []
    for assignment in assignments:
        label = format_assignment_label(assignment)
        labels.append(f"{label} ({assignment.status})")
    return truncate_text("; ".join(labels), 240)


def build_current_work_summary(participant_session):
    if not participant_session:
        return "", ""

    current_assignment = participant_session.current_assignment
    if not current_assignment:
        return participant_session.state, ""

    current_label = format_assignment_label(current_assignment)
    return participant_session.state, current_label


def render_definition_list(items):
    rows = []
    for label, value in items:
        rows.append(
            f"<dt>{html.escape(label)}</dt><dd>{html.escape(str(value if value is not None else ''))}</dd>"
        )
    return f'<dl class="detail-list">{"".join(rows)}</dl>'


def build_qa_items_status_message():
    imported = request.args.get("imported")
    skipped = request.args.get("skipped")
    deleted = request.args.get("deleted")
    bulk_deleted = request.args.get("bulk_deleted")
    assign_ok = request.args.get("assign_ok")
    bulk_assigned = request.args.get("bulk_assigned")
    updated = request.args.get("updated")
    error = request.args.get("error")
    if error:
        return str(error), "error"

    parts = []
    if imported is not None:
        parts.append(f"Imported {imported} question(s)")
    if skipped is not None:
        parts.append(f"skipped {skipped} duplicate(s)")
    if deleted:
        parts.append("Question deleted")
    if bulk_deleted is not None:
        parts.append(f"Deleted {bulk_deleted} question(s)")
    if assign_ok:
        parts.append("Question assigned to participant")
    if bulk_assigned is not None:
        parts.append(f"Assigned {bulk_assigned} question(s) to participant")
    if updated:
        parts.append("Question settings updated")
    if not parts:
        return "", "success"
    return ", ".join(parts) + ".", "success"


def parse_selected_qa_item_ids(raw_ids: str):
    if not raw_ids:
        return []
    selected = []
    seen = set()
    for value in raw_ids.split(","):
        qa_item_id = value.strip()
        if not qa_item_id or qa_item_id in seen:
            continue
        seen.add(qa_item_id)
        selected.append(qa_item_id)
    return selected


def parse_keywords_from_form(field_name):
    remove_field = f"remove_{field_name}"
    keywords = [value.strip() for value in request.form.getlist(field_name) if value.strip()]
    remove_values = {value.strip() for value in request.form.getlist(remove_field) if value.strip()}
    keywords = [keyword for keyword in keywords if keyword not in remove_values]

    new_raw = request.form.get(f"new_{field_name}", "").strip()
    if new_raw:
        keywords.extend(
            part.strip()
            for part in re.split(r"[\n,]+", new_raw)
            if part.strip()
        )

    deduped = []
    seen = set()
    for keyword in keywords:
        normalized = keyword.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(keyword)
    return deduped


def parse_qa_item_settings_form():
    min_responses_raw = request.form.get("min_responses_required", "").strip()
    review_priority_raw = request.form.get("review_priority", "").strip()

    try:
        min_responses_required = int(min_responses_raw)
    except ValueError as exc:
        raise ValueError("Min responses required must be a whole number") from exc

    if min_responses_required < 1:
        raise ValueError("Min responses required must be at least 1")

    try:
        review_priority = int(review_priority_raw)
    except ValueError as exc:
        raise ValueError("Review priority must be a whole number") from exc

    regenerate_required = request.form.get("regenerate_required_keywords") == "1"
    required_keywords = parse_keywords_from_form("required_keywords")
    optional_keywords = parse_keywords_from_form("optional_keywords")

    return (
        min_responses_required,
        review_priority,
        required_keywords,
        optional_keywords,
        regenerate_required,
    )


def render_keyword_rows(field_name, keywords):
    rows = []
    for keyword in keywords or []:
        escaped_keyword = html.escape(keyword)
        rows.append(
            f"""
      <div class="keyword-row">
        <input type="text" name="{field_name}" value="{escaped_keyword}">
        <label class="keyword-remove">
          <input type="checkbox" name="remove_{field_name}" value="{escaped_keyword}">
          Remove
        </label>
      </div>"""
        )
    if not rows:
        rows.append('<p class="field-hint">No keywords yet. Add one below.</p>')
    return "".join(rows)


def render_qa_item_settings_form(qa_item, selected_languages=None):
    settings_url = html.escape(url_for("admin.qa_item_update_settings", qa_item_id=qa_item.id))
    selected_languages = selected_languages or []
    required_rows = render_keyword_rows("required_keywords", qa_item.required_keywords)
    optional_rows = render_keyword_rows("optional_keywords", qa_item.optional_keywords)
    return f"""
  <section class="detail-panel admin-form">
    <h2>Question settings</h2>
    <form method="post" action="{settings_url}">
      <input type="hidden" name="selected_languages" value="{html.escape(','.join(selected_languages))}">
      <div class="settings-section">
        <h3>Distribution</h3>
        <label for="min_responses_required">Min responses required</label>
        <input
          id="min_responses_required"
          name="min_responses_required"
          type="number"
          min="1"
          step="1"
          value="{html.escape(str(qa_item.min_responses_required))}"
          required
        >
        <p class="field-hint">Target number of participant responses needed across the study.</p>
        <label for="review_priority">Review priority</label>
        <input
          id="review_priority"
          name="review_priority"
          type="number"
          step="1"
          value="{html.escape(str(qa_item.review_priority))}"
          required
        >
        <p class="field-hint">Higher values are preferred sooner when auto-assigning the next question.</p>
      </div>
      <div class="settings-section">
        <h3>Required keywords (import default)</h3>
        <p class="field-hint">Used when no per-language rubric exists on <a href="{html.escape(url_for('admin.record_dashboard'))}">Record</a>. Prefer editing keywords there for each target language.</p>
        {required_rows}
        <div class="keyword-add">
          <label for="new_required_keywords">Add required keyword(s)</label>
          <input
            id="new_required_keywords"
            name="new_required_keywords"
            type="text"
            placeholder="e.g. zechariah or word1, word2"
          >
        </div>
        <label class="keyword-remove">
          <input type="checkbox" name="regenerate_required_keywords" value="1">
          Replace required keywords from expected answer (ignores edits above)
        </label>
      </div>
      <div class="settings-section">
        <h3>Optional keywords</h3>
        <p class="field-hint">Stored for reference; not used in automatic scoring today.</p>
        {optional_rows}
        <div class="keyword-add">
          <label for="new_optional_keywords">Add optional keyword(s)</label>
          <input
            id="new_optional_keywords"
            name="new_optional_keywords"
            type="text"
            placeholder="e.g. temple, priest"
          >
        </div>
      </div>
      <button type="submit">Save settings</button>
    </form>
  </section>
"""


def render_qa_assign_form(
    qa_item_id, participants, sessions_by_participant, selected_languages=None
):
    selected_languages = selected_languages or []
    options = ['<option value="">Select a participant</option>']
    for participant in participants:
        label = participant.display_name or participant.wa_id
        language = participant.target_language or "any"
        participant_session = sessions_by_participant.get(participant.id)
        session_state = participant_session.state if participant_session else "no session"
        options.append(
            f'<option value="{html.escape(participant.id)}">'
            f"{html.escape(label)} ({html.escape(participant.wa_id)}, "
            f"{html.escape(language)}, {html.escape(session_state)})"
            f"</option>"
        )

    assign_url = html.escape(url_for("admin.qa_item_assign", qa_item_id=qa_item_id))
    return f"""
  <section id="assign" class="detail-panel admin-form">
    <h2>Assign to participant</h2>
    <p>Uses the same assignment workflow as the chatbot: creates an assignment, schedules reminders, and sets the session to awaiting response. Does not send WhatsApp automatically.</p>
    <p class="field-hint">Assignment requires an expert <strong>question</strong> recording at <a href="{html.escape(url_for('admin.record_dashboard'))}">/admin/record</a> for the participant&apos;s target language.</p>
    <form method="post" action="{assign_url}">
      <input type="hidden" name="selected_languages" value="{html.escape(','.join(selected_languages))}">
      <label for="participant_id">Participant</label>
      <select id="participant_id" name="participant_id" required>
        {"".join(options)}
      </select>
      <button type="submit">Assign question</button>
    </form>
  </section>
"""


def read_import_json_from_request():
    uploaded = request.files.get("json_file")
    if uploaded and uploaded.filename:
        return uploaded.read().decode("utf-8")

    return request.form.get("json_text", "").strip()


@admin_blueprint.route("/qa-items/import", methods=["POST"])
@admin_token_required
def qa_items_import():
    try:
        import_defaults = parse_qa_import_form_defaults()
        json_text = read_import_json_from_request()
        entries = parse_entries_from_json_text(json_text)
        skip_existing = request.form.get("skip_existing") == "1"
        session_factory = get_session_factory()
        with session_factory() as db:
            result = import_qa_entries(
                db,
                entries,
                skip_existing=skip_existing,
                import_defaults=import_defaults,
            )
            db.commit()

        if result["errors"]:
            preview = "; ".join(result["errors"][:3])
            extra = ""
            if len(result["errors"]) > 3:
                extra = f" (+{len(result['errors']) - 3} more)"
            error_message = (
                f"Imported {result['created']} with {len(result['errors'])} error(s): "
                f"{preview}{extra}"
            )[:500]
            return redirect(
                url_for(
                    "admin.qa_items_dashboard",
                    imported=result["created"],
                    skipped=result["skipped"],
                    error=error_message,
                )
            )

        return redirect(
            url_for(
                "admin.qa_items_dashboard",
                imported=result["created"],
                skipped=result["skipped"],
            )
        )
    except (QAImportError, ValueError) as exc:
        return redirect(url_for("admin.qa_items_dashboard", error=str(exc)))
    except Exception as exc:
        return redirect(url_for("admin.qa_items_dashboard", error=str(exc)))


@admin_blueprint.route("/qa-items/<qa_item_id>/delete", methods=["POST"])
@admin_token_required
def qa_item_delete(qa_item_id):
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            qa_item = db.get(QAItem, qa_item_id)
            if not qa_item:
                return redirect(url_for("admin.qa_items_dashboard", error="QA item not found"))
            db.delete(qa_item)
            db.commit()
    except Exception as exc:
        return redirect(
            url_for(
                "admin.qa_items_dashboard",
                error=f"Could not delete question: {exc}",
            )
        )

    return redirect(url_for("admin.qa_items_dashboard", deleted=1))


@admin_blueprint.route("/qa-items", methods=["GET"])
@admin_token_required
def qa_items_dashboard():
    session_factory = get_session_factory()
    with session_factory() as db:
        qa_items = db.scalars(select(QAItem)).all()
        qa_items = sort_qa_items_by_passage_asc(qa_items)
        participants = db.scalars(
            select(Participant).order_by(Participant.display_name, Participant.wa_id)
        ).all()
        response_counts = {}
        flagged_counts = {}
        score_totals = {}
        score_counts = {}
        for qa_item_id, is_correct, correctness_score in db.execute(
            select(
                ParticipantResponse.qa_item_id,
                ParticipantResponse.is_correct,
                ParticipantResponse.correctness_score,
            )
        ):
            response_counts[qa_item_id] = response_counts.get(qa_item_id, 0) + 1
            if is_correct in {"pending", "no (expert)"}:
                flagged_counts[qa_item_id] = flagged_counts.get(qa_item_id, 0) + 1
            if correctness_score is not None:
                score_totals[qa_item_id] = score_totals.get(qa_item_id, 0) + correctness_score
                score_counts[qa_item_id] = score_counts.get(qa_item_id, 0) + 1

    rows = []
    for qa_item in qa_items:
        scored = score_counts.get(qa_item.id, 0)
        average_score = (
            format_correctness_score(score_totals[qa_item.id] / scored) if scored else ""
        )
        rows.append(
            {
                "id": qa_item.id,
                "passage": qa_item.passage_reference or qa_item.passage_id,
                "question": qa_item.question_text,
                "question_type": (qa_item.question_type or "open").strip().lower(),
                "review_status": format_qa_item_review_status_label(qa_item),
                "response_count": response_counts.get(qa_item.id, 0),
                "flagged_count": flagged_counts.get(qa_item.id, 0),
                "average_score": average_score,
                "min_responses": qa_item.min_responses_required,
                "review_priority": qa_item.review_priority,
                "active": qa_item.active,
            }
        )

    status_message, status_level = build_qa_items_status_message()
    return render_admin_page(
        "QA Items",
        [
            render_status_banner(status_message, status_level),
            render_qa_import_form(),
            "<p>Click a question to view responses and analytics. Use row checkboxes for bulk assign/delete, or per-row actions.</p>",
            render_qa_items_table(rows),
            render_qa_items_bulk_actions(participants),
            render_qa_items_bulk_script(),
        ],
        current_path="/admin/qa-items",
    )


@admin_blueprint.route("/qa-items/bulk-action", methods=["POST"])
@admin_token_required
def qa_items_bulk_action():
    action = (request.form.get("action") or "").strip().lower()
    selected_ids = parse_selected_qa_item_ids(
        request.form.get("selected_qa_item_ids", "").strip()
    )
    if not selected_ids:
        return redirect(url_for("admin.qa_items_dashboard", error="Select at least one QA item."))

    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            qa_items = db.scalars(select(QAItem).where(QAItem.id.in_(selected_ids))).all()
            qa_items_by_id = {item.id: item for item in qa_items}
            ordered_qa_items = [qa_items_by_id[item_id] for item_id in selected_ids if item_id in qa_items_by_id]
            if not ordered_qa_items:
                return redirect(url_for("admin.qa_items_dashboard", error="Selected QA items were not found."))

            if action == "delete":
                for qa_item in ordered_qa_items:
                    db.delete(qa_item)
                db.commit()
                return redirect(
                    url_for("admin.qa_items_dashboard", bulk_deleted=len(ordered_qa_items))
                )

            if action == "assign":
                participant_id = (request.form.get("participant_id") or "").strip()
                if not participant_id:
                    return redirect(
                        url_for(
                            "admin.qa_items_dashboard",
                            error="Select a participant before assigning.",
                        )
                    )

                participant = db.get(Participant, participant_id)
                if not participant:
                    return redirect(url_for("admin.qa_items_dashboard", error="Participant not found."))

                participant_session = get_or_create_participant_session(db, participant)
                for qa_item in ordered_qa_items:
                    assign_qa_item_to_participant(db, participant, participant_session, qa_item)
                db.commit()
                return redirect(
                    url_for("admin.qa_items_dashboard", bulk_assigned=len(ordered_qa_items))
                )

            return redirect(url_for("admin.qa_items_dashboard", error="Unknown bulk action."))
    except AssignmentAssignError as exc:
        return redirect(url_for("admin.qa_items_dashboard", error=str(exc)))
    except Exception as exc:
        return redirect(url_for("admin.qa_items_dashboard", error=f"Bulk action failed: {exc}"))


@admin_blueprint.route("/qa-items/<qa_item_id>/settings", methods=["POST"])
@admin_token_required
def qa_item_update_settings(qa_item_id):
    selected_languages = parse_selected_languages(
        (request.form.get("selected_languages") or "").split(","),
        "",
    )
    try:
        (
            min_responses_required,
            review_priority,
            required_keywords,
            optional_keywords,
            regenerate_required,
        ) = parse_qa_item_settings_form()
    except ValueError as exc:
        return redirect(
            url_for(
                "admin.qa_item_detail",
                qa_item_id=qa_item_id,
                languages=selected_languages,
                error=str(exc),
            )
        )

    session_factory = get_session_factory()
    with session_factory() as db:
        qa_item = db.get(QAItem, qa_item_id)
        if not qa_item:
            return redirect(url_for("admin.qa_items_dashboard", error="QA item not found"))

        qa_item.min_responses_required = min_responses_required
        qa_item.review_priority = review_priority
        if regenerate_required:
            # If the QA item was imported with explicit keywords, restore those.
            if qa_item.original_required_keywords:
                qa_item.required_keywords = list(qa_item.original_required_keywords)
                qa_item.required_keyword_specs = list(
                    qa_item.original_required_keyword_specs or []
                )
            else:
                return redirect(
                    url_for(
                        "admin.qa_item_detail",
                        qa_item_id=qa_item_id,
                        languages=selected_languages,
                        error=(
                            "Cannot regenerate required keywords because this QA item "
                            "does not have original required keywords from import."
                        ),
                    )
                )
        else:
            qa_item.required_keywords = required_keywords
        qa_item.optional_keywords = optional_keywords
        db.commit()

    return redirect(
        url_for(
            "admin.qa_item_detail",
            qa_item_id=qa_item_id,
            languages=selected_languages,
            updated=1,
        )
    )


@admin_blueprint.route("/qa-items/<qa_item_id>/assign", methods=["POST"])
@admin_token_required
def qa_item_assign(qa_item_id):
    selected_languages = parse_selected_languages(
        (request.form.get("selected_languages") or "").split(","),
        "",
    )
    participant_id = request.form.get("participant_id", "").strip()
    if not participant_id:
        return redirect(
            url_for(
                "admin.qa_item_detail",
                qa_item_id=qa_item_id,
                languages=selected_languages,
                error="Select a participant to assign this question.",
            )
        )

    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            qa_item = db.get(QAItem, qa_item_id)
            if not qa_item:
                return redirect(url_for("admin.qa_items_dashboard", error="QA item not found"))

            participant = db.get(Participant, participant_id)
            if not participant:
                return redirect(
                    url_for(
                        "admin.qa_item_detail",
                        qa_item_id=qa_item_id,
                        languages=selected_languages,
                        error="Participant not found.",
                    )
                )

            participant_session = get_or_create_participant_session(db, participant)
            assign_qa_item_to_participant(db, participant, participant_session, qa_item)
            db.commit()
    except AssignmentAssignError as exc:
        return redirect(
            url_for(
                "admin.qa_item_detail",
                qa_item_id=qa_item_id,
                languages=selected_languages,
                error=str(exc),
            )
        )
    except Exception as exc:
        return redirect(
            url_for(
                "admin.qa_item_detail",
                qa_item_id=qa_item_id,
                languages=selected_languages,
                error=f"Assignment failed: {exc}",
            )
        )

    return redirect(
        url_for(
            "admin.qa_item_detail",
            qa_item_id=qa_item_id,
            languages=selected_languages,
            assign_ok=1,
        )
    )


@admin_blueprint.route("/qa-items/<qa_item_id>", methods=["GET"])
@admin_token_required
def qa_item_detail(qa_item_id):
    active_tab = (request.args.get("tab") or "overview").strip().lower()
    if active_tab not in {"overview", "stats"}:
        active_tab = "overview"

    session_factory = get_session_factory()
    with session_factory() as db:
        qa_item = db.get(QAItem, qa_item_id)
        participants = db.scalars(
            select(Participant).order_by(Participant.display_name, Participant.wa_id)
        ).all()

    if not qa_item:
        return render_admin_page(
            "QA Item Not Found",
            [
                '<p class="back-link"><a href="/admin/qa-items">← Back to QA Items</a></p>',
                "<p>The requested QA item does not exist.</p>",
            ],
            current_path="/admin/qa-items",
        ), 404

    selected_languages = parse_selected_languages(
        request.args.getlist("languages") or [request.args.get("language", "")],
        "",
    )
    all_responses = get_qa_item_responses(qa_item_id)
    all_assignments = get_qa_item_assignments(qa_item_id)
    with session_factory() as db:
        sync_system_languages_registry(db)
        db.commit()
        language_options = get_registered_system_languages(db)
        prompt_recordings = get_latest_recordings_by_kind(
            db, [qa_item_id], selected_languages[0] if selected_languages else ""
        )
    language_options = sorted(
        set(language_options)
        | set(selected_languages)
        - {""}
    )
    if not selected_languages:
        selected_languages = list(language_options)
    question_prompt_recording = prompt_recordings.get((qa_item_id, "question"))
    answer_prompt_recording = prompt_recordings.get((qa_item_id, "answer"))
    selected_language_set = set(selected_languages)
    responses = [
        response
        for response in all_responses
        if (not selected_language_set)
        or (response_language_for_qa(response) in selected_language_set)
    ]
    assignments = [
        assignment
        for assignment in all_assignments
        if (not selected_language_set)
        or (participant_language_for_qa(assignment.participant) in selected_language_set)
    ]
    metrics = compute_qa_item_metrics(qa_item, responses)
    filtered_participants = [
        participant
        for participant in participants
        if (not selected_language_set)
        or (participant_language_for_qa(participant) in selected_language_set)
    ]
    _, sessions_by_participant = get_participant_workload(participants)
    status_message, status_level = build_qa_items_status_message()
    back_link = '<p class="back-link"><a href="/admin/qa-items">← Back to QA Items</a></p>'
    language_filter = render_qa_item_language_filter(
        qa_item.id,
        language_options,
        selected_languages,
        active_tab=active_tab,
    )
    detail_tabs = render_qa_item_detail_tabs(
        qa_item.id, active_tab, selected_languages
    )
    assign_form = render_qa_assign_form(
        qa_item.id, filtered_participants, sessions_by_participant, selected_languages
    )
    settings_form = render_qa_item_settings_form(qa_item, selected_languages)
    question_prompt_recording_html = ""
    if question_prompt_recording:
        question_prompt_recording_html = (
            f'<p class="field-hint">Target language recording ({html.escape(question_prompt_recording.language)})</p>'
            f"{render_recording_cell(question_prompt_recording)}"
        )
    answer_prompt_recording_html = ""
    if answer_prompt_recording:
        answer_prompt_recording_html = (
            f'<p class="field-hint">Target language recording ({html.escape(answer_prompt_recording.language)})</p>'
            f"{render_recording_cell(answer_prompt_recording)}"
        )
    passage_text_html = ""
    if qa_item.passage_text:
        passage_text_html = f"""
    <div class="settings-section">
      <h3>Passage text</h3>
      <p>{html.escape(qa_item.passage_text)}</p>
    </div>"""
    question_panel = f"""
  <section class="detail-panel">
    <h2>Question</h2>
    {render_definition_list(
        [
            ("Passage", qa_item.passage_reference or qa_item.passage_id),
            ("Question type", (qa_item.question_type or "open").strip().lower()),
            (
                "Review status",
                format_qa_item_review_status_label(qa_item, include_timestamp=True),
            ),
            ("Language scope", ", ".join(selected_languages)),
            ("Active", qa_item.active),
        ]
    )}
    {passage_text_html}
    <div class="settings-section">
      <h3>Question text</h3>
      <p>{html.escape(qa_item.question_text)}</p>
      {question_prompt_recording_html}
    </div>
    <div class="settings-section">
      <h3>Expected answer</h3>
      {render_qa_item_expected_answer_html(qa_item)}
      {answer_prompt_recording_html}
    </div>
  </section>
"""
    analytics_panel = f"""
  <section class="detail-panel">
    <h2>Analytics</h2>
    {render_definition_list(
        [
            ("Total responses", metrics["total_responses"]),
            ("Scored responses", metrics["scored_count"]),
            ("Average correctness score", metrics["average_score"]),
            ("Flagged responses", metrics["flagged_count"]),
            ("Flag rate", metrics["flag_rate"]),
            ("Meets minimum responses", metrics["meets_min_responses"]),
            ("Responses still needed", metrics["responses_needed"]),
        ]
    )}
  </section>
"""
    choice_scored_item = qa_item_is_choice_scored(qa_item)
    response_rows = []
    for response in responses:
        participant = response.participant
        participant_label = ""
        if participant:
            participant_label = participant.display_name or participant.id
        row = {
            "received_at": serialize_datetime(response.received_at),
            "participant": participant_label,
            "language": response_language_for_qa(response),
            "response_type": response.response_type,
            "recording": render_response_audio_cell(response),
        }
        if choice_scored_item:
            row["choice_answer"] = format_choice_response_answer_display(qa_item, response)
            row["correctness"] = format_choice_correctness_label(response.is_correct)
        else:
            answer_text = response.transcript_text or response.response_text or ""
            row.update(
                {
                    "answer": answer_text,
                    "normalized_text": response.normalized_text or "",
                    "correctness_score": format_correctness_score(
                        response.correctness_score
                    ),
                    "matched_keywords": format_keyword_list(response.matched_keywords),
                    "missing_keywords": format_keyword_list(response.missing_keywords),
                    "is_correct": response.is_correct,
                    "flag_reason": response.flag_reason or "",
                    "review_status": response.review_status,
                }
            )
        response_rows.append(row)

    assignment_rows = []
    for assignment in assignments:
        participant = assignment.participant
        assignment_rows.append(
            {
                "participant": participant.display_name or participant.id if participant else "",
                "wa_id": participant.wa_id if participant else "",
                "language": participant_language_for_qa(participant),
                "status": assignment.status,
                "assigned_at": serialize_datetime(assignment.assigned_at),
                "completed_at": serialize_datetime(assignment.completed_at),
                "batch_id": assignment.batch_id or "",
            }
        )

    assignments_section = f"""
  <section class="detail-panel">
    <h2>Assigned participants ({len(assignment_rows)})</h2>
    {render_table(
        [
            ("participant", "Participant"),
            ("wa_id", "WhatsApp ID"),
            ("language", "Language"),
            ("status", "Assignment status"),
            ("assigned_at", "Assigned"),
            ("completed_at", "Completed"),
            ("batch_id", "Batch"),
        ],
        assignment_rows,
    )}
  </section>
"""
    if choice_scored_item:
        response_columns = [
            ("received_at", "Received"),
            ("participant", "Participant"),
            ("language", "Language"),
            ("response_type", "Type"),
            ("recording", "Recording"),
            ("choice_answer", "Answer"),
            ("correctness", "Correctness status"),
        ]
    else:
        response_columns = [
            ("received_at", "Received"),
            ("participant", "Participant"),
            ("language", "Language"),
            ("response_type", "Type"),
            ("recording", "Recording"),
            ("answer", "Answer / transcript"),
            ("normalized_text", "Normalized text"),
            ("correctness_score", "Correctness score"),
            ("matched_keywords", "Matched keywords"),
            ("missing_keywords", "Missing keywords"),
            ("is_correct", "Correctness status"),
            ("flag_reason", "Flag reason"),
            ("review_status", "Review status"),
        ]
    responses_section = f"""
  <section class="detail-panel">
    <h2>Responses ({len(response_rows)})</h2>
    {render_table(
        response_columns,
        response_rows,
        html_safe_keys=("recording",),
    )}
  </section>
"""
    delete_url = html.escape(url_for("admin.qa_item_delete", qa_item_id=qa_item.id))
    delete_form = f"""
  <form method="post" action="{delete_url}" class="admin-form"
        onsubmit="return confirm('Delete this question and all related assignments/responses?');">
    <button type="submit" class="nav-link btn-danger">Delete question</button>
  </form>
"""
    title = truncate_text(qa_item.question_text, 80) or "QA Item Detail"
    if active_tab == "stats":
        tab_sections = [render_qa_item_stats_panel(qa_item, responses)]
    else:
        tab_sections = [
            question_panel,
            settings_form,
            analytics_panel,
            assign_form,
            assignments_section,
            responses_section,
        ]
    return render_admin_page(
        title,
        [
            back_link,
            render_status_banner(status_message, status_level),
            language_filter,
            delete_form,
            detail_tabs,
            *tab_sections,
        ],
        current_path="/admin/qa-items",
    )


@admin_blueprint.route("/review-qa", methods=["GET"])
@admin_or_expert_token_required
def review_qa_dashboard():
    tab = (request.args.get("tab") or "unreviewed").strip().lower()
    if tab not in {"unreviewed", "reviewed", "removed"}:
        tab = "unreviewed"
    message = request.args.get("message", "")
    error = request.args.get("error", "")

    session_factory = get_session_factory()
    with session_factory() as db:
        qa_items = load_review_qa_items(db, tab)

    if tab == "removed":
        panel = render_review_qa_removed_table(qa_items)
    else:
        panel = render_review_qa_active_panel(group_qa_items_by_chapter(qa_items), tab)

    return render_admin_page(
        "Review QA",
        [
            render_status_banner(error, "error") if error else "",
            render_status_banner(message, "success") if message else "",
            "<p>Review question–answer pairs for accuracy and cultural appropriateness. "
            "Removed items are excluded from participant assignment.</p>",
            render_review_qa_tabs(tab),
            panel,
        ],
        current_path="/admin/review-qa",
    )


def _review_qa_redirect(tab="unreviewed", *, message="", error=""):
    return redirect(
        url_for(
            "admin.review_qa_dashboard",
            tab=tab,
            message=message,
            error=error,
        )
    )


@admin_blueprint.route("/review-qa/bulk", methods=["POST"])
@admin_or_expert_token_required
def review_qa_bulk():
    action = (request.form.get("action") or "").strip().lower()
    chapter = (request.form.get("chapter") or "").strip()
    tab = (request.form.get("tab") or "unreviewed").strip().lower()

    if not chapter:
        return _review_qa_redirect(tab, error="Chapter name is required.")

    session_factory = get_session_factory()
    with session_factory() as db:
        if action == "mark_reviewed":
            count = bulk_mark_chapter_reviewed(db, chapter)
            db.commit()
            if count == 0:
                return _review_qa_redirect(
                    "unreviewed",
                    error=f"No unreviewed questions found in {chapter}.",
                )
            return _review_qa_redirect(
                "unreviewed",
                message=f"Marked {count} question(s) in {chapter} as reviewed.",
            )

        if action == "clear_reviewed":
            count = bulk_clear_chapter_reviewed(db, chapter)
            db.commit()
            if count == 0:
                return _review_qa_redirect(
                    "reviewed",
                    error=f"No reviewed questions found in {chapter}.",
                )
            return _review_qa_redirect(
                "unreviewed",
                message=f"Returned {count} question(s) in {chapter} to unreviewed.",
            )

    return _review_qa_redirect(tab, error="Unknown bulk action.")


@admin_blueprint.route("/review-qa/<qa_item_id>/update", methods=["POST"])
@admin_or_expert_token_required
def review_qa_update(qa_item_id):
    tab = (request.form.get("tab") or "unreviewed").strip().lower()
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            qa_item = db.get(QAItem, qa_item_id)
            if not qa_item:
                return _review_qa_redirect(tab, error="QA item not found.")
            update_qa_item_review_text(
                qa_item,
                request.form.get("question_text", ""),
                request.form.get("expected_answer", ""),
                question_type=request.form.get("question_type", "open"),
                mcq_choices=[
                    request.form.get(f"mcq_choice_{index}", "")
                    for index in range(4)
                ],
                mcq_correct_choice=request.form.get("mcq_correct_choice", ""),
            )
            db.commit()
    except ValueError as exc:
        return _review_qa_redirect(tab, error=str(exc))
    return _review_qa_redirect(tab, message="QA saved and marked reviewed.")


@admin_blueprint.route("/review-qa/<qa_item_id>/mark-reviewed", methods=["POST"])
@admin_or_expert_token_required
def review_qa_mark_reviewed(qa_item_id):
    tab = (request.form.get("tab") or "unreviewed").strip().lower()
    session_factory = get_session_factory()
    with session_factory() as db:
        qa_item = db.get(QAItem, qa_item_id)
        if not qa_item:
            return _review_qa_redirect(tab, error="QA item not found.")
        if qa_item_is_removed(qa_item):
            return _review_qa_redirect("removed", error="Cannot review a removed QA item.")
        mark_qa_item_reviewed(qa_item)
        db.commit()
    return _review_qa_redirect(tab, message="QA marked as reviewed.")


@admin_blueprint.route("/review-qa/<qa_item_id>/return-unreviewed", methods=["POST"])
@admin_or_expert_token_required
def review_qa_return_unreviewed(qa_item_id):
    tab = (request.form.get("tab") or "reviewed").strip().lower()
    session_factory = get_session_factory()
    with session_factory() as db:
        qa_item = db.get(QAItem, qa_item_id)
        if not qa_item:
            return _review_qa_redirect(tab, error="QA item not found.")
        if qa_item_is_removed(qa_item):
            return _review_qa_redirect("removed", error="Cannot change review status of a removed QA item.")
        clear_qa_item_reviewed(qa_item)
        db.commit()
    return _review_qa_redirect("unreviewed", message="QA returned to unreviewed.")


@admin_blueprint.route("/review-qa/<qa_item_id>/revert", methods=["POST"])
@admin_or_expert_token_required
def review_qa_revert(qa_item_id):
    tab = (request.form.get("tab") or "active").strip().lower()
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            qa_item = db.get(QAItem, qa_item_id)
            if not qa_item:
                return _review_qa_redirect(tab, error="QA item not found.")
            revert_qa_item_to_original(qa_item)
            db.commit()
    except ValueError as exc:
        return _review_qa_redirect(tab, error=str(exc))
    return _review_qa_redirect("unreviewed", message="Reverted to original text.")


@admin_blueprint.route("/review-qa/<qa_item_id>/remove", methods=["POST"])
@admin_or_expert_token_required
def review_qa_remove(qa_item_id):
    tab = (request.form.get("tab") or "unreviewed").strip().lower()
    session_factory = get_session_factory()
    with session_factory() as db:
        qa_item = db.get(QAItem, qa_item_id)
        if not qa_item:
            return _review_qa_redirect(tab, error="QA item not found.")
        remove_qa_item_from_review(qa_item)
        db.commit()
    return _review_qa_redirect("removed", message="QA moved to Removed QAs.")


@admin_blueprint.route("/review-qa/<qa_item_id>/restore", methods=["POST"])
@admin_or_expert_token_required
def review_qa_restore(qa_item_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        qa_item = db.get(QAItem, qa_item_id)
        if not qa_item:
            return _review_qa_redirect("removed", error="QA item not found.")
        restore_qa_item_from_removed(qa_item)
        db.commit()
        target_tab = review_qa_tab_for_item(qa_item)
    return _review_qa_redirect(target_tab, message="QA restored.")


@admin_blueprint.route("/review", methods=["GET"])
@admin_or_expert_token_required
def expert_review_dashboard():
    selected_language = canonical_language_code(request.args.get("language", ""))
    error = request.args.get("error")
    responses = get_responses(flagged_only=True)
    session_factory = get_session_factory()
    with session_factory() as db:
        sync_system_languages_registry(db)
        db.commit()
        language_options = get_registered_system_languages(db)

        qa_item_ids = sorted(
            {response.qa_item_id for response in responses if response.qa_item_id}
        )
        recording_statement = select(QAItemRecording).where(
            QAItemRecording.qa_item_id.in_(qa_item_ids),
            QAItemRecording.recording_type == "question",
        )
        if selected_language:
            recording_statement = recording_statement.where(
                func.lower(QAItemRecording.language) == selected_language
            )
        prompt_recordings = db.scalars(
            recording_statement.order_by(QAItemRecording.created_at.desc())
        ).all()
        keywords_by_item_lang = get_all_language_keywords_for_qa_items(db, qa_item_ids)

    prompt_recording_map = {}
    for recording in prompt_recordings:
        language_code = canonical_language_code(recording.language)
        key = (recording.qa_item_id, recording.recording_type, language_code)
        existing = prompt_recording_map.get(key)
        if not existing or (recording.version, recording.created_at) > (
            existing.version,
            existing.created_at,
        ):
            prompt_recording_map[key] = recording

    filtered_responses = []
    for response in responses:
        response_language = response_language_for_qa(response)
        if selected_language and response_language != selected_language:
            continue
        filtered_responses.append(response)

    filtered_responses.sort(key=review_passage_sort_key)
    rows = [
        {
            "response_id": response.id,
            "language": response_language_for_qa(response),
            "passage": response.qa_item.passage_reference or response.qa_item.passage_id
            if response.qa_item
            else "",
            "passage_text": response.qa_item.passage_text if response.qa_item else "",
            "question": response.qa_item.question_text if response.qa_item else "",
            "expected_answer_en": response.qa_item.expected_answer if response.qa_item else "",
            "keywords": render_review_keywords_cell(
                response.qa_item,
                keywords_by_item_lang.get(
                    (response.qa_item_id, response_language_for_qa(response))
                )
                if response.qa_item_id
                else None,
            ),
            "question_target_audio": render_recording_cell(
                prompt_recording_map.get(
                    (
                        response.qa_item_id,
                        "question",
                        selected_language or response_language_for_qa(response),
                    )
                )
            ),
            "answer": render_review_answer_cell(response),
            "score": format_correctness_score(response.correctness_score),
            "status": response.review_status,
            "actions": render_expert_review_actions(response.id, selected_language),
        }
        for response in filtered_responses
    ]
    return render_admin_page(
        "Review Response",
        [
            "<p>Review flagged participant responses.</p>",
            render_expert_review_language_filter(selected_language, language_options),
            render_expert_review_table(
                [
                    ("language", "Language"),
                    ("passage", "Passage"),
                    ("question", "Question"),
                    ("expected_answer_en", "Expected answer (English)"),
                    ("keywords", render_review_keywords_header(), True),
                    ("question_target_audio", "Question (target language)"),
                    ("answer", "Answer"),
                    ("score", "Score"),
                    ("status", "Review status"),
                    ("actions", "Review"),
                ],
                rows,
                html_safe_keys=(
                    "keywords",
                    "answer",
                    "question_target_audio",
                    "actions",
                ),
            ),
        ],
        current_path="/admin/review",
    )


@admin_blueprint.route("/review/<response_id>/decision", methods=["POST"])
@admin_or_expert_token_required
def expert_review_decision(response_id):
    decision = (request.form.get("decision") or "").strip().lower()
    selected_language = canonical_language_code(request.form.get("language", ""))
    if decision not in {"correct", "incorrect"}:
        return redirect(
            url_for(
                "admin.expert_review_dashboard",
                language=selected_language,
                error="Decision must be correct or incorrect.",
            )
        )

    session_factory = get_session_factory()
    with session_factory() as db:
        response = db.get(ParticipantResponse, response_id)
        if not response:
            return redirect(
                url_for(
                    "admin.expert_review_dashboard",
                    language=selected_language,
                    error="Response not found.",
                )
            )

        if decision == "correct":
            response.is_correct = "yes (expert)"
            response.review_status = "reviewed"
            response.flag_reason = ""
        else:
            response.is_correct = "no (expert)"
            response.review_status = "reviewed"
            if not (response.flag_reason or "").strip():
                response.flag_reason = "Marked incorrect by expert review."
        db.commit()

    return redirect(url_for("admin.expert_review_dashboard", language=selected_language))


def get_qa_item_response_count_rows(db):
    qa_items = sort_qa_items_by_passage_asc(db.scalars(select(QAItem)).all())
    response_counts = dict(
        db.execute(
            select(ParticipantResponse.qa_item_id, func.count())
            .group_by(ParticipantResponse.qa_item_id)
        ).all()
    )
    rows = []
    for qa_item in qa_items:
        count = response_counts.get(qa_item.id, 0)
        min_required = qa_item.min_responses_required or 0
        rows.append(
            {
                "qa_item_id": qa_item.id,
                "passage": qa_item.passage_reference or qa_item.passage_id,
                "question": truncate_text(qa_item.question_text, 80),
                "response_count": count,
                "min_required": min_required,
                "meets_target": count >= min_required if min_required else True,
            }
        )
    return rows


def render_response_count_dashboard(rows):
    if not rows:
        return "<p>No questions found.</p>"

    total_responses = sum(row["response_count"] for row in rows)
    chart_rows = []
    for row in rows:
        count = row["response_count"]
        min_required = row["min_required"] or 0
        scale_max = max(count, min_required, 1)
        bar_pct = round((count / scale_max) * 100, 1)
        min_pct = round((min_required / scale_max) * 100, 1) if min_required else None
        below_target = min_required and count < min_required
        bar_class = "response-count-bar-fill"
        if count == 0:
            bar_class += " zero"
        elif below_target:
            bar_class += " below-target"
        detail_url = html.escape(
            url_for("admin.qa_item_detail", qa_item_id=row["qa_item_id"])
        )
        min_marker_html = ""
        if min_pct is not None:
            min_marker_html = (
                f'<div class="response-count-min-marker" style="left: {min_pct}%;" '
                f'title="Minimum required: {min_required}"></div>'
            )
        chart_rows.append(
            f"""
      <div class="response-count-row">
        <div class="response-count-label">
          <div class="passage">{html.escape(str(row["passage"]))}</div>
          <div class="question"><a href="{detail_url}">{html.escape(str(row["question"]))}</a></div>
        </div>
        <div class="response-count-bar-area" title="{count} response(s), minimum target {min_required or 'n/a'}">
          <div class="{bar_class}" style="width: {bar_pct}%;"></div>
          {min_marker_html}
        </div>
        <div class="response-count-value">
          {html.escape(str(count))}{f' / {min_required}' if min_required else ''}
        </div>
      </div>"""
        )

    return f"""
  <section class="detail-panel response-count-dashboard">
    <h2>Responses per question</h2>
    <p class="chart-summary">
      {len(rows)} question(s), {total_responses} total response(s).
       </p>
    <div class="response-count-legend">
      <span><i class="swatch-min"></i> Minimum required</span>
    </div>
    <div class="response-count-chart">
      {"".join(chart_rows)}
    </div>
  </section>
"""


@admin_blueprint.route("/analytics", methods=["GET"])
@admin_or_expert_token_required
def analytics_dashboard():
    responses = get_responses(flagged_only=False)
    session_factory = get_session_factory()
    with session_factory() as db:
        participant_count = len(db.scalars(select(Participant.id)).all())
        qa_item_count = len(db.scalars(select(QAItem.id)).all())
        response_count_rows = get_qa_item_response_count_rows(db)

    total_responses = len(responses)
    flagged_count = sum(
        1 for response in responses if response.is_correct in {"pending", "no (expert)"}
    )
    scored_responses = [
        response.correctness_score
        for response in responses
        if response.correctness_score is not None
    ]
    average_score = (
        format_correctness_score(sum(scored_responses) / len(scored_responses))
        if scored_responses
        else ""
    )

    qa_metrics = {}
    for response in responses:
        if not response.qa_item:
            continue

        metrics = qa_metrics.setdefault(
            response.qa_item.id,
            {
                "passage": response.qa_item.passage_reference
                or response.qa_item.passage_id,
                "question": response.qa_item.question_text,
                "responses": 0,
                "flagged": 0,
                "score_sum": 0,
                "scored": 0,
            },
        )
        metrics["responses"] += 1
        metrics["flagged"] += 1 if response.is_correct in {"pending", "no (expert)"} else 0
        if response.correctness_score is not None:
            metrics["score_sum"] += response.correctness_score
            metrics["scored"] += 1

    rows = []
    for metrics in qa_metrics.values():
        rows.append(
            {
                "passage": metrics["passage"],
                "question": metrics["question"],
                "responses": metrics["responses"],
                "flagged": metrics["flagged"],
                "flag_rate": round(metrics["flagged"] / metrics["responses"], 3)
                if metrics["responses"]
                else "",
                "average_score": format_correctness_score(
                    metrics["score_sum"] / metrics["scored"]
                )
                if metrics["scored"]
                else "",
            }
        )

    summary = render_table(
        [
            ("participants", "Participants"),
            ("qa_items", "QA items"),
            ("responses", "Responses"),
            ("flagged", "Flagged"),
            ("average_score", "Average score"),
        ],
        [
            {
                "participants": participant_count,
                "qa_items": qa_item_count,
                "responses": total_responses,
                "flagged": flagged_count,
                "average_score": average_score,
            }
        ],
    )
    return render_admin_page(
        "Analytics",
        [
            "<p>Shared admin/expert aggregate response analytics.</p>",
            summary,
            render_response_count_dashboard(response_count_rows),
            render_table(
                [
                    ("passage", "Passage"),
                    ("question", "Question"),
                    ("responses", "Responses"),
                    ("flagged", "Flagged"),
                    ("flag_rate", "Flag rate"),
                    ("average_score", "Average score"),
                ],
                rows,
            ),
        ],
        current_path="/admin/analytics",
    )


@admin_blueprint.route("/participants", methods=["GET"])
@admin_token_required
def participants_dashboard():
    session_factory = get_session_factory()
    with session_factory() as db:
        participants = db.scalars(select(Participant).order_by(Participant.created_at.desc())).all()
        response_stats = get_participant_response_stats(db, [participant.id for participant in participants])

    assignments_by_participant, sessions_by_participant = get_participant_workload(participants)
    rows = []
    for participant in participants:
        participant_session = sessions_by_participant.get(participant.id)
        session_state, current_question = build_current_work_summary(participant_session)
        stats = response_stats.get(
            participant.id,
            {"total": 0, "correct": 0, "incorrect": 0, "under_review": 0},
        )
        detail_url = html.escape(
            url_for("admin.participant_detail", participant_id=participant.id)
        )
        display_label = html.escape(participant.display_name or participant.wa_id)
        rows.append(
            {
                "id": participant.id,
                "wa_id": participant.wa_id,
                "display_name": f'<a href="{detail_url}">{display_label}</a>',
                "language": participant.target_language or "",
                "session_state": session_state,
                "current_question": current_question,
                "assigned_questions": build_assigned_questions_summary(
                    assignments_by_participant.get(participant.id, [])
                ),
                "questions_completed": stats["total"],
                "correct": stats["correct"],
                "incorrect": stats["incorrect"],
                "under_review": stats["under_review"],
                "batch_size": participant.preferred_batch_size,
                "last_seen": serialize_datetime(participant.last_seen_at),
                "consented": participant.consented,
            }
        )

    return render_admin_page(
        "Participants",
        [
            "<p>Admin-only participant view. Shows assigned questions, progress, and how each "
            "submitted response was scored (correct, incorrect, or awaiting expert review).</p>",
            render_table(
                [
                    ("wa_id", "WhatsApp ID"),
                    ("display_name", "Display name"),
                    ("language", "Language"),
                    ("session_state", "Session state"),
                    ("current_question", "Currently working on"),
                    ("assigned_questions", "Assigned questions"),
                    ("questions_completed", "Questions completed"),
                    ("correct", "Correct"),
                    ("incorrect", "Incorrect"),
                    ("under_review", "Under review"),
                    ("batch_size", "Batch size"),
                    ("last_seen", "Last seen"),
                    ("consented", "Consented"),
                ],
                rows,
                html_safe_keys=("display_name",),
            ),
        ],
        current_path="/admin/participants",
    )


@admin_blueprint.route("/participants/<participant_id>", methods=["GET"])
@admin_token_required
def participant_detail(participant_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        participant = db.scalar(
            select(Participant)
            .where(Participant.id == participant_id)
            .options(
                selectinload(Participant.session)
                .selectinload(ParticipantSession.current_assignment)
                .selectinload(Assignment.qa_item)
            )
        )
        if not participant:
            return render_admin_page(
                "Participant Not Found",
                [
                    '<p class="back-link"><a href="/admin/participants">← Back to Participants</a></p>',
                    "<p>The requested participant does not exist.</p>",
                ],
                current_path="/admin/participants",
            ), 404

        responses = db.scalars(
            select(ParticipantResponse)
            .where(ParticipantResponse.participant_id == participant_id)
            .options(selectinload(ParticipantResponse.qa_item))
            .order_by(ParticipantResponse.received_at.desc())
        ).all()
        assignments = db.scalars(
            select(Assignment)
            .where(Assignment.participant_id == participant_id)
            .options(selectinload(Assignment.qa_item))
            .order_by(Assignment.assigned_at.desc())
        ).all()
        response_stats = get_participant_response_stats(db, [participant_id])

    participant_session = participant.session
    session_state, current_question = build_current_work_summary(participant_session)
    stats = response_stats.get(
        participant_id,
        {"total": 0, "correct": 0, "incorrect": 0, "under_review": 0},
    )
    metadata_panel = f"""
  <section class="detail-panel">
    <h2>Participant</h2>
    {render_definition_list(
        [
            ("WhatsApp ID", participant.wa_id),
            ("Display name", participant.display_name or ""),
            ("Language", participant.target_language or ""),
            ("Session state", session_state),
            ("Currently working on", current_question or "—"),
            (
                "Assigned questions",
                build_assigned_questions_summary(assignments) or "—",
            ),
            ("Questions completed", stats["total"]),
            ("Correct", stats["correct"]),
            ("Incorrect", stats["incorrect"]),
            ("Under review", stats["under_review"]),
            ("Batch size", participant.preferred_batch_size),
            ("Last seen", serialize_datetime(participant.last_seen_at) or "—"),
            ("Consented", participant.consented),
        ]
    )}
  </section>
"""
    history_rows = build_participant_response_history_rows(responses)
    history_section = f"""
  <section class="detail-panel">
    <h2>Questions answered ({len(history_rows)})</h2>
    {render_table(
        [
            ("passage", "Passage"),
            ("question", "Question"),
            ("question_type", "Question type"),
            ("expected_answer", "Expected answer"),
            ("user_answer", "User answer"),
            ("correctness_status", "Correctness status"),
        ],
        history_rows,
        html_safe_keys=("question",),
    )}
  </section>
"""
    title = participant.display_name or participant.wa_id or "Participant"
    return render_admin_page(
        title,
        [
            '<p class="back-link"><a href="/admin/participants">← Back to Participants</a></p>',
            metadata_panel,
            history_section,
        ],
        current_path="/admin/participants",
    )


def choice_answer_recording_version(letter: str) -> int:
    return ord(letter.upper()) - ord("A") + 1


def render_new_take_button(
    qa_item_id, recording_type, language, label, *, choice_letter=None
):
    safe_id = html.escape(qa_item_id, quote=True)
    safe_type = html.escape(recording_type, quote=True)
    safe_language = html.escape(language or "", quote=True)
    safe_label = html.escape(label)
    choice_attr = ""
    if choice_letter:
        choice_attr = (
            f' data-record-choice="{html.escape(choice_letter.upper(), quote=True)}"'
        )
    return f"""
      <button
        type="button"
        class="nav-link"
        data-record-kind="{safe_type}"
        data-record-mode="new"
        data-qa-id="{safe_id}"
        data-record-language="{safe_language}"{choice_attr}
      >{safe_label}</button>
    """


def choice_letter_for_answer_recording(recording) -> str | None:
    if (recording.recording_type or "").strip().lower() != "answer":
        return None
    if recording.version < 1 or recording.version > 4:
        return None
    return chr(ord("A") + recording.version - 1)


def render_retake_button(recording):
    safe_id = html.escape(recording.qa_item_id, quote=True)
    safe_type = html.escape(recording.recording_type, quote=True)
    safe_language = html.escape(recording.language or "", quote=True)
    safe_recording_id = html.escape(recording.id, quote=True)
    safe_version = html.escape(str(recording.version), quote=True)
    choice_letter = choice_letter_for_answer_recording(recording)
    choice_attr = ""
    if choice_letter:
        choice_attr = (
            f' data-record-choice="{html.escape(choice_letter, quote=True)}"'
        )
    return f"""
      <button
        type="button"
        class="nav-link"
        data-record-kind="{safe_type}"
        data-record-mode="retake"
        data-qa-id="{safe_id}"
        data-record-language="{safe_language}"
        data-recording-id="{safe_recording_id}"
        data-version="{safe_version}"{choice_attr}
      >Retake</button>
    """


def render_remove_take_button(recording):
    safe_recording_id = html.escape(recording.id, quote=True)
    safe_version = html.escape(str(recording.version), quote=True)
    return f"""
      <button
        type="button"
        class="nav-link nav-link-remove"
        data-delete-recording="1"
        data-recording-id="{safe_recording_id}"
        data-version="{safe_version}"
      >Remove</button>
    """


def format_recording_take_label(recording_type_label, version, created_at):
    timestamp = serialize_datetime(created_at)
    return f"{recording_type_label} v{version} {timestamp}".strip()


def next_recording_version(db, qa_item_id, recording_type, language):
    max_version = db.scalar(
        select(func.coalesce(func.max(QAItemRecording.version), 0)).where(
            QAItemRecording.qa_item_id == qa_item_id,
            QAItemRecording.recording_type == recording_type,
            QAItemRecording.language == language,
        )
    )
    return int(max_version or 0) + 1


def delete_qa_recordings_for_slot(db, qa_item_id, recording_type, language):
    statement = select(QAItemRecording).where(
        QAItemRecording.qa_item_id == qa_item_id,
        QAItemRecording.recording_type == recording_type,
        QAItemRecording.language == language,
    )
    for existing in db.scalars(statement).all():
        if existing.storage_uri:
            delete_storage_uri(existing.storage_uri)
        db.delete(existing)


def delete_qa_recording_version(db, qa_item_id, recording_type, language, version):
    statement = select(QAItemRecording).where(
        QAItemRecording.qa_item_id == qa_item_id,
        QAItemRecording.recording_type == recording_type,
        QAItemRecording.language == language,
        QAItemRecording.version == version,
    )
    for existing in db.scalars(statement).all():
        if existing.storage_uri:
            delete_storage_uri(existing.storage_uri)
        db.delete(existing)


def get_recordings_grouped_by_kind(db, qa_item_ids, language):
    if not qa_item_ids:
        return {}

    statement = select(QAItemRecording).where(QAItemRecording.qa_item_id.in_(qa_item_ids))
    if language:
        statement = statement.where(
            func.lower(QAItemRecording.language) == canonical_language_code(language)
        )

    recordings = db.scalars(
        statement.order_by(QAItemRecording.version.asc(), QAItemRecording.created_at.asc())
    ).all()
    grouped = {}
    for recording in recordings:
        key = (recording.qa_item_id, recording.recording_type)
        grouped.setdefault(key, []).append(recording)
    return grouped


def get_latest_recordings_by_kind(db, qa_item_ids, language):
    grouped = get_recordings_grouped_by_kind(db, qa_item_ids, language)
    latest = {}
    for key, recordings in grouped.items():
        latest[key] = max(recordings, key=lambda recording: (recording.version, recording.created_at))
    return latest


def format_single_recording_label(recording_type_label, created_at):
    timestamp = serialize_datetime(created_at)
    return f"{recording_type_label} {timestamp}".strip()


def render_single_recording_take_cell(recording, recording_type_label):
    playback_url = qa_recording_media_url(recording.id)
    audio_html = (
        f'<audio controls preload="none" src="{html.escape(playback_url, quote=True)}"></audio>'
        if parse_storage_uri(recording.storage_uri or "")
        else '<span class="audio-meta">No stored file</span>'
    )
    take_label = format_single_recording_label(recording_type_label, recording.created_at)
    return f"""
            <div class="recording-take">
              <div class="recording-take-header">
                <span class="recording-take-label">{html.escape(take_label)}</span>
                <div class="recording-take-actions">
                  {render_retake_button(recording)}
                  {render_remove_take_button(recording)}
                </div>
              </div>
              {audio_html}
            </div>
            """


def render_question_recording_cell(recordings, qa_item_id=None, recording_language=None):
    if not recordings:
        if qa_item_id and recording_language:
            return (
                f'<div class="audio-links">'
                f'{render_new_take_button(qa_item_id, "question", recording_language, "Record question")}'
                f"</div>"
            )
        return '<span class="audio-meta">No recording yet</span>'
    recording = max(recordings, key=lambda recording: (recording.version, recording.created_at))
    return (
        f'<div class="recording-takes">{render_single_recording_take_cell(recording, "Question")}</div>'
    )


def render_answer_recording_cell(
    recordings,
    *,
    qa_item_id,
    recording_language,
    choice_letter=None,
):
    version = choice_answer_recording_version(choice_letter) if choice_letter else 1
    slot_recordings = [r for r in recordings if r.version == version]
    if not slot_recordings:
        if qa_item_id and recording_language:
            return (
                '<div class="record-answer-controls">'
                f'{render_new_take_button(qa_item_id, "answer", recording_language, "Record", choice_letter=choice_letter)}'
                "</div>"
            )
        return '<span class="audio-meta">No recording yet</span>'

    recording = max(slot_recordings, key=lambda row: row.created_at)
    playback_url = qa_recording_media_url(recording.id)
    audio_html = (
        f'<audio controls preload="none" src="{html.escape(playback_url, quote=True)}"></audio>'
        if parse_storage_uri(recording.storage_uri or "")
        else '<span class="audio-meta">No stored file</span>'
    )
    return (
        '<div class="record-answer-controls">'
        f"{audio_html}"
        f"{render_retake_button(recording)}"
        "</div>"
    )


def render_record_standard_answer_cell(qa_item, answer_recordings, recording_language):
    question_type = (qa_item.question_type or "open").strip().lower()
    if question_type in {"mcq", "tf"}:
        choice_slots = 4 if question_type == "mcq" else 2
        choices = list(qa_item.mcq_choices or [])
        correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
        items = []
        for index in range(choice_slots):
            letter = chr(ord("A") + index)
            raw = choices[index] if index < len(choices) else ""
            text = html.escape(str(raw).strip()) if str(raw).strip() else "…"
            star = "*" if letter == correct_letter else ""
            items.append(
                f"""
        <li class="keyword-record-item">
          <span class="keyword-record-label">{star}{letter}: {text}</span>
          {render_answer_recording_cell(
                answer_recordings,
                qa_item_id=qa_item.id,
                recording_language=recording_language,
                choice_letter=letter,
            )}
        </li>"""
            )
        return (
            '<div class="keyword-record-panel record-answer-panel">'
            f'<ul class="keyword-record-list">{"".join(items)}</ul>'
            "</div>"
        )

    answer_text = html.escape((qa_item.expected_answer or "").strip() or "…")
    return f"""
  <div class="keyword-record-panel record-answer-panel">
    <p class="keyword-record-label" style="font-weight:400">{answer_text}</p>
    {render_answer_recording_cell(
        answer_recordings,
        qa_item_id=qa_item.id,
        recording_language=recording_language,
    )}
  </div>"""


def render_recordings_list_cell(recordings, recording_type_label):
    if not recordings:
        return '<span class="audio-meta">No recordings yet</span>'

    takes_html = []
    for recording in recordings:
        playback_url = qa_recording_media_url(recording.id)
        audio_html = (
            f'<audio controls preload="none" src="{html.escape(playback_url, quote=True)}"></audio>'
            if parse_storage_uri(recording.storage_uri or "")
            else '<span class="audio-meta">No stored file</span>'
        )
        take_label = format_recording_take_label(
            recording_type_label, recording.version, recording.created_at
        )
        takes_html.append(
            f"""
            <div class="recording-take">
              <div class="recording-take-header">
                <span class="recording-take-label">{html.escape(take_label)}</span>
                <div class="recording-take-actions">
                  {render_retake_button(recording)}
                  {render_remove_take_button(recording)}
                </div>
              </div>
              {audio_html}
            </div>
            """
        )

    return f'<div class="recording-takes">{"".join(takes_html)}</div>'


def render_recording_cell(recording):
    if not recording:
        return '<span class="audio-meta">No recording yet</span>'

    if not parse_storage_uri(recording.storage_uri or ""):
        return '<span class="audio-meta">No stored file</span>'

    safe_url = html.escape(qa_recording_media_url(recording.id), quote=True)
    meta = f"{recording.language} · {serialize_datetime(recording.created_at)}"
    return (
        '<div class="response-audio">'
        f'<audio controls preload="none" src="{safe_url}"></audio>'
        f'<span class="audio-meta">{html.escape(meta)}</span>'
        "</div>"
    )


def render_system_language_panel(language_options):
    rows = []
    for language in language_options:
        safe_language = html.escape(language)
        remove_url = html.escape(url_for("admin.system_languages_remove"))
        rows.append(
            f"""
            <tr>
              <td>{safe_language}</td>
              <td class="actions">
                <form method="post" action="{remove_url}" style="display:inline;">
                  <input type="hidden" name="code" value="{safe_language}">
                  <button type="submit" class="nav-link">Remove</button>
                </form>
              </td>
            </tr>
            """
        )
    body = "".join(rows) or "<tr><td colspan='2'>No languages registered.</td></tr>"
    add_url = html.escape(url_for("admin.system_languages_add"))
    return f"""
  <section class="detail-panel admin-form">
    <h2>System languages</h2>
    <form method="post" action="{add_url}">
      <label for="new_system_language">Add language</label>
      <input
        id="new_system_language"
        name="code"
        type="text"
        placeholder="e.g. eng, fra, hau"
        required
      >
      <button type="submit">Add language</button>
    </form>
    <table>
      <thead>
        <tr>
          <th>Language code</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {body}
      </tbody>
    </table>
  </section>
"""


def render_record_language_filter(language_options, selected_language):
    safe_options = []
    for language in language_options:
        safe_language = html.escape(language)
        selected_attr = " selected" if language == selected_language else ""
        safe_options.append(
            f'<option value="{safe_language}"{selected_attr}>{safe_language}</option>'
        )

    return f"""
  <section class="detail-panel admin-form">
    <h2>Record into language</h2>
    <form method="get" action="{html.escape(url_for('admin.record_dashboard'))}">
      <label for="record_language">Language</label>
      <select id="record_language" name="language">
        {"".join(safe_options)}
      </select>
      <p class="field-hint">Question recordings use the selected language.</p>
      <button type="submit">Apply language</button>
    </form>
  </section>
"""


def render_record_page(record_language, language_options, rows):
    rows_html = []
    for row in rows:
        rows_html.append(
            {
                "passage": row["passage"],
                "question": row["question"],
                "answer": row["answer"],
                "question_recording": row["question_recording"],
            }
        )

    table_html = render_table(
        [
            ("passage", "Passage"),
            ("question", "Question"),
            ("answer", "Standard answer (English)"),
            ("question_recording", "Question recording"),
        ],
        rows_html,
        html_safe_keys=("answer", "question_recording"),
    )

    return f"""
  {render_record_language_filter(language_options, record_language)}
  <p id="record-status" class="status-banner success" style="display:none;"></p>
  {table_html}
  <div id="record-retake-confirm-modal" class="record-modal" hidden>
    <div class="record-modal-backdrop"></div>
    <div class="record-modal-panel" role="dialog" aria-modal="true" aria-labelledby="record-retake-title">
      <h3 id="record-retake-title">Replace this recording?</h3>
      <p>Listen to what you just recorded. If you continue, the existing take will be replaced.</p>
      <audio id="record-retake-preview" controls preload="auto"></audio>
      <div class="record-modal-actions">
        <button type="button" class="nav-link" id="record-retake-cancel">Cancel</button>
        <button type="button" class="nav-link" id="record-retake-confirm">Replace recording</button>
      </div>
    </div>
  </div>
  <script>
    (function () {{
      const statusEl = document.getElementById("record-status");
      const uploadUrl = "{html.escape(url_for('admin.record_upload'))}";
      const deleteUrl = "{html.escape(url_for('admin.record_delete'))}";
      let mediaStream = null;
      let mediaRecorder = null;
      let recordingChunks = [];
      let activeButton = null;

      function setStatus(message, isError) {{
        if (!statusEl) return;
        statusEl.style.display = "block";
        statusEl.className = isError ? "status-banner error" : "status-banner success";
        statusEl.textContent = message;
      }}

      function stopActiveRecorder() {{
        if (mediaRecorder && mediaRecorder.state !== "inactive") {{
          mediaRecorder.stop();
        }}
      }}

      function releaseStream() {{
        if (mediaStream) {{
          mediaStream.getTracks().forEach(function (track) {{ track.stop(); }});
          mediaStream = null;
        }}
      }}

      function resetButton(button) {{
        if (!button) return;
        button.dataset.recordState = "idle";
        button.textContent = button.dataset.defaultLabel || "Record";
      }}

      function confirmRetakeUpload(blob) {{
        return new Promise(function (resolve, reject) {{
          const modal = document.getElementById("record-retake-confirm-modal");
          const audio = document.getElementById("record-retake-preview");
          const confirmBtn = document.getElementById("record-retake-confirm");
          const cancelBtn = document.getElementById("record-retake-cancel");
          if (!modal || !audio || !confirmBtn || !cancelBtn) {{
            resolve(true);
            return;
          }}

          const previewUrl = URL.createObjectURL(blob);
          audio.src = previewUrl;
          modal.hidden = false;

          function cleanup() {{
            modal.hidden = true;
            audio.pause();
            audio.removeAttribute("src");
            URL.revokeObjectURL(previewUrl);
            confirmBtn.removeEventListener("click", onConfirm);
            cancelBtn.removeEventListener("click", onCancel);
            modal.removeEventListener("click", onBackdrop);
          }}

          function onConfirm() {{
            cleanup();
            resolve(true);
          }}

          function onCancel() {{
            cleanup();
            reject(new Error("Retake cancelled"));
          }}

          function onBackdrop(event) {{
            if (event.target.classList.contains("record-modal-backdrop")) {{
              onCancel();
            }}
          }}

          confirmBtn.addEventListener("click", onConfirm);
          cancelBtn.addEventListener("click", onCancel);
          modal.addEventListener("click", onBackdrop);
        }});
      }}

      async function uploadBlob(button, blob) {{
        const formData = new FormData();
        formData.append("qa_item_id", button.dataset.qaId || "");
        formData.append("recording_type", button.dataset.recordKind || "");
        formData.append("language", button.dataset.recordLanguage || "");
        if (button.dataset.recordChoice) {{
          formData.append("choice_letter", button.dataset.recordChoice);
        }}
        formData.append("mode", button.dataset.recordMode || "new");
        if (button.dataset.recordingId) {{
          formData.append("recording_id", button.dataset.recordingId);
        }}
        if (button.dataset.version) {{
          formData.append("version", button.dataset.version);
        }}
        formData.append("audio", blob, "recording.webm");
        const response = await fetch(uploadUrl, {{
          method: "POST",
          body: formData,
        }});
        const payload = await response.json().catch(function () {{ return {{}}; }});
        if (!response.ok || payload.status !== "ok") {{
          throw new Error(payload.message || "Upload failed");
        }}
        setStatus("Recording saved. Reloading...", false);
        window.setTimeout(function () {{ window.location.reload(); }}, 500);
      }}

      document.querySelectorAll("[data-delete-recording]").forEach(function (button) {{
        button.addEventListener("click", async function () {{
          const version = button.dataset.version || "";
          const label = version ? "take v" + version : "this take";
          if (!window.confirm("Remove " + label + "? This deletes the recording from the database.")) {{
            return;
          }}
          const formData = new FormData();
          formData.append("recording_id", button.dataset.recordingId || "");
          try {{
            const response = await fetch(deleteUrl, {{
              method: "POST",
              body: formData,
            }});
            const payload = await response.json().catch(function () {{ return {{}}; }});
            if (!response.ok || payload.status !== "ok") {{
              throw new Error(payload.message || "Delete failed");
            }}
            setStatus("Recording removed. Reloading...", false);
            window.setTimeout(function () {{ window.location.reload(); }}, 500);
          }} catch (err) {{
            setStatus(err.message || "Failed to remove recording", true);
          }}
        }});
      }});

      document.querySelectorAll("[data-record-kind]").forEach(function (button) {{
        button.dataset.defaultLabel = button.textContent;
        button.dataset.recordState = "idle";
        button.addEventListener("click", function () {{
          const state = button.dataset.recordState || "idle";
          if (state === "recording") {{
            stopActiveRecorder();
            return;
          }}

          if (activeButton && activeButton !== button) {{
            stopActiveRecorder();
            resetButton(activeButton);
          }}

          navigator.mediaDevices.getUserMedia({{ audio: true }})
            .then(function (stream) {{
              mediaStream = stream;
              recordingChunks = [];
              mediaRecorder = new MediaRecorder(stream);
              activeButton = button;
              button.dataset.recordState = "recording";
              button.textContent = "Stop";
              setStatus("Recording... click Stop when done.", false);

              mediaRecorder.ondataavailable = function (event) {{
                if (event.data && event.data.size > 0) {{
                  recordingChunks.push(event.data);
                }}
              }};

              mediaRecorder.onstop = async function () {{
                const blob = new Blob(recordingChunks, {{ type: mediaRecorder.mimeType || "audio/webm" }});
                try {{
                  if (blob.size === 0) {{
                    throw new Error("No audio captured");
                  }}
                  if ((button.dataset.recordMode || "new") === "retake") {{
                    await confirmRetakeUpload(blob);
                  }}
                  await uploadBlob(button, blob);
                }} catch (err) {{
                  const cancelled = (err && err.message) === "Retake cancelled";
                  setStatus(
                    err.message || "Recording upload failed",
                    cancelled ? false : true
                  );
                }} finally {{
                  resetButton(button);
                  releaseStream();
                  mediaRecorder = null;
                  recordingChunks = [];
                  activeButton = null;
                }}
              }};
              mediaRecorder.start();
            }})
            .catch(function (err) {{
              setStatus("Microphone access denied or unavailable: " + (err.message || err), true);
              resetButton(button);
            }});
        }});
      }});

      window.addEventListener("beforeunload", function () {{
        stopActiveRecorder();
        releaseStream();
      }});

    }})();
  </script>
"""


@admin_blueprint.route("/record", methods=["GET"])
@admin_or_expert_token_required
def record_dashboard():
    selected_language = canonical_language_code(request.args.get("language", ""))
    session_factory = get_session_factory()
    with session_factory() as db:
        sync_system_languages_registry(db)
        db.commit()
        qa_items = sort_qa_items_by_passage_asc(load_recordable_qa_items(db))
        language_options = get_registered_system_languages(db)
        if not selected_language:
            selected_language = language_options[0] if language_options else ""
        grouped_recordings = get_recordings_grouped_by_kind(
            db,
            [item.id for item in qa_items],
            selected_language,
        )
        rows = [
            {
                "qa_item_id": qa_item.id,
                "passage": qa_item.passage_reference or qa_item.passage_id,
                "question": qa_item.question_text,
                "answer": render_record_standard_answer_cell(
                    qa_item,
                    grouped_recordings.get((qa_item.id, "answer"), []),
                    selected_language,
                ),
                "question_recording": render_question_recording_cell(
                    grouped_recordings.get((qa_item.id, "question"), []),
                    qa_item_id=qa_item.id,
                    recording_language=selected_language,
                ),
            }
            for qa_item in qa_items
        ]

    intro = (
        "<p>Record the <strong>question</strong> audio for each passage in the selected "
        "target language. Only QAs marked <strong>reviewed</strong> on "
        f'<a href="{html.escape(url_for("admin.review_qa_dashboard", tab="reviewed"))}">Review QA</a> '
        "appear here. Participants hear the question prompt when answering.</p>"
    )
    if not rows:
        intro += (
            '<p class="field-hint">No reviewed QAs yet. Complete Review QA first '
            f'(Save or Mark as reviewed), then return here.</p>'
        )

    return render_admin_page(
        "Record",
        [
            intro,
            render_record_page(selected_language, language_options, rows),
        ],
        current_path="/admin/record",
    )


@admin_blueprint.route("/system-languages", methods=["GET"])
@admin_or_expert_token_required
def system_languages_dashboard():
    session_factory = get_session_factory()
    with session_factory() as db:
        sync_system_languages_registry(db)
        db.commit()
        language_options = get_registered_system_languages(db)

    return render_admin_page(
        "System Languages",
        [
            "<p>Manage language codes available across the system.</p>",
            render_system_language_panel(language_options),
        ],
        current_path="/admin/system-languages",
    )


@admin_blueprint.route("/system-languages/add", methods=["POST"])
@admin_or_expert_token_required
def system_languages_add():
    code = canonical_language_code(request.form.get("code", ""))
    if not code:
        return redirect(url_for("admin.system_languages_dashboard"))

    session_factory = get_session_factory()
    with session_factory() as db:
        upsert_system_language(db, code, source="manual")
        db.commit()
    return redirect(url_for("admin.system_languages_dashboard"))


@admin_blueprint.route("/system-languages/remove", methods=["POST"])
@admin_or_expert_token_required
def system_languages_remove():
    code = canonical_language_code(request.form.get("code", ""))
    if not code:
        return redirect(url_for("admin.system_languages_dashboard"))

    session_factory = get_session_factory()
    with session_factory() as db:
        language_entry = db.get(SystemLanguage, code)
        if language_entry:
            db.delete(language_entry)
            db.commit()

    return redirect(url_for("admin.system_languages_dashboard"))


@admin_blueprint.route("/record/upload", methods=["POST"])
@admin_or_expert_token_required
def record_upload():
    qa_item_id = (request.form.get("qa_item_id") or "").strip()
    recording_type = (request.form.get("recording_type") or "").strip().lower()
    language = canonical_language_code(request.form.get("language", ""))
    file = request.files.get("audio")

    if not qa_item_id:
        return jsonify({"status": "error", "message": "qa_item_id is required"}), 400
    if recording_type not in {"question", "answer"}:
        return jsonify(
            {"status": "error", "message": "recording_type must be question or answer"},
        ), 400
    if not language:
        return jsonify({"status": "error", "message": "language is required"}), 400
    if not file:
        return jsonify({"status": "error", "message": "audio file is required"}), 400
    if not is_supabase_storage_configured():
        return jsonify({"status": "error", "message": "Supabase Storage is not configured"}), 503

    content = file.read()
    if not content:
        return jsonify({"status": "error", "message": "audio file is empty"}), 400

    content_type = file.mimetype or "audio/webm"
    uploader = session.get("admin_email") or session.get("admin_display_name") or session.get("admin_role")

    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            qa_item = db.get(QAItem, qa_item_id)
            if not qa_item:
                return jsonify({"status": "error", "message": "qa_item not found"}), 404
            if not qa_item_is_recordable(qa_item):
                return jsonify(
                    {
                        "status": "error",
                        "message": "QA must be reviewed on Review QA before recording.",
                    },
                ), 400

            mode = (request.form.get("mode") or "new").strip().lower()
            recording_id = (request.form.get("recording_id") or "").strip()
            version_raw = (request.form.get("version") or "").strip()
            choice_letter = (request.form.get("choice_letter") or "").strip().upper()
            question_type = (qa_item.question_type or "open").strip().lower()
            target_version = 1
            if recording_type == "answer" and choice_letter:
                allowed_letters = "".join(choice_letters_for_type(question_type))
                if choice_letter not in allowed_letters:
                    return jsonify(
                        {
                            "status": "error",
                            "message": f"choice_letter must be one of {allowed_letters}",
                        },
                    ), 400
                target_version = choice_answer_recording_version(choice_letter)

            if mode == "new":
                if recording_type == "question":
                    delete_qa_recordings_for_slot(db, qa_item_id, recording_type, language)
                else:
                    delete_qa_recording_version(
                        db, qa_item_id, recording_type, language, target_version
                    )
                stored = store_qa_recording_audio(
                    content=content,
                    content_type=content_type,
                    qa_item_id=qa_item_id,
                    recording_type=recording_type,
                    language=language,
                    version=target_version,
                )
                record = QAItemRecording(
                    qa_item_id=qa_item_id,
                    recording_type=recording_type,
                    language=language,
                    version=target_version,
                    storage_uri=stored.storage_uri,
                    content_type=stored.content_type,
                    uploaded_by=uploader,
                )
                db.add(record)
                upsert_system_language(db, language, "recording")
                db.commit()
                return jsonify({"status": "ok"})

            if mode == "retake":
                record = None
                if recording_id:
                    record = db.get(QAItemRecording, recording_id)
                elif version_raw.isdigit():
                    record = db.scalar(
                        select(QAItemRecording).where(
                            QAItemRecording.qa_item_id == qa_item_id,
                            QAItemRecording.recording_type == recording_type,
                            QAItemRecording.language == language,
                            QAItemRecording.version == int(version_raw),
                        )
                    )
                if not record:
                    return jsonify(
                        {"status": "error", "message": "Recording version not found"},
                    ), 404
                if (
                    record.qa_item_id != qa_item_id
                    or record.recording_type != recording_type
                    or canonical_language_code(record.language) != language
                ):
                    return jsonify(
                        {"status": "error", "message": "Recording does not match request"},
                    ), 400

                stored = store_qa_recording_audio(
                    content=content,
                    content_type=content_type,
                    qa_item_id=qa_item_id,
                    recording_type=recording_type,
                    language=language,
                    version=record.version,
                )
                record.storage_uri = stored.storage_uri
                record.content_type = stored.content_type
                record.uploaded_by = uploader
                record.created_at = utc_now()
                duplicate_filters = [
                    QAItemRecording.qa_item_id == qa_item_id,
                    QAItemRecording.recording_type == recording_type,
                    QAItemRecording.language == language,
                    QAItemRecording.id != record.id,
                ]
                if recording_type == "answer":
                    duplicate_filters.append(QAItemRecording.version == record.version)
                for duplicate in db.scalars(
                    select(QAItemRecording).where(*duplicate_filters)
                ).all():
                    if duplicate.storage_uri:
                        delete_storage_uri(duplicate.storage_uri)
                    db.delete(duplicate)
            else:
                return jsonify(
                    {
                        "status": "error",
                        "message": "Use Record or Retake; additional versions are not supported",
                    },
                ), 400
            upsert_system_language(db, language, "recording")
            db.commit()
    except Exception as exc:
        logging.exception("Failed to upload QA recording")
        return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify({"status": "ok"})


@admin_blueprint.route("/record/delete", methods=["POST"])
@admin_or_expert_token_required
def record_delete():
    recording_id = (request.form.get("recording_id") or "").strip()
    if not recording_id:
        return jsonify({"status": "error", "message": "recording_id is required"}), 400

    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            record = db.get(QAItemRecording, recording_id)
            if not record:
                return jsonify({"status": "error", "message": "Recording not found"}), 404

            storage_uri = record.storage_uri
            db.delete(record)
            db.commit()

        if storage_uri:
            delete_storage_uri(storage_uri)
    except Exception as exc:
        logging.exception("Failed to delete QA recording")
        return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify({"status": "ok"})


def render_audio_export_group_header(group_key, title, meta_text):
    body_id = html.escape(f"audio-export-body-{group_key}")
    return f"""
    <div class="audio-export-group-header">
      <button
        type="button"
        class="nav-link group-toggle"
        aria-expanded="true"
        aria-controls="{body_id}"
        title="Collapse or expand"
      >▼</button>
      <label>
        <input type="checkbox" class="group-select">
        <strong>{html.escape(title)}</strong>
        <span class="audio-meta">{html.escape(meta_text)}</span>
      </label>
    </div>
    <div id="{body_id}" class="audio-export-group-body">
"""


def render_audio_export_response_row(item):
    row_class = "audio-export-response-row"
    checkbox_html = ""
    if item.has_storage:
        checkbox_html = (
            f'<input type="checkbox" class="response-select" '
            f'name="response_ids" value="{html.escape(item.response_id)}">'
        )
    else:
        row_class += " is-disabled"

    storage_note = (
        ""
        if item.has_storage
        else "<span class='audio-meta'>File not stored</span>"
    )
    received_at_text = format_display_datetime(item.received_at)
    received_html = (
        f'<span class="audio-meta" title="Response received (UTC)">'
        f"Received {html.escape(received_at_text)}</span>"
        if received_at_text
        else ""
    )
    return (
        f"<li>"
        f'<div class="{row_class}">'
        f"{checkbox_html}"
        f'<span class="export-filename">{html.escape(item.export_filename)}</span>'
        f"<span>{html.escape(item.participant_label)} "
        f"({html.escape(item.wa_id)})</span>"
        f"{received_html}"
        f"{storage_note}"
        f"</div></li>"
    )


def render_audio_export_page(chapters):
    if not is_supabase_storage_configured():
        config_warning = (
            "<p class='status-banner error'>"
            "Supabase Storage is not configured. Audio files cannot be downloaded until "
            "<code>SUPABASE_URL</code> and <code>SUPABASE_SERVICE_ROLE_KEY</code> are set."
            "</p>"
        )
    else:
        config_warning = ""

    if not chapters:
        return (
            config_warning
            + "<p>No audio responses with recordings found yet.</p>"
        )

    download_zip_url = html.escape(url_for("admin.export_audio_download"))
    single_download_template = html.escape(
        url_for("admin.export_audio_file", response_id="__ID__")
    )
    chapter_sections = []

    for chapter in chapters:
        chapter_file_count = sum(
            1
            for qa_group in chapter.qa_groups
            for item in qa_group.items
            if item.has_storage
        )
        qa_sections = []
        for qa_group in chapter.qa_groups:
            qa_file_count = sum(1 for item in qa_group.items if item.has_storage)
            response_rows = "".join(
                render_audio_export_response_row(item) for item in qa_group.items
            )
            qa_key = html.escape(f"{chapter.chapter_key}-qa-{qa_group.qa_item_id}")
            qa_sections.append(
                f"""
      <section class="audio-export-group audio-export-qa" data-group-key="{qa_key}">
        {render_audio_export_group_header(qa_key, qa_group.question_label, f"({qa_file_count} audio file{'s' if qa_file_count != 1 else ''})")}
          <ul class="audio-export-responses">
            {response_rows}
          </ul>
        </div>
      </section>"""
            )

        chapter_key = html.escape(chapter.chapter_key)
        chapter_sections.append(
            f"""
  <section class="audio-export-group audio-export-chapter" data-group-key="{chapter_key}">
    {render_audio_export_group_header(chapter_key, chapter.chapter_label, f"({chapter_file_count} audio file{'s' if chapter_file_count != 1 else ''})")}
      {"".join(qa_sections)}
    </div>
  </section>"""
        )

    return f"""
  {config_warning}
  <form
    id="audio-export-form"
    method="post"
    action="{download_zip_url}"
    data-single-download-url="{single_download_template}"
  >
    <div class="audio-export-toolbar">
      <button type="button" class="nav-link" id="select-all-passages">Select all passages</button>
      <button type="button" class="nav-link" id="clear-all-passages">Clear selection</button>
      <button type="button" class="nav-link" id="download-selected">Download</button>
      <button type="submit" class="nav-link">Download (.zip)</button>
    </div>
    {"".join(chapter_sections)}
  </form>
  <script>
    (function () {{
      const form = document.getElementById("audio-export-form");
      if (!form) return;

      function setDescendantsChecked(group, checked) {{
        group.querySelectorAll(".response-select, .group-select").forEach(function (box) {{
          box.checked = checked;
          box.indeterminate = false;
        }});
      }}

      function syncGroupSelect(group) {{
        const responses = group.querySelectorAll(".response-select");
        if (!responses.length) return;
        const checked = group.querySelectorAll(".response-select:checked");
        const groupBox = group.querySelector(":scope > .audio-export-group-header .group-select");
        if (!groupBox) return;
        groupBox.checked = checked.length === responses.length;
        groupBox.indeterminate = checked.length > 0 && checked.length < responses.length;
      }}

      function syncAncestorGroups(group) {{
        let parent = group.parentElement ? group.parentElement.closest(".audio-export-group") : null;
        while (parent) {{
          syncGroupSelect(parent);
          parent = parent.parentElement ? parent.parentElement.closest(".audio-export-group") : null;
        }}
      }}

      form.querySelectorAll(".group-toggle").forEach(function (toggleButton) {{
        toggleButton.addEventListener("click", function () {{
          const group = toggleButton.closest(".audio-export-group");
          if (!group) return;
          const collapsed = group.classList.toggle("is-collapsed");
          toggleButton.setAttribute("aria-expanded", collapsed ? "false" : "true");
          toggleButton.textContent = collapsed ? "▶" : "▼";
        }});
      }});

      form.querySelectorAll(".group-select").forEach(function (groupCheckbox) {{
        groupCheckbox.addEventListener("change", function () {{
          const group = groupCheckbox.closest(".audio-export-group");
          if (!group) return;
          setDescendantsChecked(group, groupCheckbox.checked);
          syncAncestorGroups(group);
        }});
      }});

      form.querySelectorAll(".response-select").forEach(function (responseCheckbox) {{
        responseCheckbox.addEventListener("change", function () {{
          const group = responseCheckbox.closest(".audio-export-group");
          if (!group) return;
          syncGroupSelect(group);
          syncAncestorGroups(group);
        }});
      }});

      document.getElementById("select-all-passages").addEventListener("click", function () {{
        form.querySelectorAll(".audio-export-chapter").forEach(function (chapterGroup) {{
          setDescendantsChecked(chapterGroup, true);
        }});
      }});

      document.getElementById("clear-all-passages").addEventListener("click", function () {{
        form.querySelectorAll(".response-select, .group-select").forEach(function (box) {{
          box.checked = false;
          box.indeterminate = false;
        }});
      }});

      document.getElementById("download-selected").addEventListener("click", function () {{
        const checked = form.querySelectorAll(".response-select:checked");
        if (checked.length === 0) {{
          window.alert("Select one audio file to download.");
          return;
        }}
        if (checked.length > 1) {{
          window.alert("Select exactly one file for Download, or use Download (.zip) for multiple.");
          return;
        }}
        const template = form.dataset.singleDownloadUrl || "";
        window.location.href = template.replace("__ID__", encodeURIComponent(checked[0].value));
      }});
    }})();
  </script>
"""


@admin_blueprint.route("/export/audio", methods=["GET"])
@admin_token_required
def export_audio_dashboard():
    chapters = get_audio_export_chapters()
    error = request.args.get("error")
    status_html = render_status_banner(error, "error") if error else ""
    return render_admin_page(
        "Export Audio",
        [
            status_html,
            render_audio_export_page(chapters),
        ],
        current_path="/admin/export/audio",
    )


@admin_blueprint.route("/export/audio/file/<response_id>", methods=["GET"])
@admin_token_required
def export_audio_file(response_id):
    try:
        content, content_type, filename = fetch_response_audio_bytes(response_id)
    except Exception as exc:
        return redirect(
            url_for("admin.export_audio_dashboard", error=f"Download failed: {exc}")
        )

    if not content:
        return redirect(
            url_for(
                "admin.export_audio_dashboard",
                error="Audio file not found or not stored in Supabase.",
            )
        )

    return Response(
        content,
        mimetype=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_blueprint.route("/export/audio/download", methods=["POST"])
@admin_token_required
def export_audio_download():
    response_ids = request.form.getlist("response_ids")
    if not response_ids:
        return redirect(
            url_for(
                "admin.export_audio_dashboard",
                error="Select at least one audio recording to download.",
            )
        )

    try:
        archive_bytes, included, errors = build_zip_archive(response_ids)
    except ValueError as exc:
        return redirect(url_for("admin.export_audio_dashboard", error=str(exc)))
    except Exception as exc:
        return redirect(
            url_for("admin.export_audio_dashboard", error=f"ZIP failed: {exc}")
        )

    if errors:
        logging.warning("Audio export completed with %s errors", len(errors))

    filename = zip_download_filename()
    return Response(
        archive_bytes,
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_blueprint.route("/export/responses.csv", methods=["GET"])
@admin_token_required
def export_responses_csv():
    return build_csv_response(get_responses(flagged_only=False), "responses.csv")


@admin_blueprint.route("/export/flagged.csv", methods=["GET"])
@admin_token_required
def export_flagged_csv():
    return build_csv_response(get_responses(flagged_only=True), "flagged.csv")
