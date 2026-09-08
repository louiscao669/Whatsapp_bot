"""Who may sign in to the admin platform.

This is an access-control contract, not a parsing exercise. The platform sits
on a public IP with the study's participant data behind it, so the two things
worth pinning down are: an address that is not on the list gets no login code
mailed to it at all, and role comes from the list rather than from whatever
happens to be in the database.
"""

import pytest

from app.services import admin_auth_service as auth
from app.services.admin_auth_service import (
    AdminAuthError,
    email_is_allowed,
    get_allowed_emails,
    get_allowlisted_role,
    send_admin_login_otp,
)


@pytest.fixture(autouse=True)
def _clear_allowlist(monkeypatch):
    monkeypatch.delenv("ADMIN_ALLOWED_EMAILS", raising=False)


def test_bare_addresses_default_to_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_ALLOWED_EMAILS", "Lcao4@ND.edu, second@nd.edu")
    assert get_allowed_emails() == {"lcao4@nd.edu": "admin", "second@nd.edu": "admin"}


def test_role_suffix_is_honoured(monkeypatch):
    monkeypatch.setenv("ADMIN_ALLOWED_EMAILS", "lead@nd.edu:admin,helper@nd.edu:expert")
    assert get_allowlisted_role("helper@nd.edu") == "expert"
    assert get_allowlisted_role("HELPER@nd.edu ") == "expert"


def test_unknown_role_raises_instead_of_downgrading(monkeypatch):
    # A typo like ":admn" must not quietly become an expert, or worse, an admin.
    monkeypatch.setenv("ADMIN_ALLOWED_EMAILS", "someone@nd.edu:admn")
    with pytest.raises(AdminAuthError):
        get_allowed_emails()


def test_empty_allowlist_leaves_the_database_as_the_gate(monkeypatch):
    monkeypatch.setenv("ADMIN_ALLOWED_EMAILS", "   ")
    assert get_allowed_emails() == {}
    # email_is_allowed only decides whether to MAIL a code; admin_users still
    # decides whether the verified address gets a session.
    assert email_is_allowed("anyone@example.com") is True


def test_unlisted_address_is_refused_before_any_mail_is_sent(monkeypatch):
    monkeypatch.setenv("ADMIN_ALLOWED_EMAILS", "lcao4@nd.edu")
    monkeypatch.setenv("ADMIN_AUTH_PROVIDER", "smtp")

    def _explode(*args, **kwargs):
        raise AssertionError("an OTP was generated for an unlisted address")

    monkeypatch.setattr(auth, "send_smtp_login_otp", _explode)
    monkeypatch.setattr(auth, "send_supabase_login_otp", _explode)

    with pytest.raises(AdminAuthError):
        send_admin_login_otp("stranger@example.com")


def test_listed_address_still_reaches_the_sender(monkeypatch):
    monkeypatch.setenv("ADMIN_ALLOWED_EMAILS", "lcao4@nd.edu")
    monkeypatch.setenv("ADMIN_AUTH_PROVIDER", "smtp")

    sent = []
    monkeypatch.setattr(auth, "send_smtp_login_otp", lambda email: sent.append(email) or email)

    assert send_admin_login_otp("  LCAO4@nd.edu ") == "lcao4@nd.edu"
    assert sent == ["lcao4@nd.edu"]
