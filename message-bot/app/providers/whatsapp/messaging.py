import json
import logging

import requests
from flask import current_app, jsonify

from app.messaging.workflow import (
    record_whatsapp_audio_message,
    record_whatsapp_text_message,
)
from app.providers.whatsapp.schedule_policy import (
    BATCH_NEXT_START_NOW_REPLY,
    BATCH_NEXT_WAIT_REPLY,
    format_batch_next_assign_hour,
)
from eten_shared.mcq import (
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_TF,
    choice_letters_for_type,
    format_choices_for_display,
)


def log_http_response(response):
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")


def get_text_message_input(recipient, text):
    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
    )


def get_audio_message_input(recipient, audio_url):
    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "audio",
            "audio": {"link": audio_url},
        }
    )


def _truncate_whatsapp_text(value, max_length):
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def get_choice_list_message_input(recipient, prompt):
    question_type = (getattr(prompt, "question_type", None) or "open").strip().lower()
    choices = list(prompt.mcq_choices or ())
    letters = choice_letters_for_type(question_type)
    rows = []
    for index, choice in enumerate(choices[: len(letters)]):
        rows.append(
            {
                "id": f"mcq_{index}",
                "title": letters[index],
                "description": _truncate_whatsapp_text(choice, 72),
            }
        )

    body_lines = []
    if prompt.passage_reference:
        body_lines.append(f"Passage: {prompt.passage_reference}")
    body_lines.append(prompt.question_text)
    if question_type == QUESTION_TYPE_TF:
        body_lines.append("Tap Choose an answer and pick A or B.")
    else:
        body_lines.append("Tap Choose an answer and pick A–D.")

    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": _truncate_whatsapp_text("\n\n".join(body_lines), 1024)},
                "action": {
                    "button": "Choose answer",
                    "sections": [{"title": "Choices", "rows": rows}],
                },
            },
        }
    )


def get_next_batch_choice_message_input(recipient):
    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": (
                        "Would you like to start a new batch now, or wait "
                        f"until tomorrow at {format_batch_next_assign_hour()}?"
                    )
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": BATCH_NEXT_START_NOW_REPLY,
                                "title": "Start now",
                            },
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": BATCH_NEXT_WAIT_REPLY,
                                "title": "Tomorrow",
                            },
                        },
                    ]
                },
            },
        }
    )


def get_assignment_prompt_text(prompt):
    parts = []
    if prompt.passage_reference:
        parts.append(f"Passage: {prompt.passage_reference}")

    question_type = (getattr(prompt, "question_type", None) or "open").strip().lower()
    if question_type in {QUESTION_TYPE_MCQ, QUESTION_TYPE_TF} and getattr(prompt, "mcq_choices", None):
        if prompt.audio_url:
            parts.append("Listen to the audio, then choose your answer:")
        elif question_type == QUESTION_TYPE_TF:
            parts.append("Choose your answer (reply A or B):")
        else:
            parts.append("Choose your answer (reply A, B, C, or D):")
        parts.append(prompt.question_text)
        parts.append(format_choices_for_display(list(prompt.mcq_choices), question_type))
        return "\n\n".join(parts)

    if prompt.audio_url:
        parts.append("Listen to the audio, then reply with your answer:")
    else:
        parts.append("Reply with your answer:")

    parts.append(prompt.question_text)
    return "\n\n".join(parts)


def send_assignment_prompt(recipient, prompt):
    if prompt.audio_url:
        send_message(get_audio_message_input(recipient, prompt.audio_url))

    question_type = (getattr(prompt, "question_type", None) or "open").strip().lower()
    if question_type in {QUESTION_TYPE_MCQ, QUESTION_TYPE_TF} and getattr(prompt, "mcq_choices", None):
        send_message(get_choice_list_message_input(recipient, prompt))
        return

    send_message(get_text_message_input(recipient, get_assignment_prompt_text(prompt)))


def get_batch_complete_message(completed_batch_size, currency_awards=(), currency_balance=None):
    question_label = "question" if completed_batch_size == 1 else "questions"
    message = (
        f"Thanks, your answer was recorded. Batch complete: "
        f"you finished {completed_batch_size} {question_label}."
    )
    earned = sum(
        award.get("amount", 0)
        for award in currency_awards
        if award.get("amount", 0) > 0
    )
    if earned and currency_balance is not None:
        coin_label = "coin" if earned == 1 else "coins"
        message += f"\n\n+{earned} {coin_label} earned. Balance: {currency_balance}."
    return message


def get_badge_message(badge):
    return (
        f"Badge earned: {badge['title']}\n"
        f"{badge['description']}"
    )


def send_badge_messages(recipient, badges):
    for badge in badges:
        send_message(get_text_message_input(recipient, get_badge_message(badge)))


def send_next_batch_choice_message(recipient):
    send_message(get_next_batch_choice_message_input(recipient))


def get_no_assignment_message(response_recorded):
    if response_recorded:
        return "Thanks, your answer was recorded. No more questions are available right now."

    return "Thanks for checking in. No questions are available right now."


def send_message(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }

    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/messages"

    try:
        response = requests.post(
            url, data=data, headers=headers, timeout=10
        )
        response.raise_for_status()
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return jsonify({"status": "error", "message": "Request timed out"}), 408
    except requests.RequestException as e:
        logging.error(f"Request failed due to: {e}")
        return jsonify({"status": "error", "message": "Failed to send message"}), 500
    else:
        log_http_response(response)
        return response


def extract_inbound_message_payload(message):
    message_type = message.get("type")

    if message_type == "text":
        return message["text"]["body"], message_type

    if message_type == "interactive":
        interactive = message.get("interactive") or {}
        interactive_type = interactive.get("type")
        if interactive_type == "list_reply":
            reply = interactive.get("list_reply") or {}
            return reply.get("id") or reply.get("title") or "", "text"
        if interactive_type == "button_reply":
            reply = interactive.get("button_reply") or {}
            return reply.get("id") or reply.get("title") or "", "text"

    if message_type == "audio":
        return None, message_type

    return None, message_type


def process_whatsapp_message(body):
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]

    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    message_type = message.get("type")
    payload_text, normalized_type = extract_inbound_message_payload(message)

    if normalized_type == "text":
        workflow_result = record_whatsapp_text_message(
            wa_id=wa_id,
            display_name=name,
            message_id=message.get("id"),
            message_text=payload_text,
        )
    elif message_type == "audio":
        audio = message.get("audio", {})
        workflow_result = record_whatsapp_audio_message(
            wa_id=wa_id,
            display_name=name,
            message_id=message.get("id"),
            media_id=audio.get("id"),
            mime_type=audio.get("mime_type"),
            sha256=audio.get("sha256"),
            voice=audio.get("voice"),
        )
    else:
        logging.info("Unsupported WhatsApp message type: %s", message_type)
        send_message(
            get_text_message_input(
                wa_id,
                "Please reply with a text message, tap a list option, or send a voice note.",
            )
        )
        return

    logging.info(
        "Processed WhatsApp workflow for participant %s in state %s",
        workflow_result.participant_id,
        workflow_result.session_state,
    )

    if workflow_result.awarded_badges:
        send_badge_messages(wa_id, workflow_result.awarded_badges)

    if workflow_result.status_message:
        send_message(get_text_message_input(wa_id, workflow_result.status_message))
        return

    if workflow_result.batch_completed:
        send_message(
            get_text_message_input(
                wa_id,
                get_batch_complete_message(
                    workflow_result.completed_batch_size,
                    workflow_result.currency_awards,
                    workflow_result.currency_balance,
                ),
            )
        )
        send_next_batch_choice_message(wa_id)

    if workflow_result.prompt:
        send_assignment_prompt(wa_id, workflow_result.prompt)
        return

    if workflow_result.batch_completed:
        return

    response = get_no_assignment_message(response_recorded=bool(workflow_result.response_id))
    send_message(get_text_message_input(wa_id, response))


def is_valid_whatsapp_message(body):
    """
    Check if the incoming webhook event has a valid WhatsApp message structure.
    """
    return (
        body.get("object")
        and body.get("entry")
        and body["entry"][0].get("changes")
        and body["entry"][0]["changes"][0].get("value")
        and body["entry"][0]["changes"][0]["value"].get("messages")
        and body["entry"][0]["changes"][0]["value"]["messages"][0]
    )
