"""Verified MCQ omission curves for three Hard66 models in four configurations."""
import hashlib
import json
import os
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[2]
ROOT = REPO / "evaluation/runs/hard66_full_ladder_2026-10-23"
NO_THINK_ROOT = REPO / "evaluation/runs/hard66_omission_mcq_qwen317b_nothink_2026-10-26"
os.environ["MPLCONFIGDIR"] = str(OUT / ".matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

CONFIGS = [
    {"model": "llama3.2:1b", "mode": "standard", "label": "Llama 3.2 1B", "color": "#A86116", "marker": "s", "style": "-", "root": ROOT},
    {"model": "qwen2.5:1.5b", "mode": "standard", "label": "Qwen 2.5 1.5B", "color": "#087EA4", "marker": "o", "style": "-", "root": ROOT},
    {"model": "qwen3:1.7b", "mode": "thinking", "label": "Qwen3 1.7B · thinking", "color": "#8C4AA5", "marker": "^", "style": "-", "root": ROOT},
    {"model": "qwen3:1.7b", "mode": "no_thinking", "label": "Qwen3 1.7B · no thinking", "color": "#2E7D32", "marker": "D", "style": "--", "root": NO_THINK_ROOT},
]
RATES = [0, 5, 10, 15, 20, 25, 30]
state = json.loads((ROOT / "campaign_state.json").read_text())
passages = sorted({key.split("/")[2] for key in state["cells"]})
assert len(passages) == 10
reference = None
data = []
for config in CONFIGS:
    model, label, root = config["model"], config["label"], config["root"]
    state = json.loads((root / "campaign_state.json").read_text())
    assert state["status"] == "complete"
    slug = model.replace(":", "").replace(".", "") + ("_nothink" if config["mode"] == "no_thinking" else "_think")
    for rate in RATES:
        rows, answers = [], []
        for pid in passages:
            directory = root / pid / slug / f"omission/{rate}%"
            key = f"{'clean' if rate == 0 else 'omission'}/{model}/{pid}/omission/{rate}%"
            saved = state["cells"][key]
            assert saved["status"] == "complete"
            for name in ["scores_target_llama.json", "generated_answers_target_llama.json"]:
                assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == saved["result_hashes"][name]
            rows.extend(r for r in json.loads((directory / "scores_target_llama.json").read_text())["items"] if r["q_type"] == "mcq")
            answers.extend(r for r in json.loads((directory / "generated_answers_target_llama.json").read_text()) if r["q_type"] == "mcq")
        keyed = {r["id"]: r["correct_choice"] for r in rows}
        answer_map = {r["id"]: r for r in answers}
        if reference is None:
            reference = keyed
        assert len(rows) == len(keyed) == len(answers) == len(answer_map) == 65
        assert keyed == reference and answer_map.keys() == keyed.keys()
        for row in rows:
            if answer_map[row["id"]].get("generation_error"):
                assert row["direct_correct"] is False
        if config["mode"] == "no_thinking":
            assert all(a.get("answer_effort", {}).get("thinking_chars") == 0 for a in answers)
        correct = sum(r["direct_correct"] for r in rows)
        data.append({"model": model, "mode": config["mode"], "label": label, "nominal_omission_percent": rate,
                     "correct": correct, "n": 65, "accuracy_percent": correct / 65 * 100,
                     "generation_errors": sum(bool(r.get("generation_error")) for r in answers)})

report = {"source_runs": [str(ROOT), str(NO_THINK_ROOT)], "question_format": "mcq", "passages": passages,
          "verified_cells": 280, "model_responses": 1820,
          "notes": ["Same 65 reviewed MCQs and clean answer key at every point.",
                    "0% is the clean baseline; x-axis is nominal whole-passage omission.",
                    "Models answer from the same curated local verse windows.",
                    "All responses remain in the denominator; generation failures count as incorrect.",
                    "Qwen3 1.7B has separate thinking and no-thinking curves; the smaller models use standard inference.",
                    "Observed accuracy only; connecting lines are not fitted trends."], "data": data}
(OUT / "omission_four_modes_data.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "text.color": "#17212E", "axes.labelcolor": "#334155",
                     "xtick.color": "#475569", "ytick.color": "#475569",
                     "svg.fonttype": "none"})
fig = plt.figure(figsize=(11.8, 7.6), facecolor="white")
ax = fig.add_axes([.085, .22, .84, .49])
fig.text(.085, .94, "Hard66 · Accuracy under omission", fontsize=23, weight="bold", va="top")
fig.text(.085, .88, "Three models · four configurations · 65 MCQs across 10 passages per level", fontsize=12.5, color="#526171")

endpoints = []
for config in CONFIGS:
    values = [next(d["accuracy_percent"] for d in data if d["model"] == config["model"]
                   and d["mode"] == config["mode"] and d["nominal_omission_percent"] == rate) for rate in RATES]
    ax.plot(RATES, values, color=config["color"], marker=config["marker"], linestyle=config["style"], linewidth=2.6,
            markersize=7.2, markeredgecolor="white", markeredgewidth=.85, label=config["label"])
    endpoints.append((values[-1], config["color"]))
previous_y = -100
for value, color in sorted(endpoints):
    label_y = max(value, previous_y + 5)
    ax.annotate(f"{value:.1f}%", xy=(30, value), xytext=(31.0, label_y),
                color=color, fontsize=11, weight="bold", va="center",
                arrowprops={"arrowstyle": "-", "color": color, "linewidth": .7})
    previous_y = label_y
ax.set(xlim=(-.6, 33.2), ylim=(0, 100), xticks=RATES, yticks=range(0, 101, 20),
       xlabel="Omission level (%)", ylabel="MCQ accuracy")
ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
ax.xaxis.labelpad = 11
ax.yaxis.labelpad = 11
ax.grid(axis="y", color="#E2E8F0", linewidth=.85)
ax.set_axisbelow(True)
ax.spines["left"].set_color("#CBD5E1")
ax.spines["bottom"].set_color("#CBD5E1")
ax.tick_params(length=0, pad=9)
fig.legend(*ax.get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(.075, .84),
           ncol=2, frameon=False, fontsize=11.4, handlelength=2.2, columnspacing=3.2, labelspacing=.85)
fig.text(.085, .105, "0% = clean baseline. Omission levels are nominal passage rates; answers use fixed local verse windows.",
         fontsize=10.2, color="#526171")
fig.text(.085, .065, "All responses are included. Failures count as incorrect (Qwen3 thinking: 1 at 25% and 1 at 30%).",
         fontsize=9.8, color="#526171")
fig.savefig(OUT / "omission_mcq_four_modes.png", dpi=200, facecolor="white")
fig.savefig(OUT / "omission_mcq_four_modes.svg", facecolor="white")
plt.close(fig)
print(json.dumps({"png": str(OUT / "omission_mcq_four_modes.png"), "svg": str(OUT / "omission_mcq_four_modes.svg"), "verified_cells": 280}))
