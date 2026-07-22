#!/usr/bin/env python3
"""Build per-chapter token->replacement dictionaries that turn the pipeline's
decanonicalization placeholders (人物甲, 地区甲, 至高者甲, 人物01 ...) into
readable pseudonyms, while preserving the blind (no canonical names restored).

Policy
  person  -> gendered transliteration pseudonym (M: 玛伦/米珥/兰维, F: 哈丽/芮茉)
  people  -> collective name (族群 = nations/peoples, e.g. Israel -> 泰隆人)
  place   -> transliteration + type suffix (地区->地, 城市->城, 村庄->村)
  deity   -> distinct neutral title (God 主宰, Most High 至尊, Lord 主宰者, ...)
  generic -> the plain Chinese word restored (船, 门徒, 祭司, 香) -- not a spoiler
  text    -> 'this account'  (the gospel-book placeholder, no alias)

Consistency: keyed on the real entity (english aliases), so the same person is
the same name in every chapter. Pinned names are honoured exactly and removed
from the pools to avoid collisions.

Run from evaluation/:  python build_pseudonym_remap.py
Writes: datasets/pseudonym_remap/luke{1..8}_remap.json  (+ prints a doubling scan)
"""

import glob, hashlib, json, os, re
from collections import defaultdict

OUT = "datasets/pseudonym_remap"
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- load dicts
def chapter_mapping(ch):
    for c in (sorted(glob.glob(f"outputs/luke{ch}/*/*/*/decanonicalized_metadata.json"))
              + sorted(glob.glob(f"outputs/luke{ch}/*/*/decanonicalized_metadata.json"))):
        d = json.load(open(c))
        mp = (d.get("canonicalization") or {}).get("mapping")
        if mp:
            return mp
    return None

MAPS = {ch: chapter_mapping(ch) for ch in range(1, 9)}
canon_zh = {z for mp in MAPS.values() if mp for e in mp for z in (e.get("chinese_alias_hints") or [])}

def first_alias(e):
    al = e.get("english_aliases") or []
    return al[0] if al else ""

# ---------------------------------------------------------------- policy tables
DEITY = {"God", "Lord", "Holy Spirit", "Most High", "Messiah", "Son of Man",
         "devil", "Satan", "angel of the Lord"}
DEITY_MAP = {"God": "至高者", "Most High": "至高者", "Lord": "主", "Holy Spirit": "圣灵",
             "Messiah": "救主", "Son of Man": "人子", "devil": "魔君", "Satan": "魔君",
             "angel of the Lord": "天使"}
# Single-char divine titles that can sit next to an identical word.
DIVINE = {"至高者", "主", "圣灵", "救主", "人子", "魔君"}

def collapse_repeats(text, words):
    """Collapse adjacent repeats of any pseudonym/title (X X -> X, X X X -> X).

    Safe because ``words`` are the remap's replacement values (invented names and
    fixed titles) -- these are never legitimately reduplicated the way ordinary
    Chinese words can be (e.g. 研究研究). Repeats arise only from the placeholder
    token and a leaked canonical name both mapping to the same replacement.
    """
    ws = sorted({w for w in words if w}, key=len, reverse=True)
    if not ws:
        return text
    pat = re.compile(r'(' + '|'.join(re.escape(w) for w in ws) + r')(?:\s*\1)+')
    prev = None
    while prev != text:
        prev, text = text, pat.sub(r'\1', text)
    return text

def collapse_divine_dupes(text):  # back-compat helper
    return collapse_repeats(text, DIVINE)
FEMALE_ALIASES = {"Elizabeth", "Mary", "Anna", "Joanna", "Susanna", "Magdalene", "Herodias"}
PINS = {"Jesus": "玛伦", "John": "米珥", "Herod": "兰维"}

def category(e):
    ph = e["placeholder"]; a = first_alias(e)
    if ph.startswith("族群"):                    return "people"    # nations -> collective name
    if a in DEITY:                               return "deity"
    if not a:                                    return "text"
    if ph.startswith(("物件", "实体", "群体")):   return "generic"   # objects/entities/groups -> plain word
    if a[0].islower():                           return "generic"   # common noun
    if ph.startswith(("地点", "地区", "城市", "村庄")): return "place"
    return "person"

# ---------------------------------------------------------------- name pools
SYL1 = "迪 塞 珂 娑 尼 玛 撒 亚 利 珥 拉 泰 洛 维 卡 兰 索 迦 哈 珀 弗 米 诺 瓦 苏 黛 楠 韦 佳 隆 昆 珈 慕 芮".split()
MALE_FIN = "洛 顿 姆 斯 隆 恩 昂 图 达 萨 伦 恒 朗 罗 谷 磐 德 里 松 温".split()
FEM_FIN  = "娜 拉 尼 岚 苔 雯 娅 莎 妮 雅 丽 珊 黛 茉 琳 蔻 妲 娃".split()
PLACE_BASE = ["塞夫兰", "迦拓斯", "洛尼亚", "玛顿", "亚斯林", "索伦", "迪兰", "珂兰", "娑林",
              "尼澳", "赫洛", "塞伦", "迦洛", "泰洛", "维珥顿", "珀萨", "兰姆", "迪玛拉", "卡兰迪",
              "尼洛斯", "撒珥顿", "泰伦", "娜索", "塞岚", "珂谷", "维恩", "洛磐", "苏岱", "兰茂"]
PEOPLE = ["泰隆"]  # nation names (no 人 suffix, so an existing 人 in '以色列人' still reads right)

def _gpool(finals, seed):
    # exclude pinned names, place bases, and people names so a person can never
    # share a name with a place/people (keeps person vs place visually distinct)
    out, seen = [], set(PINS.values()) | set(PLACE_BASE) | set(PEOPLE)
    for a in SYL1:
        for b in finals:
            n = a + b
            if n in canon_zh or n in seen:
                continue
            seen.add(n); out.append(n)
    out.sort(key=lambda n: hashlib.md5((seed + n).encode()).hexdigest())
    return out

MALE_NAMES = _gpool(MALE_FIN, "male")
FEMALE_NAMES = _gpool(FEM_FIN, "female")
PLACE_SUFFIX = {"地点": "", "地区": "地", "城市": "城", "村庄": "村"}

def strip_suffix(tok):
    return re.sub(r'[甲乙丙丁戊己庚辛壬癸]$|\d+$', '', tok)

# ---------------------------------------------------------------- assign per entity
def ekey(e):
    al = tuple(sorted(e.get("english_aliases") or []))
    if al:  return ("en",) + al
    zh = tuple(sorted(e.get("chinese_alias_hints") or []))
    return ("zh",) + zh if zh else ("ph", e["placeholder"])

all_entities = {}
for ch in range(1, 9):
    for e in (MAPS[ch] or []):
        all_entities.setdefault(ekey(e), e)

entity_repl, entity_cat = {}, {}
mi = fi = pli = pei = 0
for k in sorted(all_entities, key=lambda k: hashlib.md5(str(k).encode()).hexdigest()):
    e = all_entities[k]; cat = category(e); entity_cat[k] = cat; a = first_alias(e)
    if cat == "generic":
        zh = e.get("chinese_alias_hints") or []
        entity_repl[k] = "香" if a.lower().startswith("incense") else (zh[0] if zh else strip_suffix(e["placeholder"]))
    elif cat == "deity":
        entity_repl[k] = DEITY_MAP.get(a, strip_suffix(e["placeholder"]) or "至尊")
    elif cat == "text":
        entity_repl[k] = "这记录"
    elif cat == "people":
        entity_repl[k] = PEOPLE[pei % len(PEOPLE)]; pei += 1
    elif cat == "place":
        entity_repl[k] = PLACE_BASE[pli % len(PLACE_BASE)] + PLACE_SUFFIX.get(e["placeholder"][:2], ""); pli += 1
    else:  # person
        al = set(e.get("english_aliases") or [])
        pin = next((PINS[x] for x in al if x in PINS), None)
        if pin:                       entity_repl[k] = pin
        elif al & FEMALE_ALIASES:     entity_repl[k] = FEMALE_NAMES[fi]; fi += 1
        else:                         entity_repl[k] = MALE_NAMES[mi]; mi += 1

# The gospel-text token (文本甲, no english alias) is used both as a citation
# source and, in one intro question, as the author. Map it to the author's
# person name so that question reads naturally; the citation form gets reduced to
# a bare "ch:verse" reference at apply time.
_author = next((entity_repl[k] for k, e in all_entities.items()
                if "Luke" in (e.get("english_aliases") or [])), None)
if _author:
    for k in list(entity_repl):
        if entity_cat[k] == "text":
            entity_repl[k] = _author

# ---------------------------------------------------------------- emit + scan
def build_remaps():
    """Return {chapter: {token/canonical -> replacement}} and the master rows."""
    remaps, master = {}, []
    for ch in range(1, 9):
        remap = {}
        for e in (MAPS[ch] or []):
            k = ekey(e); rep = entity_repl[k]; remap[e["placeholder"]] = rep
            # also map the canonical spelling(s) of proper names, so any leaked
            # (un-tokenized) canonical name is caught too. Proper names only --
            # never generic/deity common words.
            if entity_cat[k] in ("person", "place", "people"):
                for z in (e.get("chinese_alias_hints") or []):
                    if len(z) >= 2:
                        remap.setdefault(z, rep)
            master.append((ch, e["placeholder"], entity_cat[k], rep, first_alias(e),
                           (e.get("chinese_alias_hints") or [""])[0]))
        remaps[ch] = remap
    return remaps, master

def write_remaps():
    remaps, master = build_remaps()
    for ch, remap in remaps.items():
        json.dump(remap, open(f"{OUT}/luke{ch}_remap.json", "w"), ensure_ascii=False, indent=1)
    json.dump(master, open(f"{OUT}/_master.json", "w"), ensure_ascii=False)
    return remaps, master

def collapsible_words(remap):
    """The set of replacement words safe to de-duplicate for a given remap."""
    return DIVINE | {v for v in remap.values() if len(v) >= 2}

# doubling scan: apply each remap to its passage and look for any 'WW' adjacency
def scan():
    bad = []
    for ch in range(1, 9):
        pf = f"outputs/luke{ch}/1.7b/omission/0%/passage_target_decanonicalized.txt"
        if not os.path.exists(pf):
            continue
        txt = open(pf, encoding="utf-8").read()
        remap = json.load(open(f"{OUT}/luke{ch}_remap.json"))
        for t in sorted(remap, key=len, reverse=True):
            txt = txt.replace(t, remap[t])
        txt = collapse_repeats(txt, DIVINE | {v for v in remap.values() if len(v) >= 2})
        compact = re.sub(r'\s+', '', txt)
        for w in {v for v in remap.values() if len(v) >= 2}:
            if w + w in compact:
                bad.append((ch, w))
    return bad

if __name__ == "__main__":
    from collections import Counter
    write_remaps()
    print("categories:", dict(Counter(entity_cat.values())))
    print("wrote", len(MAPS), "chapter remaps to", OUT)
    bad = scan()
    print("doubling scan:", "clean ✓" if not bad else bad)
