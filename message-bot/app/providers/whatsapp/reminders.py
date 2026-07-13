"""WhatsApp reminder delivery and template scheduling."""

import os

import requests

from eten_shared.models import Reminder, ReminderStatus, utc_now
from app.providers.whatsapp.schedule_policy import (
    TEMPLATE_REMINDER_TYPE,
    build_reminder_message,
    get_reminder_template_language,
    get_reminder_template_name,
    get_template_reminder_max_count,
    get_template_reminder_repeat_delay,
    is_template_reminder,
)


def get_graph_api_version():
    return os.getenv("VERSION", "v25.0")


def get_template_body_parameters(participant, assignment, reminder, recipient=""):
    configured_value = os.getenv("REMINDER_TEMPLATE_BODY_PARAMS", "")
    if not configured_value.strip():
        return []

    context = {
        "name": participant.display_name or "there",
        "wa_id": recipient,
        "participant_id": participant.id,
        "assignment_id": assignment.id if assignment else "",
        "reminder_type": reminder.reminder_type if reminder else "",
    }
    return [
        value.strip().format(**context)
        for value in configured_value.split(",")
        if value.strip()
    ]


def build_template_message_input(
    recipient,
    template_name,
    language_code,
    body_parameters=None,
):
    template = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if body_parameters:
        template["components"] = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": value} for value in body_parameters
                ],
            }
        ]

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "template",
        "template": template,
    }


def get_text_message_input(recipient, text):
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }


def send_whatsapp_message(payload):
    access_token = os.getenv("ACCESS_TOKEN")
    phone_number_id = os.getenv("PHONE_NUMBER_ID")
    if not access_token or not phone_number_id:
        raise RuntimeError("ACCESS_TOKEN and PHONE_NUMBER_ID are required to send reminders")

    url = (
        f"https://graph.facebook.com/{get_graph_api_version()}/"
        f"{phone_number_id}/messages"
    )
    response = requests.post(
        url,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response


def send_whatsapp_text(recipient, text):
    return send_whatsapp_message(get_text_message_input(recipient, text))


def send_whatsapp_template(recipient, participant, assignment, reminder):
    template_name = (reminder.delivery_metadata or {}).get("template_name") or get_reminder_template_name()
    if not template_name:
        raise RuntimeError("REMINDER_TEMPLATE_NAME is required to send template reminders")

    language_code = (
        (reminder.delivery_metadata or {}).get("template_language")
        or get_reminder_template_language()
    )
    return send_whatsapp_message(
        build_template_message_input(
            recipient=recipient,
            template_name=template_name,
            language_code=language_code,
            body_parameters=get_template_body_parameters(
                participant, assignment, reminder, recipient
            ),
        )
    )


def send_reminder(participant, assignment, reminder, recipient):
    if is_template_reminder(reminder):
        return send_whatsapp_template(
            recipient,
            participant,
            assignment,
            reminder,
        )
    return send_whatsapp_text(recipient, reminder.message_text)


def create_next_template_reminder(db, reminder, assignment, participant):
    metadata = reminder.delivery_metadata or {}
    template_count = int(metadata.get("template_count", 1))
    max_count = get_template_reminder_max_count()
    if max_count and template_count >= max_count:
        return None

    repeat_delay = get_template_reminder_repeat_delay()
    next_count = template_count + 1
    next_reminder = Reminder(
        participant_id=participant.id,
        assignment_id=assignment.id,
        reminder_type=TEMPLATE_REMINDER_TYPE,
        message_text=build_reminder_message(TEMPLATE_REMINDER_TYPE),
        status=ReminderStatus.PENDING.value,
        scheduled_for=utc_now() + repeat_delay,
        delivery_metadata={
            "delay_hours": int(repeat_delay.total_seconds() // 3600),
            "message_kind": "template",
            "provider": "whatsapp",
            "template_name": get_reminder_template_name(),
            "template_language": get_reminder_template_language(),
            "template_count": next_count,
            "previous_reminder_id": reminder.id,
        },
    )
    db.add(next_reminder)
    return next_reminder
