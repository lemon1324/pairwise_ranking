// Rankings mockup: ranked parts list with rating and ± SE, category filter, retired toggle,
// CSV export, and a floating detail callout (figures plus weighted record) for the selected row.
// Mockup only; the real app renders rows server-side.

(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  let items;
  let showRetired;
  let category;
  let detailOpen;
  let noVotes;
  let note;

  const byId = (id) => items.find((it) => it.id === id);

  function reset(state) {
    items = window.SAMPLE.items.map((it) => ({ ...it }));
    showRetired = state === "retired";
    category = state === "filtered" ? "Tactile" : "";
    detailOpen = false;
    noVotes = state === "novotes";
    note = "";
    if (state === "toofew") items = items.slice(0, 1);
    if (noVotes) {
      items.forEach((it) => {
        it.rating = 1500;
        it.comparisons = 0;
        it.record = [];
      });
    }
  }

  // Ranks number the active items 1..N by rating across all categories; retired items have none.
  function ranked() {
    const act = items.filter((it) => it.status === "active");
    if (noVotes) return new Map();
    const order = [...act].sort((a, b) => b.rating - a.rating);
    return new Map(order.map((it, i) => [it.id, i + 1]));
  }

  function rows() {
    const act = items.filter((it) => it.status === "active");
    if (act.length < 2) return [];
    const ranks = ranked();
    return items
      .filter((it) => showRetired || it.status === "active")
      .filter((it) => !category || it.cat === category)
      .map((it) => ({ ...it, rank: ranks.get(it.id) }))
      .sort((a, b) => (noVotes ? a.name.localeCompare(b.name) : b.rating - a.rating));
  }

  const head = `
    <thead><tr>
      <th class="c-find" style="width:3.5rem">Rank</th>
      <th>Name</th>
      <th class="c-cat" style="width:6.5rem">Category</th>
      <th class="n" style="width:4.75rem">Rating</th>
      <th class="n" style="width:4.25rem">± SE</th>
      <th class="n c-phone-hide" style="width:5.5rem">Compared</th>
    </tr></thead>`;

  function rowHtml(it) {
    const cls = ["bom-row"];
    if (it.status === "retired") cls.push("is-retired");
    const rank = it.rank ? `<span class="bom-rank">${it.rank}</span>` : `<span class="bom-rank" aria-label="no rank">–</span>`;
    const tag = it.status === "retired" ? ` <span class="tag">Retired</span>` : "";
    return `<tr class="${cls.join(" ")}" data-id="${it.id}" tabindex="-1" aria-selected="false">
      <td class="c-find">${rank}</td>
      <td><span class="bom-name">${esc(it.name)}${tag}</span></td>
      <td class="c-cat"><span class="bom-cat">${esc(it.cat)}</span></td>
      <td class="n">${noVotes ? "–" : it.rating}</td>
      <td class="n">${noVotes ? "–" : `±${it.se}`}</td>
      <td class="n c-phone-hide">${it.comparisons}</td>
    </tr>`;
  }

  function stripHtml(it) {
    if (!detailOpen) return "";
    const figures = noVotes
      ? `<dt class="label">Votes</dt><dd>none yet</dd>`
      : `<dt class="label">Rating</dt><dd>${it.rating} ±${it.se}</dd>
         <dt class="label">Strength</dt><dd>${it.strength.toFixed(3)}</dd>
         <dt class="label">Log-strength</dt><dd>${it.logStrength.toFixed(3)}</dd>
         <dt class="label">SE (log)</dt><dd>${it.seLog.toFixed(3)}</dd>
         <dt class="label">Compared</dt><dd>${it.comparisons} times</dd>`;
    const top = it.record.slice(0, 7);
    const more = it.record.length - top.length;
    const record = it.record.length
      ? `<table class="record">
          <caption class="label">Weighted record</caption>
          <thead><tr><th>Opponent</th><th class="n">Won</th><th class="n">Lost</th></tr></thead>
          <tbody>${top
            .map((r) => `<tr><td>${esc(byId(r.id)?.name ?? "Deleted item")}</td><td class="n">${r.won}</td><td class="n">${r.lost}</td></tr>`)
            .join("")}</tbody>
        </table>${more > 0 ? `<p class="record more">and ${more} more ${more === 1 ? "opponent" : "opponents"}</p>` : ""}`
      : `<p class="field-hint">No votes involve this item yet.</p>`;
    return `<div class="strip-body">
      <p class="strip-title">${it.rank ? `#${it.rank} ` : ""}${esc(it.name)}</p>
      <div class="strip-detail">
        <dl>
          ${figures}
          ${it.desc ? `<p class="detail-desc">${esc(it.desc)}</p>` : ""}
        </dl>
        <div>${record}</div>
      </div>
    </div>`;
  }

  function emptyHtml() {
    const act = items.filter((it) => it.status === "active");
    if (act.length < 2) {
      return `<div class="bom-empty">
        <p class="lead">Rankings need at least 2 items.</p>
        <p class="detail">This project has ${act.length} active item${act.length === 1 ? "" : "s"}.</p>
        <a class="cell-button" href="items.html">Open Items <svg class="icon" aria-hidden="true"><use href="#i-arrow"/></svg></a>
      </div>`;
    }
    return `<div class="bom-empty">
      <p class="lead">No ${esc(category)} items${showRetired ? "" : " are active"}.</p>
      <p class="detail">Choose another category or All categories.</p>
    </div>`;
  }

  const sheet = window.BomSheet({
    field: $("field"),
    titleblock: $("titleblock"),
    caption: "Rankings",
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
    // A click opens the clicked row's detail. Clicking the selected row again is the same as
    // Esc: close the detail and deselect in one step.
    onRowClick: (id, wasSelected) => {
      if (wasSelected) {
        detailOpen = false;
        sheet.clear();
      } else {
        detailOpen = true;
        sheet.select(id);
      }
      return true;
    },
    onKey: handleKey,
  });

  function renderTitleblock() {
    const cats = [...new Set(items.map((it) => it.cat))].sort();
    $("category").innerHTML =
      `<option value="">All categories</option>` +
      cats.map((c) => `<option value="${esc(c)}"${c === category ? " selected" : ""}>${esc(c)}</option>`).join("");
    const shown = rows();
    const activeShown = shown.filter((it) => it.status === "active").length;
    const retiredAll = items.filter((it) => it.status === "retired" && (!category || it.cat === category)).length;
    let text = `<span class="num">${activeShown}</span> active shown · <span class="num">${retiredAll}</span> retired ${showRetired ? "shown" : "hidden"}.`;
    if (noVotes) text += " No votes yet, so the order is arbitrary.";
    else text += " Ratings are relative to the items in this project.";
    if (note) text = `${note} ${text}`;
    $("tb-summary").innerHTML = text;
    $("toggle-retired").setAttribute("aria-pressed", String(showRetired));
    $("retired-text").textContent = showRetired ? "Shown" : "Hidden";
    $("retired-icon").setAttribute("href", showRetired ? "#i-eye" : "#i-eye-off");
  }

  function render() {
    renderTitleblock();
    sheet.render();
  }

  function toggleDetail() {
    if (sheet.selectedId == null) return;
    detailOpen = !detailOpen;
    sheet.refreshCallout();
  }

  function exportCsv() {
    const shown = rows();
    const header = ["Rank", "Name", "Category", "Identifier", "Status", "ELO Rating", "Uncertainty (SE)", "Comparisons", "Description"];
    const quote = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = [header, ...shown.map((it) => [it.rank ?? "", it.name, it.cat, it.slot, it.status, it.rating, it.se, it.comparisons, it.desc])];
    const blob = new Blob([lines.map((l) => l.map(quote).join(",")).join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "rankings.csv";
    a.click();
    URL.revokeObjectURL(a.href);
    note = `Exported rankings.csv (${shown.length} rows).`;
    renderTitleblock();
  }

  function handleKey(e, inControl) {
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    if (!inControl && e.target.closest("button, a") && (e.key === "Enter" || e.key === " ")) return false;
    if (e.key === "Escape") {
      if (inControl) e.target.blur();
      else if (sheet.selectedId != null) {
        detailOpen = false;
        sheet.clear();
      }
      return true;
    }
    if (inControl) return false;
    switch (e.key) {
      case "Enter":
        toggleDetail();
        return true;
      case "h":
      case "H":
        showRetired = !showRetired;
        render();
        return true;
      case "x":
      case "X":
        exportCsv();
        return true;
      case "c":
      case "C":
        $("category").focus();
        return true;
      default:
        return false;
    }
  }

  $("toggle-retired").addEventListener("click", () => {
    showRetired = !showRetired;
    render();
  });
  $("export").addEventListener("click", exportCsv);
  $("category").addEventListener("change", (e) => {
    category = e.target.value;
    detailOpen = false;
    sheet.selectedId = null;
    render();
  });
  $("page-prev").addEventListener("click", () => sheet.setPage(sheet.page - 1));
  $("page-next").addEventListener("click", () => sheet.setPage(sheet.page + 1));

  function applyState(state) {
    reset(state);
    sheet.selectedId = null;
    if (state === "expanded") {
      sheet.selectedId = "it1";
      detailOpen = true;
    }
    render();
    if (state === "expanded") sheet.focusSelected();
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

  // ?state=expanded&theme=dark opens the mockup in a given state (used for review captures).
  const params = new URLSearchParams(location.search);
  const startTheme = params.get("theme");
  if (startTheme) document.querySelector(`input[name="theme"][value="${startTheme}"]`)?.click();
  const startState = params.get("state") || "normal";
  const picker = document.querySelector(`input[name="state"][value="${startState}"]`);
  if (picker) picker.checked = true;
  applyState(picker ? startState : "normal");
})();
