"""Validate and report the two Sol cohorts separately on the slide 35–43 design."""
import argparse
import csv
import time
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile

import run_sol_slide_experiment as run


NAMES = {"scratch": "From-scratch", "prepared": "Prepared"}
MODELS = [run.model_name(*model) for model in run.MODELS]
FAMILIES = ["omission", "mistranslation", "grammar"]
OUTCOMES = ["correct", "incorrect", "abstain", "invalid"]


def expected_groups():
    for index, model in enumerate(MODELS):
        conditions = [*run.FULL, "grammarMax"] if index < 4 else run.SHORT
        for condition in conditions:
            yield model, condition, "mcq"
            if index < 3 and condition in run.SHORT:
                yield model, condition, "open"


def results(study):
    roster, packs = run.source()
    roster = {r["id"]: r for r in roster if r["source"] == run.STUDIES[study]}
    assert list(roster) == run.read(run.RUN / "design.json")["bank_questions"][study]
    with run.db_open() as db:
        db.execute("begin")
        values = db.execute("""
            SELECT o.model,o.condition,o.form,o.item,o.request_hash,o.choice,o.outcome,
                   a.answer,a.done_reason,g.score,m.signature
            FROM observations o
            LEFT JOIN answers a ON o.request_hash=a.hash
            LEFT JOIN grades g ON o.form='open' AND (o.study,o.model,o.condition,o.item)
                =(g.study,g.model,g.condition,g.item)
            LEFT JOIN mapped_observations m ON o.form='mcq' AND (o.study,o.model,o.condition,o.item)
                =(m.study,m.reader,m.condition,m.item)
            WHERE o.study=? ORDER BY o.model,o.condition,o.form,o.item
        """, (study,)).fetchall()
    coverage = {}
    max_file = run.RUN / "grammar_max_coverage.json"
    if max_file.exists():
        coverage = run.read(max_file)
        maximum = run.max_verses()
    groups = defaultdict(dict)
    hashes = set()
    for model, condition, form, item, hashed, choice, outcome, answer, stop, score, mapped in values:
        assert item in roster and answer is not None
        if form == "mcq":
            label = ("correct" if choice == roster[item]["correct"] else "abstain" if choice == "E"
                     else "incorrect" if choice in ("A", "B", "C", "D") else "invalid")
            assert outcome == label and score is None
            if outcome == "invalid" and answer.strip() and model in MODELS[:4]:
                label = "awaiting mapper"
            assert mapped is None or (model in MODELS[:4] and choice in tuple("ABCDE"))
        else:
            assert outcome is None and score in (None, 0, 0.5, 1)
            label = {None:"awaiting grade", 0:"zero", 0.5:"partial", 1:"full"}[score]
        group = groups[model, condition, form]
        assert item not in group
        group[item] = (label, stop == "length", mapped is not None)
        hashes.add(hashed)
    assert groups.keys() <= set(expected_groups())
    rows = []
    same_window = {}
    for model, condition, form in expected_groups():
        group = groups[model, condition, form]
        count = Counter(label for label, _, _ in group.values())
        scored = len(group) - count["awaiting grade"] - count["awaiting mapper"]
        complete = set(group) == set(roster) and scored == len(roster)
        if condition not in same_window and (condition != "grammarMax" or coverage):
            identical = 0
            for item in roster.values():
                pid = item["passage_id"]
                pack = packs[pid]["conditions"]
                versions = [pack["clean"]["verses"], maximum[pid] if condition == "grammarMax" else pack[condition]["verses"]]
                excerpts = [" ".join(v[k] for k in item["verses"] if k in v) for v in versions]
                assert all(excerpts)
                identical += excerpts[0] == excerpts[1]
            same_window[condition] = identical
        rows.append(dict(model=model, condition=condition, form=form, expected=len(roster),
                         observed=len(group), scored=scored, complete=complete,
                         correct=count["correct"] if form=="mcq" else count["full"],
                         wrong_ad=count["incorrect"] if form=="mcq" else None,
                         cannot_tell=count["abstain"] if form=="mcq" else None,
                         invalid=count["invalid"] if form=="mcq" else None,
                         partial=count["partial"] if form=="open" else None,
                         zero=count["zero"] if form=="open" else None,
                         hit_token_limit=sum(hit for label,hit,mapped in group.values()),
                         mapped_choices=sum(mapped for label,hit,mapped in group.values()) if form=="mcq" else None,
                         mapped_correct=sum(label=="correct" and mapped for label,hit,mapped in group.values()) if form=="mcq" else None,
                         windows_identical_to_clean=same_window.get(condition),
                         accuracy_pct=round(100*(count["correct"]+count["full"])/scored,2) if complete else None))
    return rows, len(hashes), coverage


def label(condition):
    if condition == "grammarMax":
        return "Grammar Max"
    if condition == "clean":
        return "Clean"
    if condition == "wbw":
        return "Google word-by-word"
    family = next(name for name in FAMILIES if condition.startswith(name))
    return family.title() + " " + condition[len(family):] + "%"


def percent(row):
    return f"{row['accuracy_pct']:.1f}% ({row['correct']}/{row['scored']})" if row["complete"] else "Pending"


def table(headings, values):
    return "<table><thead><tr>" + "".join("<th scope='col'>"+escape(h)+"</th>" for h in headings) + "</tr></thead><tbody>" + "".join(
        "<tr>" + "".join("<td>"+escape(str(v))+"</td>" for v in row) + "</tr>" for row in values) + "</tbody></table>"


def figures(path, title, cells):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import Patch
    colors = ["#14775c","#c86819","#786ab1","#9ca7ae"]
    legends = [Patch(color=c, label=l) for c,l in zip(colors,["Correct A–D","Incorrect A–D","E · cannot tell","Invalid"])]
    with PdfPages(path) as pdf:
        fig, axes = plt.subplots(1,3,figsize=(12.5,6.2),sharey=True)
        for model, axis in zip(MODELS, axes):
            for delta,form,color in [(-.19,"mcq","#276796"),(.19,"open","#7966ab")]:
                vals = [cells[model,c,form]["accuracy_pct"] for c in run.SHORT]
                axis.barh([i+delta for i in range(len(vals))],vals,.35,color=color)
            axis.set(title=model,xlim=(0,100),xlabel="Fully correct (%)")
            axis.spines[["top","right"]].set_visible(False)
        axes[0].set_yticks(range(len(run.SHORT)),[label(c) for c in run.SHORT])
        axes[0].invert_yaxis()
        fig.suptitle(title+" · Answer format",fontsize=15,fontweight="bold")
        fig.legend(handles=[Patch(color="#276796",label="Multiple choice"),Patch(color="#7966ab",label="Open · full credit")],
                   loc="lower center",ncol=2,frameon=False)
        fig.tight_layout(rect=(0,.09,1,.92))
        pdf.savefig(fig)
        plt.close(fig)
        for family, slides in zip([*FAMILIES,"wbw"],[(36,37),(38,39),(40,41),(42,43)]):
            for models,slide in zip([MODELS[:4],MODELS[4:]],slides):
                fig, axes = plt.subplots(2,2,figsize=(11.7,8.3),sharey=True)
                for axis,model in zip(axes.flat,models):
                    conditions = ["clean","wbw"] if family=="wbw" else ["clean",*[f"{family}{i}" for i in range(5,31,5)]]
                    if family=="grammar":
                        conditions.append("grammarMax")
                    conditions = [c for c in conditions if (model,c,"mcq") in cells]
                    bottom = [0.] * len(conditions)
                    for metric,color in zip(["correct","wrong_ad","cannot_tell","invalid"],colors):
                        heights = [100*cells[model,c,"mcq"][metric]/cells[model,c,"mcq"]["expected"] for c in conditions]
                        axis.bar(range(len(conditions)),heights,bottom=bottom,color=color,width=.71)
                        for i,h in enumerate(heights):
                            if h>=11:
                                axis.text(i,bottom[i]+h/2,f"{h:.0f}",ha="center",va="center",
                                          color="white" if metric in ("correct","cannot_tell") else "#1c1e20",fontsize=8)
                        bottom = [b+h for b,h in zip(bottom,heights)]
                    axis.set_title(model)
                    axis.set_ylim(0,100)
                    axis.set_xticks(range(len(conditions)),["Clean" if c=="clean" else "Word-by-word" if c=="wbw" else "Max" if c=="grammarMax" else c[len(family):]+"%" for c in conditions])
                    axis.set_ylabel("Responses (%)")
                    axis.spines[["top","right"]].set_visible(False)
                if len(models)==3:
                    axes.flat[-1].set_visible(False)
                name = "Google word-by-word" if family=="wbw" else family.title()
                fig.suptitle(f"{title} · {name}",fontsize=15,fontweight="bold")
                fig.legend(handles=legends,loc="lower center",ncol=4,frameon=False)
                fig.text(.02,.025,f"Corresponds to slide {slide}. Segments show percentages of all questions in the set.",fontsize=8)
                fig.tight_layout(rect=(0,.09,1,.93))
                pdf.savefig(fig)
                plt.close(fig)


def publish(study, require_complete):
    rows, distinct, coverage = results(study)
    completed = all(r["complete"] for r in rows)
    if require_complete and not completed:
        raise ValueError(f"{study} has {sum(not r['complete'] for r in rows)} unfinished cells.")
    n = rows[0]["expected"]
    slug = "from-scratch" if study == "scratch" else study
    run.REPORT.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", newline="", dir=run.REPORT, delete=False) as f:
        writer = csv.DictWriter(f, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    Path(f.name).replace(run.REPORT / (slug+".csv"))
    cells = {(r["model"], r["condition"], r["form"]):r for r in rows}
    title = f"{NAMES[study]} Sol questions · {n} items"
    parts = ["<!doctype html><html lang='en'><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
             "<title>"+escape(title)+"</title><style>body{font:16px/1.5 system-ui;color:#202830;max-width:1170px;margin:3rem auto;padding:0 1rem}h1,h2{line-height:1.2}h2{margin-top:2.2em}table{border-collapse:collapse;font-size:.94rem;width:100%;margin-bottom:1.5rem}th,td{padding:.45rem .7rem;border-bottom:1px solid #ccd4d6;text-align:right;font-variant-numeric:tabular-nums}th:first-child,td:first-child{text-align:left}th{background:#eaf1f1}section{overflow-x:auto}a{color:#096069}</style>",
             f"<h1>{escape(title)}</h1>", f"<p>{'Complete' if completed else 'In progress'} · {sum(r['observed'] for r in rows):,} of {len(rows)*n:,} scheduled reader answers recorded. {distinct:,} distinct reader prompts. <a href='{slug}.csv'>Download counts by model, condition and format</a>.</p>",
             "<h2>Slide 35 · Multiple choice and open response</h2><p>Each model answers the same items in both formats. Multiple-choice accuracy uses the published clean key. Open accuracy counts full credit only. GPT-4.1-mini translates and grades responses against the published Chinese key translated into English. The CSV also includes half-credit and zero-credit counts.</p>"]
    for model in MODELS[:3]:
        parts.extend([f"<h3>{escape(model)}</h3>",table(["Condition","MCQ correct","Open full credit"],
              [(label(c),percent(cells[model,c,"mcq"]),percent(cells[model,c,"open"])) for c in run.SHORT])])
    for family, slides in zip([*FAMILIES, "wbw"], ["36–37","38–39","40–41","42–43"]):
        title_family = "Google word-by-word" if family == "wbw" else family.title()
        parts.append(f"<h2>Slides {slides} · {title_family}</h2>")
        if family == "grammar":
            parts.append("<p>Max applies the approved sentence edits. Its unit differs from the 5–30% ladder. Per-passage sentence coverage appears below.</p>")
        conditions = ["clean","wbw"] if family=="wbw" else ["clean",*[f"{family}{i}" for i in range(5,31,5)]]
        if family=="grammar":
            conditions.append("grammarMax")
        for group in [MODELS[:4], MODELS[4:]]:
            matched = [c for c in conditions if (group[0],c,"mcq") in cells]
            parts.extend(["<section>",table(["Condition",*group],[(label(c),*[percent(cells[m,c,"mcq"]) for m in group]) for c in matched]),"</section>"])
    parts.extend(["<h2>What the reader saw</h2><p>The requested dose applies to the full passage. A question window can stay identical to clean across several doses. Exact repeated prompts reuse one reader answer. Each question contributes once per model and condition. These are model results.</p>",
        table(["Condition","Question windows identical to clean", "Questions"],[(label(c), cells[MODELS[0],c,"mcq"]["windows_identical_to_clean"],n) for c in [*run.FULL, "grammarMax"] if cells[MODELS[0],c,"mcq"]["windows_identical_to_clean"] is not None])])
    if coverage:
        parts.append(table(["Passage","Approved sentence units","Eligible sentence units","Coverage"],[
            [pid,v["approved_sentence_units"],v["total_sentence_units"],f"{v['sentence_coverage']:.1%}"] for pid,v in sorted(coverage.items())]))
    parts.append("<h2>Multiple-choice response distribution</h2><p>E means the reader selected “根据这段文字无法判断”. The original GPT-4.1-mini scoring step maps unmatched free-text replies from the four primary reader configurations to a choice using only the reply and options. The last two columns give the number mapped and how many matched the key. These counts are already included in the score. The three additional configurations use the original direct parser.</p>")
    for model in MODELS:
        parts.extend([f"<details><summary>{escape(model)}</summary>", table(["Condition","Correct A–D","Incorrect A–D","E","Invalid","Total","Mapped","Mapped correct"],
          [(label(r["condition"]),r["correct"],r["wrong_ad"],r["cannot_tell"],r["invalid"],r["observed"],r["mapped_choices"],r["mapped_correct"]) for r in rows if r["form"]=="mcq" and r["model"]==model and r["complete"]]),"</details>"])
    parts.append("</html>")
    if completed:
        pdf_path = run.REPORT / (slug+"-figures.pdf")
        with NamedTemporaryFile(dir=run.REPORT, suffix=".pdf", delete=False) as output:
            tmp_path=Path(output.name)
        figures(tmp_path,title,cells)
        tmp_path.replace(pdf_path)
        parts.insert(3,f"<p><a href='{pdf_path.name}'>Download the nine figures for this set (PDF)</a></p>")
    with NamedTemporaryFile(mode="w", dir=run.REPORT, delete=False) as f:
        f.write("\n".join(parts))
    Path(f.name).replace(run.REPORT / (slug+".html"))
    print(study, sum(r["observed"] for r in rows), "reader responses;", sum(r["scored"] for r in rows), "scored;", "complete" if completed else "in progress")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", choices=run.STUDIES)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--monitor", action="store_true", help="Refresh while the readers and graders finish.")
    args = parser.parse_args()
    if args.monitor:
        while True:
            rows,_,_ = results(args.study)
            if all(r["complete"] for r in rows):
                break
            publish(args.study,False)
            time.sleep(90)
    publish(args.study, args.require_complete)
