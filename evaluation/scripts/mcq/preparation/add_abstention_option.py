#!/usr/bin/env python3
"""Add a fifth MCQ option E -- an ABSTENTION, not "none of the above".

  E. I can't tell from this passage.

Why that wording rather than "none of the above": the defect knob destroys
information, so at 30% omission the keyed answer usually IS still one of A-D as
a fact about the source text -- the reader simply cannot recover it from what
they were given. "None of the above" would be a false assertion in exactly the
cells that matter; "I can't tell from this passage" is the CORRECT response to a
damaged text. It also scopes the answer to the passage, which is what lets you
detect respondents answering from prior knowledge.

E is never the keyed answer. Its selection rate is a separate outcome:
it should be ~0 on clean text and rise with dose.

Usage:
  python3 evaluation/scripts/mcq/preparation/add_abstention_option.py \
      evaluation/datasets/pseudonymized/qa/tier1_bsb_gold72 \
      evaluation/datasets/pseudonymized/qa/tier1_bsb_gold72_5opt
"""
import json, os, re, sys

ABSTAIN_EN = "I can't tell from this passage"
ABSTAIN_ZH = "根据这段文字无法判断"   # pinned after translation; see pin_abstention_option.py

def add_e(item):
    mcq = item.get("mcq")
    if not mcq: return False
    opts = mcq.get("mcq_options")
    if not isinstance(opts, list): return False
    if any(ABSTAIN_EN.rstrip(".").lower() in str(o).lower() for o in opts):
        return False                      # already has it, idempotent
    if len(opts) != 4:
        print(f"  !! {item.get('id')}: expected 4 options, found {len(opts)} -- skipped")
        return False
    mcq["mcq_options"] = list(opts) + [ABSTAIN_EN]
    content = mcq.get("content", "")
    m = re.search(r"(\n\s*D\.\s*[^\n]*)(\n<question>)", content)
    if not m:
        print(f"  !! {item.get('id')}: could not locate option D in content -- skipped")
        mcq["mcq_options"] = opts          # roll back
        return False
    mcq["content"] = content[:m.end(1)] + f"\nE. {ABSTAIN_EN}" + content[m.start(2):]
    mcq["abstention_option"] = "E"
    return True

def main():
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    files = changed = total = 0
    keys = {}
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".json"): continue
        items = json.load(open(os.path.join(src, fn)))
        files += 1
        for it in items:
            if not isinstance(it, dict) or not it.get("mcq"): continue
            total += 1
            if add_e(it): changed += 1
            m = re.search(r"<answer>([A-E])<answer>", it["mcq"].get("content", ""))
            if m: keys[m.group(1)] = keys.get(m.group(1), 0) + 1
        json.dump(items, open(os.path.join(dst, fn), "w"), ensure_ascii=False, indent=2)
    print(f"{src} -> {dst}")
    print(f"  files {files}   mcq items {total}   option E added to {changed}")
    print(f"  keyed-letter distribution (E must be absent): {dict(sorted(keys.items()))}")
    assert keys.get("E", 0) == 0, "E must never be the keyed answer"

if __name__ == "__main__":
    main()
