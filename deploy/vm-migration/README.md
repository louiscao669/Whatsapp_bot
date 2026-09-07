# Migrating the study VM to the database's region

Why: on 2026-09-07 a `SELECT 1` from the `us-central1` VM to the Supabase
project in AWS `us-east-2` measured **27ms**. Every endpoint pays that per
query — `GET /question` issues ~40 of them while minting an assignment, which
is the 1.1s participants wait after each submit. Same-region should be 1–3ms,
turning a ~2s submit into ~0.2s. No code change achieves anything close.

This is a rebuild-from-git migration (Route B). The alternative — cloning the
disk with `gcloud compute machine-images` — carries everything across in two
commands and is the faster path if you do not want a documented rebuild.

## Set these once, in every shell you use

```bash
OLD_VM=translation-project
OLD_ZONE=us-central1-a
NEW_VM=<the instance you created>
NEW_ZONE=us-east5-a          # GCP Columbus, same city as AWS us-east-2
```

## 1. Take what is NOT in git, first

Two things live only on the old box, and losing either is painful:

```bash
# From your Mac.
gcloud compute scp $OLD_VM:/opt/eten-whatsapp-bot/.env ./env-backup --zone $OLD_ZONE
gcloud compute ssh $OLD_VM --zone $OLD_ZONE \
  --command 'systemctl cat eten-platform eten-telegram-bot' > units-backup.txt
```

`.env` holds `DATABASE_URL`, the Supabase keys, and `DASHBOARD_LINK_SECRET`.
**Do not regenerate that secret** — every signed deep link already issued
verifies against it, and a new one silently invalidates all of them.

The unit files in `/etc/systemd/system/` are not in the repo either. Read
`units-backup.txt` before writing new ones; it is the record of how the
services were actually configured.

## 2. Build the new box

```bash
gcloud compute ssh $NEW_VM --zone $NEW_ZONE
```

Then, on the new VM:

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip

sudo mkdir -p /opt/eten-whatsapp-bot
sudo chown $USER:$USER /opt/eten-whatsapp-bot
git clone <your GitHub remote> /opt/eten-whatsapp-bot

cd /opt/eten-whatsapp-bot
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r platform/requirements.txt
.venv/bin/pip install -r message-bot/requirements.txt
```

If the repo is private and the clone prompts for credentials, the old VM
already has working access — check `git remote -v` and `~/.git-credentials`
there rather than inventing a new auth method.

`psycopg[binary]` ships wheels, so no compiler or `libpq-dev` is needed.

## 3. Put `.env` in place, with the new base URL

```bash
# From your Mac.
gcloud compute scp ./env-backup $NEW_VM:/opt/eten-whatsapp-bot/.env --zone $NEW_ZONE
```

Then on the new VM, edit one line — `DASHBOARD_PUBLIC_BASE_URL` still points at
the old VM's IP, so links minted after the cutover would send participants to a
box that is about to be turned off:

```bash
nano /opt/eten-whatsapp-bot/.env
# DASHBOARD_PUBLIC_BASE_URL=http://<new external IP>:7860
```

While you are in there, delete the duplicate `REQUIRE_QUESTION_AUDIO=false`
line — it appears twice, which is harmless until the day the two disagree.

## 4. Prove the move was worth it, BEFORE cutting over

```bash
cd /opt/eten-whatsapp-bot && .venv/bin/python - <<'PY'
import time
from dotenv import load_dotenv
load_dotenv("/opt/eten-whatsapp-bot/.env")
from sqlalchemy import text
from eten_shared.database import get_session_factory
s = get_session_factory()()
s.execute(text("select 1"))
for _ in range(5):
    t = time.perf_counter(); s.execute(text("select 1"))
    print(round((time.perf_counter()-t)*1000, 1), "ms")
PY
```

**Expect 1–3ms.** If it still reports ~27ms, stop: the instance is not in the
region you think it is (`curl -s -H "Metadata-Flavor: Google"
http://metadata.google.internal/computeMetadata/v1/instance/zone`), and
continuing would mean doing this twice.

## 5. Services

```bash
# Copy the unit files from units-backup.txt, then:
sudo mkdir -p /etc/systemd/system/eten-platform.service.d
sudo cp /opt/eten-whatsapp-bot/deploy/gunicorn/override.conf \
        /etc/systemd/system/eten-platform.service.d/
sudo mkdir -p /etc/systemd/journald.conf.d
sudo cp /opt/eten-whatsapp-bot/deploy/journald/10-eten-retention.conf \
        /etc/systemd/journald.conf.d/
sudo systemctl restart systemd-journald
sudo systemctl daemon-reload

test -x /opt/eten-whatsapp-bot/.venv/bin/gunicorn || echo "STOP: gunicorn missing"
sudo systemctl enable --now eten-platform
```

Do **not** start `eten-telegram-bot` yet. See the cutover below.

## 6. Firewall

The existing rule targets a network tag, so an untagged instance has port 7860
closed no matter what is running:

```bash
gcloud compute instances add-tags $NEW_VM --tags=eten-platform --zone $NEW_ZONE
```

Verify from your Mac: `curl -sI http://<new IP>:7860/pilot/ | head -1`

## 7. Cutover — order matters

**Stop the Telegram bot on the old VM before starting it on the new one.** Two
pollers on one bot token fight over the same update stream: Telegram returns
409 conflicts, and participants get duplicate or dropped messages. This is the
only step in the migration that can corrupt a live study session.

```bash
gcloud compute ssh $OLD_VM --zone $OLD_ZONE --command 'sudo systemctl stop eten-telegram-bot eten-platform'
gcloud compute ssh $NEW_VM --zone $NEW_ZONE --command 'sudo systemctl enable --now eten-telegram-bot'
```

## 8. Verify, then leave the old box alone for a week

Open `http://<new IP>:7860/pilot/<participant-id>`, answer a question, and read
the durations in the access log:

```bash
sudo journalctl -u eten-platform --since "5 minutes ago" --no-pager | grep '"POST\|"GET' | tail
```

`GET /question` after a submit should be **~120ms**, down from 1123ms.

Then:

```bash
gcloud compute instances stop $OLD_VM --zone $OLD_ZONE
```

Stopped, not deleted. It costs almost nothing and it is the rollback. Delete it
after a week of the new box behaving.

## Still outstanding after this

Plain HTTP on a bare IP: participants still see "Not secure" beside the consent
form, and the app is exposed directly to the internet on 7860. Fixing that
needs a hostname (Let's Encrypt will not certify an IP) plus nginx in front of
gunicorn. When that happens, set `PLATFORM_BIND=127.0.0.1:7860` so the app is
reachable only through the proxy, and give nginx's `access_log` the same
IP/participant-id redaction as `deploy/journald/` — it does not inherit the
application's.
