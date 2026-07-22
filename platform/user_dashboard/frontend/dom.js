import { translateText } from "./i18n.js";

export function el(tag, options = {}, children = []) {
  const svgTags = new Set(["svg", "path", "circle", "rect", "line", "polyline", "polygon", "g"]);
  const node = svgTags.has(tag)
    ? document.createElementNS("http://www.w3.org/2000/svg", tag)
    : document.createElement(tag);
  for (const [key, value] of Object.entries(options)) {
    if (key === "className") {
      if (node.namespaceURI === "http://www.w3.org/2000/svg") {
        node.setAttribute("class", value);
      } else {
        node.className = value;
      }
    } else if (key === "text") {
      node.textContent = translateText(value);
    } else if (key === "html") {
      node.innerHTML = value;
    } else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value !== false && value !== null && value !== undefined) {
      const translatedValue = ["title", "placeholder", "aria-label"].includes(key)
        ? translateText(value)
        : value;
      node.setAttribute(key, translatedValue === true ? "" : translatedValue);
    }
  }
  node.append(...children.filter(Boolean));
  return node;
}

export function setActiveBodyCosmetics(payload) {
  // Keep the dashboard on one consistent light theme at every time of day.
  // Profile cosmetics are rendered by their components and remain enabled.
  document.body.classList.remove("dashboard-bg-sunrise");
}

export function showModal(message, title = "Action unavailable") {
  document.querySelector("#actionModalTitle").textContent = translateText(title);
  document.querySelector("#actionModalMessage").replaceChildren(
    el("p", { text: message })
  );
  document.querySelector("#actionModal").hidden = false;
  document.querySelector("#actionModalClose").focus();
}

export function showModalContent(title, children = []) {
  document.querySelector("#actionModalTitle").textContent = translateText(title);
  document.querySelector("#actionModalMessage").replaceChildren(...children.filter(Boolean));
  document.querySelector("#actionModal").hidden = false;
  document.querySelector("#actionModalClose").focus();
}

export function showConfirm({
  title = "Please confirm",
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel
} = {}) {
  const modal = document.querySelector("#actionModal");
  const closeBtn = document.querySelector("#actionModalClose");
  document.querySelector("#actionModalTitle").textContent = translateText(title);

  const close = () => {
    modal.hidden = true;
    if (closeBtn) closeBtn.hidden = false;
  };

  const confirmBtn = el("button", {
    type: "button",
    className: "modal-btn modal-btn-confirm",
    text: confirmLabel,
    onclick: () => {
      close();
      if (typeof onConfirm === "function") onConfirm();
    }
  });
  const cancelBtn = el("button", {
    type: "button",
    className: "modal-btn modal-btn-cancel",
    text: cancelLabel,
    onclick: () => {
      close();
      if (typeof onCancel === "function") onCancel();
    }
  });

  document.querySelector("#actionModalMessage").replaceChildren(
    el("p", { text: message }),
    el("div", { className: "modal-actions" }, [cancelBtn, confirmBtn])
  );
  if (closeBtn) closeBtn.hidden = true;
  modal.hidden = false;
  confirmBtn.focus();
}

export function bindModal() {
  const modal = document.querySelector("#actionModal");
  const close = document.querySelector("#actionModalClose");
  const dismiss = () => {
    modal.hidden = true;
    if (close) close.hidden = false;
  };
  close.addEventListener("click", dismiss);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      dismiss();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) {
      dismiss();
    }
  });
}
