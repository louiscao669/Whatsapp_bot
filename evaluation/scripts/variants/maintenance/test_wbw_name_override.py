#!/usr/bin/env python3
"""Pure tests for the word-by-word canonical-name override.

Run: python3 evaluation/scripts/variants/maintenance/test_wbw_name_override.py
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "evaluation" / "scripts" / "scoring" / "current"))
from translation_quality import (  # noqa: E402
    _wbw_load_name_overrides, wbw_join, wbw_name_override,
)

OV = {"micah": "米迦", "dan": "但", "danites": "但人", "who": "谁",
      "beth-millo": "米罗", "zebul": "西布"}
fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


check("bare proper noun is canonicalised",
      wbw_name_override("Micah", OV) == "米迦")
check("case is irrelevant to the lookup",
      wbw_name_override("MICAH", OV) == wbw_name_override("micah", OV) == "米迦")
check("the generic 'who' no longer renders as the organisation",
      wbw_name_override("who", OV) == "谁")

# the punctuation-dependence is the whole reason one passage held two spellings
check("trailing punctuation rides along, name still canonical",
      wbw_name_override("Micah,", OV) == "米迦,")
check("a verse number glued to the token survives intact",
      wbw_name_override("Micah.\n\n12", OV) == "米迦.\n\n12")
check("leading quote rides along",
      wbw_name_override("“Micah", OV) == "“米迦")
check("every punctuation variant now gives the SAME name",
      len({wbw_name_override(w, OV).replace(w.strip("“,.\n0123456789"), "")
           for w in ("Micah", "Micah,", "“Micah")}) >= 1
      and all("米迦" in wbw_name_override(w, OV)
              for w in ("Micah", "Micah,", "Micah.\n\n12", "“Micah")))

check("possessive becomes 的 rather than falling through",
      wbw_name_override("Micah’s", OV) == "米迦的")
check("ascii possessive too", wbw_name_override("Micah's", OV) == "米迦的")
check("hyphenated place name is one entry, not two words",
      wbw_name_override("Beth-millo", OV) == "米罗")

# all-or-nothing: an unknown latin run must send the token down the normal path
check("unknown word falls through", wbw_name_override("mother", OV) is None)
check("hyphenated NON-name falls through, never half-translated",
      wbw_name_override("twenty-two", OV) is None)
check("a token with no latin at all falls through",
      wbw_name_override("1,100", OV) is None)
check("empty override table is a no-op", wbw_name_override("Micah", {}) is None)
check("possessive of an unknown name falls through",
      wbw_name_override("Jezebel’s", OV) is None)

# the shipped table
shipped = _wbw_load_name_overrides()
check("shipped table loads and is non-trivial", len(shipped) >= 80)
check("shipped table is all lower-cased keys",
      all(k == k.lower() for k in shipped))
check("shipped table carries no latin-script values",
      not any(any(c.isascii() and c.isalpha() for c in v) for v in shipped.values()))
for eng, want in (("micah", "米迦"), ("dan", "但"), ("danites", "但人"),
                  ("who", "谁"), ("abimelech", "亚比米勒"), ("gaal", "迦勒")):
    check(f"shipped: {eng} -> {want}", shipped.get(eng) == want)

# ---------------------------------------------------------------- spacing
# Chinese is not spaced between words; the old " ".join announced the arm as machine
# output on sight. Two gaps must still survive, or the passage stops being parseable.
def J(*tokens, keep=False):
    return wbw_join([(t, r) for t, r in tokens], keep_spaces=keep)


check("words are joined with nothing, as Chinese is written",
      J(("Now", "现在"), ("a", "一个"), ("man", "男人")) == "现在一个男人")
check("keep_spaces=1 reproduces the old spaced output",
      J(("Now", "现在"), ("a", "一个"), keep=True) == "现在 一个")

# pilot_import._TIER1_MARKER is r"(\d{1,3})\s+" -- a marker without its space is not a verse
check("a verse marker keeps its trailing space",
      J(("17", "17"), ("Now", "现在"), ("a", "一个")) == "17 现在一个")
check("a verse number glued to the previous token keeps its space too",
      J(("Micah.\n\n12", "米迦.\n\n12"), ("They", "他们")) == "米迦.\n\n12 他们")
import re as _re
_MARKER = _re.compile(r"(?<![\w\]\-\u2013\u2014])(\d{1,3})\s+")
check("the pilot's verse-marker regex still finds both markers",
      [m.group(1) for m in _MARKER.finditer(
          J(("17", "17"), ("a", "一个"), ("man.\n\n2", "男人.\n\n2"), ("said", "说")))] == ["17", "2"])

check("a number inside the text is NOT spaced, and is not a marker",
      J(("1,100", "1,100"), ("shekels", "谢克尔")) == "1,100谢克尔")
check("two latin runs stay separated so they cannot fuse",
      J(("rapha", "rapha"), ("arameans", "arameans")) == "rapha arameans")
check("latin next to chinese needs no space",
      J(("rapha", "rapha"), ("and", "和")) == "rapha和")
check("empty tokens from double spaces do not add gaps",
      J(("a", "一个"), ("", ""), ("man", "男人")) == "一个男人")
check("a single token is returned unchanged", J(("man", "男人")) == "男人")
check("no tokens gives an empty string", wbw_join([]) == "")

print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILED: {fails}"))
sys.exit(1 if fails else 0)
