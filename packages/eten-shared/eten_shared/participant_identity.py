"""Keyed protection for participant platform identifiers.

The study's consent language promises that the research database holds no
readable platform identifier, and that identifiers are destroyed with their key
once collection ends. The bot, however, has to *send* messages, so a one-way
hash alone is not viable: you cannot deliver a Telegram message to a digest.

The resolution is the standard blind-index pattern, two values per contact:

``external_user_id``      HMAC-SHA256(key, "provider:chat_id"), hex.
                          Deterministic, so an inbound message can still be
                          matched to its participant with an equality lookup,
                          but it reveals nothing and cannot be reversed.

``external_user_secret``  AES-GCM(key, chat_id), base64 of nonce||ciphertext.
                          Reversible *only* with the key, which lives in the
                          environment and never in the database. Outbound
                          delivery decrypts this at send time.

Destroying the key therefore destroys both directions at once: the index was
never reversible, and the ciphertext becomes permanently unreadable. That is
what ``scripts/purge_participant_identity.py`` relies on.

Set ``PARTICIPANT_ID_KEY`` to a base64 32-byte value. Generate one with:

    python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

Keep it in the secret store, not in the repository and not in the database. If
it is lost, existing participants can no longer be messaged -- which is the
intended failure mode, not a bug.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENV_KEY = "PARTICIPANT_ID_KEY"
_NONCE_BYTES = 12


class IdentityKeyError(RuntimeError):
    """The identity key is absent or malformed."""


def _key() -> bytes:
    raw = os.getenv(ENV_KEY, "").strip()
    if not raw:
        raise IdentityKeyError(
            f"{ENV_KEY} is not set. Participant identifiers cannot be read or "
            "written without it; refusing to fall back to plaintext."
        )
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except Exception as exc:  # pragma: no cover - malformed env
        raise IdentityKeyError(f"{ENV_KEY} is not valid base64: {exc}") from exc
    if len(key) != 32:
        raise IdentityKeyError(f"{ENV_KEY} must decode to 32 bytes, got {len(key)}")
    return key


def key_fingerprint() -> str:
    """Short, non-reversible tag for the active key.

    Recorded alongside sealed values so an operator can tell which key a row was
    written under -- and therefore whether a purge has actually orphaned it --
    without the key itself appearing anywhere.
    """

    return hashlib.sha256(_key()).hexdigest()[:12]


def blind_index(provider: str, external_user_id: str) -> str:
    """Deterministic, non-reversible lookup handle.

    The provider is part of the input so the same numeric id on two platforms
    does not collide into one participant.
    """

    message = f"{(provider or '').strip().lower()}:{str(external_user_id).strip()}"
    return hmac.new(_key(), message.encode("utf-8"), hashlib.sha256).hexdigest()


def seal(external_user_id: str) -> str:
    """Encrypt a platform id for storage. Random nonce, so never deterministic."""

    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_key()).encrypt(nonce, str(external_user_id).encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def unseal(sealed: str) -> str:
    """Recover a platform id for delivery. Raises if the key no longer matches."""

    if not sealed:
        raise IdentityKeyError("No sealed identifier stored for this contact")
    blob = base64.urlsafe_b64decode(str(sealed) + "=" * (-len(str(sealed)) % 4))
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    try:
        return AESGCM(_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception as exc:
        raise IdentityKeyError(
            "Sealed identifier could not be decrypted with the current "
            f"{ENV_KEY}. If the key was purged this is expected and permanent."
        ) from exc


def generate_key() -> str:
    """A fresh key, for setup. Printed once and stored in the secret manager."""

    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def delivery_address(contact) -> str:
    """The platform id to send to, decrypted at the moment of sending.

    Every outbound path goes through here so there is one audited place where a
    readable identifier exists, and it exists only in memory. Raises rather than
    returning the stored blind index -- sending to a hash would silently fail,
    and falling back to a plaintext column would defeat the scheme.
    """

    sealed = getattr(contact, "external_user_secret", None)
    if not sealed:
        raise IdentityKeyError(
            "Contact has no sealed identifier; it predates identity protection "
            "or was purged. Run scripts/migrate_participant_identity.py."
        )
    return unseal(sealed)
