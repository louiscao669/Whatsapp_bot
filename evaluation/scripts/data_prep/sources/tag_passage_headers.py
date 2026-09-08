#!/usr/bin/env python3
"""Wrap Bible section headings in explicit ``<header>`` tags.

Headings are identified by the known section-start verses in Luke 1--8.  This
avoids mistaking unnumbered poetry continuation lines for headings.  The
operation is idempotent and preserves the original files and line endings
apart from adding the tags.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


SECTION_STARTS = {
    1: {1, 5, 26, 39, 46, 57, 67},
    2: {1, 22, 41},
    3: {1, 21},
    4: {1, 14, 31, 38},
    5: {1, 12, 17, 27, 33},
    6: {1, 12, 17, 27, 37, 43, 46},
    7: {1, 11, 18, 36},
    8: {1, 16, 19, 22, 26, 40},
}

DEFAULT_FILE_NAMES = (
    "passage_target.txt",
    "passage_target_decanonicalized.txt",
    "passage_target_backcanonicalized.txt",
)

VERSE_RE = re.compile(r"^\s*(?P<verse>\d{1,3})[a-z]?(?:[\].):])?\s+")
TAGGED_RE = re.compile(r"^\s*<header>.*</header>\s*$")


def tag_text(text: str, section_starts: set[int]) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    tagged = 0
    for index, line in enumerate(lines[:-1]):
        content = line.rstrip("\r\n")
        stripped = content.strip()
        if not stripped or TAGGED_RE.match(content) or VERSE_RE.match(stripped):
            continue
        if index > 0 and lines[index - 1].strip():
            continue
        next_match = VERSE_RE.match(lines[index + 1].strip())
        if not next_match or int(next_match.group("verse")) not in section_starts:
            continue

        leading = content[: len(content) - len(content.lstrip())]
        trailing = content[len(content.rstrip()) :]
        newline = line[len(content) :]
        lines[index] = f"{leading}<header>{stripped}</header>{trailing}{newline}"
        tagged += 1
    return "".join(lines), tagged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs-root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--model", default="1.7b")
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument("--file-names", nargs="+", default=list(DEFAULT_FILE_NAMES))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files_seen = 0
    files_changed = 0
    headings_tagged = 0
    wanted = set(args.file_names)

    for chapter in args.chapters:
        root = args.outputs_root / f"luke{chapter}" / args.model
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name in wanted):
            files_seen += 1
            original = path.read_text(encoding="utf-8")
            transformed, count = tag_text(original, SECTION_STARTS[chapter])
            if not count:
                continue
            files_changed += 1
            headings_tagged += count
            if not args.dry_run:
                path.write_text(transformed, encoding="utf-8")

    action = "would tag" if args.dry_run else "tagged"
    print(f"scanned {files_seen} file(s)")
    print(f"{action} {headings_tagged} heading(s) in {files_changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
