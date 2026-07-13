#!/usr/bin/env python3
"""
Item-level grid: chapter x item x method x model -> (answer, score).

For each QA item (e.g. Luke 1, question 13), shows what each of the three
answer models replied and its score, across all 8 translation methods.

Long/tidy CSV  : reports/item_level_grid.csv   (one row per item x method x model)
Nested JSON    : reports/item_level_grid.json
HTML drill-down: reports/item_level_grid.html  (pick chapter+item -> 8x3 grid)

Item score: open -> llm_score in [0,1] (answer = English gloss);
            mcq  -> 1.0 if direct_correct else 0.0 (answer = selected choice).
Run: cd evaluation && python3 scripts/item_level_grid.py
"""
import json, os
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))          # repo root (script now lives in QA_algorithm/scripts)
OUT  = os.path.join(REPO, "evaluation", "outputs")     # answer-score inputs stay under evaluation/
REPORTS = os.path.join(REPO, "QA_algorithm", "outputs", "reports", "item_level_grid_analysis")

METHODS = ["google_word_by_word", "mBART-50", "helsinki", "nllb-200-distilled-600M",
           "llm_prompt_low", "llm_prompt_medium", "nllb-200-1.3B", "llm_prompt_high"]
MODELS  = {"llama 1b": "llama1b", "1.5b": "qwen1.5b", "1.7b": "qwen1.7b"}
LABELS  = list(MODELS.values())
CHAPTERS = [f"luke{i}" for i in range(1, 9)]


def load_items(path):
    with open(path) as f:
        return json.load(f)["items"]


def item_view(it):
    if it["q_type"] == "mcq":
        ans = f"{it.get('selected_choice')} (correct {it.get('correct_choice')})"
        score = 1.0 if it.get("direct_correct") else 0.0
    else:
        ans = it.get("generated_answer_english") or it.get("generated_answer") or ""
        score = it.get("llm_score")
    return ans, score


# grid[chapter][item_id] = {index, q_type, question, standard, cells:{method:{model:(ans,score)}}}
grid = {}
rows = []  # long form
for ch in CHAPTERS:
    for md, lab in MODELS.items():
        for meth in METHODS:
            p = f"{OUT}/{ch}/{md}/{meth}/scores_target_llama.json"
            if not os.path.exists(p):
                continue
            for it in load_items(p):
                iid = it["id"]
                g = grid.setdefault(ch, {}).setdefault(iid, {
                    "index": it.get("item_index"),
                    "q_type": it["q_type"],
                    "question": it.get("question", ""),
                    "reference": it.get("passage_reference", ""),
                    "standard": it.get("standard_answer", ""),
                    "cells": {m: {} for m in METHODS},
                })
                ans, score = item_view(it)
                g["cells"][meth][lab] = {"answer": ans, "score": score}
                rows.append({
                    "chapter": ch, "item_id": iid, "item_index": it.get("item_index"),
                    "q_type": it["q_type"], "reference": it.get("passage_reference", ""),
                    "question": it.get("question", ""), "standard_answer": it.get("standard_answer", ""),
                    "method": meth, "model": lab,
                    "generated_answer": ans,
                    "score": "" if score is None else round(score, 3),
                })

os.makedirs(REPORTS, exist_ok=True)

# ---- long CSV ----
import csv
cols = ["chapter", "item_id", "item_index", "q_type", "reference", "question",
        "standard_answer", "method", "model", "generated_answer", "score"]
with open(f"{REPORTS}/item_level_grid.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    rows.sort(key=lambda r: (r["chapter"], r["item_index"] or 0,
                             METHODS.index(r["method"]), LABELS.index(r["model"])))
    w.writerows(rows)

# ---- nested JSON ----
with open(f"{REPORTS}/item_level_grid.json", "w") as f:
    json.dump({"generated": str(date.today()), "models": LABELS,
               "methods": METHODS, "grid": grid}, f, ensure_ascii=False, indent=2)

# ---- HTML drill-down ----
data_js = json.dumps(grid, ensure_ascii=False)
htmlpage = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Item-level grid — model × quality × answer</title>
<style>
 body{font-family:system-ui,Arial,sans-serif;margin:20px;color:#222}
 select{font-size:14px;padding:4px;margin-right:8px}
 .meta{background:#f4f4f4;padding:10px 14px;border-radius:8px;margin:12px 0}
 table{border-collapse:collapse;width:100%;font-size:13px}
 th,td{border:1px solid #ccc;padding:6px 8px;vertical-align:top}
 th{background:#eceff1;text-align:left}
 td.m{white-space:nowrap;font-weight:600;background:#fafafa}
 .ans{display:block;max-width:340px}
 .sc{display:inline-block;min-width:34px;text-align:center;color:#fff;
     border-radius:4px;padding:1px 4px;font-weight:700;font-size:12px}
 .q{font-size:16px;font-weight:600;margin:4px 0}
</style></head><body>
<h2>Item-level grid — 8 translations × 3 answer models</h2>
<div>Chapter <select id="ch"></select> Question <select id="it"></select></div>
<div class="meta" id="meta"></div>
<table id="tbl"></table>
<script>
const DATA = __DATA__;
const METHODS = __METHODS__, MODELS = __MODELS__;
const chSel=document.getElementById('ch'), itSel=document.getElementById('it');
function color(s){ if(s===null||s==='')return 'transparent'; s=+s;
  if(s>=0.99)return '#1b5e20'; if(s>=0.5)return '#7cb342';
  if(s>0)return '#f9a825'; return '#c62828';}
Object.keys(DATA).sort().forEach(c=>chSel.add(new Option(c,c)));
function fillItems(){ itSel.innerHTML='';
  const items=DATA[chSel.value];
  Object.keys(items).sort((a,b)=>items[a].index-items[b].index)
    .forEach(id=>itSel.add(new Option(items[id].index+' · '+items[id].q_type+' · '+id,id)));
  render();}
function render(){
  const it=DATA[chSel.value][itSel.value];
  document.getElementById('meta').innerHTML=
    '<div class="q">Q'+it.index+' ('+it.reference+', '+it.q_type+'): '+it.question+'</div>'+
    '<div><b>Standard answer:</b> '+it.standard+'</div>';
  let h='<tr><th>method</th>'+MODELS.map(m=>'<th>'+m+'</th>').join('')+'</tr>';
  METHODS.forEach(me=>{ h+='<tr><td class="m">'+me+'</td>';
    MODELS.forEach(mo=>{ const c=(it.cells[me]||{})[mo];
      if(!c){h+='<td>—</td>';return;}
      const s=c.score;
      h+='<td><span class="sc" style="background:'+color(s)+'">'+
         (s===null||s===''?'·':(+s).toFixed(2))+'</span>'+
         '<span class="ans">'+(c.answer||'')+'</span></td>';});
    h+='</tr>';});
  document.getElementById('tbl').innerHTML=h;}
chSel.onchange=fillItems; itSel.onchange=render; fillItems();
</script></body></html>"""
htmlpage = (htmlpage.replace("__DATA__", data_js)
                    .replace("__METHODS__", json.dumps(METHODS))
                    .replace("__MODELS__", json.dumps(LABELS)))
with open(f"{REPORTS}/item_level_grid.html", "w") as f:
    f.write(htmlpage)

print(f"rows: {len(rows)}  chapters: {len(grid)}  items(luke1): {len(grid.get('luke1',{}))}")
for ext in ("csv", "json", "html"):
    print("  wrote", f"{REPORTS}/item_level_grid.{ext}")
