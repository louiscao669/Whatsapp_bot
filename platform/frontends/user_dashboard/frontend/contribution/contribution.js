import { el } from "../dom.js";
import { formatNumber } from "../state.js";

export function renderContribution(payload) {
  const history = payload.history_summary || {};
  const totalQuestions = Number(history.total_questions_answered || 0);
  const savedHours = Number(history.total_translation_hours_saved || estimateSavedHours(totalQuestions));
  const chapters = chapterActivity(history);
  const contributionCount = Number(payload.events?.filter((event) => Number(event.amount || 0) > 0).length || 0);
  const activeChapters = chapters.filter((chapter) => Number(chapter.answered_questions || 0) > 0).length;

  return el("section", { className: "contribution-page" }, [
    el("section", { className: "contribution-hero" }, [
      el("div", { className: "contribution-hero-left" }, [
        el("p", { className: "contribution-eyebrow", text: "Your contribution" }),
        el("h1", { className: "contribution-headline" }, [
          el("span", { text: formatNumber(totalQuestions) }),
          document.createTextNode(" questions"),
          el("br"),
          document.createTextNode("answered")
        ]),
        el("p", {
          className: "contribution-sub",
          text: totalQuestions > 0
            ? "Every answer you submit helps train better Bible translation AI."
            : "Every answer you submit helps train better Bible translation AI. Start answering to make an impact."
        })
      ]),
      el("div", { className: "contribution-impact" }, [
        el("strong", { text: `${savedHours.toFixed(1)}h` }),
        el("span", { text: "Time saved" }),
        el("p", { text: "in translation work" })
      ])
    ]),
    el("div", { className: "contribution-stats" }, [
      stat("Answered questions", formatNumber(totalQuestions), totalQuestions ? "Keep building the dataset" : "Answer your first today"),
      stat("Contributions", formatNumber(contributionCount), "Keep the streak alive"),
      stat("Active chapters", formatNumber(activeChapters), "Unlock by progressing")
    ]),
    el("section", { className: "chapter-log" }, [
      el("div", { className: "chapter-log-header" }, [
        el("div", {}, [
          el("p", { className: "contribution-log-eyebrow", text: "Luke" }),
          el("h2", { text: "Activity Log" })
        ])
      ]),
      el("div", { className: "chapter-activity-grid" }, chapters.map((chapter) => (
        el("span", {
          className: `chapter-cell level-${Number(chapter.level || 0)}`,
          title: `Luke ${chapter.chapter}: ${Number(chapter.answered_questions || 0)} answers`,
          text: String(chapter.chapter)
        })
      )))
    ])
  ]);
}

function chapterActivity(history) {
  const chapters = Array.isArray(history.chapter_activity) ? history.chapter_activity : [];
  if (chapters.length) {
    return chapters;
  }
  return Array.from({ length: 24 }, (_, index) => ({
    book: "Luke",
    chapter: index + 1,
    answered_questions: 0,
    level: 0
  }));
}

function estimateSavedHours(totalQuestions) {
  return totalQuestions * 0.18;
}

function stat(label, value, hint) {
  return el("article", { className: "stat-card contribution-stat-card" }, [
    el("span", { text: label }),
    el("strong", { text: value }),
    el("p", { className: "contribution-stat-hint", text: hint })
  ]);
}
