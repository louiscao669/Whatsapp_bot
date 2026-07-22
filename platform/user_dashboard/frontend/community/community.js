import { el } from "../dom.js";

export function renderCommunity(payload, state, actions) {
  const leaderboard = payload.leaderboard || {};
  const activeTab = state.communityTab || "individual";
  const rows = activeTab === "team"
    ? leaderboard.teams || []
    : leaderboard.rows || [];
  const participantId = payload.participant?.id || "";

  return el("section", { className: "community-page" }, [
    el("div", { className: "tabs" }, [
      tabButton("individual", "Individual", activeTab, actions.setCommunityTab),
      tabButton("team", "Team", activeTab, actions.setCommunityTab)
    ]),
    activeTab === "team"
      ? renderTeamControls(rows, actions)
      : null,
    renderPodium(rows, activeTab),
    renderLeaderboard(rows, activeTab, participantId)
  ]);
}

function tabButton(id, label, activeTab, onSelect) {
  return el("button", {
    type: "button",
    className: `tab-button ${activeTab === id ? "active" : ""}`,
    onclick: () => onSelect(id),
    text: label
  });
}

function renderTeamControls(rows, actions) {
  const currentTeam = rows.find((row) => row.is_current_user);
  const joinable = rows.filter((row) => !row.is_current_user && Number(row.member_count || 0) < 4);
  const teamSelect = el("select", {
    className: "search-input",
    disabled: currentTeam || !joinable.length
  }, joinable.map((row) => el("option", {
    value: row.team_id,
    text: `${row.display_name} (${row.member_count || 0}/4)`
  })));
  return el("div", { className: "team-controls" }, [
    el("div", { className: "team-search-wrap" }, [
      currentTeam
        ? el("div", { className: "team-membership", text: `Your team: ${currentTeam.display_name} (${currentTeam.member_count}/4)` })
        : teamSelect
    ]),
    el("div", { className: "community-actions" }, [
      !currentTeam ? el("button", {
        type: "button",
        className: "btn-join",
        disabled: !joinable.length,
        text: joinable.length ? "Join selected team" : "No open teams",
        onclick: () => teamSelect.value && actions.joinTeam(teamSelect.value)
      }) : null,
      !currentTeam ? el("button", {
        type: "button",
        className: "btn-create",
        text: "Create team",
        onclick: () => requestTeamName("Create team", "", actions.createTeam)
      }) : null,
      currentTeam?.is_creator ? el("button", {
        type: "button",
        className: "btn-create",
        text: "Change team name",
        onclick: () => requestTeamName(
          "Change team name",
          currentTeam.display_name,
          (name) => actions.renameTeam(currentTeam.team_id, name)
        )
      }) : null,
      currentTeam?.is_creator ? el("button", {
        type: "button",
        className: "btn-team-danger",
        text: "Remove team",
        onclick: () => actions.removeTeam(currentTeam.team_id, currentTeam.display_name)
      }) : null,
      currentTeam && !currentTeam.is_creator ? el("button", {
        type: "button",
        className: "btn-team-danger",
        text: "Leave team",
        onclick: () => actions.leaveTeam(currentTeam.team_id, currentTeam.display_name)
      }) : null
    ])
  ]);
}

function requestTeamName(title, value, onSubmit) {
  const name = window.prompt(title, value);
  if (name !== null && name.trim()) {
    onSubmit(name.trim());
  }
}

function renderPodium(rows, type) {
  const topRows = [rowByRank(rows, 2), rowByRank(rows, 1), rowByRank(rows, 3)];
  if (!rows.length) {
    return null;
  }
  return el("section", { className: "podium-card" }, [
    el("p", {
      className: "podium-label",
      text: type === "team" ? "This week's top teams" : "This week's top contributors"
    }),
    el("div", { className: "podium" }, topRows.map((row, index) => (
      row ? podiumItem(row, type, index) : el("div", { className: "podium-item podium-empty" })
    )))
  ]);
}

function podiumItem(row, type, index) {
  const rank = Number(row.rank || 0);
  const rankClass = rank === 1 ? "first" : rank === 2 ? "second" : "third";
  const name = displayName(row, type);
  return el("article", { className: `podium-item ${rankClass}` }, [
    rank === 1 ? el("div", { className: "podium-crown", text: "1" }) : null,
    el("div", { className: "pod-avatar", text: initials(name, type) }),
    el("strong", { className: "pod-name", text: name }),
    el("span", { className: "pod-score", text: `${score(row)} pts` }),
    el("div", { className: "pod-block" }, [
      el("span", { className: "pod-rank", text: String(index === 0 ? 2 : index === 1 ? 1 : 3) })
    ])
  ]);
}

function renderLeaderboard(rows, type, participantId) {
  if (!rows.length) {
    return el("div", { className: "empty-state", text: "No leaderboard activity yet." });
  }
  return el("div", { className: "leaderboard-list" }, rows.map((row) => (
    el("article", { className: `leaderboard-row ${isCurrentRow(row, participantId) ? "me" : ""}` }, [
      el("span", {
        className: `rank-num ${Number(row.rank || 0) <= 3 ? "top" : ""}`,
        text: row.rank ? String(row.rank) : "-"
      }),
      el("span", { className: `leader-avatar rank-${row.rank || ""}`, text: initials(displayName(row, type), type) }),
      el("span", { className: "leader-row-body" }, [
        el("span", { className: "leader-name", text: displayName(row, type) }),
        isCurrentRow(row, participantId) ? el("span", { className: "you-badge", text: "you" }) : null,
        el("span", { className: "leader-sub", text: rowSub(row, type) })
      ]),
      el("span", { className: "leader-score-wrap" }, [
        el("span", { className: "leader-score", text: score(row).toLocaleString() }),
        el("span", { className: "leader-delta", text: "pts" })
      ])
    ])
  )));
}

function rowByRank(rows, rank) {
  return rows.find((row) => Number(row.rank || 0) === rank) || null;
}

function displayName(row, type) {
  return row.display_name || (type === "team" ? "Team" : "Name");
}

function score(row) {
  return Number(row.weekly_earned || 0);
}

function rowSub(row, type) {
  if (type === "team") {
    const count = Number(row.member_count || (Array.isArray(row.members) ? row.members.length : 0));
    return `${count}/4 members`;
  }
  return "Weekly contribution";
}

function initials(name, type) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) {
    return type === "team" ? "T" : "U";
  }
  if (type === "team") {
    const number = parts.find((part) => /\d+/.test(part));
    return number ? `T${number.replace(/\D/g, "").slice(0, 2)}` : "T";
  }
  return parts.slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

function isCurrentRow(row, participantId) {
  if (row.is_current_user) {
    return true;
  }
  if (participantId && Array.isArray(row.member_ids)) {
    return row.member_ids.includes(participantId);
  }
  return false;
}
