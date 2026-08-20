/**
 * Active-page timing for one pilot question.
 *
 * The study's primary duration metric is how long the question page was
 * VISIBLE, not how long the tab existed. So:
 *
 *  - "active" means `document.visibilityState === "visible"`, and nothing else.
 *    `document.hasFocus()` is deliberately NOT consulted: clicking the address
 *    bar, opening a browser menu or using devtools drops focus while the
 *    participant is still reading, which would silently truncate the segment.
 *  - durations come from an injected monotonic clock (`performance.now()` in
 *    the browser), never from a time-of-day clock, so a clock adjustment or an
 *    NTP step cannot corrupt a measurement.
 *  - time only ever accumulates in closed segments, so nothing is counted
 *    twice and hidden stretches are simply never opened.
 *
 * Nothing in this module runs on a schedule: segments are opened and closed by
 * events only, and no periodic reporting of any kind happens here.
 */

const MAX_ACTIVE_MS = 6 * 60 * 60 * 1000;

function sanitizeMs(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return 0;
  }
  return Math.min(numeric, MAX_ACTIVE_MS);
}

function sanitizeCount(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return 0;
  }
  return Math.floor(numeric);
}

/**
 * Accumulates the time spent in ONE boolean state, plus a count of how many
 * times that state flipped. Used three times over (see createAttentionTimers):
 * for page visibility, for window focus and for the passage being on screen.
 *
 * @param {object} options
 * @param {() => number} options.now      monotonic clock, in milliseconds
 * @param {number} [options.activeMs]     already-accumulated time (reload restore)
 * @param {number} [options.visibilityChangeCount] state flips so far
 */
export function createActiveTimer({ now, activeMs = 0, visibilityChangeCount = 0 } = {}) {
  if (typeof now !== "function") {
    throw new TypeError("createActiveTimer requires a now() function");
  }

  let accumulatedMs = sanitizeMs(activeMs);
  let changeCount = sanitizeCount(visibilityChangeCount);
  let segmentStartedAt = null;

  function openSegmentMs() {
    if (segmentStartedAt === null) {
      return 0;
    }
    return Math.max(0, now() - segmentStartedAt);
  }

  const timer = {
    get running() {
      return segmentStartedAt !== null;
    },

    /** Total visible time so far, including any segment still open. */
    get activeMs() {
      return Math.round(Math.min(accumulatedMs + openSegmentMs(), MAX_ACTIVE_MS));
    },

    get visibilityChangeCount() {
      return changeCount;
    },

    /** Open a segment. A no-op while one is already open, so a duplicate
     *  `visible` event cannot restart (and therefore lose) the current one. */
    start() {
      if (segmentStartedAt === null) {
        segmentStartedAt = now();
      }
      return timer;
    },

    /** Close the open segment and bank it. Idempotent. */
    pause() {
      if (segmentStartedAt !== null) {
        accumulatedMs = Math.min(accumulatedMs + openSegmentMs(), MAX_ACTIVE_MS);
        segmentStartedAt = null;
      }
      return timer;
    },

    /**
     * Handle a visibility transition.
     * @param {boolean} visible
     * @param {{countChange?: boolean}} [options] `countChange: false` for the
     *   initial render, which is not a *change*.
     */
    setVisible(visible, { countChange = true } = {}) {
      if (countChange) {
        changeCount += 1;
      }
      return visible ? timer.start() : timer.pause();
    },

    /** Close the final segment (used at submit). Everything after this call --
     *  the network round trip, the server's scoring work -- is excluded. */
    stop() {
      timer.pause();
      return timer.snapshot();
    },

    snapshot() {
      return {
        activeMs: timer.activeMs,
        visibilityChangeCount: changeCount,
        running: timer.running
      };
    }
  };

  return timer;
}

const STORAGE_PREFIX = "pilot.trial.";

/**
 * Per-question scratch state kept in `sessionStorage`, and nothing else.
 *
 * Scope is deliberately narrow: the current assignment id, the unsubmitted
 * answer draft, the accumulated durations and the current segment state.
 * Never a question that has not been presented, never a score, never a
 * completion state -- the server is the only authority on all three, and a
 * cached copy of any of them would be a way to leak or fake study data.
 */
export function createTrialStore(storage) {
  function key(assignmentId) {
    return `${STORAGE_PREFIX}${assignmentId}`;
  }

  return {
    read(assignmentId) {
      if (!storage || !assignmentId) {
        return null;
      }
      try {
        const raw = storage.getItem(key(assignmentId));
        if (!raw) {
          return null;
        }
        const parsed = JSON.parse(raw);
        return {
          assignmentId,
          draft: typeof parsed.draft === "string" ? parsed.draft : "",
          submissionId:
            typeof parsed.submissionId === "string" ? parsed.submissionId : null,
          activeMs: sanitizeMs(parsed.activeMs),
          focusedMs: sanitizeMs(parsed.focusedMs),
          onscreenMs: sanitizeMs(parsed.onscreenMs),
          visibilityChangeCount: sanitizeCount(parsed.visibilityChangeCount),
          focusChangeCount: sanitizeCount(parsed.focusChangeCount),
          reloadCount: sanitizeCount(parsed.reloadCount),
          segmentOpen: parsed.segmentOpen === true
        };
      } catch (error) {
        return null;
      }
    },

    write(assignmentId, state) {
      if (!storage || !assignmentId) {
        return;
      }
      try {
        storage.setItem(
          key(assignmentId),
          JSON.stringify({
            draft: state.draft || "",
            submissionId: state.submissionId || null,
            activeMs: sanitizeMs(state.activeMs),
            focusedMs: sanitizeMs(state.focusedMs),
            onscreenMs: sanitizeMs(state.onscreenMs),
            visibilityChangeCount: sanitizeCount(state.visibilityChangeCount),
            focusChangeCount: sanitizeCount(state.focusChangeCount),
            reloadCount: sanitizeCount(state.reloadCount),
            segmentOpen: state.segmentOpen === true
          })
        );
      } catch (error) {
        /* sessionStorage can be unavailable in private/restricted contexts. */
      }
    },

    /** Only ever called after the server has acknowledged the submission. */
    clear(assignmentId) {
      if (!storage || !assignmentId) {
        return;
      }
      try {
        storage.removeItem(key(assignmentId));
      } catch (error) {
        /* ignore */
      }
    }
  };
}

/**
 * The three durations the pilot records for one question.
 *
 * They deliberately measure different things, and each is wrong in a KNOWN
 * direction, so reading them together brackets the truth:
 *
 *   activeMs    page visible. The primary metric, definition unchanged. Blind
 *               to occlusion (a covered window still reports visible), so it
 *               is an UPPER bound on reading time.
 *   focusedMs   page visible AND the window has focus. Catches "browser on
 *               screen but the participant is in another app", and in exchange
 *               drops moments when focus went to the address bar, a browser
 *               menu or an OS notification -- so it is a LOWER bound.
 *   onscreenMs  page visible AND the passage element intersects the viewport.
 *               Answers a different question entirely: was the text they were
 *               asked to read actually on screen, or scrolled past?
 *
 * Focus is NEVER allowed to gate activeMs. That is the whole point of keeping
 * them separate: a metric that stopped on every address-bar click would
 * silently truncate attentive readers.
 */
export function createAttentionTimers({
  now,
  activeMs = 0,
  focusedMs = 0,
  onscreenMs = 0,
  visibilityChangeCount = 0,
  focusChangeCount = 0
} = {}) {
  const active = createActiveTimer({ now, activeMs, visibilityChangeCount });
  const focused = createActiveTimer({
    now,
    activeMs: focusedMs,
    visibilityChangeCount: focusChangeCount
  });
  const onscreen = createActiveTimer({ now, activeMs: onscreenMs });

  let state = { visible: false, focused: false, onscreen: false };

  function apply(next, { countChanges = true } = {}) {
    const previous = state;
    state = { ...state, ...next };
    // Focus and on-screen are only meaningful while the page is visible; a
    // hidden tab is neither focused nor showing anything.
    const isVisible = state.visible;
    if (previous.visible !== state.visible) {
      active.setVisible(state.visible, { countChange: countChanges });
    } else if (!active.running && state.visible) {
      active.start();
    }
    const isFocused = isVisible && state.focused;
    const wasFocused = previous.visible && previous.focused;
    focused.setVisible(isFocused, { countChange: countChanges && wasFocused !== isFocused });
    onscreen.setVisible(isVisible && state.onscreen, { countChange: false });
    return timers;
  }

  const timers = {
    get state() {
      return { ...state };
    },
    get running() {
      return active.running;
    },
    /** Apply a state change, e.g. `{ visible: true }` or `{ focused: false }`. */
    update(next, options) {
      return apply(next, options);
    },
    /** Initial render: set the starting state without counting it as a change. */
    begin(next) {
      return apply(next, { countChanges: false });
    },
    /** Close every open segment (used at submit). */
    stop() {
      active.pause();
      focused.pause();
      onscreen.pause();
      return timers.snapshot();
    },
    snapshot() {
      return {
        activeMs: active.activeMs,
        focusedMs: focused.activeMs,
        onscreenMs: onscreen.activeMs,
        visibilityChangeCount: active.visibilityChangeCount,
        focusChangeCount: focused.visibilityChangeCount,
        running: active.running
      };
    }
  };

  return timers;
}

/**
 * Accumulated time to resume from after a reload: the larger of the durable
 * server checkpoint and this tab's own record. Taking the max means neither a
 * beacon that never landed nor a tab that lost its storage can shorten a
 * measurement.
 */
export function resumeActiveMs(serverActiveMs, storedActiveMs) {
  return Math.max(sanitizeMs(serverActiveMs), sanitizeMs(storedActiveMs));
}

export const __testing = { sanitizeMs, sanitizeCount, MAX_ACTIVE_MS };
