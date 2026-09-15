#!/usr/bin/env python3
"""Flatten the distribution of KEY POSITIONS across an MCQ set.

Why. The answer models are deterministic at temperature 0 and each has a letter prior:

    llama3.2:1b   A 24%  B 33%  C 22%  D 21%
    qwen2.5:1.5b  A 21%  B 31%  C 31%  D 18%
    qwen3:1.7b    A 21%  B 25%  C 21%  D 33%

gold72's keys sit at A 19% / B 28% / C 22% / D 31%. Because the key distribution is
uneven, a model that reads nothing and simply repeats its favourite letter scores the
SHARE OF KEYS on that letter -- measured exactly, on the real 72 items:

    always "A" -> 0.194     always "C" -> 0.222
    always "B" -> 0.278     always "D" -> 0.306

With the key distribution flat, that contribution is exactly chance whatever the model's
prior, since sum_L P(key=L) * P(pick=L) = 0.25 * sum_L P(pick=L) = 0.25.

What this fixes and what it does not. It removes the AGGREGATE artifact -- the reason a
"which items does the key lose on?" screen returned a set that was 78% keyed D and
flattered the D-preferring model. It does NOT make any single item's measurement
prior-free: an item is still one deterministic decision at one position. For per-item
work (item difficulty, closed-book screening, adaptive selection) use the rotation ladder
in mcq_option_order.py, which costs four runs. For pooled dose sensitivity this is enough,
and it costs one.

It also leaves the paired dose contrast untouched, because that contrast already
differences the position effect out: 0% and 30% cells of an item share a position.

Method. Each item's content options are CYCLICALLY ROTATED so the key text lands on its
target letter; the key text itself never changes and the distractors keep their relative
order. Assignment is minimum-churn -- an item keeps its current key letter whenever that
letter still has quota -- so the smallest possible number of items move. Meta-options
(abstention, none-of-the-above) never move: they are appended after the content options
and are never the key.

The SAME assignment, keyed by content_id, is applied to every directory given, so the
4-, 5- and 6-option variants of an item stay in lockstep.

    python3 .../rebalance_key_positions.py --dir <qa-dir> [--dir <qa-dir> ...] --dry-run
    python3 .../rebalance_key_positions.py --dir <qa-dir> [--dir <qa-dir> ...]
    python3 .../rebalance_key_positions.py --self-test
"""
from __future__ import annotations

import argparse, collections, json, os, random, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
for p in (str(REPO), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from evaluation.scripts.mcq.preparation.propagate_core import (  # noqa: E402
    core_of, key_of, load_dir, rebuild)
from evaluation.scripts.mcq.preparation.rewrite_distractors_gold72_en import (  # noqa: E402
    LETTERS)


def quotas(n: int, labels=LETTERS) -> dict:
    """As flat as the count allows: the remainder goes to the earliest letters."""
    k = len(labels)
    return {L: n // k + (1 if i < n % k else 0) for i, L in enumerate(labels)}


def assign_targets(current: dict, seed: str = "keybalance", labels=LETTERS) -> dict:
    """content_id -> target key letter. Minimum churn, deterministic.

    Pass 1 keeps an item where it is while that letter still has quota. The ids are walked
    in a SEEDED SHUFFLE of sorted order, not sorted order itself: sorted order made the
    over-quota items the ones that sort last, which put all eight of gold72's moves inside
    t1_judg9 and skewed that passage's key distribution while flattening the global one.
    Pass 2 hands the leftover letters to the leftover items, also shuffled.
    """
    q = quotas(len(current), labels)
    rng0 = random.Random(f"{seed}:order:{len(current)}")
    ids = sorted(current)
    rng0.shuffle(ids)
    out, leftover = {}, []
    for cid in ids:
        L = current[cid]
        if q.get(L, 0) > 0:
            out[cid] = L
            q[L] -= 1
        else:
            leftover.append(cid)
    pool = [L for L, c in q.items() for _ in range(c)]
    rng = random.Random(f"{seed}:{len(current)}")
    rng.shuffle(pool)
    rng.shuffle(leftover)
    for cid, L in zip(leftover, pool):          # both already shuffled
        out[cid] = L
    for cid in leftover:                      # belt and braces: nothing may be dropped
        assert cid in out, cid
    return out


def rotated_core(core, from_letter, to_letter, labels=LETTERS):
    """Rotate so the key text moves from `from_letter` to `to_letter`.

    A cyclic rotation is the least invasive permutation that does the job: distractors
    keep their relative order, so nothing about the item changes except where the key sits.
    """
    n = len(core)
    c, t = labels.index(from_letter), labels.index(to_letter)
    k = (c - t) % n
    return [core[(j + k) % n] for j in range(n)]


def rebalance(dirs, seed="keybalance", dry_run=False):
    loaded = {d: load_dir(d) for d in dirs}
    ref = loaded[dirs[0]]
    current = {cid: key_of(it["mcq"]) for cid, (_, it) in ref.items()}
    before = collections.Counter(current.values())
    targets = assign_targets(current, seed)
    after = collections.Counter(targets.values())
    moved = [c for c in targets if targets[c] != current[c]]

    n = len(current)
    fmt = lambda c: "  ".join(f"{L} {c[L]:3d} ({c[L]/n:.0%})" for L in LETTERS)
    print(f"items: {n}")
    print(f"  key letters before : {fmt(before)}")
    print(f"  key letters after  : {fmt(after)}")
    print(f"  items whose key moves: {len(moved)} ({len(moved)/n:.0%})")
    # Churn concentrated in one passage would flatten the global distribution while
    # skewing a passage's -- which matters for any per-passage analysis.
    bypass = collections.Counter(c.split(":")[0] for c in moved)
    print(f"  spread of those moves: "
          + ", ".join(f"{p}:{k}" for p, k in sorted(bypass.items())))
    print(f"  a letter-only answerer now scores "
          f"{min(after[L] for L in LETTERS)/n:.3f}-{max(after[L] for L in LETTERS)/n:.3f} "
          f"instead of {min(before[L] for L in LETTERS)/n:.3f}-"
          f"{max(before[L] for L in LETTERS)/n:.3f}")
    if dry_run:
        for c in sorted(moved)[:10]:
            print(f"    would move {c}: {current[c]} -> {targets[c]}")
        if len(moved) > 10:
            print(f"    ... and {len(moved) - 10} more")
        return 0

    total = 0
    for d in dirs:
        idx = loaded[d]
        touched = {}
        changed = 0
        for cid, target in targets.items():
            if cid not in idx:
                continue
            fn, it = idx[cid]
            mcq = it["mcq"]
            cur = key_of(mcq)
            if cur == target:
                continue
            core = core_of(mcq)
            key_text_before = core[LETTERS.index(cur)]
            new_core = rotated_core(core, cur, target)
            assert new_core[LETTERS.index(target)] == key_text_before, \
                f"{cid}: the key text moved"
            assert sorted(new_core) == sorted(core), f"{cid}: options were lost"
            rebuild(mcq, new_core, target)
            touched[fn] = True
            changed += 1
        for fn in touched:
            p = os.path.join(d, fn)
            # Its own backup name: propagate_core.py already owns ".bak", and reusing it
            # would mean the only surviving copy is two generations old.
            if not os.path.exists(p + ".prekey.bak"):
                shutil.copy(p, p + ".prekey.bak")
            items = json.load(open(p))
            by_cid = {str(i.get("content_id") or ""): i for i in items}
            for cid in targets:
                if cid in idx and idx[cid][0] == fn and cid in by_cid:
                    by_cid[cid]["mcq"] = idx[cid][1]["mcq"]
            json.dump(items, open(p, "w"), ensure_ascii=False, indent=2)
        print(f"  {d}: {changed} item(s) re-keyed")
        total += changed
    print(f"\nre-keyed {total} item(s) across {len(dirs)} director(ies); "
          f"originals backed up alongside as .prekey.bak")
    return 0


def self_test():
    ok = []
    ok.append(("quotas are as flat as the count allows",
               quotas(71) == {"A": 18, "B": 18, "C": 18, "D": 17}
               and quotas(72) == {"A": 18, "B": 18, "C": 18, "D": 18}
               and sum(quotas(71).values()) == 71))

    cur = {}
    for i in range(19): cur[f"a{i:02d}"] = "A"
    for i in range(28): cur[f"b{i:02d}"] = "B"
    for i in range(22): cur[f"c{i:02d}"] = "C"
    for i in range(31): cur[f"d{i:02d}"] = "D"          # gold72's actual 19/28/22/31 shape
    t = assign_targets(cur)
    got = collections.Counter(t.values())
    ok.append((f"the real 19/28/22/31 shape flattens to {dict(sorted(got.items()))}",
               got == collections.Counter(quotas(len(cur)))))
    ok.append(("every item gets exactly one target", set(t) == set(cur)))
    kept = sum(1 for c in cur if t[c] == cur[c])
    ok.append((f"minimum churn: {kept} of {len(cur)} items keep their key letter",
               kept == sum(min(collections.Counter(cur.values())[L], quotas(len(cur))[L])
                           for L in LETTERS)))
    ok.append(("assignment is deterministic", assign_targets(cur) == t))
    ok.append(("a different seed gives a different assignment",
               assign_targets(cur, seed="other") != t))

    core = ["w", "x", "y", "z"]
    for frm in LETTERS:
        for to in LETTERS:
            nc = rotated_core(core, frm, to)
            ok.append((f"rotation moves the key {frm}->{to} and keeps the text",
                       nc[LETTERS.index(to)] == core[LETTERS.index(frm)]
                       and sorted(nc) == sorted(core)))
    ok.append(("rotation is the identity when nothing moves",
               rotated_core(core, "C", "C") == core))
    ok.append(("rotation preserves the distractors' relative order",
               rotated_core(core, "A", "B") == ["z", "w", "x", "y"]))

    bad = 0
    for name, cond in ok:
        if not cond:
            print(f"  [FAIL] {name}")
            bad += 1
    shown = [n for n, c in ok if c][:8]
    for n in shown:
        print(f"  [PASS] {n}")
    print(f"  [PASS] ... and {len(ok) - bad - len(shown)} more")
    print(f"\n{len(ok) - bad}/{len(ok)} self-tests passed")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", dest="dirs", action="append", default=[],
                    help="QA dir to re-key; repeatable. The FIRST one defines the "
                         "assignment, and it is applied by content_id to the rest so the "
                         "option-count variants stay in lockstep.")
    ap.add_argument("--seed", default="keybalance")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.dirs:
        ap.error("at least one --dir is required")
    return rebalance(a.dirs, a.seed, a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
