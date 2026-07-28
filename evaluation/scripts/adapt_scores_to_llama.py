#!/usr/bin/env python3
"""Tier 0.5 bridge: make the NEW window3_v2 results readable by the OLD analysis scripts.

Every downstream analysis (dose-response, anchor-IRT, item-sensitivity/tau, semireal p1-p5)
hardcodes scores_target_llama.json and reads fields the new scores_target_window3_v2.json
doesn't carry (item_index, question, standard_answer, ...). So rather than edit each script,
we OVERWRITE scores_target_llama.json using the OLD file as a TEMPLATE (which already has
item_index + all metadata) and inject only the fresh correctness values from window3_v2:
    mcq  -> direct_correct, selected_choice, correct_choice
    open -> llm_score, generated_answer
Items retired in the new set (174346/174388 mcq, 174382 open) are dropped. The summary
mcq_correct / open_llm_score_mean / counts are recomputed. The original file is backed up to
scores_target_llama.pre_v2.json (once); --restore reverts.

  python evaluation/scripts/adapt_scores_to_llama.py            # apply (backs up)
  python evaluation/scripts/adapt_scores_to_llama.py --dry-run
  python evaluation/scripts/adapt_scores_to_llama.py --restore
"""
import argparse, glob, json, os, shutil, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from regen_mcq_tier01 import item_stem, EXCLUDED_OPEN_STEMS   # same active-filter as the driver

BACKUP = "scores_target_llama.pre_v2.json"


def numeric(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def is_active(item, active_mcq, active_stems):
    iid = item.get("id") or item.get("passage_id") or ""
    st = item_stem(iid)
    if item.get("q_type") == "mcq":
        return iid in active_mcq
    return st in active_stems and st not in EXCLUDED_OPEN_STEMS


def adapt_cell(new_path, dry, active_mcq, active_stems):
    cell = new_path.parent
    old_path = cell / "scores_target_llama.json"
    if not old_path.exists():
        return "no_template"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    new_by_id = {it["id"]: it for it in json.loads(new_path.read_text(encoding="utf-8")).get("items", [])}

    kept, dropped, updated = [], 0, 0
    for item in old.get("items", []):
        nid = item.get("id") or item.get("passage_id")
        nw = new_by_id.get(nid)
        # drop if retired (absent from new) OR excluded by the driver's active-filter (e.g.
        # 174382-open, which lingers in the new file but should not enter analyses)
        if nw is None or not is_active(item, active_mcq, active_stems):
            dropped += 1
            continue
        if item.get("q_type") == "mcq":
            item["direct_correct"] = bool(nw.get("direct_correct"))
            item["selected_choice"] = nw.get("selected_choice")
            item["correct_choice"] = nw.get("correct_choice")
            if isinstance(item.get("core_claim"), dict):
                item["core_claim"].update({"direct_correct": item["direct_correct"],
                                           "selected_choice": item["selected_choice"],
                                           "correct_choice": item["correct_choice"]})
        else:
            item["llm_score"] = nw.get("llm_score")
            item["generated_answer"] = nw.get("generated_answer")
        updated += 1
        kept.append(item)
    old["items"] = kept

    mcq = [i for i in kept if i.get("q_type") == "mcq"]
    opn = [i for i in kept if i.get("q_type") != "mcq"]
    open_scores = [numeric(i.get("llm_score")) for i in opn if numeric(i.get("llm_score")) is not None]
    s = old.setdefault("summary", {})
    s.update({"total": len(kept), "mcq_count": len(mcq),
              "mcq_correct": sum(1 for i in mcq if i.get("direct_correct")),
              "open_count": len(opn),
              "open_llm_score_mean": (sum(open_scores) / len(open_scores)) if open_scores else None})

    if not dry:
        bak = cell / BACKUP
        if not bak.exists():
            shutil.copy2(old_path, bak)
        old_path.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"ok(updated={updated},dropped={dropped})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="evaluation/outputs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    news = sorted(glob.glob(f"{args.root}/luke*/**/scores_target_window3_v2.json", recursive=True))
    active_mcq = set(json.loads((Path(args.root).parent / "mcq_rewrites.json").read_text(encoding="utf-8")))
    active_stems = {item_stem(i) for i in active_mcq}

    if args.restore:
        n = 0
        for p in news:
            bak = Path(p).parent / BACKUP
            if bak.exists():
                shutil.copy2(bak, Path(p).parent / "scores_target_llama.json")
                n += 1
        print(f"restored {n} scores_target_llama.json from {BACKUP}")
        return

    stats = {"ok": 0, "no_template": 0}
    missing = []
    for p in news:
        r = adapt_cell(Path(p), args.dry_run, active_mcq, active_stems)
        if r == "no_template":
            stats["no_template"] += 1
            missing.append(str(Path(p).parent))
        else:
            stats["ok"] += 1
    print(f"{'(dry) ' if args.dry_run else ''}cells with window3_v2: {len(news)} | "
          f"adapted: {stats['ok']} | no old template (skipped): {stats['no_template']}")
    for m in missing[:10]:
        print("  no template:", m)
    print("\nDone -> scores_target_llama.json now holds the new results (old saved as "
          f"{BACKUP}). Downstream scripts (dose-response, anchor-IRT, tau) read it unchanged.")


if __name__ == "__main__":
    main()
