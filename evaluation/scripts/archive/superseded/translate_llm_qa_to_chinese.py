#!/usr/bin/env python3
"""Compatibility wrapper for the evaluation translator script."""

from pathlib import Path
import runpy


SCRIPT = (
    Path(__file__).resolve().parents[4]
    / "evaluation"
    / "scripts"
    / "pipeline"
    / "translate_qa.py"
)


if __name__ == "__main__":
    runpy.run_path(str(SCRIPT), run_name="__main__")
