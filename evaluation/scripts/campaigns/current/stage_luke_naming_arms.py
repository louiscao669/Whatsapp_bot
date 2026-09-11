#!/usr/bin/env python3
"""Stage the Luke naming-condition arms for the blinding diagnostic.

Luke already carries THREE naming conditions in every variant cell, so no
re-translation is needed -- the arms differ only in which passage/QA the
answerer reads:

  decanon    passage_target_decanonicalized.txt   人物丙 / 角色02   (historical eval condition)
  pseudonym  passage_target_pseudonymized.txt     珂温 / 哈丽 / 米珥 (pilot delivery form)
  canonical  passage_target_backcanonicalized.txt 撒迦利亚 / 以利沙伯 (UNBLINDED)

answer_score_subset_in_place.py reads exactly two filenames from the method dir,
so each arm is staged by copying the cell and overwriting those two.

Everything else is held identical: same variant passages, same doses, same items,
same models, same window, same judge -- run all arms in one session at temp 0.
"""
import os, shutil, sys

def _outputs_root():
    """Resolve evaluation/outputs portably.

    Prefer EVAL_OUTPUTS_ROOT, then evaluation/outputs relative to the repo root
    (it is a symlink into eten-research-outputs), then the cwd. Never hardcode a
    machine-specific absolute path -- that silently yields an empty result set
    and reads as 'the run has not finished'.
    """
    import os as _os
    env = _os.environ.get("EVAL_OUTPUTS_ROOT")
    if env and _os.path.isdir(env):
        return env
    here = _os.path.dirname(_os.path.abspath(__file__))
    for _ in range(6):
        cand = _os.path.join(here, "evaluation", "outputs")
        if _os.path.isdir(cand):
            return cand
        here = _os.path.dirname(here)
    for cand in ("evaluation/outputs", "outputs", "."):
        if _os.path.isdir(cand):
            return cand
    raise SystemExit("cannot locate evaluation/outputs; set EVAL_OUTPUTS_ROOT")


R   = _outputs_root()
ARMS = {
    "decanon":   ("passage_target_decanonicalized.txt",   "qa_target_decanonicalized.json"),
    "pseudonym": ("passage_target_pseudonymized.txt",     "qa_target_pseudonymized.json"),
    "canonical": ("passage_target_backcanonicalized.txt", "qa_target.json"),
}
TIERS = ["1.7b", "1.5b", "llama 1b"]
CHAPTERS = [int(c) for c in (sys.argv[1].split(",") if len(sys.argv) > 1 else "1 2 3 4 5 6 7 8".split())]
DOSES = ["0%", "30%"]
# ARM_SUFFIX="_5opt" stages into naming_<arm>_5opt so the 4-option arms survive
SUFFIX = os.environ.get("ARM_SUFFIX", "")
DEFECT = "omission"
# files the answerer needs; deliberately excludes prior answers/scores
CARRY = ["passage_translation.json", "omission_metadata.json", "decanonicalized_metadata.json"]

made = skipped = 0
for arm, (psrc, qsrc) in ARMS.items():
    for ch in CHAPTERS:
        for dose in DOSES:
            src = os.path.join(R, f"luke{ch}", "1.7b", DEFECT, dose)
            if not os.path.isdir(src):
                print(f"  !! missing source {src}"); skipped += 1; continue
            for f in (psrc, qsrc):
                if not os.path.exists(os.path.join(src, f)):
                    print(f"  !! {arm} luke{ch} {dose}: missing {f}"); skipped += 1; break
            else:
                for tier in TIERS:
                    dst = os.path.join(R, f"naming_{arm}{SUFFIX}", f"luke{ch}", tier, DEFECT, dose)
                    os.makedirs(dst, exist_ok=True)
                    shutil.copyfile(os.path.join(src, psrc), os.path.join(dst, "passage_target_decanonicalized.txt"))
                    shutil.copyfile(os.path.join(src, qsrc), os.path.join(dst, "qa_target_decanonicalized.json"))
                    for f in CARRY:
                        s = os.path.join(src, f)
                        if os.path.exists(s): shutil.copyfile(s, os.path.join(dst, f))
                    made += 1
print(f"\nstaged {made} cells, skipped {skipped}")
print(f"chapters {CHAPTERS}  x  {len(TIERS)} tiers  x  {len(DOSES)} doses  x  {len(ARMS)} arms")

# ---- prove the arms actually differ, per chapter
print("\nSANITY -- first names in each arm's passage (must differ):")
import re
for ch in CHAPTERS[:3]:
    print(f"  luke{ch}")
    for arm in ARMS:
        p = os.path.join(R, f"naming_{arm}{SUFFIX}", f"luke{ch}", "1.7b", DEFECT, "0%", "passage_target_decanonicalized.txt")
        t = open(p, encoding="utf-8").read()[:400].replace("\n", " ")
        print(f"    {arm:10} {t[:110]}")
