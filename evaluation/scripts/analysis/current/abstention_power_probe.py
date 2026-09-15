#!/usr/bin/env python3
"""Did the meta-options fire often enough to be worth analysing?

Run this on a SMALL probe before committing to a long campaign. It answers one question:
given the rate at which E ("I can't tell from this passage") and F ("None of the above")
actually fire, how many events will the planned design produce per cell, and what size of
difference could that detect?

Background. With a single meta-option, abstention fired at 6.6% at omission 30% -- 14
events in 213 observations. Split two ways across E and F, and with one answer model
instead of three, the per-cell event count can fall into single digits, where a
family x option interaction is not testable at all. A rate is cheap to measure and
expensive to assume.

Detection matches compare_meta_options.py: the choice MAPPER returns None when it cannot
map a reply to a permitted letter, and in the 2026-09-11 run all 18 Nones were the model
quoting option E's text verbatim. Reading selected_choice alone reported 0% abstention for
a run that abstained 18 times, so the answer TEXT is checked too.

  python3 .../abstention_power_probe.py <run-root> [--items 71] [--cells 4]
  python3 .../abstention_power_probe.py --self-test
"""
from __future__ import annotations

import argparse, glob, json, math, os, sys
from collections import Counter, defaultdict

ABSTAIN_ZH = "根据这段文字无法判断"
NOTA_ZH = "以上都不是"
ABSTAIN_EN = "I can't tell from this passage"
NOTA_EN = "None of the above"


def wilson(k, n, z=1.959963985):
    """95% Wilson interval. Correct at the small counts this script exists to expose;
    the normal approximation gives negative lower bounds at k=1, n=70."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def detectable_delta(n_per_cell, baseline, power=0.80, alpha=0.05):
    """Smallest rise above `baseline` a two-proportion test would catch at this n.

    Searched rather than solved because the closed form has p2 on both sides.
    """
    if n_per_cell <= 0:
        return float("nan")
    za, zb = 1.959963985, 0.8416212336
    p1 = baseline
    for step in range(1, 20001):
        p2 = min(0.999, p1 + step / 20000.0)
        pbar = (p1 + p2) / 2
        need = ((za * math.sqrt(2 * pbar * (1 - pbar))
                 + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2) / ((p2 - p1) ** 2)
        if need <= n_per_cell:
            return p2 - p1
    return float("nan")


def classify(item):
    """-> 'abstain' | 'nota' | 'content' | 'none'. Text is checked as well as the letter."""
    sel = (item.get("selected_choice") or "").strip().upper()
    text = " ".join(str(item.get(k) or "") for k in
                    ("generated_answer", "selected_choice_text", "generated_answer_english"))
    if any(t and t in text for t in (ABSTAIN_ZH, ABSTAIN_EN)):
        return "abstain"
    if any(t and t in text for t in (NOTA_ZH, NOTA_EN)):
        return "nota"
    ab = (os.environ.get("MCQ_ABSTAIN_LABEL") or "E").strip().upper()
    no = (os.environ.get("MCQ_NOTA_LABEL") or "F").strip().upper()
    if sel == ab:
        return "abstain"
    if sel == no:
        return "nota"
    if sel:
        return "content"
    return "none"


def scan(root):
    by = defaultdict(Counter)
    files = 0
    for fp in glob.glob(os.path.join(root, "*", "*", "*", "*",
                                     "generated_answers_target_llama.json")):
        parts = fp.split(os.sep)
        model, family, dose = parts[-4], parts[-3], parts[-2]   # root/pid/model/family/dose
        try:
            data = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        files += 1
        for it in data if isinstance(data, list) else []:
            if it.get("q_type") != "mcq":
                continue
            by[(model, family, dose)][classify(it)] += 1
    return by, files


def report(root, items, cells):
    by, files = scan(root)
    if not by:
        print(f"no MCQ answers found under {root}", file=sys.stderr)
        return 1
    print(f"scanned {files} answer file(s) under {root}\n")
    print(f"{'model':16} {'family':15} {'dose':6} {'n':>5} "
          f"{'E abstain':>18} {'F nota':>18} {'unmapped':>9}")
    per_dose = defaultdict(Counter)
    for key in sorted(by):
        model, family, dose = key
        c = by[key]
        n = sum(c.values())
        per_dose[dose] += c
        e, f = c["abstain"], c["nota"]
        el, eh = wilson(e, n)
        fl, fh = wilson(f, n)
        print(f"{model:16} {family:15} {dose:6} {n:5d} "
              f"{f'{e:3d} {e/n:5.1%} [{el:.1%},{eh:.1%}]':>18} "
              f"{f'{f:3d} {f/n:5.1%} [{fl:.1%},{fh:.1%}]':>18} {c['none']:9d}")

    print("\npooled by dose")
    for dose in sorted(per_dose):
        c = per_dose[dose]
        n = sum(c.values())
        e, f = c["abstain"], c["nota"]
        el, eh = wilson(e, n)
        print(f"  {dose:6} n={n:5d}  E {e:4d} ({e/n:.1%}) 95% CI [{el:.1%}, {eh:.1%}]"
              f"   F {f:4d} ({f/n:.1%})   meta total {(e+f)/n:.1%}")

    hi = max(per_dose, key=lambda d: (per_dose[d]["abstain"] + per_dose[d]["nota"])
             / max(1, sum(per_dose[d].values())))
    c = per_dose[hi]
    n = sum(c.values())
    rate_e = c["abstain"] / n if n else 0.0
    rate_f = c["nota"] / n if n else 0.0
    print(f"\nhighest-firing dose: {hi}  (E {rate_e:.1%}, F {rate_f:.1%})")
    print(f"\nPROJECTION onto a design of {items} items x {cells} cell(s) per comparison")
    per = items
    print(f"  observations per cell : {per}")
    for name, r in (("E", rate_e), ("F", rate_f)):
        ev = per * r
        print(f"  expected {name} events/cell : {ev:.1f}")
        if ev < 5:
            print(f"     -> below 5. A proportion test on {name} is not meaningful here; "
                  f"report raw counts or pool cells.")
    base = rate_e
    d = detectable_delta(per, base)
    if math.isfinite(d):
        print(f"  at n={per}/cell and a {base:.1%} baseline, the smallest rise detectable "
              f"at 80% power is +{d:.1%} (i.e. {base:.1%} -> {base + d:.1%})")
    else:
        print(f"  at n={per}/cell no rise above {base:.1%} is detectable at 80% power")
    need = None
    for m in range(1, 200):
        if detectable_delta(per * m, base) and detectable_delta(per * m, base) <= 0.05:
            need = m
            break
    if need:
        print(f"  to detect a +5 point rise you need ~{need}x that, i.e. "
              f"~{per * need} observations per cell "
              f"({need} model-arms, or {need} passages' worth of extra items)")
    return 0


def self_test():
    ok = []
    ok.append(("wilson is sane at a normal count", 
               all(0 < x < 1 for x in wilson(14, 213))))
    lo, hi = wilson(14, 213)
    ok.append((f"wilson(14/213) = [{lo:.3f}, {hi:.3f}] brackets the measured 6.6%",
               lo < 14 / 213 < hi))
    ok.append(("wilson never goes negative at k=1 (where the normal approx does)",
               wilson(1, 70)[0] >= 0))
    ok.append(("wilson at k=0 has a zero lower bound and a positive upper",
               wilson(0, 100)[0] == 0 and wilson(0, 100)[1] > 0))
    ok.append(("n=0 is not a crash", all(math.isnan(x) for x in wilson(0, 0))))
    d_small = detectable_delta(71, 0.066)
    d_big = detectable_delta(710, 0.066)
    ok.append((f"more observations detect a smaller rise ({d_small:.1%} vs {d_big:.1%})",
               d_big < d_small))
    ok.append(("detectable delta is undefined at n=0",
               math.isnan(detectable_delta(0, 0.066))))
    ok.append(("abstention is caught from the TEXT even when the letter is missing",
               classify({"q_type": "mcq", "selected_choice": None,
                         "generated_answer": ABSTAIN_ZH}) == "abstain"))
    ok.append(("none-of-the-above is caught from the text",
               classify({"selected_choice": "", "generated_answer": NOTA_ZH}) == "nota"))
    ok.append(("a letter is used when there is no telltale text",
               classify({"selected_choice": "E", "generated_answer": "甲"}) == "abstain"
               and classify({"selected_choice": "F", "generated_answer": "甲"}) == "nota"))
    ok.append(("a content answer is content",
               classify({"selected_choice": "B", "generated_answer": "乙"}) == "content"))
    ok.append(("an unmappable empty answer is counted separately, not as content",
               classify({"selected_choice": None, "generated_answer": ""}) == "none"))
    bad = 0
    for name, cond in ok:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        bad += not cond
    print(f"\n{len(ok) - bad}/{len(ok)} self-tests passed")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", help="run output root")
    ap.add_argument("--items", type=int, default=71,
                    help="items per cell in the design you are planning")
    ap.add_argument("--cells", type=int, default=4,
                    help="cells the comparison needs (e.g. 2 families x 2 options)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.root:
        ap.error("a run root is required")
    return report(a.root, a.items, a.cells)


if __name__ == "__main__":
    raise SystemExit(main())
