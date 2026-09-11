"""Dashboard store services."""

from ._common import *  # noqa: F401,F403

def _get_or_create_wallet(db, participant):
    wallet = db.scalars(
        select(ParticipantWallet).where(
            ParticipantWallet.participant_id == participant.id
        )
    ).first()
    if wallet:
        return wallet

    wallet = ParticipantWallet(participant_id=participant.id)
    db.add(wallet)
    db.flush()
    return wallet


def _store_purchase_events(db, participant_id):
    return db.scalars(
        select(ParticipantCurrencyEvent).where(
            ParticipantCurrencyEvent.participant_id == participant_id,
            ParticipantCurrencyEvent.reason == "store_purchase",
        )
    ).all()


def get_store_inventory(db, participant_id):
    inventory = {
        item_id: {
            "owned": 0,
            "max_owned": item["max_owned"],
        }
        for item_id, item in STORE_ITEMS.items()
    }
    for event in _store_purchase_events(db, participant_id):
        metadata = event.currency_metadata or {}
        item_id = metadata.get("item_id")
        if item_id in inventory:
            inventory[item_id]["owned"] += 1
    participant = db.get(Participant, participant_id)
    if participant:
        inventory[STREAK_FREEZE_ITEM_ID]["owned"] = get_freeze_token_balance(
            db,
            participant,
        )["available"]
    return inventory


def get_store_payload(db, participant):
    inventory = get_store_inventory(db, participant.id)
    items = sorted(STORE_ITEMS.values(), key=lambda item: (item["cost"], item["title"]))
    return {
        "items": items,
        "inventory": inventory,
    }


def get_equipped_cosmetics(participant):
    preferences = participant.dashboard_preferences or {}
    return {
        "profile_frame": preferences.get("profile_frame"),
        "dashboard_background": preferences.get("dashboard_background"),
    }


def set_cosmetic_equipped(db, participant_id: str, item_id: str, equipped: bool):
    from .profile import _participant_by_id
    from .payload import get_user_dashboard_payload

    item = STORE_ITEMS.get((item_id or "").strip())
    if not item:
        raise CosmeticUpdateError("Store item not found")
    if item["item_type"] != "cosmetic":
        raise CosmeticUpdateError("Only cosmetic items can be equipped")
    slot = COSMETIC_SLOTS.get(item["item_id"])
    if not slot:
        raise CosmeticUpdateError("Cosmetic slot not found")

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise CosmeticUpdateError("Participant not found")

    inventory = get_store_inventory(db, participant.id)
    owned = inventory.get(item["item_id"], {}).get("owned", 0)
    if owned <= 0:
        raise CosmeticUpdateError("Buy this cosmetic before equipping it")

    preferences = dict(participant.dashboard_preferences or {})
    if equipped:
        preferences[slot] = item["item_id"]
    elif preferences.get(slot) == item["item_id"]:
        preferences.pop(slot, None)

    participant.dashboard_preferences = preferences
    participant.updated_at = datetime.now(timezone.utc)
    db.add(
        ParticipantEvent(
            participant_id=participant.id,
            event_type="cosmetic_updated",
            source="user_dashboard",
            event_metadata={
                "item_id": item["item_id"],
                "slot": slot,
                "equipped": bool(equipped),
            },
        )
    )
    db.flush()
    return get_user_dashboard_payload(db, participant_id)


def purchase_store_item(db, participant_id: str, item_id: str):
    from .profile import _participant_by_id
    from .payload import get_user_dashboard_payload

    item = STORE_ITEMS.get((item_id or "").strip())
    if not item:
        raise StorePurchaseError("Store item not found")

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise StorePurchaseError("Participant not found")

    wallet = db.scalar(
        select(ParticipantWallet).where(ParticipantWallet.participant_id == participant.id)
    )
    inventory = get_store_inventory(db, participant.id)
    owned = inventory.get(item["item_id"], {}).get("owned", 0)
    if owned >= item["max_owned"]:
        raise StorePurchaseError("Item limit reached")
    if wallet.balance < item["cost"]:
        raise StorePurchaseError("Not enough diamonds")

    wallet.balance -= item["cost"]
    wallet.lifetime_spent += item["cost"]
    wallet.updated_at = datetime.now(timezone.utc)

    event = ParticipantCurrencyEvent(
        participant_id=participant.id,
        wallet_id=wallet.id,
        amount=-item["cost"],
        balance_after=wallet.balance,
        reason="store_purchase",
        source="user_dashboard",
        currency_metadata={
            "item_id": item["item_id"],
            "title": item["title"],
            "item_type": item["item_type"],
        },
    )
    db.add(event)
    db.flush()
    return get_user_dashboard_payload(db, participant_id)


