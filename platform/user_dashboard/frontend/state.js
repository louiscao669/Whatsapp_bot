export const DEFAULT_API_BASE = "http://127.0.0.1:7860";

export const sampleDashboard = {
  participant: {
    id: "participant_sample_001",
    display_name: "Sample Participant",
    participant_id: "15551234567",
    profile_photo_url: ""
  },
  wallet: {
    balance: 18
  },
  xp_points: 0,
  lives: 0,
  settings: {
    language: "en",
    batch_size: 3
  },
  history_summary: {
    total_questions_answered: 12,
    total_batches_answered: 4,
    total_translation_hours_saved: 2.3,
    completion_score: 0.42
  },
  events: [
    { created_at: "2026-06-16T12:05:00Z", reason: "batch_completed_bonus", amount: 3, balance_after: 18 },
    { created_at: "2026-06-16T12:04:48Z", reason: "answer_completed", amount: 1, balance_after: 15 },
    { created_at: "2026-06-15T13:22:11Z", reason: "answer_completed", amount: 1, balance_after: 14 }
  ],
  badges: [
    { badge_type: "first_batch", title: "First Batch", description: "Completed the first question batch.", awarded_at: "2026-06-14T15:18:00Z" },
    { badge_type: "three_day_streak", title: "Three Day Streak", description: "Answered questions on three different days.", awarded_at: "2026-06-16T12:05:00Z" },
    { badge_type: "ten_answers", title: "Ten Answers", description: "Submitted ten answers.", awarded_at: "2026-06-16T12:05:00Z" }
  ],
  leaderboard: {
    scope: "language",
    language: "eng",
    week_start: "2026-06-15T00:00:00+00:00",
    week_end: "2026-06-22T00:00:00+00:00",
    current_user: { rank: 2, participant_id: "participant_sample_001", display_name: "Sample Participant", weekly_earned: 12, is_current_user: true },
    rows: [
      { rank: 1, participant_id: "participant_sample_002", display_name: "Mina", weekly_earned: 57, is_current_user: false },
      { rank: 2, participant_id: "participant_sample_001", display_name: "Sample Participant", weekly_earned: 42, is_current_user: true },
      { rank: 3, participant_id: "participant_sample_003", display_name: "Theo", weekly_earned: 33, is_current_user: false },
      { rank: 4, participant_id: "participant_sample_004", display_name: "Ana", weekly_earned: 25, is_current_user: false }
    ],
    teams: [
      { rank: 1, team_id: "team-1", display_name: "Team 1", weekly_earned: 157 },
      { rank: 2, team_id: "team-2", display_name: "Team 2", weekly_earned: 113 },
      { rank: 3, team_id: "team-3", display_name: "Team 3", weekly_earned: 92 },
      { rank: 4, team_id: "team-4", display_name: "Team 4", weekly_earned: 78 }
    ]
  },
  streak: {
    timezone: "America/Indiana/Indianapolis",
    current_daily_streak: 12,
    current_weekly_streak: 4,
    freeze_tokens: { available: 1, purchased: 1, awarded: 0, used: 0 },
    pause: { active: false, started_at: null },
    heatmap: Array.from({ length: 24 }, (_, index) => ({
      date: `2026-06-${String((index % 22) + 1).padStart(2, "0")}`,
      count: index % 5 === 0 ? 2 : index % 3 === 0 ? 1 : 0,
      level: index % 5 === 0 ? 3 : index % 3 === 0 ? 1 : 0
    }))
  },
  store: {
    items: [
      { item_id: "streak_freeze", title: "Streak Freeze", description: "Protects your streak for one missed day.", cost: 8, item_type: "consumable", max_owned: 3 },
      { item_id: "extra_life", title: "Extra Heart", description: "A saved recovery chance for future retry mechanics.", cost: 12, item_type: "consumable", max_owned: 3 },
      { item_id: "dashboard_background_sunrise", title: "Sunrise Background", description: "Changes your dashboard background to a warm sunrise color.", cost: 8, item_type: "cosmetic", max_owned: 1 }
    ],
    inventory: {
      streak_freeze: { owned: 1, max_owned: 3 },
      extra_life: { owned: 0, max_owned: 3 },
      dashboard_background_sunrise: { owned: 0, max_owned: 1 }
    }
  },
  cosmetics: {
    equipped: {
      profile_frame: null,
      dashboard_background: null
    }
  },
  journey: {
    chapters: [
      { title: "Luke 1", status: "continue", progress: 0.42 },
      { title: "Luke 2", status: "continue", progress: 0.2 }
    ]
  },
  daily_challenge: {
    title: "Daily challenge",
    body: "Answer today's question batch to keep your streak alive."
  },
  encouragements: [
    "Unlock the leadership board.",
    "Jesus loves you!"
  ]
};

export function emptyDashboard(participantId) {
  return {
    ...sampleDashboard,
    participant: {
      id: "",
      display_name: "Participant",
      participant_id: participantId,
      profile_photo_url: ""
    },
    wallet: { balance: 0 },
    events: [],
    badges: []
  };
}

export function parseParticipantIdFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const queryParticipantId =
    params.get("participant_id") || params.get("pid") || params.get("participant");
  if (queryParticipantId) {
    return queryParticipantId.trim();
  }

  const hashParticipantId = window.location.hash.replace(/^#\/?/, "").trim();
  if (hashParticipantId) {
    return hashParticipantId;
  }

  const decodedPath = decodeURIComponent(window.location.pathname);
  const marker = "/index.html/";
  const markerIndex = decodedPath.indexOf(marker);
  if (markerIndex >= 0) {
    return decodedPath.slice(markerIndex + marker.length).split("/")[0].trim();
  }

  return "";
}

export function apiBaseFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const explicit = params.get("api_base") || window.USER_DASHBOARD_API_BASE;
  if (explicit) {
    return explicit.replace(/\/$/, "");
  }
  const origin = window.location.origin;
  if (origin && !["http://127.0.0.1:5500", "http://localhost:5500"].includes(origin)) {
    return origin.replace(/\/$/, "");
  }
  return DEFAULT_API_BASE;
}

export function normalizeDashboard(payload) {
  return {
    ...sampleDashboard,
    ...payload,
    participant: { ...sampleDashboard.participant, ...(payload.participant || {}) },
    wallet: { ...sampleDashboard.wallet, ...(payload.wallet || {}) },
    history_summary: { ...sampleDashboard.history_summary, ...(payload.history_summary || {}) },
    leaderboard: { ...sampleDashboard.leaderboard, ...(payload.leaderboard || {}) },
    streak: { ...sampleDashboard.streak, ...(payload.streak || {}) },
    store: { ...sampleDashboard.store, ...(payload.store || {}) },
    cosmetics: { ...sampleDashboard.cosmetics, ...(payload.cosmetics || {}) },
    settings: { ...sampleDashboard.settings, ...(payload.settings || {}) },
    journey: { ...sampleDashboard.journey, ...(payload.journey || {}) }
  };
}

export async function fetchDashboard(participantId) {
  const response = await fetch(`${apiBaseFromLocation()}/user-dashboard/api/${encodeURIComponent(participantId)}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || `Request failed with ${response.status}`);
  }
  return normalizeDashboard(payload);
}

export async function postJson(participantId, path, body) {
  const response = await fetch(`${apiBaseFromLocation()}/user-dashboard/api/${encodeURIComponent(participantId)}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || `Request failed with ${response.status}`);
  }
  return normalizeDashboard(payload);
}

export async function postRawJson(participantId, path, body) {
  const response = await fetch(`${apiBaseFromLocation()}/user-dashboard/api/${encodeURIComponent(participantId)}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || `Request failed with ${response.status}`);
  }
  return payload;
}

export async function uploadProfilePhoto(participantId, file) {
  const formData = new FormData();
  formData.append("photo", file);
  const response = await fetch(`${apiBaseFromLocation()}/user-dashboard/api/${encodeURIComponent(participantId)}/profile-photo`, {
    method: "POST",
    body: formData
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.message || `Request failed with ${response.status}`);
  }
  return normalizeDashboard(payload);
}

export function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

export function pluralize(value, singular, plural) {
  return Math.abs(Number(value)) === 1 ? singular : plural;
}
