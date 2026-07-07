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
      node.textContent = value;
    } else if (key === "html") {
      node.innerHTML = value;
    } else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value !== false && value !== null && value !== undefined) {
      node.setAttribute(key, value === true ? "" : value);
    }
  }
  node.append(...children.filter(Boolean));
  return node;
}

export function setActiveBodyCosmetics(payload) {
  const equipped = payload.cosmetics?.equipped || {};
  document.body.classList.toggle("dashboard-bg-sunrise", equipped.dashboard_background === "dashboard_background_sunrise");
}

export function showModal(message, title = "Action unavailable") {
  document.querySelector("#actionModalTitle").textContent = title;
  document.querySelector("#actionModalMessage").replaceChildren(
    el("p", { text: message })
  );
  document.querySelector("#actionModal").hidden = false;
  document.querySelector("#actionModalClose").focus();
}

export function showModalContent(title, children = []) {
  document.querySelector("#actionModalTitle").textContent = title;
  document.querySelector("#actionModalMessage").replaceChildren(...children.filter(Boolean));
  document.querySelector("#actionModal").hidden = false;
  document.querySelector("#actionModalClose").focus();
}

export function bindModal() {
  const modal = document.querySelector("#actionModal");
  const close = document.querySelector("#actionModalClose");
  close.addEventListener("click", () => {
    modal.hidden = true;
  });
  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      modal.hidden = true;
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) {
      modal.hidden = true;
    }
  });
}
