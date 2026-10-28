"""Restyle the verified grammar results with a compressed axis and connected final points."""
import json
import os
from pathlib import Path

OUT = Path(__file__).resolve().parent
os.environ["MPLCONFIGDIR"] = str(OUT / ".matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

report = json.loads((OUT / "grammar_four_modes_data.json").read_text())
data = report["data"]
assert len(data) == 32 and all(d["n"] == 65 for d in data)
CONFIGS = [
    {"label": "Llama 3.2 1B", "color": "#A86116", "marker": "s", "style": "-"},
    {"label": "Qwen 2.5 1.5B", "color": "#087EA4", "marker": "o", "style": "-"},
    {"label": "Qwen3 1.7B · thinking", "color": "#8C4AA5", "marker": "^", "style": "-"},
    {"label": "Qwen3 1.7B · no thinking", "color": "#2E7D32", "marker": "D", "style": "--"},
]
RATES = [0, 5, 10, 15, 20, 25, 30]
# The final condition is drawn at 42 to compress the unevaluated interval.
FINAL_X = 42
X = RATES + [FINAL_X]
CONDITIONS = RATES + ["100% target"]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "text.color": "#17212E", "axes.labelcolor": "#334155",
                     "xtick.color": "#475569", "ytick.color": "#475569", "svg.fonttype": "none"})
fig = plt.figure(figsize=(11.8, 7.6), facecolor="white")
ax = fig.add_axes([.085, .25, .84, .46])
fig.text(.085, .94, "Hard66 · Accuracy under grammar defects", fontsize=23, weight="bold", va="top")
fig.text(.085, .88, "Three models · four configurations · 65 MCQs across 10 passages per condition", fontsize=12.5, color="#526171")

endpoints, plotted = [], []
for config in CONFIGS:
    series = [d for d in data if d["label"] == config["label"]]
    assert len(series) == len(CONDITIONS)
    values = [next(d["accuracy_percent"] for d in series if d["condition"] == c) for c in CONDITIONS]
    for condition, value in zip(CONDITIONS, values):
        row = next(d for d in series if d["condition"] == condition)
        assert value == 100 * row["correct"] / row["n"]
    ax.plot(X, values, color=config["color"], marker=config["marker"], linestyle=config["style"], linewidth=2.6,
            markersize=7.2, markeredgecolor="white", markeredgewidth=.85, label=config["label"])
    endpoints.append((values[-1], config["color"]))
    plotted.append({"label": config["label"], "display_x": X, "accuracy_percent": values})

previous_y = -100
for value, color in sorted(endpoints):
    label_y = max(value, previous_y + 5.5)
    ax.annotate(f"{value:.1f}%", xy=(FINAL_X, value), xytext=(43.1, label_y), color=color,
                fontsize=11, weight="bold", va="center",
                arrowprops={"arrowstyle": "-", "color": color, "linewidth": .7})
    previous_y = label_y

ax.set(xlim=(-.6, 46.4), ylim=(0, 100), xticks=X,
       xticklabels=[str(r) for r in RATES] + ["100% target*"], yticks=range(0, 101, 20),
       xlabel="Grammar defect level (%)", ylabel="MCQ accuracy")
ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
ax.xaxis.labelpad = 11
ax.yaxis.labelpad = 11
ax.set_axisbelow(True)
# Draw the horizontal grid without its zero line, leaving room for the axis break.
for y in range(20, 101, 20):
    ax.axhline(y, color="#E2E8F0", linewidth=.85, zorder=0)
ax.spines["left"].set_color("#CBD5E1")
ax.spines["bottom"].set_visible(False)
axis_transform = ax.get_xaxis_transform()
for left, right in [(-.6, 34.2), (36.8, 46.4)]:
    ax.plot([left, right], [0, 0], transform=axis_transform, color="#94A3B8", linewidth=1.05, clip_on=False)
ax.plot([34.2, 34.65, 35.10, 35.55, 36.0, 36.45, 36.8],
        [0, .016, -.016, .016, -.016, .016, 0], transform=axis_transform,
        color="#475569", linewidth=1.5, clip_on=False, solid_joinstyle="round")
ax.tick_params(length=0, pad=9)
fig.legend(*ax.get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(.075, .84),
           ncol=2, frameon=False, fontsize=11.4, handlelength=2.2, columnspacing=3.2, labelspacing=.85)
fig.text(.085, .13, "0% = clean. 5–30% = nominal content-character coverage of affected clauses.", fontsize=10.2, color="#526171")
fig.text(.085, .09, "*100% target: 345/358 sentence units affected (96.4% actual); this uses a different coverage measure.",
         fontsize=10.2, color="#526171")
fig.text(.085, .05, "Axis break compresses 30–100%. Connecting lines guide the eye; no intermediate results are implied.",
         fontsize=9.8, color="#526171")
for extension in ["png", "svg"]:
    fig.savefig(OUT / f"grammar_mcq_four_modes_axis_break.{extension}", dpi=200, facecolor="white")
plt.close(fig)

report["notes"] = [n for n in report["notes"] if "no connecting line" not in n]
report["notes"].append("At the user's request, all series connect 30% to the 100% target across a compressed x-axis interval. The final condition uses a different coverage measure; connecting segments are visual guides, not interpolated results.")
report["plot_layout"] = {"conditions": CONDITIONS, "display_x": X, "axis_break_display_x": [34.2, 36.8]}
(OUT / "grammar_four_modes_axis_break_data.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"points": sum(len(s["accuracy_percent"]) for s in plotted), "data_unchanged": report["data"] == data,
                  "png": str(OUT / "grammar_mcq_four_modes_axis_break.png")}))
