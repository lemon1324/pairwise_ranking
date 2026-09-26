// Settings sheet: redraws the change marks, the errors and the Status cell as values are typed,
// fills the defaults in place for Reset, and saves on Ctrl+S. Ported from
// docs/mockups/settings.js.
//
// It has no rules of its own. Each input carries its saved value, its default, its range and
// the sentences its errors are (templates/settings.html); the form carries the number pattern
// and the two sentences shared by every field. The server draws the same marks and sentences
// for the address it was asked, so this only keeps them true while the values change, and
// disables Save while there is nothing to save or something to fix. Saving is the form's own
// post: no htmx, so no swap to guard.
//
// The slot table (8c) is redrawn the same way: a tile per distinct slot as the list is typed,
// each an input for its short label, with the duplicate and collision warnings and the label
// errors. The board carries the saved labels, the slots in use and the two label sentences.

(() => {
  const form = document.getElementById("settings");
  if (!form) return;
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  const inputs = [...document.querySelectorAll("[data-field]")];
  const pattern = new RegExp(form.dataset.numberPattern);
  const status = $("status");
  const save = $("save");
  const reset = $("reset");
  const RESET_NOTE = "Defaults filled in; the slot list is unchanged. Save to apply.";
  // A tile's field name is this followed by its slot's name (LABEL_PREFIX in the route).
  const LABEL_PREFIX = "label:";

  // The sentence a save or a reset leads the cell with, until the next edit.
  let note = status.dataset.note || "";
  let submitting = false;

  const isSwitch = (el) => el.type === "checkbox";

  // src/web/routes/settings.py parse_value, sentence for sentence.
  function validate(el) {
    if (isSwitch(el)) return { value: el.checked };
    const text = el.value.trim();
    if (!text) return { error: el.dataset.errorEmpty };
    if (!pattern.test(text)) return { error: form.dataset.errorNumber };
    const n = Number(text);
    if (!Number.isFinite(n)) return { error: form.dataset.errorNumber };
    if (el.dataset.whole && !Number.isInteger(n)) return { error: form.dataset.errorWhole };
    const max = el.dataset.max === "" ? null : Number(el.dataset.max);
    if (n < Number(el.dataset.min) || (max !== null && n > max)) return { error: el.dataset.errorRange };
    return { value: n };
  }

  function savedValue(el) {
    return isSwitch(el) ? el.dataset.saved === "1" : Number(el.dataset.saved);
  }

  // ---- The slot table: the list, one label input per tile, the warnings. ----
  // src/web/routes/settings.py build_slot_panel, rule for rule; src/app/slots.py
  // check_slot_labels for the labels.

  const slotsText = $("slots");
  const board = $("slot-board");
  // Maps, never plain objects, for anything looked up by slot name: a slot may be named
  // "toString" or "__proto__", which an object would answer from Object.prototype.
  const savedLabels = new Map(Object.entries(JSON.parse(board.dataset.savedLabels || "{}")));
  const usedSlots = new Set(JSON.parse(board.dataset.used || "[]"));
  const labelMax = Number(board.dataset.labelMax);
  // What each slot's tile holds, kept across redraws so a label survives editing the list.
  const typedLabels = new Map();
  for (const input of board.querySelectorAll(".slot-label")) {
    typedLabels.set(input.name.slice(LABEL_PREFIX.length), input.value);
  }

  // Characters, not UTF-16 units, as Python counts them.
  const chars = (s) => Array.from(s);
  const derivedOf = (name) => chars(name).slice(0, labelMax).join("");

  function parseSlotText(text) {
    const names = [];
    const dups = [];
    for (const part of text.split(/[\n,]/)) {
      const name = part.trim();
      if (!name) continue;
      if (names.includes(name)) {
        if (!dups.includes(name)) dups.push(name);
        continue;
      }
      names.push(name);
    }
    return { names, dups };
  }

  // A slot's typed label, else the one it was saved with.
  const typedOf = (name) => (typedLabels.has(name) ? typedLabels.get(name) : savedLabels.get(name) ?? "").trim();

  // The server's str.format: each name filled in once, as given, "$" patterns and all.
  const fill = (sentence, values) => sentence.replace(/\{(slot|label)\}/g, (_, key) => values[key]);

  // check_slot_labels: the labels worth storing, and the refused ones with their sentences.
  function checkLabels(names) {
    const entered = new Map();
    for (const name of names) {
      const label = typedOf(name);
      if (label && label !== derivedOf(name)) entered.set(name, label);
    }
    const shown = (name) => (entered.has(name) ? chars(entered.get(name)).slice(0, labelMax).join("") : derivedOf(name));
    // A Map, not an object: an object would put names like "12" before the others.
    const errors = new Map();
    names.forEach((name, position) => {
      const label = entered.get(name);
      if (label === undefined) return;
      if (chars(label).length > labelMax) {
        errors.set(name, board.dataset.errorLong);
        return;
      }
      const owner = names.find(
        (other, otherPosition) =>
          other !== name && !(entered.has(other) && otherPosition > position) && shown(other) === label
      );
      if (owner !== undefined) errors.set(name, fill(board.dataset.errorTaken, { slot: owner, label }));
    });
    const groups = new Map();
    for (const name of names) {
      const label = shown(name);
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(name);
    }
    const collisions = [...groups].filter(([, members]) => members.length > 1);
    return { entered, errors, collisions };
  }

  const sameLabels = (a, b) => a.size === b.size && [...a].every(([name, label]) => b.get(name) === label);

  const tileTitle = (name, dup) => `Slot ${name}, ${usedSlots.has(name) ? "in use" : "free"}${dup ? ", listed twice" : ""}`;

  // Draws a tile per distinct slot listed; only when the list changes, so a tile keeps the focus.
  // The server drew the first board; it is kept (and so is its autofocus) until the list changes.
  let boardNames = [...typedLabels.keys()];
  function drawBoard(names, dups) {
    boardNames = names;
    board.innerHTML = names
      .map((name) => {
        const title = esc(tileTitle(name, dups.includes(name)));
        return `<li class="balloon" title="${title}"><input class="slot-label" name="${esc(LABEL_PREFIX + name)}" form="settings" value="${esc(typedLabels.get(name) ?? savedLabels.get(name) ?? "")}" placeholder="${esc(derivedOf(name))}" maxlength="${labelMax}" autocomplete="off" spellcheck="false" aria-label="Short label, ${title}"></li>`;
      })
      .join("");
  }

  // Marks the tiles and writes the errors and warnings; returns what the Status cell needs.
  function updateSlots() {
    const { names, dups } = parseSlotText(slotsText.value);
    if (names.join("\n") !== boardNames.join("\n")) drawBoard(names, dups);
    const { entered, errors, collisions } = checkLabels(names);
    const clashing = new Set(collisions.flatMap(([, members]) => members));
    board.querySelectorAll(".balloon").forEach((tile, i) => {
      const name = names[i];
      const input = tile.querySelector(".slot-label");
      const dup = dups.includes(name);
      tile.classList.toggle("is-used", usedSlots.has(name));
      tile.classList.toggle("is-dup", dup);
      tile.classList.toggle("is-clash", clashing.has(name));
      tile.classList.toggle("is-error", errors.has(name));
      tile.title = tileTitle(name, dup);
      input.setAttribute("aria-label", `Short label, ${tile.title}`);
      if (errors.has(name)) {
        input.setAttribute("aria-invalid", "true");
        input.setAttribute("aria-describedby", "slot-errors");
      } else {
        input.removeAttribute("aria-invalid");
        input.removeAttribute("aria-describedby");
      }
    });
    $("slot-errors").innerHTML = [...errors]
      .map(
        ([name, error]) =>
          `<p class="spec-error"><svg class="icon" aria-hidden="true"><use href="#i-warn"/></svg><span><strong>Slot ${esc(name)}:</strong> ${esc(error)}</span></p>`
      )
      .join("");

    const quiet = collisions.filter(([, members]) => !members.some((m) => errors.has(m)));
    const parts = [];
    if (dups.length) {
      parts.push(
        `<strong>${dups.length === 1 ? `Slot ${esc(dups[0])} is` : `Slots ${dups.map(esc).join(", ")} are`} listed twice.</strong> Duplicates are dropped when you save.`
      );
    }
    if (quiet.length) {
      const sentences = quiet.map(
        ([label, members]) =>
          `<strong>Slots ${members.slice(0, -1).map(esc).join(", ")} and ${esc(members[members.length - 1])} both show ${esc(label)}.</strong>`
      );
      parts.push(`${sentences.join(" ")} Type a short label on one of their tiles.`);
    }
    $("slot-warning").hidden = !parts.length;
    $("slot-warning-text").innerHTML = parts.join(" ");
    $("slots-count").textContent = `${names.length} slots · ${names.filter((n) => usedSlots.has(n)).length} in use`;

    const changed = names.join(", ") !== slotsText.dataset.saved || !sameLabels(entered, savedLabels);
    $("slots-panel").classList.toggle("is-changed", changed);
    return { changed, errors: [...errors].map(([name, error]) => `Slot ${name}: ${error}`) };
  }

  function update() {
    const changed = [];
    const errors = [];
    for (const el of inputs) {
      const key = el.dataset.field;
      const { value, error } = validate(el);
      const row = $(`row-${key}`);
      const err = $(`e-${key}`);
      row.classList.toggle("is-error", !!error);
      err.hidden = !error;
      err.innerHTML = error
        ? `<svg class="icon" aria-hidden="true"><use href="#i-warn"/></svg><span><strong>${esc(error)}</strong></span>`
        : "";
      if (error) el.setAttribute("aria-invalid", "true");
      else el.removeAttribute("aria-invalid");
      const isChanged = error ? el.value.trim() !== el.dataset.saved : value !== savedValue(el);
      row.classList.toggle("is-changed", isChanged);
      if (isSwitch(el)) $(`s-${key}`).textContent = value ? "On" : "Off";
      if (isChanged) changed.push(el.dataset.name);
      if (error) errors.push(`${el.dataset.name}: ${error}`);
    }
    const slots = updateSlots();
    if (slots.changed) changed.push("Slots");
    errors.push(...slots.errors);

    $("status-cell").classList.toggle("is-error", errors.length > 0);
    let text;
    if (errors.length) {
      text = `<strong>Fix ${errors.length} ${errors.length === 1 ? "value" : "values"} before saving.</strong> ${esc(errors.join(" "))}`;
    } else if (changed.length) {
      text = `<strong>${changed.length} unsaved ${changed.length === 1 ? "change" : "changes"}:</strong> ${esc(changed.join(", "))}. Changed values are marked with a triangle.`;
    } else {
      text = `No unsaved changes. Last saved ${esc(status.dataset.lastSaved)}.`;
    }
    if (note && !errors.length) text = `${esc(note)} ${text}`;
    status.innerHTML = text;
    save.disabled = errors.length > 0 || changed.length === 0;
  }

  function edited() {
    note = "";
    update();
  }

  function press() {
    if (submitting) return;
    update();
    if (save.disabled) {
      document.querySelector(".is-error .input, .slot-board .is-error .slot-label")?.focus();
      return;
    }
    form.requestSubmit(save);
  }

  // Every parameter back to its default; the slot list is left as it is. Nothing is saved.
  function fillDefaults() {
    for (const el of inputs) {
      if (isSwitch(el)) el.checked = el.dataset.default === "1";
      else el.value = el.dataset.default;
    }
    note = RESET_NOTE;
    update();
    note = "";
  }

  for (const el of inputs) {
    el.addEventListener("input", edited);
    el.addEventListener("change", edited);
  }
  slotsText.addEventListener("input", edited);
  // Tiles are redrawn, so their typing is heard on the board.
  board.addEventListener("input", (event) => {
    const input = event.target.closest(".slot-label");
    if (!input) return;
    typedLabels.set(input.name.slice(LABEL_PREFIX.length), input.value);
    edited();
  });

  form.addEventListener("submit", (event) => {
    if (submitting) {
      event.preventDefault();
      return;
    }
    submitting = true;
  });
  // Back to this page from the one the save landed on, the browser may restore it as it was left.
  window.addEventListener("pageshow", () => {
    submitting = false;
  });

  reset.addEventListener("click", (event) => {
    event.preventDefault();
    fillDefaults();
  });

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "s") {
      event.preventDefault();
      if (!event.repeat) press();
    } else if (event.key === "Escape" && event.target.closest && event.target.closest("input, textarea")) {
      event.target.blur();
    }
  });

  update();
  // Save's state and the Status cell are this script's from here on; the capture harness waits
  // for this before it photographs the sheet (SETTINGS_CHECK in scripts/capture_web.py).
  form.dataset.ready = "1";
})();
