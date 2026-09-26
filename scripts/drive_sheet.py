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

``form-once``
    The form a page address opens (``form=delete&item=X``) is the arriving
    selection's callout only: X selected again shows its actions. The
    ``form=new`` ghost row goes once another row is selected.

``filter-callout``
    A selected row the filter keeps gets a callout for the new view - its
    Retire form and Edit carry the new filter - and an open edit form closes
    into the row's actions.

``filter-enter``
    Enter in the filter, pressed inside its 200 ms delay, waits for the new
    rows and selects the first of them, not the first of the old ones.

``compare-keys``
    Not the folding engine: the Compare sheet's own keys
    (``static/js/compare.js``), which live outside the frame htmx swaps. ``2``
    votes and the frame is swapped in place with the address following, the
    station marked across the swap (and unmarked when its 420 ms are up) and
    the new revision announced; Ctrl+Z
    undoes it and the pair comes back on its sides; a held key's repeat votes
    nothing, and ``S`` moves on without a vote, to a pair other than the one
    it was pressed on.

``compare-notice``
    The changed-on-disk notice, which sits outside the frame htmx swaps: with
    the project file saved behind the server's back, a vote's swap brings the
    strip in out of band, the next vote's swap puts it away, and Dismiss hides
    it without a navigation. It undoes its votes.

``compare-double``
    A second press in the 140 ms between a vote's answer and its new frame -
    ``5`` 30 ms after ``2``'s answer, a station clicked twice - records
    nothing: the file gains one vote, the page's count is the file's, the
    address names the pair the vote form posts, and the new frame lands with
    station 2 alone marked. It undoes its votes.

``compare-error``
    A vote the server answers with an error page shows that page: the project
    file is deleted behind the server's back, ``2`` lands on "Not found", and
    the file is put back.

``items-error``
    The engine's own GETs answered with an error show the error page: the
    Items project file is deleted behind the server's back, a row is clicked,
    its callout's 404 makes sheet.js load the sheet's address again, that
    lands on "Not found" (which does not boot the engine), and the file is put
    back. Then a callout for an item that does not exist, fetched twice on a
    sheet that draws, reloads the page once and the second time only says so
    in the status region.

``rankings-keys``
    The Rankings sheet on ``switches-sample``: an arrow selects without
    opening the detail, Enter opens it and closes it again, arrows carry an
    open detail to the next row, a click opens a row's detail and a second
    click closes it with the selection, Esc deselects; C goes to the category,
    choosing one swaps the rows and carries the export cell, H shows retired
    items keeping the category, and X submits the export form with the whole
    view, whose answer is a CSV with as many rows as the sheet draws.

``settings-keys``
    The Settings sheet on ``switches-sample-settings`` (settings.js, not the
    engine): typing marks a changed value with the triangle and the Status
    cell names it, a value typed back to the saved one is no change, a value
    out of range shows the server's sentence and disables Save, Ctrl+S is
    taken from the browser and with a value to fix puts the caret in it, Esc
    leaves a field, Reset fills the defaults in place and leaves the slots
    alone, and Ctrl+S then saves and lands on "Saved.". The file is put back.

``settings-slots``
    The Settings slot table on the same project: typing the list redraws the
    board, marks a repeated slot and warns of it, flags two slots drawn alike
    without blocking Save; a label typed on a tile that another slot shows is
    refused with the server's sentence and Ctrl+S focuses that tile; a free
    label clears the collision and Ctrl+S saves the list and the label. The
    file is put back.

Each check leaves the page as it found it by navigating afresh, so they are
independent and ``--check`` can run any one of them alone.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs


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


def check_form_once(devtools: DevTools, base: str) -> str:
    """
    Check that the form a page address opens is opened once, not for good.

    ``form=delete&item=X`` arrives on X's delete question. Select another row
    and then X again: X shows its actions, where the bug this pins asked the
    question again, with Delete focused. And ``form=new``'s ghost row goes as
    soon as another row is selected.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}{ITEMS_PATH}?form=delete&item=item-3", *NARROW)
    first = devtools.evaluate(CALLOUT)["label"]
    expect(first == "Delete (3) Candidate 3", f"the address opened {first!r}")
    for row in ("item-4", "item-3"):
        devtools.evaluate(f'window.sheet.select("{row}"), true')
        time.sleep(CALLOUT_WAIT_S)
    again = devtools.evaluate(CALLOUT)["label"]
    expect(again == "(3) Candidate 3", f"selecting the row again opened {again!r}, not its actions")

    open_page(devtools, f"{base}{ITEMS_PATH}?form=new", *NARROW)
    ghost = state(devtools)
    expect(ghost["selectedId"] == "__new" and "__new" in ghost["ids"], "form=new drew no ghost row")
    devtools.evaluate('window.sheet.select("item-3"), true')
    time.sleep(CALLOUT_WAIT_S)
    after = state(devtools)
    expect("__new" not in after["ids"], "the ghost row outlived its selection")
    expect(after["rowCount"] == 64, f"the engine holds {after['rowCount']} rows, not 64")
    expect(
        devtools.evaluate(CALLOUT)["label"] == "(3) Candidate 3",
        "the row selected after the ghost did not show its actions",
    )
    return f"{first!r} once, then the row's actions; the ghost row gone with its selection"


# The view the open callout carries back: its Retire form's filter, its label,
# and the address its first action cell (Edit) asks for.
CALLOUT_VIEW = """
(() => {
  const callout = document.querySelector("#row-callout .bom-callout");
  const q = document.querySelector('#row-callout input[name="q"]');
  const edit = document.querySelector("#row-callout [hx-get]");
  return {
    label: callout ? callout.getAttribute("aria-label") : "",
    retireQ: q ? q.value : "",
    editUrl: edit ? edit.getAttribute("hx-get") : "",
  };
})()
"""


def check_filter_callout(devtools: DevTools, base: str) -> str:
    """
    Check that a row kept through a filter gets a callout for the new view.

    The callout is built for the view it was fetched under: its action cells,
    its Retire form and a form's Save and Cancel all carry the filter back.
    Kept across a filter, the bug this pins retired with no ``q`` and the 303
    dropped the filter. An open edit form closes into the row's actions, as
    the mockup closes it on filter input.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}{ITEMS_PATH}?selected=item-10", *NARROW)
    before = devtools.evaluate(CALLOUT_VIEW)
    expect(before["label"] == "(10) Candidate 10", f"the arriving callout is {before['label']!r}")
    expect(before["retireQ"] == "", "the unfiltered callout carries a filter")

    type_filter(devtools, "Candidate 1")
    after = devtools.evaluate(CALLOUT_VIEW)
    expect(devtools.evaluate("window.sheet.selectedId") == "item-10", "the filter dropped a row it keeps")
    expect(after["label"] == "(10) Candidate 10", f"the kept row's callout is {after['label']!r}")
    expect(
        after["retireQ"] == "Candidate 1",
        f"the kept row's Retire form carries q={after['retireQ']!r}, not the filter",
    )
    expect("q=Candidate" in after["editUrl"], f"its Edit asks for {after['editUrl']!r}")

    devtools.evaluate("document.activeElement.blur(), true")
    press(devtools, "Enter")
    expect(
        devtools.evaluate(CALLOUT)["label"] == "Edit (10) Candidate 10",
        "Enter did not open the edit form",
    )
    type_filter(devtools, "Candidate 10")
    closed = devtools.evaluate(CALLOUT_VIEW)
    expect(
        closed["label"] == "(10) Candidate 10" and closed["retireQ"] == "Candidate 10",
        f"after the filter the edit form left {closed}",
    )
    return "the kept row's actions re-fetched with the filter; an open edit form closed into them"


def check_filter_enter(devtools: DevTools, base: str) -> str:
    """
    Check Enter in the filter, pressed before and after its rows arrive.

    Typed faster than the filter's 200 ms delay, the rows on the sheet are the
    previous view's. The bug this pins selected the first of those, then the
    swap took it away: no selection, and the focus on ``<body>``. Enter now
    sends the request at once and selects the first row of what it brings.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    focused_row = '(document.activeElement && document.activeElement.dataset.id) || ""'

    open_page(devtools, f"{base}{ITEMS_PATH}", *NARROW)
    # Typing and Enter in one go, well inside the delay. Unfiltered, the first
    # row is Candidate 1; "Candidate 2" starts at Candidate 2.
    devtools.evaluate(
        """
        (() => {
          const filter = document.getElementById("filter");
          filter.focus();
          filter.value = "Candidate 2";
          filter.dispatchEvent(new Event("input", { bubbles: true }));
          filter.dispatchEvent(new KeyboardEvent("keydown", {
            key: "Enter", bubbles: true, cancelable: true
          }));
          return true;
        })()
        """
    )
    time.sleep(FILTER_WAIT_S)
    fast = state(devtools)
    expect(fast["rowCount"] == 11, f"'Candidate 2' left {fast['rowCount']} rows, not 11")
    expect(fast["selectedId"] == "item-2", f"Enter inside the delay selected {fast['selectedId']!r}")
    expect(devtools.evaluate(focused_row) == "item-2", "the focus did not land on the first match")
    expect(
        devtools.evaluate(CALLOUT)["label"] == "(2) Candidate 2",
        "the first match's callout did not arrive",
    )

    # Settled: the rows are the filter's, so Enter selects at once.
    devtools.evaluate('window.sheet.select("item-25", { focus: false }), true')
    time.sleep(CALLOUT_WAIT_S)
    press(devtools, "Enter", in_field="#filter")
    settled = state(devtools)
    expect(settled["selectedId"] == "item-2", f"Enter after the swap selected {settled['selectedId']!r}")
    expect(devtools.evaluate(focused_row) == "item-2", "the focus did not follow Enter to the row")
    return "Enter inside the delay waited for its rows and chose Candidate 2; after it, at once"


# A project no other check counts on: the vote this check casts it also undoes,
# but the file's modified time moves either way.
COMPARE_PATH = "/projects/switches-sample-full.pairrank/compare"

# What the Compare checks read off the sheet, in one round trip. `swapped` is a
# marker set on the window before a key is pressed: still there afterwards, the
# page was swapped in place by htmx rather than loaded again.
COMPARE_STATE = """
(() => {
  const text = (el) => (el ? el.textContent.replace(/\\s+/g, " ").trim() : "");
  const rows = Array.from(document.querySelectorAll("#rev-rows .rev-row"));
  return {
    search: location.search,
    swapped: window.__driveMarker === 1,
    votes: text(document.getElementById("votes")),
    latest: rows.length ? rows[rows.length - 1].className + " | " + text(rows[rows.length - 1]) : "",
    marked: Array.from(document.querySelectorAll(".station.is-marked"), (el) => el.dataset.key),
    status: text(document.getElementById("callout-status")),
    nameA: text(document.getElementById("name-a")),
  };
})()
"""


def compare_key(devtools: DevTools, key: str, ctrl: bool = False, repeat: bool = False) -> None:
    """
    Press a key on the Compare sheet, as the browser sends it to the page.

    Args:
        devtools: The CDP session.
        key: A UI Events key value.
        ctrl: Whether Control is held.
        repeat: Whether it is an auto-repeat of a held key.
    """
    devtools.evaluate(
        f"""
        (() => {{
          (document.activeElement || document.body).dispatchEvent(new KeyboardEvent("keydown", {{
            key: "{key}", ctrlKey: {str(ctrl).lower()}, repeat: {str(repeat).lower()},
            bubbles: true, cancelable: true
          }}));
          return true;
        }})()
        """
    )


def wait_for_compare(devtools: DevTools, condition: str, what: str) -> dict:
    """
    Wait until the Compare sheet satisfies a condition, and read it.

    Args:
        devtools: The CDP session.
        condition: A JavaScript expression over the page.
        what: What was expected, for the failure message.

    Returns:
        dict: The sheet's state once it holds.

    Raises:
        CheckError: If it never does.
    """
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            arrived = devtools.evaluate(
                f'document.readyState === "complete" && !!window.htmx && ({condition})'
            )
        except CaptureError:
            arrived = False
        if arrived:
            return devtools.evaluate(COMPARE_STATE)
        time.sleep(POLL_INTERVAL_S)
    raise CheckError(f"never saw {what}")


def check_compare_keys(devtools: DevTools, base: str) -> str:
    """
    Check the Compare keys end to end: a vote, its undo, a held key and Skip.

    ``2`` votes A better through htmx and the frame is swapped in place, the
    address following the redirect; the receipt's new row is said in the
    status region and the station is marked. Ctrl+Z takes it back, the pair
    returning on the sides it was drawn on. A held key's repeats vote nothing,
    and ``S`` moves on without a vote. The vote is undone, so the project ends
    with the votes it began with.
    """
    size(devtools, *NARROW)
    devtools.call("Page.navigate", {"url": f"{base}{COMPARE_PATH}?a=it1&b=it2"})
    before = wait_for_compare(devtools, 'document.getElementById("station-2")', "the Compare sheet")
    expect(before["nameA"] == "Gateron Oil King", f"View A drew {before['nameA']!r}")
    devtools.evaluate("window.__driveMarker = 1, true")

    compare_key(devtools, "2")
    # The address follows the redirect before the new frame has settled, and
    # compare.js does its post-swap work (the mark, the status) on htmx:load,
    # which fires at settle; so wait for that work, not just the address.
    voted = wait_for_compare(
        devtools,
        'location.search.includes("done=voted")'
        ' && document.getElementById("callout-status").textContent.includes("over")',
        "the vote land",
    )
    expect(voted["swapped"], "the vote reloaded the page instead of swapping the frame")
    expect(int(voted["votes"]) == int(before["votes"]) + 1, f"votes went {before['votes']} -> {voted['votes']}")
    expect(
        "is-new" in voted["latest"] and "Gateron Oil King over Cherry MX Black" in voted["latest"],
        f"the receipt's latest row is {voted['latest']!r}",
    )
    expect(voted["marked"] == ["2"], f"station 2 was not marked across the swap: {voted['marked']}")
    expect("Gateron Oil King over" in voted["status"], f"the status region said {voted['status']!r}")
    time.sleep(CALLOUT_WAIT_S)
    faded = devtools.evaluate(COMPARE_STATE)["marked"]
    expect(faded == [], f"the mark outlived its 420 ms on the swapped-in frame: {faded}")

    compare_key(devtools, "z", ctrl=True)
    undone = wait_for_compare(devtools, 'location.search.includes("done=undone")', "the undo land")
    expect(undone["swapped"], "the undo reloaded the page")
    expect(undone["votes"] == before["votes"], f"votes after the undo: {undone['votes']}")
    expect("a=it1&b=it2" in undone["search"], f"the undone pair came back as {undone['search']!r}")
    expect(
        "is-undone" in undone["latest"] and "pair re-offered" in undone["latest"],
        f"the receipt's latest row is {undone['latest']!r}",
    )

    compare_key(devtools, "3", repeat=True)
    time.sleep(CALLOUT_WAIT_S)
    held = devtools.evaluate(COMPARE_STATE)
    expect(held["search"] == undone["search"], "a held key's repeat voted")

    compare_key(devtools, "s")
    skipped = wait_for_compare(devtools, '!location.search.includes("done=")', "Skip land")
    expect(skipped["swapped"], "Skip reloaded the page")
    expect(skipped["votes"] == before["votes"], f"Skip recorded a vote: {skipped['votes']}")
    landed = parse_qs(skipped["search"].lstrip("?"))
    expect(
        {landed.get("a", [""])[0], landed.get("b", [""])[0]} != {"it1", "it2"},
        f"Skip offered the pair it was pressed on again: {skipped['search']!r}",
    )
    return "2 voted and swapped the frame, marked and announced; Ctrl+Z put it back on its sides; a repeat voted nothing and S moved to another pair"


# The data directory the server was booted on, for the one check that has to
# play "another program" and write a project file behind the server's back.
# Set by run() before any check runs.
DATA_DIR = {"path": None}

# What the notice check reads: the strip's state, the address, and whether the
# page was swapped rather than loaded.
NOTICE_STATE = """
(() => {
  const notice = document.getElementById("notice");
  return {
    search: location.search,
    swapped: window.__driveMarker === 1,
    shown: !!notice && !notice.hidden,
    text: notice ? notice.textContent.replace(/\\s+/g, " ").trim() : "",
    status: (document.getElementById("callout-status") || {}).textContent || "",
  };
})()
"""


def save_elsewhere(file_name: str) -> None:
    """
    Write a project file again, byte for byte, as another program saving it would.

    The content is unchanged; the stamp is not, which is all the registry's
    check looks at.

    Args:
        file_name: The project's file name in the data directory.
    """
    path = Path(DATA_DIR["path"]) / file_name
    data = path.read_bytes()
    time.sleep(0.05)
    path.write_bytes(data)


def check_compare_notice(devtools: DevTools, base: str) -> str:
    """
    Check the changed-on-disk notice through htmx, which swaps only the frame.

    The file is saved behind the server's back and ``2`` votes: the page the
    frame is swapped in from carries the notice strip out of band, so it shows
    without a reload. The next vote's page puts it away again. Saved behind
    its back once more, the strip shows and Dismiss hides it where it is. The
    three votes are undone.
    """
    size(devtools, *NARROW)
    devtools.call("Page.navigate", {"url": f"{base}{COMPARE_PATH}?a=it1&b=it2"})
    wait_for_compare(devtools, 'document.getElementById("station-2")', "the Compare sheet")
    devtools.evaluate("window.__driveMarker = 1, true")
    file_name = COMPARE_PATH.split("/")[2]

    def vote_and_read(count: int) -> dict:
        # Waits for the vote's row in the status region, which compare.js
        # writes on htmx:load - after the frame and the strip have settled.
        compare_key(devtools, "2")
        wait_for_compare(
            devtools,
            f'location.search.includes("done=voted") && document.getElementById("votes").textContent.trim() === "{count}"'
            f' && document.getElementById("callout-status").textContent.includes("R{count} ")',
            "the vote land",
        )
        return devtools.evaluate(NOTICE_STATE)

    start = int(devtools.evaluate(COMPARE_STATE)["votes"])
    expect(not devtools.evaluate(NOTICE_STATE)["shown"], "the notice showed before anything changed")

    save_elsewhere(file_name)
    first = vote_and_read(start + 1)
    expect(first["swapped"], "the vote reloaded the page instead of swapping the frame")
    expect(first["shown"], "the notice did not come in with the swap")
    expect("saved by another program" in first["text"], f"the notice said {first['text']!r}")
    expect("File changed on disk" in first["status"], f"the status region said {first['status']!r}")

    second = vote_and_read(start + 2)
    expect(not second["shown"], "the notice stayed up after the next vote")

    save_elsewhere(file_name)
    third = vote_and_read(start + 3)
    expect(third["shown"], "the second change on disk was not announced")
    devtools.evaluate('document.getElementById("notice-dismiss").click(), true')
    dismissed = devtools.evaluate(NOTICE_STATE)
    expect(not dismissed["shown"], "Dismiss left the notice up")
    expect(
        dismissed["swapped"] and dismissed["search"] == third["search"],
        "Dismiss navigated instead of hiding the strip",
    )

    for count in (start + 2, start + 1, start):
        compare_key(devtools, "z", ctrl=True)
        wait_for_compare(
            devtools,
            f'location.search.includes("done=undone") && document.getElementById("votes").textContent.trim() === "{count}"',
            "the undo land",
        )
    return "a vote over a file saved elsewhere swapped the notice in; the next vote put it away; Dismiss hid it in place"


# What the double-press check compares: the page's vote count and pair against
# the file's and the address's.
DOUBLE_STATE = """
(() => {
  const field = (name) => (document.querySelector('#vote-form input[name="' + name + '"]') || {}).value;
  const query = new URLSearchParams(location.search);
  return {
    votes: document.getElementById("votes").textContent.trim(),
    addressed: [query.get("a"), query.get("b")],
    posted: [field("a"), field("b")],
  };
})()
"""


def stored_votes(file_name: str) -> int:
    """
    Count the votes in a project file as it is on disk.

    Args:
        file_name: The project's file name in the data directory.

    Returns:
        int: How many votes the file holds.
    """
    path = Path(DATA_DIR["path"]) / file_name
    return len(json.loads(path.read_text(encoding="utf-8"))["votes"])


def check_compare_double(devtools: DevTools, base: str) -> str:
    """
    Check that a second press before the new pair is in records nothing.

    htmx lets go of a request when its answer arrives, before the delayed swap
    has put the next pair in; for those 140 ms the old frame's stations are
    still on screen. A key pressed 30 ms after the answer, and a station
    clicked twice in the same window, must each leave exactly one vote in the
    file, the page's count equal to the file's, the address naming the pair
    the vote form posts, and only the first press's station marked as the new
    frame lands. Both votes are undone.
    """
    size(devtools, *NARROW)
    file_name = COMPARE_PATH.split("/")[2]
    start = stored_votes(file_name)

    def second_press(first: str, then: str) -> dict:
        devtools.call("Page.navigate", {"url": f"{base}{COMPARE_PATH}?a=it1&b=it2"})
        wait_for_compare(devtools, 'document.getElementById("station-2")', "the Compare sheet")
        count = stored_votes(file_name)
        devtools.evaluate(
            f"""
            (() => {{
              window.__markedOnLoad = null;
              document.addEventListener("htmx:load", (event) => {{
                if (event.target.id === "frame" && window.__markedOnLoad === null)
                  window.__markedOnLoad = Array.from(
                    document.querySelectorAll(".station.is-marked"), (station) => station.dataset.key
                  );
              }});
              document.addEventListener("htmx:afterRequest", () => setTimeout(() => {{ {then} }}, 30), {{ once: true }});
              {first}
              return true;
            }})()
            """
        )
        wait_for_compare(
            devtools,
            'location.search.includes("done=voted")'
            ' && document.getElementById("callout-status").textContent.includes("over")',
            "the vote land",
        )
        # Past the second press, and past any vote it could have started.
        time.sleep(CALLOUT_WAIT_S)
        state = devtools.evaluate(DOUBLE_STATE)
        # The refused press marks nothing, so the new pair lands carrying
        # the first press's mark alone.
        marked = devtools.evaluate("window.__markedOnLoad")
        expect(marked == ["2"], f"the new frame landed with stations {marked} marked")
        stored = stored_votes(file_name)
        expect(stored == count + 1, f"the file went from {count} to {stored} votes")
        expect(int(state["votes"]) == stored, f"the page reads {state['votes']} votes, the file {stored}")
        expect(
            state["addressed"] == state["posted"],
            f"the address names {state['addressed']}, the vote form posts {state['posted']}",
        )
        return state

    key = (
        '(document.activeElement || document.body).dispatchEvent(new KeyboardEvent("keydown",'
        ' {{ key: "{0}", bubbles: true, cancelable: true }}));'
    )
    second_press(key.format("2"), key.format("5"))
    second_press(
        'document.getElementById("station-2").click();',
        'document.getElementById("station-2").click();',
    )

    for count in (start + 1, start):
        compare_key(devtools, "z", ctrl=True)
        wait_for_compare(
            devtools,
            f'location.search.includes("done=undone") && document.getElementById("votes").textContent.trim() === "{count}"',
            "the undo land",
        )
    return "a key 30 ms after the answer, and a second click, each left one vote; page, file and address agree"


def check_compare_error(devtools: DevTools, base: str) -> str:
    """
    Check that a vote the server refuses with an error page shows that page.

    htmx swaps no 4xx answer, so without compare.js's handler a vote over a
    deleted project did nothing and said nothing. The file is taken away
    behind the server's back, ``2`` is pressed, and the not-found page must be
    what the browser shows. The file is put back afterwards.
    """
    size(devtools, *NARROW)
    file_name = COMPARE_PATH.split("/")[2]
    path = Path(DATA_DIR["path"]) / file_name
    devtools.call("Page.navigate", {"url": f"{base}{COMPARE_PATH}?a=it1&b=it2"})
    wait_for_compare(devtools, 'document.getElementById("station-2")', "the Compare sheet")
    saved = path.read_bytes()
    path.unlink()
    try:
        compare_key(devtools, "2")
        deadline = time.monotonic() + READY_TIMEOUT_S
        shown = ""
        while time.monotonic() < deadline:
            try:
                shown = devtools.evaluate(
                    'document.readyState === "complete" && !document.getElementById("station-2")'
                    ' ? document.title : ""'
                )
            except CaptureError:
                shown = ""
            if shown:
                break
            time.sleep(POLL_INTERVAL_S)
        page = devtools.evaluate(
            '({ href: location.href, title: document.title, sheet: !!document.getElementById("station-2") })'
        )
        expect("Not found" in shown, f"the error page never showed: {page}")
    finally:
        path.write_bytes(saved)
    return "a vote over a deleted project showed the not-found page"


def check_items_error(devtools: DevTools, base: str) -> str:
    """
    Check that a row whose callout the server refuses shows the error page.

    htmx swaps no 4xx answer, so without sheet.js's handler a click on a row
    of a project deleted behind the server's back selected the row, fetched
    nothing and said nothing. The file is taken away, a row is clicked, and
    the not-found page must be what the browser shows: the engine loads the
    sheet's own address again, which the server answers with that page. The
    file is put back afterwards.
    """
    file_name = ITEMS_PATH.split("/")[2]
    path = Path(DATA_DIR["path"]) / file_name
    open_page(devtools, f"{base}{ITEMS_PATH}", *NARROW)
    saved = path.read_bytes()
    path.unlink()
    try:
        devtools.evaluate('document.querySelector("tr[data-id=item-5]").click(), true')
        deadline = time.monotonic() + READY_TIMEOUT_S
        shown = ""
        while time.monotonic() < deadline:
            try:
                shown = devtools.evaluate(
                    'document.readyState === "complete" && !document.querySelector(".bom-field")'
                    ' ? document.title : ""'
                )
            except CaptureError:
                shown = ""
            if shown:
                break
            time.sleep(POLL_INTERVAL_S)
        # Not window.sheet: the error page's #sheet element answers to that name.
        page = devtools.evaluate(
            '({ href: location.href, title: document.title,'
            ' engine: Array.from(document.scripts).some((s) => s.src.endsWith("/sheet.js")) })'
        )
        expect("Not found" in shown, f"the error page never showed: {page}")
        expect(not page["engine"], f"the error page loads the engine, which could reload it again: {page}")
    finally:
        path.write_bytes(saved)

    # A fragment that fails on a page that still draws reloads it once, not
    # for ever: the second failure straight after says so in the status region.
    # Another address, because the guard remembers the one reloaded above.
    open_page(devtools, f"{base}{ITEMS_PATH}?selected=item-2", *NARROW)
    missing = f'htmx.ajax("GET", "{ITEMS_PATH}/no-such-item/callout", {{ target: "#row-callout" }})'
    devtools.evaluate(f"window.__beforeReload = true, {missing}, true")
    wait_for_page(devtools, "!window.__beforeReload", "the sheet loaded again after a 404")
    devtools.evaluate(f"window.__beforeReload = true, {missing}, true")
    time.sleep(2 * CALLOUT_WAIT_S)
    after = devtools.evaluate(
        '({ kept: window.__beforeReload === true,'
        ' status: document.getElementById("callout-status").textContent })'
    )
    expect(after["kept"], "a second 404 straight after the reload loaded the page again")
    expect("could not answer" in after["status"], f"the status region says {after['status']!r}")
    return "a row clicked in a deleted project showed the not-found page; a repeated fragment 404 reloaded once and then said so"


SAMPLE_RANKINGS_PATH = "/projects/switches-sample.pairrank/rankings"

# The selected row and what the callout host holds on the Rankings sheet.
RANKINGS = """
(() => {
  const callout = document.querySelector("#row-callout .bom-callout");
  const host = document.getElementById("row-callout");
  return {
    selectedId: window.sheet.selectedId,
    ids: Array.from(document.querySelectorAll(".bom-field tr[data-id]"), (tr) => tr.dataset.id),
    detail: !!(host && !host.hidden && callout && callout.querySelector(".strip-detail")),
    label: callout ? callout.getAttribute("aria-label") : "",
    focused: (document.activeElement || {}).id || "",
  };
})()
"""


def check_rankings_keys(devtools: DevTools, base: str) -> str:
    """
    Check the Rankings sheet's keys and its detail callout.

    The detail opens on a click and toggles with Enter, arrows carry it while
    it is open, and Esc or a second click closes it with the selection - the
    mockup's rules, kept by the page's boot script on top of the engine. Then
    C goes to the category, a category swaps the rows and carries the export
    cell, H shows retired items keeping the category, and X presses the
    export form with the view.

    Args:
        devtools: The CDP session.
        base: The server's base URL.

    Returns:
        str: What was measured, for the log.
    """
    open_page(devtools, f"{base}{SAMPLE_RANKINGS_PATH}", *NARROW)
    start = devtools.evaluate(RANKINGS)
    expect(len(start["ids"]) > 2, f"the sheet drew {len(start['ids'])} rows")
    first, second, third = start["ids"][:3]

    press(devtools, "ArrowDown")
    moved = devtools.evaluate(RANKINGS)
    expect(moved["selectedId"] == first, f"ArrowDown selected {moved['selectedId']!r}, not {first!r}")
    expect(not moved["detail"], "an arrow opened the detail, which only a click or Enter opens")

    press(devtools, "Enter")
    opened = devtools.evaluate(RANKINGS)
    expect(opened["detail"], "Enter did not open the selected row's detail")
    expect(opened["label"].startswith("#1 "), f"the first row's detail is labelled {opened['label']!r}")

    press(devtools, "ArrowDown")
    carried = devtools.evaluate(RANKINGS)
    expect(carried["selectedId"] == second, "ArrowDown did not move the selection")
    expect(
        carried["detail"] and carried["label"].startswith("#2 "),
        f"the open detail did not follow the selection: {carried['label']!r}",
    )

    press(devtools, "Enter")
    closed = devtools.evaluate(RANKINGS)
    expect(not closed["detail"], "Enter did not close the detail")
    expect(closed["selectedId"] == second, "closing the detail dropped the selection")

    press(devtools, "Escape")
    expect(devtools.evaluate(RANKINGS)["selectedId"] is None, "Esc did not deselect")

    click = f'document.querySelector(\'.bom-field tr[data-id="{third}"]\').click(), true'
    devtools.evaluate(click)
    time.sleep(CALLOUT_WAIT_S)
    clicked = devtools.evaluate(RANKINGS)
    expect(clicked["selectedId"] == third and clicked["detail"], "a click did not open the row's detail")
    devtools.evaluate(click)
    time.sleep(CALLOUT_WAIT_S)
    again = devtools.evaluate(RANKINGS)
    expect(
        again["selectedId"] is None and not again["detail"],
        "a second click on the selected row did not close it",
    )

    press(devtools, "c")
    expect(devtools.evaluate(RANKINGS)["focused"] == "category", "C did not go to the category")
    devtools.evaluate(
        """
        (() => {
          const select = document.getElementById("category");
          select.value = "Linear";
          select.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()
        """
    )
    time.sleep(FILTER_WAIT_S)
    narrowed = devtools.evaluate(
        """
        (() => ({
          categories: Array.from(document.querySelectorAll(".bom-field .bom-cat"), (c) => c.textContent),
          search: location.search,
          exportCategory: (document.querySelector('#export-cell input[name="category"]') || {}).value || "",
        }))()
        """
    )
    expect(
        narrowed["categories"] and set(narrowed["categories"]) == {"Linear"},
        f"the category left {sorted(set(narrowed['categories']))}",
    )
    expect("category=Linear" in narrowed["search"], "the category did not replace the address")
    expect(narrowed["exportCategory"] == "Linear", "the export cell was not carried with the category")

    devtools.evaluate("document.activeElement.blur(), true")
    press(devtools, "h")
    wait_for_page(devtools, 'location.search.includes("retired=1")', "the sheet with retired items")
    shown = devtools.evaluate(
        '({ retired: document.querySelectorAll(".bom-field tr.is-retired").length,'
        ' search: location.search })'
    )
    expect(shown["retired"] > 0, "H showed no retired rows")
    expect("category=Linear" in shown["search"], "H dropped the category")

    # X presses the export form; the submission is caught before it downloads,
    # and the address it would have gone to is fetched instead.
    exported = devtools.evaluate(
        """
        new Promise((resolve) => {
          document.addEventListener("submit", (event) => {
            event.preventDefault();
            const form = event.target;
            const url = form.action + "?" + new URLSearchParams(new FormData(form));
            fetch(url).then((response) => response.text().then((text) => resolve({
              id: form.id,
              url,
              type: response.headers.get("content-type"),
              header: text.split("\\r\\n")[0],
              rows: text.trim().split("\\r\\n").length - 1,
            })));
          }, { once: true, capture: true });
          document.body.dispatchEvent(new KeyboardEvent("keydown", {
            key: "x", bubbles: true, cancelable: true
          }));
        })
        """
    )
    expect(exported["id"] == "export-cell", f"X submitted {exported['id']!r}")
    expect(
        "category=Linear" in exported["url"] and "retired=1" in exported["url"],
        f"X exported {exported['url']!r}, not the view",
    )
    expect(exported["type"].startswith("text/csv"), f"the export answered {exported['type']!r}")
    expect(exported["header"].startswith("Rank,Name,Category"), f"the export began {exported['header']!r}")
    rows_drawn = devtools.evaluate('document.querySelectorAll(".bom-field tr[data-id]").length')
    expect(exported["rows"] == rows_drawn, f"the export has {exported['rows']} rows, the sheet {rows_drawn}")
    return (
        "arrows select, Enter toggles the detail and arrows carry it, click opens and closes it; "
        f"C, a category swap, H and X kept the view ({exported['rows']} rows exported)"
    )


# The Settings sheet on the seeder's project holding the mockup's saved values:
# two parameters off their defaults, so Reset has something to change.
SETTINGS_FILE = "switches-sample-settings.pairrank"
SETTINGS_PATH = f"/projects/{SETTINGS_FILE}/settings"

# What the Settings sheet shows: the rows marked changed and in error, whether
# the revision triangle is drawn on them, Save's state, the Status cell, the
# focused element, and a marker a reload would lose.
SETTINGS_STATE = """
(() => {
  const ids = (selector) => Array.from(document.querySelectorAll(selector), (row) => row.id.slice(4));
  const shown = (row) => getComputedStyle(row.querySelector(".rev-mark")).visibility === "visible";
  return {
    changed: ids("#params tr.is-changed"),
    errors: ids("#params tr.is-error"),
    marks: Array.from(document.querySelectorAll('#params tr[id^="row-"]')).filter(shown).map((row) => row.id.slice(4)),
    saveDisabled: document.getElementById("save").disabled,
    status: document.getElementById("status").textContent.trim(),
    statusError: document.getElementById("status-cell").classList.contains("is-error"),
    error: (document.querySelector("#params tr.is-error .spec-error") || {}).textContent || "",
    focused: (document.activeElement || {}).id || "",
    slots: document.getElementById("slots").value,
    search: location.search,
    kept: window.__driveMarker === 1,
  };
})()
"""


def settings_type(devtools: DevTools, key: str, text: str) -> dict:
    """
    Type a value into one Settings field, as the browser reports an edit.

    Args:
        devtools: The CDP session.
        key: The setting's name.
        text: The field's new text.

    Returns:
        dict: The sheet's state afterwards.
    """
    devtools.evaluate(
        f"""
        (() => {{
          const input = document.getElementById("f-{key}");
          input.focus();
          input.value = {json.dumps(text)};
          input.dispatchEvent(new Event("input", {{ bubbles: true }}));
          return true;
        }})()
        """
    )
    return devtools.evaluate(SETTINGS_STATE)


def settings_ctrl_s(devtools: DevTools) -> bool:
    """
    Press Ctrl+S on the Settings sheet, where the person is.

    Returns:
        bool: Whether the page took the key from the browser (its own "Save
        page as" would otherwise open).
    """
    return devtools.evaluate(
        """
        (() => {
          const event = new KeyboardEvent("keydown", {
            key: "s", ctrlKey: true, bubbles: true, cancelable: true
          });
          (document.activeElement || document.body).dispatchEvent(event);
          return event.defaultPrevented;
        })()
        """
    )


def wait_for_settings(devtools: DevTools, condition: str, what: str) -> dict:
    """
    Wait until the Settings sheet is drawn, its script run, and a condition holds.

    Args:
        devtools: The CDP session.
        condition: A JavaScript expression over the page.
        what: What was expected, for the failure message.

    Returns:
        dict: The sheet's state once it holds.

    Raises:
        CheckError: If it never does.
    """
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            arrived = devtools.evaluate(
                'document.readyState === "complete"'
                ' && !!document.querySelector("form#settings[data-ready]")'
                f" && ({condition})"
            )
        except CaptureError:
            arrived = False
        if arrived:
            return devtools.evaluate(SETTINGS_STATE)
        time.sleep(POLL_INTERVAL_S)
    raise CheckError(f"never saw {what}")


def check_settings_keys(devtools: DevTools, base: str) -> str:
    """
    Check the Settings sheet's change marks, errors, Reset and Ctrl+S.

    Typing redraws the marks and the Status cell against the saved values the
    page carries, and Save is enabled only while there is something to save
    and nothing to fix; the error drawn as typed is the server's sentence.
    Ctrl+S is taken from the browser, does nothing with nothing to save, and
    puts the caret in the first field in error when there is one; Esc leaves
    a field. Reset fills the defaults in place without a request and leaves
    the slot list alone. Ctrl+S then saves, landing on "Saved." with the
    defaults written. The file is put back as it was.
    """
    path = Path(DATA_DIR["path"]) / SETTINGS_FILE
    original = path.read_bytes()
    try:
        size(devtools, *NARROW)
        devtools.call("Page.navigate", {"url": f"{base}{SETTINGS_PATH}"})
        start = wait_for_settings(devtools, "true", "the Settings sheet")
        devtools.evaluate("window.__driveMarker = 1, true")
        expect(start["changed"] == [] and start["marks"] == [], f"a saved sheet drew marks: {start['marks']}")
        expect(start["saveDisabled"], "Save was enabled with nothing to save")
        expect(start["status"].startswith("No unsaved changes."), f"the Status said {start['status']!r}")

        expect(settings_ctrl_s(devtools), "Ctrl+S was left to the browser")
        time.sleep(CALLOUT_WAIT_S)
        expect(devtools.evaluate(SETTINGS_STATE)["kept"], "Ctrl+S with nothing to save left the page")

        typed = settings_type(devtools, "weight_freshness", "0.75")
        expect(typed["changed"] == ["weight_freshness"], f"typing marked {typed['changed']}")
        expect(typed["marks"] == ["weight_freshness"], f"the triangle is drawn on {typed['marks']}")
        expect(not typed["saveDisabled"], "Save stayed disabled with a change to save")
        expect(
            typed["status"].startswith("1 unsaved change: Freshness."),
            f"the Status said {typed['status']!r}",
        )

        wrong = settings_type(devtools, "cross_category_rate", "1.5")
        expect(wrong["errors"] == ["cross_category_rate"], f"1.5 put {wrong['errors']} in error")
        expect(wrong["error"].strip() == "Must be between 0 and 1.", f"the error read {wrong['error']!r}")
        expect(wrong["saveDisabled"] and wrong["statusError"], "Save was enabled with a value to fix")
        expect(
            wrong["status"].startswith("Fix 1 value before saving."),
            f"the Status said {wrong['status']!r}",
        )
        devtools.evaluate("document.activeElement.blur(), true")
        settings_ctrl_s(devtools)
        time.sleep(CALLOUT_WAIT_S)
        refused = devtools.evaluate(SETTINGS_STATE)
        expect(refused["kept"], "Ctrl+S with a value to fix left the page")
        expect(refused["focused"] == "f-cross_category_rate", f"Ctrl+S focused {refused['focused']!r}")
        press(devtools, "Escape")
        expect(devtools.evaluate(SETTINGS_STATE)["focused"] == "", "Esc did not leave the field")

        settings_type(devtools, "cross_category_rate", ".1")
        same = settings_type(devtools, "weight_freshness", "0.50")
        expect(same["changed"] == [] and same["saveDisabled"], "the saved values respelled read as changes")

        devtools.evaluate('document.getElementById("reset").click(), true')
        time.sleep(CALLOUT_WAIT_S)
        reset = devtools.evaluate(SETTINGS_STATE)
        expect(reset["kept"] and "reset" not in reset["search"], "Reset left the page with JavaScript on")
        expect(
            sorted(reset["changed"]) == ["decay_timescale_days", "weight_uncompared"],
            f"Reset changed {reset['changed']}",
        )
        expect(reset["status"].startswith("Defaults filled in;"), f"the Status said {reset['status']!r}")
        expect(reset["slots"] == start["slots"], "Reset changed the slot list")

        settings_ctrl_s(devtools)
        saved = wait_for_settings(devtools, 'location.search.includes("done=saved")', "the save land")
        expect(not saved["kept"], "the save did not load the page it landed on")
        expect(saved["status"].startswith("Saved. No unsaved changes."), f"the Status said {saved['status']!r}")
        written = json.loads(path.read_text(encoding="utf-8"))["settings"]
        expect(
            written["weight_uncompared"] == 2.0 and written["decay_timescale_days"] == 30.0,
            f"the save wrote {written}",
        )
    finally:
        time.sleep(0.05)
        path.write_bytes(original)
    return (
        "typing marks and unmarks, errors disable Save, Ctrl+S focuses the error, "
        "Esc leaves, Reset fills in place, Ctrl+S saves"
    )


# What the Settings slot table shows: the tiles in order with their state
# classes and label text, the warning and the label errors, the focused tile.
SLOTS_STATE = """
(() => {
  const tiles = Array.from(document.querySelectorAll("#slot-board .balloon"), (tile) => {
    const input = tile.querySelector(".slot-label");
    return {
      name: input.name.slice("label:".length),
      value: input.value,
      placeholder: input.placeholder,
      classes: Array.from(tile.classList).filter((c) => c !== "balloon"),
    };
  });
  const warning = document.getElementById("slot-warning");
  return {
    tiles,
    count: document.getElementById("slots-count").textContent.trim(),
    panelChanged: document.getElementById("slots-panel").classList.contains("is-changed"),
    warning: warning.hidden ? "" : warning.textContent.replace(/\\s+/g, " ").trim(),
    errors: document.getElementById("slot-errors").textContent.replace(/\\s+/g, " ").trim(),
    focused: (document.activeElement || {}).name || "",
    saveDisabled: document.getElementById("save").disabled,
    status: document.getElementById("status").textContent.trim(),
    kept: window.__driveMarker === 1,
  };
})()
"""


def slots_type(devtools: DevTools, selector: str, text: str) -> dict:
    """
    Type into the slot list or a tile, as the browser reports an edit.

    Args:
        devtools: The CDP session.
        selector: The field's CSS selector.
        text: The field's new text.

    Returns:
        dict: The slot table's state afterwards.
    """
    devtools.evaluate(
        f"""
        (() => {{
          const input = document.querySelector({json.dumps(selector)});
          input.focus();
          input.value = {json.dumps(text)};
          input.dispatchEvent(new Event("input", {{ bubbles: true }}));
          return true;
        }})()
        """
    )
    return devtools.evaluate(SLOTS_STATE)


def tile_of(state: dict, name: str) -> dict:
    """
    Find one tile in a slot table's state.

    Args:
        state: What SLOTS_STATE returned.
        name: The slot's name.

    Returns:
        dict: The tile, or an empty dict when the board has none.
    """
    return next((tile for tile in state["tiles"] if tile["name"] == name), {})


def check_settings_slots(devtools: DevTools, base: str) -> str:
    """
    Check the Settings slot table: the board as the list is typed, the labels.

    Typing the list redraws the board with a tile per distinct slot, marks a
    repeat and warns of it (the mockup's dupslots state), and flags two slots
    drawn alike with the collision warning, which does not block Save. A label
    typed on a tile that another slot already shows is refused with the
    server's sentence, disables Save, and Ctrl+S puts the caret on that tile;
    typing keeps the caret in the tile (the board is not redrawn). A label that
    resolves the collision clears it, and Ctrl+S saves the list and the label.
    The file is put back.
    """
    path = Path(DATA_DIR["path"]) / SETTINGS_FILE
    original = path.read_bytes()
    try:
        size(devtools, *NARROW)
        devtools.call("Page.navigate", {"url": f"{base}{SETTINGS_PATH}"})
        wait_for_settings(devtools, "true", "the Settings sheet")
        devtools.evaluate("window.__driveMarker = 1, true")
        start = devtools.evaluate(SLOTS_STATE)
        saved_text = devtools.evaluate('document.getElementById("slots").value')
        expect(len(start["tiles"]) == 60, f"the board drew {len(start['tiles'])} tiles")
        expect(tile_of(start, "Apostrophe").get("value") == "'", "Apostrophe's saved label is not on its tile")
        expect(tile_of(start, "Enter").get("placeholder") == "En", "Enter's tile has no derived placeholder")
        expect(not start["panelChanged"] and start["warning"] == "", "a saved slot table drew a mark or a warning")

        dup = slots_type(devtools, "#slots", f"{saved_text}, 7, Esc")
        expect(len(dup["tiles"]) == 61, f"the list with a repeat drew {len(dup['tiles'])} tiles")
        expect("is-dup" in tile_of(dup, "7").get("classes", []), "the repeated slot is not marked")
        expect(dup["warning"].startswith("Slot 7 is listed twice."), f"the warning read {dup['warning']!r}")
        expect(dup["panelChanged"] and "Slots." in dup["status"], f"the Status said {dup['status']!r}")
        expect(dup["count"] == "61 slots · 56 in use", f"the count read {dup['count']!r}")

        clash = slots_type(devtools, "#slots", f"{saved_text}, 7, Esc, Enterprise")
        expect(
            all("is-clash" in tile_of(clash, name).get("classes", []) for name in ("Enter", "Enterprise")),
            "Enter and Enterprise are not flagged",
        )
        expect(
            "Slots Enter and Enterprise both show En." in clash["warning"],
            f"the warning read {clash['warning']!r}",
        )
        expect(not clash["saveDisabled"], "a collision nobody chose disabled Save")

        taken = slots_type(devtools, '.slot-label[name="label:Enterprise"]', "Sp")
        expect("is-error" in tile_of(taken, "Enterprise").get("classes", []), "the taken label is not in error")
        expect(
            taken["errors"] == "Slot Enterprise: Slot Space already shows Sp.",
            f"the error read {taken['errors']!r}",
        )
        expect(taken["saveDisabled"], "Save was enabled with a label to fix")
        expect(taken["status"].startswith("Fix 1 value before saving."), f"the Status said {taken['status']!r}")
        expect(taken["focused"] == "label:Enterprise", f"typing on a tile moved the caret to {taken['focused']!r}")
        devtools.evaluate("document.activeElement.blur(), true")
        settings_ctrl_s(devtools)
        time.sleep(CALLOUT_WAIT_S)
        refused = devtools.evaluate(SLOTS_STATE)
        expect(refused["kept"], "Ctrl+S with a label to fix left the page")
        expect(refused["focused"] == "label:Enterprise", f"Ctrl+S focused {refused['focused']!r}")

        fixed = slots_type(devtools, '.slot-label[name="label:Enterprise"]', "E2")
        expect(fixed["errors"] == "" and not fixed["saveDisabled"], "a free label was still refused")
        expect("is-clash" not in tile_of(fixed, "Enter").get("classes", []), "the label left the collision flagged")
        expect("both show" not in fixed["warning"], f"the warning read {fixed['warning']!r}")

        settings_ctrl_s(devtools)
        wait_for_settings(devtools, 'location.search.includes("done=saved")', "the save land")
        written = json.loads(path.read_text(encoding="utf-8"))
        expect(written["slots"][-2:] == ["Esc", "Enterprise"], f"the save wrote the slots {written['slots'][-3:]}")
        expect(
            written["slot_labels"] == {"Apostrophe": "'", "Enterprise": "E2"},
            f"the save wrote the labels {written['slot_labels']}",
        )
    finally:
        time.sleep(0.05)
        path.write_bytes(original)
    return (
        "the board follows the list, a repeat and a collision are warned of, a taken label is "
        "refused and focused by Ctrl+S, a free one saves with the list"
    )


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
    "form-once": check_form_once,
    "filter-callout": check_filter_callout,
    "filter-enter": check_filter_enter,
    "compare-keys": check_compare_keys,
    "compare-notice": check_compare_notice,
    "compare-double": check_compare_double,
    "compare-error": check_compare_error,
    "items-error": check_items_error,
    "rankings-keys": check_rankings_keys,
    "settings-keys": check_settings_keys,
    "settings-slots": check_settings_slots,
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

    DATA_DIR["path"] = data_dir
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
