#!/usr/bin/env python3
"""One row per QA item, joining everything measured about it into a single table.

Every analysis in this project so far has reported per-CONDITION aggregates -- accuracy at
dose 0%, abstention at 30%, dead-distractor rate. Those hide stratification. The clearest
case: high-overlap items looked far more dose-sensitive (accuracy drop 50% vs 18%) until
the numbers were conditioned on being correct in the first place, at which point the
difference vanished (46% vs 45% of correct items lost). A per-item table makes that kind of
confound visible instead of accidental.

MEASURES, defined exactly.

  zh_overlap    Fraction of the CHINESE key option's 2-character sequences that also occur
                in its Chinese window. Bigrams, not single characters: individual Chinese
                characters are far too common to mean anything (的, 他, 是 match everywhere).
                Computed on the undamaged (0%) window. Range 0-1, None if the option has no
                CJK bigrams.
  en_overlap    Same idea on the English side: fraction of the English key option's tokens
                of 4+ letters that occur in the English BSB window. The 4-letter floor
                drops function words. These two are NOT comparable in absolute value -- the
                tokenisations differ -- only within a column.
  (required_keywords is deliberately NOT carried here. It is legacy scoring machinery,
   and as a window-adequacy signal it is unusable: the lists mix function words with
   non-BSB lemmas, so a miss can mean the keyword is wrong rather than the window thin.)
  window_verses / verses_present_30
                How many verses the window names, and how many still carry text at omission
                30%. Omission deletes whole verses as well as truncating them, so the
                difference is how much evidence that item actually lost.
  column names  <arm>_<condition>_<measure>, where the condition carries the DEFECT FAMILY:
                on_omission_30%_correct, not on_dose_30%_correct. "30%" alone does not say
                30% of what, and the families damage a passage in opposite ways -- omission
                deletes the answer (E's case), mistranslation replaces it (F's case). Naming
                them apart also lets a mistranslation run add columns to this same table
                instead of colliding with the omission ones.
  correct_*     selected_choice == the item's keyed letter, per arm and condition.
  abstained_*   selected_choice == E.   nota_*  selected_choice == F.
  survived_dose correct at 0% AND still correct at 30%. Only defined for items correct at
                0%, because an item that was already wrong cannot lose anything -- this is
                the floor-free version of dose sensitivity.
  beaten_key, keyrate, dead_distractors
                From the 2026-09-12 behavioural audit, over ~159 pooled observations. Those
                pooled observations are ~4 deterministic decisions replicated, so keyrate is
                a coarse measure; `beaten` in particular was shown to select for key=D.
  placeholder   A __NAME__ placeholder leaked into the Chinese text of this item.

    python3 .../build_item_metadata.py            # writes CSV + JSON
    python3 .../build_item_metadata.py --self-test
"""
from __future__ import annotations
import argparse, csv, json, glob, os, re, sys

REPO = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(REPO, "evaluation")):
        break
    REPO = os.path.dirname(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "evaluation/scripts/mcq/diagnostics"))

CJK = lambda c: "一" <= c <= "鿿"


def zh_overlap(option: str, window: str):
    """Fraction of the option's CJK bigrams present in the window."""
    grams = {option[i:i + 2] for i in range(len(option) - 1)
             if CJK(option[i]) and CJK(option[i + 1])}
    return (sum(1 for g in grams if g in window) / len(grams)) if grams else None


def en_overlap(option: str, window: str):
    """Fraction of the option's 4+ letter tokens present in the window."""
    toks = {w for w in re.findall(r"[a-z']{4,}", (option or "").lower())}
    if not toks:
        return None
    wtok = set(re.findall(r"[a-z']{4,}", (window or "").lower()))
    return sum(1 for t in toks if t in wtok) / len(toks)


def build(args):
    from abstention_thinking_probe import load_dose_items, parse_ref_span
    from evaluation.scripts.mcq.preparation.rewrite_distractors_gold72_en import (
        PASSAGE_FILE, parse_passage)

    W = json.load(open(args.windows, encoding="utf-8"))
    wins = {str(w.get("content_id") or ""): w for w in W["windows"]}
    ENG = {}
    for p, stem in PASSAGE_FILE.items():
        try:
            ENG[p] = parse_passage(stem, args.passage_dir)
        except Exception:
            ENG[p] = {}

    rows = {}
    for fp in sorted(glob.glob(os.path.join(args.qa_dir, "*.json"))):
        for it in json.load(open(fp, encoding="utf-8")):
            m = it.get("mcq")
            if not m:
                continue
            cid = str(it.get("content_id") or "")
            key = m["content"].split("<answer>")[1] if "<answer>" in m["content"] else None
            opts = m.get("mcq_options") or []
            rows[cid] = {
                "content_id": cid, "passage_id": cid.split(":")[0], "id": it.get("id"),
                "reference": it.get("reference"), "stem_en": m.get("mcq_stem"),
                "key_letter": key,
                "key_en": opts["ABCDEF".index(key)] if key and key in "ABCDEF" else None,
                "n_options": len(opts),
            }

    # windows: English text, span, chapter straddle
    for cid, r in rows.items():
        w = wins.get(cid)
        if not w:
            continue
        pid = r["passage_id"]
        base = int(re.match(r"^[0-9]?[a-z]+_(\d+)_", PASSAGE_FILE[pid]).group(1))
        refs = [x for v in w["window"] for x in parse_ref_span(v, base)]
        etxt = " ".join(ENG.get(pid, {}).get(x, "") for x in refs)
        r["window"] = ";".join(str(v) for v in w["window"])
        r["window_verses"] = len(refs)
        r["window_straddles_chapter"] = int(len({c for c, _ in refs}) > 1)
        r["en_overlap"] = en_overlap(r["key_en"], etxt)

    # Chinese side + dose survival, from the answered run
    items, _ = load_dose_items(args.run_root, args.windows, ["0%", "30%"], 0, "omission")
    for i in items:
        r = rows.get(i["cid"])
        if not r:
            continue
        keyzh = i["choices"].get(i["correct"], "")
        r["key_zh"] = keyzh
        r["zh_overlap"] = zh_overlap(keyzh, i["windows"]["dose_0%"])
        r["verses_present_0"] = i["verses_present"]["dose_0%"]
        r["verses_present_30"] = i["verses_present"]["dose_30%"]
        r["verses_lost_30"] = i["window_verses"] - i["verses_present"]["dose_30%"]
        r["placeholder_in_zh"] = int(bool(re.search(r"__[A-Z_]*[A-Z]__", keyzh)))

    # per-arm outcomes
    for arm, tag, defect in args.arms:
        p = os.path.join(args.run_dir, arm + ".json")
        if not os.path.exists(p):
            continue
        for x in json.load(open(p, encoding="utf-8")):
            r = rows.get(x["cid"])
            if not r:
                continue
            # Prefer the defect recorded on the row; fall back to the arm's declared one
            # for runs made before the probe started stamping it.
            c = x["condition"]
            if c.startswith("dose_"):
                c = f"{x.get('defect') or defect}_{c[len('dose_'):]}"
            r[f"{tag}_{c}_choice"] = x.get("choice")
            r[f"{tag}_{c}_correct"] = int(x.get("choice") == x.get("key"))
            r[f"{tag}_{c}_abstained"] = int(bool(x.get("abstained")))
            r[f"{tag}_{c}_nota"] = int(bool(x.get("nota")))
            r[f"{tag}_{c}_trace_chars"] = len(x.get("thinking") or "")

    # floor-free dose sensitivity
    for r in rows.values():
        c0, c3 = r.get("on_omission_0%_correct"), r.get("on_omission_30%_correct")
        r["survived_dose"] = (int(bool(c3)) if c0 else None) if c0 is not None else None

    # the 2026-09-12 behavioural audit
    if args.audit and os.path.exists(args.audit):
        for a in json.load(open(args.audit, encoding="utf-8")):
            r = next((v for v in rows.values() if v["id"] == a.get("id")), None)
            if r:
                r.update(keyrate=a.get("keyrate"), beaten_key=int(bool(a.get("beaten"))),
                         dead_distractors=a.get("dead"), top_distractor=a.get("topd"))

    # gate verdicts
    for path, tag in ((args.relevance, "relevance"), (args.falseness, "falseness")):
        if not path or not os.path.exists(path):
            continue
        for x in json.load(open(path, encoding="utf-8")):
            r = next((v for v in rows.values() if v["id"] == x.get("id")), None)
            g = x.get(tag) or {}
            if r and g:
                r[f"{tag}_failed"] = ",".join(g.get("failed") or [])
                r[f"{tag}_audited"] = int(bool(g.get("audited")))
    return rows


def write(rows, out_csv, out_json):
    cols = []
    for r in rows.values():
        for k in r:
            if k not in cols:
                cols.append(k)
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for cid in sorted(rows):
            w.writerow({k: ("" if rows[cid].get(k) is None else rows[cid].get(k))
                        for k in cols})
    json.dump([rows[c] for c in sorted(rows)], open(out_json, "w"),
              ensure_ascii=False, indent=1)
    return cols


def self_test():
    ok = []
    ok.append(("zh bigram overlap counts 2-char sequences",
               zh_overlap("按分派的队伍", "军队按分派的队伍出征") == 1.0))
    ok.append(("zh overlap is 0 when nothing matches",
               zh_overlap("按班次出征", "勇士家族的首领") == 0.0))
    ok.append(("zh overlap ignores non-CJK", zh_overlap("ABC", "任何") is None))
    ok.append(("single characters are NOT counted (too promiscuous)",
               zh_overlap("的", "的的的") is None))
    ok.append(("en overlap drops words under 4 letters",
               en_overlap("By assigned divisions.", "went out by assigned divisions") == 1.0))
    ok.append(("en overlap is case-insensitive",
               en_overlap("The Word Of Yahweh", "the word of yahweh came") == 1.0))
    ok.append(("en overlap 0 when disjoint",
               en_overlap("ambush soldiers", "the king spoke") == 0.0))
    bad = 0
    for n, c in ok:
        print(f"  [{'PASS' if c else 'FAIL'}] {n}")
        bad += not c
    print(f"\n{len(ok)-bad}/{len(ok)} self-tests passed")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qa-dir", default="evaluation/datasets/qa/tier1_gold72_canonical_5opt")
    ap.add_argument("--passage-dir", default="evaluation/datasets/passages/tier1_bsb")
    ap.add_argument("--windows",
                    default="QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json")
    ap.add_argument("--run-root", default="evaluation/outputs/tier1_bsb_unblinded_5opt")
    ap.add_argument("--run-dir",
                    default="evaluation/outputs/reports/abstention_overnight_20260913_015756")
    ap.add_argument("--audit", default=os.path.expanduser(
        "~/mnt/Bible Translation/GOLD72_DISTRACTOR_AUDIT_2026-09-12.json"))
    ap.add_argument("--relevance",
                    default="evaluation/outputs/reports/gold72_relevance_audit.json")
    ap.add_argument("--falseness",
                    default="evaluation/outputs/reports/gold72_falseness_audit.json")
    ap.add_argument("--out-csv", default="evaluation/outputs/reports/item_metadata.csv")
    ap.add_argument("--out-json", default="evaluation/outputs/reports/item_metadata.json")
    ap.add_argument("--defect", default="omission",
                    help="defect family the dose arms were run with; names the columns "
                         "(on_omission_30%% ...). Only used for runs predating the probe "
                         "stamping `defect` on each row.")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    a.arms = [("arm3_dose_think_off", "off", a.defect),
              ("arm4_dose_think_on", "on", a.defect),
              ("arm2_redact_think_on", "redact_on", a.defect)]
    rows = build(a)
    cols = write(rows, a.out_csv, a.out_json)
    print(f"{len(rows)} items x {len(cols)} columns")
    print(f"  {a.out_csv}\n  {a.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
