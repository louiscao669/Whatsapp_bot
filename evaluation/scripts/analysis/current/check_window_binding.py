#!/usr/bin/env python3
"""Assert the answerer actually got a verse window, not the whole passage.

Run this after every campaign. The strong-66 / hard95 grids were run with
WINDOWS="" and nobody noticed for six weeks; median prompt_tokens would have
caught it on day one. Blinded gold72 baseline: ~281.
"""
import glob, json, statistics, sys
root = sys.argv[1] if len(sys.argv) > 1 else "evaluation/outputs/tier1_bsb_unblinded"
pat = f"{root}/*/*/*/*/generated_answers_target_llama.json"
pt = [x["answer_effort"]["prompt_tokens"]
      for f in glob.glob(pat)
      for x in json.load(open(f))
      if (x.get("answer_effort") or {}).get("prompt_tokens")]
if not pt:
    print(f"no answer files under {root}"); sys.exit(1)
med = statistics.median(pt)
print(f"{root}\n  cells matched : {len(glob.glob(pat))}\n  observations  : {len(pt)}")
print(f"  median prompt_tokens : {med:.0f}   (windowed ~281 | whole passage ~900)")
print("  VERDICT:", "windows bound OK" if med < 450 else "!! WINDOWS DID NOT BIND -- comparison is void")
sys.exit(0 if med < 450 else 2)
