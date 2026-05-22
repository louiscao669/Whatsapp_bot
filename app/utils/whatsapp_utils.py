import logging
from flask import current_app, jsonify
import json
import requests

from app.services.chatbot_workflow import (
    record_whatsapp_audio_message,
    record_whatsapp_text_message,
)

# from app.services.openai_service import generate_response
import re


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


def get_assignment_prompt_text(prompt):
    parts = []
    if prompt.passage_reference:
        parts.append(f"Passage: {prompt.passage_reference}")

    if prompt.audio_url:
        parts.append("Listen to the audio, then reply with your answer:")
    else:
        parts.append("Reply with your answer:")

    parts.append(prompt.question_text)
    return "\n\n".join(parts)


def send_assignment_prompt(recipient, prompt):
    if prompt.audio_url:
        send_message(get_audio_message_input(recipient, prompt.audio_url))

    send_message(get_text_message_input(recipient, get_assignment_prompt_text(prompt)))


def get_no_assignment_message(response_recorded):
    if response_recorded:
        return "Thanks, your answer was recorded. No more questions are available right now."

    return "Thanks for checking in. No questions are available right now."


def generate_response(response):
    # Return text in uppercase
    return response.upper()


def send_message(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }

    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/messages"

    try:
        response = requests.post(
            url, data=data, headers=headers, timeout=10
        )  # 10 seconds timeout as an example
        response.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return jsonify({"status": "error", "message": "Request timed out"}), 408
    except (
        requests.RequestException
    ) as e:  # This will catch any general request exception
        logging.error(f"Request failed due to: {e}")
        return jsonify({"status": "error", "message": "Failed to send message"}), 500
    else:
        # Process the response as normal
        log_http_response(response)
        return response


def process_text_for_whatsapp(text):
    # Remove brackets
    pattern = r"\【.*?\】"
    # Substitute the pattern with an empty string
    text = re.sub(pattern, "", text).strip()

    # Pattern to find double asterisks including the word(s) in between
    pattern = r"\*\*(.*?)\*\*"

    # Replacement pattern with single asterisks
    replacement = r"*\1*"

    # Substitute occurrences of the pattern with the replacement
    whatsapp_style_text = re.sub(pattern, replacement, text)

    return whatsapp_style_text


def process_whatsapp_message(body):
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]

    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    message_type = message.get("type")

    if message_type == "text":
        workflow_result = record_whatsapp_text_message(
            wa_id=wa_id,
            display_name=name,
            message_id=message.get("id"),
            message_text=message["text"]["body"],
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
                "Please reply with a text message or voice note.",
            )
        )
        return

    logging.info(
        "Processed WhatsApp workflow for participant %s in state %s",
        workflow_result.participant_id,
        workflow_result.session_state,
    )

    if workflow_result.prompt:
        send_assignment_prompt(wa_id, workflow_result.prompt)
        return

    response = get_no_assignment_message(response_recorded=bool(workflow_result.response_id))
    data = get_text_message_input(wa_id, response)
    send_message(data)


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
