import { el } from "../dom.js";
import { formatNumber, pluralize } from "../state.js";

export function renderShop(payload, state, actions) {
  const store = payload.store || {};
  const items = store.items || [];
  const tools = items.filter((item) => item.item_type !== "cosmetic");
  const decorations = items.filter((item) => item.item_type === "cosmetic");

  return el("section", { className: "store-page" }, [
    el("div", { className: "shop-hero" }, [
      el("div", { className: "shop-scene", "aria-hidden": "true" }, [
        merch("merch1", "one"),
        merch("merch2", "two"),
        el("img", {
          className: "shop-building",
          src: "/user_dashboard/assets/shop.svg",
          alt: ""
        }),
        merch("merch3", "three"),
        merch("merch4", "four")
      ])
    ]),
    el("section", { className: "store-section" }, [
      el("h2", { className: "store-section-label", text: "Tools" }),
      ...toolRows(tools, payload, actions)
    ]),
    el("section", { className: "store-section" }, [
      el("h2", { className: "store-section-label", text: "Decoration" }),
      el("div", { className: "store-decoration-grid" }, decorationRows(decorations, payload, actions))
    ]),
    el("p", { id: "shopStatus", className: "status-line", text: state.shopMessage || "" })
  ]);
}

function merch(name, position) {
  return el("img", {
    className: `shop-merch shop-merch-${position}`,
    src: `/user_dashboard/assets/${name}.svg`,
    alt: ""
  });
}

function toolRows(items, payload, actions) {
  if (!items.length) {
    return [el("div", { className: "empty-state", text: "No items available." })];
  }
  return items.map((item) => toolCard(item, payload, actions));
}

function decorationRows(items, payload, actions) {
  if (!items.length) {
    return [el("div", { className: "empty-state", text: "No decorations available." })];
  }
  return items.map((item) => decorationCard(item, payload, actions));
}

function toolCard(item, payload, actions) {
  const state = itemState(item, payload);
  const style = itemStyle(item.item_id);

  return el("article", { className: `tool-card ${state.owned ? "owned" : ""}` }, [
    el("div", { className: `item-icon ${style.iconClass}` }, [
      el("img", { src: style.icon, alt: "", "aria-hidden": "true" })
    ]),
    el("div", { className: "item-body" }, [
      el("h3", { className: "item-name", text: item.title }),
      el("p", { className: "item-desc", text: item.description || "" }),
      el("div", { className: "item-tags" }, [
        tag("tag-diamond", "/user_dashboard/assets/diamond.svg", String(state.cost)),
        tag("tag-stack", "", `Owned ${formatNumber(state.owned)}/${formatNumber(state.maxOwned)}`)
      ])
    ]),
    actionButton(item, state, actions)
  ]);
}

function decorationCard(item, payload, actions) {
  const state = itemState(item, payload);
  const style = itemStyle(item.item_id);
  const className = `deco-card ${state.isEquipped ? "equipped" : ""}`;

  return el("article", { className }, [
    el("div", { className: `deco-preview ${style.previewClass}` }, [
      style.previewIcon
        ? el("img", { src: style.previewIcon, alt: "", "aria-hidden": "true" })
        : el("span", { text: style.previewText })
    ]),
    el("div", {}, [
      el("h3", { className: "item-name", text: item.title }),
      el("p", { className: "item-desc", text: item.description || "" })
    ]),
    el("div", { className: "item-tags" }, [
      tag("tag-diamond", "/user_dashboard/assets/diamond.svg", String(state.cost)),
      state.owned ? tag("tag-owned", "", "Owned") : null
    ]),
    state.isEquipped
      ? el("div", { className: "deco-footer" }, [
        actionButton(item, state, actions),
        el("span", { className: "equipped-badge", text: "Equipped" })
      ])
      : actionButton(item, state, actions)
  ]);
}

function itemState(item, payload) {
  const inventory = payload.store?.inventory || {};
  const equipped = payload.cosmetics?.equipped || {};
  const balance = Number(payload.wallet?.balance || 0);
  const owned = Number(inventory[item.item_id]?.owned || 0);
  const maxOwned = Number(item.max_owned || inventory[item.item_id]?.max_owned || 1);
  const cost = Number(item.cost || 0);
  const slot = cosmeticSlotForItem(item.item_id);
  const isEquipped = Boolean(slot && equipped[slot] === item.item_id);
  const atLimit = owned >= maxOwned;
  const canAfford = balance >= cost;
  const isOwnedCosmetic = item.item_type === "cosmetic" && owned > 0;
  return {
    owned,
    maxOwned,
    cost,
    isEquipped,
    atLimit,
    canAfford,
    isOwnedCosmetic
  };
}

function actionButton(item, state, actions) {
  const isCosmetic = item.item_type === "cosmetic";
  const buttonText = state.isOwnedCosmetic
    ? (state.isEquipped ? "Unequip" : "Equip")
    : state.atLimit
      ? "Owned"
      : state.canAfford
        ? "Buy"
        : "Need Diamonds";
  const className = state.atLimit && !state.isOwnedCosmetic
    ? "btn-owned"
    : state.canAfford || state.isOwnedCosmetic
      ? (isCosmetic ? "btn-equip" : "btn-buy")
      : "btn-buy";

  return el("button", {
    type: "button",
    className,
    disabled: !state.isOwnedCosmetic && (state.atLimit || !state.canAfford),
    title: `${state.cost} ${pluralize(state.cost, "diamond", "diamonds")}`,
    onclick: () => {
      if (state.isOwnedCosmetic) {
        actions.setCosmetic(item.item_id, !state.isEquipped);
      } else {
        actions.purchase(item.item_id);
      }
    },
    text: buttonText
  });
}

function tag(className, icon, text) {
  return el("span", { className: `tag ${className}` }, [
    icon ? el("img", { src: icon, alt: "", "aria-hidden": "true" }) : null,
    el("span", { text })
  ]);
}

function itemStyle(itemId) {
  const styles = {
    streak_freeze: {
      icon: "/user_dashboard/assets/streak_fire.svg",
      iconClass: "item-icon-freeze",
      previewClass: "preview-sunrise",
      previewText: "BG"
    },
    extra_life: {
      icon: "/user_dashboard/assets/heart.svg",
      iconClass: "item-icon-heart",
      previewClass: "preview-gold",
      previewText: "Frame"
    },
    dashboard_background_sunrise: {
      icon: "/user_dashboard/assets/sunrise.svg",
      iconClass: "item-icon-sunrise",
      previewClass: "preview-sunrise",
      previewIcon: "/user_dashboard/assets/sunrise.svg",
      previewText: ""
    },
    profile_frame_gold: {
      icon: "/user_dashboard/assets/crown.svg",
      iconClass: "item-icon-gold",
      previewClass: "preview-gold",
      previewIcon: "/user_dashboard/assets/crown.svg",
      previewText: ""
    }
  };
  return styles[itemId] || {
    icon: "/user_dashboard/assets/store.svg",
    iconClass: "item-icon-default",
    previewClass: "preview-default",
    previewText: "Item"
  };
}

function cosmeticSlotForItem(itemId) {
  if (itemId === "profile_frame_gold") {
    return "profile_frame";
  }
  if (itemId === "dashboard_background_sunrise") {
    return "dashboard_background";
  }
  return null;
}
