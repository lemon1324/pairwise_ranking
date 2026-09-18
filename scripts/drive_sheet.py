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
app, runs every check and tears it all down. ``--data-dir`` points it at a
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

Each check leaves the page as it found it by navigating afresh, so they are
independent and ``--check`` can run any one of them alone.
"""

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_web import (  # noqa: E402
    CaptureError,
    DevTools,
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


CHECKS = {
    "fold": check_fold,
    "swap-empty": check_swap_empty,
    "swap-fewer": check_swap_fewer,
    "page-then-arrow": check_page_then_arrow,
    "escape-in-field": check_escape_in_field,
    "autofocus-select": check_autofocus_select,
    "key-on-fixed": check_key_on_fixed,
    "short-window": check_short_window,
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
        scratch = tempfile.mkdtemp(prefix="pairrank-drive-")
        written = seed(Path(scratch))
        data_dir = scratch
        print(f"{PROGRAM}: seeded {written} projects in {data_dir}")

    names = args.checks or list(CHECKS)
    server = None
    chrome = None
    devtools = None
    profile_dir = tempfile.mkdtemp(prefix="pairrank-drive-profile-")
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
