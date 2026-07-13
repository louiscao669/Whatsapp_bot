import { renderAchievements } from "./achievements/achievements.js";
import { renderCommunity } from "./community/community.js";
import { renderContribution } from "./contribution/contribution.js";
import { bindModal, el, setActiveBodyCosmetics, showModal, showModalContent } from "./dom.js";
import { renderJourney } from "./journey/journey.js";
import { renderRightRail } from "./rightRail.js";
import { renderShop } from "./shop/shop.js";
import { renderSidebar } from "./sidebar/sidebar.js";
import {
  emptyDashboard,
  fetchDashboard,
  normalizeDashboard,
  parseParticipantIdFromLocation,
  postJson,
  postRawJson,
  sampleDashboard,
  uploadProfilePhoto
} from "./state.js";

const app = document.querySelector("#app");
const state = {
  participantId: parseParticipantIdFromLocation(),
  activePage: "journey",
  journeyChapterIndex: null,
  journeyAnswerAssignmentId: null,
  journeyAnswerQuestion: null,
  questionCompletion: null,
  startingBatch: false,
  claimingBatchRewardId: null,
  communityTab: "individual",
  shopMessage: "",
  payload: normalizeDashboard(sampleDashboard)
};

hydrateCachedDashboard();
hydrateCachedProfilePhoto();

const pageRenderers = {
  journey: renderJourney,
  achievements: renderAchievements,
  community: renderCommunity,
  contribution: renderContribution,
  shop: renderShop
};

function render() {
  setActiveBodyCosmetics(state.payload);
  const actions = {
    navigate,
    startDailyChallenge,
    setCommunityTab,
    setJourneyChapter,
    clearJourneyChapter,
    openQuestion,
    closeQuestion,
    submitAnswer,
    continueAfterAnswer,
    startNewBatch,
    startingBatch: state.startingBatch,
    claimingBatchRewardId: state.claimingBatchRewardId,
    claimBatchReward,
    purchase,
    setCosmetic,
    setStreakPause,
    uploadPhoto
  };
  const renderer = pageRenderers[state.activePage] || renderJourney;
  app.replaceChildren(
    el("div", { className: "dashboard-shell" }, [
      renderSidebar({
        payload: state.payload,
        activePage: state.activePage,
        onNavigate: navigate,
        onPhotoSelected: uploadPhoto
      }),
      el("section", { className: "main-pane" }, [
        renderer(state.payload, state, actions)
      ]),
      renderRightRail(state.payload, actions)
    ])
  );
}

function navigate(pageId) {
  state.activePage = pageId;
  if (pageId !== "journey") {
    state.journeyChapterIndex = null;
    state.journeyAnswerAssignmentId = null;
    state.journeyAnswerQuestion = null;
    state.questionCompletion = null;
  }
  state.shopMessage = "";
  render();
}

function startDailyChallenge() {
  const chapterIndex = Number.isInteger(state.payload.journey?.summary?.active_chapter_index)
    ? state.payload.journey.summary.active_chapter_index
    : 0;
  state.activePage = "journey";
  state.journeyChapterIndex = chapterIndex;
  state.journeyAnswerAssignmentId = null;
  state.journeyAnswerQuestion = null;
  state.questionCompletion = null;
  state.shopMessage = "";
  render();
}

function setJourneyChapter(index) {
  state.journeyChapterIndex = index;
  state.journeyAnswerAssignmentId = null;
  state.journeyAnswerQuestion = null;
  state.questionCompletion = null;
  render();
}

function clearJourneyChapter() {
  state.journeyChapterIndex = null;
  state.journeyAnswerAssignmentId = null;
  state.journeyAnswerQuestion = null;
  state.questionCompletion = null;
  render();
}

function pingQuestionViewed(assignmentId) {
  // Fire-and-forget: starts the time-on-task clock on the backend the
  // first time a question is rendered on the dashboard.
  if (!state.participantId || !assignmentId) {
    return;
  }
  postRawJson(state.participantId, "/question-viewed", { assignment_id: assignmentId })
    .catch(() => {});
}

function openQuestion(assignmentId) {
  if (!assignmentId) {
    showModal("This question is not ready yet.");
    return;
  }
  state.journeyAnswerAssignmentId = assignmentId;
  state.journeyAnswerQuestion = null;
  state.questionCompletion = null;
  state.shopMessage = "";
  pingQuestionViewed(assignmentId);
  render();
}

function closeQuestion() {
  state.journeyAnswerAssignmentId = null;
  state.journeyAnswerQuestion = null;
  state.questionCompletion = null;
  render();
}

function setCommunityTab(tab) {
  state.communityTab = tab;
  render();
}

async function refreshMutation(mutation) {
  if (!state.participantId) {
    showModal("Open a user dashboard URL before making changes.");
    return;
  }
  try {
    state.payload = await mutation();
    rememberDashboard();
    rememberProfilePhoto();
    state.shopMessage = "";
    render();
  } catch (error) {
    showModal(error.message);
  }
}

async function purchase(itemId) {
  state.shopMessage = "Purchasing...";
  render();
  await refreshMutation(() => postJson(state.participantId, "/purchases", { item_id: itemId }));
}

async function setCosmetic(itemId, equipped) {
  state.shopMessage = equipped ? "Equipping..." : "Removing...";
  render();
  await refreshMutation(() => postJson(state.participantId, "/cosmetics", { item_id: itemId, equipped }));
}

async function setStreakPause(paused) {
  await refreshMutation(() => postJson(state.participantId, "/streak-pause", { paused }));
}

async function claimBatchReward(batchId) {
  if (!batchId) {
    showModal("Batch reward is not available yet.");
    return;
  }
  if (!state.participantId) {
    showModal("Open a user dashboard URL before opening chests.");
    return;
  }
  if (state.claimingBatchRewardId) {
    return;
  }
  state.claimingBatchRewardId = batchId;
  render();
  try {
    const payload = await postJson(state.participantId, "/batch-rewards", { batch_id: batchId });
    state.payload = payload;
    rememberDashboard();
    rememberProfilePhoto();
    state.claimingBatchRewardId = null;
    render();
    showChestRewardModal(payload.last_reward?.amount || 0);
  } catch (error) {
    state.claimingBatchRewardId = null;
    render();
    showModal(error.message);
  }
}

async function submitAnswer(assignmentId, responseText) {
  if (!state.participantId) {
    showModal("Open a user dashboard URL before answering questions.");
    return;
  }
  if (!assignmentId || !String(responseText || "").trim()) {
    showModal("Answer the question before submitting.");
    return;
  }
  state.questionCompletion = {
    pending: true,
    submission: {},
    nextQuestion: null,
    awards: {},
    wallet: {}
  };
  state.journeyAnswerAssignmentId = null;
  state.journeyAnswerQuestion = null;
  render();
  try {
    const payload = await postRawJson(state.participantId, "/answers", {
      assignment_id: assignmentId,
      response_text: responseText
    });
    applyCompactAnswerResult(payload, assignmentId);
    rememberDashboard();
    rememberProfilePhoto();
    const submission = payload.answer_submission || {};
    state.questionCompletion = {
      pending: false,
      submission,
      nextQuestion: payload.next_question || null,
      awards: payload.awards || {},
      wallet: payload.wallet || {}
    };
    render();
  } catch (error) {
    state.questionCompletion = {
      pending: false,
      failed: true,
      errorMessage: error.message,
      submission: {},
      nextQuestion: null,
      awards: {},
      wallet: {}
    };
    render();
    showModal(error.message);
  }
}

async function continueAfterAnswer() {
  const completion = state.questionCompletion;
  if (!completion) {
    return;
  }
  if (completion.pending) {
    return;
  }
  if (completion.failed) {
    closeQuestion();
    return;
  }
  state.questionCompletion = null;
  const submission = completion.submission || {};
  if (submission.batch_completed) {
    state.journeyAnswerAssignmentId = null;
    state.journeyAnswerQuestion = null;
    render();
    refreshDashboardInBackground();
    return;
  }
  const nextQuestion = completion.nextQuestion || null;
  state.journeyAnswerQuestion = nextQuestion;
  state.journeyAnswerAssignmentId = nextQuestion?.assignment_id
    || submission.next_assignment_id
    || null;
  pingQuestionViewed(state.journeyAnswerAssignmentId);
  render();
}

async function refreshDashboardInBackground() {
  if (!state.participantId) {
    return;
  }
  try {
    state.payload = await fetchDashboard(state.participantId);
    rememberDashboard();
    rememberProfilePhoto();
    render();
  } catch (error) {
    showModal(error.message, "Dashboard refresh failed");
  }
}

async function startNewBatch() {
  if (!state.participantId) {
    showModal("Open a user dashboard URL before starting a new batch.");
    return;
  }
  if (state.startingBatch) {
    return;
  }
  state.startingBatch = true;
  render();
  try {
    state.payload = await postJson(state.participantId, "/start-batch", {});
    rememberDashboard();
    rememberProfilePhoto();
    const chapterIndex = Number.isInteger(state.payload.journey?.summary?.active_chapter_index)
      ? state.payload.journey.summary.active_chapter_index
      : state.journeyChapterIndex;
    state.journeyChapterIndex = chapterIndex;
    state.journeyAnswerAssignmentId = null;
    state.journeyAnswerQuestion = null;
    state.questionCompletion = null;
    state.startingBatch = false;
    render();
  } catch (error) {
    state.startingBatch = false;
    render();
    showModal(error.message);
  }
}

function applyCompactAnswerResult(payload, answeredAssignmentId) {
  state.payload = {
    ...state.payload,
    wallet: {
      ...(state.payload.wallet || {}),
      ...(payload.wallet || {})
    }
  };
  const submission = payload.answer_submission || {};
  const nextQuestion = payload.next_question || null;
  const chapters = state.payload.journey?.chapters || [];
  for (const chapter of chapters) {
    for (const batch of chapter.batches || []) {
      const questions = batch.questions || [];
      const answeredIndex = questions.findIndex((question) => (
        question.assignment_id === answeredAssignmentId
      ));
      if (answeredIndex < 0) {
        continue;
      }
      questions[answeredIndex] = {
        ...questions[answeredIndex],
        status: "complete"
      };
      if (submission.batch_completed) {
        batch.status = "complete";
        return;
      }
      if (nextQuestion) {
        const existingIndex = questions.findIndex((question) => (
          question.assignment_id === nextQuestion.assignment_id
        ));
        const insertIndex = existingIndex >= 0
          ? existingIndex
          : questions.findIndex((question, index) => (
            index > answeredIndex && question.status === "locked"
          ));
        if (insertIndex >= 0) {
          questions[insertIndex] = nextQuestion;
        } else {
          questions.push(nextQuestion);
        }
        batch.status = "active";
      }
      return;
    }
  }
}

async function uploadPhoto(file) {
  if (!state.participantId) {
    showModal("Open a user dashboard URL before changing photo.");
    return;
  }
  if (!file.type || !file.type.startsWith("image/")) {
    showModal("Choose an image file.");
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    showModal("Photo must be 5 MB or smaller.");
    return;
  }
  try {
    state.payload = await uploadProfilePhoto(state.participantId, file);
    rememberDashboard();
    rememberProfilePhoto();
    render();
  } catch (error) {
    showModal(error.message);
  }
}

function showChestRewardModal(amount) {
  const diamondCount = Math.max(1, Math.min(5, Number(amount || 0)));
  showModalContent("Treasure chest!", [
    el("div", { className: "chest-claim-modal" }, [
      el("span", { className: "chest-claim-sparkle", text: "*" }),
      el("span", { className: "chest-claim-sparkle", text: "*" }),
      el("span", { className: "chest-claim-sparkle", text: "*" }),
      Number(amount) > 2 ? el("div", { className: "chest-claim-eyebrow", text: "You got lucky!" }) : null,
      el("div", { className: "chest-claim-icon-wrap" }, [
        el("div", { className: "chest-claim-ring" }),
        el("img", {
          className: "chest-claim-icon",
          src: "/user_dashboard/assets/chest_opened.svg",
          alt: "",
          "aria-hidden": "true"
        })
      ]),
      el("div", { className: "chest-claim-title", text: `+${amount} diamonds!` }),
      el("div", { className: "chest-claim-diamonds" }, Array.from({ length: diamondCount }, () => (
        el("img", { src: "/user_dashboard/assets/diamond.svg", alt: "", "aria-hidden": "true" })
      )))
    ])
  ]);
}

async function boot() {
  bindModal();
  if (!state.participantId) {
    // No identity in the URL — send them to the login page to resolve their
    // WhatsApp number / Telegram chat id into a participant id.
    window.location.replace("/user_dashboard/login");
    return;
  }
  render();
  try {
    state.payload = await fetchDashboard(state.participantId);
    rememberDashboard();
    rememberProfilePhoto();
  } catch (error) {
    if (!hydrateCachedDashboard()) {
      state.payload = normalizeDashboard(emptyDashboard(state.participantId));
      hydrateCachedProfilePhoto();
    }
    showModal(`Could not load dashboard: ${error.message}`, "Dashboard error");
  }
  render();
}

boot();

function dashboardCacheKey() {
  return state.participantId ? `user_dashboard_payload:${state.participantId}` : "";
}

function profilePhotoCacheKey() {
  return state.participantId ? `user_dashboard_profile_photo:${state.participantId}` : "";
}

function hydrateCachedDashboard() {
  const key = dashboardCacheKey();
  if (!key) {
    return false;
  }
  try {
    const cachedPayload = window.localStorage.getItem(key);
    if (!cachedPayload) {
      return false;
    }
    state.payload = normalizeDashboard(JSON.parse(cachedPayload));
    return true;
  } catch {
    return false;
  }
}

function rememberDashboard() {
  const key = dashboardCacheKey();
  if (!key) {
    return;
  }
  try {
    window.localStorage.setItem(key, JSON.stringify(state.payload));
  } catch {
    // Ignore storage failures; live API data still renders normally.
  }
}

function hydrateCachedProfilePhoto() {
  const key = profilePhotoCacheKey();
  if (!key) {
    return;
  }
  try {
    const cachedUrl = window.localStorage.getItem(key);
    if (cachedUrl) {
      state.payload = {
        ...state.payload,
        participant: {
          ...(state.payload.participant || {}),
          profile_photo_url: cachedUrl
        }
      };
      preloadProfilePhoto(cachedUrl);
    }
  } catch {
    // localStorage may be unavailable in private or restricted browser contexts.
  }
}

function rememberProfilePhoto() {
  const key = profilePhotoCacheKey();
  const url = state.payload.participant?.profile_photo_url || "";
  if (!key) {
    return;
  }
  try {
    if (url) {
      window.localStorage.setItem(key, url);
      preloadProfilePhoto(url);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    // Ignore storage failures; the image still loads normally.
  }
}

function preloadProfilePhoto(url) {
  if (!url) {
    return;
  }
  const image = new Image();
  image.decoding = "async";
  image.src = url;
}
