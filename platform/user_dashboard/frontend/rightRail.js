import { el } from "./dom.js";
import { formatNumber } from "./state.js";

export function renderRightRail(payload, actions = {}) {
  const balance = payload.wallet?.balance || 0;
  const xp = payload.xp_points || 0;
  const lives = payload.lives || 0;
  const daily = payload.daily_challenge || {};
  const encouragements = payload.encouragements || [];

  return el("aside", { className: "right-rail" }, [
    el("div", { className: "wallet-row", "aria-label": "Wallet totals" }, [
      walletStat("/user_dashboard/assets/points.svg", xp, "points", true),
      walletStat("/user_dashboard/assets/diamond.svg", balance, "diamond", true),
      walletStat("/user_dashboard/assets/heart.svg", lives, "heart", true)
    ]),
    el("section", {
      className: `rail-card daily-challenge-card ${daily.completed ? "completed" : ""}`
    }, [
      widgetIcon("/user_dashboard/assets/campfire.svg", "Daily challenge"),
      el("h2", { className: "widget-title", text: daily.title || "Daily challenge" }),
      el("p", {
        className: "widget-sub",
        text: daily.body || "Answer today's question batch to keep your streak alive."
      }),
      el("button", {
        type: "button",
        className: "widget-action widget-action-primary",
        onclick: () => actions.startDailyChallenge?.(),
        text: daily.completed ? "Completed" : "Start challenge"
      })
    ]),
    el("section", { className: "rail-card leaderboard-card" }, [
      widgetIcon("/user_dashboard/assets/ranking.svg", "Leaderboard"),
      el("h2", {
        className: "widget-title",
        text: encouragements[0] || "Unlock the leaderboard"
      }),
      el("p", {
        className: "widget-sub",
        text: "Keep contributing to climb the weekly board."
      }),
      el("button", {
        type: "button",
        className: "widget-action widget-action-secondary",
        onclick: () => actions.navigate?.("community"),
        text: "View board"
      })
    ])
  ]);
}

function widgetIcon(src, label) {
  return el("img", {
    className: "widget-icon",
    src,
    alt: "",
    "aria-hidden": "true",
    title: label
  });
}

function walletStat(icon, value, variant = "", isImage = false) {
  return el("span", { className: "wallet-stat" }, [
    isImage
      ? el("img", {
        className: `wallet-icon ${variant}`,
        src: icon,
        alt: "",
        "aria-hidden": "true"
      })
      : el("span", { className: `wallet-icon ${variant}`, text: icon }),
    el("span", { text: formatNumber(value) })
  ]);
}
