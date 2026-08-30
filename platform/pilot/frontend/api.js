/**
 * Pilot API client.
 *
 * Every request is `cache: "no-store"` and every response carries
 * `Cache-Control: no-store` from the server: PostgreSQL is the source of truth
 * for questions, submissions and completion, and a browser cache must never
 * stand in for it.
 */

export function parseParticipantIdFromLocation(location = window.location) {
  const params = new URLSearchParams(location.search);
  const fromQuery =
    params.get("participant_id") || params.get("pid") || params.get("participant");
  if (fromQuery) {
    return fromQuery.trim();
  }
  const path = decodeURIComponent(location.pathname);
  const match = path.match(/^\/pilot\/(?!api\b|static\b|t\b)([^/]+)/);
  return match ? match[1].trim() : "";
}

export function createPilotApi(participantId, { origin = window.location.origin } = {}) {
  const base = `${origin.replace(/\/$/, "")}/pilot/api/${encodeURIComponent(participantId)}`;

  async function request(path, { method = "GET", body } = {}) {
    const response = await fetch(`${base}${path}`, {
      method,
      cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.message || `Request failed with ${response.status}`);
    }
    return payload;
  }

  return {
    /** Current question or completion state. Never returns a future question. */
    getState() {
      return request("/question");
    },

    /** Whether the consent screen is due, plus the approved text to render. */
    getConsent() {
      return request("/consent");
    },

    /** Record the decision. `agreed` is always sent explicitly, never defaulted. */
    recordConsent(agreed, consentVersion) {
      return request("/consent", {
        method: "POST",
        body: { agreed: Boolean(agreed), consent_version: consentVersion || undefined }
      });
    },

    startSession(consentVersion) {
      return request("/session", {
        method: "POST",
        body: { consent_version: consentVersion || undefined }
      });
    },

    markViewed(body) {
      return request("/question/viewed", { method: "POST", body });
    },

    submitAnswer(body) {
      return request("/answers", { method: "POST", body });
    },

    /**
     * Durable timing checkpoint. Fired ONLY on visibility change / page hide /
     * submit -- never on a schedule. `sendBeacon` first so the write survives a
     * tab being closed; `fetch(..., {keepalive: true})` where it is missing.
     */
    checkpoint(body) {
      const url = `${base}/question/checkpoint`;
      const payload = JSON.stringify(body);
      if (navigator.sendBeacon) {
        const blob = new Blob([payload], { type: "application/json" });
        if (navigator.sendBeacon(url, blob)) {
          return Promise.resolve(true);
        }
      }
      return fetch(url, {
        method: "POST",
        cache: "no-store",
        keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: payload
      })
        .then(() => true)
        .catch(() => false);
    }
  };
}
