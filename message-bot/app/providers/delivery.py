from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from eten_shared.models import ParticipantProviderContact


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


def send_assignment_prompt(db, participant, prompt):
    contact = active_provider_contact(db, participant)
    if contact and contact.provider == "telegram":
        from telegram import Bot

        from app.providers.telegram.config import telegram_bot_token
        from app.providers.telegram.messaging import send_assignment_prompt as send_telegram_prompt

        bot = Bot(token=telegram_bot_token())
        asyncio.run(send_telegram_prompt(bot, contact.external_user_id, prompt))
        return DeliveryResult(provider="telegram")

    from app.providers.whatsapp.messaging import send_assignment_prompt as send_whatsapp_prompt

    response = send_whatsapp_prompt(participant.wa_id, prompt)
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
        asyncio.run(send_text(bot, contact.external_user_id, reminder.message_text))
        return DeliveryResult(provider="telegram")

    from app.providers.whatsapp.reminders import send_reminder as send_whatsapp_reminder

    response = send_whatsapp_reminder(participant, assignment, reminder)
    return DeliveryResult(
        provider="whatsapp",
        status_code=getattr(response, "status_code", 200),
    )
