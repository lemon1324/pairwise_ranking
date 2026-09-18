// The parts-list sheet engine: folding, selection, the row callout and the shared keys.
//
// Ported from docs/mockups/bom.js, with one change that runs through everything: the mockup held
// the rows in JavaScript and drew them from sample data, and this reads them out of the page. The
// server renders one long table, which is the whole sheet on phones and with JavaScript off. Here
// that table is the source of truth: its <tr> elements are moved - never re-created - into as many
// columns as fit at MIN_COL_REM each and, once a sheet is full, onto continuation sheets. Moving
// the server's own rows is what keeps their hx- attributes, their ids and their event handlers
// alive across a fold.
//
// Nothing on the sheet needs this file to be correct. Without it the page is the long table with
// the title block after it, every row readable and every link and form still working; the engine
// only decides where the rows are drawn and which one is selected.
//
// What a screen has to do, and all it has to do:
//
//   - Draw its rows with the parts_list / parts_row macros, inside .bom-field.
//   - Put hx-get + hx-target="#row-callout" + hx-trigger="sheet:select" on a row that has a
//     callout. The engine clears the host before the event, so a stale callout never shows.
//   - Mark its own verbs with data-sheet-key on the button that performs them, e.g.
//     data-sheet-key="R" on Retire, data-sheet-key="Escape" on a form's Cancel. The engine
//     presses the button; the screen never writes a key handler. Anything stranger than that can
//     register one with sheet.onKey().
//
// Events, all dispatched on the row (so hx-trigger on a row can hear them) and bubbling:
// sheet:select {id}, sheet:open {id} (Enter, when nothing declares Enter), and sheet:clear {id}
// on the field.

(() => {
  "use strict";

  // The phone breakpoint DESIGN.md sets: below it there is one scrolling table and no folding.
  const PHONE = matchMedia("(max-width: 40rem)");
  const MIN_COL_REM = 36;
  const CLEARANCE_REM = 0.75; // space between the last column and the title block below it
  const GAP_REM = 0.5; // between the selected row and its callout
  const EDGE_REM = 0.375; // between the find-number column and the callout's left edge
  const MIN_CALLOUT_REM = 12;
  const REFOLD_MS = 60;

  const rem = () => parseFloat(getComputedStyle(document.documentElement).fontSize);

  /**
   * Build the engine over one drawing area.
   *
   * @param {Element} startField The .bom-field the server rendered its table into.
   * @returns {object} The sheet, as documented at the bottom of this file.
   */
  function createSheet(startField) {
    let field = startField;
    // Every sheet in the set closes with a title block, and the fold is measured against this one.
    // A detached stand-in keeps a sheet that somehow has none from taking the engine, and with it
    // the whole list, down.
    let titleblock =
      document.querySelector(".bom-sheet > .titleblock") || document.createElement("div");
    const host = document.getElementById("row-callout");

    let source = null; // the server's table, held detached while the sheet is folded
    let rows = []; // its <tr>s in document order, moved between columns as they fold
    let label = "Parts list";
    let selectedId = null;
    let page = 0;
    let pages = 1;
    let limits = { bottom: Infinity, lastColBottom: Infinity };
    let followSelection = true;
    let placedNode = null; // the callout element last positioned, to keep a refold from replaying
    let pendingFocusId = null; // the row that had focus when HTMX took the table away
    const rowPage = new Map();
    const keyHandlers = [];

    // ---------- Reading what the server drew ----------

    /**
     * Take over the table currently in the drawing area, if it is a new one.
     *
     * A folded column's table is marked, so this finds only markup the server produced: the first
     * render, and every HTMX swap that replaces the rows.
     *
     * @returns {boolean} True if a new table was adopted.
     */
    function adopt() {
      const table = field.querySelector("table.bom:not([data-sheet-column])");
      if (!table) return false;
      source = table;
      label = table.getAttribute("aria-label") || field.getAttribute("aria-label") || label;
      rows = Array.from(table.tBodies[0] ? table.tBodies[0].rows : []);
      return true;
    }

    /** @returns {Element|null} The row with the current selection, wherever it has been folded. */
    function findRow(id) {
      if (id == null) return null;
      return field.querySelector(`tr[data-id="${CSS.escape(String(id))}"]`);
    }

    // ---------- Folding ----------

    /**
     * Build a fresh table shell for one column: the repeated header and an empty body.
     *
     * @returns {HTMLTableElement} The shell, marked as the engine's own work.
     */
    function columnTable() {
      const table = document.createElement("table");
      table.className = source.className;
      table.dataset.sheetColumn = "";
      if (source.tHead) table.append(source.tHead.cloneNode(true));
      table.append(document.createElement("tbody"));
      return table;
    }

    /**
     * Say, to assistive technology, that the split tables are one list.
     *
     * A folded sheet is several <table>s holding one parts list between them, and left alone each
     * would be announced as a list of its own that starts again at row 1. So every column declares
     * the whole list's length and every row its position in the whole list - the case
     * aria-rowcount and aria-rowindex exist for - and each column's caption names the list and
     * says which part of it this is. The caption is visually hidden: the sheet already shows which
     * column is which by drawing them side by side.
     *
     * @param {Element[]} pageEls The .bom-page elements, in order.
     */
    function announceAsOneList(pageEls) {
      const index = new Map(rows.map((tr, i) => [tr, i + 2])); // + the header row, which is row 1
      pageEls.forEach((pageEl, i) => {
        const columns = pageEl.querySelectorAll(".bom-col");
        columns.forEach((column, j) => {
          const table = column.querySelector("table.bom");
          table.setAttribute("aria-rowcount", String(rows.length + 1));
          const caption = table.createCaption();
          caption.className = "visually-hidden";
          caption.textContent =
            `${label}, sheet ${i + 1} of ${pageEls.length}, column ${j + 1} of ${columns.length}`;
          const header = table.tHead && table.tHead.rows[0];
          if (header) header.setAttribute("aria-rowindex", "1");
          for (const tr of table.tBodies[0].rows) {
            tr.setAttribute("aria-rowindex", String(index.get(tr)));
          }
        });
      });
    }

    /** Draw the phone sheet: the server's own table, whole, scrolling. */
    function renderPhone() {
      titleblock.style.width = "";
      const body = source.tBodies[0];
      for (const tr of rows) body.append(tr);
      source.setAttribute("aria-rowcount", String(rows.length + 1));
      field.replaceChildren(source);
      rows.forEach((tr, i) => {
        tr.setAttribute("aria-rowindex", String(i + 2));
        rowPage.set(tr.dataset.id, 0);
      });
      pages = 1;
      page = 0;
      limits = { bottom: Infinity, lastColBottom: Infinity };
    }

    /** Fold the rows into columns and continuation sheets. */
    function renderFolded() {
      const width = field.clientWidth;
      const height = field.clientHeight;
      // The rightmost column matches the standard title-block width (--tb-width) so the block sits
      // exactly under it; the other columns share the rest, each at least MIN_COL_REM wide.
      const standard =
        parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--tb-width")) * rem();
      const minCol = MIN_COL_REM * rem();
      const tbWidth = Math.min(standard, width);
      const others = Math.floor((width - tbWidth) / minCol);
      const columns = others + 1;
      const otherWidth = others ? (width - tbWidth) / others : 0;
      const widthFor = (i) => (i === columns - 1 ? tbWidth : otherWidth);

      titleblock.style.width = `${tbWidth}px`;
      const tbTop = titleblock.isConnected
        ? titleblock.getBoundingClientRect().top - field.getBoundingClientRect().top
        : height;
      const lastCol = columns - 1;
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
        col.style.width = `${widthFor(colIndex)}px`;
        col.dataset.limit = String(colIndex === lastCol ? lastColBottom : height);
        const table = columnTable();
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
      for (const tr of rows) {
        body.append(tr);
        // One row past the column's limit starts the next column - unless it is the only row
        // there, which would leave an empty column and try the same row again for ever.
        if (col.offsetHeight > Number(col.dataset.limit) && body.children.length > 1) {
          tr.remove();
          if (colIndex < lastCol) newCol();
          else newPage();
          body.append(tr);
        }
        rowPage.set(tr.dataset.id, pageEls.length - 1);
      }

      pageEls.forEach((el) => {
        const cols = el.querySelectorAll(".bom-col");
        // A page that ran to the full column count reaches the frame's right-hand line and drops
        // its own rule there, so the two do not double up.
        if (cols.length === columns) cols[cols.length - 1].classList.add("is-edge");
        cols.forEach((c, j) => c.classList.toggle("is-last", j === lastCol));
      });
      announceAsOneList(pageEls);
      pages = pageEls.length;
    }

    /**
     * Draw the sheet: phone or folded, then settle the selection, the callout and the sheet count.
     */
    function render() {
      const phone = PHONE.matches;
      // The class the stylesheet folds on: it pins the sheet to the viewport and the title block
      // to its lower-right corner. Off it, the page is the long table the server rendered.
      document.documentElement.classList.toggle("bom-fixed", !phone);
      titleblock = document.querySelector(".bom-sheet > .titleblock") || titleblock;

      const focusedRow = document.activeElement && document.activeElement.closest
        ? document.activeElement.closest("tr[data-id]")
        : null;
      const refocusId = focusedRow ? focusedRow.dataset.id : pendingFocusId;
      pendingFocusId = null;

      rowPage.clear();
      // A row the server has just taken away - deleted, retired out of the filter - cannot go on
      // being the selection, and its callout has nothing left to point at.
      if (selectedId != null && !rows.some((tr) => tr.dataset.id === String(selectedId))) {
        selectedId = null;
        clearCallout();
      }
      if (!source || !rows.length) {
        // Nothing to fold: the server's empty state is already in the drawing area, and the title
        // block falls back to the width the stylesheet gives it.
        titleblock.style.width = "";
        pages = 1;
        page = 0;
        finish();
        if (refocusId) focusSelected();
        return;
      }

      // Detaching the source first takes the rows out of the page in one move; they are held in
      // `rows` throughout, so nothing is lost and no row is ever rebuilt from markup.
      source.remove();
      field.replaceChildren();
      if (phone) renderPhone();
      else renderFolded();
      finish();
      if (refocusId != null && String(refocusId) === String(selectedId)) focusSelected();
    }

    // ---------- Selection, the callout and the sheet count ----------

    /** Show the current sheet, mark the selected row, place the callout and update SHEET n OF N. */
    function finish() {
      // The sheet follows the selection unless the reader paged away with PgUp/PgDn.
      if (followSelection && selectedId != null && rowPage.has(String(selectedId))) {
        page = rowPage.get(String(selectedId));
      }
      page = Math.max(0, Math.min(page, pages - 1));
      field.querySelectorAll(".bom-page").forEach((el, i) => (el.hidden = i !== page));
      field.querySelectorAll("tr[data-id]").forEach((tr) => {
        const on = tr.dataset.id === String(selectedId);
        tr.classList.toggle("is-selected", on);
        tr.setAttribute("aria-selected", String(on));
      });
      placeCallout();
      announcePage();
    }

    /** Write the sheet count into the title block and enable the pager it belongs to. */
    function announcePage() {
      const count = document.getElementById("sheet-no");
      if (count) count.textContent = `${page + 1} of ${pages}`;
      const prev = document.getElementById("page-prev");
      const next = document.getElementById("page-next");
      // The server draws both disabled, which is the truth until the rows have been folded: it
      // cannot know how many sheets they come to at this width.
      if (prev) prev.disabled = page === 0;
      if (next) next.disabled = page >= pages - 1;
    }

    /** Empty the callout host, so no callout outlives the selection it belongs to. */
    function clearCallout() {
      if (!host) return;
      host.replaceChildren();
      host.hidden = true;
      placedNode = null;
    }

    /**
     * Put the callout beside the find-number column, just off the selected row.
     *
     * The host is a zero-size anchor parked at the drawing area's top-left corner, so everything
     * below is measured in the same coordinates the folding code uses. The callout leaves every
     * row's find number visible and clickable, and an elbow leader runs from a dot on the selected
     * row's number into its side.
     */
    function placeCallout() {
      if (!host) return;
      const callout = host.querySelector(".bom-callout");
      const tr = findRow(selectedId);
      // offsetParent is null on a row folded onto a sheet that is not the one being shown.
      if (!callout || !tr || tr.offsetParent === null) {
        // A callout with no row under it stays hidden rather than being drawn wherever the last
        // one happened to sit. A screen that wants a callout for something that is not a row yet
        // - Items adding an item, the register importing a project - renders a ghost row for it
        // and selects that, the way the mockups do; then there is something to point the leader at.
        host.hidden = true;
        if (!callout) placedNode = null;
        return;
      }

      // A callout that is only being re-placed - a refold, a resize - must not replay its entry
      // animation; a freshly swapped-in one should.
      callout.classList.toggle("is-settled", callout === placedNode);
      placedNode = callout;
      host.hidden = false;

      const fieldBox = field.getBoundingClientRect();
      host.style.left = `${fieldBox.left + scrollX}px`;
      host.style.top = `${fieldBox.top + scrollY}px`;

      const rowBox = tr.getBoundingClientRect();
      const colEl = tr.closest(".bom-col") || field;
      const colBox = colEl.getBoundingClientRect();
      const findBox = tr.cells[0].getBoundingClientRect();
      const gap = GAP_REM * rem();
      const edge = EDGE_REM * rem();
      const left = findBox.right - fieldBox.left + edge;
      callout.style.left = `${left}px`;
      callout.style.width =
        `${Math.max(MIN_CALLOUT_REM * rem(), colBox.right - fieldBox.left - edge - left)}px`;
      // The leader runs in the space between the number and the column rule, never through a number.
      const leaderX = findBox.right - fieldBox.left - 0.375 * rem();
      callout.style.setProperty("--leader-dx", `${left - leaderX}px`);

      const rowTop = rowBox.top - fieldBox.top;
      const rowBottom = rowBox.bottom - fieldBox.top;
      const bottomLimit = colEl.classList.contains("is-last") ? limits.lastColBottom : limits.bottom;
      callout.classList.remove("is-above");
      callout.style.setProperty("--gap", `${gap}px`);
      const height = callout.offsetHeight;
      if (rowBottom + gap + height <= bottomLimit) {
        callout.style.top = `${rowBottom + gap}px`;
      } else if (rowTop - gap - height >= 0) {
        callout.classList.add("is-above");
        callout.style.top = `${rowTop - gap - height}px`;
      } else {
        // It fits neither below nor above: sit it as low as the column allows rather than let it
        // run into the title block or be clipped away (DESIGN.md open issue). The leader is told
        // the real distance it has to cover, so it still reaches the row it belongs to.
        const top = Math.max(0, Math.min(rowBottom + gap, bottomLimit - height));
        callout.style.top = `${top}px`;
        callout.style.setProperty("--gap", `${Math.max(0, rowBottom - top)}px`);
      }
      // Phones scroll the long sheet; keep the callout clear of the bottom tab bar.
      if (PHONE.matches) callout.scrollIntoView({ block: "nearest" });
    }

    /** Give the selected row the focus, without scrolling a folded sheet sideways. */
    function focusSelected() {
      const el = findRow(selectedId);
      if (!el || el.offsetParent === null) return;
      el.focus({ preventScroll: true });
      if (PHONE.matches) el.scrollIntoView({ block: "nearest" });
    }

    /**
     * Select a row: mark it, turn to its sheet, focus it and ask the screen for its callout.
     *
     * @param {string|null} id The row's data-id.
     * @param {object} options focus: false to leave the focus where it is.
     */
    function select(id, { focus = true } = {}) {
      const tr = findRow(id);
      if (!tr) return;
      selectedId = tr.dataset.id;
      followSelection = true;
      // Cleared before the event rather than after the reply: the old callout belongs to the old
      // row, and leaving it up while a new one is fetched would show it beside the wrong one.
      clearCallout();
      finish();
      if (focus) focusSelected();
      tr.dispatchEvent(new CustomEvent("sheet:select", { detail: { id: selectedId }, bubbles: true }));
    }

    /** Drop the selection and its callout. */
    function clear() {
      const previous = selectedId;
      selectedId = null;
      clearCallout();
      finish();
      field.dispatchEvent(new CustomEvent("sheet:clear", { detail: { id: previous }, bubbles: true }));
    }

    /**
     * Move the selection by whole rows, in the order the server rendered them.
     *
     * @param {number} delta 1 for the next row, -1 for the previous one.
     */
    function move(delta) {
      if (!rows.length) return;
      const onSheet = rows.filter((tr) => rowPage.get(tr.dataset.id) === page);
      let i = rows.findIndex((tr) => tr.dataset.id === String(selectedId));
      if (i < 0 || rowPage.get(String(selectedId)) !== page) {
        // Nothing selected on this sheet: start at its first row (down) or its last row (up).
        const start = delta > 0 ? onSheet[0] : onSheet[onSheet.length - 1];
        i = rows.indexOf(start || rows[0]);
      } else {
        i = Math.max(0, Math.min(rows.length - 1, i + delta));
      }
      select(rows[i].dataset.id);
    }

    /**
     * Turn to another continuation sheet.
     *
     * Paging only shows another sheet; it never selects, and the next arrow key starts from the
     * sheet on screen.
     *
     * @param {number} next The sheet to show, from 0.
     */
    function setPage(next) {
      const target = Math.max(0, Math.min(pages - 1, next));
      if (target === page) return;
      page = target;
      followSelection = false;
      finish();
    }

    // ---------- Keys ----------

    /**
     * Find the element a screen has put this key on.
     *
     * The open callout is searched first, so a form's Cancel takes Esc and its Save takes Enter
     * ahead of anything the title block declares.
     *
     * @param {KeyboardEvent} e The key press.
     * @returns {Element|null} The button to press.
     */
    function keyTarget(e) {
      const wanted = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const scopes = [host, document.getElementById("sheet")].filter(Boolean);
      for (const scope of scopes) {
        for (const el of scope.querySelectorAll("[data-sheet-key]")) {
          if (el.disabled || el.hidden || el.offsetParent === null) continue;
          const keys = el.dataset.sheetKey.split(/\s+/);
          if (keys.some((k) => (k.length === 1 ? k.toLowerCase() : k) === wanted)) return el;
        }
      }
      return null;
    }

    /**
     * The shared key map, and the way a screen's own verbs reach their buttons.
     *
     * @param {KeyboardEvent} e The key press.
     */
    function onKeyDown(e) {
      // The target is not always an element: a key pressed with nothing focused arrives on the
      // document, which has no closest().
      const closest = (selector) => (e.target.closest ? e.target.closest(selector) : null);
      const inControl = !!closest("input, textarea, select, [contenteditable]");
      for (const handler of keyHandlers) {
        if (handler(e, inControl)) {
          e.preventDefault();
          return;
        }
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      if (e.key === "Escape") {
        const cancel = keyTarget(e);
        if (cancel) cancel.click();
        else if (inControl) e.target.blur();
        else if (selectedId != null) clear();
        else return;
        e.preventDefault();
        return;
      }
      if (inControl) return;

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
          if (rows.length) select(rows[0].dataset.id);
          break;
        case "End":
          if (rows.length) select(rows[rows.length - 1].dataset.id);
          break;
        // Paging is the one pair of keys that changes what is on screen without changing what is
        // selected; DESIGN.md is explicit that they never move the selection.
        case "PageDown":
          setPage(page + 1);
          break;
        case "PageUp":
          setPage(page - 1);
          break;
        default: {
          // Enter and Space on a button or a link activate it, not a row verb.
          if ((e.key === "Enter" || e.key === " ") && closest("button, a")) return;
          const target = keyTarget(e);
          if (target) {
            target.click();
            break;
          }
          const tr = findRow(selectedId);
          if (e.key === "Enter" && tr) {
            tr.dispatchEvent(
              new CustomEvent("sheet:open", { detail: { id: selectedId }, bubbles: true })
            );
            break;
          }
          return;
        }
      }
      e.preventDefault();
    }

    // ---------- Wiring ----------

    // Clicks are taken on the document rather than on the field, because HTMX can replace the
    // field itself and a listener bound to the old element would go with it.
    document.addEventListener("click", (e) => {
      const pager = e.target.closest("#page-prev, #page-next");
      if (pager) {
        setPage(pager.id === "page-next" ? page + 1 : page - 1);
        return;
      }
      if (e.target.closest("#row-callout")) return;
      const tr = e.target.closest("tr[data-id]");
      if (!tr || !field.contains(tr)) return;
      // Clicking the selected row again is Esc: close what is open, otherwise deselect.
      if (tr.dataset.id === String(selectedId)) {
        const cancel = host && host.querySelector('[data-sheet-key~="Escape"]');
        if (cancel) cancel.click();
        else clear();
        return;
      }
      select(tr.dataset.id);
    });

    document.addEventListener("keydown", onKeyDown);

    // Fold again whenever the drawing area changes size (window resize, scrollbar, zoom) and
    // whenever web fonts finish loading, since both change how many rows fit. Folding never
    // changes the drawing area's own size, so this cannot loop; the size guard below is a second
    // lock on that, and keeps the one resize that switching to the fixed layout does cause from
    // costing a second fold.
    let timer;
    let lastSize = "";
    const refold = () => {
      clearTimeout(timer);
      timer = setTimeout(render, REFOLD_MS);
    };
    const observer = new ResizeObserver(() => {
      const box = field.parentElement.getBoundingClientRect();
      const size = `${Math.round(box.width)}x${Math.round(box.height)}`;
      if (size === lastSize) return;
      lastSize = size;
      refold();
    });
    observer.observe(field.parentElement);
    PHONE.addEventListener("change", () => {
      lastSize = "";
      render();
    });
    if (document.fonts) {
      document.fonts.ready.then(refold);
      document.fonts.addEventListener("loadingdone", refold);
    }

    // Remember which row had the focus before HTMX takes the table out of the page: by the time
    // the swap is over the focused element is gone and the browser has fallen back to <body>.
    document.body.addEventListener("htmx:beforeSwap", (e) => {
      const tr = document.activeElement && document.activeElement.closest
        ? document.activeElement.closest("tr[data-id]")
        : null;
      if (tr && (e.target === field || e.target.contains(field) || field.contains(e.target))) {
        pendingFocusId = tr.dataset.id;
      }
    });

    document.body.addEventListener("htmx:afterSwap", (e) => {
      if (host && (e.target === host || host.contains(e.target))) {
        // Only the callout changed: place it and put the focus in it if it asked for it. The rows
        // are untouched, so nothing is refolded and nothing else moves.
        placeCallout();
        const first = host.querySelector("[autofocus]");
        if (first) first.focus({ preventScroll: true });
        return;
      }
      const current = document.querySelector(".bom-field");
      const touched =
        current !== field || e.target === field || field.contains(e.target) || e.target.contains(field);
      if (!touched) return;
      if (current && current !== field) {
        field = current;
        observer.disconnect();
        lastSize = "";
        observer.observe(field.parentElement);
      }
      adopt();
      lastSize = "";
      render();
    });

    adopt();

    return {
      /** @returns {boolean} True while the sheet is one scrolling table. */
      isPhone: () => PHONE.matches,
      /** Re-read the rows the server drew and fold them again. */
      reload: () => {
        adopt();
        render();
      },
      render,
      select,
      clear,
      move,
      setPage,
      focusSelected,
      /** Re-place the callout after something outside the engine changed its size. */
      place: placeCallout,
      /**
       * Add a key handler, tried before the shared map.
       *
       * @param {function} handler (event, inControl) => true when it has handled the key.
       */
      onKey: (handler) => keyHandlers.push(handler),
      get selectedId() {
        return selectedId;
      },
      get page() {
        return page;
      },
      get pages() {
        return pages;
      },
      get rowCount() {
        return rows.length;
      },
    };
  }

  const field = document.querySelector(".bom-field");
  if (field) {
    window.sheet = createSheet(field);
    window.sheet.render();
  }
})();
