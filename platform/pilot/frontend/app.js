/**
 * The `/pilot` participant interface: one question at a time, plainly.
 *
 * Not present, on purpose: any correctness feedback during the study, any
 * score / reward / balance / streak, any clock shown to the participant, any
 * time limit, any periodic
 * poll, and any preloading of the next question. The next question is fetched
 * only after the server acknowledges the current answer, so it cannot be
 * exposed early and its clock cannot start early.
 *
 * Every measurement and every network call in this file is driven by a user or
 * browser event. There is no polling loop and no scheduled timer of any kind;
 * `platform/pilot/tests/timing.test.mjs` asserts that at the source level.
 */

// Sub-module imports carry the same ?v= as the entry point in index.html.
// Everything under /pilot/static/ is served immutable for a year, so an
// unversioned module URL would pin participants to a stale build forever.
// Bump all three together when the frontend changes.
import { createPilotApi, parseParticipantIdFromLocation } from "./api.js?v=20260818c";
import { createAttentionTimers, createTrialStore, resumeActiveMs } from "./timing.js?v=20260818c";

const root = document.querySelector("#pilot");
const participantId = parseParticipantIdFromLocation();
const api = createPilotApi(participantId);
const store = createTrialStore(window.sessionStorage);

/** The one question currently on screen. Never holds a future question. */
let trial = null;
let submitting = false;

function isVisible() {
  return document.visibilityState === "visible";
}

function isFocused() {
  // Recorded alongside visibility, never used to gate it -- see timing.js.
  return typeof document.hasFocus === "function" ? document.hasFocus() : true;
}

function newSubmissionId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  // Fallback for browsers without randomUUID: still a client-generated id, and
  // the server dedupes on (assignment, submission_id) either way.
  return `sub-${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random()
    .toString(16)
    .slice(2)}`;
}

function isReloadNavigation() {
  try {
    const [entry] = performance.getEntriesByType("navigation");
    return Boolean(entry && entry.type === "reload");
  } catch (error) {
    return false;
  }
}

function persist() {
  if (!trial) {
    return;
  }
  const snapshot = trial.timers.snapshot();
  store.write(trial.assignmentId, {
    draft: trial.draft,
    submissionId: trial.submissionId,
    activeMs: snapshot.activeMs,
    focusedMs: snapshot.focusedMs,
    onscreenMs: snapshot.onscreenMs,
    visibilityChangeCount: snapshot.visibilityChangeCount,
    focusChangeCount: snapshot.focusChangeCount,
    reloadCount: trial.reloadCount,
    segmentOpen: snapshot.running
  });
}

function timingPayload() {
  const snapshot = trial.timers.snapshot();
  return {
    assignment_id: trial.assignmentId,
    active_time_ms: snapshot.activeMs,
    focused_time_ms: snapshot.focusedMs,
    passage_onscreen_ms: snapshot.onscreenMs,
    visibility_change_count: snapshot.visibilityChangeCount,
    focus_change_count: snapshot.focusChangeCount,
    reload_count: trial.reloadCount,
    client_event_at: new Date().toISOString()
  };
}

function checkpoint(eventType) {
  if (!trial) {
    return;
  }
  api.checkpoint({ ...timingPayload(), event_type: eventType });
}

// --------------------------------------------------------------- rendering
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function renderMessage(title, body) {
  root.replaceChildren();
  const card = element("section", "pilot-card");
  card.append(element("h1", "pilot-title", title));
  if (body) {
    card.append(element("p", "pilot-body", body));
  }
  root.append(card);
}

function renderComplete() {
  renderMessage(
    "You're finished",
    "Thank you — you have answered every question. You can close this page."
  );
}

function renderQuestion(question) {
  root.replaceChildren();
  const card = element("section", "pilot-card");
  card.append(element("p", "pilot-step", `Question ${question.question_number}`));

  // One line per verse. `passage_lines` is the same delivered text the server
  // split on verse boundaries; it falls back to the whole block when the text
  // could not be split without guessing.
  const lines =
    question.passage_lines && question.passage_lines.length
      ? question.passage_lines
      : [question.passage_text].filter(Boolean);
  let passageNode = null;
  if (lines.length) {
    const passage = element("div", "pilot-passage");
    passageNode = passage;
    if (question.passage_reference) {
      passage.append(element("p", "pilot-passage-ref", question.passage_reference));
    }
    lines.forEach((line) => passage.append(element("p", "pilot-verse", line)));
    card.append(passage);
  }

  card.append(element("h1", "pilot-question", question.question));

  const form = element("form", "pilot-form");
  form.noValidate = true;
  let readAnswer;

  if (question.answer_mode === "mcq") {
    const list = element("div", "pilot-choices");
    question.choices.forEach((choice) => {
      const label = element("label", "pilot-choice");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "pilot-choice";
      input.value = choice.letter;
      if (trial && trial.draft === choice.letter) {
        input.checked = true;
      }
      input.addEventListener("change", () => {
        trial.draft = input.value;
        persist();
      });
      label.append(input, element("span", "pilot-choice-text", `${choice.letter}. ${choice.text}`));
      list.append(label);
    });
    form.append(list);
    readAnswer = () => {
      const checked = form.querySelector("input[name='pilot-choice']:checked");
      return checked ? checked.value : "";
    };
  } else {
    const textarea = document.createElement("textarea");
    textarea.className = "pilot-answer";
    textarea.rows = 6;
    textarea.placeholder = "Type your answer";
    textarea.value = (trial && trial.draft) || "";
    textarea.addEventListener("input", () => {
      trial.draft = textarea.value;
      persist();
    });
    form.append(textarea);
    readAnswer = () => textarea.value;
  }

  const submit = element("button", "pilot-submit", "Submit");
  submit.type = "submit";
  const status = element("p", "pilot-status", "");
  form.append(submit, status);
  card.append(form);
  root.append(card);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onSubmit(readAnswer(), submit, status);
  });

  return passageNode;
}

/**
 * Watch whether the passage itself is in the viewport.
 *
 * A different question from "is the tab visible": this catches a participant
 * who scrolled straight past the text to the answer box. Scoped to the one
 * passage element of the current question and torn down with it, so it cannot
 * become general scroll analytics.
 */
function observePassage(passageNode) {
  if (!trial || !passageNode || typeof IntersectionObserver !== "function") {
    // Without the API, treat the passage as on screen so the metric degrades
    // to "page visible" rather than silently reading zero.
    if (trial) {
      trial.timers.update({ onscreen: true }, { countChanges: false });
    }
    return;
  }
  const observer = new IntersectionObserver(
    (entries) => {
      if (!trial) {
        return;
      }
      // threshold 0: any part of the passage in the viewport counts.
      const onscreen = entries.some((entry) => entry.isIntersecting);
      trial.timers.update({ onscreen });
      persist();
    },
    { threshold: 0 }
  );
  observer.observe(passageNode);
  trial.observer = observer;
}

function releaseObserver() {
  if (trial && trial.observer) {
    trial.observer.disconnect();
    trial.observer = null;
  }
}

// ---------------------------------------------------------------- lifecycle
async function loadQuestion() {
  renderMessage("Loading…", "");
  let state;
  try {
    state = await api.getState();
  } catch (error) {
    renderMessage("Something went wrong", error.message);
    return;
  }

  if (state.state !== "question" || !state.question) {
    trial = null;
    renderComplete();
    return;
  }

  const question = state.question;
  const stored = store.read(question.assignment_id);
  const reloadCount =
    (stored ? stored.reloadCount : 0) + (stored && isReloadNavigation() ? 1 : 0);

  trial = {
    assignmentId: question.assignment_id,
    question,
    draft: stored ? stored.draft : "",
    submissionId: stored ? stored.submissionId : null,
    reloadCount,
    viewedSent: false,
    observer: null,
    // Resume from the larger of the durable server checkpoint and this tab's
    // own record, so a reload never loses time already spent reading.
    timers: createAttentionTimers({
      now: () => performance.now(),
      activeMs: resumeActiveMs(question.active_time_ms, stored ? stored.activeMs : 0),
      focusedMs: resumeActiveMs(question.focused_time_ms, stored ? stored.focusedMs : 0),
      onscreenMs: resumeActiveMs(
        question.passage_onscreen_ms,
        stored ? stored.onscreenMs : 0
      ),
      visibilityChangeCount: Math.max(
        question.visibility_change_count || 0,
        stored ? stored.visibilityChangeCount : 0
      ),
      focusChangeCount: Math.max(
        question.focus_change_count || 0,
        stored ? stored.focusChangeCount : 0
      )
    })
  };

  const passage = renderQuestion(question);
  observePassage(passage);
  persist();

  // Only start once the question is actually painted AND the page is visible.
  // A question opened in a background tab is rendered but not timed, and stays
  // untimed until the participant looks at it.
  requestAnimationFrame(() => {
    if (isVisible()) {
      beginVisibleSegment();
    }
  });
}

async function beginVisibleSegment() {
  if (!trial || trial.timers.running) {
    return;
  }
  // Server timestamp is authoritative for "first viewed"; the client only
  // reports that it happened.
  if (!trial.viewedSent) {
    trial.viewedSent = true;
    try {
      await api.markViewed({
        assignment_id: trial.assignmentId,
        reload_count: trial.reloadCount,
        client_event_at: new Date().toISOString()
      });
    } catch (error) {
      /* The clock still runs locally; the next checkpoint re-reports it. */
    }
  }
  if (!trial || !isVisible()) {
    return;
  }
  trial.timers.begin({ visible: true, focused: isFocused() });
  persist();
}

function onVisibilityChange() {
  if (!trial || submitting) {
    return;
  }
  const visible = isVisible();
  trial.timers.update({ visible, focused: visible && isFocused() });
  persist();
  if (visible) {
    if (!trial.viewedSent) {
      beginVisibleSegment();
    } else {
      checkpoint("question_visible");
    }
  } else {
    checkpoint("question_hidden");
  }
}

function onPageHide() {
  if (!trial || submitting) {
    return;
  }
  trial.timers.update({ visible: false, focused: false });
  persist();
  checkpoint("question_hidden");
}

/**
 * Window focus changes. These move ONLY focused_time_ms -- active_time_ms
 * keeps running, because losing focus to the address bar or an OS notification
 * is not the participant looking away.
 */
function onFocusChange() {
  if (!trial || submitting || !isVisible()) {
    return;
  }
  trial.timers.update({ focused: isFocused() });
  persist();
}

function onPageShow(event) {
  if (!trial) {
    return;
  }
  if (event.persisted) {
    trial.reloadCount += 1;
  }
  if (isVisible() && !trial.timers.running) {
    trial.timers.update({ visible: true, focused: isFocused() });
    persist();
    checkpoint("question_visible");
  }
}

async function onSubmit(answer, submitButton, status) {
  if (!trial || submitting) {
    return;
  }
  const trimmed = (answer || "").trim();
  if (!trimmed) {
    status.textContent = "Please answer before continuing.";
    return;
  }

  // Close the final segment FIRST. Everything after this line -- the request,
  // the server's work, the scoring that follows -- is outside the measurement.
  const snapshot = trial.timers.stop();
  releaseObserver();
  submitting = true;
  submitButton.disabled = true;
  status.textContent = "Saving…";

  trial.draft = trimmed;
  trial.submissionId = trial.submissionId || newSubmissionId();
  // The pending answer stays in sessionStorage until the server acknowledges
  // it, so a crash mid-request cannot lose it -- and the stable submission id
  // makes the retry idempotent.
  persist();

  const submittedAssignmentId = trial.assignmentId;
  try {
    await api.submitAnswer({
      assignment_id: submittedAssignmentId,
      submission_id: trial.submissionId,
      answer: trimmed,
      active_time_ms: snapshot.activeMs,
      focused_time_ms: snapshot.focusedMs,
      passage_onscreen_ms: snapshot.onscreenMs,
      visibility_change_count: snapshot.visibilityChangeCount,
      focus_change_count: snapshot.focusChangeCount,
      reload_count: trial.reloadCount,
      client_event_at: new Date().toISOString()
    });
  } catch (error) {
    submitting = false;
    submitButton.disabled = false;
    status.textContent = `${error.message} — tap Submit to try again.`;
    return;
  }

  // Acknowledged and committed: only now is the local copy safe to drop, and
  // only now do we ask for the next question.
  store.clear(submittedAssignmentId);
  releaseObserver();
  trial = null;
  submitting = false;
  await loadQuestion();
}

document.addEventListener("visibilitychange", onVisibilityChange);
window.addEventListener("focus", onFocusChange);
window.addEventListener("blur", onFocusChange);
window.addEventListener("pagehide", onPageHide);
window.addEventListener("pageshow", onPageShow);

if (!participantId) {
  renderMessage(
    "Participant link required",
    "Open the personal link you were given to start the study."
  );
} else {
  loadQuestion();
}
