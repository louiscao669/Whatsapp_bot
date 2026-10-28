"""Compare clean and Google word-by-word MCQ results with the shared four-mode legend."""
import hashlib
import json
import os
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[2]
ROOT = REPO / "evaluation/runs/hard66_full_ladder_2026-10-23"
NO_THINK = REPO / "evaluation/runs/hard66_google_word_by_word_mcq_qwen317b_nothink_2026-10-26"
os.environ["MPLCONFIGDIR"] = str(OUT / ".matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

CONFIGS = [
    {"model": "llama3.2:1b", "mode": "standard", "label": "Llama 3.2 1B", "color": "#A86116", "marker": "s", "style": "-", "root": ROOT},
    {"model": "qwen2.5:1.5b", "mode": "standard", "label": "Qwen 2.5 1.5B", "color": "#087EA4", "marker": "o", "style": "-", "root": ROOT},
    {"model": "qwen3:1.7b", "mode": "thinking", "label": "Qwen3 1.7B · thinking", "color": "#8C4AA5", "marker": "^", "style": "-", "root": ROOT},
    {"model": "qwen3:1.7b", "mode": "no_thinking", "label": "Qwen3 1.7B · no thinking", "color": "#2E7D32", "marker": "D", "style": "--", "root": NO_THINK},
]
CONDITIONS = [("clean", "clean", "omission/0%"), ("google_word_by_word", "wbw", "google_word_by_word")]


def read(path):
    return json.loads(path.read_text())


manifests, states = {}, {}
for root in [ROOT, NO_THINK]:
    manifests[root] = read(root / "release.json")
    states[root] = read(root / "campaign_state.json")
    assert states[root]["status"] == "complete"
    for name, digest in manifests[root]["input_hashes"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, (root, name)
passages = manifests[NO_THINK]["passages"]
assert len(passages) == 10
reference, data, verified_cells = None, [], 0
for config in CONFIGS:
    root, model = config["root"], config["model"]
    no_think = config["mode"] == "no_thinking"
    slug = model.replace(":", "").replace(".", "") + ("_nothink" if no_think else "_think")
    for condition, stage, method in CONDITIONS:
        rows, answers = [], []
        for pid in passages:
            directory = root / pid / slug / method
            saved = states[root]["cells"][f"{stage}/{model}/{pid}/{method}"]
            assert saved["status"] == "complete"
            for name, digest in saved["result_hashes"].items():
                assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
            for name in ["passage_target.txt", "passage_target_decanonicalized.txt"]:
                assert (directory / name).read_bytes() == (root / pid / method / name).read_bytes()
                assert (directory / name).read_bytes() == (ROOT / pid / method / name).read_bytes()
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
        data.append({"model": model, "mode": config["mode"], "label": config["label"], "condition": condition,
                     "correct": correct, "n": 65, "accuracy_percent": 100 * correct / 65,
                     "generation_errors": sum(bool(r.get("generation_error")) for r in answers),
                     "truncated_answers": sum(r.get("answer_effort", {}).get("done_reason") == "length" for r in answers),
                     "source_run": str(root)})
assert verified_cells == 80 and len(data) == 8
comparisons = []
for c in CONFIGS:
    clean, wbw = [d for d in data if d["label"] == c["label"]]
    comparisons.append({"label": c["label"], "clean_correct": clean["correct"], "wbw_correct": wbw["correct"],
                        "change_percentage_points": wbw["accuracy_percent"] - clean["accuracy_percent"]})
report = {"source_runs": [str(ROOT), str(NO_THINK)], "question_format": "mcq", "passages": passages,
          "verified_cells": verified_cells, "model_responses": 65 * len(data),
          "notes": ["Same 65 reviewed MCQs and clean answer key in both conditions; answers use fixed local verse windows.",
                    "Google word-by-word is a single saved translation condition; no percentage ladder was evaluated.",
                    "All responses remain in the denominator; generation failures count as incorrect.",
                    "Qwen3 no-thinking word-by-word results were newly evaluated; its verified clean baseline was reused.",
                    "Observed accuracy only; lines connect the two categorical conditions."],
          "data": data, "comparisons": comparisons}
(OUT / "google_wbw_four_modes_data.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "text.color": "#17212E", "axes.labelcolor": "#334155",
                     "xtick.color": "#475569", "ytick.color": "#475569", "svg.fonttype": "none"})
fig = plt.figure(figsize=(11.8, 7.6), facecolor="white")
ax = fig.add_axes([.085, .22, .84, .49])
fig.text(.085, .94, "Hard66 · Google word-by-word translation", fontsize=23, weight="bold", va="top")
fig.text(.085, .88, "Three models · four configurations · 65 MCQs across 10 passages per condition", fontsize=12.5, color="#526171")
endpoints = [[], []]
for c in CONFIGS:
    values = [d["accuracy_percent"] for d in data if d["label"] == c["label"]]
    ax.plot([0, 1], values, color=c["color"], marker=c["marker"], linestyle=c["style"], linewidth=2.6,
            markersize=8, markeredgecolor="white", markeredgewidth=.85, label=c["label"])
    for i, value in enumerate(values):
        endpoints[i].append((value, c["color"]))
for x, points in enumerate(endpoints):
    previous_y = -100
    for value, color in sorted(points):
        label_y = max(value, previous_y + 5.5)
        ax.annotate(f"{value:.1f}%", xy=(x, value), xytext=(x + (.045 if x else -.045), label_y),
                    color=color, fontsize=11, weight="bold", va="center", ha="left" if x else "right",
                    arrowprops={"arrowstyle": "-", "color": color, "linewidth": .7})
        previous_y = label_y
ax.set(xlim=(-.16, 1.17), ylim=(0, 100), xticks=[0, 1], xticklabels=["Clean baseline", "Google word-by-word"],
       yticks=range(0, 101, 20), ylabel="MCQ accuracy")
ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
ax.yaxis.labelpad = 11
ax.grid(axis="y", color="#E2E8F0", linewidth=.85)
ax.set_axisbelow(True)
ax.spines["left"].set_color("#CBD5E1")
ax.spines["bottom"].set_color("#CBD5E1")
ax.tick_params(length=0, pad=11)
fig.legend(*ax.get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(.075, .84),
           ncol=2, frameon=False, fontsize=11.4, handlelength=2.2, columnspacing=3.2, labelspacing=.85)
fig.text(.085, .105, "Google word-by-word is a single translation condition. Both conditions use the same fixed local verse windows.",
         fontsize=10.2, color="#526171")
fig.text(.085, .065, "All 65 responses are included per point. Failed generations count as incorrect against the clean answer key.",
         fontsize=9.8, color="#526171")
for extension in ["png", "svg"]:
    fig.savefig(OUT / f"google_wbw_mcq_four_modes.{extension}", dpi=200, facecolor="white")
plt.close(fig)
print(json.dumps({"verified_cells": verified_cells, "comparisons": comparisons}))
