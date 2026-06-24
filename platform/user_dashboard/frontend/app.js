import { renderAchievements } from "./achievements/achievements.js";
import { renderCommunity } from "./community/community.js";
import { renderContribution } from "./contribution/contribution.js";
import { bindModal, el, setActiveBodyCosmetics, showModal } from "./dom.js";
import { renderJourney } from "./journey/journey.js";
import { renderRightRail } from "./rightRail.js";
import { renderShop } from "./shop/shop.js";
import { renderSidebar } from "./sidebar/sidebar.js";
import {
  emptyDashboard,
  fetchDashboard,
  normalizeDashboard,
  parseWaIdFromLocation,
  postJson,
  sampleDashboard,
  uploadProfilePhoto
} from "./state.js";

const app = document.querySelector("#app");
const state = {
  waId: parseWaIdFromLocation(),
  activePage: "journey",
  communityTab: "individual",
  shopMessage: "",
  payload: normalizeDashboard(sampleDashboard)
};

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
    setCommunityTab,
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
  state.shopMessage = "";
  render();
}

function setCommunityTab(tab) {
  state.communityTab = tab;
  render();
}

async function refreshMutation(mutation) {
  if (!state.waId) {
    showModal("Open a user dashboard URL before making changes.");
    return;
  }
  try {
    state.payload = await mutation();
    state.shopMessage = "";
    render();
  } catch (error) {
    showModal(error.message);
  }
}

async function purchase(itemId) {
  state.shopMessage = "Purchasing...";
  render();
  await refreshMutation(() => postJson(state.waId, "/purchases", { item_id: itemId }));
}

async function setCosmetic(itemId, equipped) {
  state.shopMessage = equipped ? "Equipping..." : "Removing...";
  render();
  await refreshMutation(() => postJson(state.waId, "/cosmetics", { item_id: itemId, equipped }));
}

async function setStreakPause(paused) {
  await refreshMutation(() => postJson(state.waId, "/streak-pause", { paused }));
}

async function uploadPhoto(file) {
  if (!state.waId) {
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
    state.payload = await uploadProfilePhoto(state.waId, file);
    rememberProfilePhoto();
    render();
  } catch (error) {
    showModal(error.message);
  }
}

async function boot() {
  bindModal();
  render();
  if (!state.waId) {
    return;
  }
  try {
    state.payload = await fetchDashboard(state.waId);
    rememberProfilePhoto();
  } catch (error) {
    state.payload = normalizeDashboard(emptyDashboard(state.waId));
    hydrateCachedProfilePhoto();
    showModal(`Could not load dashboard: ${error.message}`, "Dashboard error");
  }
  render();
}

boot();

function profilePhotoCacheKey() {
  return state.waId ? `user_dashboard_profile_photo:${state.waId}` : "";
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
