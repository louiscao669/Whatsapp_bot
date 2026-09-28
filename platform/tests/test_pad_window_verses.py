#!/usr/bin/env python3
"""pad_window_verses: restore an omission-damaged delivery window to full length.

Pure-function tests -- no database, no ORM rows. Run:
    python platform/tests/test_pad_window_verses.py

Why the function exists: with gold72, a window holding all three verses NEVER has its
answer deleted (0% at both doses measured 2026-09-28), so window length tells a reader
whether to abstain before reading a word -- "abstain iff <= 1 verse" scores 81.4% on its
own, beating two of the three answer models. Padding removes that shortcut.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "eten-shared"))

from eten_shared.verse_windows import pad_window_verses  # noqa: E402


class V:
    def __init__(self, n):
        self.verse_number = n

    def __repr__(self):
        return f"V({self.verse_number})"


def nums(verses):
    return [v.verse_number for v in verses]


fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


ALL = [V(n) for n in (20, 21, 22, 23, 24, 25)]

check("intact window returned unchanged",
      nums(pad_window_verses([21, 22, 23], ALL)) == [21, 22, 23])
check("two survivors pad to three", len(pad_window_verses([21, 22], ALL)) == 3)
check("one survivor pads to three", len(pad_window_verses([22], ALL)) == 3)
check("padding keeps the survivors it started from",
      {21, 22} <= set(nums(pad_window_verses([21, 22], ALL))))
check("result is in passage order",
      nums(pad_window_verses([22], ALL)) == sorted(nums(pad_window_verses([22], ALL))))

GAPPED = [V(n) for n in (20, 22, 25)]
check("a gapped passage still yields three (gaps are what omission did)",
      nums(pad_window_verses([22], GAPPED)) == [20, 22, 25])

check("a DELETED verse is never returned",
      23 not in nums(pad_window_verses([22, 23], [V(20), V(21), V(22), V(24)])))

check("prefers a verse no other window claims",
      23 not in nums(pad_window_verses([22], ALL, occupied={23})))
check("takes a claimed verse rather than return a short window",
      len(pad_window_verses([22], ALL, occupied={20, 21, 23, 24, 25})) == 3)
check("occupied is advisory: it never shrinks the result",
      len(pad_window_verses([21], ALL, occupied={20, 22, 23, 24, 25})) == 3)

check("a wholly deleted window anchors where it was, not at the passage start",
      nums(pad_window_verses([24], [V(20), V(21), V(22), V(25), V(26)])) == [22, 25, 26])
check("no surviving verses -> empty, not a crash", pad_window_verses([21, 22], []) == [])
check("no window and no survivors -> empty", pad_window_verses([], []) == [])
check("a passage shorter than the window returns what exists",
      len(pad_window_verses([21], [V(21), V(22)])) == 2)

print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILED: {fails}"))
raise SystemExit(1 if fails else 0)
