# Log retention on the study VM

The application no longer writes client IP addresses, participant ids or
deep-link tokens into its logs (`eten_shared/log_redaction.py`, installed by
`configure_logging()` in both services). This directory covers the other half:
how long what is left is kept, and clearing the logs written *before* redaction
existed.

Why it matters: journald is outside every data-handling path the protocol
describes. `human_pilot/export_pilot_metrics.py` does not read it, the
identifier-destruction step does not touch it, and nothing rotates it by
default on this image. Un-redacted request logs going back to first boot would
therefore outlive the study.

## 1. Install the retention policy

```bash
sudo mkdir -p /etc/systemd/journald.conf.d
sudo cp deploy/journald/10-eten-retention.conf /etc/systemd/journald.conf.d/
sudo systemctl restart systemd-journald
```

Verify:

```bash
journalctl --disk-usage
systemd-analyze cat-config systemd/journald.conf | grep -A5 '\[Journal\]'
```

## 2. Purge the pre-redaction logs, once

Everything logged before the redaction filter shipped still contains real IPs
and participant ids. Rotate the active file first, or the current one is
skipped:

```bash
sudo journalctl --rotate
sudo journalctl --vacuum-time=1s
```

Confirm nothing identifying is left:

```bash
sudo journalctl -u eten-platform --since "1 hour ago" | grep -E '/pilot/[0-9a-f]{8}-' || echo "clean"
```

`--vacuum-time` is global, not per-unit — it drops old entries for every unit on
the box. That is the intent here; if you need another unit's history, export it
first.

## 3. Deploy the app-side change

Redaction is applied when the service starts, so it takes effect only after a
restart:

```bash
cd /opt/eten-whatsapp-bot && git pull origin main
sudo systemctl restart eten-platform eten-telegram-bot
```

Then confirm a real request is redacted end to end:

```bash
curl -s "http://127.0.0.1:7860/pilot/api/<participant-id>/consent" > /dev/null
sudo journalctl -u eten-platform -n 5 --no-pager
```

The access line should read `127.0.0.1 ... "GET /pilot/api/<participant-id>/consent"`
with the literal placeholder, not the id.

## What this does not fix

The service still runs on the Flask development server, which is what writes
these access lines. Moving to gunicorn behind nginx with TLS is the real fix for
a study that recruits outside participants; redaction is what keeps the current
setup honest until then. If nginx is added, its own `access_log` needs the same
treatment — nginx logs the full request line and the client IP by default, and
it will not inherit any of this.
