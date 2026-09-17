// Project picker mockup: the drawing register of every .pairrank file in the data directory, with
// open, duplicate-without-votes and download in the row popover, new project and import forms,
// and file conditions (old format, newer format, unreadable) shown as tags plus words.
// Mockup only; the real app lists the bind-mounted data directory server-side.

(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const svg = (id) => `<svg class="icon" aria-hidden="true"><use href="#${id}"/></svg>`;

  // Sample files; figures invented. kind: ok | v1 | newer | unreadable.
  const FILES = [
    { id: "p1", name: "Linear switches, winter shortlist", file: "switches-2026.pairrank", items: 64, votes: 203, modified: "2026-09-16 21:04", kind: "ok" },
    { id: "p2", name: "Espresso, September roasts", file: "espresso-sept.pairrank", items: 12, votes: 88, modified: "2026-09-14 08:12", kind: "ok" },
    { id: "p3", name: "Keyboard cases", file: "cases.pairrank", items: null, votes: null, modified: "2026-09-10 17:45", kind: "newer", format: 3 },
    { id: "p4", name: "Tactile shortlist", file: "tactile.pairrank", items: 22, votes: 131, modified: "2026-09-02 19:40", kind: "ok" },
    { id: "p5", name: "Pour-over grinders", file: "grinders.pairrank", items: 7, votes: 21, modified: "2026-08-19 10:02", kind: "ok" },
    { id: "p6", name: null, file: "notes.pairrank", items: null, votes: null, modified: "2026-06-30 12:15", kind: "unreadable", reason: "not valid JSON (line 12)" },
    { id: "p7", name: "Migrated Project", file: "project.pairrank", items: 18, votes: 240, modified: "2026-01-04 10:15", kind: "v1" },
    { id: "p8", name: "Whisky flight, November", file: "whisky-flight.pairrank", items: 9, votes: 36, modified: "2025-11-23 22:31", kind: "ok" },
  ];

  let files;
  let mode; // null | "new" | "import" | "duplicate"
  let draft;
  let error;
  let importState; // null | "parsed" | "error"
  let note;

  // Mirrors safe_project_filename: keep letters, digits, spaces, _ and -; anything else becomes _.
  const safeName = (name) => [...name].map((c) => (/[\p{L}\p{N} _-]/u.test(c) ? c : "_")).join("");
  const fileFor = (name) => `${safeName(name.trim())}.pairrank`;
  const taken = (file) => files.some((f) => f.file.toLowerCase() === file.toLowerCase());

  function reset(state) {
    files = FILES.map((f) => ({ ...f }));
    mode = null;
    draft = null;
    error = null;
    importState = null;
    note = "";
    if (state === "empty") files = [];
  }

  function rows() {
    const list = files.map((f, i) => ({ ...f, no: i + 1 }));
    if (mode === "new" || mode === "import") list.unshift({ id: "__form", kind: "form" });
    return list;
  }

  const head = `
    <thead><tr>
      <th class="c-find" style="width:3rem">No.</th>
      <th>Project</th>
      <th class="n c-phone-hide" style="width:4.5rem">Items</th>
      <th class="n" style="width:4.5rem">Votes</th>
      <th class="c-cat" style="width:10rem">Modified</th>
    </tr></thead>`;

  const TAGS = { v1: "Old format", newer: "Newer format", unreadable: "Unreadable" };

  function rowHtml(f) {
    if (f.kind === "form") {
      return `<tr class="bom-row is-new" data-id="__form" tabindex="-1" aria-selected="false">
        <td class="c-find"><span class="bom-rank">–</span></td>
        <td><span class="bom-name">${mode === "new" ? "New project" : "Imported file"}</span></td>
        <td class="n c-phone-hide"></td><td class="n"></td><td class="c-cat"></td>
      </tr>`;
    }
    const cls = ["bom-row"];
    if (f.kind === "newer" || f.kind === "unreadable") cls.push("is-retired");
    const tag = TAGS[f.kind] ? ` <span class="tag">${TAGS[f.kind]}</span>` : "";
    return `<tr class="${cls.join(" ")}" data-id="${f.id}" tabindex="-1" aria-selected="false">
      <td class="c-find"><span class="bom-rank">${f.no}</span></td>
      <td><span class="bom-name">${esc(f.name ?? f.file)}${tag}</span><span class="bom-desc num">${esc(f.file)}</span></td>
      <td class="n c-phone-hide">${f.items ?? "–"}</td>
      <td class="n">${f.votes ?? "–"}</td>
      <td class="c-cat"><span class="bom-cat num">${esc(f.modified)}</span></td>
    </tr>`;
  }

  const act = (action, text, key) =>
    `<button class="strip-action" type="button" data-action="${action}">${text}${key ? `<span class="key">${key}</span>` : ""}</button>`;

  function stripHtml(f) {
    if (f.kind === "form") return mode === "new" ? newFormHtml() : importHtml();
    if (mode === "duplicate") return duplicateHtml(f);
    if (f.kind === "newer") {
      return `<div class="strip-confirm">${svg("i-warn")}<div>
        <p><strong>Made by a newer version (format ${f.format}).</strong> This version reads format 2 and older, so it won’t open this file. Update the app, or open it in the app that wrote it.</p>
        <div class="strip-buttons"><a class="cell-button" href="#download">Download</a></div>
      </div></div>`;
    }
    if (f.kind === "unreadable") {
      return `<div class="strip-confirm">${svg("i-warn")}<div>
        <p><strong>Can’t read ${esc(f.file)}:</strong> ${esc(f.reason)}. The file is left untouched.</p>
        <div class="strip-buttons"><a class="cell-button" href="#download">Download</a></div>
      </div></div>`;
    }
    const upgrade =
      f.kind === "v1"
        ? `<p class="strip-body field-hint" style="margin:0;padding-bottom:0">Written by an older version (format 1). Opening upgrades it once and keeps the original as <span class="num">${esc(f.file)}.v1.bak</span>.</p>`
        : "";
    return `${upgrade}<div class="strip-actions">${act("open", "Open", "↵")}${act("duplicate", "Duplicate", "D")}${act("download", "Download", "")}</div>`;
  }

  function nameField(label, value, hintFile) {
    const bad = error && error.field === "name";
    return `<div class="field field-wide${bad ? " is-error" : ""}">
      <label class="label" for="f-name">${label}</label>
      <input class="input" id="f-name" name="name" value="${esc(value)}" autocomplete="off"${bad ? ' aria-invalid="true" aria-describedby="err-name"' : ""}>
      ${bad ? `<p class="field-error" id="err-name">${svg("i-warn")}<span>${error.html}</span></p>` : `<span class="field-hint" id="f-file">Saves as <span class="num">/data/${esc(hintFile)}</span></span>`}
    </div>`;
  }

  const buttons = (primary) => `<div class="strip-buttons">
      <button class="cell-button is-primary" type="submit">${primary} <span class="key">↵</span></button>
      <button class="cell-button" type="button" data-action="cancel">Cancel <span class="key">Esc</span></button>
    </div>`;

  function newFormHtml() {
    const name = draft?.name ?? "";
    return `<div class="strip-body">
      <p class="strip-title">New project</p>
      <form class="strip-form" data-form="new" novalidate>
        ${nameField("Name", name, name.trim() ? fileFor(name) : "….pairrank")}
        ${buttons("Create")}
      </form>
    </div>`;
  }

  function duplicateHtml(f) {
    const name = draft?.name ?? `${f.name} copy`;
    return `<div class="strip-body">
      <p class="strip-title">Duplicate ${esc(f.name)} without votes</p>
      <form class="strip-form" data-form="duplicate" novalidate>
        ${nameField("New name", name, fileFor(name))}
        <p class="field-hint field-wide">Copies the ${f.items} items, categories, slots and settings. No votes are copied.</p>
        ${buttons("Duplicate")}
      </form>
    </div>`;
  }

  function importHtml() {
    let detail = `<p class="field-hint">Choose a .pairrank file from the desktop app, or drop it here.</p>`;
    if (importState === "parsed") {
      detail = `<p class="tb-text" style="margin:0"><strong>Coffee flight</strong> · <span class="num">coffee-flight.pairrank</span> · <span class="num">14</span> items · <span class="num">96</span> votes · format 2</p>
        <p class="field-hint" style="margin:0">Saves as <span class="num">/data/coffee-flight.pairrank</span>.</p>`;
    } else if (importState === "error") {
      detail = `<p class="field-error">${svg("i-warn")}<span><strong>grinders.csv isn’t a project file.</strong> Import takes .pairrank files. Old CSV data is migrated by the desktop app.</span></p>`;
    }
    return `<div class="strip-body">
      <p class="strip-title">Import a project file</p>
      <form class="strip-form" data-form="import" novalidate>
        <label class="field field-wide bom-empty" style="max-width:none;padding:var(--s-4);cursor:pointer">
          <span class="lead" style="font-size:1rem">${importState === "parsed" ? "coffee-flight.pairrank" : "Drop a .pairrank file"}</span>
          <span class="cell-button">Choose file</span>
          <input class="visually-hidden" type="file" accept=".pairrank">
        </label>
        <div class="field field-wide">${detail}</div>
        ${importState === "parsed" ? buttons("Import") : `<div class="strip-buttons"><button class="cell-button" type="button" data-action="cancel">Cancel <span class="key">Esc</span></button></div>`}
      </form>
    </div>`;
  }

  function emptyHtml() {
    return `<div class="bom-empty">
      <p class="lead">No projects in /data yet.</p>
      <p class="detail">Start a new project, import a .pairrank file, or copy projects from the desktop app into the appdata share.</p>
      <div class="strip-buttons" style="justify-content:center">
        <button class="cell-button" type="button" data-action="new">New project <span class="key">N</span></button>
        <button class="cell-button" type="button" data-action="import">Import <span class="key">I</span></button>
      </div>
    </div>`;
  }

  const sheet = window.BomSheet({
    field: $("field"),
    titleblock: $("titleblock"),
    caption: "Projects",
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
      if (id !== "__form") {
        if (mode === "new" || mode === "import") mode = null;
        if (mode === "duplicate") mode = null;
        draft = null;
        error = null;
      }
    },
    onRowClick: (id, wasSelected) => {
      if (!wasSelected) return false;
      cancel();
      return true;
    },
    onKey: handleKey,
  });

  function renderTitleblock() {
    const problems = files.filter((f) => f.kind === "newer" || f.kind === "unreadable").length;
    $("tb-counts").innerHTML =
      `<span class="num">${files.length}</span> files` + (problems ? ` · <span class="num">${problems}</span> can’t be opened` : "");
    if (note) $("tb-note").textContent = note;
  }

  function render() {
    renderTitleblock();
    sheet.render();
    const input = $("field").querySelector(".bom-callout .input");
    if (input) {
      input.focus({ preventScroll: true });
      if (!error) input.select();
    }
  }

  function start(next) {
    mode = next;
    draft = null;
    error = null;
    importState = null;
    sheet.selectedId = "__form";
    render();
  }

  function cancel() {
    const wasForm = sheet.selectedId === "__form";
    mode = null;
    draft = null;
    error = null;
    importState = null;
    if (wasForm) sheet.selectedId = null;
    if (!wasForm && sheet.selectedId) sheet.clear();
    else render();
  }

  function selected() {
    return files.find((f) => f.id === sheet.selectedId);
  }

  function submit(form) {
    const name = (new FormData(form).get("name") ?? "").toString().trim();
    if (form.dataset.form === "import") {
      files.unshift({ id: "p9", name: "Coffee flight", file: "coffee-flight.pairrank", items: 14, votes: 96, modified: "2026-09-16 21:10", kind: "ok" });
      note = "Imported coffee-flight.pairrank.";
      mode = null;
      sheet.selectedId = "p9";
      render();
      return;
    }
    if (!name) {
      draft = { name };
      error = { field: "name", html: "<strong>Enter a name.</strong>" };
      render();
      return;
    }
    const file = fileFor(name);
    if (taken(file)) {
      draft = { name };
      error = { field: "name", html: `<strong>/data/${esc(file)} already exists.</strong> Choose another name.` };
      render();
      return;
    }
    const source = selected();
    const created = {
      id: `p${Date.now()}`,
      name,
      file,
      items: form.dataset.form === "duplicate" ? source.items : 0,
      votes: 0,
      modified: "2026-09-16 21:10",
      kind: "ok",
    };
    files.unshift(created);
    note = form.dataset.form === "duplicate" ? `Duplicated ${source.name} as ${file}, without votes.` : `Created ${file}.`;
    mode = null;
    draft = null;
    error = null;
    sheet.selectedId = created.id;
    render();
  }

  function handleKey(e, inControl) {
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    if (!inControl && e.target.closest("button, a") && (e.key === "Enter" || e.key === " ")) return false;
    if (e.key === "Escape") {
      if (mode || sheet.selectedId) cancel();
      return true;
    }
    if (inControl || mode) return false;
    const f = selected();
    switch (e.key) {
      case "Enter":
        if (f && (f.kind === "ok" || f.kind === "v1")) location.href = "compare.html";
        return !!f;
      case "n":
      case "N":
        start("new");
        return true;
      case "i":
      case "I":
        start("import");
        return true;
      case "d":
      case "D":
        if (f && (f.kind === "ok" || f.kind === "v1")) {
          mode = "duplicate";
          render();
        }
        return !!f;
      default:
        return false;
    }
  }

  $("field").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    if (action === "open") location.href = "compare.html";
    else if (action === "duplicate") {
      mode = "duplicate";
      render();
    } else if (action === "download") {
      note = `Downloading ${selected()?.file}.`;
      renderTitleblock();
    } else if (action === "cancel") cancel();
    else if (action === "new" || action === "import") start(action);
  });
  $("field").addEventListener("submit", (e) => {
    e.preventDefault();
    submit(e.target);
  });
  $("field").addEventListener("input", (e) => {
    if (e.target.id !== "f-name") return;
    const hint = $("f-file");
    if (hint) hint.innerHTML = `Saves as <span class="num">/data/${esc(e.target.value.trim() ? fileFor(e.target.value) : "….pairrank")}</span>`;
  });
  $("field").addEventListener("change", (e) => {
    if (e.target.type === "file") {
      importState = "parsed";
      render();
    }
  });
  $("new").addEventListener("click", () => start("new"));
  $("import").addEventListener("click", () => start("import"));
  $("page-prev").addEventListener("click", () => sheet.setPage(sheet.page - 1));
  $("page-next").addEventListener("click", () => sheet.setPage(sheet.page + 1));

  function applyState(state) {
    reset(state);
    sheet.selectedId = null;
    if (state === "selected") sheet.selectedId = "p1";
    if (state === "v1") sheet.selectedId = "p7";
    if (state === "newer") sheet.selectedId = "p3";
    if (state === "unreadable") sheet.selectedId = "p6";
    if (state === "new" || state === "newconflict") {
      mode = "new";
      sheet.selectedId = "__form";
    }
    if (state === "newconflict") {
      draft = { name: "Tactile shortlist" };
      error = { field: "name", html: "<strong>/data/Tactile shortlist.pairrank already exists.</strong> Choose another name." };
      files.push({ id: "p10", name: "Tactile shortlist", file: "Tactile shortlist.pairrank", items: 22, votes: 0, modified: "2026-09-16 21:08", kind: "ok" });
    }
    if (state === "import" || state === "importerror") {
      mode = "import";
      sheet.selectedId = "__form";
      importState = state === "import" ? "parsed" : "error";
    }
    render();
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

  // ?state=new&theme=dark opens the mockup in a given state (used for review captures).
  const params = new URLSearchParams(location.search);
  const startTheme = params.get("theme");
  if (startTheme) document.querySelector(`input[name="theme"][value="${startTheme}"]`)?.click();
  const startState = params.get("state") || "normal";
  const picker = document.querySelector(`input[name="state"][value="${startState}"]`);
  if (picker) picker.checked = true;
  applyState(picker ? startState : "normal");
})();
