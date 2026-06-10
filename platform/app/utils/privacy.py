import hashlib


def normalize_wa_id_for_hash(wa_id: str) -> str:
    value = (wa_id or "").strip()
    if not value:
        return ""
    digits = "".join(character for character in value if character.isdigit())
    return digits if digits else value


def hash_wa_id_for_display(wa_id: str) -> str:
    normalized = normalize_wa_id_for_hash(wa_id)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
