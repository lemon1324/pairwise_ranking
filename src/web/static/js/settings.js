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
      document.querySelector(".is-error .input")?.focus();
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
})();
