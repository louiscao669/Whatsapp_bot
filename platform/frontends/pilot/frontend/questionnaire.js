/**
 * Background & eligibility questionnaire: shown after consent, before Question 1.
 *
 * One section per screen, in the server's order (A eligibility -> B background
 * -> C consent prompt + items -> D familiarity). The server decides which
 * section is due; earlier sections can be edited until the questionnaire is finished.
 * Nothing here scores or reveals anything: the Section D key never reaches the
 * browser and no response carries a score.
 *
 * Like the rest of the pilot frontend: no timers and no polling. Every request
 * is triggered by a click.
 */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function label(value, language) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value[language] || value.zh || value.en || "";
}

export function renderScreenedOut(root, ui) {
  root.replaceChildren();
  const card = el("section", "pilot-card");
  card.append(el("h1", "pilot-title", ui.screened_out_title));
  card.append(el("p", "pilot-body", ui.screened_out_body));
  root.append(card);
}

/**
 * Render the section that is due. `onDone()` runs once the server reports the
 * questionnaire complete (or not required); `onScreenedOut(ui)` on screen-out.
 */
export function renderQuestionnaire(root, api, state, { onDone, onScreenedOut }) {
  const instrument = state.instrument;
  const language = instrument.language;
  const ui = instrument.ui;
  const sections = instrument.sections;
  const drafts = { ...state.answers };
  let due = state.status;
  let religionConsent = state.religion_consent;

  function sectionById(id) {
    return sections.find((entry) => entry.id === id);
  }

  async function send(sectionId, answers, extra, controls) {
    controls.buttons.forEach((button) => (button.disabled = true));
    controls.status.textContent = ui.saving;
    let result;
    try {
      result = await api.submitQuestionnaire({
        section: sectionId, answers, ...extra, ...(sectionId !== due ? { edit: true } : {})
      });
    } catch (error) {
      controls.buttons.forEach((button) => (button.disabled = false));
      controls.status.textContent = error.message;
      return;
    }
    drafts[sectionId] = answers;
    if (sectionId === "religion") religionConsent = extra.religion_consent;
    due = result.status;
    const next = sections[sections.indexOf(sectionById(sectionId)) + 1];
    route(sectionById(due) && next ? next.id : due);
  }

  function route(status) {
    if (status === "screened_out") {
      onScreenedOut(ui);
    } else if (status === "complete" || status === "not_required") {
      onDone();
    } else if (sectionById(status)) {
      showSection(status);
    } else {
      onDone();
    }
  }

  function header(card, entry) {
    const index = sections.indexOf(entry) + 1;
    card.append(
      el(
        "p",
        "pilot-step",
        ui.step.replace("{n}", String(index)).replace("{total}", String(sections.length))
      )
    );
    if (index === 1) {
      card.append(el("h1", "pilot-title", ui.heading));
      card.append(el("p", "pilot-body", ui.intro));
    }
    card.append(el("h2", "pilot-q-section", label(entry.title, language)));
    if (entry.intro) card.append(el("p", "pilot-q-intro", label(entry.intro, language)));
  }

  function renderItem(item, readers, values, required) {
    const group = el("fieldset", "pilot-q-item");
    group.append(el("legend", "pilot-q-text", label(item.text, language)));
    if (item.help) group.append(el("p", "pilot-q-help", label(item.help, language)));

    if (item.type === "single") {
      const list = el("div", "pilot-choices");
      let specifyInput = null;
      const clear = el("button", "pilot-q-clear", ui.clear_answer);
      clear.type = "button";
      clear.hidden = !values[item.id];
      item.options.forEach((option) => {
        const row = el("label", "pilot-choice");
        const input = document.createElement("input");
        input.type = "radio";
        input.name = item.id;
        input.value = option.code;
        input.checked = values[item.id] === option.code;
        row.append(input, el("span", "pilot-choice-text", label(option, language)));
        list.append(row);
        input.addEventListener("change", () => {
          clear.hidden = false;
          if (specifyInput) {
            const on = input.value === item.specify.option;
            specifyInput.hidden = !on;
            if (!on) specifyInput.value = "";
          }
        });
      });
      group.append(list);
      if (item.specify) {
        specifyInput = document.createElement("input");
        specifyInput.type = "text";
        specifyInput.className = "pilot-q-input";
        specifyInput.placeholder = ui.specify_placeholder;
        specifyInput.maxLength = 120;
        specifyInput.hidden = values[item.id] !== item.specify.option;
        specifyInput.value = values[item.specify.id] || "";
        group.append(specifyInput);
        readers[item.specify.id] = () => specifyInput.value.trim() || null;
      }
      readers[item.id] = () => {
        const checked = group.querySelector(`input[name='${item.id}']:checked`);
        return checked ? checked.value : null;
      };
      if (!required) {
        clear.addEventListener("click", () => {
          const checked = list.querySelector("input:checked");
          if (checked) checked.checked = false;
          if (specifyInput) {
            specifyInput.value = "";
            specifyInput.hidden = true;
          }
          clear.hidden = true;
          list.querySelector("input").focus();
        });
        group.append(clear);
      }
    } else if (item.type === "text_or_prefer_not") {
      const input = document.createElement("input");
      input.type = "text";
      input.className = "pilot-q-input";
      input.placeholder = ui.text_placeholder;
      input.maxLength = item.max_length || 120;
      const prefer = el("label", "pilot-choice");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = values[item.id] === "prefer_not_to_say";
      input.disabled = box.checked;
      input.value = box.checked ? "" : values[item.id] || "";
      prefer.append(box, el("span", "pilot-choice-text", language === "en" ? "Prefer not to say" : "不愿透露"));
      box.addEventListener("change", () => {
        input.disabled = box.checked;
        if (box.checked) input.value = "";
      });
      group.append(input, prefer);
      readers[item.id] = () => (box.checked ? "prefer_not_to_say" : input.value.trim() || null);
    }
    return group;
  }

  function previousButton(onClick) {
    const button = el("button", "pilot-submit pilot-decline", ui.previous);
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  }

  function itemsForm(card, entry, { submitLabel, extra, previous }) {
    const form = el("form", "pilot-form");
    form.noValidate = true;
    const readers = {};
    entry.items.forEach((item) => form.append(renderItem(item, readers, drafts[entry.id] || {}, entry.required)));
    function readAnswers() {
      const answers = {};
      Object.entries(readers).forEach(([id, read]) => {
        const value = read();
        if (value !== null) answers[id] = value;
      });
      return answers;
    }
    const actions = el("div", "pilot-q-actions");
    const buttons = [];
    if (previous) {
      const back = previousButton(() => {
        drafts[entry.id] = readAnswers();
        previous();
      });
      actions.append(back);
      buttons.push(back);
    }
    const submit = el("button", "pilot-submit", submitLabel);
    submit.type = "submit";
    const status = el("p", "pilot-status", "");
    buttons.push(submit);
    actions.append(submit);
    form.append(actions, status);
    form.addEventListener("change", () => {
      if (status.textContent === ui.required_missing) status.textContent = "";
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const answers = readAnswers();
      if (entry.required && entry.items.some((item) => !answers[item.id])) {
        status.textContent = ui.required_missing;
        return;
      }
      send(entry.id, answers, extra, { buttons, status });
    });
    card.append(form);
  }

  function showSection(sectionId, religionItems = false) {
    const entry = sectionById(sectionId);
    root.replaceChildren();
    const card = el("section", "pilot-card pilot-questionnaire");
    header(card, entry);
    const isLast = sections.indexOf(entry) === sections.length - 1;
    const submitLabel = isLast ? ui.finish : ui.continue;

    const previous = sections[sections.indexOf(entry) - 1];
    const goBack = previous && (() => showSection(previous.id, previous.id === "religion" && religionConsent));
    if (entry.consent_prompt && !religionItems) {
      // Section C: its own consent prompt first; declining skips the items.
      const prompt = entry.consent_prompt;
      card.append(el("p", "pilot-q-consent", label(prompt, language)));
      const actions = el("div", "pilot-consent-actions");
      const agree = el("button", "pilot-submit", label(prompt.agree, language));
      const decline = el("button", "pilot-submit pilot-decline", label(prompt.decline, language));
      agree.type = "button";
      decline.type = "button";
      const status = el("p", "pilot-status", "");
      const back = previousButton(goBack);
      agree.addEventListener("click", () => showSection(entry.id, true));
      decline.addEventListener("click", () =>
        send(entry.id, {}, { religion_consent: false }, { buttons: [back, agree, decline], status })
      );
      actions.append(agree, decline);
      card.append(actions, back, status);
    } else {
      itemsForm(card, entry, {
        submitLabel,
        extra: religionItems ? { religion_consent: true } : {},
        previous: religionItems ? () => showSection(entry.id) : goBack
      });
    }
    root.append(card);
    window.scrollTo(0, 0);
  }

  route(state.status);
}
