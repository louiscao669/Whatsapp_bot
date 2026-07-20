import subprocess
import csv
import time
import random
import logging

logging.basicConfig(
    filename="send_log.csv",
    level=logging.INFO,
    format="%(asctime)s,%(message)s",
)

def send_imessage(recipient: str, message: str) -> bool:
    """Send one iMessage via AppleScript. Returns True on success."""
    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        set targetBuddy to buddy "{recipient}" of targetService
        send "{message}" to targetBuddy
    end tell
    '''
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        logging.info(f"{recipient},SUCCESS")
        return True
    except subprocess.CalledProcessError as e:
        logging.info(f"{recipient},FAILED,{e.stderr.strip()}")
        return False


def run_campaign(csv_path: str, min_delay=8, max_delay=20):
    """CSV columns expected: phone_or_email, name"""
    with open(csv_path, newline="", encoding="utf-8") as f:
        participants = list(csv.DictReader(f))

    for i, p in enumerate(participants, 1):
        recipient = p["phone_or_email"].strip()
        message = (
            f"Hi {p['name']}, this is a message from the Notre Dame SaNDwich Lab Bible translation research team. "
            f"..."
        )
        ok = send_imessage(recipient, message)
        print(f"[{i}/{len(participants)}] {recipient}: {'sent' if ok else 'FAILED'}")

        # Randomized delay to avoid spam flags — skip after the last one
        if i < len(participants):
            time.sleep(random.uniform(min_delay, max_delay))


if __name__ == "__main__":
    run_campaign("participants.csv")