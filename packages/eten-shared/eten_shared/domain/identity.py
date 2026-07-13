"""Canonical participant identity, resolved through provider contacts.

A ``Participant`` is identified by its own ``id`` (a UUID). Every external
identity — a WhatsApp phone number, a Telegram chat id, an iMessage handle —
is a row in ``participant_provider_contacts`` keyed by ``(provider,
external_user_id)``. There is no per-provider column on ``participants``; all
adapters resolve and create participants through the helpers here, so the
same person can carry several provider contacts under one ``participant_id``.

Replaces the old ``get_or_create_participant(wa_id)`` flow, where WhatsApp
identity lived in a ``participants.wa_id`` column and Telegram used a
synthetic ``telegram:<chat_id>`` value.
"""

from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from eten_shared.models import (
    Assignment,
    OutboxNotification,
    Participant,
    ParticipantBadge,
    ParticipantCurrencyEvent,
    ParticipantEvent,
    ParticipantProviderContact,
    ParticipantResponse,
    ParticipantSession,
    ParticipantWallet,
    Reminder,
    utc_now,
)

PROVIDER_WHATSAPP = "whatsapp"
PROVIDER_TELEGRAM = "telegram"
PROVIDER_IMESSAGE = "imessage"

# Optional contact fields callers may pass through to the contact row.
_CONTACT_FIELDS = (
    "display_name",
    "username",
    "first_name",
    "last_name",
    "phone",
    "locale",
)


def _apply_contact_fields(contact: ParticipantProviderContact, fields: dict) -> None:
    for key, value in (fields or {}).items():
        if key in _CONTACT_FIELDS and value is not None:
            setattr(contact, key, value)


def get_contact(
    db: Session, provider: str, external_user_id
) -> Optional[ParticipantProviderContact]:
    return db.scalars(
        select(ParticipantProviderContact).where(
            ParticipantProviderContact.provider == provider,
            ParticipantProviderContact.external_user_id == str(external_user_id),
        )
    ).first()


def resolve_participant(
    db: Session, provider: str, external_user_id
) -> Optional[Participant]:
    """Return the participant behind a provider identity, or None."""

    contact = get_contact(db, provider, external_user_id)
    return contact.participant if contact else None


def normalize_phone(value) -> str:
    """Digits-only form of a phone number (drops +, spaces, dashes)."""

    return "".join(ch for ch in str(value or "") if ch.isdigit())


def resolve_login(
    db: Session, identifier, provider: Optional[str] = None
) -> Optional[Participant]:
    """Resolve a participant from a login identifier — a WhatsApp phone number
    or a Telegram chat id. Matches the identifier as entered and in a
    digits-normalized form against provider-contact external ids. Optionally
    restricted to one provider. Resolve-only: never creates or merges.
    """

    identifier = str(identifier or "").strip()
    if not identifier:
        return None

    candidates = [identifier]
    normalized = normalize_phone(identifier)
    if normalized and normalized != identifier:
        candidates.append(normalized)

    stmt = select(ParticipantProviderContact).where(
        ParticipantProviderContact.external_user_id.in_(candidates),
        ParticipantProviderContact.opted_out_at.is_(None),
    )
    if provider:
        stmt = stmt.where(ParticipantProviderContact.provider == provider)
    stmt = stmt.order_by(ParticipantProviderContact.updated_at.desc())
    contact = db.scalars(stmt).first()
    return contact.participant if contact else None


def get_or_create_participant_by_contact(
    db: Session,
    provider: str,
    external_user_id,
    *,
    display_name: Optional[str] = None,
    locale: Optional[str] = None,
    opt_in: bool = True,
    **contact_fields,
) -> Tuple[Participant, ParticipantProviderContact, bool]:
    """Resolve (or create) the participant for a provider identity.

    Returns ``(participant, contact, created)``. ``created`` is True when a
    new participant + contact were minted for this identity.
    """

    external_user_id = str(external_user_id)
    now = utc_now()
    contact = get_contact(db, provider, external_user_id)

    if contact is not None:
        participant = contact.participant
        participant.last_seen_at = now
        contact.last_seen_at = now
        if display_name:
            if not participant.display_name:
                participant.display_name = display_name
            contact.display_name = display_name
        if locale:
            contact.locale = locale
            if not participant.locale:
                participant.locale = locale
        _apply_contact_fields(contact, contact_fields)
        if opt_in and contact.opted_in_at is None:
            contact.opted_in_at = now
        contact.opted_out_at = None
        return participant, contact, False

    participant = Participant(
        display_name=display_name,
        locale=locale,
        last_seen_at=now,
    )
    db.add(participant)
    db.flush()

    contact = ParticipantProviderContact(
        participant_id=participant.id,
        provider=provider,
        external_user_id=external_user_id,
        display_name=display_name,
        locale=locale,
        opted_in_at=now if opt_in else None,
        last_seen_at=now,
    )
    _apply_contact_fields(contact, contact_fields)
    db.add(contact)
    db.flush()
    return participant, contact, True


def active_contact(
    db: Session, participant, provider: Optional[str] = None
) -> Optional[ParticipantProviderContact]:
    """Most-recently-updated non-opted-out contact for a participant,
    optionally restricted to one provider."""

    stmt = select(ParticipantProviderContact).where(
        ParticipantProviderContact.participant_id == participant.id,
        ParticipantProviderContact.opted_out_at.is_(None),
    )
    if provider is not None:
        stmt = stmt.where(ParticipantProviderContact.provider == provider)
    stmt = stmt.order_by(ParticipantProviderContact.updated_at.desc())
    return db.scalars(stmt).first()


def provider_external_id(
    db: Session, participant, provider: str
) -> Optional[str]:
    """External id (e.g. WhatsApp phone / Telegram chat id) to address this
    participant on a given provider, or None if they have no such contact."""

    contact = active_contact(db, participant, provider)
    return contact.external_user_id if contact else None


def whatsapp_phone(db: Session, participant) -> Optional[str]:
    return provider_external_id(db, participant, PROVIDER_WHATSAPP)


# Child tables carrying a participant_id FK; used when merging identities.
_CHILD_TABLES = (
    Assignment,
    ParticipantResponse,
    ParticipantEvent,
    Reminder,
    ParticipantBadge,
    ParticipantCurrencyEvent,
    OutboxNotification,
    ParticipantProviderContact,
)

# 1:1 tables — the target keeps its own row; the source's is repointed only
# when the target has none.
_SINGLETON_TABLES = (ParticipantWallet, ParticipantSession)


def link_provider_contact(
    db: Session,
    participant,
    provider: str,
    external_user_id,
    **contact_fields,
) -> ParticipantProviderContact:
    """Attach an additional provider identity to an existing participant.

    If that identity already belongs to a *different* participant, merge that
    participant into ``participant`` (see :func:`merge_participants`). Enables
    one person to share a single ``participant_id`` across WhatsApp, Telegram,
    etc.
    """

    external_user_id = str(external_user_id)
    now = utc_now()
    existing = get_contact(db, provider, external_user_id)
    if existing is not None:
        if existing.participant_id == participant.id:
            _apply_contact_fields(existing, contact_fields)
            existing.last_seen_at = now
            return existing
        merge_participants(db, source=existing.participant, target=participant)
        merged = get_contact(db, provider, external_user_id)
        _apply_contact_fields(merged, contact_fields)
        return merged

    contact = ParticipantProviderContact(
        participant_id=participant.id,
        provider=provider,
        external_user_id=external_user_id,
        opted_in_at=now,
        last_seen_at=now,
    )
    _apply_contact_fields(contact, contact_fields)
    db.add(contact)
    db.flush()
    return contact


def merge_participants(db: Session, *, source: Participant, target: Participant) -> Participant:
    """Fold ``source`` into ``target``: repoint child rows, then delete
    ``source``. Used when two provider identities turn out to be the same
    person. Prefer linking at provisioning time (before either identity has
    activity) so this stays a no-conflict repoint.
    """

    if source.id == target.id:
        return target

    target_singletons = {
        model: db.scalars(
            select(model).where(model.participant_id == target.id)
        ).first()
        for model in _SINGLETON_TABLES
    }

    for model in _CHILD_TABLES:
        db.execute(
            update(model)
            .where(model.participant_id == source.id)
            .values(participant_id=target.id)
        )

    for model in _SINGLETON_TABLES:
        source_row = db.scalars(
            select(model).where(model.participant_id == source.id)
        ).first()
        if source_row is None:
            continue
        if target_singletons.get(model) is None:
            source_row.participant_id = target.id
        else:
            db.delete(source_row)

    db.flush()
    db.delete(source)
    db.flush()
    return target
