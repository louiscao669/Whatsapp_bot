"""Log redaction contract.

These are participant-protection tests, not formatting tests. A failure here
means the running service is writing something into journald that the consent
form says is not kept: a client IP that can single out a household, a
participant id, or a signed deep-link token that is a working credential for
somebody's session.

The two "must survive" cases matter as much as the redactions. A filter that
mangles timestamps or the server's own address would be turned off by the first
operator who had to debug an outage, and then nothing is redacted at all.
"""

import io
import logging

from eten_shared.log_redaction import (
    ID_PLACEHOLDER,
    TOKEN_PLACEHOLDER,
    install_log_redaction,
    redact,
)

ACCESS_LINE = (
    '66.254.228.64 - - [07/Sep/2026 18:29:37] '
    '"GET /pilot/api/38a46be5-43e2-4e79-8830-f5858b3dd28b/question HTTP/1.1" 500 -'
)


def test_access_line_loses_the_last_octet_and_the_participant_id():
    line = redact(ACCESS_LINE)
    assert "66.254.228.0" in line
    assert "66.254.228.64" not in line
    assert "38a46be5-43e2-4e79-8830-f5858b3dd28b" not in line
    assert ID_PLACEHOLDER in line
    # Still a usable access log: method, path shape and status survive.
    assert '"GET /pilot/api/' in line and "500" in line


def test_deep_link_token_is_removed_in_both_path_shapes():
    token = "LTEwNTc2YTAxY2VkMiJ9.ap8CMg.CWjUKkl6xAHf1SBIw3MnB605rjo"
    assert token not in redact(f'"GET /pilot/t/{token} HTTP/1.1" 200 -')
    assert TOKEN_PLACEHOLDER in redact(f'"GET /pilot/t/{token} HTTP/1.1" 200 -')
    # A token pasted into the plain participant path -- observed in production
    # on 2026-09-07 -- has no distinguishing shape, so the position is what
    # must be redacted, not the pattern.
    assert token not in redact(f'"GET /pilot/{token} HTTP/1.1" 200 -')


def test_participant_id_is_redacted_outside_the_access_log_too():
    # The traceback header leaks the same id the access line does.
    line = redact(
        "Exception on /pilot/api/92221d77-5d9d-42fe-b400-10576a01ced2/question [GET]"
    )
    assert "92221d77-5d9d-42fe-b400-10576a01ced2" not in line


def test_route_words_in_the_id_position_are_left_alone():
    for path in (
        "/pilot/static/frontend/app.js?v=20260830a",
        "/pilot/api/results",
        "/user-dashboard/api/login",
    ):
        assert redact(f'"GET {path} HTTP/1.1" 200 -').count(ID_PLACEHOLDER) == 0


def test_global_ipv6_is_truncated_to_a_48():
    assert "2606:4700:4700::" in redact("client 2606:4700:4700::1111 connected")
    assert "::1111" not in redact("client 2606:4700:4700::1111 connected")


def test_operator_facing_values_survive():
    # Timestamps contain colons but are not addresses.
    assert redact("timestamps 18:29:37 and 07/Sep/2026") == (
        "timestamps 18:29:37 and 07/Sep/2026"
    )
    # The server's own addresses identify the server, not a participant.
    assert redact("Running on http://10.128.0.52:7860") == (
        "Running on http://10.128.0.52:7860"
    )
    assert redact("loopback ::1 and 127.0.0.1") == "loopback ::1 and 127.0.0.1"


def test_filter_redacts_through_a_handler_and_never_drops_a_record():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("test_log_redaction")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    assert install_log_redaction(logger) == 1
    assert install_log_redaction(logger) == 0  # idempotent

    # A literal % in the message would raise if args were left in place after
    # the message was interpolated by the filter.
    logger.info("%s GET /pilot/%s 100%%", "66.254.228.64", "38a46be5-1111-2222-3333-444455556666")
    logger.info("a line with no identifiers at all")

    written = stream.getvalue()
    assert "66.254.228.0" in written
    assert "66.254.228.64" not in written
    assert ID_PLACEHOLDER in written
    assert "100%" in written
    assert "a line with no identifiers at all" in written
    assert len(written.strip().splitlines()) == 2
