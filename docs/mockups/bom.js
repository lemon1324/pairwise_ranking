// Parts-list sheet engine for the Items and Rankings mockups.
//
// Folds table rows into as many columns as fit (each at least MIN_COL_REM wide) and, once a sheet
// is full, onto continuation sheets. The last column stops above the title block. The selected
// row's callout (actions, a form, or detail) floats over the table, anchored to the row, so
// selecting never refolds anything. Also owns the shared keys: arrows or J/K, Home/End,
// PgUp/PgDn; pages add their own through onKey. On phones the sheet is one long table.

(() => {
  const PHONE = matchMedia("(max-width: 40rem)");
  const MIN_COL_REM = 36;
  const CLEARANCE_REM = 0.75; // space between the last column and the title block below it

  window.BomSheet = function BomSheet(o) {
    let selectedId = null;
    let page = 0;
    let pages = 1;
    let limits = { bottom: Infinity, lastColBottom: Infinity };
    let lastCalloutKey = "";
    const rowPage = new Map();

    const rem = () => parseFloat(getComputedStyle(document.documentElement).fontSize);

    function tableShell() {
      const table = document.createElement("table");
      table.className = "bom";
      table.innerHTML = `${o.head}<tbody></tbody>`;
      return table;
    }

    function rowEl(row) {
      const tpl = document.createElement("template");
      tpl.innerHTML = o.rowHtml(row, false);
      return tpl.content.firstElementChild;
    }

    // ---------- Folding ----------

    function render() {
      document.documentElement.classList.toggle("bom-fixed", !PHONE.matches);
      const field = o.field;
      const rows = o.rows();
      field.innerHTML = "";
      rowPage.clear();

      if (!rows.length) {
        field.innerHTML = o.emptyHtml();
        pages = 1;
        page = 0;
        o.onPage(page, pages);
        return;
      }

      if (PHONE.matches) {
        o.titleblock.style.width = "";
        const col = document.createElement("div");
        col.className = "bom-col";
        const table = tableShell();
        col.append(table);
        field.append(col);
        for (const row of rows) {
          table.tBodies[0].append(rowEl(row));
          rowPage.set(row.id, 0);
        }
        pages = 1;
        page = 0;
        limits = { bottom: Infinity, lastColBottom: Infinity };
        finish();
        return;
      }

      const width = field.clientWidth;
      const height = field.clientHeight;
      // The rightmost column matches the standard title block width (--tb-width) so the title
      // block sits exactly under it; the other columns share the rest, each >= MIN_COL_REM.
      const tbStandard = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--tb-width")) * rem();
      const minCol = MIN_COL_REM * rem();
      const tbWidth = Math.min(tbStandard, width);
      const others = Math.floor((width - tbWidth) / minCol);
      const n = others + 1;
      const otherWidth = others ? (width - tbWidth) / others : 0;
      const colWidthFor = (i) => (i === n - 1 ? tbWidth : otherWidth);

      o.titleblock.style.width = `${tbWidth}px`;
      const tbTop = o.titleblock.getBoundingClientRect().top - field.getBoundingClientRect().top;
      const lastCol = n - 1;
      const lastColBottom = tbTop - CLEARANCE_REM * rem();
      limits = { bottom: height, lastColBottom };

      const pageEls = [];
      let pageEl;
      let colIndex;
      let col;
      let body;

      const newCol = () => {
        colIndex += 1;
        col = document.createElement("div");
        col.className = "bom-col";
        col.style.width = `${colWidthFor(colIndex)}px`;
        col.dataset.limit = String(colIndex === lastCol ? lastColBottom : height);
        const table = tableShell();
        col.append(table);
        pageEl.append(col);
        body = table.tBodies[0];
      };
      const newPage = () => {
        pageEl = document.createElement("div");
        pageEl.className = "bom-page";
        field.append(pageEl);
        pageEls.push(pageEl);
        colIndex = -1;
        newCol();
      };

      newPage();
      for (const row of rows) {
        const tr = rowEl(row);
        body.append(tr);
        if (col.offsetHeight > Number(col.dataset.limit) && body.children.length > 1) {
          tr.remove();
          if (colIndex < lastCol) newCol();
          else newPage();
          body.append(tr);
        }
        rowPage.set(row.id, pageEls.length - 1);
      }

      pageEls.forEach((el, i) => {
        const cols = el.querySelectorAll(".bom-col");
        if (cols.length === n) cols[cols.length - 1].classList.add("is-edge");
        cols.forEach((c, j) => {
          c.classList.toggle("is-last", j === lastCol);
          const cap = c.querySelector(".bom").createCaption();
          cap.className = "visually-hidden";
          cap.textContent = `${o.caption}, sheet ${i + 1}, column ${j + 1}`;
        });
      });
      pages = pageEls.length;
      finish();
    }

    // ---------- Selection and the floating callout ----------

    function finish() {
      if (selectedId != null && rowPage.has(selectedId)) page = rowPage.get(selectedId);
      page = Math.max(0, Math.min(page, pages - 1));
      o.field.querySelectorAll(".bom-page").forEach((el, i) => (el.hidden = i !== page));
      o.field.querySelectorAll("tr[data-id]").forEach((tr) => {
        const on = tr.dataset.id === String(selectedId);
        tr.classList.toggle("is-selected", on);
        tr.setAttribute("aria-selected", String(on));
      });
      placeCallout();
      o.onPage(page, pages);
    }

    function findRow(id) {
      return o.field.querySelector(`tr[data-id="${CSS.escape(String(id))}"]`);
    }

    function placeCallout() {
      o.field.querySelector(".bom-callout")?.remove();
      const tr = selectedId != null ? findRow(selectedId) : null;
      const row = tr && o.rows().find((r) => String(r.id) === tr.dataset.id);
      const html = row ? o.stripHtml(row) : "";
      if (!html) return;

      const callout = document.createElement("div");
      callout.className = "bom-callout strip";
      // Only animate a callout that is new; a refold redrawing the same one keeps it still.
      const key = `${selectedId}\n${html}`;
      if (key === lastCalloutKey) callout.classList.add("is-settled");
      lastCalloutKey = key;
      callout.innerHTML = html;
      o.field.append(callout);

      // A popover beside the find-number column: it leaves every row's number visible and
      // clickable, sits a short offset off the selected row, and is as tall as its content.
      // An elbow leader runs from a dot on the selected row's number into its side.
      const fieldBox = o.field.getBoundingClientRect();
      const rowBox = tr.getBoundingClientRect();
      const colEl = tr.closest(".bom-col");
      const colBox = colEl.getBoundingClientRect();
      const findBox = tr.cells[0].getBoundingClientRect();
      const gap = 0.5 * rem();
      const edge = 0.375 * rem();
      const left = findBox.right - fieldBox.left + edge;
      callout.style.left = `${left}px`;
      callout.style.width = `${colBox.right - fieldBox.left - edge - left}px`;
      // The leader runs in the space between the number and the column rule, never through a number.
      const leaderX = findBox.right - fieldBox.left - 0.375 * rem();
      callout.style.setProperty("--leader-dx", `${left - leaderX}px`);
      callout.style.setProperty("--gap", `${gap}px`);

      const rowTop = rowBox.top - fieldBox.top;
      const rowBottom = rowBox.bottom - fieldBox.top;
      const bottomLimit = colEl.classList.contains("is-last") ? limits.lastColBottom : limits.bottom;
      const h = callout.offsetHeight;
      if (rowBottom + gap + h > bottomLimit && rowTop - gap - h >= 0) {
        callout.classList.add("is-above");
        callout.style.top = `${rowTop - gap - h}px`;
      } else {
        callout.style.top = `${rowBottom + gap}px`;
      }
      // Phones scroll the long sheet; keep the callout clear of the bottom tab bar.
      if (PHONE.matches) callout.scrollIntoView({ block: "nearest" });
    }

    function focusSelected() {
      const el = findRow(selectedId);
      if (!el) return;
      el.focus({ preventScroll: true });
      if (PHONE.matches) el.scrollIntoView({ block: "nearest" });
    }

    function select(id, { focus = true } = {}) {
      selectedId = id;
      if (o.onSelect) o.onSelect(id);
      if (id != null && rowPage.has(id)) finish();
      else render();
      if (focus) focusSelected();
    }

    function move(delta) {
      const rows = o.rows();
      if (!rows.length) return;
      let i = rows.findIndex((r) => r.id === selectedId);
      if (i < 0) i = delta > 0 ? 0 : rows.length - 1;
      else i = Math.max(0, Math.min(rows.length - 1, i + delta));
      select(rows[i].id);
    }

    function setPage(next) {
      const target = Math.max(0, Math.min(pages - 1, next));
      if (target === page) return;
      const first = [...rowPage].find(([, p]) => p === target);
      if (first) select(first[0]);
    }

    function clear() {
      selectedId = null;
      if (o.onSelect) o.onSelect(null);
      finish();
    }

    // Clicking a row selects it; clicking the selected row again acts like Esc. Pages can take
    // over either case through onRowClick(id, wasSelected), returning true when handled.
    o.field.addEventListener("click", (e) => {
      if (e.target.closest(".bom-callout")) return;
      const tr = e.target.closest("tr[data-id]");
      if (!tr) return;
      const row = o.rows().find((r) => String(r.id) === tr.dataset.id);
      if (!row) return;
      const wasSelected = row.id === selectedId;
      if (o.onRowClick && o.onRowClick(row.id, wasSelected)) return;
      if (wasSelected) clear();
      else select(row.id);
    });

    document.addEventListener("keydown", (e) => {
      const inControl = !!e.target.closest("input, textarea, select");
      if (o.onKey && o.onKey(e, inControl)) {
        e.preventDefault();
        return;
      }
      if (inControl || e.ctrlKey || e.metaKey || e.altKey) return;
      const rows = o.rows();
      switch (e.key) {
        case "ArrowDown":
        case "j":
          move(1);
          break;
        case "ArrowUp":
        case "k":
          move(-1);
          break;
        case "Home":
          if (rows.length) select(rows[0].id);
          break;
        case "End":
          if (rows.length) select(rows[rows.length - 1].id);
          break;
        case "PageDown":
          setPage(page + 1);
          break;
        case "PageUp":
          setPage(page - 1);
          break;
        default:
          return;
      }
      e.preventDefault();
    });

    // Fold again whenever the drawing area changes size (window resize, scrollbar, zoom) and
    // whenever web fonts finish loading, since both change how many rows fit. Folding never
    // changes the drawing area's own size, so this cannot loop.
    let refoldTimer;
    const refold = () => {
      clearTimeout(refoldTimer);
      refoldTimer = setTimeout(render, 60);
    };
    new ResizeObserver(refold).observe(o.field.parentElement);
    document.fonts?.addEventListener("loadingdone", refold);
    PHONE.addEventListener("change", render);

    return {
      isPhone: () => PHONE.matches,
      render,
      refreshCallout: placeCallout,
      select,
      clear,
      move,
      setPage,
      focusSelected,
      get selectedId() {
        return selectedId;
      },
      set selectedId(id) {
        selectedId = id;
      },
      get page() {
        return page;
      },
      get pages() {
        return pages;
      },
    };
  };
})();
