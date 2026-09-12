#!/usr/bin/env python3
"""Pin each translated meta-option to one fixed string, everywhere.

    E  根据这段文字无法判断   abstention  -- not enough information in the passage
    F  以上都不是             none-of-the-above -- passage answers, but not with A-D

The MT stage translates options per item and per passage batch, so the same English
sentence comes back worded several ways (measured: 2 renderings of E across one
run's 426 items, e.g. 我无法从这段经文判断 / 我无法从这段经文中判断). A meta-option
whose wording drifts is a different option in each item, which destroys the point of
measuring its selection rate -- and for these two the plausible variants cross the
construct boundary (无法判断 "cannot determine" vs 未提及 "not mentioned" vs 不知道
"don't know" are three different claims).

Run AFTER the QA translation, BEFORE answering. Covers the _shared upstream files
too: the decanonicalize stage regenerates the per-cell files from them, so pinning
only the cells silently reverts.

  python3 .../pin_meta_options.py <output-root>                 # dry run
  python3 .../pin_meta_options.py <output-root> --apply
  python3 .../pin_meta_options.py <output-root> --apply --add-missing   # already-Chinese QA
"""
import json, os, sys
from collections import Counter

PINNED = {"E": "根据这段文字无法判断", "F": "以上都不是"}
MARKERS = {
    "E": ("无法", "不能", "没有说", "未提", "不知道", "判断", "确定", "can't tell", "cannot tell", "unable"),
    "F": ("以上", "都不", "均不", "none of the above", "no ne of"),
}
TARGETS = ("qa_target.json", "qa_target_decanonicalized.json")
SHARED_SUFFIXES = ("_qa_zh.json", "_qa_zh_decanonicalized.json")


def looks_right(label, txt):
    t = str(txt).lower()
    return any(m.lower() in t for m in MARKERS[label])


def main():
    if len(sys.argv) < 2: print(__doc__); return 2
    root = sys.argv[1]
    apply_ = "--apply" in sys.argv
    force = "--force" in sys.argv
    add_missing = "--add-missing" in sys.argv

    if apply_ and not force:
        stale = [d for d, _, fs in os.walk(root) if "generated_answers_target_llama.json" in fs]
        if stale:
            print(f"REFUSING: {len(stale)} cell(s) already contain answers, e.g.")
            for d in stale[:3]: print(f"    {d}")
            print("Pinning now would make qa_target*.json misrepresent what the model saw.")
            print("Run before answering (STOP_AFTER=translate), or pass --force then re-answer")
            print("with FORCE_ANSWER=1.")
            return 2

    seen = {L: Counter() for L in PINNED}
    fixed = Counter(); refused = []; files = 0
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn not in TARGETS and not fn.endswith(SHARED_SUFFIXES): continue
            path = os.path.join(dirpath, fn)
            data = json.load(open(path))
            touched = False
            for it in data:
                if not isinstance(it, dict) or it.get("q_type") != "mcq": continue
                opts = it.get("A")
                if not isinstance(opts, dict): continue
                n_content = sum(1 for L in "ABCD" if L in opts)
                for L, pin in PINNED.items():
                    if L in opts:
                        seen[L][opts[L]] += 1
                        if opts[L] == pin: continue
                        if not looks_right(L, opts[L]) and not force:
                            refused.append((L, it.get("passage_id"), opts[L])); continue
                        if apply_: opts[L] = pin; touched = True
                        fixed[L] += 1
                    elif add_missing:
                        # only extend an item that has its full content set and no key clash
                        if n_content != 4 or str(it.get("correct", "")).upper() == L: continue
                        if L == "F" and "E" not in opts: continue   # E before F
                        seen[L]["<added>"] += 1
                        if apply_: opts[L] = pin; touched = True
                        fixed[L] += 1
            if touched:
                json.dump(data, open(path, "w"), ensure_ascii=False, indent=2); files += 1

    print(f"root: {root}")
    for L in PINNED:
        if not seen[L]: continue
        print(f"  option {L}: {len(seen[L])} distinct rendering(s)")
        for txt, n in seen[L].most_common(8): print(f"      {n:5d}  {txt}")
    if refused:
        print(f"  !! {len(refused)} option(s) do NOT read as the expected meta-option, LEFT ALONE:")
        for L, pid, txt in refused[:8]: print(f"       {L} {pid}: {txt}")
        print("     inspect before using --force; a blind replace would destroy a real option")
    if apply_:
        print(f"  rewrote {dict(fixed)} across {files} file(s)")
    else:
        print(f"  would rewrite {dict(fixed)} (dry run; pass --apply)")
    if not any(seen.values()):
        print("  !! no meta-options found -- did the run use a _5opt/_6opt QA dir?")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
