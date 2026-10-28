"""Plot verified grammar ladder results and the separate every-sentence condition."""
import hashlib
import json
import os
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[2]
RUNS = REPO / "evaluation/runs"
CLEAN = RUNS / "hard66_full_ladder_2026-10-23"
GRAMMAR = RUNS / "hard66_grammar_full_2026-10-24"
NO_THINK = RUNS / "hard66_grammar_mcq_qwen317b_nothink_2026-10-26"
SENTENCE = RUNS / "hard66_grammar_sentence_all_mcq_models_2026-10-25"
SENTENCE_NO_THINK = RUNS / "hard66_grammar_sentence_all_mcq_qwen317b_nothink_2026-10-25"
os.environ["MPLCONFIGDIR"] = str(OUT / ".matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

CONFIGS = [
    {"model": "llama3.2:1b", "mode": "standard", "label": "Llama 3.2 1B", "color": "#A86116", "marker": "s", "style": "-", "sentence_root": SENTENCE / "llama321b"},
    {"model": "qwen2.5:1.5b", "mode": "standard", "label": "Qwen 2.5 1.5B", "color": "#087EA4", "marker": "o", "style": "-", "sentence_root": SENTENCE / "qwen2515b"},
    {"model": "qwen3:1.7b", "mode": "thinking", "label": "Qwen3 1.7B · thinking", "color": "#8C4AA5", "marker": "^", "style": "-", "sentence_root": SENTENCE / "qwen317b"},
    {"model": "qwen3:1.7b", "mode": "no_thinking", "label": "Qwen3 1.7B · no thinking", "color": "#2E7D32", "marker": "D", "style": "--", "sentence_root": SENTENCE_NO_THINK},
]
RATES = [0, 5, 10, 15, 20, 25, 30]


def read(path):
    return json.loads(path.read_text())


roots = [CLEAN, GRAMMAR, NO_THINK] + [c["sentence_root"] for c in CONFIGS]
manifests, states = {}, {}
for root in roots:
    manifests[root] = read(root / "release.json")
    states[root] = read(root / "campaign_state.json")
    assert states[root]["status"] == "complete", root
    for name, digest in manifests[root]["input_hashes"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, (root, name)

coverage = manifests[SENTENCE_NO_THINK]["coverage"]
passages = list(coverage)
assert len(passages) == 10
assert all(manifests[c["sentence_root"]]["coverage"] == coverage for c in CONFIGS)
approved = sum(c["approved_sentence_units"] for c in coverage.values())
total = sum(c["total_sentence_units"] for c in coverage.values())
assert (approved, total) == (345, 358)
reference, data = None, []
verified_cells = 0
for config in CONFIGS:
    model = config["model"]
    no_think = config["mode"] == "no_thinking"
    slug = model.replace(":", "").replace(".", "") + ("_nothink" if no_think else "_think")
    for level in RATES + ["100% target"]:
        sentence = isinstance(level, str)
        if sentence:
            root = config["sentence_root"]
            methods = {pid: method for stage, m, pid, method in manifests[root]["cells"] if m == model}
        else:
            root = NO_THINK if no_think else CLEAN if level == 0 else GRAMMAR
            methods = {pid: f"{'omission' if level == 0 else 'grammar'}/{level}%" for pid in passages}
        rows, answers = [], []
        for pid in passages:
            method = methods[pid]
            directory = root / pid / slug / method
            stage = "clean" if level == 0 else "grammar"
            saved = states[root]["cells"][f"{stage}/{model}/{pid}/{method}"]
            assert saved["status"] == "complete"
            for name, digest in saved["result_hashes"].items():
                assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
            for name in ["passage_target.txt", "passage_target_decanonicalized.txt"]:
                assert (directory / name).read_bytes() == (root / pid / method / name).read_bytes()
            rows.extend(r for r in read(directory / "scores_target_llama.json")["items"] if r["q_type"] == "mcq")
            answers.extend(r for r in read(directory / "generated_answers_target_llama.json") if r["q_type"] == "mcq")
            verified_cells += 1
        keyed = {r["id"]: r["correct_choice"] for r in rows}
        answer_map = {r["id"]: r for r in answers}
        if reference is None:
            reference = keyed
        assert len(rows) == len(keyed) == len(answers) == len(answer_map) == 65
        assert keyed == reference and answer_map.keys() == keyed.keys()
        for row in rows:
            assert row["direct_correct"] == (row["selected_choice"] == row["correct_choice"])
            if answer_map[row["id"]].get("generation_error"):
                assert row["direct_correct"] is False
        if no_think:
            assert states[root].get("no_think") is True
            assert all(a.get("answer_effort", {}).get("thinking_chars") == 0 for a in answers)
        correct = sum(r["direct_correct"] for r in rows)
        data.append({"model": model, "mode": config["mode"], "label": config["label"],
                     "condition": level, "coverage_measure": "sentence_units" if sentence else "affected_clause_content_characters",
                     "actual_sentence_coverage_percent": 100 * approved / total if sentence else None,
                     "correct": correct, "n": 65, "accuracy_percent": 100 * correct / 65,
                     "generation_errors": sum(bool(r.get("generation_error")) for r in answers),
                     "truncated_answers": sum(r.get("answer_effort", {}).get("done_reason") == "length" for r in answers),
                     "source_run": str(root)})

assert verified_cells == 320 and len(data) == 32
report = {"source_runs": [str(r) for r in roots], "question_format": "mcq", "passages": passages,
          "verified_cells": verified_cells, "model_responses": 65 * len(data), "sentence_coverage": coverage,
          "notes": ["Same 65 reviewed MCQs and clean answer key at every point; answers use fixed local verse windows.",
                    "0% is clean. The 5–30% levels use nominal affected-clause content-character coverage.",
                    "The separate 100% target condition reached 345/358 sentence units (96.4%); 13 units remain unchanged.",
                    "The final condition uses a different coverage measure; there is no connecting line from 30%.",
                    "All responses remain in the denominator; generation failures count as incorrect.",
                    "Qwen3 no-thinking positive ladder levels were newly evaluated; its verified clean baseline was reused.",
                    "Observed accuracy only; connecting lines are not fitted trends."], "data": data}
(OUT / "grammar_four_modes_data.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "text.color": "#17212E", "axes.labelcolor": "#334155",
                     "xtick.color": "#475569", "ytick.color": "#475569", "svg.fonttype": "none"})
fig = plt.figure(figsize=(11.8, 7.6), facecolor="white")
ax = fig.add_axes([.085, .25, .62, .46])
final_ax = fig.add_axes([.78, .25, .16, .46], sharey=ax)
fig.text(.085, .94, "Hard66 · Accuracy under grammar defects", fontsize=23, weight="bold", va="top")
fig.text(.085, .88, "Three models · four configurations · 65 MCQs across 10 passages per condition", fontsize=12.5, color="#526171")

endpoints = []
for i, config in enumerate(CONFIGS):
    series = [d for d in data if d["model"] == config["model"] and d["mode"] == config["mode"]]
    values = [next(d["accuracy_percent"] for d in series if d["condition"] == rate) for rate in RATES]
    ax.plot(RATES, values, color=config["color"], marker=config["marker"], linestyle=config["style"], linewidth=2.6,
            markersize=7.2, markeredgecolor="white", markeredgewidth=.85, label=config["label"])
    value = next(d["accuracy_percent"] for d in series if d["condition"] == "100% target")
    x = [-.05, -.08, .04, .02][i]
    final_ax.plot(x, value, color=config["color"], marker=config["marker"], linestyle="none",
                  markersize=8.5, markeredgecolor="white", markeredgewidth=.85)
    endpoints.append((value, config["color"], x))

previous_y = -100
for value, color, x in sorted(endpoints):
    label_y = max(value, previous_y + 6)
    final_ax.annotate(f"{value:.1f}%", xy=(x, value), xytext=(.30, label_y), color=color,
                      fontsize=11, weight="bold", va="center",
                      arrowprops={"arrowstyle": "-", "color": color, "linewidth": .7})
    previous_y = label_y

ax.set(xlim=(-.6, 30.8), ylim=(0, 100), xticks=RATES, yticks=range(0, 101, 20),
       xlabel="Grammar defect level (%)", ylabel="MCQ accuracy")
ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
final_ax.set(xlim=(-.6, .85), xticks=[0], xticklabels=["100% target*"])
final_ax.tick_params(axis="y", labelleft=False)
final_ax.spines["left"].set_visible(False)
final_ax.set_title("Sentence-level condition", fontsize=10.5, color="#526171", pad=12)
for axes in [ax, final_ax]:
    axes.xaxis.labelpad = 11
    axes.yaxis.labelpad = 11
    axes.grid(axis="y", color="#E2E8F0", linewidth=.85)
    axes.set_axisbelow(True)
    axes.spines["left"].set_color("#CBD5E1")
    axes.spines["bottom"].set_color("#CBD5E1")
    axes.tick_params(length=0, pad=9)
fig.add_artist(Line2D([.745, .745], [.25, .71], transform=fig.transFigure,
                      color="#CBD5E1", linewidth=1, linestyle=(0, (3, 4))))
fig.legend(*ax.get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(.075, .84),
           ncol=2, frameon=False, fontsize=11.4, handlelength=2.2, columnspacing=3.2, labelspacing=.85)
fig.text(.085, .13, "0% = clean. 5–30% = nominal content-character coverage of affected clauses.", fontsize=10.2, color="#526171")
fig.text(.085, .09, "*100% target: 345/358 sentence units affected (96.4% actual). Shown separately because coverage measures differ.",
         fontsize=10.2, color="#526171")
fig.text(.085, .05, "All 65 responses are included per point. Failed generations count as incorrect against the clean answer key.",
         fontsize=9.8, color="#526171")
for extension in ["png", "svg"]:
    fig.savefig(OUT / f"grammar_mcq_four_modes_0_30_and_100.{extension}", dpi=200, facecolor="white")
plt.close(fig)
print(json.dumps({"verified_cells": verified_cells, "data": [
    {"label": c["label"], "correct": [d["correct"] for d in data if d["label"] == c["label"]]} for c in CONFIGS]}))
