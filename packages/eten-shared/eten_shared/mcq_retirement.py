"""Evidence recorded when the Sol MCQ reviewer assesses an exhausted repair."""
import hashlib
import json


REPAIR_STAGES = ("repair", "second_repair", "third_repair", "fourth_repair")


def published_signature(row):
    content = [row["id"], row["passage_id"], row["question"], row["choices"], row["correct"],
               list(row["verses"].items())]
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest()


def validate_final_review(row, review):
    """Reject stale wording, missing passage evidence or inconsistent decisions."""
    stages = review["repair_stages"]
    if (review["id"] != row["id"] or review["published_signature"] != published_signature(row)
            or not stages or stages != list(REPAIR_STAGES[:len(stages)])
            or not review["model"] or not review["version"] or not review["reason"].strip()
            or not review["quote"].strip() or review["quote"] not in row["verses"].get(review["verse"], "")):
        raise ValueError(f"Invalid final MCQ review evidence for {row['id']}")
    verdict = review["verdict"]
    if verdict == "hold":
        return
    if review["repair_possible"] != "no":
        raise ValueError("Retirement requires ruling out a repair preserving the target.")
    if verdict == "unsupported_target" and review["target_support"] == "unsupported" and review["missing_link"].strip():
        return
    if (verdict == "unfair_menu" and review["target_support"] == "supported"
            and review["menu_shortcut"].strip() and review["alternatives_considered"].strip()):
        return
    raise ValueError(f"Unconfirmed MCQ retirement for {row['id']}")
