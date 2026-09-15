#!/usr/bin/env python3
"""Score abstention-probe arms BY ROLE, and contrast two arms on correctness.

Why this exists rather than --compare: that instrument was built for thinking off vs on
and reports the rate of LETTER E. These arms swap which letter carries which meaning
(--abstain F --nota E puts none-of-the-above first in the option list), so a letter rate
is meaningless across them. Everything here is keyed to the ROLE -- abstain, nota, content
-- which every row now records as abstain_letter/nota_letter.

The second reason: a wording change that makes abstaining harder will improve the arm where
nota is correct AND damage the arm where abstain is correct. Reading one side alone buys a
trade and calls it a fix. So correctness against `expected` is the headline number here, and
the campaign runs both controls.

  python3 score_meta_arms.py FILE [FILE ...]          per-arm table
  python3 score_meta_arms.py --contrast BEFORE AFTER  paired McNemar on correctness
  python3 score_meta_arms.py --self-test
"""
import json
import sys
from collections import Counter
from math import comb


def roles(row):
    # Rows written before the label sets existed had abstain=E, nota=F by construction.
    return row.get("abstain_letter") or "E", row.get("nota_letter") or "F"


def expected_of(row):
    """The letter that is correct for this row, by construction of its condition.

    A stored `expected` is trusted EXCEPT when it names a letter the run never showed --
    which is what a five-option run written before 2026-09-14 does: the loader stamped
    expected="F" from an `or "F"` fallback, and every corrupted row then scored wrong
    whatever the model chose. Repaired here rather than only at the source, so the runs
    already on disk stay readable.
    """
    ab, nota = roles(row)
    stored = row.get("expected")
    if stored and not ("nota_letter" in row and not row["nota_letter"]
                       and stored != ab and stored not in "ABCD"):
        return stored
    cond = row.get("condition")
    if cond == "redacted":          # the keyed verse was removed: the passage is silent
        return ab
    if cond == "corrupted":         # the passage answers, but no content option says it
        # With one hatch that same hatch is correct here too: it asserts only that no
        # content option is supported, which is true in both conditions. "nota off" has
        # to be read as the FIELD being present and empty -- a row written before these
        # fields existed has neither, and was a six-option run with nota on F.
        nota_off = "nota_letter" in row and not row["nota_letter"]
        return ab if nota_off else nota
    if cond in ("full", "intact"):  # untouched passage: the key is present and listed
        return row.get("key")
    if cond == "dose_0%":           # the undamaged base translation, same as intact
        return row.get("key")
    return None                     # a dosed passage may or may not still answer, so
                                    # there is no single defensible letter to score


def summarize(rows):
    by = {}
    for r in rows:
        by.setdefault(r["condition"], []).append(r)
    out = []
    for cond in sorted(by):
        rs = by[cond]
        n = len(rs)
        exp = [expected_of(r) for r in rs]
        scored = [(r, e) for r, e in zip(rs, exp) if e]
        correct = sum(1 for r, e in scored if r["choice"] == e)
        ab_n = sum(1 for r in rs if r["choice"] == roles(r)[0])
        nota_n = sum(1 for r in rs if r["choice"] == roles(r)[1])
        out.append({
            "condition": cond, "n": n,
            "scored": len(scored),
            "correct": correct,
            "acc": correct / len(scored) if scored else None,
            "abstain": ab_n, "abstain_rate": ab_n / n,
            "nota": nota_n, "nota_rate": nota_n / n,
            "content": n - ab_n - nota_n,
            "expected_role": Counter(
                "abstain" if e == roles(r)[0] else "nota" if e == roles(r)[1] else "content"
                for r, e in scored).most_common(1)[0][0] if scored else "-",
        })
    return out


def mcnemar(b, c):
    """Exact two-sided binomial test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def print_arm(path, rows):
    print(f"\n{path}")
    meta = {(r.get("meta_labels"), r.get("meta_wording"),
             r.get("abstain_letter"), r.get("nota_letter")) for r in rows}
    for labels, wording, ab, nota in sorted(meta, key=str):
        # Printing a default letter for a hatch that is OFF invites exactly the misreading
        # it caused on 2026-09-14: an arm showing "nota=F" in a five-option run where F was
        # never on screen.
        print(f"  labels={labels or 'current'} wording={wording} "
              f"abstain={ab or 'E'} nota={nota or 'OFF'}")
    print(f"  {'condition':11} {'n':>4} {'correct':>13}  {'abstain':>13} {'nota':>13}"
          f"  correct role")
    for s in summarize(rows):
        acc = f"{s['correct']:3d} {s['acc']:6.1%}" if s["acc"] is not None else "      n/a"
        print(f"  {s['condition']:11} {s['n']:>4} {acc:>13}  "
              f"{s['abstain']:3d} {s['abstain_rate']:6.1%}  "
              f"{s['nota']:3d} {s['nota_rate']:6.1%}  {s['expected_role']}")


def contrast(path_a, path_b):
    A = {(r["cid"], r["condition"]): r for r in json.load(open(path_a, encoding="utf-8"))}
    B = {(r["cid"], r["condition"]): r for r in json.load(open(path_b, encoding="utf-8"))}
    keys = sorted(set(A) & set(B))
    print("=" * 78)
    print(f"BEFORE  {path_a}")
    print(f"AFTER   {path_b}")
    print(f"paired on {len(keys)} (item, condition) pair(s)")
    if not keys:
        print("  nothing in common -- different item sets?")
        return 1
    for cond in sorted({k[1] for k in keys}):
        ks = [k for k in keys if k[1] == cond]
        ea = {k: expected_of(A[k]) for k in ks}
        if not any(ea.values()):
            continue
        ca = [k for k in ks if ea[k] and A[k]["choice"] == ea[k]]
        cb = [k for k in ks if expected_of(B[k]) and B[k]["choice"] == expected_of(B[k])]
        gained = sum(1 for k in ks if k in set(cb) and k not in set(ca))
        lost = sum(1 for k in ks if k in set(ca) and k not in set(cb))
        n = len(ks)
        print(f"\n{cond.upper():10} n={n}   correct role: "
              f"{summarize([A[k] for k in ks])[0]['expected_role']}")
        print(f"  correct   before {len(ca):3d} {len(ca)/n:6.1%}"
              f"   after {len(cb):3d} {len(cb)/n:6.1%}")
        print(f"  changed   gained {gained}, lost {lost}   "
              f"McNemar exact p = {mcnemar(gained, lost):.4f}")
        for role, idx in (("abstain", 0), ("nota", 1)):
            ra = sum(1 for k in ks if A[k]["choice"] == roles(A[k])[idx])
            rb = sum(1 for k in ks if B[k]["choice"] == roles(B[k])[idx])
            print(f"  {role:8}  before {ra:3d} {ra/n:6.1%}   after {rb:3d} {rb/n:6.1%}")
    return 0


def self_test():
    ok = []
    row = {"cid": "x", "condition": "corrupted", "key": "A", "choice": "E",
           "abstain_letter": "F", "nota_letter": "E"}
    ok.append(("expected follows the ROLE, not the letter", expected_of(row) == "E"))
    ok.append(("a swapped arm scores E as CORRECT when E carries nota",
               summarize([row])[0]["correct"] == 1))
    old = {"cid": "x", "condition": "corrupted", "key": "A", "choice": "E"}
    ok.append(("a row written before the swap existed still means abstain=E",
               expected_of(old) == "F" and summarize([old])[0]["correct"] == 0))
    one = {"cid": "z", "condition": "corrupted", "key": "A", "choice": "E",
           "abstain_letter": "E", "nota_letter": None}
    ok.append(("with ONE hatch, that hatch is correct in the corrupted condition too",
               expected_of(one) == "E" and summarize([one])[0]["correct"] == 1))
    ok.append(("a legacy row has no nota_letter field and still expects F, not E",
               expected_of({"cid": "w", "condition": "corrupted", "key": "A"}) == "F"))
    red = {"cid": "y", "condition": "redacted", "key": "A", "choice": "E"}
    ok.append(("redaction makes the abstain role correct", expected_of(red) == "E"))
    full = {"cid": "y", "condition": "full", "key": "C", "choice": "C"}
    ok.append(("an untouched passage expects its key", expected_of(full) == "C"))
    zero = {"cid": "y", "condition": "dose_0%", "key": "C", "choice": "C"}
    ok.append(("an undamaged dose cell is scored against the key",
               expected_of(zero) == "C" and summarize([zero])[0]["acc"] == 1.0))
    dose = {"cid": "y", "condition": "dose_30%", "key": "C", "choice": "E"}
    ok.append(("a dose condition has no expected letter and is not scored",
               expected_of(dose) is None and summarize([dose])[0]["acc"] is None))
    ok.append(("an explicit expected field wins over the fallback",
               expected_of({"condition": "redacted", "expected": "B"}) == "B"))
    stale = {"cid": "v", "condition": "corrupted", "key": "C", "choice": "E",
             "abstain_letter": "E", "nota_letter": None, "expected": "F"}
    ok.append(("a stored expected naming a letter the run never showed is repaired",
               expected_of(stale) == "E" and summarize([stale])[0]["correct"] == 1))
    ok.append(("a stored expected naming a CONTENT letter is still trusted",
               expected_of({"cid": "u", "condition": "intact", "key": "C",
                            "abstain_letter": "E", "nota_letter": None,
                            "expected": "C"}) == "C"))
    ok.append(("mcnemar: all-gain is significant, a tie is not",
               mcnemar(10, 0) < 0.01 and mcnemar(5, 5) == 1.0))
    ok.append(("mcnemar: no discordant pairs means p=1", mcnemar(0, 0) == 1.0))
    bad = [n for n, good in ok if not good]
    for n, good in ok:
        print(("  [PASS] " if good else "  [FAIL] ") + n)
    print(f"\n{len(ok) - len(bad)}/{len(ok)} self-tests passed")
    return 1 if bad else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    if "--contrast" in argv:
        i = argv.index("--contrast")
        return contrast(argv[i + 1], argv[i + 2])
    if not argv:
        print(__doc__)
        return 2
    for path in argv:
        print_arm(path, json.load(open(path, encoding="utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
