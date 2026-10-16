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


def outputs_root(start_file: str | Path) -> str:
    """Locate outputs using the environment, caller's repository, then cwd."""
    import os

    env = os.environ.get("EVAL_OUTPUTS_ROOT")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(start_file))
    for _ in range(6):
        candidate = os.path.join(here, "evaluation", "outputs")
        if os.path.isdir(candidate):
            return candidate
        here = os.path.dirname(here)
    for candidate in ("evaluation/outputs", "outputs", "."):
        if os.path.isdir(candidate):
            return candidate
    raise SystemExit("cannot locate evaluation/outputs; set EVAL_OUTPUTS_ROOT")


def longest_shared_span(option: str, window: str) -> int:
    best = 0
    for start in range(len(option)):
        for end in range(start + best + 1, len(option) + 1):
            if option[start:end] in window:
                best = end - start
            else:
                break
    return best


def all_format_variants(item: dict) -> list[dict]:
    variants = []
    for q_type in ("open", "mcq"):
        nested = item.get(q_type)
        if not isinstance(nested, dict):
            continue
        merged = {
            key: value for key, value in item.items() if key not in {"open", "mcq"}
        }
        merged.update(nested)
        merged["q_type"] = q_type
        base_id = item.get("content_id") or item.get("id") or item.get("passage_id")
        if base_id:
            merged["content_id"] = f"{base_id}-{q_type}"
            merged["passage_id"] = f"uw-{base_id}-{q_type}"
        variants.append(merged)
    return variants
