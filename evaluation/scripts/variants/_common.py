"""Deterministic parsing, seeds, and file helpers for passage variants."""

from __future__ import annotations

import json
import re
import shutil
import zlib
from pathlib import Path
from typing import Any

VERSE_MARKER_PATTERN = re.compile(r"(?<![\w\]])(\d{1,3})\s+")
CONTENT_CHAR_PATTERN = re.compile(r"[\w\u3400-\u9fff]")


def seed_offset(chapter) -> int:
    """Deterministic per-cell seed offset.

    Cells used to be integer chapter numbers, so the seed was `args.seed +
    chapter`. Named passage dirs ("tier1/t1_judg9") broke that with a TypeError.
    Integers keep their exact previous offset, so every Luke variant reproduces
    bit-for-bit; names hash to a stable offset. crc32 rather than hash(), which
    is salted per process and would make runs non-reproducible.
    """
    if isinstance(chapter, int):
        return chapter
    text = str(chapter)
    if text.isdigit():
        return int(text)
    return zlib.crc32(text.encode("utf-8")) % 100000


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def format_rate(rate: float) -> str:
    value = rate * 100
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))}%"
    return f"{value:g}%"


def content_len(text: str) -> int:
    return len(CONTENT_CHAR_PATTERN.findall(text or ""))


def parse_verse_blocks(text: str) -> list[dict]:
    matches = list(VERSE_MARKER_PATTERN.finditer(text))
    if not matches:
        return [{"kind": "text", "verse": None, "text": text}]

    blocks = []
    if matches[0].start() > 0:
        blocks.append(
            {
                "kind": "heading",
                "verse": None,
                "text": text[: matches[0].start()],
            }
        )

    for index, match in enumerate(matches):
        verse = int(match.group(1))
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append(
            {
                "kind": "verse",
                "verse": verse,
                "text": text[start:end],
            }
        )
    return blocks


def copy_if_exists(source: Path, target: Path) -> None:
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def copy_shared_files(source_shared: Path, target_shared: Path) -> None:
    if not source_shared.exists():
        return
    target_shared.mkdir(parents=True, exist_ok=True)
    for path in source_shared.iterdir():
        if path.is_file():
            shutil.copy2(path, target_shared / path.name)
