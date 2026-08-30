from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from eten_shared.participant_identity import delivery_address
from eten_shared.domain.identity import PROVIDER_WHATSAPP, provider_external_id
from eten_shared.models import ParticipantProviderContact
from eten_shared.answer_receipts import record_assignment_delivery


@dataclass(frozen=True)
class DeliveryResult:
    provider: str
    status_code: int = 200


def active_provider_contact(db, participant):
    contact = db.scalars(
        select(ParticipantProviderContact)
        .where(
            ParticipantProviderContact.participant_id == participant.id,
            ParticipantProviderContact.opted_out_at.is_(None),
        )
        .order_by(ParticipantProviderContact.updated_at.desc())
    ).first()
    return contact


def provider_name_for_participant(db, participant):
    contact = active_provider_contact(db, participant)
    return contact.provider if contact else "whatsapp"


def _whatsapp_recipient(db, participant, contact=None):
    """WhatsApp address (phone number) for a participant, from their WhatsApp
    provider contact."""

    if contact is not None and contact.provider == PROVIDER_WHATSAPP:
        return delivery_address(contact)
    return provider_external_id(db, participant, PROVIDER_WHATSAPP)


def send_assignment_prompt(db, participant, prompt):
    contact = active_provider_contact(db, participant)
    if contact and contact.provider == "telegram":
        from telegram import Bot

        from app.providers.telegram.config import telegram_bot_token
        from app.providers.telegram.messaging import send_assignment_prompt as send_telegram_prompt

        bot = Bot(token=telegram_bot_token())
        sent = asyncio.run(send_telegram_prompt(bot, delivery_address(contact), prompt))
        message_id = getattr(sent, "message_id", None)
        if message_id is not None:
            record_assignment_delivery(
                db,
                participant_id=participant.id,
                assignment_id=prompt.assignment_id,
                provider="telegram",
                provider_message_id=message_id,
            )
        return DeliveryResult(provider="telegram")

    from app.providers.whatsapp.messaging import send_assignment_prompt as send_whatsapp_prompt

    response = send_whatsapp_prompt(_whatsapp_recipient(db, participant, contact), prompt)
    return DeliveryResult(
        provider="whatsapp",
        status_code=getattr(response, "status_code", 200),
    )


def send_text_message(db, participant, text):
    """Send a plain text message over the participant's active provider."""

    contact = active_provider_contact(db, participant)
    if contact and contact.provider == "telegram":
        from telegram import Bot

        from app.providers.telegram.config import telegram_bot_token
        from app.providers.telegram.messaging import send_text

        bot = Bot(token=telegram_bot_token())
        asyncio.run(send_text(bot, delivery_address(contact), text))
        return DeliveryResult(provider="telegram")

    from app.providers.whatsapp.messaging import get_text_message_input, send_message

    response = send_message(
        get_text_message_input(_whatsapp_recipient(db, participant, contact), text)
    )
    return DeliveryResult(
        provider="whatsapp",
        status_code=getattr(response, "status_code", 200),
    )


def send_reminder(db, participant, assignment, reminder):
    contact = active_provider_contact(db, participant)
    if contact and contact.provider == "telegram":
        from telegram import Bot

        from app.providers.telegram.config import telegram_bot_token
        from app.providers.telegram.messaging import send_text

        bot = Bot(token=telegram_bot_token())
        asyncio.run(send_text(bot, delivery_address(contact), reminder.message_text))
        return DeliveryResult(provider="telegram")

    from app.providers.whatsapp.reminders import send_reminder as send_whatsapp_reminder

    response = send_whatsapp_reminder(
        participant, assignment, reminder, _whatsapp_recipient(db, participant, contact)
    )
    return DeliveryResult(
        provider="whatsapp",
        status_code=getattr(response, "status_code", 200),
    )
