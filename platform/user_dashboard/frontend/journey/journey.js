import { el } from "../dom.js";

export function renderJourney(payload) {
  const chapters = payload.journey?.chapters || [
    { title: "Luke 1", status: "continue" },
    { title: "Luke 2", status: "continue" }
  ];
  const completeCount = chapters.filter((chapter) => chapter.status === "complete").length;
  const activeChapter = chapters.find((chapter) => chapter.status !== "complete") || chapters[0];
  const averageProgress = chapters.length
    ? chapters.reduce((sum, chapter) => sum + normalizedProgress(chapter), 0) / chapters.length
    : 0;

  return el("section", { className: "journey-page" }, [
    el("section", { className: "journey-hero" }, [
      el("div", {}, [
        el("p", { className: "journey-kicker", text: "Current path" }),
        el("h1", { text: activeChapter?.title || "Luke" }),
        el("p", {
          className: "journey-copy",
          text: "Keep moving through the chapter path and complete each question batch."
        })
      ]),
      el("div", { className: "journey-progress-ring", style: `--progress:${Math.round(averageProgress * 100)}%` }, [
        el("strong", { text: `${Math.round(averageProgress * 100)}%` }),
        el("span", { text: "overall" })
      ])
    ]),
    el("div", { className: "journey-stats" }, [
      stat("Chapters done", `${completeCount}/${chapters.length}`),
      stat("Active chapter", activeChapter?.title || "None"),
      stat("Next reward", "Daily streak")
    ]),
    el("section", { className: "journey-list" }, chapters.map(renderChapter))
  ]);
}

function renderChapter(chapter, index) {
  const progress = normalizedProgress(chapter);
  const complete = chapter.status === "complete";
  const active = !complete && progress > 0;
  return el("article", { className: `chapter-card ${complete ? "complete" : ""} ${active ? "active" : ""}` }, [
    el("div", { className: "chapter-art", "aria-hidden": "true" }, [
      el("span", { className: "chapter-node", text: String(index + 1) })
    ]),
    el("div", { className: "chapter-body" }, [
      el("div", { className: "chapter-heading" }, [
        el("h2", { text: chapter.title }),
        el("span", {
          className: `chapter-status ${complete ? "complete" : active ? "active" : ""}`,
          text: complete ? "Complete" : "In progress"
        })
      ]),
      el("p", {
        className: "journey-copy",
        text: complete
          ? "You finished this chapter. Review it any time."
          : "Continue this chapter to unlock the next step."
      }),
      el("div", { className: "chapter-progress-track", "aria-hidden": "true" }, [
        el("span", { style: `width:${Math.round(progress * 100)}%` })
      ])
    ]),
    el("button", {
      type: "button",
      className: `chapter-action ${active ? "primary-btn" : ""}`,
      text: complete ? "Review" : "Continue"
    })
  ]);
}

function stat(label, value) {
  return el("article", { className: "journey-stat" }, [
    el("span", { text: label }),
    el("strong", { text: value })
  ]);
}

function normalizedProgress(chapter) {
  if (chapter.status === "complete") {
    return 1;
  }
  return Math.max(0, Math.min(1, Number(chapter.progress || 0)));
}
