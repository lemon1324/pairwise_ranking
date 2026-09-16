// Items mockup: parts list with slot balloons, a callout strip of actions under the selected row,
// in-strip forms for edit, new, replace and reactivate, and in-strip delete confirmation.
// Mockup only; the real app renders rows server-side and swaps strips with HTMX.

(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const svg = (id) => `<svg class="icon" aria-hidden="true"><use href="#${id}"/></svg>`;

  let items;
  let slots;
  let showRetired;
  let filter;
  let mode; // null | "edit" | "new" | "replace" | "reactivate" | "delete"
  let draft; // form values when re-rendering with an error
  let error; // { field, html }
  let lastChange;
  let nextId = 1000;

  const byId = (id) => items.find((it) => it.id === id);
  const active = () => items.filter((it) => it.status === "active");
  const usedSlots = (exceptId) =>
    new Map(active().filter((it) => it.slot && it.id !== exceptId).map((it) => [it.slot, it]));
  const freeSlots = (exceptId) => {
    if (!slots) return [];
    const used = usedSlots(exceptId);
    return slots.filter((s) => !used.has(s));
  };
  const label = (it) => (it.slot ? `(${it.slot}) ${it.name}` : it.name);

  function reset(state) {
    items = window.SAMPLE.items.map((it) => ({ ...it }));
    slots = [...window.SAMPLE.slots];
    showRetired = false;
    filter = "";
    mode = null;
    draft = null;
    error = null;
    lastChange = "Edited (21) Kailh Box White V2 · 20:58";
    if (state === "empty") {
      items = [];
      lastChange = "No changes yet.";
    }
    if (state === "noslots") {
      slots = null;
    }
    if (state === "full") {
      slots = active().filter((it) => it.slot).map((it) => it.slot);
      slots.sort((a, b) => Number(a) - Number(b));
    }
    if (state === "retired") showRetired = true;
    $("filter").value = "";
  }

  function rows() {
    const q = filter.trim().toLowerCase();
    const list = items
      .filter((it) => showRetired || it.status === "active")
      .filter((it) => !q || it.name.toLowerCase().includes(q))
      .sort((a, b) => {
        const rank = (it) => (it.status === "retired" ? 2 : it.slot ? 0 : 1);
        if (rank(a) !== rank(b)) return rank(a) - rank(b);
        if (a.slot && b.slot) return Number(a.slot) - Number(b.slot) || a.slot.localeCompare(b.slot);
        return a.name.localeCompare(b.name);
      });
    if (mode === "new") list.unshift({ id: "__new", name: "New item", cat: "", desc: "", slot: "", status: "new" });
    return list;
  }

  const head = `
    <thead><tr>
      <th class="c-find" style="width:3.5rem">Slot</th>
      <th>Name</th>
      <th class="c-cat" style="width:6.5rem">Category</th>
      <th style="width:6.25rem">Status</th>
    </tr></thead>`;

  function rowHtml(it, selected) {
    const cls = ["bom-row"];
    if (selected) cls.push("is-selected");
    if (it.status === "retired") cls.push("is-retired");
    if (it.status === "new") cls.push("is-new");
    const balloon = it.slot
      ? `<span class="balloon">${esc(it.slot)}</span>`
      : `<span class="balloon is-empty" aria-hidden="true">–</span>`;
    let status = `<span class="status">Active</span>`;
    if (it.status === "retired") status = `<span class="tag">Retired</span>`;
    else if (it.status === "new") status = `<span class="tag">New</span>`;
    else if (!it.slot) status = `<span class="tag">No slot</span>`;
    return `<tr class="${cls.join(" ")}" data-id="${it.id}" tabindex="-1" aria-selected="${selected}">
      <td class="c-find">${balloon}</td>
      <td><span class="bom-name">${esc(it.name)}</span>${it.desc ? `<span class="bom-desc">${esc(it.desc)}</span>` : ""}</td>
      <td class="c-cat"><span class="bom-cat">${esc(it.cat)}</span></td>
      <td>${status}</td>
    </tr>`;
  }

  // Content of the floating callout under the selected row.
  function stripHtml(it) {
    if (mode === "delete") return confirmHtml(it);
    if (mode) return formHtml(it);
    return actionsHtml(it);
  }

  function actionsHtml(it) {
    const act = (action, text, key) =>
      `<button class="strip-action" type="button" data-action="${action}">${text}<span class="key">${key}</span></button>`;
    if (it.status === "retired") {
      return `<div class="strip-actions">${act("reactivate", "Reactivate", "A")}${act("delete", "Delete", "Del")}</div>`;
    }
    return `<div class="strip-actions">${act("edit", "Edit", "↵")}${act("retire", "Retire", "R")}${act("replace", "Replace", "P")}${act("delete", "Delete", "Del")}</div>`;
  }

  function confirmHtml(it) {
    return `<div class="strip-confirm" role="alertdialog" aria-labelledby="confirm-q">
      ${svg("i-warn")}
      <div>
        <p id="confirm-q"><strong>Delete ${esc(label(it))} and its ${it.votes} votes?</strong></p>
        <p>This can’t be undone. Retire keeps the votes and frees the slot instead.</p>
        <div class="strip-buttons">
          <button class="cell-button is-danger" type="button" data-action="confirm-delete">Delete <span class="key">Del</span></button>
          <button class="cell-button" type="button" data-action="cancel">Cancel <span class="key">Esc</span></button>
        </div>
      </div>
    </div>`;
  }

  function formHtml(it) {
    const titles = {
      edit: `Edit ${esc(label(it))}`,
      new: "New item",
      replace: `Replace ${esc(label(it))}`,
      reactivate: `Reactivate ${esc(it.name)}`,
    };
    const base =
      mode === "edit"
        ? it
        : mode === "replace"
          ? { name: "", cat: it.cat, slot: it.slot, desc: "" }
          : mode === "reactivate"
            ? { ...it, slot: freeSlots()[0] || "" }
            : { name: "", cat: "", slot: freeSlots()[0] || "", desc: "" };
    const v = draft || base;
    const exceptId = mode === "edit" ? it.id : mode === "replace" ? it.id : null;
    const free = freeSlots(exceptId);
    const fieldCls = (name) => `field${error && error.field === name ? " is-error" : ""}`;
    const err = (name) => (error && error.field === name ? `<p class="field-error" id="err-${name}">${svg("i-warn")}<span>${error.html}</span></p>` : "");
    const describedBy = (name) => (error && error.field === name ? ` aria-invalid="true" aria-describedby="err-${name}"` : "");
    let slotHint;
    if (!slots) slotHint = "No slot list: any identifier, unique among active items.";
    else if (free.length) slotHint = `Free: <span class="num">${free.map(esc).join(", ")}</span>`;
    else slotHint = "No free slots. Retire an item or extend the slot list in Settings.";
    const note =
      mode === "replace"
        ? `<p class="field-hint field-wide">Saving retires ${esc(it.name)} (its votes are kept) and adds this item in its slot.</p>`
        : "";
    return `<div class="strip-body">
      <p class="strip-title"><span class="label">Form</span>${titles[mode]}</p>
      <form class="strip-form" data-form="${mode}" novalidate>
        ${mode === "reactivate" ? "" : `<div class="${fieldCls("name")} field-wide">
          <label class="label" for="f-name">Name</label>
          <input class="input" id="f-name" name="name" value="${esc(v.name)}" autocomplete="off" required${describedBy("name")}>
          ${err("name")}
        </div>`}
        ${mode === "reactivate" ? "" : `<div class="field">
          <label class="label" for="f-cat">Category</label>
          <input class="input" id="f-cat" name="cat" list="dl-categories" value="${esc(v.cat)}" autocomplete="off">
          <span class="field-hint">Pick one or type a new category.</span>
        </div>`}
        <div class="${fieldCls("slot")}${mode === "reactivate" ? " field-wide" : ""}">
          <label class="label" for="f-slot">Slot</label>
          <input class="input num" id="f-slot" name="slot" list="dl-slots" value="${esc(v.slot)}" autocomplete="off"${describedBy("slot")}>
          ${err("slot") || `<span class="field-hint">${slotHint}</span>`}
        </div>
        ${mode === "reactivate" ? "" : `<div class="field field-wide">
          <label class="label" for="f-desc">Description</label>
          <textarea class="input" id="f-desc" name="desc" rows="2">${esc(v.desc)}</textarea>
        </div>`}
        ${note}
        <div class="strip-buttons">
          <button class="cell-button is-primary" type="submit">${mode === "reactivate" ? "Reactivate" : "Save"} <span class="key">↵</span></button>
          <button class="cell-button" type="button" data-action="cancel">Cancel <span class="key">Esc</span></button>
        </div>
      </form>
    </div>`;
  }

  function emptyHtml() {
    if (!items.length) {
      return `<div class="bom-empty">
        <p class="lead">No items yet.</p>
        <p class="detail">Add the things you want to rank. Each item can take a slot from the board.</p>
        <button class="cell-button" type="button" data-action="new">Add item <span class="key">N</span></button>
      </div>`;
    }
    return `<div class="bom-empty">
      <p class="lead">No items match “${esc(filter)}”.</p>
      <p class="detail">${showRetired ? "" : "Retired items are hidden. "}Clear the filter with Esc.</p>
    </div>`;
  }

  const sheet = window.BomSheet({
    field: $("field"),
    titleblock: $("titleblock"),
    caption: "Items",
    head,
    rows,
    rowHtml,
    stripHtml,
    emptyHtml,
    onPage: (page, pages) => {
      $("sheet-no").textContent = `${page + 1} of ${pages}`;
      $("page-prev").disabled = page === 0;
      $("page-next").disabled = page >= pages - 1;
    },
    onSelect: (id) => {
      if (id !== "__new") {
        mode = null;
        draft = null;
        error = null;
      }
    },
    // Clicking the selected row again is the same as Esc: close a form, otherwise deselect.
    onRowClick: (id, wasSelected) => {
      if (!wasSelected) return false;
      if (mode) cancel();
      else sheet.clear();
      return true;
    },
    onKey: handleKey,
  });

  function renderTitleblock() {
    const act = active();
    const retired = items.length - act.length;
    if (!slots) {
      $("tb-slots").innerHTML = `No slot list. Identifiers are free text.`;
    } else {
      const used = usedSlots().size;
      const free = freeSlots();
      const listed = free.length > 8 ? `${free.slice(0, 6).join(" ")}</span> and ${free.length - 6} more<span>` : free.join(" ");
      $("tb-slots").innerHTML =
        `<span class="num">${used}/${slots.length}</span> used · ` +
        (free.length ? `free <span class="num">${listed}</span>` : `<strong>none free</strong>`);
    }
    $("tb-counts").innerHTML =
      `<span class="num">${act.length}</span> active · <span class="num">${retired}</span> retired`;
    $("tb-last").textContent = lastChange;
    $("toggle-retired").setAttribute("aria-pressed", String(showRetired));
    $("retired-text").textContent = showRetired ? "Shown" : "Hidden";
    $("retired-icon").setAttribute("href", showRetired ? "#i-eye" : "#i-eye-off");
    $("dl-categories").innerHTML = [...new Set(items.map((it) => it.cat).filter(Boolean))]
      .sort()
      .map((c) => `<option value="${esc(c)}">`)
      .join("");
    const exceptId = mode === "edit" || mode === "replace" ? sheet.selectedId : null;
    $("dl-slots").innerHTML = freeSlots(exceptId).map((s) => `<option value="${esc(s)}">`).join("");
  }

  function render({ focus = true } = {}) {
    renderTitleblock();
    sheet.render();
    if (mode && mode !== "delete") {
      const first = $("field").querySelector(error ? ".is-error .input" : ".strip-form .input");
      if (first) {
        first.focus({ preventScroll: true });
        if (first.select && !error) first.select();
      }
    } else if (mode === "delete") {
      $("field").querySelector('[data-action="confirm-delete"]')?.focus({ preventScroll: true });
    } else if (focus) {
      sheet.focusSelected();
    }
    const lastRow = $("field").querySelector(".bom-row.is-selected");
    if (lastRow && lastRow.scrollIntoView && matchMedia("(max-width: 40rem)").matches) lastRow.scrollIntoView({ block: "nearest" });
  }

  function setMode(next) {
    mode = next;
    draft = null;
    error = null;
    render();
  }

  function selectedItem() {
    return sheet.selectedId && sheet.selectedId !== "__new" ? byId(sheet.selectedId) : null;
  }

  function neighbourAfterRemoval(id) {
    const list = rows();
    const i = list.findIndex((r) => r.id === id);
    const next = list[i + 1] || list[i - 1];
    return next ? next.id : null;
  }

  function now() {
    return "21:06";
  }

  function retire(it) {
    if (it.status !== "active") return;
    const next = showRetired ? it.id : neighbourAfterRemoval(it.id);
    const slot = it.slot;
    it.status = "retired";
    it.slot = "";
    lastChange = `Retired ${it.name}${slot ? ` · slot ${slot} freed` : ""} · ${now()}`;
    sheet.selectedId = next;
    mode = null;
    render();
  }

  function remove(it) {
    const next = neighbourAfterRemoval(it.id);
    items = items.filter((x) => x.id !== it.id);
    lastChange = `Deleted ${label(it)} and its ${it.votes} votes · ${now()}`;
    sheet.selectedId = next;
    mode = null;
    render();
  }

  function readForm(form) {
    const data = Object.fromEntries(new FormData(form));
    return {
      name: (data.name ?? "").trim(),
      cat: (data.cat ?? "").trim(),
      slot: (data.slot ?? "").trim(),
      desc: (data.desc ?? "").trim(),
    };
  }

  function submit(form) {
    const it = selectedItem();
    const v = readForm(form);
    const exceptId = mode === "edit" || mode === "replace" ? it.id : null;
    if (mode !== "reactivate" && !v.name) {
      draft = v;
      error = { field: "name", html: "<strong>Name is required.</strong>" };
      render();
      return;
    }
    if (v.slot) {
      const holder = usedSlots(exceptId).get(v.slot);
      if (holder) {
        const free = freeSlots(exceptId);
        draft = mode === "reactivate" ? { ...it, slot: v.slot } : v;
        error = {
          field: "slot",
          html:
            `<strong>Slot ${esc(v.slot)} is taken</strong> by ${esc(holder.name)}. ` +
            (free.length ? `Free slots: <span class="num">${free.join(", ")}</span>.` : "No slots are free."),
        };
        render();
        return;
      }
    }
    if (mode === "edit") {
      Object.assign(it, { name: v.name, cat: v.cat || "Default", slot: v.slot, desc: v.desc });
      lastChange = `Edited ${label(it)} · ${now()}`;
    } else if (mode === "new") {
      const created = { id: `it${nextId++}`, name: v.name, cat: v.cat || "Default", slot: v.slot, desc: v.desc, status: "active", votes: 0 };
      items.push(created);
      lastChange = `Added ${label(created)} · ${now()}`;
      sheet.selectedId = created.id;
    } else if (mode === "replace") {
      const created = { id: `it${nextId++}`, name: v.name, cat: v.cat || it.cat, slot: v.slot, desc: v.desc, status: "active", votes: 0 };
      it.status = "retired";
      it.slot = "";
      items.push(created);
      lastChange = `Replaced ${it.name} with ${label(created)} · ${now()}`;
      sheet.selectedId = created.id;
    } else if (mode === "reactivate") {
      it.status = "active";
      it.slot = v.slot;
      lastChange = `Reactivated ${label(it)} · ${now()}`;
    }
    mode = null;
    draft = null;
    error = null;
    render();
  }

  function cancel() {
    const wasNew = mode === "new";
    mode = null;
    draft = null;
    error = null;
    if (wasNew) sheet.selectedId = null;
    render();
  }

  function startNew() {
    sheet.selectedId = "__new";
    mode = "new";
    draft = null;
    error = null;
    render();
  }

  function handleKey(e, inControl) {
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    // Enter and Space on a focused button or link activate it, not the row shortcut.
    if (!inControl && e.target.closest("button, a") && (e.key === "Enter" || e.key === " ")) return false;
    const it = selectedItem();
    if (e.key === "Escape") {
      if (mode) cancel();
      else if (filter) {
        filter = "";
        $("filter").value = "";
        render();
      } else if (sheet.selectedId) {
        sheet.selectedId = null;
        render({ focus: false });
        document.activeElement?.blur();
      }
      return true;
    }
    if (inControl) {
      if (e.target.id === "filter" && e.key === "Enter") {
        e.target.blur();
        const first = rows()[0];
        if (first) sheet.select(first.id);
        return true;
      }
      if (e.key === "Enter" && e.target.tagName === "TEXTAREA" && !e.ctrlKey) return false;
      return false;
    }
    if (mode === "delete") {
      if (e.key === "Delete" || e.key === "Backspace") {
        remove(it);
        return true;
      }
      return false;
    }
    if (mode) return false;
    switch (e.key) {
      case "Enter":
        if (it && it.status === "active") setMode("edit");
        return !!it;
      case "n":
      case "N":
        startNew();
        return true;
      case "r":
      case "R":
        if (it) retire(it);
        return !!it;
      case "p":
      case "P":
        if (it && it.status === "active") setMode("replace");
        return !!it;
      case "a":
      case "A":
        if (it && it.status === "retired") setMode("reactivate");
        return !!it;
      case "Delete":
        if (it) setMode("delete");
        return !!it;
      case "h":
      case "H":
        toggleRetired();
        return true;
      case "/":
        $("filter").focus();
        return true;
      default:
        return false;
    }
  }

  function toggleRetired() {
    showRetired = !showRetired;
    const it = selectedItem();
    if (it && it.status === "retired" && !showRetired) sheet.selectedId = null;
    mode = null;
    render({ focus: false });
  }

  $("field").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const it = selectedItem();
    const action = btn.dataset.action;
    if (action === "new") startNew();
    else if (action === "cancel") cancel();
    else if (action === "confirm-delete") remove(it);
    else if (action === "retire") retire(it);
    else setMode(action);
  });
  $("field").addEventListener("submit", (e) => {
    e.preventDefault();
    submit(e.target);
  });
  $("add").addEventListener("click", startNew);
  $("toggle-retired").addEventListener("click", toggleRetired);
  $("filter").addEventListener("input", (e) => {
    filter = e.target.value;
    mode = null;
    renderTitleblock();
    sheet.render();
  });
  $("page-prev").addEventListener("click", () => sheet.setPage(sheet.page - 1));
  $("page-next").addEventListener("click", () => sheet.setPage(sheet.page + 1));

  function applyState(state) {
    reset(state);
    sheet.selectedId = null;
    const oilKing = "it1";
    if (["selected", "editing", "conflict", "delete"].includes(state)) sheet.selectedId = oilKing;
    if (state === "editing") mode = "edit";
    if (state === "conflict") {
      mode = "edit";
      const it = byId(oilKing);
      draft = { name: it.name, cat: it.cat, slot: "7", desc: it.desc };
      const free = freeSlots(oilKing);
      error = {
        field: "slot",
        html: `<strong>Slot 7 is taken</strong> by Cherry MX Black Clear-Top (Hyperglide). Free slots: <span class="num">${free.join(", ")}</span>.`,
      };
    }
    if (state === "delete") mode = "delete";
    if (state === "retired") sheet.selectedId = "it14";
    render({ focus: state !== "normal" });
    if (state === "sheet2") sheet.setPage(1);
  }

  document.querySelectorAll('input[name="state"]').forEach((input) =>
    input.addEventListener("change", () => applyState(input.value))
  );
  document.querySelectorAll('input[name="theme"]').forEach((input) =>
    input.addEventListener("change", () => {
      if (input.value === "auto") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", input.value);
    })
  );

  // ?state=editing&theme=dark opens the mockup in a given state (used for review captures).
  const params = new URLSearchParams(location.search);
  const startTheme = params.get("theme");
  if (startTheme) document.querySelector(`input[name="theme"][value="${startTheme}"]`)?.click();
  const startState = params.get("state") || "normal";
  const picker = document.querySelector(`input[name="state"][value="${startState}"]`);
  if (picker) picker.checked = true;
  applyState(picker ? startState : "normal");
})();
