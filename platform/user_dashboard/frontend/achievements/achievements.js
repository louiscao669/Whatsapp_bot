import { el } from "../dom.js";
import { formatNumber, pluralize } from "../state.js";

const BADGE_DEFINITIONS = [
  {
    badge_type: "first_response",
    title: "First Answer",
    description: "Submitted your first answer."
  },
  {
    badge_type: "completed_first_batch",
    title: "First Batch Complete",
    description: "Completed your first question batch."
  },
  {
    badge_type: "completed_5_questions",
    title: "Five Questions",
    description: "Completed 5 validation questions."
  },
  {
    badge_type: "completed_10_questions",
    title: "Ten Questions",
    description: "Completed 10 validation questions."
  },
  {
    badge_type: "completed_25_questions",
    title: "Twenty-Five Questions",
    description: "Completed 25 validation questions."
  },
  {
    badge_type: "streak_3_days",
    title: "Three-Day Streak",
    description: "Answered at least one question across 3 streak days."
  },
  {
    badge_type: "streak_7_days",
    title: "Seven-Day Streak",
    description: "Kept a validation streak for 7 days."
  },
  {
    badge_type: "streak_14_days",
    title: "Two-Week Resolver",
    description: "Maintained a 14-day validation streak."
  },
  {
    badge_type: "streak_30_days",
    title: "Thirty-Day Resolver",
    description: "Maintained a 30-day validation streak."
  }
];

export function renderAchievements(payload, state, actions) {
  const streak = payload.streak || {};
  const badges = payload.badges || [];
  const earnedBadgeCount = earnedSystemBadgeCount(badges);
  const daily = Number(streak.current_daily_streak || 0);
  const weekly = Number(streak.current_weekly_streak || 0);
  const freeze = streak.freeze_tokens?.available || 0;
  const pause = streak.pause || {};

  return el("section", { className: "achievements-page" }, [
    el("section", { className: "achievement-hero streak-hero" }, [
      el("div", { className: "streak-left" }, [
        el("div", { className: "daily-streak-title" }, [
          el("img", {
            className: "flame-big",
            src: "/user_dashboard/assets/streak_fire.svg",
            alt: "",
            "aria-hidden": "true"
          }),
          el("div", {}, [
            el("p", { className: "streak-label", text: "Daily streak" }),
            el("h1", { className: "streak-num", text: `${formatNumber(daily)} ${pluralize(daily, "day", "days")}` })
          ])
        ])
      ]),
      el("div", { className: "cal-wrap" }, [
        el("div", { className: "cal-label", text: "This month" }),
        el("div", { className: "streak-calendar cal-days", "aria-label": `${daily} day streak calendar` }, (
          Array.from({ length: calendarCellCount(daily) }, (_, index) => {
            const checked = index < daily;
            return el("span", {
              className: `streak-day cal-day ${checked ? "checked done" : ""} ${index === daily ? "today" : ""}`,
              style: checked ? `--delay:${Math.min(index, 20) * 90}ms` : "",
              title: checked ? `Streak day ${index + 1}` : "Future streak day"
            }, checked ? [
              el("img", {
                src: "/user_dashboard/assets/checkmark.svg",
                alt: "",
                "aria-hidden": "true"
              })
            ] : []);
          })
        ))
      ])
    ]),
    el("div", { className: "achievement-stats top-grid" }, [
      stat("Weekly streak", `${formatNumber(weekly)} ${pluralize(weekly, "week", "weeks")}`),
      breakBox(freeze, pause, actions)
    ]),
    el("section", { className: "trophy-collection badges-section" }, [
      el("div", { className: "trophy-heading badges-header" }, [
        el("div", {}, [
          el("p", { className: "trophy-kicker badges-title", text: "Badges" })
        ]),
        el("span", {
          className: "earned-pill",
          text: `${earnedBadgeCount}/${BADGE_DEFINITIONS.length} earned`
        })
      ]),
      el("div", { className: "badge-strip badges-grid" }, badgeNodes(badges))
    ])
  ]);
}

function breakBox(freeze, pause, actions) {
  const canPause = pause.active || freeze > 0;
  return el("article", { className: "break-card freeze-card" }, [
    el("div", { className: "freeze-left" }, [
      el("h2", { className: "fc-title", text: "Taking a break?" }),
      el("p", {
        className: "status-line fc-sub",
        text: pause.active
          ? `Paused for up to ${formatNumber(pause.max_days || 7)} days.`
          : `${formatNumber(freeze)} streak ${pluralize(freeze, "freeze", "freezes")} available.`
      })
    ]),
    el("button", {
      type: "button",
      className: "freeze-btn",
      disabled: !canPause,
      title: canPause ? "" : "You need a streak freeze to pause.",
      onclick: () => actions.setStreakPause(!pause.active),
      text: pause.active ? "Resume Streak" : "Use Freeze"
    })
  ]);
}

function calendarCellCount(daily) {
  return Math.max(21, Math.min(35, Math.ceil(Math.max(daily, 1) / 7) * 7));
}

function stat(label, value) {
  return el("article", { className: "stat-card achievement-stat-card" }, [
    el("span", { className: "stat-card-label", text: label }),
    el("strong", { className: "stat-card-val", text: value })
  ]);
}

function badgeNodes(badges) {
  const badgeByType = new Map((badges || []).map((badge) => [badge.badge_type, badge]));
  return BADGE_DEFINITIONS.map((definition, index) => (
    trophyCard(definition, badgeByType.get(definition.badge_type) || null, index)
  ));
}

function trophyCard(definition, badge, index) {
  const earned = Boolean(badge);
  const title = earned
    ? definition.title
    : "Locked Trophy";
  const description = earned
    ? badge.description || definition.description
    : definition.description;
  return el("article", { className: `badge badge-card ${earned ? "earned" : "locked"}` }, [
    el("div", { className: `trophy-icon badge-icon-wrap ${earned ? "earned-icon" : "locked-icon"}`, "aria-hidden": "true" }, [
      el("img", {
        src: badgeIconUrl(earned, index),
        alt: "",
        "aria-hidden": "true"
      })
    ]),
    el("div", { className: "trophy-copy" }, [
      el("strong", { className: `badge-name ${earned ? "" : "locked-name"}`, text: title }),
      el("p", { className: "badge-desc", text: description }),
      el("span", {
        className: `badge-status ${earned ? "earned-status" : "locked-status"}`,
        text: earned ? `Trophy ${index + 1} earned` : "Not unlocked"
      })
    ])
  ]);
}

function badgeIconUrl(earned, index) {
  if (!earned) {
    return "/user_dashboard/assets/unlocked_fire.svg";
  }
  if (index === 0) {
    return "/user_dashboard/assets/first_answer_badge.svg";
  }
  return "/user_dashboard/assets/achievement.svg";
}

function earnedSystemBadgeCount(badges) {
  const earnedTypes = new Set((badges || []).map((badge) => badge.badge_type));
  return BADGE_DEFINITIONS.filter((definition) => earnedTypes.has(definition.badge_type)).length;
}
