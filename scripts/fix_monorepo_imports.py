#!/usr/bin/env python3
"""One-off import rewriter for monorepo split."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SHARED_REPLACEMENTS = [
    ("from eten_shared.models", "from eten_shared.models"),
    ("from eten_shared.database", "from eten_shared.database"),
    ("from eten_shared.repo_paths", "from eten_shared.repo_paths"),
    ("from eten_shared.media_storage", "from eten_shared.media_storage"),
    ("from eten_shared.mcq", "from eten_shared.mcq"),
    ("from eten_shared.keyword_matching", "from eten_shared.keyword_matching"),
    ("from eten_shared.qa_keywords", "from eten_shared.qa_keywords"),
    ("from eten_shared.transcription", "from eten_shared.transcription"),
    ("from eten_shared.recordings", "from eten_shared.recordings"),
    (
        "from eten_shared.domain.qa_eligibility import qa_item_is_assignable",
        "from eten_shared.domain.qa_eligibility import qa_item_is_assignable",
    ),
    (
        "from eten_shared.domain.qa_eligibility import qa_item_is_recordable",
        "from eten_shared.domain.qa_eligibility import qa_item_is_recordable",
    ),
    (
        "from eten_shared.domain.chapter_labels import chapter_label_from_reference",
        "from eten_shared.domain.chapter_labels import chapter_label_from_reference",
    ),
    (
        "from eten_shared.languages import LanguageError as QAImportError, normalize_language_code",
        "from eten_shared.languages import LanguageError as QAImportError, normalize_language_code",
    ),
    (
        "from eten_shared.languages import normalize_language_code",
        "from eten_shared.languages import normalize_language_code",
    ),
    (
        "from eten_shared.languages import LanguageError as QAImportError",
        "from eten_shared.languages import LanguageError as QAImportError",
    ),
]

BOT_REPLACEMENTS = [
    ("from app.services.workflow", "from app.services.workflow"),
    ("from app.services.reminders", "from app.services.reminders"),
    ("from app.services.batch_continuation", "from app.services.batch_continuation"),
    ("from app.services.badges", "from app.services.badges"),
    ("from app.webhook.messaging", "from app.webhook.messaging"),
    ("from app.webhook.messaging", "from app.webhook.messaging"),
    ("from app.webhook.routes import", "from app.webhook.routes import"),
    ("from app.decorators.security", "from app.decorators.security"),
]

PLATFORM_REPLACEMENTS = [
    ("from app.spa_views", "from app.spa_views"),
    ("from app.admin_nav", "from app.admin_nav"),
    ("from app.utils.admin_formatters", "from app.utils.admin_formatters"),
    ("from app.utils.media_urls", "from app.utils.media_urls"),
    ("from app.services.workflow import AssignmentAssignError", "from app.services.workflow_bridge import AssignmentAssignError"),
    (
        "from app.services.workflow import (\n    AssignmentAssignError,\n    assign_qa_item_to_participant,\n    get_or_create_participant_session,\n)",
        "from app.services.workflow_bridge import (\n    AssignmentAssignError,\n    assign_qa_item_to_participant,\n    get_or_create_participant_session,\n)",
    ),
]


def rewrite_tree(root: Path, extra_replacements: list[tuple[str, str]]):
    replacements = SHARED_REPLACEMENTS + extra_replacements
    for path in root.rglob("*.py"):
        text = path.read_text()
        original = text
        for old, new in replacements:
            text = text.replace(old, new)
        if text != original:
            path.write_text(text)
            print(f"updated {path.relative_to(REPO)}")


def fix_qa_review_service():
    path = REPO / "platform/app/services/qa_review_service.py"
    text = path.read_text()
    text = text.replace(
        "def qa_item_is_removed(qa_item: QAItem) -> bool:\n    return qa_item.review_removed_at is not None\n\n\n"
        "def qa_item_is_reviewed(qa_item: QAItem) -> bool:\n    return qa_item.qa_reviewed_at is not None\n\n\n"
        "def qa_item_is_assignable(qa_item: QAItem) -> bool:\n    return bool(qa_item.active) and not qa_item_is_removed(qa_item)\n\n\n"
        "def qa_item_is_recordable(qa_item: QAItem) -> bool:\n    \"\"\"Eligible for /record after QA text review.\"\"\"\n    return qa_item_is_reviewed(qa_item) and not qa_item_is_removed(qa_item)\n\n\n",
        "",
    )
    if "from eten_shared.domain.qa_eligibility import" not in text:
        text = text.replace(
            "from eten_shared.models import QAItem, utc_now\n",
            "from eten_shared.models import QAItem, utc_now\n"
            "from eten_shared.domain.qa_eligibility import (\n"
            "    qa_item_is_assignable,\n"
            "    qa_item_is_recordable,\n"
            "    qa_item_is_removed,\n"
            "    qa_item_is_reviewed,\n"
            ")\n",
        )
    path.write_text(text)
    print("updated platform/app/services/qa_review_service.py")


def fix_recordings():
    path = REPO / "packages/eten-shared/eten_shared/recordings.py"
    text = path.read_text()
    text = text.replace(
        "from eten_shared.languages import LanguageError as QAImportError, normalize_language_code",
        "from eten_shared.languages import LanguageError as QAImportError, normalize_language_code",
    )
    path.write_text(text)


def fix_mcq():
    path = REPO / "packages/eten-shared/eten_shared/mcq.py"
    text = path.read_text()
    text = text.replace(
        "from eten_shared.keyword_matching import normalize_response_text",
        "from eten_shared.keyword_matching import normalize_response_text",
    )
    path.write_text(text)


def fix_transcription():
    path = REPO / "packages/eten-shared/eten_shared/transcription.py"
    text = path.read_text()
    text = text.replace(
        "from eten_shared.media_storage import download_storage_object, parse_storage_uri",
        "from eten_shared.media_storage import download_storage_object, parse_storage_uri",
    )
    path.write_text(text)


def fix_qa_keywords():
    path = REPO / "packages/eten-shared/eten_shared/qa_keywords.py"
    text = path.read_text()
    text = text.replace("from eten_shared.models", "from eten_shared.models")
    text = text.replace(
        "from app.services.uw_qa_import_service import",
        "from app.services.uw_qa_import_service import",  # platform-only import stays in platform copy
    )
    # uw helpers duplicated minimally in shared for keyword_spec etc - qa_keywords imports from uw
    # Move keyword helpers to shared or inline - read qa_keywords imports
    path.write_text(text)


if __name__ == "__main__":
    rewrite_tree(REPO / "packages/eten-shared/eten_shared", [])
    rewrite_tree(REPO / "whatsapp-bot", BOT_REPLACEMENTS)
    rewrite_tree(REPO / "platform", PLATFORM_REPLACEMENTS)
    rewrite_tree(REPO / "scripts", BOT_REPLACEMENTS + PLATFORM_REPLACEMENTS)
    fix_mcq()
    fix_transcription()
    fix_recordings()
    fix_qa_review_service()
