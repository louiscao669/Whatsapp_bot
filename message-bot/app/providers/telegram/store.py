from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.database import get_session_factory
from eten_shared.domain.assignments import (
    get_or_create_participant_session,
    record_participant_event,
)
from eten_shared.models import (
    Participant,
    ParticipantProviderContact,
    SessionState,
    utc_now,
)

PROVIDER = "telegram"


@dataclass(frozen=True)
class TelegramContactInput:
    chat_id: str
    display_name: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    message_id: str | None = None


def contact_input_from_update(update) -> TelegramContactInput:
    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message
    return TelegramContactInput(
        chat_id=str(chat.id),
        display_name=(user.full_name if user else None),
        username=(user.username if user else None),
        first_name=(user.first_name if user else None),
        last_name=(user.last_name if user else None),
        language_code=(user.language_code if user else None),
        message_id=str(message.message_id) if message else None,
    )


def _compat_wa_id(chat_id: str) -> str:
    return f"telegram:{chat_id}"


def _get_contact(db: Session, chat_id: str) -> ParticipantProviderContact | None:
    return db.scalars(
        select(ParticipantProviderContact).where(
            ParticipantProviderContact.provider == PROVIDER,
            ParticipantProviderContact.external_user_id == chat_id,
        )
    ).first()


def upsert_telegram_contact(contact_input: TelegramContactInput):
    session_factory = get_session_factory()
    now = utc_now()

    with session_factory() as db:
        contact = _get_contact(db, contact_input.chat_id)
        created = False

        if contact is None:
            participant = Participant(
                wa_id=_compat_wa_id(contact_input.chat_id),
                display_name=contact_input.display_name,
                locale=contact_input.language_code,
                last_seen_at=now,
            )
            db.add(participant)
            db.flush()

            contact = ParticipantProviderContact(
                participant_id=participant.id,
                provider=PROVIDER,
                external_user_id=contact_input.chat_id,
                opted_in_at=now,
                last_seen_at=now,
            )
            db.add(contact)
            created = True
        else:
            participant = contact.participant
            participant.last_seen_at = now
            contact.last_seen_at = now

        if contact_input.display_name:
            participant.display_name = contact_input.display_name
            contact.display_name = contact_input.display_name
        if contact_input.language_code:
            participant.locale = contact_input.language_code
            contact.locale = contact_input.language_code

        contact.username = contact_input.username
        contact.first_name = contact_input.first_name
        contact.last_name = contact_input.last_name
        contact.opted_out_at = None
        if contact.opted_in_at is None:
            contact.opted_in_at = now

        participant_session = get_or_create_participant_session(db, participant)
        if participant_session.opted_out_at:
            participant_session.opted_out_at = None
        if participant_session.state == SessionState.OPTED_OUT.value:
            participant_session.state = SessionState.IDLE.value

        record_participant_event(
            db,
            participant,
            "provider_contact_opted_in" if created else "provider_contact_seen",
            {
                "provider": PROVIDER,
                "external_user_id": contact_input.chat_id,
                "username": contact_input.username,
                "message_id": contact_input.message_id,
            },
            source=PROVIDER,
        )
        db.commit()
        return participant, contact, created


def opt_out_telegram_contact(contact_input: TelegramContactInput) -> bool:
    session_factory = get_session_factory()
    now = utc_now()

    with session_factory() as db:
        contact = _get_contact(db, contact_input.chat_id)
        if contact is None:
            return False

        contact.opted_out_at = now
        contact.last_seen_at = now
        participant = contact.participant
        participant.last_seen_at = now
        participant_session = get_or_create_participant_session(db, participant)
        participant_session.opted_out_at = now
        participant_session.state = SessionState.OPTED_OUT.value
        record_participant_event(
            db,
            participant,
            "provider_contact_opted_out",
            {
                "provider": PROVIDER,
                "external_user_id": contact_input.chat_id,
                "message_id": contact_input.message_id,
            },
            source=PROVIDER,
        )
        db.commit()
        return True


def active_telegram_contacts() -> list[ParticipantProviderContact]:
    session_factory = get_session_factory()
    with session_factory() as db:
        return list(
            db.scalars(
                select(ParticipantProviderContact)
                .where(
                    ParticipantProviderContact.provider == PROVIDER,
                    ParticipantProviderContact.opted_out_at.is_(None),
                )
                .order_by(ParticipantProviderContact.created_at)
            ).all()
        )
