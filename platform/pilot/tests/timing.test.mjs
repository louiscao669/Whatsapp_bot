/**
 * Client half of the pilot timing contract.
 *
 * Run from the repository root:
 *   node --test platform/pilot/tests/
 *
 * The clock is injected, so these assert exact millisecond arithmetic rather
 * than sleeping and hoping. The server half (started_at stamping, monotonic
 * checkpoints, submission closing the trial) is in
 * platform/tests/test_pilot_service.py.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import test from "node:test";

import {
  createActiveTimer,
  createAttentionTimers,
  createTrialStore,
  resumeActiveMs
} from "../frontend/timing.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(HERE, "..", "frontend");

/** A controllable stand-in for `performance.now()`. */
function fakeClock(start = 0) {
  let value = start;
  return {
    now: () => value,
    advance(ms) {
      value += ms;
      return value;
    }
  };
}

function memoryStorage() {
  const map = new Map();
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
    get size() {
      return map.size;
    }
  };
}

test("a question rendered while the page is hidden accrues no active time", () => {
  const clock = fakeClock();
  const timer = createActiveTimer({ now: clock.now });

  // Hidden at render: the client never opens a segment.
  timer.setVisible(false, { countChange: false });
  clock.advance(30_000);

  assert.equal(timer.activeMs, 0);
  assert.equal(timer.running, false);
});

test("timing starts only once the question is visible", () => {
  const clock = fakeClock();
  const timer = createActiveTimer({ now: clock.now });

  timer.setVisible(true, { countChange: false });
  clock.advance(4_000);

  assert.equal(timer.activeMs, 4_000);
  assert.equal(timer.running, true);
});

test("active time pauses when the page becomes hidden", () => {
  const clock = fakeClock();
  const timer = createActiveTimer({ now: clock.now });

  timer.setVisible(true, { countChange: false });
  clock.advance(5_000);
  timer.setVisible(false);
  clock.advance(60_000);

  assert.equal(timer.activeMs, 5_000);
  assert.equal(timer.running, false);
});

test("active time resumes when the page becomes visible again", () => {
  const clock = fakeClock();
  const timer = createActiveTimer({ now: clock.now });

  timer.setVisible(true, { countChange: false });
  clock.advance(5_000);
  timer.setVisible(false);
  clock.advance(60_000);
  timer.setVisible(true);
  clock.advance(3_000);

  assert.equal(timer.activeMs, 8_000);
  assert.equal(timer.visibilityChangeCount, 2);
});

test("hidden time is excluded no matter how many times visibility flips", () => {
  const clock = fakeClock();
  const timer = createActiveTimer({ now: clock.now });

  timer.setVisible(true, { countChange: false });
  for (let index = 0; index < 5; index += 1) {
    clock.advance(1_000); // visible
    timer.setVisible(false);
    clock.advance(10_000); // hidden -- must not count
    timer.setVisible(true);
  }
  timer.pause();

  assert.equal(timer.activeMs, 5_000);
  assert.equal(timer.visibilityChangeCount, 10);
});

test("a duplicate visible event does not restart the open segment", () => {
  const clock = fakeClock();
  const timer = createActiveTimer({ now: clock.now });

  timer.setVisible(true, { countChange: false });
  clock.advance(2_000);
  timer.start(); // e.g. pageshow firing while already visible
  clock.advance(1_000);

  assert.equal(timer.activeMs, 3_000);
});

test("a reload restores accumulated active time and keeps counting", () => {
  const store = createTrialStore(memoryStorage());
  const assignmentId = "assignment-1";
  const before = createActiveTimer({ now: fakeClock().now });

  // --- first page life ---
  const clockA = fakeClock();
  const timerA = createActiveTimer({ now: clockA.now });
  timerA.setVisible(true, { countChange: false });
  clockA.advance(7_000);
  timerA.pause(); // pagehide checkpoint
  store.write(assignmentId, {
    draft: "half an answer",
    submissionId: null,
    activeMs: timerA.activeMs,
    visibilityChangeCount: timerA.visibilityChangeCount,
    reloadCount: 0,
    segmentOpen: false
  });

  // --- after reload: performance.now() restarts from zero ---
  const restored = store.read(assignmentId);
  assert.equal(restored.draft, "half an answer");
  const clockB = fakeClock();
  const timerB = createActiveTimer({
    now: clockB.now,
    activeMs: resumeActiveMs(0, restored.activeMs),
    visibilityChangeCount: restored.visibilityChangeCount
  });
  timerB.setVisible(true, { countChange: false });
  clockB.advance(3_000);

  assert.equal(before.activeMs, 0);
  assert.equal(timerB.activeMs, 10_000);
});

test("the durable server checkpoint wins when the tab's copy is behind", () => {
  // A beacon landed but the tab's own write was lost: resume from the server.
  assert.equal(resumeActiveMs(9_000, 4_000), 9_000);
  assert.equal(resumeActiveMs(0, 4_000), 4_000);
  assert.equal(resumeActiveMs(-5, Number.NaN), 0);
});

test("submitting closes the final segment and excludes network + scoring time", () => {
  const clock = fakeClock();
  const timer = createActiveTimer({ now: clock.now });

  timer.setVisible(true, { countChange: false });
  clock.advance(6_000);
  const snapshot = timer.stop(); // fired before the request goes out

  clock.advance(2_500); // network round trip
  clock.advance(45_000); // server-side scoring

  assert.equal(snapshot.activeMs, 6_000);
  assert.equal(snapshot.running, false);
  assert.equal(timer.activeMs, 6_000, "the timer stays closed after submit");
});

test("the draft and timing cache are cleared only on acknowledgement", () => {
  const storage = memoryStorage();
  const store = createTrialStore(storage);

  store.write("assignment-1", {
    draft: "pending answer",
    submissionId: "sub-1",
    activeMs: 1_200,
    visibilityChangeCount: 1,
    reloadCount: 0,
    segmentOpen: true
  });
  assert.equal(storage.size, 1);
  assert.equal(store.read("assignment-1").submissionId, "sub-1");

  store.clear("assignment-1");
  assert.equal(storage.size, 0);
  assert.equal(store.read("assignment-1"), null);
});

test("stored timing is sanitized, so a tampered cache cannot inflate it", () => {
  const storage = memoryStorage();
  const store = createTrialStore(storage);
  storage.setItem(
    "pilot.trial.assignment-1",
    JSON.stringify({ activeMs: -50, visibilityChangeCount: -3, draft: 42 })
  );

  const restored = store.read("assignment-1");

  assert.equal(restored.activeMs, 0);
  assert.equal(restored.visibilityChangeCount, 0);
  assert.equal(restored.draft, "");
});

test("the pilot frontend emits no periodic heartbeat", () => {
  for (const name of ["app.js", "api.js", "timing.js"]) {
    const source = readFileSync(join(FRONTEND, name), "utf8");
    for (const forbidden of ["setInterval", "setTimeout", "requestIdleCallback", "heartbeat"]) {
      assert.equal(
        source.includes(forbidden),
        false,
        `${name} must not use ${forbidden}: pilot timing is event-driven only`
      );
    }
  }
});

test("the pilot frontend never expires a question or shows a countdown", () => {
  const source = readFileSync(join(FRONTEND, "app.js"), "utf8");
  for (const forbidden of ["expire", "deadline", "countdown", "timeLimit", "TIME_LIMIT"]) {
    assert.equal(source.includes(forbidden), false, `app.js must not reference ${forbidden}`);
  }
});

test("the pilot frontend uses the monotonic clock and visibility, not focus", () => {
  const app = readFileSync(join(FRONTEND, "app.js"), "utf8");
  const timing = readFileSync(join(FRONTEND, "timing.js"), "utf8");

  assert.ok(app.includes("performance.now()"), "durations must come from performance.now()");
  assert.ok(app.includes('document.visibilityState === "visible"'));
  assert.ok(app.includes('addEventListener("visibilitychange"'));
  assert.ok(app.includes('addEventListener("pagehide"'));
  assert.ok(app.includes('addEventListener("pageshow"'));
  assert.equal(timing.includes("Date.now()"), false, "timing must not use a wall clock");
});

// --------------------------------------------------- attention measures
test("losing window focus pauses focused time but NOT active time", () => {
  // The guarantee the whole split exists for: an address-bar click, a browser
  // menu or an OS notification must not truncate a reader's active time.
  const clock = fakeClock();
  const timers = createAttentionTimers({ now: clock.now });

  timers.begin({ visible: true, focused: true, onscreen: true });
  clock.advance(5_000);
  timers.update({ focused: false }); // clicked the address bar
  clock.advance(3_000);
  timers.update({ focused: true });
  clock.advance(2_000);

  const snapshot = timers.snapshot();
  assert.equal(snapshot.activeMs, 10_000, "active time ignores focus entirely");
  assert.equal(snapshot.focusedMs, 7_000, "focused time excludes the unfocused gap");
  assert.equal(snapshot.focusChangeCount, 2);
  assert.equal(snapshot.visibilityChangeCount, 0, "focus is not a visibility change");
});

test("focused time is a lower bound and active time an upper bound", () => {
  const clock = fakeClock();
  const timers = createAttentionTimers({ now: clock.now });

  timers.begin({ visible: true, focused: false, onscreen: true });
  clock.advance(4_000);

  const snapshot = timers.snapshot();
  assert.ok(snapshot.focusedMs <= snapshot.activeMs);
  assert.equal(snapshot.focusedMs, 0);
  assert.equal(snapshot.activeMs, 4_000);
});

test("hiding the page stops all three measures", () => {
  const clock = fakeClock();
  const timers = createAttentionTimers({ now: clock.now });

  timers.begin({ visible: true, focused: true, onscreen: true });
  clock.advance(6_000);
  timers.update({ visible: false, focused: false });
  clock.advance(90_000);

  const snapshot = timers.snapshot();
  assert.equal(snapshot.activeMs, 6_000);
  assert.equal(snapshot.focusedMs, 6_000);
  assert.equal(snapshot.onscreenMs, 6_000);
});

test("scrolling the passage out of view stops only the on-screen measure", () => {
  const clock = fakeClock();
  const timers = createAttentionTimers({ now: clock.now });

  timers.begin({ visible: true, focused: true, onscreen: true });
  clock.advance(3_000);
  timers.update({ onscreen: false }); // scrolled down to the answer box
  clock.advance(8_000);

  const snapshot = timers.snapshot();
  assert.equal(snapshot.onscreenMs, 3_000);
  assert.equal(snapshot.activeMs, 11_000, "they are still reading the question");
  assert.equal(snapshot.focusedMs, 11_000);
});

test("submitting closes all three segments at once", () => {
  const clock = fakeClock();
  const timers = createAttentionTimers({ now: clock.now });

  timers.begin({ visible: true, focused: true, onscreen: true });
  clock.advance(9_000);
  const snapshot = timers.stop();
  clock.advance(30_000); // network + scoring

  assert.deepEqual(
    [snapshot.activeMs, snapshot.focusedMs, snapshot.onscreenMs],
    [9_000, 9_000, 9_000]
  );
  assert.deepEqual(
    [timers.snapshot().activeMs, timers.snapshot().focusedMs, timers.snapshot().onscreenMs],
    [9_000, 9_000, 9_000]
  );
});

test("all three measures survive a reload", () => {
  const store = createTrialStore(memoryStorage());
  const clockA = fakeClock();
  const timersA = createAttentionTimers({ now: clockA.now });
  timersA.begin({ visible: true, focused: true, onscreen: true });
  clockA.advance(5_000);
  timersA.update({ onscreen: false });
  clockA.advance(5_000);
  const before = timersA.stop();
  store.write("a1", { draft: "", ...before, reloadCount: 0, segmentOpen: false });

  const restored = store.read("a1");
  const clockB = fakeClock();
  const timersB = createAttentionTimers({
    now: clockB.now,
    activeMs: restored.activeMs,
    focusedMs: restored.focusedMs,
    onscreenMs: restored.onscreenMs,
    focusChangeCount: restored.focusChangeCount
  });
  timersB.begin({ visible: true, focused: true, onscreen: true });
  clockB.advance(1_000);

  const after = timersB.snapshot();
  assert.equal(after.activeMs, 11_000);
  assert.equal(after.focusedMs, 11_000);
  assert.equal(after.onscreenMs, 6_000, "on-screen time did not accrue while scrolled away");
});

test("the passage observer is scoped to the question, not to page scrolling", () => {
  const app = readFileSync(join(FRONTEND, "app.js"), "utf8");

  assert.ok(app.includes("new IntersectionObserver"));
  assert.ok(app.includes("threshold: 0"), "any part of the passage in view counts");
  assert.ok(app.includes("observer.disconnect()"), "must be torn down with the question");
  assert.ok(
    app.includes('window.addEventListener("focus"') &&
      app.includes('window.addEventListener("blur"'),
    "focus transitions must be observed"
  );
});

test("the pilot frontend caches only the four permitted keys, in sessionStorage", () => {
  const app = readFileSync(join(FRONTEND, "app.js"), "utf8");
  const timing = readFileSync(join(FRONTEND, "timing.js"), "utf8");

  assert.ok(app.includes("window.sessionStorage"));
  assert.equal(app.includes("localStorage"), false, "answers must not outlive the tab session");
  assert.equal(timing.includes("localStorage"), false);
  // Nothing about scores or completion is ever written to storage.
  for (const forbidden of ["score", "correct", "completed"]) {
    assert.equal(timing.includes(`${forbidden}:`), false);
  }
});

test("every immutably-cached asset URL is versioned", () => {
  // /pilot/static/ is served `immutable, max-age=1y`, so an unversioned URL --
  // including a bare ESM sub-import -- would pin participants to a stale build.
  const html = readFileSync(join(FRONTEND, "..", "index.html"), "utf8");
  const app = readFileSync(join(FRONTEND, "app.js"), "utf8");

  const assetUrls = [
    // Only real attribute values, not prose in the page's comments.
    ...[...html.matchAll(/(?:href|src)="(\/pilot\/static\/[^"]+)"/g)].map((m) => m[1]),
    ...[...app.matchAll(/from "(\.\/[^"]+)"/g)].map((m) => m[1])
  ];
  assert.ok(assetUrls.length >= 4, "expected the page and its module graph");
  for (const url of assetUrls) {
    assert.ok(url.includes("?v="), `${url} must be version-stamped`);
  }
});

test("the pilot API client never asks the browser to cache a response", () => {
  const api = readFileSync(join(FRONTEND, "api.js"), "utf8");
  const fetchCalls = api.match(/fetch\(/g) || [];

  assert.equal(fetchCalls.length, (api.match(/cache: "no-store"/g) || []).length);
  assert.ok(api.includes("sendBeacon"), "checkpoints must survive an unloading tab");
  assert.ok(api.includes("keepalive: true"));
});
