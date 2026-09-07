"""Strip participant-identifying detail out of log records before they are written.

Why this exists
---------------
The consent form tells participants that the only thing identifying them is
stored as a keyed hash, held separately from their answers and destroyed when
data collection ends. Application logs were quietly outside that promise: the
WSGI access log writes one line per request containing the client IP address
next to the request path, and every ``/pilot/`` path carries the participant id
-- which is not merely an identifier but the participant's *only credential*.
Those lines land in journald, which no export or deletion script touches.

Two things are redacted, at the logging layer, so no call site has to remember:

``IP addresses``
    Truncated, never hashed or dropped: IPv4 keeps the first three octets
    (``66.254.228.64`` -> ``66.254.228.0``) and IPv6 keeps the first three
    groups (a /48). That is enough to debug a routing or firewall problem and
    not enough to single out a household. Truncation is deliberate over
    removal, because an operator who cannot tell two clients apart at all
    cannot diagnose the study platform.

``Participant ids and deep-link tokens``
    Replaced with a fixed placeholder. A signed deep-link token is a bearer
    credential; anyone holding a logged one can open that participant's
    session, so it must never be at rest in a log file.

Redaction happens on the ``LogRecord`` itself, attached to the root handlers,
so it covers the access log, application logs and exception messages alike --
including tracebacks whose ``Exception on /pilot/api/<id>/question`` header
would otherwise leak the same id the access log does.

This module deliberately imports nothing outside the standard library so it can
be exercised without the application's dependency tree.
"""

import ipaddress
import logging
import re

#: What a redacted identifier looks like in the log. Kept short and distinctive
#: so it is greppable, and so a reader can tell redaction from a missing value.
ID_PLACEHOLDER = "<participant-id>"
TOKEN_PLACEHOLDER = "<deep-link-token>"

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

#: Every participant-facing path shape, in one pass: ``/pilot/<id>``,
#: ``/pilot/api/<id>/...``, ``/pilot/t/<token>`` and the dashboard's
#: equivalents. Positional rather than pattern-based on the id itself, because
#: the id is not always a UUID -- it has already been a phone number and is now
#: a hashed key -- and because a deep-link token pasted into the plain
#: ``/pilot/<...>`` path (which is exactly what happened on 2026-09-07) has no
#: distinguishing shape at all. Matched before the IP and UUID passes, since a
#: token's payload can contain either shape.
_PARTICIPANT_PATH_RE = re.compile(
    r"(?P<prefix>/(?:pilot|user_dashboard|user-dashboard))"
    r"(?P<api>/api)?/(?P<token>t/)?(?P<id>[A-Za-z0-9_\-.=]+)"
)

#: Route words that sit in the id's position but are not ids.
_PATH_KEYWORDS = frozenset({"api", "static", "t", "login", "logout", "results"})

_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")

#: Only a candidate with a ``::`` or a full eight groups is considered, which
#: is what keeps this off log timestamps -- ``18:29:37`` has colons but is
#: neither, and would otherwise be mangled into something unreadable. Every
#: candidate is still validated by :mod:`ipaddress` before it is touched.
_IPV6_RE = re.compile(
    r"(?=[0-9A-Fa-f:]*::|(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4})"
    r"[0-9A-Fa-f:]{3,45}"
)


def _redact_path(match):
    identifier = match.group("id")
    if identifier.lower() in _PATH_KEYWORDS:
        return match.group(0)
    placeholder = TOKEN_PLACEHOLDER if match.group("token") else ID_PLACEHOLDER
    return (
        match.group("prefix")
        + (match.group("api") or "")
        + "/"
        + (match.group("token") or "")
        + placeholder
    )


def _mask_ipv4(match):
    text = match.group(0)
    try:
        address = ipaddress.IPv4Address(text)
    except ValueError:
        return text
    if not address.is_global:
        # Loopback, the VM's own 10.x, link-local: these identify the server,
        # not a participant, and masking them only makes an operator's own
        # startup banner and health checks harder to read.
        return text
    octets = str(address).split(".")
    return ".".join(octets[:3] + ["0"])


def _mask_ipv6(match):
    text = match.group(0)
    try:
        address = ipaddress.IPv6Address(text)
    except ValueError:
        return text
    if not address.is_global:
        return text
    groups = address.exploded.split(":")
    return ":".join(groups[:3]) + "::"


def redact(message):
    """Return ``message`` with IPs truncated and participant ids removed.

    Pure and total: anything that does not parse as an address or an id is
    returned untouched, so a malformed log line is never made less readable
    than it already was.
    """

    if not message:
        return message
    text = _PARTICIPANT_PATH_RE.sub(_redact_path, message)
    text = _IPV6_RE.sub(_mask_ipv6, text)
    text = _IPV4_RE.sub(_mask_ipv4, text)
    text = _UUID_RE.sub(ID_PLACEHOLDER, text)
    return text


class RedactingFilter(logging.Filter):
    """Rewrite a record's message in place. Never drops a record.

    A filter that returned False would silently lose log lines, which is a
    worse failure than an unredacted one: an operator would have no way to
    tell that anything was missing. This one only ever edits.
    """

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - a broken record is still a record
            return True
        redacted = redact(message)
        if redacted != message:
            # The message is now fully interpolated, so the args must go with
            # it -- leaving them would re-run %-formatting over redacted text
            # and raise on any literal % the message happens to contain.
            record.msg = redacted
            record.args = ()
        return True


def install_log_redaction(logger=None):
    """Attach the filter to every handler on ``logger`` (root by default).

    Handlers, not loggers: a filter on a logger sees only records logged
    directly to it, while a filter on the root's handlers sees everything that
    propagates there -- werkzeug's access log included. Idempotent, so calling
    it again after adding a handler is safe and is the intended way to cover
    handlers installed later.
    """

    target = logger if logger is not None else logging.getLogger()
    installed = 0
    for handler in target.handlers:
        if any(isinstance(existing, RedactingFilter) for existing in handler.filters):
            continue
        handler.addFilter(RedactingFilter())
        installed += 1
    return installed
