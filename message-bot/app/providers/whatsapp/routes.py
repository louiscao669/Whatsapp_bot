import logging
import json

from flask import Blueprint, request, jsonify, current_app

from app.providers.whatsapp.security import signature_required
from app.providers.whatsapp.messaging import (
    process_whatsapp_message,
    is_valid_whatsapp_message,
)

webhook_blueprint = Blueprint("webhook", __name__)


def _get_first_change_value(body):
    try:
        return body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
    except (AttributeError, IndexError, TypeError):
        return {}


def _describe_webhook_event(body):
    if not isinstance(body, dict):
        return "unknown or non-WhatsApp event"

    value = _get_first_change_value(body)

    statuses = value.get("statuses") or []
    if statuses:
        status_names = sorted(
            {
                status.get("status", "unknown")
                for status in statuses
                if isinstance(status, dict)
            }
        )
        return "message status update: " + ", ".join(status_names or ["unknown"])

    messages = value.get("messages") or []
    if messages:
        message_types = sorted(
            {
                message.get("type", "unknown")
                for message in messages
                if isinstance(message, dict)
            }
        )
        return "incoming user message: " + ", ".join(message_types or ["unknown"])

    if body.get("object") == "whatsapp_business_account":
        return "webhook test event or unsupported WhatsApp event"

    return "unknown or non-WhatsApp event"


def handle_message():
    """
    Handle incoming webhook events from the WhatsApp API.

    This function processes incoming WhatsApp messages and other events,
    such as delivery statuses. If the event is a valid message, it gets
    processed. If the incoming payload is not a recognized WhatsApp event,
    an error is returned.

    Every message send will trigger 4 HTTP requests to your webhook: message, sent, delivered, read.

    Returns:
        response: A tuple containing a JSON response and an HTTP status code.
    """
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        logging.info("=== WEBHOOK RECEIVED ===")
        logging.info(json.dumps(body, indent=2, ensure_ascii=False))
        logging.info("Webhook event type: %s", _describe_webhook_event(body))
        return jsonify({"status": "ok", "message": "Webhook event logged"}), 200

    logging.info("=== WEBHOOK RECEIVED ===")
    logging.info(json.dumps(body, indent=2, ensure_ascii=False))
    logging.info("Webhook event type: %s", _describe_webhook_event(body))

    # Check if it's a WhatsApp status update
    if _get_first_change_value(body).get("statuses"):
        return jsonify({"status": "ok"}), 200

    try:
        if is_valid_whatsapp_message(body):
            process_whatsapp_message(body)
            return jsonify({"status": "ok"}), 200
        else:
            return jsonify({"status": "ok", "message": "Webhook event logged"}), 200
    except json.JSONDecodeError:
        logging.error("Failed to decode JSON")
        return jsonify({"status": "error", "message": "Invalid JSON provided"}), 400


# Required webhook verifictaion for WhatsApp
def verify():
    # Parse params from the webhook verification request
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    # Check if a token and mode were sent
    if mode and token:
        # Check the mode and token sent are correct
        if mode == "subscribe" and token == current_app.config["VERIFY_TOKEN"]:
            # Respond with 200 OK and challenge token from the request
            logging.info("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            # Responds with '403 Forbidden' if verify tokens do not match
            logging.info("VERIFICATION_FAILED")
            return jsonify({"status": "error", "message": "Verification failed"}), 403
    else:
        # Responds with '400 Bad Request' if verify tokens do not match
        logging.info("MISSING_PARAMETER")
        return jsonify({"status": "error", "message": "Missing parameters"}), 400


@webhook_blueprint.route("/webhook", methods=["GET"])
def webhook_get():
    return verify()

@webhook_blueprint.route("/webhook", methods=["POST"])
@signature_required
def webhook_post():
    return handle_message()
