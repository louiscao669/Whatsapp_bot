#!/usr/bin/env python3
"""Shared helpers reused as-is (no behavior differences) across evaluation/scripts/*.py."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_items(data: Any) -> list[dict]:
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [item for item in data["items"] if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def average_ranks_desc(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    ranks: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and math.isclose(ordered[end][1], ordered[index][1]):
            end += 1
        rank = (index + 1 + end) / 2
        for key, _ in ordered[index:end]:
            ranks[key] = rank
        index = end
    return ranks
