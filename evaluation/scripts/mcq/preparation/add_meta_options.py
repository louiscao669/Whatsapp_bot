#!/usr/bin/env python3
"""Append meta-options to every MCQ: an ABSTENTION (E) and optionally NONE-OF-THE-ABOVE (F).

    E. I can't tell from this passage      -- the passage does not give enough
                                              information. A claim about the READER.
    F. None of the above                   -- the passage does answer, but not with
                                              any of A-D. A claim about the OPTION SET.

Why they are different options rather than one: under omission the answer-bearing
clause is deleted, so E is correct; under mistranslation the fact is present but
altered, so F is correct. Running both can in principle discriminate defect family,
which nothing else in the design does.

Why that may not be measurable yet: with one meta-option, abstention fired at 6.6%
at omission 30% (14/213). Split two ways that is ~7 events per cell, and testing the
family x option interaction needs four cells. Build it, but check the fair-prompt
firing rate before trusting a 6-option run.

Neither meta-option is ever the keyed answer, and both are appended AFTER any
shuffle so their letters never move.

Usage:
  python3 .../add_meta_options.py <src-qa-dir> <dst-qa-dir>            # 5 options: A-E
  python3 .../add_meta_options.py <src-qa-dir> <dst-qa-dir> --nota     # 6 options: A-F
"""
import json, os, re, sys

ABSTAIN_EN = "I can't tell from this passage"
ABSTAIN_ZH = "根据这段文字无法判断"      # pinned post-translation
NOTA_EN    = "None of the above"
NOTA_ZH    = "以上都不是"                # pinned post-translation


def repair_ids(item):
    """Derive a missing top-level id/passage_id from content_id.

    gold72 t1_judg9:o93q (Judges 9:54) ships without either field. The pipeline
    keys on passage_id, so it has been SILENTLY DROPPED from every run.
    """
    cid = str(item.get("content_id") or "")
    if ":" not in cid: return False
    pid, iid = cid.split(":", 1)
    fixed = False
    if not item.get("passage_id"): item["passage_id"] = pid; fixed = True
    if not item.get("id"): item["id"] = iid.split("#")[0]; fixed = True
    if not item.get("question"):
        q = ((item.get("open") or {}).get("original_question")
             or (item.get("mcq") or {}).get("mcq_stem"))
        if q: item["question"] = q; fixed = True
    if not item.get("answer"):
        a = (item.get("open") or {}).get("original_answer")
        if a: item["answer"] = a; fixed = True
    return fixed


def add_meta(item, want_nota):
    mcq = item.get("mcq")
    if not mcq: return None
    opts = mcq.get("mcq_options")
    if not isinstance(opts, list): return None
    have = [str(o) for o in opts]
    base = [o for o in have
            if ABSTAIN_EN.rstrip(".").lower() not in o.lower()
            and NOTA_EN.lower() not in o.lower()]
    if len(base) != 4:
        print(f"  !! {item.get('id')}: expected 4 content options, found {len(base)} -- skipped")
        return None
    keyed = re.search(r"<answer>([A-F])<answer>", mcq.get("content", ""))
    if not keyed:
        print(f"  !! {item.get('id')}: no keyed letter -- skipped"); return None
    key = keyed.group(1)
    if key not in "ABCD":
        print(f"  !! {item.get('id')}: key {key} is not a content option -- skipped"); return None
    final = base + [ABSTAIN_EN] + ([NOTA_EN] if want_nota else [])
    letters = "ABCDEF"[:len(final)]
    stem = mcq.get("mcq_stem") or item.get("question") or ""
    mcq["mcq_options"] = final
    mcq["content"] = ("<question>" + stem + "\n\n"
                      + "\n".join(f"{L}. {final[i]}" for i, L in enumerate(letters))
                      + f"\n<question><answer>{key}<answer>")
    mcq["abstention_option"] = "E"
    if want_nota: mcq["nota_option"] = "F"
    mcq["meta_option_count"] = len(final) - 4
    return key


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    want_nota = "--nota" in sys.argv
    if len(args) != 2:
        print(__doc__); return 2
    src, dst = args
    os.makedirs(dst, exist_ok=True)
    files = changed = total = 0
    keys = {}
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".json"): continue
        items = json.load(open(os.path.join(src, fn)))
        files += 1
        for it in items:
            if not isinstance(it, dict) or not it.get("mcq"): continue
            if repair_ids(it):
                print(f"  repaired ids for {it.get('content_id')} "
                      f"-> passage_id={it.get('passage_id')} id={it.get('id')}")
            total += 1
            k = add_meta(it, want_nota)
            if k: changed += 1; keys[k] = keys.get(k, 0) + 1
        json.dump(items, open(os.path.join(dst, fn), "w"), ensure_ascii=False, indent=2)
    n_opt = 6 if want_nota else 5
    print(f"{src} -> {dst}")
    print(f"  files {files}   mcq items {total}   meta-options added to {changed}")
    print(f"  options per item: {n_opt}   nominal chance: {1/n_opt:.3f}")
    print(f"  keyed-letter distribution (E/F must be absent): {dict(sorted(keys.items()))}")
    assert not (set(keys) & {"E", "F"}), "a meta-option must never be the keyed answer"
    print(f"  NOTE: {n_opt}-option results are NOT comparable to any other option count.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
