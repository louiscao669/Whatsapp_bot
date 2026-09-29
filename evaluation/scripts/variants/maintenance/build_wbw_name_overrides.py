#!/usr/bin/env python3
"""Rebuild evaluation/datasets/perturbations/wbw_name_overrides.json (provenance).

WHY THE TABLE EXISTS. google_word_by_word keys its cache on ``word.lower()``, so the
capital that marks a proper noun is gone before the translator sees the token. "Dan"
came back as 担 (the verb "to carry"), "Micah" as 米卡 rather than the Bible's 米迦,
and "who" as the Latin-script organisation "WHO". The answer also depended on what
punctuation rode along -- 'micah' -> 米卡 but 'micah,' -> 米迦 -- so one passage
called the same man by two names.

HOW THE TABLE IS BUILT, in three passes, each gated on the same check:

  1. harvest   -- candidate renderings are taken from the cache itself, since the
                  punctuated variants often already hold the canonical name.
  2. propose   -- standard (CUV) renderings supplied by hand for what pass 1 missed.
  3. reference -- for what pass 2 missed, the rendering read directly off the
                  reference Chinese translation, which is NOT always CUV (it renders
                  Aram as 叙利亚 and drops the Beth- of Beth-millo).

THE GATE. No entry is accepted unless the exact string OCCURS in the reference
Chinese target of a passage whose English source contains that name. A wrong guess is
therefore dropped, never written in, and matching the reference -- rather than a
dictionary -- is what keeps a passage's names consistent with the QA built from it.

Deliberately NOT fixed: ordinary words rendered two ways (alive -> 活 / 还活着, fire ->
火 / 火灾). That is the word-salad the condition exists to produce.

  python3 evaluation/scripts/variants/maintenance/build_wbw_name_overrides.py
"""


# ======================== stage: harvest ========================
def _stage_harvest():
    import json, re, sys, glob, os
    from collections import defaultdict

    REPO = os.path.expanduser("~/mnt/eten-whatsapp-bot")
    OUTS = os.path.expanduser("~/mnt/eten-research-outputs/evaluation/outputs/tier1_bsb_unblinded_5opt_think")
    CACHE = f"{REPO}/evaluation/datasets/perturbations/.wbw_cache_en_zh-CN.json"

    CJK = re.compile(r"[一-鿿]+")
    LATIN = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
    STOP = set("""the a an and or but if then so for of to in on at by with from as that this these those
    he she it they we you i his her its their our your my him them us me who whom which what when where why how
    was were is are be been being had has have do does did not no nor all any some each every both few more most other
    said says say saying went go going came come coming made make making took take taking gave give giving
    there here now after before while when because since until unless though although however therefore thus
    look please should saddle bring indeed treason about let finally once suddenly surely seize intercede oh lay
    even under only leave long help may hear today prepare provide learning stay put putting remember listen one
    reign meanwhile muster hurry draw many corner valley gate mount governor excellency greetings blessed diviners
    oak seven testimony guards""".split())

    cache = json.load(open(CACHE, encoding="utf-8"))

    # cache keys grouped by their single latin core, e.g. 'micah' <- {'micah','micah,','“micah'}
    by_core = defaultdict(list)
    for key, val in cache.items():
        runs = LATIN.findall(key)
        if len(runs) == 1 and val:
            by_core[runs[0].lower()].append((key, val))

    rows, overrides, unresolved = [], {}, []
    for pdir in sorted(glob.glob(f"{OUTS}/t1_*")):
        pid = os.path.basename(pdir)
        eng_p = f"{pdir}/_base/llm_prompt_high/passage_source_decanonicalized.txt"
        zh_p  = f"{pdir}/_base/llm_prompt_high/passage_target.txt"
        if not (os.path.exists(eng_p) and os.path.exists(zh_p)):
            print(f"  ! {pid}: missing base files", file=sys.stderr); continue
        eng = open(eng_p, encoding="utf-8").read()
        zh  = open(zh_p,  encoding="utf-8").read()
        names = {w for w in re.findall(r"\b[A-Z][a-z]+(?:-[A-Za-z][a-z]+)*\b", eng) if w.lower() not in STOP}
        for name in sorted(names):
            low = name.lower()
            bare = cache.get(low)
            bare_zh = "".join(CJK.findall(bare or ""))
            # every Chinese rendering any punctuation-variant produced
            cands = {}
            for key, val in by_core.get(low, []):
                for run in CJK.findall(val):
                    cands[run] = max(cands.get(run, 0), zh.count(run))
            verified = sorted(((n, c) for c, n in cands.items() if n > 0), reverse=True)
            if not verified:
                unresolved.append((pid, name, bare))
                continue
            count, canon = verified[0]
            rows.append((pid, name, bare, canon, count, canon != bare_zh))
            if canon != bare_zh:
                prev = overrides.get(low)
                if prev and prev != canon:
                    print(f"  ! conflict for {low}: {prev} vs {canon}", file=sys.stderr)
                overrides[low] = canon

    changed = [r for r in rows if r[5]]
    print(f"names examined          : {len(rows) + len(unresolved)}")
    print(f"verified against clean  : {len(rows)}")
    print(f"WRONG in the bare cache : {len(changed)}")
    print(f"no verified rendering   : {len(unresolved)}\n")
    print("=== names the bare cache gets wrong (override -> canonical, verified count) ===")
    for pid, name, bare, canon, count, _ in sorted(changed, key=lambda r: -r[4]):
        print(f"  {name:16s} {str(bare):12s} -> {canon:10s} (x{count} in clean {pid})")
    json.dump(overrides, open("evaluation/datasets/perturbations/wbw_name_overrides.json", "w"),
              ensure_ascii=False, indent=2, sort_keys=True)
    json.dump([list(u) for u in unresolved], open("evaluation/datasets/perturbations/.wbw_name_unresolved.json", "w"),
              ensure_ascii=False, indent=2)
    print(f"\n{len(overrides)} overrides -> the override table")

# ======================== stage: propose ========================
def _stage_propose():
    import json, re, glob, os
    OUTS = os.path.expanduser("~/mnt/eten-research-outputs/evaluation/outputs/tier1_bsb_unblinded_5opt_think")

    PROPOSED = {
     "abishai":"亚比筛","ammonites":"亚扪人","amoz":"亚摩斯","antipatris":"安提帕底","aram":"亚兰",
     "aramean":"亚兰人","arameans":"亚兰人","arumah":"亚鲁玛","ashdod":"亚实突","athaliah":"亚他利雅",
     "azariah":"亚撒利雅","baal-berith":"巴力比利土","beer":"比珥","ben-hadad":"便哈达","beth-millo":"伯米罗",
     "beth-rehob":"伯利合","caesarea":"该撒利亚","carites":"迦利人","cilicia":"基利家","claudius":"革老丢",
     "dan":"但","danites":"但人","ebed":"以别","egyptians":"埃及人","el-berith":"伊勒比利土",
     "elhanan":"伊勒哈难","eloth":"以禄","eshtaol":"以实陶","eutychus":"犹推古","gaal":"迦勒",
     "gershom":"革舜","gittite":"迦特人","gob":"歌珥","gur-baal":"姑珥巴力","hamor":"哈抹",
     "herod":"希律","hittites":"赫人","hushathite":"户沙人","ishbi-benob":"以实比诺","jabneh":"雅比尼",
     "jair":"睚珥","jecoliah":"耶可利雅","jehoiada":"耶何耶大","jeiel":"耶利","jerubbaal":"耶路巴力",
     "joash":"约阿施","jonathan":"约拿单","laish":"拉亿","lysias":"吕西亚","maaseiah":"玛西雅",
     "mahaneh-dan":"玛哈尼但","mattan":"玛坦","meunites":"米乌尼人","ophrah":"俄弗拉","philistine":"非利士人",
     "philistines":"非利士人","samaria":"撒马利亚","sanhedrin":"公会","saph":"撒弗","sceva":"士基瓦",
     "shaphat":"沙法","shimei":"示米","sibbecai":"西比该","sur":"苏珥","thebez":"提备斯",
     "uzziah":"乌西雅","zalmon":"撒们","zebul":"西布勒","zeruiah":"洗鲁雅","zorah":"琐拉",
     # not a name: Google reads the isolated token as the health organization
     "who":"谁",
     # the BARE token already renders correctly (拉法), so pass 1 saw nothing to fix --
     # but every punctuated variant was an untranslated fallback ('rapha,' -> 'rapha，'),
     # which only an override covers.
     "rapha":"拉法",
    }
    ALWAYS = {"who"}   # generic, no passage to verify against

    passages = {}
    for pdir in sorted(glob.glob(f"{OUTS}/t1_*")):
        pid = os.path.basename(pdir)
        e = f"{pdir}/_base/llm_prompt_high/passage_source_decanonicalized.txt"
        z = f"{pdir}/_base/llm_prompt_high/passage_target.txt"
        if os.path.exists(e) and os.path.exists(z):
            passages[pid] = (open(e,encoding="utf-8").read().lower(), open(z,encoding="utf-8").read())

    kept, rejected = {}, []
    for low, canon in sorted(PROPOSED.items()):
        if low in ALWAYS:
            kept[low] = canon; continue
        hits = [(pid, zh.count(canon)) for pid,(en,zh) in passages.items()
                if re.search(rf"\b{re.escape(low)}\b", en)]
        good = [(pid,n) for pid,n in hits if n > 0]
        if good:
            kept[low] = canon
            print(f"  KEEP   {low:14s} {canon:8s} " + ", ".join(f"{p}x{n}" for p,n in good))
        else:
            rejected.append((low, canon, [p for p,_ in hits]))

    print(f"\nkept {len(kept)}, rejected {len(rejected)}")
    print("=== rejected (my proposal does not occur in the clean passage; left alone) ===")
    for low, canon, pids in rejected:
        print(f"  {low:14s} proposed {canon:8s} not found in {','.join(pids) or '(no passage)'}")

    harvested = json.load(open("evaluation/datasets/perturbations/wbw_name_overrides.json"))
    merged = dict(harvested); merged.update(kept)
    json.dump(merged, open("evaluation/datasets/perturbations/wbw_name_overrides.json","w"),
              ensure_ascii=False, indent=2, sort_keys=True)
    print(f"\nmerged map: {len(harvested)} harvested + {len(kept)} verified proposals = {len(merged)}")

# ======================== stage: propose2 ========================
def _stage_propose_two():
    import json, re, glob, os
    OUTS = os.path.expanduser("~/mnt/eten-research-outputs/evaluation/outputs/tier1_bsb_unblinded_5opt_think")

    FROM_REFERENCE = {
     "azariah":("亚撒利亚","t1_2chr26"), "jecoliah":("耶哥利雅","t1_2chr26"),
     "jeiel":("耶列","t1_2chr26"), "maaseiah":("玛西亚","t1_2chr26"),
     "aram":("叙利亚","t1_2kgs6_7"), "aramean":("叙利亚人","t1_2kgs6_7"),
     "arameans":("叙利亚人","t1_2kgs6_7"),
     "gob":("迦百","t1_2sam21"), "ishbi-benob":("以施比·比拿","t1_2sam21"),
     "eutychus":("尤提古斯","t1_acts20"),
     "antipatris":("安提帕特里斯","t1_acts23"), "claudius":("克劳狄","t1_acts23"),
     "lysias":("利西亚","t1_acts23"),
     "gershom":("革顺","t1_judg17_18"), "laish":("来士","t1_judg17_18"),
     "mahaneh-dan":("玛哈念但","t1_judg17_18"), "zorah":("所拉","t1_judg17_18"),
     "beth-millo":("米罗","t1_judg9"), "ebed":("耶比底","t1_judg9"),
     "el-berith":("以利比利土","t1_judg9"), "hamor":("含莫","t1_judg9"),
     "jerubbaal":("耶鲁巴力","t1_judg9"), "thebez":("底璧","t1_judg9"),
     "zalmon":("撒耳门","t1_judg9"), "zebul":("西布","t1_judg9"),
    }
    # dropped deliberately: egyptians / hittites -- the bare cache already gives 埃及人 / 赫人,
    # and the reference only ever says 埃及的诸王, so an override would lose the "people" sense.

    kept, bad = {}, []
    for low, (canon, pid) in sorted(FROM_REFERENCE.items()):
        zh = open(f"{OUTS}/{pid}/_base/llm_prompt_high/passage_target.txt", encoding="utf-8").read()
        n = zh.count(canon)
        (kept.__setitem__(low, canon) if n else bad.append((low, canon, pid)))
        print(f"  {'KEEP  ' if n else 'REJECT'} {low:14s} {canon:12s} x{n} in {pid}")

    path = "evaluation/datasets/perturbations/wbw_name_overrides.json"
    merged = json.load(open(path)); before = len(merged); merged.update(kept)
    json.dump(merged, open(path, "w"), ensure_ascii=False, indent=2, sort_keys=True)
    print(f"\nkept {len(kept)}, rejected {len(bad)}  |  map {before} -> {len(merged)}")

if __name__ == "__main__":
    _stage_harvest()
    _stage_propose()
    _stage_propose_two()
