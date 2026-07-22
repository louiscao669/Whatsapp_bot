import { el } from "../dom.js";

export function renderSettings(state, actions) {
  const draft = state.settingsDraft || { language: "en", batch_size: 3 };
  const batchSize = Number(draft.batch_size || 3);
  return el("section", { className: "settings-page" }, [
    el("div", { className: "settings-heading" }, [
      el("button", {
        type: "button",
        className: "settings-back",
        text: "Back",
        onclick: actions.closeSettings
      }),
      el("h1", { text: "Settings" })
    ]),
    el("section", { className: "settings-card" }, [
      el("div", { className: "settings-field" }, [
        el("div", {}, [
          el("label", { for: "dashboardLanguage", text: "Dashboard language" }),
          el("p", { text: "Language" })
        ]),
        el("select", {
          id: "dashboardLanguage",
          className: "settings-select",
          onchange: (event) => actions.setSettingsLanguage(event.target.value)
        }, [
          option("en", "English", draft.language),
          option("zh", "Chinese (Simplified)", draft.language)
        ])
      ]),
      el("div", { className: "settings-field settings-batch-field" }, [
        el("div", {}, [
          el("label", { text: "Questions per batch" }),
          el("p", { text: "Choose how many questions you want in each new batch." })
        ]),
        el("div", { className: "batch-stepper" }, [
          el("button", {
            type: "button",
            "aria-label": "Decrease batch size",
            disabled: batchSize <= 1,
            text: "−",
            onclick: () => actions.adjustBatchSize(-1)
          }),
          el("strong", { "aria-live": "polite", text: String(batchSize) }),
          el("button", {
            type: "button",
            "aria-label": "Increase batch size",
            disabled: batchSize >= 10,
            text: "+",
            onclick: () => actions.adjustBatchSize(1)
          })
        ])
      ]),
      el("p", { className: "settings-note", text: "Your changes apply to future batches." }),
      el("button", {
        type: "button",
        className: "settings-save",
        disabled: state.savingSettings,
        text: state.savingSettings ? "Saving..." : "Save settings",
        onclick: actions.saveSettings
      })
    ])
  ]);
}

function option(value, label, selected) {
  return el("option", { value, selected: value === selected, text: label });
}
