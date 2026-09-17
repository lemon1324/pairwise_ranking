// Settings mockup: parameter table with change tracking against the saved values, validation,
// reset to defaults (slots untouched), and a slot list with a parsed slot board.
// Mockup only; the real app posts the form and re-renders it server-side.

(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // Field specs mirror src/models/settings.py (names, defaults) and the README's descriptions.
  const GROUPS = [
    ["Pair selection weights", [
      { key: "weight_uncertainty", name: "Uncertainty", help: "Prefer pairs whose order is least certain.", def: 1.0, min: 0, unit: "×" },
      { key: "weight_connectivity", name: "Connectivity", help: "Bonus for pairs that join groups never compared with each other.", def: 1.0, min: 0, unit: "×" },
      { key: "weight_freshness", name: "Freshness", help: "Revisit pairs whose last vote is old.", def: 0.5, min: 0, unit: "×" },
      { key: "weight_uncompared", name: "Uncompared", help: "Bonus for items with few comparisons.", def: 2.0, min: 0, unit: "×" },
    ]],
    ["Vote decay", [
      { key: "decay_timescale_days", name: "Half-life", help: "A vote counts half after this long. 0 turns decay off.", def: 30, min: 0, unit: "days" },
    ]],
    ["Top-tier focus", [
      { key: "top_tier_mode", name: "Top-tier focus", help: "Spend more comparisons near the top of the ranking.", def: false, type: "bool" },
      { key: "top_tier_count", name: "Top-tier size", help: "How many top-ranked items count as the top tier.", def: 10, min: 1, unit: "items", type: "int" },
      { key: "top_tier_weight", name: "Top-tier weight", help: "Extra weight for pairs involving the top tier.", def: 2.0, min: 0, unit: "×" },
    ]],
    ["Category comparisons", [
      { key: "cross_category_rate", name: "Cross-category rate", help: "Share of comparisons that may cross categories. 0 never, 1 ignores categories.", def: 0.1, min: 0, max: 1, unit: "" },
    ]],
    ["Comparison mode", [
      { key: "blinded_comparison_mode", name: "Blinded", help: "Show only slot identifiers when comparing. Items without a slot are skipped.", def: false, type: "bool" },
    ]],
  ];
  const FIELDS = GROUPS.flatMap(([, fields]) => fields);
  const byKey = Object.fromEntries(FIELDS.map((f) => [f.key, f]));

  // Numbers keep their precision; whole-number weights still show one decimal (1.0, 2.0).
  const fmt = (f, v) => {
    if (f.type === "bool") return v ? "On" : "Off";
    const n = Number(v);
    if (f.type === "int" || f.unit === "days") return String(n);
    if (f.key === "cross_category_rate") return n.toFixed(2);
    return Number.isInteger(n) ? n.toFixed(1) : String(n);
  };
  const range = (f) => {
    if (f.type === "bool") return "on / off";
    if (f.max != null) return `${f.min}–${f.max}`;
    return `≥ ${f.min}${f.unit && f.unit !== "×" ? ` ${f.unit}` : ""}`;
  };

  const usedSlots = new Set(window.SAMPLE.items.filter((it) => it.status === "active" && it.slot).map((it) => it.slot));

  let saved;
  let savedSlots;
  let lastSaved;

  function renderTable() {
    $("params").innerHTML = GROUPS.map(([title, fields]) => {
      const rows = fields
        .map((f) => {
          const control =
            f.type === "bool"
              ? `<label class="switch"><input type="checkbox" id="f-${f.key}" name="${f.key}"><span class="switch-state" id="s-${f.key}">Off</span><span class="visually-hidden">${esc(f.name)}</span></label>`
              : `<label class="visually-hidden" for="f-${f.key}">${esc(f.name)}</label><input class="input num" id="f-${f.key}" name="${f.key}" inputmode="decimal" autocomplete="off" aria-describedby="h-${f.key}">`;
          return `<tr id="row-${f.key}">
            <td>
              <span class="spec-name">${esc(f.name)}</span>
              <span class="spec-help" id="h-${f.key}">${esc(f.help)}</span>
              <span class="spec-phone-meta">Default ${fmt(f, f.def)} · ${range(f)}</span>
              <p class="spec-error" id="e-${f.key}" hidden></p>
            </td>
            <td><div class="spec-value"><svg class="rev-mark" viewBox="0 0 14 14" role="img" aria-label="changed"><use href="#i-rev"/></svg>${control}</div></td>
            <td class="spec-default c-default">${fmt(f, f.def)}</td>
            <td class="spec-range c-range">${range(f)}</td>
          </tr>`;
        })
        .join("");
      return `<tr class="spec-group"><th colspan="4" scope="rowgroup">${esc(title)}</th></tr>${rows}`;
    }).join("");
  }

  function read(f) {
    const el = $(`f-${f.key}`);
    return f.type === "bool" ? el.checked : el.value.trim();
  }

  function write(f, v) {
    const el = $(`f-${f.key}`);
    if (f.type === "bool") el.checked = !!v;
    else el.value = fmt(f, v);
  }

  function validate(f, raw) {
    if (f.type === "bool") return { value: raw };
    if (raw === "") return { error: `Enter a value${f.max != null ? ` from ${f.min} to ${f.max}` : ` of ${f.min} or more`}.` };
    const n = Number(raw);
    if (!Number.isFinite(n)) return { error: "Enter a number." };
    if (f.type === "int" && !Number.isInteger(n)) return { error: "Enter a whole number." };
    if (n < f.min || (f.max != null && n > f.max)) {
      return { error: f.max != null ? `Must be between ${f.min} and ${f.max}.` : `Must be ${f.min} or more.` };
    }
    return { value: n };
  }

  // Slot entries: "Name" or "Name = short label". The list is kept as one comma-separated line.
  function parseEntries(text) {
    return text
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map((p) => {
        const [name, short] = p.split("=").map((s) => s.trim());
        return { name, short: short || null };
      })
      .filter((e) => e.name);
  }

  const shortFor = (e) => e.short ?? (e.name.length <= 2 ? e.name : e.name.slice(0, 2));
  const serialize = (entries) => entries.map((e) => (e.short ? `${e.name} = ${e.short}` : e.name)).join(", ");

  function parseSlots(text) {
    const entries = parseEntries(text);
    const seen = new Map();
    const dups = new Set();
    for (const e of entries) {
      if (seen.has(e.name)) dups.add(e.name);
      else seen.set(e.name, e);
    }
    return { entries: [...seen.values()], list: [...seen.keys()], dups: [...dups] };
  }

  function update() {
    const changed = [];
    const errors = [];
    for (const f of FIELDS) {
      const raw = read(f);
      const { value, error } = validate(f, raw);
      const row = $(`row-${f.key}`);
      const err = $(`e-${f.key}`);
      row.classList.toggle("is-error", !!error);
      err.hidden = !error;
      err.innerHTML = error ? `<svg class="icon" aria-hidden="true"><use href="#i-warn"/></svg><span><strong>${esc(error)}</strong></span>` : "";
      $(`f-${f.key}`).toggleAttribute("aria-invalid", !!error);
      const isChanged = error ? raw !== fmt(f, saved[f.key]) : value !== saved[f.key];
      row.classList.toggle("is-changed", isChanged);
      if (f.type === "bool") $(`s-${f.key}`).textContent = value ? "On" : "Off";
      if (isChanged) changed.push(f.name);
      if (error) errors.push(`${f.name}: ${error}`);
    }

    const slotText = $("slots").value;
    const { entries, list, dups } = parseSlots(slotText);
    const slotsChanged = serialize(entries) !== savedSlots;
    $("slots-panel").classList.toggle("is-changed", slotsChanged);
    if (slotsChanged) changed.push("Slots");
    $("slots-count").textContent = `${list.length} slots · ${list.filter((s) => usedSlots.has(s)).length} in use`;
    // The board shows short labels; the full name and state are on hover and for screen readers.
    $("slot-board").innerHTML = entries
      .map((e) => {
        const used = usedSlots.has(e.name);
        const dup = dups.includes(e.name);
        const cls = ["balloon"];
        if (used) cls.push("is-used");
        if (dup) cls.push("is-dup");
        const label = `Slot ${esc(e.name)}, ${used ? "in use" : "free"}${dup ? ", listed twice" : ""}`;
        return `<li class="${cls.join(" ")}" title="${label}" aria-label="${label}">${esc(shortFor(e))}</li>`;
      })
      .join("");
    const warning = $("slot-warning");
    warning.hidden = !dups.length;
    $("slot-warning-text").innerHTML = dups.length
      ? `<strong>${dups.length === 1 ? `Slot ${esc(dups[0])} is` : `Slots ${dups.map(esc).join(", ")} are`} listed twice.</strong> Duplicates are dropped when you save.`
      : "";

    const cell = $("status-cell");
    cell.classList.toggle("is-error", errors.length > 0);
    let status;
    if (errors.length) {
      status = `<strong>Fix ${errors.length} ${errors.length === 1 ? "value" : "values"} before saving.</strong> ${esc(errors.join(" "))}`;
    } else if (changed.length) {
      status = `<strong>${changed.length} unsaved ${changed.length === 1 ? "change" : "changes"}:</strong> ${esc(changed.join(", "))}. Changed values are marked with a triangle.`;
    } else {
      status = `No unsaved changes. Last saved ${lastSaved}.`;
    }
    if (note && !errors.length) status = `${note} ${status}`;
    $("status").innerHTML = status;
    $("save").disabled = errors.length > 0 || changed.length === 0;
  }

  let note = "";

  function save() {
    update();
    if ($("save").disabled) {
      document.querySelector(".is-error .input")?.focus();
      return;
    }
    for (const f of FIELDS) saved[f.key] = validate(f, read(f)).value;
    // Saving normalizes the list to one comma-separated line, dropping duplicates.
    savedSlots = serialize(parseSlots($("slots").value).entries);
    $("slots").value = savedSlots;
    lastSaved = "21:07";
    note = "Saved.";
    update();
    note = "";
  }

  function reset() {
    for (const f of FIELDS) write(f, f.def);
    note = "Defaults filled in; the slot list is unchanged. Save to apply.";
    update();
    note = "";
  }

  function applyState(state) {
    saved = Object.fromEntries(FIELDS.map((f) => [f.key, f.def]));
    saved.weight_uncompared = 3.0;
    saved.decay_timescale_days = 45;
    savedSlots = serialize(window.SAMPLE.slots.map((name) => ({ name, short: window.SLOT_SHORT[name] ?? null })));
    lastSaved = "20:58";
    renderTable();
    for (const f of FIELDS) write(f, saved[f.key]);
    $("slots").value = savedSlots;
    if (state === "changed" || state === "invalid") {
      write(byKey.weight_freshness, 0.75);
      write(byKey.top_tier_mode, true);
      write(byKey.blinded_comparison_mode, true);
    }
    if (state === "invalid") $("f-cross_category_rate").value = "1.5";
    if (state === "dupslots") $("slots").value = `${savedSlots}, 7, Esc`;
    update();
    if (state === "reset") reset();
  }

  $("settings").addEventListener("input", (e) => {
    if (e.target.closest(".mockup-controls")) return;
    update();
  });
  $("settings").addEventListener("change", update);
  $("settings").addEventListener("submit", (e) => {
    e.preventDefault();
    save();
  });
  $("reset").addEventListener("click", reset);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      save();
    } else if (e.key === "Escape" && e.target.closest("input, textarea")) {
      e.target.blur();
    }
  });

  document.querySelectorAll('input[name="state"]').forEach((input) =>
    input.addEventListener("change", () => applyState(input.value))
  );
  document.querySelectorAll('input[name="theme"]').forEach((input) =>
    input.addEventListener("change", () => {
      if (input.value === "auto") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", input.value);
    })
  );

  // ?state=changed&theme=dark opens the mockup in a given state (used for review captures).
  const params = new URLSearchParams(location.search);
  const startTheme = params.get("theme");
  if (startTheme) document.querySelector(`input[name="theme"][value="${startTheme}"]`)?.click();
  const startState = params.get("state") || "normal";
  const picker = document.querySelector(`input[name="state"][value="${startState}"]`);
  if (picker) picker.checked = true;
  applyState(picker ? startState : "normal");
})();
