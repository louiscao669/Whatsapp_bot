"""Backward-compatible helpers for test scripts."""

from pathlib import Path

from app.services.uw_qa_import_service import (
    parse_entries_from_json_text,
    qa_item_payload_from_uw_entry,
)

__all__ = [
    "find_uw_entry",
    "load_uw_entries",
    "qa_item_payload_from_uw_entry",
]


def load_uw_entries(json_path):
    return parse_entries_from_json_text(Path(json_path).read_text(encoding="utf-8"))


def find_uw_entry(json_path, content_id):
    for entry in load_uw_entries(json_path):
        if str(entry.get("content_id")) == str(content_id):
            return entry
    raise ValueError(f"content_id {content_id} not found in {json_path}")
