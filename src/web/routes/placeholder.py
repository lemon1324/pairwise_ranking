"""The empty sheet, drawn with nothing on it, and a parts list of nothing in particular.

Scaffolding. Phase 4 builds the shell - the frame, the zones, the standard
title block, the stylesheets and the self-hosted fonts - before there is a
single screen to put on it, and a shell nobody can open is a shell nobody can
check. This route renders the shell and nothing else, so the capture harness
has a URL and the tests have something that exercises `base.html` end to end.

Phase 5a adds rows to it, because a folding engine with nothing to fold cannot
be looked at either. `?rows=N` fills the sheet with N invented items through
the same macros a real screen uses, and `/_sheet/callout/{row}` returns a
callout for one of them, so the whole path - macro markup, fold, select, HTMX
fragment into `#row-callout` - is exercised before any of it has a project
behind it. Everything invented lives in `sample_rows` and `SAMPLE_*` below.

It is expected to be deleted once the picker, Items, Compare, Rankings and
Settings are all reachable. Nothing should come to depend on it.
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from ..deps import Principal, get_current_user


router = APIRouter()

# The keys the parts-list sheets carry, as (legends, verb) pairs. Held here
# rather than in the template because the empty sheet is standing in for the
# real ones, and this is the list they will show.
SHEET_KEYS = (
    (("↑", "↓"), "select"),
    (("Pg↑↓",), "sheet"),
    (("↵",), "edit"),
    (("Esc",), "clear"),
)

# The columns of the scaffolding parts list, in the shape Items will use.
SHEET_COLUMNS = (
    {"label": "Slot", "width": "3.5rem", "class": "c-find"},
    {"label": "Name"},
    {"label": "Category", "width": "6.5rem", "class": "c-cat"},
    {"label": "Status", "width": "6.25rem"},
)

# Invented rows. Nothing here is a real project; it exists so that a fold can
# be looked at. Deleted with the rest of this module.
SAMPLE_NAMES = (
    "Gateron Oil King",
    "Cherry MX Black Clear-Top",
    "NovelKeys Cream",
    "Durock T1",
    "Kailh Box Jade",
    "Gazzew Boba U4T",
    "Alpaca V2",
    "Gateron Ink Black V2",
    "Zeal Tealios V2",
    "Holy Panda X",
    "HMX Hyacinth V2",
    "TTC Gold Pink V2",
)
SAMPLE_CATEGORIES = ("Linear", "Tactile", "Clicky", "Silent")
SAMPLE_DESCRIPTIONS = (
    "Deep, muted bottom-out. Smooth all the way down.",
    "",
    "Scratchy until broken in; hollow, clacky sound.",
    "",
)
# Two named keys among the numbered slots, so the Short Label Rule is on the
# sheet: the balloon shows the short label and says the full name out loud.
SAMPLE_SLOT_NAMES = {7: ("'", "Apostrophe"), 19: ("En", "Enter")}

MAX_SAMPLE_ROWS = 400


def sample_rows(count: int) -> list:
    """
    Invent a parts list of the given length.

    Deterministic, so two captures of the same width can be compared. Every
    fourth row has no slot and every seventh is retired, which puts each row
    state on the sheet without needing a project behind it.

    Args:
        count: How many rows to make.

    Returns:
        list: Mappings the template draws with the parts-list macros.
    """
    rows = []
    for index in range(count):
        retired = index % 7 == 6
        slotless = not retired and index % 4 == 3
        short, full = SAMPLE_SLOT_NAMES.get(index, ("", ""))
        if not short and not retired and not slotless:
            short = full = str(index + 1)
        rows.append(
            {
                "id": f"r{index + 1}",
                "slot_short": "" if retired or slotless else short,
                "slot_full": "" if retired or slotless else full,
                "name": f"{SAMPLE_NAMES[index % len(SAMPLE_NAMES)]} {index + 1}",
                "description": SAMPLE_DESCRIPTIONS[index % len(SAMPLE_DESCRIPTIONS)],
                "category": SAMPLE_CATEGORIES[index % len(SAMPLE_CATEGORIES)],
                "retired": retired,
                "slotless": slotless,
            }
        )
    return rows


@router.get("/_sheet", name="placeholder_sheet")
async def placeholder_sheet(
    request: Request,
    rows: int = Query(0, ge=0, le=MAX_SAMPLE_ROWS),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Draw a sheet, empty or with invented rows on it.

    Args:
        request: The incoming request.
        rows: How many invented rows to draw. Zero - the default - keeps the
            empty sheet phase 4 checked the shell against.
        user: The signed-in principal. Unused, and asked for anyway: every
            route from here on depends on it so that the day it starts reading
            a forward-auth header, no route has to be found and changed.

    Returns:
        Response: The sheet shell, with a parts list or with an empty state.
    """
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "placeholder.html",
        {
            "keys": SHEET_KEYS,
            "columns": SHEET_COLUMNS,
            "sheet_rows": sample_rows(rows),
        },
    )


@router.get("/_sheet/callout/{row_id}", name="placeholder_callout")
async def placeholder_callout(
    request: Request, row_id: str, user: Principal = Depends(get_current_user)
) -> Response:
    """
    Return one row's callout, as a fragment for `#row-callout`.

    The actions do nothing. What is being checked is the shape a screen's
    fragment has to have: the popover macro's markup, a `data-sheet-key` on
    each action so the folding engine can press it, and nothing outside the
    callout element itself.

    Args:
        request: The incoming request.
        row_id: The row's `data-id`, straight back out of the page.
        user: The signed-in principal, as above.

    Returns:
        Response: The callout fragment.
    """
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "placeholder_callout.html", {"row_id": row_id}
    )
