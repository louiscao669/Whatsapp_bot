#!/usr/bin/env python3
"""Stage a 4-option twin of the unblinded 5-option tier-1 arm.

Why: comparing thinking cost at 4 vs 5 options needs the two arms to differ ONLY in
the option count. Re-translating a 4-option QA set would also change the Chinese
wording (measured: only 13/28 questions matched between two translation runs), so
instead this copies the 5-option cells and drops the E choice from every MCQ.
Everything else -- passages, question wording, A-D texts, keys -- is byte-identical.

Copies the pilot conditions only (the defect cells the 5-option arm was answered on).

  python3 evaluation/scripts/variants/maintenance/make_4opt_arm_from_5opt.py [--conditions ...]
"""
import argparse, json, shutil
from pathlib import Path

SRC = Path("evaluation/outputs/tier1_bsb_unblinded_5opt_think")
DST = Path("evaluation/outputs/tier1_bsb_unblinded_4opt_think")
QA_FILES = ("qa_target.json", "qa_target_decanonicalized.json")


def drop_e(path: Path) -> int:
    records = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for record in records:
        choices = record.get("A")
        if isinstance(choices, dict) and "E" in choices:
            choices.pop("E")
            n += 1
        if str(record.get("correct", "")).strip().upper() == "E":
            raise SystemExit(f"{path}: an item is keyed on E; cannot drop it")
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--dst", type=Path, default=DST)
    ap.add_argument("--conditions", nargs="+",
                    default=["omission/0%", "omission/30%", "mistranslation/30%", "grammar/30%"])
    args = ap.parse_args()

    passages = sorted(p for p in args.src.glob("t1_*") if p.is_dir())
    if not passages:
        raise SystemExit(f"no passages under {args.src}")
    total = 0
    for passage in passages:
        out = args.dst / passage.name
        shared_src, shared_dst = passage / "_base" / "_shared", out / "_base" / "_shared"
        shared_dst.mkdir(parents=True, exist_ok=True)
        for f in shared_src.glob("*_qa_zh*.json"):
            shutil.copy2(f, shared_dst / f.name)
            total += drop_e(shared_dst / f.name)
        for cond in args.conditions:
            src_cell, dst_cell = passage / cond, out / cond
            if not src_cell.is_dir():
                print(f"  [warn] missing {src_cell}")
                continue
            dst_cell.mkdir(parents=True, exist_ok=True)
            for f in src_cell.iterdir():
                if f.is_file() and not f.name.startswith(("generated_answers", "scores")):
                    shutil.copy2(f, dst_cell / f.name)
            for name in QA_FILES:
                if (dst_cell / name).exists():
                    total += drop_e(dst_cell / name)
        print(f"  {passage.name}: staged {len(args.conditions)} condition(s)")
    print(f"\n{args.dst}: E dropped from {total} MCQ records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
