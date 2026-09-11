#!/usr/bin/env python3
"""Pin the translated abstention option to one fixed string, everywhere.

The MT stage translates option E per item, so the same English sentence can come
back a dozen different ways across 71 items x 10 passages. An abstention option
whose wording drifts is a different option in each item, which destroys the whole
point of measuring its selection rate. This forces one string.

Run AFTER the pipeline writes qa_target*.json, BEFORE answering, e.g. with
--stop-after translate; or re-run it and then force the answer stage.

  python3 evaluation/scripts/mcq/preparation/pin_abstention_option.py \
      evaluation/outputs/tier1_bsb_5opt --apply
"""
import json, os, sys
from collections import Counter

PINNED = "根据这段文字无法判断"
# _shared/*_qa_zh*.json are UPSTREAM of the per-cell files: the decanonicalize
# stage regenerates qa_target_decanonicalized.json from them, so pinning only the
# cell files silently reverts on the next run.
TARGETS = ("qa_target.json", "qa_target_decanonicalized.json")
SHARED_SUFFIXES = ("_qa_zh.json", "_qa_zh_decanonicalized.json")

# Guard: only overwrite text that already READS as an abstention. The script
# rewrites whatever sits at letter E, so if an item ever had real content there
# a blind replace would silently destroy a distractor. Any E text containing
# none of these markers is reported and left alone unless --force is passed.
ABSTAIN_MARKERS = ("无法", "不能", "没有说", "未提", "不知道", "判断", "确定",
                   "can't tell", "cannot tell", "unable")

def looks_like_abstention(txt):
    t = str(txt).lower()
    return any(m.lower() in t for m in ABSTAIN_MARKERS)


def main():
    root = sys.argv[1]
    apply_ = "--apply" in sys.argv
    force = "--force" in sys.argv
    add_missing = "--add-missing" in sys.argv   # for already-Chinese QA (Luke):
                                                # no translation stage, so adding
                                                # the option IS pinning it

    # Refuse to run after answering: rewriting the options then would leave the
    # file describing something the model never saw.
    if apply_ and not force:
        stale = []
        for dirpath, _, filenames in os.walk(root):
            if "generated_answers_target_llama.json" in filenames:
                stale.append(dirpath)
        if stale:
            print(f"REFUSING: {len(stale)} cell(s) already contain answers, e.g.")
            for d in stale[:3]: print(f"    {d}")
            print("Pinning now would make qa_target*.json misrepresent what the model was shown.")
            print("Run this BEFORE answering (STOP_AFTER=translate), or pass --force and")
            print("then re-answer with FORCE_ANSWER=1.")
            sys.exit(2)

    seen, fixed, files, refused = Counter(), 0, 0, []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn not in TARGETS and not fn.endswith(SHARED_SUFFIXES): continue
            p = os.path.join(dirpath, fn)
            data = json.load(open(p))
            touched = False
            for it in data:
                if it.get("q_type") != "mcq": continue
                opts = it.get("A")
                if not isinstance(opts, dict): continue
                if "E" not in opts:
                    if not add_missing: continue
                    if len(opts) != 4:
                        refused.append((it.get("passage_id"), f"<{len(opts)} options, expected 4>"))
                        continue
                    if str(it.get("correct", "")).upper() == "E":
                        refused.append((it.get("passage_id"), "<E is the keyed answer>"))
                        continue
                    seen["<added>"] += 1
                    if apply_: opts["E"] = PINNED; touched = True
                    fixed += 1
                    continue
                seen[opts["E"]] += 1
                if opts["E"] == PINNED:
                    continue
                if not looks_like_abstention(opts["E"]) and not force:
                    refused.append((it.get("passage_id"), opts["E"]))
                    continue
                if apply_: opts["E"] = PINNED; touched = True
                fixed += 1
            if touched:
                json.dump(data, open(p, "w"), ensure_ascii=False, indent=2); files += 1
    print(f"root: {root}")
    print(f"  distinct translations of option E found: {len(seen)}")
    for txt, n in seen.most_common(12):
        print(f"    {n:5d}  {txt}")
    if refused:
        print(f"  !! {len(refused)} option(s) at letter E do NOT read as an abstention and were LEFT ALONE:")
        for pid, txt in refused[:8]: print(f"       {pid}: {txt}")
        print("     inspect these before using --force; a blind replace would destroy a real distractor")
    if apply_: print(f"  rewrote {fixed} option(s) across {files} file(s) -> {PINNED}")
    else: print(f"  {fixed} option(s) would be rewritten (dry run; pass --apply)")
    if not seen:
        print("  !! no 5-option MCQ items found -- did the run use the _5opt QA dirs?")
        sys.exit(1)

if __name__ == "__main__":
    main()
