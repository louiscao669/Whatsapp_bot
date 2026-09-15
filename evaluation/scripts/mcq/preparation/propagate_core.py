#!/usr/bin/env python3
"""Copy a corrected 4-option CORE into the sibling option-count variants of the same items.

tier1_gold72_canonical, _5opt and _6opt are the same 71 items with the same A-D core and the
same key; the meta-options (E "I can't tell from this passage", F "None of the above") are a
pure tail appended by add_meta_options.py. So a distractor fix applied to one variant leaves
the others stale -- silently, because nothing compares them.

Rewriting each variant separately is NOT an option: the rewriter is an LLM, so two runs give
two different distractor sets and the variants stop being the same experiment. Fix once,
propagate.

    python3 .../propagate_core.py --from <corrected-dir> --to <dir> [--to <dir> ...] --dry-run
    python3 .../propagate_core.py --from <corrected-dir> --to <dir> [--to <dir> ...]

Items are matched by content_id. Each target keeps its OWN meta tail, so a 4-option target
stays 4-option and a 6-option target stays 6-option; only the core and the key move.

The pseudonymized arm is deliberately NOT propagatable: its option texts carry invented
names, so copying canonical text into it would reintroduce the real names the blinding
exists to remove. A target whose unchanged items do not already match the source is refused.
"""
from __future__ import annotations
import argparse, json, os, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
REPO = HERE.parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from evaluation.scripts.mcq.preparation.rewrite_distractors_gold72_en import (  # noqa: E402
    ABSTAIN_EN, LABELS, LETTERS, META_EN, NOTA_EN, split_meta)

DRIFT_LIMIT = 0.20      # fraction of matched items allowed to differ before we refuse


def load_dir(d):
    """content_id -> (filename, item). Items without an mcq or a content_id are ignored."""
    out = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        for it in json.load(open(os.path.join(d, fn))):
            cid = str(it.get("content_id") or "").strip()
            if cid and it.get("mcq"):
                out[cid] = (fn, it)
    return out


def key_of(mcq):
    c = mcq.get("content", "")
    return c.split("<answer>")[1] if "<answer>" in c else None


def core_of(mcq):
    return split_meta(mcq.get("mcq_options") or [])[0]


def rebuild(mcq, new_core, new_key_letter):
    """Write the core back, keeping THIS item's own meta tail and re-deriving the letters."""
    meta = split_meta(mcq.get("mcq_options") or [])[1]
    final = list(new_core) + meta
    labels = LABELS[:len(final)]
    assert final[labels.index(new_key_letter)] not in META_EN, "a meta-option became the key"
    mcq["mcq_options"] = final
    stem = mcq.get("mcq_stem") or ""
    mcq["content"] = ("<question>" + stem + "\n\n"
                      + "\n".join(f"{L}. {final[i]}" for i, L in enumerate(labels))
                      + f"\n<question><answer>{new_key_letter}<answer>")
    for txt, field in ((ABSTAIN_EN, "abstention_option"), (NOTA_EN, "nota_option")):
        if txt in final:
            mcq[field] = labels[final.index(txt)]
        else:
            mcq.pop(field, None)
    if meta:
        mcq["meta_option_count"] = len(meta)
    return final


def propagate(src_dir, dst_dir, dry_run=False, force=False):
    src, dst = load_dir(src_dir), load_dir(dst_dir)
    matched = [c for c in dst if c in src]
    if not matched:
        print(f"  [skip] {dst_dir}: no content_ids in common", file=sys.stderr)
        return 0, 0
    changed = [c for c in matched
               if core_of(dst[c][1]["mcq"]) != core_of(src[c][1]["mcq"])
               or key_of(dst[c][1]["mcq"]) != key_of(src[c][1]["mcq"])]
    drift = len(changed) / len(matched)
    if drift > DRIFT_LIMIT and not force:
        print(f"  [REFUSE] {dst_dir}: {len(changed)}/{len(matched)} items differ from the "
              f"source ({drift:.0%} > {DRIFT_LIMIT:.0%}). That is not a stale variant, it is "
              f"a DIFFERENT ARM -- the pseudonymized set carries invented names and needs its "
              f"own rewrite, not a copy. Use --force only if you are certain.",
              file=sys.stderr)
        return 0, len(changed)
    if dry_run:
        for c in changed:
            print(f"    would update {dst[c][1].get('id')}: "
                  f"key {key_of(dst[c][1]['mcq'])} -> {key_of(src[c][1]['mcq'])}")
        return 0, len(changed)

    touched_files = {}
    for c in changed:
        fn, it = dst[c]
        s_mcq = src[c][1]["mcq"]
        rebuild(it["mcq"], core_of(s_mcq), key_of(s_mcq))
        if s_mcq.get("distractors_rewritten"):
            it["mcq"]["distractors_rewritten"] = True
        touched_files.setdefault(fn, True)
    for fn in touched_files:
        p = os.path.join(dst_dir, fn)
        if not os.path.exists(p + ".bak"):
            shutil.copy(p, p + ".bak")
        items = json.load(open(p))
        by_cid = {str(i.get("content_id") or ""): i for i in items}
        for c in changed:
            if dst[c][0] == fn and c in by_cid:
                by_cid[c]["mcq"] = dst[c][1]["mcq"]
        json.dump(items, open(p, "w"), ensure_ascii=False, indent=2)
    return len(changed), len(changed)


def self_test():
    ok = []
    m4 = {"mcq_options": ["a", "b", "c", "d"], "mcq_stem": "Q?",
          "content": "<question>Q?\n\nA. a\nB. b\nC. c\nD. d\n<question><answer>B<answer>"}
    m6 = {"mcq_options": ["a", "b", "c", "d", ABSTAIN_EN, NOTA_EN], "mcq_stem": "Q?",
          "content": "x<answer>B<answer>", "abstention_option": "E", "nota_option": "F"}
    rebuild(m4, ["w", "x", "y", "z"], "C")
    ok.append(("4-option target stays 4-option", m4["mcq_options"] == ["w", "x", "y", "z"]))
    ok.append(("no meta fields invented on a 4-option item",
               "abstention_option" not in m4 and "nota_option" not in m4))
    ok.append(("key letter follows the source", key_of(m4) == "C"))
    rebuild(m6, ["w", "x", "y", "z"], "D")
    ok.append(("6-option target keeps its tail",
               m6["mcq_options"] == ["w", "x", "y", "z", ABSTAIN_EN, NOTA_EN]))
    ok.append(("E/F re-stamped from the rebuilt list",
               m6["abstention_option"] == "E" and m6["nota_option"] == "F"))
    ok.append(("rendered content carries all six labels",
               all(f"{L}. " in m6["content"] for L in "ABCDEF")))
    ok.append(("key is never a meta-option", key_of(m6) == "D"))
    raised = False
    try:
        rebuild({"mcq_options": ["a", "b", "c", "d", ABSTAIN_EN], "mcq_stem": ""},
                ["w", "x", "y", "z"], "E")
    except AssertionError:
        raised = True
    ok.append(("keying a meta-option raises rather than shipping", raised))
    ok.append(("split_meta round-trips through rebuild",
               split_meta(m6["mcq_options"])[1] == [ABSTAIN_EN, NOTA_EN]))
    for name, cond in ok:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    n = sum(1 for _, c in ok if c)
    print(f"\n{n}/{len(ok)} self-tests passed")
    return 0 if n == len(ok) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", help="QA dir holding the corrected core")
    ap.add_argument("--to", dest="dst", action="append", default=[],
                    help="QA dir to update; repeatable")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="propagate even when the target looks like a different arm")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.src or not a.dst:
        ap.error("--from and at least one --to are required")
    total = 0
    for d in a.dst:
        n, seen = propagate(a.src, d, a.dry_run, a.force)
        print(f"  {d}: {n} item(s) {'would be ' if a.dry_run else ''}updated "
              f"({seen} differed)")
        total += n
    print(f"\n{'would update' if a.dry_run else 'updated'} {total} item(s)"
          + ("" if a.dry_run else "; originals backed up alongside as .bak"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
