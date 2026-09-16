#!/usr/bin/env python3
"""Hand-audited corrections to the unblinded 5-option tier-1 base translations.

Audit 2026-09-16 (verse-by-verse against BSB English) found translation errors in the
gpt-4.1-mini base passages and in the separately translated Chinese QA:

  * wrong entities (Danites -> 便雅悯人, Sceva -> 司提反 "Stephen", Jehosheba -> 约沙法,
    Meunites -> 摩押人, Baal-berith -> 巴力毗珥 "Baal-peor", Gittite -> 基利提人, ...);
  * meaning reversals (Judg 9:15 "if you anoint me" -> "if I anoint you", 18:19, 7:3);
  * names rendered differently in passage and QA (米该亚/米迦, 亚她利雅/亚他利雅,
    约阿达/耶何耶大, 腓力斯/费利克斯, 亚兰/叙利亚, 撒玛利亚/撒马利亚, 西布/西布伦, ...),
    which makes an answer-bearing name unmatchable for a reader.

Everything is applied to <pid>/_base only; the defect variants are then rebuilt from
_base (run the rebuild step printed at the end). Each replacement must match, so a
drifted file fails loudly instead of being half-fixed. Idempotent: a file whose
replacements are already applied is skipped. Originals are kept once as *.orig.

  python3 evaluation/scripts/variants/maintenance/fix_unblinded_5opt_translations.py [--root DIR] [--check]
"""

import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_ROOT = Path("evaluation/outputs/tier1_bsb_unblinded_5opt_think")

# Name renderings unified across passage, QA and mistranslation bank.
NAMES = {
    "t1_judg17_18": [("米该亚", "米迦")],
    "t1_2kgs11": [("亚她利雅", "亚他利雅"), ("约阿达", "耶何耶大")],
    "t1_acts23": [("腓力斯", "费利克斯")],
    "t1_2kgs6_7": [("撒玛利亚", "撒马利亚"), ("亚兰", "叙利亚")],
    # QA used 西布伦 (the tribe Zebulun) and 加尔 for Zebul/Gaal; the passage is right.
    "t1_judg9": [("西布伦", "西布"), ("加尔", "迦勒")],
    "t1_2chr26": [("以洛施", "以禄")],
}

# Passage corrections, written against the text AFTER the name map above.
PASSAGE = {
    "t1_2chr26": [
        ("重建了以洛并使其归于犹大", "重建了以禄并使其归于犹大"),
        ("居巴力的亚拉伯人和摩押人", "住在姑珥巴力的阿拉伯人，以及米乌尼人"),
    ],
    "t1_2sam21": [
        ("示罗亚的儿子亚比筛", "洗鲁雅的儿子亚比筛"),
        ("拉法的后裔以实比拿伯", "拉法的后裔以施比·比拿"),
        ("伯利恒人耶拉的儿子以连杀了基利提人歌利亚的弟弟",
         "伯利恒人睚珥的儿子伊勒哈难杀了迦特人歌利亚的弟弟"),
        ("这样，这四个拉法的后裔", "这样，在迦特的这四个拉法的后裔"),
    ],
    "t1_acts19": [("犹太大祭司司提反的七个儿子", "犹太大祭司士基瓦的七个儿子")],
    "t1_2kgs11": [
        ("亚哈谢的妹妹约沙法", "亚哈谢的妹妹约示巴"),
        ("三分之一在示罗门的门口", "三分之一在苏珥门"),
    ],
    "t1_2kgs6_7": [
        ("愿神重重地惩罚我，如果到今日以利沙撒法的儿子的头还在他肩上！",
         "沙法的儿子以利沙的头今日若还在他肩上，愿神重重地惩罚我！"),
        ("我们坐在这里等死算了。", "我们为什么坐在这里等死呢？"),
        ("以色列王必招聚赫人和埃及王来攻击我们",
         "以色列王必是雇了赫人的诸王和埃及的诸王来攻击我们"),
    ],
    "t1_judg9": [
        ("巴力毗珥的庙", "巴力比利土的庙"),
        ("以尔毗珥神庙", "以利比利土神庙"),
        ("我若真膏你作王，愿你来投靠我的荫下；若不然，愿荆棘从我发出火来",
         "你们若真膏我作王，就要投靠在我的荫下；若不然，愿火从荆棘里出来"),
        ("使他们彼此欺骗", "使示剑的首领以诡诈待亚比米勒"),
        ("城里的男女首领都逃到那里", "城里的男人、女人和首领都逃到那里"),
    ],
    "t1_judg17_18": [
        ("为我儿子铸造雕像", "为我儿子的缘故铸造雕像"),
        ("有一个利未人，是犹大伯利恒人", "有一个少年利未人，是犹大伯利恒人"),
        ("这少年人成了米迦的儿子", "这少年人在米迦那里如同他的儿子一样"),
        ("便雅悯支派的但人寻找产业", "但支派的人正在寻找地业居住"),
        ("你们进去必遇见安居宽阔之地", "你们进去，必遇见安居无备的民，那地也宽阔"),
        ("进了少年利未人米迦的家", "进了那少年利未人的住处，就是米迦的家"),
        ("你作一个人的祭司，强如作以色列族和家族的祭司吗？",
         "你作一个人家的祭司好呢？还是作以色列一个支派一个家族的祭司好呢？"),
        ("便雅悯人转身", "但人转身"),
        ("因为那城远离西顿，没有与人结盟，位于伯利恒谷中。",
         "并无人搭救，因为那城远离西顿，也没有与人结盟；城在伯利合附近的谷中。"),
        ("摩西的孙子革顺的儿子约拿单", "摩西的孙子、革顺的儿子约拿单"),
        ("他们立米迦的雕像为偶像，直到神的殿在示罗的时候，偶像仍在那里。",
         "神的殿在示罗多少日子，他们为自己设立的米迦的雕像也在那里多少日子。"),
    ],
}

# QA corrections (question and choice text), after the name map.
QA = {
    "t1_judg9": [("以尔-伯利恒殿", "以利比利土殿"), ("巴力-伯利恒殿", "巴力比利土殿")],
    "t1_judg17_18": [("Jonathan 和他的儿子们", "约拿单和他的儿子们"), ("Micah 和他的儿子", "米迦和他的儿子")],
    "t1_2kgs11": [("迦特人和护卫的百夫长", "迦利人和护卫的百夫长")],
}

PASSAGE_FILES = ("llm_prompt_high/passage_target.txt",
                 "llm_prompt_high/passage_target_decanonicalized.txt",
                 "llm_prompt_high/passage_translation.json")
QA_FILES = ("llm_prompt_high/qa_target.json",
            "llm_prompt_high/qa_target_decanonicalized.json",
            "_shared/{pid}_base_qa_zh.json",
            "_shared/{pid}_base_qa_zh_decanonicalized.json")
BANK_FILES = ("_shared/mistranslation_bank_zh.json",)


def patch(path: Path, names, fixes=(), *, required: bool, check: bool) -> str:
    """Apply name renderings (optional per file), then fixes (must match if required)."""
    text = path.read_text(encoding="utf-8")
    new = text
    for old, repl in names:
        new = new.replace(old, repl)
    missing = []
    for old, repl in fixes:
        if old in new:
            new = new.replace(old, repl)
        elif required and repl not in new:
            missing.append(old)
    if missing:
        raise SystemExit(f"{path}: expected text not found: {missing}")
    if new == text:
        return "unchanged"
    if not check:
        orig = path.with_name(path.name + ".orig")
        if not orig.exists():
            shutil.copy2(path, orig)
        path.write_text(new, encoding="utf-8")
    return "patched"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--check", action="store_true", help="report only")
    args = ap.parse_args()
    pids = sorted(set(NAMES) | set(PASSAGE) | set(QA))
    for pid in pids:
        base = args.root / pid / "_base"
        names = NAMES.get(pid, [])
        # JSON stores CJK either raw or \\u-escaped; our files are raw (ensure_ascii=False).
        for rel in PASSAGE_FILES:
            path = base / rel
            required = rel.endswith(".txt")
            status = patch(path, names, PASSAGE.get(pid, []), required=required, check=args.check)
            print(f"  {pid:14s} {rel:52s} {status}")
        for rel in QA_FILES:
            path = base / rel.format(pid=pid)
            status = patch(path, names, QA.get(pid, []), required=False, check=args.check)
            print(f"  {pid:14s} {rel.format(pid=pid):52s} {status}")
        for rel in BANK_FILES:
            path = base / rel
            if path.exists():
                print(f"  {pid:14s} {rel:52s} {patch(path, names, required=False, check=args.check)}")
    print("\nNext: rebuild the pilot defect cells from _base, then the wbw cell, then re-import.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
