import csv
import html
import hmac
import io
import json
from functools import wraps

from flask import Blueprint, Response, current_app, jsonify, redirect, request, session, url_for
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_session_factory
from app.models import Participant, ParticipantResponse, QAItem


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
    "language",
    "question_text",
    "expected_answer",
    "required_keywords",
    "assignment_id",
    "batch_id",
    "response_type",
    "response_text",
    "media_id",
    "media_url",
    "transcript_text",
    "normalized_text",
    "correctness_score",
    "matched_keywords",
    "missing_keywords",
    "is_flagged",
    "flag_reason",
    "review_status",
]


ROLE_CONFIG = {
    "admin": "ADMIN_API_TOKEN",
    "expert": "EXPERT_API_TOKEN",
}


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
            configured_roles = [
                role
                for role in allowed_roles
                if current_app.config.get(ROLE_CONFIG[role])
            ]
            if not configured_roles:
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

            if session_role_allowed(configured_roles):
                return f(*args, **kwargs)

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


def render_login_page(error_message=""):
    error_html = (
        f"<p style=\"color: #b00020;\">{html.escape(error_message)}</p>"
        if error_message
        else ""
    )
    return Response(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Admin Login</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; max-width: 32rem; }}
    label {{ display: block; margin: 1rem 0 0.25rem; }}
    input {{ width: 100%; padding: 0.5rem; }}
    button {{ margin-top: 1rem; padding: 0.5rem 1rem; }}
  </style>
</head>
<body>
  <h1>Admin Login</h1>
  {error_html}
  <form method="post">
    <input type="hidden" name="next" value="{html.escape(request.args.get('next', '/admin/analytics'))}">
    <label for="token">Admin or expert token</label>
    <input id="token" name="token" type="password" autocomplete="current-password" required>
    <button type="submit">Log in</button>
  </form>
</body>
</html>""",
        mimetype="text/html",
    )


@admin_blueprint.route("/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_login_page()

    token = request.form.get("token", "")
    role = get_role_for_token(token)
    if not role:
        return render_login_page("Invalid token"), 401

    session.clear()
    session["admin_role"] = role
    next_url = request.form.get("next") or "/admin/analytics"
    if not next_url.startswith("/admin/"):
        next_url = "/admin/analytics"

    return redirect(next_url)


@admin_blueprint.route("/logout", methods=["GET", "POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin.admin_login"))


def serialize_datetime(value):
    return value.isoformat() if value else ""


def serialize_json(value):
    return json.dumps(value or [], ensure_ascii=False)


def response_to_row(response):
    participant = response.participant
    qa_item = response.qa_item
    assignment = response.assignment

    return {
        "response_id": response.id,
        "received_at": serialize_datetime(response.received_at),
        "participant_id": participant.id if participant else "",
        "participant_wa_id": participant.wa_id if participant else "",
        "participant_display_name": participant.display_name if participant else "",
        "qa_item_id": qa_item.id if qa_item else "",
        "passage_id": qa_item.passage_id if qa_item else "",
        "passage_reference": qa_item.passage_reference if qa_item else "",
        "language": qa_item.language if qa_item else "",
        "question_text": qa_item.question_text if qa_item else "",
        "expected_answer": qa_item.expected_answer if qa_item else "",
        "required_keywords": serialize_json(qa_item.required_keywords if qa_item else []),
        "assignment_id": assignment.id if assignment else "",
        "batch_id": assignment.batch_id if assignment else "",
        "response_type": response.response_type,
        "response_text": response.response_text or "",
        "media_id": response.media_id or "",
        "media_url": response.media_url or "",
        "transcript_text": response.transcript_text or "",
        "normalized_text": response.normalized_text or "",
        "correctness_score": (
            "" if response.correctness_score is None else response.correctness_score
        ),
        "matched_keywords": serialize_json(response.matched_keywords),
        "missing_keywords": serialize_json(response.missing_keywords),
        "is_flagged": response.is_flagged,
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
        statement = statement.where(ParticipantResponse.is_flagged.is_(True))

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


def render_admin_page(title, sections):
    section_html = "\n".join(sections)
    return Response(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    code {{ background: #f5f5f5; padding: 0.1rem 0.25rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  {section_html}
</body>
</html>""",
        mimetype="text/html",
    )


def render_table(columns, rows):
    header = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td>{html.escape(str(row.get(key, '') if row.get(key, '') is not None else ''))}</td>"
            for key, _ in columns
        )
        body_rows.append(f"<tr>{cells}</tr>")

    body = "\n".join(body_rows) or (
        f"<tr><td colspan=\"{len(columns)}\">No records found.</td></tr>"
    )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


@admin_blueprint.route("/qa-items", methods=["GET"])
@admin_token_required
def qa_items_dashboard():
    session_factory = get_session_factory()
    with session_factory() as db:
        qa_items = db.scalars(select(QAItem).order_by(QAItem.created_at.desc())).all()

    rows = [
        {
            "id": qa_item.id,
            "passage": qa_item.passage_reference or qa_item.passage_id,
            "language": qa_item.language,
            "question": qa_item.question_text,
            "min_responses": qa_item.min_responses_required,
            "review_priority": qa_item.review_priority,
            "active": qa_item.active,
        }
        for qa_item in qa_items
    ]
    return render_admin_page(
        "QA Items",
        [
            "<p>Admin/distributor view for managing the QA pool. Upload/edit actions can be added here next.</p>",
            render_table(
                [
                    ("id", "ID"),
                    ("passage", "Passage"),
                    ("language", "Language"),
                    ("question", "Question"),
                    ("min_responses", "Min responses"),
                    ("review_priority", "Review priority"),
                    ("active", "Active"),
                ],
                rows,
            ),
        ],
    )


@admin_blueprint.route("/review", methods=["GET"])
@expert_token_required
def expert_review_dashboard():
    responses = get_responses(flagged_only=True)
    rows = [
        {
            "received_at": serialize_datetime(response.received_at),
            "participant": response.participant.id if response.participant else "",
            "passage": response.qa_item.passage_reference or response.qa_item.passage_id
            if response.qa_item
            else "",
            "question": response.qa_item.question_text if response.qa_item else "",
            "answer": response.transcript_text or response.response_text or "",
            "score": response.correctness_score,
            "missing": ", ".join(response.missing_keywords or []),
            "reason": response.flag_reason or "",
            "status": response.review_status,
        }
        for response in responses
    ]
    return render_admin_page(
        "Expert Review",
        [
            "<p>Expert reviewer view for flagged participant responses.</p>",
            render_table(
                [
                    ("received_at", "Received"),
                    ("participant", "Participant"),
                    ("passage", "Passage"),
                    ("question", "Question"),
                    ("answer", "Answer/transcript"),
                    ("score", "Score"),
                    ("missing", "Missing keywords"),
                    ("reason", "Flag reason"),
                    ("status", "Review status"),
                ],
                rows,
            ),
        ],
    )


@admin_blueprint.route("/analytics", methods=["GET"])
@admin_or_expert_token_required
def analytics_dashboard():
    responses = get_responses(flagged_only=False)
    session_factory = get_session_factory()
    with session_factory() as db:
        participant_count = len(db.scalars(select(Participant.id)).all())
        qa_item_count = len(db.scalars(select(QAItem.id)).all())

    total_responses = len(responses)
    flagged_count = sum(1 for response in responses if response.is_flagged)
    scored_responses = [
        response.correctness_score
        for response in responses
        if response.correctness_score is not None
    ]
    average_score = (
        round(sum(scored_responses) / len(scored_responses), 3)
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
        metrics["flagged"] += 1 if response.is_flagged else 0
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
                "average_score": round(metrics["score_sum"] / metrics["scored"], 3)
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
    )


@admin_blueprint.route("/participants", methods=["GET"])
@admin_token_required
def participants_dashboard():
    session_factory = get_session_factory()
    with session_factory() as db:
        participants = db.scalars(select(Participant).order_by(Participant.created_at.desc())).all()

    rows = [
        {
            "id": participant.id,
            "wa_id": participant.wa_id,
            "display_name": participant.display_name or "",
            "language": participant.target_language or "",
            "completed": participant.completed_count,
            "batch_size": participant.preferred_batch_size,
            "last_seen": serialize_datetime(participant.last_seen_at),
            "consented": participant.consented,
        }
        for participant in participants
    ]
    return render_admin_page(
        "Participants",
        [
            "<p>Admin-only participant metadata view. Restrict access because it includes WhatsApp IDs.</p>",
            render_table(
                [
                    ("id", "ID"),
                    ("wa_id", "WhatsApp ID"),
                    ("display_name", "Display name"),
                    ("language", "Language"),
                    ("completed", "Completed"),
                    ("batch_size", "Batch size"),
                    ("last_seen", "Last seen"),
                    ("consented", "Consented"),
                ],
                rows,
            ),
        ],
    )


@admin_blueprint.route("/export/responses.csv", methods=["GET"])
@admin_token_required
def export_responses_csv():
    return build_csv_response(get_responses(flagged_only=False), "responses.csv")


@admin_blueprint.route("/export/flagged.csv", methods=["GET"])
@admin_token_required
def export_flagged_csv():
    return build_csv_response(get_responses(flagged_only=True), "flagged.csv")
