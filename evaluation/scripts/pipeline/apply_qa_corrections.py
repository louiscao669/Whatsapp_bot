#!/usr/bin/env python3
"""Apply reviewed Chinese QA corrections to generated campaign artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def patch_node(node: Any, corrections: dict[str, dict[str, Any]]) -> int:
    changed = 0
    if isinstance(node, list):
        for item in node:
            changed += patch_node(item, corrections)
        return changed
    if not isinstance(node, dict):
        return 0

    passage_id = node.get("passage_id")
    correction = corrections.get(passage_id)
    if correction:
        for field, value in correction.items():
            if node.get(field) != value:
                node[field] = value
                changed += 1

    for value in node.values():
        changed += patch_node(value, corrections)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="JSON file or directory to update recursively")
    parser.add_argument("--corrections", type=Path, required=True)
    args = parser.parse_args()

    corrections = json.loads(args.corrections.read_text(encoding="utf-8"))
    paths = [args.root] if args.root.is_file() else sorted(args.root.rglob("*.json"))
    changed_files = 0
    changed_fields = 0

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        changed = patch_node(data, corrections)
        if not changed:
            continue
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed_files += 1
        changed_fields += changed

    print(f"QA corrections: {changed_fields} field(s) in {changed_files} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
