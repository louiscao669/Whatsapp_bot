import { el, showConfirm } from "../dom.js";

const PROFILE_PHOTO_CHANGE_COST = 5;

export const pages = [
  { id: "journey", label: "Journey", iconUrl: "/user_dashboard/assets/journey.svg" },
  { id: "achievements", label: "Achievements", iconUrl: "/user_dashboard/assets/achievement.svg" },
  { id: "community", label: "Community", iconUrl: "/user_dashboard/assets/community.svg" },
  { id: "contribution", label: "Contribution", iconUrl: "/user_dashboard/assets/contribution.svg" },
  { id: "shop", label: "Store", iconUrl: "/user_dashboard/assets/store.svg" }
];

export function renderSidebar({ payload, activePage, onNavigate, onPhotoSelected }) {
  const participant = payload.participant || {};
  const equipped = payload.cosmetics?.equipped || {};
  const photoWrap = el("span", {
    className: `profile-photo-wrap ${equipped.profile_frame === "profile_frame_gold" ? "gold-frame" : ""}`
  }, [
    el("img", {
      id: "profilePhoto",
      className: "profile-photo",
      src: participant.profile_photo_url || "/user_dashboard/assets/diamond.svg",
      alt: "Profile",
      decoding: "async",
      fetchpriority: "high",
      loading: "eager"
    })
  ]);
  const photoInput = el("input", {
    id: "profilePhotoInput",
    type: "file",
    accept: "image/*",
    onchange: (event) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) {
        return;
      }
      showConfirm({
        title: "Change photo",
        message: `Changing photo costs ${PROFILE_PHOTO_CHANGE_COST} diamonds.`,
        confirmLabel: "Confirm",
        cancelLabel: "Cancel",
        onConfirm: () => onPhotoSelected(file)
      });
    }
  });
  const photoControl = el("button", {
    type: "button",
    className: "profile-photo-control",
    onclick: () => photoInput.click()
  }, [
    photoWrap,
    el("span", { text: "Change photo" }),
    photoInput
  ]);

  const nav = el("nav", { className: "sidebar-nav", "aria-label": "Dashboard pages" }, pages.map((page) => (
    el("button", {
      type: "button",
      className: `nav-button ${activePage === page.id ? "active" : ""}`,
      onclick: () => onNavigate(page.id)
    }, [
      el("img", {
        className: "nav-icon",
        src: page.iconUrl,
        alt: "",
        "aria-hidden": "true"
      }),
      el("span", { className: "nav-label", text: page.label })
    ])
  )));

  return el("aside", { className: "sidebar" }, [
    photoControl,
    el("h1", { className: "participant-name", text: participant.display_name || "Name" }),
    nav,
    el("p", {
      className: "status-line",
      id: "sidebarStatus",
      text: ""
    })
  ]);
}
