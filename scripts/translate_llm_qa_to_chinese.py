#!/usr/bin/env python3
"""Compatibility wrapper for the evaluation translator script."""

from pathlib import Path
import runpy


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "scripts"
    / "translate_llm_qa_to_chinese.py"
)


if __name__ == "__main__":
    runpy.run_path(str(SCRIPT), run_name="__main__")
