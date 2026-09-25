#!/usr/bin/env python
"""Drive the folding engine in a real browser and check what it did.

``src/web/static/js/sheet.js`` is the one part of this application that no
unittest can reach: it is 700 lines of measurement, and what it does depends on
the height of a rendered row, the width of a rendered column and the order in
which htmx and the browser fire their events. Four screens are written against
it, so the things they depend on are pinned here instead - in Chrome, over CDP,
against the real server.

Usage (from WSL, with the Windows venv - the same crossing ``capture_web.py``
makes, and for the same reason)::

    ./.venv/Scripts/python.exe scripts/drive_sheet.py

With no arguments it seeds its own scratch directory of projects, boots the
app, runs every check and tears it all down. The data directory and the Chrome
profile are made under ``.scratch/`` at the repository root and removed
afterwards; nothing is written outside the repository. ``--data-dir`` points it at a
directory that is already seeded, and ``--check NAME`` runs one check.

What is checked, and why each one is here:

``fold``
    The fold at the three review widths: none at 390, one column at 1280, three
    at 1920 with the title block under the rightmost. This is the whole
    premise, and it is measured rather than asserted from the stylesheet.

``swap-empty``
    An htmx swap that lands **no table** - the empty state a filter matching
    nothing renders. The engine has to forget the rows it was holding; the bug
    this pins drew the previous list back over the server's "nothing matches",
    selectable, with the empty state wiped.

``swap-fewer``
    A swap to a shorter list. The rows that remain are re-adopted and refolded,
    and a selection whose row is gone is dropped rather than left pointing at
    nothing.

``page-then-arrow``
    PgDn turns the sheet without moving the selection, and the next arrow key
    starts from the sheet on screen rather than from wherever the selection was
    left. DESIGN.md is explicit about this pair and it is easy to break.

``escape-in-field``
    Esc with the caret in a form field presses the callout's Cancel, rather
    than blurring the field or clearing the selection. Every form callout in
    the set depends on it.

``autofocus-select``
    A callout's prefilled field is selected as well as focused, so the first
    keystroke replaces the draft - but a field carrying a name that was just
    refused is not, because those are the words the person typed.

``key-on-fixed``
    A verb declared on a `position: fixed` element - a phone tab bar, anything
    a later screen pins - can still be pressed, while one on a `display: none`
    element cannot.

``short-window``
    A window too short for the title block to sit under the last column. The
    fold must degrade to fewer rows a sheet, not to one row a sheet - which is
    what an unclamped last-column limit gives, and 68 projects become 68
    sheets.

``aria``
    What the selection says to someone who cannot see it: every folded column
    is still a grid, a row with a callout names the host it controls, the grid
    has exactly one Tab stop and it follows the selection, and a callout's
    arrival is announced in the polite status region - by name and actions,
    without the key legends - and forgotten when the callout goes.

``key-on-field``
    A key declared on a field (Items' ``/`` filter, a ``C`` category select)
    puts the focus in it, with a text field's contents selected, instead of
    clicking it - which for a field does nothing at all.

``items-filter``
    The first real rows swap in the set, driven end to end on the Items sheet:
    ``/`` goes to the filter, typing narrows the rows through htmx, the address
    and the retired toggle follow, a filter matching nothing leaves the empty
    state and no selection, and Esc clears the filter and brings the rows back.

``items-actions``
    The Items row callouts, by key and by mouse: Enter opens the edit form
    with the name focused and Esc returns the focus to the row; a click on
    Replace opens its form; N draws the ghost row and Enter (declared on Save)
    adds; R retires and moves the selection on; Del asks and Del again
    deletes. It adds an item and deletes it again, so ``items-filter`` still
    finds its 64 rows.
``callout-place``
    A callout taller than the room its column leaves - the Items edit form at
    1280, on the mockups' own project - goes below its row over the title
    block rather than sliding up over the row it belongs to; and a phone's
    callout stops inside the table's right rule.

``form-verbs``
    While a form (anything with a Cancel) is open, the sheet's own verbs are
    not pressed: N and H over an Items edit form with the focus outside its
    fields leave the page and the draft alone, as I does over the register's
    New form. Esc still cancels, and N works again once it has.

Each check leaves the page as it found it by navigating afresh, so they are
independent and ``--check`` can run any one of them alone.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_web import (  # noqa: E402
    CaptureError,
    DevTools,
    scratch_dir,
    start_chrome,
    start_server,
    stop_process,
    windows_path,
)
from seed_capture_data import seed  # noqa: E402


PROGRAM = "drive_sheet.py"

DEFAULT_PORT = 8098

# How long the page may take to render and boot the engine.
READY_TIMEOUT_S = 20.0
POLL_INTERVAL_S = 0.05

# The engine debounces a refold by 60 ms; this is that, with room for the frame
# it draws afterwards. Every resize in this script waits it out.
REFOLD_WAIT_S = 0.4

# Room for one htmx round trip on loopback plus the callout's placement.
CALLOUT_WAIT_S = 0.6

# The review widths, as capture_web.py uses them.
PHONE = (390, 844)
NARROW = (1280, 900)
WIDE = (1920, 1080)

# Short enough that the title block, pinned to the lower-right corner, reaches
# up past the top of the drawing area. See the short-window check.
SHORT = (1280, 420)


class CheckError(CaptureError):
    """A check ran and the engine did not do what four screens need it to do."""


# --------------------------------------------------------------------------
# Talking to the page
# --------------------------------------------------------------------------


def size(devtools: DevTools, width: int, height: int) -> None:
    """
    Put the page at one viewport size and let the engine settle.

    Args:
        devtools: The CDP session.
        width: CSS pixels across.
        height: CSS pixels down.
    """
    devtools.call(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": False,
        },
    )
    time.sleep(REFOLD_WAIT_S)


def open_page(devtools: DevTools, url: str, width: int, height: int) -> None:
    """
    Load one address at one size and wait until the engine is up.

    Args:
        devtools: The CDP session.
        url: The address to load.
        width: CSS pixels across.
        height: CSS pixels down.

    Raises:
        CheckError: If the page never reaches a booted engine.
    """
    devtools.call(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": False,
        },
    )
    devtools.call("Page.navigate", {"url": url})

    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        ready = devtools.evaluate(
            'document.readyState === "complete" && !!window.sheet'
        )
        if ready:
            # The sheet is booted; the callout it asked for may still be in the
            # air, and the fold has a debounce in front of it.
            time.sleep(CALLOUT_WAIT_S)
            return
        time.sleep(POLL_INTERVAL_S)
    raise CheckError(f"{url} never booted the sheet engine")


def state(devtools: DevTools) -> dict:
    """
    Read everything the checks ask about, in one round trip.

    Args:
        devtools: The CDP session.

    Returns:
        dict: The engine's own view (page, pages, rowCount, selectedId) and the
        page's (the columns on the sheet being shown, the rows in the drawing
        area, whether the callout host is showing anything).
    """
    return devtools.evaluate(
        """
        (() => {
          const field = document.querySelector(".bom-field");
          const shown = field.querySelector(".bom-page:not([hidden])");
          const host = document.getElementById("row-callout");
          return {
            page: window.sheet.page,
            pages: window.sheet.pages,
            rowCount: window.sheet.rowCount,
            selectedId: window.sheet.selectedId,
            isPhone: window.sheet.isPhone(),
            fixed: document.documentElement.classList.contains("bom-fixed"),
            columns: shown ? shown.querySelectorAll(".bom-col").length : 0,
            rowsInField: field.querySelectorAll("tr[data-id]").length,
            rowsOnSheet: (shown || field).querySelectorAll("tr[data-id]").length,
            emptyLead: (field.querySelector(".bom-empty .lead") || {}).textContent || "",
            calloutShown: !!(host && !host.hidden && host.children.length),
            selectedOnSheet: !!(
              shown || field
            ).querySelector('tr[aria-selected="true"]'),
            ids: Array.from(field.querySelectorAll("tr[data-id]"), (tr) => tr.dataset.id),
          };
        })()
        """
    )


def expect(condition: bool, message: str) -> None:
    """
    Fail a check, loudly.

    Args:
        condition: What had to be true.
        message: What it means that it was not.

    Raises:
        CheckError: When the condition is false.
    """
    if not condition:
        raise CheckError(message)


# The swap the register never does and Items does constantly: htmx replaces the
# contents of the drawing area and fires afterSwap on it. Dispatched on the
# field with bubbles, which is where and how htmx fires it, so the engine's own
# listener on document.body sees exactly what it would see in the wild.
SWAP = """
(() => {
  const field = document.querySelector(".bom-field");
  field.innerHTML = %s;
  field.dispatchEvent(new CustomEvent("htmx:afterSwap", { bubbles: true }));
  return true;
})()
"""

EMPTY_MARKUP = (
    '\'<div class="bom-empty"><p class="lead">No projects match.</p>'
    "<p class=\"detail\">Clear the filter to see them all.</p></div>'"
)

# Rebuilds the server's own long table from the first few rows currently in the
# page, so the swap carries real markup - ids, hx- attributes and all.
FEWER_MARKUP = """
(() => {
  const field = document.querySelector(".bom-field");
  const rows = Array.from(field.querySelectorAll("tr[data-id]")).slice(0, 3);
  const head = field.querySelector("table.bom thead").outerHTML;
  return '<table class="bom" aria-label="Projects">' + head + "<tbody>" +
    rows.map((tr) => tr.outerHTML).join("") + "</tbody></table>";
})()
"""


def swap(devtools: DevTools, markup_expression: str) -> None:
    """
    Replace the drawing area's contents and tell the engine htmx did it.

    Args:
        devtools: The CDP session.
        markup_expression: A JavaScript expression yielding the new markup.
    """
    devtools.evaluate(SWAP % markup_expression)
    time.sleep(REFOLD_WAIT_S)


def press(devtools: DevTools, key: str, in_field: str = "") -> None:
    """
    Send a key the way the browser does, to the element the person is on.

    Args:
        devtools: The CDP session.
        key: A UI Events key value, e.g. ``ArrowDown`` or ``Escape``.
        in_field: A selector to focus first, for the keys that are only
            interesting with the caret in a form field.
    """
    focus = (
        f'document.querySelector("{in_field}").focus();' if in_field else ""
    )
    devtools.evaluate(
        f"""
        (() => {{
          {focus}
          const target = document.activeElement || document.body;
          target.dispatchEvent(new KeyboardEvent("keydown", {{
            key: "{key}", bubbles: true, cancelable: true
          }}));
          return true;
        }})()
        """
    )
    time.sleep(CALLOUT_WAIT_S)


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------


def check_fold(devtools: DevTools, base: str) -> str:
    """
    Check the fold at the three review widths.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}/", *PHONE)
    phone = state(devtools)
    expect(phone["isPhone"], "390 did not read as a phone")
    expect(not phone["fixed"], "390 pinned the sheet: the phone sheet scrolls")
    expect(phone["columns"] == 0, f"390 folded into {phone['columns']} columns")
    expect(phone["pages"] == 1, f"390 folded onto {phone['pages']} sheets")
    expect(
        phone["rowsInField"] == phone["rowCount"],
        "390 did not draw every row: "
        f"{phone['rowsInField']} of {phone['rowCount']}",
    )

    size(devtools, *NARROW)
    narrow = state(devtools)
    expect(narrow["fixed"], "1280 did not pin the sheet")
    expect(narrow["columns"] == 1, f"1280 drew {narrow['columns']} columns, not 1")
    expect(narrow["pages"] > 1, "1280 did not run onto a continuation sheet")

    size(devtools, *WIDE)
    wide = state(devtools)
    expect(wide["columns"] == 3, f"1920 drew {wide['columns']} columns, not 3")
    expect(
        wide["rowsOnSheet"] > narrow["rowsOnSheet"],
        "1920 fitted no more rows on a sheet than 1280 did",
    )
    expect(
        wide["pages"] < narrow["pages"],
        "1920 needed as many sheets as 1280 for the same rows",
    )

    # Every row is drawn exactly once, wherever it was folded to.
    expect(
        len(set(wide["ids"])) == wide["rowCount"] == len(wide["ids"]),
        "the fold lost or duplicated a row: "
        f"{len(wide['ids'])} drawn, {len(set(wide['ids']))} distinct, "
        f"{wide['rowCount']} held",
    )
    return (
        f"390: 1 table, {phone['rowsInField']} rows; "
        f"1280: 1 column, {narrow['rowsOnSheet']} rows, {narrow['pages']} sheets; "
        f"1920: 3 columns, {wide['rowsOnSheet']} rows, {wide['pages']} sheets"
    )


def check_swap_empty(devtools: DevTools, base: str) -> str:
    """
    Check a rows swap that lands no table at all.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}/", *NARROW)
    before = state(devtools)
    expect(before["rowCount"] > 0, "nothing to swap away: the register was empty")

    first = before["ids"][0]
    devtools.evaluate(f'window.sheet.select("{first}"), true')
    time.sleep(CALLOUT_WAIT_S)
    selected = state(devtools)
    expect(selected["calloutShown"], "selecting a row drew no callout")

    swap(devtools, EMPTY_MARKUP)
    after = state(devtools)
    expect(
        after["emptyLead"] == "No projects match.",
        "the swapped-in empty state was wiped: the drawing area says "
        f"{after['emptyLead']!r}",
    )
    expect(
        after["rowsInField"] == 0,
        f"{after['rowsInField']} rows were drawn back over the empty state",
    )
    expect(after["rowCount"] == 0, f"the engine still holds {after['rowCount']} rows")
    expect(after["selectedId"] is None, "a row that is gone is still selected")
    expect(not after["calloutShown"], "the callout outlived the row it belonged to")
    expect(after["pages"] == 1, f"an empty sheet folded onto {after['pages']} sheets")
    return f"{before['rowCount']} rows swapped to an empty state and stayed gone"


def check_swap_fewer(devtools: DevTools, base: str) -> str:
    """
    Check a rows swap to a shorter list.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}/", *NARROW)
    before = state(devtools)
    expect(before["rowCount"] > 3, "not enough rows to swap to a shorter list")

    # Selected row survives the swap: the selection and its callout stay.
    devtools.evaluate(f'window.sheet.select("{before["ids"][0]}"), true')
    time.sleep(CALLOUT_WAIT_S)
    swap(devtools, FEWER_MARKUP)
    kept = state(devtools)
    expect(kept["rowCount"] == 3, f"the swap left {kept['rowCount']} rows, not 3")
    expect(kept["rowsInField"] == 3, f"{kept['rowsInField']} rows were drawn, not 3")
    expect(kept["ids"] == before["ids"][:3], "the swap drew the wrong three rows")
    expect(
        kept["selectedId"] == before["ids"][0],
        "a selected row the new list still holds lost the selection",
    )
    expect(kept["pages"] == 1, f"three rows folded onto {kept['pages']} sheets")

    # Selected row does not survive: the selection goes with it.
    open_page(devtools, f"{base}/", *NARROW)
    devtools.evaluate(f'window.sheet.select("{before["ids"][4]}"), true')
    time.sleep(CALLOUT_WAIT_S)
    swap(devtools, FEWER_MARKUP)
    dropped = state(devtools)
    expect(
        dropped["selectedId"] is None,
        f"a row the new list does not hold is still selected: "
        f"{dropped['selectedId']!r}",
    )
    expect(
        not dropped["calloutShown"],
        "the callout of a row the swap took away is still on the sheet",
    )
    return f"{before['rowCount']} rows swapped to 3, selection kept and dropped"


def check_page_then_arrow(devtools: DevTools, base: str) -> str:
    """
    Check that paging moves the sheet and the next arrow starts from it.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}/", *NARROW)
    start = state(devtools)
    expect(start["pages"] > 1, "one sheet: there is nowhere to page to at 1280")

    devtools.evaluate(f'window.sheet.select("{start["ids"][0]}"), true')
    time.sleep(CALLOUT_WAIT_S)
    press(devtools, "PageDown")
    paged = state(devtools)
    expect(paged["page"] == 1, f"PgDn showed sheet {paged['page'] + 1}, not 2")
    expect(
        paged["selectedId"] == start["ids"][0],
        "PgDn moved the selection, which DESIGN.md says it never does",
    )
    expect(
        not paged["selectedOnSheet"],
        "the selected row is on sheet 2, so PgDn did not turn the sheet",
    )

    press(devtools, "ArrowDown")
    moved = state(devtools)
    expect(
        moved["page"] == 1,
        f"the arrow key jumped back to sheet {moved['page'] + 1}",
    )
    expect(
        moved["selectedId"] != start["ids"][0],
        "the arrow key did not move the selection",
    )
    expect(
        moved["selectedOnSheet"],
        "the arrow key selected a row that is not on the sheet being shown",
    )
    return (
        f"PgDn to sheet 2 of {start['pages']} kept "
        f"{start['ids'][0]!r} selected; the arrow then took "
        f"{moved['selectedId']!r}, on sheet 2"
    )


def check_escape_in_field(devtools: DevTools, base: str) -> str:
    """
    Check that Esc with the caret in a form field presses the form's Cancel.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}/?form=new", *NARROW)
    opened = state(devtools)
    expect(opened["calloutShown"], "the new-project form never arrived")
    focused = devtools.evaluate(
        '(document.activeElement && document.activeElement.id) || ""'
    )
    expect(
        focused == "f-name",
        f"the form's [autofocus] field did not take the focus: {focused!r}",
    )

    devtools.evaluate('document.getElementById("f-name").value = "Draft", true')
    press(devtools, "Escape", in_field="#f-name")
    # Cancel is a link, so pressing it is a navigation; give it the round trip.
    time.sleep(CALLOUT_WAIT_S)
    where = devtools.evaluate("location.search")
    expect(
        where == "",
        f"Esc in the field did not press Cancel: the address is still {where!r}",
    )
    return "Esc with the caret in the name field pressed Cancel and left the form"


def check_autofocus_select(devtools: DevTools, base: str) -> str:
    """
    Check that a prefilled draft is selected and a refused one is not.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    caret = """
    (() => {
      const el = document.activeElement;
      if (!el || el.id !== "f-name") return null;
      return {
        value: el.value,
        start: el.selectionStart,
        end: el.selectionEnd,
        invalid: el.getAttribute("aria-invalid") === "true",
      };
    })()
    """

    open_page(devtools, f"{base}/?form=new&name=Draft%20name", *NARROW)
    draft = devtools.evaluate(caret)
    expect(draft is not None, "the new-project form did not take the focus")
    expect(
        (draft["start"], draft["end"]) == (0, len(draft["value"])),
        f"a prefilled draft was focused but not selected: {draft}",
    )

    # A name already on the register, so the form comes back refused.
    open_page(devtools, f"{base}/", *NARROW)
    taken = devtools.evaluate(
        '(document.querySelector("tr[data-id]").dataset.id || "")'
        '.replace(/\\.pairrank$/, "")'
    )
    open_page(devtools, f"{base}/?form=new&name={taken}&submitted=1", *NARROW)
    refused = devtools.evaluate(caret)
    expect(refused is not None, "the refused form did not take the focus")
    expect(refused["invalid"], f"{taken!r} was not refused as a name already taken")
    expect(
        refused["start"] == refused["end"],
        "a refused name was selected, so the next keystroke would wipe what "
        f"the person typed: {refused}",
    )
    return (
        f"{draft['value']!r} selected on open; {refused['value']!r}, refused, "
        "left with a caret and no selection"
    )


def check_key_on_fixed(devtools: DevTools, base: str) -> str:
    """
    Check that a verb declared on a pinned element can still be pressed.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}/", *PHONE)
    devtools.evaluate(
        """
        (() => {
          window.__pressed = [];
          const make = (key, css) => {
            const b = document.createElement("button");
            b.type = "button";
            b.dataset.sheetKey = key;
            b.textContent = key;
            b.style.cssText = css;
            b.addEventListener("click", () => window.__pressed.push(key));
            document.getElementById("sheet").append(b);
          };
          // What a phone tab bar is, and what nothing on the sheet may be.
          make("Q", "position:fixed;left:0;bottom:0");
          make("W", "position:static");
          make("E", "display:none");
          return true;
        })()
        """
    )
    for key in ("q", "w", "e"):
        press(devtools, key)
    pressed = devtools.evaluate("window.__pressed")

    expect("Q" in pressed, "a key declared on a fixed element was not pressed")
    expect("W" in pressed, "a key declared on an ordinary element was not pressed")
    expect("E" not in pressed, "a key declared on a hidden element was pressed")
    return f"pressed {pressed} of Q (fixed), W (in flow), E (display:none)"


def check_short_window(devtools: DevTools, base: str) -> str:
    """
    Check the fold in a window too short for the title block to clear.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}/", *NARROW)
    normal = state(devtools)

    size(devtools, *SHORT)
    short = state(devtools)
    expect(
        short["rowsOnSheet"] >= 3,
        f"a short window put {short['rowsOnSheet']} rows on a sheet: the last "
        "column's limit has gone to nothing and every row overflows it",
    )
    expect(
        short["pages"] * 3 <= short["rowCount"],
        f"{short['rowCount']} rows folded onto {short['pages']} sheets - "
        "about one sheet each, which is the unclamped limit",
    )
    expect(
        short["rowsInField"] > 0 and len(set(short["ids"])) == short["rowCount"],
        "the short window lost rows",
    )
    return (
        f"1280x420: {short['rowsOnSheet']} rows a sheet over {short['pages']} "
        f"sheets (1280x900: {normal['rowsOnSheet']} over {normal['pages']})"
    )


ARIA_STATE = """
(() => {
  const field = document.querySelector(".bom-field");
  const callout = document.querySelector("#row-callout .bom-callout");
  const shown = field.querySelector(".bom-page:not([hidden])") || field;
  return {
    roles: Array.from(field.querySelectorAll("table.bom"), (t) => t.getAttribute("role")),
    stops: Array.from(field.querySelectorAll("tr[data-id]"))
      .filter((tr) => tr.tabIndex === 0)
      .map((tr) => tr.dataset.id),
    firstOnSheet: (shown.querySelector("tr[data-id]") || { dataset: {} }).dataset.id || null,
    status: document.getElementById("callout-status").textContent,
    label: callout ? callout.getAttribute("aria-label") : null,
    controls: Array.from(field.querySelectorAll("tr[data-id][hx-get]"))
      .every((tr) => tr.getAttribute("aria-controls") === "row-callout"),
  };
})()
"""


def check_aria(devtools: DevTools, base: str) -> str:
    """
    Check what the selection says to assistive technology.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}/", *NARROW)
    before = devtools.evaluate(ARIA_STATE)
    expect(before["roles"], "the folded sheet has no tables at all")
    expect(
        all(role == "grid" for role in before["roles"]),
        f"a folded column lost the grid role: {before['roles']}",
    )
    expect(before["controls"], "a row with a callout does not name #row-callout")
    expect(
        before["stops"] == [before["firstOnSheet"]],
        "with nothing selected the grid's one Tab stop should be the first row "
        f"on the sheet; it is {before['stops']}",
    )

    ids = state(devtools)["ids"]
    devtools.evaluate(f'window.sheet.select("{ids[2]}"), true')
    time.sleep(CALLOUT_WAIT_S)
    selected = devtools.evaluate(ARIA_STATE)
    expect(selected["label"], "selecting a row drew no callout to announce")
    expect(
        selected["stops"] == [ids[2]],
        f"the Tab stop did not follow the selection: {selected['stops']}",
    )
    expect(
        selected["status"].startswith(f"Callout for {selected['label']}"),
        f"the arrival of {selected['label']!r}'s callout was announced as "
        f"{selected['status']!r}",
    )
    expect(
        "Open" in selected["status"] and "↵" not in selected["status"],
        "the announcement should list the actions by name, without their "
        f"legends: {selected['status']!r}",
    )

    devtools.evaluate("window.sheet.clear(), true")
    time.sleep(REFOLD_WAIT_S)
    cleared = devtools.evaluate(ARIA_STATE)
    expect(
        cleared["status"] == "",
        f"the announcement outlived its callout: {cleared['status']!r}",
    )
    return (
        f"{len(before['roles'])} grid column(s); Tab stop on "
        f"{before['stops'][0]!r}, then on the selection; announced "
        f"{selected['status']!r}"
    )


def check_key_on_field(devtools: DevTools, base: str) -> str:
    """
    Check that a key declared on a field puts the caret in it.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}/", *NARROW)
    devtools.evaluate(
        """
        (() => {
          const input = document.createElement("input");
          input.id = "probe-filter";
          input.dataset.sheetKey = "/";
          input.value = "typed before";
          const select = document.createElement("select");
          select.id = "probe-category";
          select.dataset.sheetKey = "C";
          select.innerHTML = "<option>All</option><option>Linear</option>";
          document.getElementById("sheet").append(input, select);
          document.activeElement && document.activeElement.blur();
          return true;
        })()
        """
    )
    focused = """
    (() => {
      const el = document.activeElement;
      return {
        id: (el && el.id) || "",
        selected: !!(el && el.select && el.selectionStart === 0 &&
                     el.selectionEnd === el.value.length),
      };
    })()
    """

    press(devtools, "/")
    slash = devtools.evaluate(focused)
    expect(
        slash["id"] == "probe-filter",
        f"/ declared on a field did not focus it: the focus is on {slash['id']!r}",
    )
    expect(slash["selected"], "the filter's old text was not selected, so typing adds to it")

    devtools.evaluate("document.activeElement.blur(), true")
    press(devtools, "c")
    category = devtools.evaluate(focused)
    expect(
        category["id"] == "probe-category",
        f"C declared on a select did not focus it: the focus is on {category['id']!r}",
    )
    return "/ put the caret in a filter with its text selected; C focused a select"


# The seeded project with the most items: 64 of them, "Candidate 1" onwards.
ITEMS_PATH = "/projects/switches-2026.pairrank/items"

# The debounce on the filter's input trigger, with room for the round trip and
# the refold after it.
FILTER_WAIT_S = 0.2 + CALLOUT_WAIT_S + REFOLD_WAIT_S


def type_filter(devtools: DevTools, text: str) -> None:
    """
    Put text in the Items filter the way typing does, and wait for the swap.

    Args:
        devtools: The CDP session.
        text: The whole new value of the field.
    """
    devtools.evaluate(
        f"""
        (() => {{
          const filter = document.getElementById("filter");
          filter.focus();
          filter.value = {text!r};
          filter.dispatchEvent(new Event("input", {{ bubbles: true }}));
          return true;
        }})()
        """
    )
    time.sleep(FILTER_WAIT_S)


def check_items_filter(devtools: DevTools, base: str) -> str:
    """
    Check the Items filter's real rows swap, end to end.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    retired_q = """
    (() => {
      const q = document.querySelector('#retired-cell input[name="q"]');
      return q ? q.value : "";
    })()
    """

    open_page(devtools, f"{base}{ITEMS_PATH}", *NARROW)
    start = state(devtools)
    expect(start["rowCount"] == 64, f"the sheet drew {start['rowCount']} items, not 64")

    press(devtools, "/")
    focused = devtools.evaluate('(document.activeElement || {}).id || ""')
    expect(focused == "filter", f"/ did not go to the filter: the focus is on {focused!r}")

    type_filter(devtools, "Candidate 1")
    narrowed = state(devtools)
    expect(
        narrowed["rowCount"] == 11,
        f"'Candidate 1' left {narrowed['rowCount']} rows, not 11 (1 and 10-19)",
    )
    expect(narrowed["rowsInField"] == 11, "the engine did not refold the swapped rows")
    expect(
        "q=Candidate" in devtools.evaluate("location.search"),
        "the filter did not replace the address, so a reload loses it",
    )
    expect(
        devtools.evaluate(retired_q) == "Candidate 1",
        "the retired toggle was not re-drawn with the filter it has to keep",
    )

    devtools.evaluate('window.sheet.select("item-10", { focus: false }), true')
    type_filter(devtools, "zzz")
    empty = state(devtools)
    expect(empty["emptyLead"].startswith("No items match"), "no empty state after a filter matching nothing")
    expect(empty["rowsInField"] == 0 and empty["rowCount"] == 0, "rows survived a filter matching nothing")
    expect(empty["selectedId"] is None, "the selection outlived the rows the filter took away")

    press(devtools, "Escape", in_field="#filter")
    time.sleep(FILTER_WAIT_S)
    cleared = state(devtools)
    expect(
        devtools.evaluate('document.getElementById("filter").value') == "",
        "Esc did not clear the filter, which the empty state promises it does",
    )
    expect(cleared["rowCount"] == 64, f"clearing the filter brought back {cleared['rowCount']} rows")
    return "/ took the filter; 64 rows to 11 to an empty state and back with Esc, address and toggle kept in step"


def wait_for_page(devtools: DevTools, condition: str, what: str) -> None:
    """
    Wait for a navigation a key started to land, and for the engine on it.

    Args:
        devtools: The CDP session.
        condition: A JavaScript expression true once the new page is the one
            expected - usually a test of ``location.search``.
        what: What was expected, for the failure message.

    Raises:
        CheckError: If it never arrives.
    """
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        # A page mid-navigation can have no document to evaluate in.
        try:
            arrived = devtools.evaluate(
                f'document.readyState === "complete" && !!window.sheet && ({condition})'
            )
        except CaptureError:
            arrived = False
        if arrived:
            time.sleep(CALLOUT_WAIT_S)
            return
        time.sleep(POLL_INTERVAL_S)
    raise CheckError(f"never landed on {what}")


# What the callout host holds: its label, and the id of the focused element.
CALLOUT = """
(() => {
  const callout = document.querySelector("#row-callout .bom-callout");
  return {
    label: callout ? callout.getAttribute("aria-label") : "",
    focused: (document.activeElement || {}).id || "",
    focusedText: ((document.activeElement || {}).textContent || "").trim(),
    last: document.getElementById("tb-last").textContent.trim(),
  };
})()
"""


def check_items_actions(devtools: DevTools, base: str) -> str:
    """
    Check the Items row actions by their keys and by the mouse, end to end.

    Adds an item, retires it and deletes it again, so the sheet ends as it
    began and ``items-filter`` still finds its 64 rows whichever order the two
    run in.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}{ITEMS_PATH}?selected=item-3", *NARROW)
    callout = devtools.evaluate(CALLOUT)
    expect(callout["label"] == "(3) Candidate 3", f"the selected row's callout is {callout['label']!r}")

    # Enter opens the edit form, focused on the name; Esc goes back to the row.
    press(devtools, "Enter")
    callout = devtools.evaluate(CALLOUT)
    expect(callout["label"] == "Edit (3) Candidate 3", f"Enter opened {callout['label']!r}")
    expect(callout["focused"] == "f-name", f"the edit form left the focus on {callout['focused']!r}")
    press(devtools, "Escape")
    wait_for_page(devtools, 'location.search === "?selected=item-3"', "the row after Cancel")
    focused_row = devtools.evaluate(
        '(document.activeElement && document.activeElement.dataset.id) || ""'
    )
    expect(focused_row == "item-3", f"Cancel returned the focus to {focused_row!r}, not the row")

    # The mouse: the Replace cell opens its form in the same host.
    devtools.evaluate('document.querySelector("#row-callout [data-action=replace]").click(), true')
    time.sleep(CALLOUT_WAIT_S)
    callout = devtools.evaluate(CALLOUT)
    expect(callout["label"] == "Replace (3) Candidate 3", f"clicking Replace opened {callout['label']!r}")

    # N: the ghost row and the Add form; Enter (declared on Save) posts it. The
    # Replace form is closed first: while a form is open, N is not pressed.
    press(devtools, "Escape")
    wait_for_page(devtools, 'location.search === "?selected=item-3"', "the row after Cancel")
    devtools.evaluate("document.activeElement.blur(), true")
    press(devtools, "n")
    wait_for_page(devtools, 'location.search.includes("form=new")', "the Add form")
    expect(devtools.evaluate("window.sheet.selectedId") == "__new", "N did not select the ghost row")
    callout = devtools.evaluate(CALLOUT)
    expect(callout["focused"] == "f-name", f"the Add form left the focus on {callout['focused']!r}")
    devtools.evaluate(
        'document.getElementById("f-name").value = "Driven item", '
        'document.getElementById("f-name").blur(), true'
    )
    press(devtools, "Enter")
    wait_for_page(devtools, 'location.search.includes("done=added")', "the added item")
    added = devtools.evaluate("window.sheet.selectedId")
    expect(bool(added) and added != "__new", f"the new item was not selected: {added!r}")
    expect(
        devtools.evaluate(CALLOUT)["last"].startswith("Added Driven item"),
        "Last change does not name the added item",
    )

    # R retires it at once, and the selection moves to the row before it.
    press(devtools, "r")
    wait_for_page(devtools, 'location.search.includes("done=retired")', "the retired item")
    after_retire = state(devtools)
    expect(added not in after_retire["ids"], "the retired item is still drawn with retired items hidden")
    expect(after_retire["selectedId"] == "item-64", f"Retire left {after_retire['selectedId']!r} selected")

    # Del asks, Del again deletes: back to the 64 the sheet started with.
    open_page(devtools, f"{base}{ITEMS_PATH}?retired=1&selected={added}", *NARROW)
    press(devtools, "a")
    callout = devtools.evaluate(CALLOUT)
    expect(callout["label"] == "Reactivate Driven item", f"A opened {callout['label']!r}")
    expect(callout["focused"] == "f-slot", f"Reactivate left the focus on {callout['focused']!r}")
    press(devtools, "Escape")
    wait_for_page(devtools, f'location.search.includes("selected={added}")', "the row after Cancel")
    press(devtools, "Delete")
    callout = devtools.evaluate(CALLOUT)
    expect(callout["label"] == "Delete Driven item", f"Del opened {callout['label']!r}")
    expect(callout["focusedText"].startswith("Delete"), "the confirmation did not focus Delete")
    press(devtools, "Delete")
    wait_for_page(devtools, 'location.search.includes("done=deleted")', "the sheet after Delete")
    end = state(devtools)
    expect(end["rowCount"] == 64 and added not in end["ids"], f"Delete left {end['rowCount']} rows")
    return "Enter/Esc, a click on Replace, N and Enter to add, R to retire, A to reactivate, Del Del to delete; focus and selection where the brief puts them"


# The mockups' own project (seed_capture_data.py), whose rows carry
# descriptions and whose edit form is taller than the space a 1280 sheet leaves
# between a row near the top and the title block.
SAMPLE_ITEMS_PATH = "/projects/switches-sample.pairrank/items"

# Where the selected row and its callout are, and the table they belong to.
PLACEMENT = """
(() => {
  const tr = document.querySelector('.bom-field tr[aria-selected="true"]');
  const callout = document.querySelector("#row-callout .bom-callout");
  if (!tr || !callout) return null;
  const row = tr.getBoundingClientRect();
  const box = callout.getBoundingClientRect();
  return {
    rowBottom: row.bottom,
    tableRight: tr.closest("table").getBoundingClientRect().right,
    top: box.top,
    right: box.right,
    above: callout.classList.contains("is-above"),
  };
})()
"""


def check_callout_place(devtools: DevTools, base: str) -> str:
    """
    Check that a tall callout stays off its own row, and inside a phone's table.

    At 1280 the Items edit form on the third row of a sheet fits neither below
    its row within the column (the title block is in the way) nor above it.
    It goes below the row, over the title block, as the mockup draws it: the
    bug this pins slid it up over its own row, leader and all. On a phone the
    callout's right edge is the table's right rule less the edge, not the
    drawing area's.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    url = f"{base}{SAMPLE_ITEMS_PATH}?form=edit&item=it1"
    open_page(devtools, url, *NARROW)
    placed = devtools.evaluate(PLACEMENT)
    expect(placed is not None, "the edit form never arrived under its row")
    expect(
        not placed["above"] and placed["top"] >= placed["rowBottom"],
        f"the edit form's top is at {placed['top']:.0f}, over its row, which ends at "
        f"{placed['rowBottom']:.0f}",
    )
    narrow = placed

    open_page(devtools, url, *PHONE)
    placed = devtools.evaluate(PLACEMENT)
    expect(placed is not None, "the edit form never arrived on the phone")
    expect(
        placed["right"] < placed["tableRight"],
        f"the phone callout ends at {placed['right']:.0f}, past the table's rule at "
        f"{placed['tableRight']:.0f}",
    )
    return (
        f"1280: form {narrow['top'] - narrow['rowBottom']:.0f} px below its row; "
        f"390: {placed['tableRight'] - placed['right']:.0f} px inside the table's rule"
    )


def check_form_verbs(devtools: DevTools, base: str) -> str:
    """
    Check that a sheet's verbs are not pressed while a form is open.

    With the focus outside the form's fields - the person clicked its padding -
    N and H used to press the title block's Add and Retired, leaving the page
    with the draft. The form's own keys still work: Esc cancels it, and with
    only the actions open N adds again. The register's I is checked too,
    because the rule is the engine's.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    kept = """
    (() => ({
      search: location.search,
      draft: (document.getElementById("f-name") || {}).value || "",
    }))()
    """

    open_page(devtools, f"{base}{ITEMS_PATH}?form=edit&item=item-3", *NARROW)
    expect(
        devtools.evaluate(CALLOUT)["label"] == "Edit (3) Candidate 3",
        "the edit form did not open from its address",
    )
    devtools.evaluate(
        'document.getElementById("f-name").value = "Draft kept", '
        "document.activeElement.blur(), true"
    )
    start = devtools.evaluate(kept)
    for key in ("n", "h"):
        press(devtools, key)
        now = devtools.evaluate(kept)
        expect(
            now == start,
            f"{key.upper()} with the edit form open left {start} for {now}",
        )

    press(devtools, "Escape")
    wait_for_page(devtools, 'location.search === "?selected=item-3"', "the row after Cancel")
    devtools.evaluate("document.activeElement.blur(), true")
    press(devtools, "n")
    wait_for_page(devtools, 'location.search.includes("form=new")', "the Add form after Cancel")

    open_page(devtools, f"{base}/?form=new&name=Draft%20name", *NARROW)
    devtools.evaluate("document.activeElement.blur(), true")
    before = devtools.evaluate("location.search")
    press(devtools, "i")
    after = devtools.evaluate("location.search")
    expect(before == after, f"I with the register's New form open went from {before} to {after}")
    return "N and H ignored over an Items edit form, I over the register's New form; Esc then N still work"


CHECKS = {
    "fold": check_fold,
    "swap-empty": check_swap_empty,
    "swap-fewer": check_swap_fewer,
    "page-then-arrow": check_page_then_arrow,
    "escape-in-field": check_escape_in_field,
    "autofocus-select": check_autofocus_select,
    "key-on-fixed": check_key_on_fixed,
    "short-window": check_short_window,
    "aria": check_aria,
    "key-on-field": check_key_on_field,
    "items-filter": check_items_filter,
    "items-actions": check_items_actions,
    "callout-place": check_callout_place,
    "form-verbs": check_form_verbs,
}


# --------------------------------------------------------------------------
# Running them
# --------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    """
    Boot the app and Chrome, run the checks, and tear it all down.

    Args:
        args: The parsed command line.

    Returns:
        int: 0 when every check passed.
    """
    scratch = None
    if args.data_dir:
        data_dir = windows_path(args.data_dir)
        if not Path(data_dir).is_dir():
            raise CheckError(f"no such data directory: {data_dir}")
    else:
        scratch = scratch_dir("pairrank-drive-")
        written = seed(Path(scratch))
        data_dir = scratch
        print(f"{PROGRAM}: seeded {written} projects in {data_dir}")

    names = args.checks or list(CHECKS)
    server = None
    chrome = None
    devtools = None
    profile_dir = scratch_dir("pairrank-drive-profile-")
    failures = 0

    try:
        server = start_server(data_dir, args.port)
        base = f"http://127.0.0.1:{args.port}"
        print(f"{PROGRAM}: serving {data_dir} at {base}")
        chrome, devtools = start_chrome(profile_dir)

        for name in names:
            try:
                note = CHECKS[name](devtools, base)
            except CaptureError as e:
                failures += 1
                print(f"{PROGRAM}: FAIL {name}: {e}", file=sys.stderr)
            else:
                print(f"{PROGRAM}: ok   {name}: {note}")
    finally:
        if devtools is not None:
            devtools.close()
        if chrome is not None:
            stop_process(chrome)
        if server is not None:
            stop_process(server)
        shutil.rmtree(profile_dir, ignore_errors=True)
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)

    print(f"{PROGRAM}: {len(names) - failures} of {len(names)} checks passed")
    return 1 if failures else 0


def main(argv: list = None) -> int:
    """
    Parse the command line and run.

    Args:
        argv: Arguments, defaulting to the process's.

    Returns:
        int: 0 when every check passed, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Drive src/web/static/js/sheet.js in Chrome and check it.",
    )
    parser.add_argument(
        "--data-dir",
        help=(
            "a seeded PAIRRANK_DATA_DIR to boot against; without it a scratch "
            "one is seeded and removed again"
        ),
    )
    parser.add_argument(
        "--check",
        dest="checks",
        action="append",
        choices=sorted(CHECKS),
        help="run one check, repeatable (default: all of them)",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="dev port (default: 8098)"
    )
    args = parser.parse_args(argv)

    try:
        return run(args)
    except CaptureError as e:
        print(f"{PROGRAM}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
