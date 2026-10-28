"""Recalculate saved Hard66 MCQs excluding E, and plot accuracy alongside E rates."""
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[2]
REPORTS = REPO / "evaluation/reports"
INPUTS = {
    "omission": REPORTS / "hard66_omission_mcq_2026-10-26/omission_four_modes_data.json",
    "mistranslation": REPORTS / "hard66_mistranslation_mcq_2026-10-26/mistranslation_four_modes_data.json",
    "grammar": REPORTS / "hard66_grammar_mcq_2026-10-26/grammar_four_modes_data.json",
    "google_wbw": REPORTS / "hard66_google_wbw_mcq_2026-10-26/google_wbw_four_modes_data.json",
}
CONFIGS = [
    {"label": "Llama 3.2 1B", "color": "#A86116", "marker": "s", "style": "-"},
    {"label": "Qwen 2.5 1.5B", "color": "#087EA4", "marker": "o", "style": "-"},
    {"label": "Qwen3 1.7B · thinking", "color": "#8C4AA5", "marker": "^", "style": "-"},
    {"label": "Qwen3 1.7B · no thinking", "color": "#2E7D32", "marker": "D", "style": "--"},
]


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


manifests, states, cells = {}, {}, {}


def verify_run(root):
    if root in manifests:
        return
    manifests[root] = read(root / "release.json")
    states[root] = read(root / "campaign_state.json")
    assert states[root]["status"] == "complete", root
    for name, digest in manifests[root]["input_hashes"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, (root, name)


def load_cell(root, pid, model, mode, method, stage):
    slug = model.replace(":", "").replace(".", "") + ("_nothink" if mode == "no_thinking" else "_think")
    directory = root / pid / slug / method
    if directory in cells:
        return cells[directory]
    saved = states[root]["cells"][f"{stage}/{model}/{pid}/{method}"]
    assert saved["status"] == "complete"
    for name, digest in saved["result_hashes"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest, (directory, name)
    answers = [r for r in read(directory / "generated_answers_target_llama.json") if r["q_type"] == "mcq"]
    scores = {r["id"]: r for r in read(directory / "scores_target_llama.json")["items"] if r["q_type"] == "mcq"}
    assert len(scores) == len(answers) == len({r["id"] for r in answers})
    result = []
    for answer in answers:
        score = scores[answer["id"]]
        selected = answer.get("selected_choice")
        failure = bool(answer.get("generation_error"))
        assert selected in ["A", "B", "C", "D", "E"] or (selected is None and failure), answer["id"]
        assert score["correct_choice"] in "ABCD"
        assert bool(score["direct_correct"]) == (selected == score["correct_choice"])
        if selected == "E":
            assert not score["direct_correct"]
            assert answer["selected_choice_text"] == answer["mcq_choices"]["E"]
            if failure:
                assert answer["selected_choice_source"] == "random_empty_response_fallback"
        if failure:
            assert not score["direct_correct"]
        if mode == "no_thinking":
            assert answer["answer_effort"]["thinking_chars"] == 0
        result.append({"id": answer["id"], "passage": pid, "selected_choice": selected,
                       "correct_choice": score["correct_choice"], "correct": bool(score["direct_correct"]),
                       "is_e": selected == "E" and not failure, "generation_error": failure,
                       "automatic_fallback_e": selected == "E" and failure,
                       "score_file_choice": score.get("selected_choice"), "source_directory": str(directory)})
    cells[directory] = result
    return result


reference, families, item_audit = None, {}, []
for family, path in INPUTS.items():
    original = read(path)
    points = []
    for prior in original["data"]:
        root = Path(prior.get("source_run") or original["source_runs"][prior["mode"] == "no_thinking"])
        verify_run(root)
        condition = prior.get("condition", prior.get(f"nominal_{family}_percent"))
        if condition == "100% target":
            methods = {pid: method for stage, model, pid, method in manifests[root]["cells"]}
            stage = "grammar"
        else:
            clean = condition in [0, "clean"]
            method = "omission/0%" if clean else "google_word_by_word" if family == "google_wbw" else f"{family}/{condition}%"
            methods = {pid: method for pid in original["passages"]}
            stage = "clean" if clean else "wbw" if family == "google_wbw" else family
        rows = [row for pid, method in methods.items()
                for row in load_cell(root, pid, prior["model"], prior["mode"], method, stage)]
        keys = {r["id"]: r["correct_choice"] for r in rows}
        if reference is None:
            reference = keys
        assert len(rows) == len(keys) == 65 and keys == reference
        count_e = sum(r["is_e"] for r in rows)
        n = len(rows)
        correct = sum(r["correct"] for r in rows)
        denominator = n - count_e
        assert correct == prior["correct"] and n == prior["n"]
        assert 0 <= correct <= denominator <= n
        accuracy = 100 * correct / denominator if denominator else None
        assert accuracy is None or accuracy >= prior["accuracy_percent"] - 1e-10
        point = {"model": prior["model"], "mode": prior["mode"], "label": prior["label"], "condition": condition,
                 "total_questions": n, "correct": correct, "e_count": count_e, "accuracy_denominator": denominator,
                 "accuracy_excluding_e_percent": accuracy, "e_rate_percent": 100 * count_e / n,
                 "original_accuracy_percent": prior["accuracy_percent"],
                 "generation_errors_retained": sum(r["generation_error"] for r in rows),
                 "automatic_fallback_e_retained": sum(r["automatic_fallback_e"] for r in rows),
                 "source_run": str(root)}
        points.append(point)
        item_audit.extend({"family": family, "model": prior["model"], "mode": prior["mode"], "condition": condition, **r} for r in rows)
    families[family] = {"source_report": str(path), "passages": original["passages"], "points": points}

assert len(item_audit) == 6240 and len(cells) == 870
for config in CONFIGS:
    baselines = [next(p for p in f["points"] if p["label"] == config["label"] and p["condition"] in [0, "clean"])
                 for f in families.values()]
    assert len({(p["correct"], p["e_count"], p["accuracy_denominator"]) for p in baselines}) == 1
report = {
    "accuracy_definition": "correct against the original clean answer key / (65 - E selections)",
    "e_rate_definition": "E selections / 65",
    "e_detection": "Use selected_choice from generated_answers_target_llama.json; legacy score files map E to null. Exclude only E choices without a generation error; two automatic random-fallback E labels are retained as failures, not counted as model abstentions.",
    "failure_policy": "Remove only explicit E selections. Generation failures remain in the accuracy denominator and count as incorrect.",
    "all_e_policy": "If every answer is E, conditional accuracy is undefined and is plotted as a gap.",
    "unique_saved_cells_verified": len(cells), "plotted_question_observations_including_repeated_clean_baselines": len(item_audit),
    "new_inference_performed": False,
    "grammar_note": "The final 100% target reached 345/358 sentence units (96.4%); the 5–30% levels use affected-clause content-character coverage. The axis break and connecting lines are retained as requested.",
    "families": families,
}
write(OUT / "accuracy_excluding_e_data.json", report)
write(OUT / "item_audit.json", item_audit)
for family, values in families.items():
    print(family, json.dumps([{k:p[k] for k in ["label", "condition", "correct", "e_count", "accuracy_denominator"]}
                             for p in values["points"] if p["condition"] in [0, "clean", 30, "100% target", "google_word_by_word"]]))

# Match the established colors and model markers. Dotted, hollow-marker lines
# show E rates; filled-marker lines retain the original model line styles.
os.environ["MPLCONFIGDIR"] = str(REPORTS / "hard66_grammar_mcq_2026-10-26/.matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "text.color": "#17212E", "axes.labelcolor": "#334155",
                     "xtick.color": "#475569", "ytick.color": "#475569", "svg.fonttype": "none"})
titles = {"omission": "Omission", "mistranslation": "Mistranslation", "grammar": "Grammar defects",
          "google_wbw": "Google word-by-word translation"}
outputs = []
for family, family_data in families.items():
    points = family_data["points"]
    if family == "google_wbw":
        conditions, positions = ["clean", "google_word_by_word"], [0, 1]
        labels, xlim, label_x = ["Clean baseline", "Google word-by-word"], (-.06, 1.23), 1.035
        xlabel = "Translation condition"
    elif family == "grammar":
        conditions = [0, 5, 10, 15, 20, 25, 30, "100% target"]
        positions = [0, 5, 10, 15, 20, 25, 30, 42]
        labels = [str(r) for r in conditions[:-1]] + ["100% target*"]
        xlim, label_x, xlabel = (-.6, 48), 43.1, "Grammar defect level (%)"
    else:
        conditions = positions = [0, 5, 10, 15, 20, 25, 30]
        labels = [str(r) for r in conditions]
        xlim, label_x, xlabel = (-.6, 34.4), 31, titles[family] + " level (%)"

    fig = plt.figure(figsize=(12.6, 8.6), facecolor="white")
    ax = fig.add_axes([.085, .245, .84, .46])
    fig.text(.085, .96, f"Hard66 · {titles[family]}", fontsize=24, weight="bold", va="top")
    fig.text(.085, .89, "Accuracy excluding E, with E selection shown separately", fontsize=14, color="#526171")
    endpoints, model_handles = [], []
    for config in CONFIGS:
        series = [p for p in points if p["label"] == config["label"]]
        ordered = [next(p for p in series if p["condition"] == condition) for condition in conditions]
        values = [p["accuracy_excluding_e_percent"] if p["accuracy_excluding_e_percent"] is not None else float("nan") for p in ordered]
        e_values = [p["e_rate_percent"] for p in ordered]
        color, marker = config["color"], config["marker"]
        handle, = ax.plot(positions, values, color=color, marker=marker, linestyle=config["style"], linewidth=2.6,
                          markersize=7.1, markeredgecolor="white", markeredgewidth=.8, label=config["label"], zorder=3)
        ax.plot(positions, e_values, color=color, marker=marker, linestyle=":", linewidth=2,
                markersize=6.6, markerfacecolor="white", markeredgecolor=color, markeredgewidth=1.4, zorder=3)
        model_handles.append(handle)
        endpoints.extend([(values[-1], color, False), (e_values[-1], color, True)])

    previous_y = -100
    for value, color, is_e in sorted(endpoints):
        if value != value:
            continue
        label_y = max(value, previous_y + 4.5)
        ax.annotate(f"{'E ' if is_e else ''}{value:.1f}%", xy=(positions[-1], value), xytext=(label_x, label_y),
                    color=color, fontsize=10.7, weight="bold", va="center",
                    arrowprops={"arrowstyle": "-", "color": color, "linewidth": .7}, zorder=5)
        previous_y = label_y

    ax.set(xlim=xlim, ylim=(-4, 100), xticks=positions, xticklabels=labels,
           yticks=range(0, 101, 20), xlabel=xlabel, ylabel="Accuracy / E selection rate")
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.xaxis.labelpad = 12
    ax.yaxis.labelpad = 11
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#E2E8F0", linewidth=.85)
    ax.spines["left"].set_color("#CBD5E1")
    ax.spines["bottom"].set_color("#CBD5E1")
    ax.tick_params(length=0, pad=9)
    if family == "grammar":
        ax.spines["bottom"].set_visible(False)
        transform = ax.get_xaxis_transform()
        for left, right in [(xlim[0], 34.2), (36.8, xlim[1])]:
            ax.plot([left, right], [0, 0], transform=transform, color="#94A3B8", linewidth=1.05, clip_on=False)
        ax.plot([34.2, 34.65, 35.1, 35.55, 36, 36.45, 36.8], [0, .016, -.016, .016, -.016, .016, 0],
                transform=transform, color="#475569", linewidth=1.5, clip_on=False, solid_joinstyle="round")

    fig.legend(model_handles, [c["label"] for c in CONFIGS], loc="upper left", bbox_to_anchor=(.076, .875),
               ncol=2, frameon=False, fontsize=11.5, handlelength=2.2, columnspacing=3.2, labelspacing=.85)
    metric_handles = [Line2D([0], [0], color="#334155", marker="o", linestyle="-", linewidth=2.4,
                             markerfacecolor="#334155", markersize=6),
                      Line2D([0], [0], color="#334155", marker="o", linestyle=":", linewidth=2,
                             markerfacecolor="white", markersize=6)]
    fig.legend(metric_handles, ["Accuracy excluding E · filled markers", "E selection rate · dotted, hollow markers"],
               loc="upper left", bbox_to_anchor=(.076, .775), ncol=2, frameon=False,
               fontsize=10.5, handlelength=2.5, columnspacing=2.7)
    fig.text(.085, .145, "Accuracy excluding E = correct ÷ (65 − E choices).   E rate = E choices ÷ 65.", fontsize=10.5, color="#526171")
    fig.text(.085, .105, "Original clean answer key; failed responses remain incorrect. 65 MCQs across 10 passages per condition.",
             fontsize=10.1, color="#526171")
    if family == "grammar":
        fig.text(.085, .065, "5–30%: affected-clause content-character coverage. *100% target: 96.4% sentence coverage (345/358).",
                 fontsize=9.9, color="#526171")
        fig.text(.085, .03, "Axis break compresses 30–100%; connecting lines are visual guides across different coverage measures.",
                 fontsize=9.6, color="#526171")
    else:
        note = "Google word-by-word is a single saved translation condition." if family == "google_wbw" else f"0% = clean baseline. {titles[family]} levels are nominal whole-passage rates."
        fig.text(.085, .065, note + " Answers use fixed local verse windows.", fontsize=10, color="#526171")
    for extension in ["png", "svg"]:
        output = OUT / f"{family}_accuracy_excluding_e_and_e_rate.{extension}"
        fig.savefig(output, dpi=200, facecolor="white")
        outputs.append(output)
    plt.close(fig)

from zipfile import ZipFile, ZIP_DEFLATED
with ZipFile(OUT / "all_four_graphs.zip", "w", compression=ZIP_DEFLATED) as archive:
    for output in outputs + [OUT / "accuracy_excluding_e_data.json"]:
        archive.write(output, output.name)
print(json.dumps({"graphs_created": 4, "verified_saved_cells": len(cells), "output_directory": str(OUT)}))
