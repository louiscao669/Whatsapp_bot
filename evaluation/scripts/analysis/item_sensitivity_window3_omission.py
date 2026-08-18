#!/usr/bin/env python3
"""DEPRECATED shim -> item_sensitivity_window3.py.

The 2026-07-27 design fits BOTH adequacy families ({0,15,30}% omission AND mistranslation),
so the analysis moved to the family-agnostic `item_sensitivity_window3.py`. Calling this file
forwards every argument there. With no arguments it reproduces the ORIGINAL behaviour of this
script -- omission only, on the old {0,10,20,30} ladder -- so previously recorded numbers stay
reproducible:

  python evaluation/scripts/analysis/item_sensitivity_window3_omission.py
      == item_sensitivity_window3.py --families omission --doses 0 10 20 30

Use item_sensitivity_window3.py directly for anything new.
"""
import runpy
import sys
from pathlib import Path

TARGET = Path(__file__).with_name("item_sensitivity_window3.py")
LEGACY_ARGS = ["--families", "omission", "--doses", "0", "10", "20", "30"]

if __name__ == "__main__":
    print(f"[deprecated] {Path(__file__).name} -> {TARGET.name}", file=sys.stderr)
    # Legacy defaults go FIRST so any --families/--doses the caller supplies overrides them,
    # while every other flag (e.g. --no-per-item) still lands on the legacy omission ladder.
    print(f"[deprecated] pinning legacy scope: {' '.join(LEGACY_ARGS)}", file=sys.stderr)
    sys.argv = [str(TARGET)] + LEGACY_ARGS + sys.argv[1:]
    runpy.run_path(str(TARGET), run_name="__main__")
