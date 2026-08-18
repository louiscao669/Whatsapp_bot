#!/usr/bin/env python3
"""Promote the hand-written MCQ distractor rewrites into the delivered qa_target files.

Reads mcq_rewrites.json  {passage_id: {A,B,C,D,correct}}  and patches every
qa_target_pseudonymized.json under evaluation/outputs/luke{1..8}/ : for each MCQ record
whose passage_id has a rewrite, it REPLACES the options (`A` dict) and the `correct` letter.
Duplicate ids (chapters 4 & 5 repeat some) are all patched. Each file is backed up to
<name>.bak once before writing.

  # preview, no writes
  python scripts/promote_mcq_rewrites.py --dry-run
  # apply (backs up each file to .bak)
  python scripts/promote_mcq_rewrites.py
  # only the delivered clean dir (omission/0%), leave LLM condition dirs untouched
  python scripts/promote_mcq_rewrites.py --clean-only
  # undo
  python scripts/promote_mcq_rewrites.py --restore
"""
import argparse
import glob
import json
import shutil
from pathlib import Path


def target_files(root, chapters, clean_only):
    files = []
    for ch in chapters:
        if clean_only:
            files += glob.glob(f"{root}/luke{ch}/*/omission/0%/qa_target_pseudonymized.json")
        else:
            files += glob.glob(f"{root}/luke{ch}/**/qa_target_pseudonymized.json", recursive=True)
    return sorted(set(files))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rewrites", default="evaluation/datasets/mcq/mcq_rewrites.json")
    ap.add_argument("--root", default="evaluation/outputs")
    ap.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    ap.add_argument("--clean-only", action="store_true",
                    help="patch only the delivered omission/0%% file per chapter")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", action="store_true", help="revert every file from its .bak")
    args = ap.parse_args()

    files = target_files(args.root, args.chapters, args.clean_only)

    if args.restore:
        n = 0
        for f in files:
            bak = f + ".bak"
            if Path(bak).exists():
                shutil.copy2(bak, f)
                n += 1
        print(f"restored {n} files from .bak")
        return

    rw = json.loads(Path(args.rewrites).read_text(encoding="utf-8"))
    total_files = total_recs = 0
    for f in files:
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        patched = 0
        for r in data:
            if r.get("q_type") != "mcq":
                continue
            nw = rw.get(r.get("passage_id"))
            if not nw:
                continue
            r["A"] = {L: nw[L] for L in "ABCD"}
            r["correct"] = nw["correct"]
            patched += 1
        if not patched:
            continue
        total_files += 1
        total_recs += patched
        if not args.dry_run:
            bak = f + ".bak"
            if not Path(bak).exists():
                shutil.copy2(f, bak)
            Path(f).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{'[dry] ' if args.dry_run else ''}{f}: {patched} mcq patched")
    print(f"\n{'(dry run) ' if args.dry_run else ''}patched {total_recs} mcq records "
          f"across {total_files} files")


if __name__ == "__main__":
    main()
