#!/usr/bin/env python3
"""Run both falseness-gate wiring suites. Offline: no langchain, no ollama, no API key.

Each suite installs its own fake `relevance_chain` into sys.modules, so they cannot share a
process -- hence the subprocess per suite.

    python3 evaluation/scripts/mcq/preparation/tests_falseness_gate.py
"""
import subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITES = ["tests_falseness_gate_en.py", "tests_falseness_gate_luke.py",
          "tests_falseness_gate_unaudited.py"]

bad = 0
for name in SUITES:
    r = subprocess.run([sys.executable, str(HERE / name)], capture_output=True, text=True)
    print(f"--- {name} ---")
    for line in (r.stdout + r.stderr).splitlines():
        if any(t in line for t in ("[PASS]", "[FAIL]", "Error", "assert", "checks passed")):
            print("  " + line.strip())
    if r.returncode:
        bad += 1
        print(r.stdout[-1500:]); print(r.stderr[-2500:])
print("\nFALSENESS GATE WIRING: " + ("ALL PASS" if not bad else f"{bad} SUITE(S) FAILED"))
raise SystemExit(1 if bad else 0)
