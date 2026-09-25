"""The Items sheet: one project's items, drawn as an assembly parts list.

One row per item, find-numbered by its slot balloon, with its name and
description, category and status; the title block says how full the slot list
is and how many items are active and retired, and carries the three controls
that decide which rows are drawn - a name filter (``/``), a category (``C``)
and whether retired items are shown (``H``). Ported from
``docs/mockups/items.html``.

**Every view of the sheet has an address.** The three controls are the query
of :func:`items_sheet` - ``q``, ``category`` and ``retired`` - so a filtered,
narrowed or retired-showing sheet can be reloaded, linked and photographed, and
works with JavaScript off: the controls are one GET form. With JavaScript on,
typing in the filter or choosing a category asks for the same address through
htmx and swaps only the drawing area, which is the rows swap the folding engine
was built for. A filter that matches nothing answers with the empty state and
**no table** - never an empty one - and the engine forgets the rows it was
holding (see §5c of the plan, and ``drive_sheet.py --check swap-empty``).

**This chunk draws the sheet and nothing that changes it.** The row callout -
Edit, Retire, Replace, Reactivate, Delete - and the Add form are the next
chunk's, so the rows here carry no ``callout_url`` yet and the Add cell points
at the ``form=new`` address that chunk will serve.
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from src.app.slots import short_label
from src.models.item import Item

from ..deps import Principal, get_current_user, get_registry
from ..registry import ProjectRegistry
from ..urls import PROJECTS_PREFIX, project_url


logger = logging.getLogger(__name__)

router = APIRouter()

# The slug this sheet is served under, and the tab it marks as current.
SHEET = "items"

# The keys the title block lists: the mockup's eight, and the category's C,
# which is listed where docs/mockups/rankings.html lists it because its cell
# has no room for a legend. Add (N), Retired (H) and the filter (/) are drawn
# on their own cells. Every one of them is declared on the control it presses.
ITEM_KEYS = (
    (("↑", "↓"), "select"),
    (("Pg↑↓",), "sheet"),
    (("↵",), "edit"),
    (("R",), "retire"),
    (("P",), "replace"),
    (("A",), "reactivate"),
    (("Del",), "delete"),
    (("C",), "category"),
    (("Esc",), "clear"),
)

# The sheet's columns, in the shape the parts-list macro wants them.
ITEM_COLUMNS = (
    {"label": "Slot", "width": "3.5rem", "class": "c-find"},
    {"label": "Name"},
    {"label": "Category", "width": "6.5rem", "class": "c-cat"},
    {"label": "Status", "width": "6.25rem"},
)

# The tags drawn in the Status column: the words that go with ink 3 on a
# retired row, and with the dashed balloon on an item that has no slot. An
# active item with a slot is plain "Active", which is not a tag.
TAG_RETIRED = "Retired"
TAG_NO_SLOT = "No slot"

# How many free slots the Slots cell lists before it counts the rest instead,
# and how many it lists when it does. From the mockup: nine or more free slots
# read as the first six "and n more", because a line of thirty numbers is not a
# summary.
FREE_LIST_LIMIT = 8
FREE_LIST_SHOWN = 6

# How the Last change cell writes the project's modified time. No seconds, as
# on the register.
MODIFIED_FORMAT = "%Y-%m-%d %H:%M"

# The value of `retired` that shows retired items. Anything else hides them: a
# mistyped address should draw the sheet, not an error page.
SHOW_RETIRED = "1"


def _templates(request: Request) -> Jinja2Templates:
    """
    Reach the application's template environment.

    Args:
        request: The incoming request.

    Returns:
        Jinja2Templates: The environment the factory built.
    """
    return request.app.state.templates


def _natural(text: str) -> tuple:
    """
    Build a sort key that puts "2" before "10".

    Slots are usually numbered, and a slot list that is not in order - or a
    project with no slot list, whose identifiers are free text - should still
    read 1, 2, 10 rather than 1, 10, 2.

    Args:
        text: The identifier.

    Returns:
        tuple: The key; runs of digits compare as numbers, the rest casefolded.
    """
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part.casefold())
        for part in re.split(r"(\d+)", text)
        if part
    )


def _row_order(item: Item, slot_order: dict) -> tuple:
    """
    Place one item in the sheet's order.

    Slotted items first, in the order the slot list defines, so the sheet reads
    down the board the way the board is laid out; then active items without a
    slot; then retired items. Within the last two, by name. An identifier the
    slot list does not name comes after every one it does, in natural order.

    Args:
        item: The item.
        slot_order: Slot name to its position in the project's slot list.

    Returns:
        tuple: The sort key.
    """
    if not item.is_active():
        return (2, 0, (), item.name.casefold())
    if not item.identifier:
        return (1, 0, (), item.name.casefold())
    position = slot_order.get(item.identifier, len(slot_order))
    return (0, position, _natural(item.identifier), item.name.casefold())


def _row(item: Item, labels: dict) -> dict:
    """
    Turn one item into the row the template draws.

    Args:
        item: The item.
        labels: The project's explicit slot short labels.

    Returns:
        dict: The row. Named for what each value holds, never ``items`` or
        ``keys``: a template's dot reaches a mapping's own methods first.
    """
    if not item.is_active():
        tag = TAG_RETIRED
    elif not item.identifier:
        tag = TAG_NO_SLOT
    else:
        tag = None
    short = short_label(item.identifier, labels) if item.identifier else ""
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "category": item.category,
        # The balloon shows the short label and gives the full slot name to
        # hover and to assistive technology - but only when the two differ, so
        # a numbered slot is not read out twice.
        "short": short,
        "slot": item.identifier if item.identifier != short else None,
        "retired": not item.is_active(),
        "tag": tag,
    }


def _slot_entry(slot: str, labels: dict) -> dict:
    """
    Describe one slot as the Slots cell lists it.

    Args:
        slot: The slot name.
        labels: The project's explicit slot short labels.

    Returns:
        dict: The short label, and the full name when it differs from it.
    """
    short = short_label(slot, labels)
    return {"short": short, "full": slot if slot != short else None}


def _slots_summary(session, labels: dict) -> Optional[dict]:
    """
    Summarize the slot list for the Slots cell.

    Args:
        session: The project's session.
        labels: The project's explicit slot short labels.

    Returns:
        Optional[dict]: None when the project has no slot list, which the cell
        says in words. Otherwise the used and total counts, the free slots to
        list, and how many more are free than are listed.
    """
    summary = session.slot_summary()
    if not summary.total:
        return None
    free = summary.free
    listed = free[:FREE_LIST_SHOWN] if len(free) > FREE_LIST_LIMIT else free
    return {
        "used": summary.used,
        "total": summary.total,
        "free": [_slot_entry(slot, labels) for slot in listed],
        "more": len(free) - len(listed),
    }


def _empty_state(
    has_items: bool, q: str, category: str, show_retired: bool
) -> dict:
    """
    Choose what the drawing area says when no row is drawn.

    Args:
        has_items: Whether the project has any items at all.
        q: The name filter.
        category: The category chosen.
        show_retired: Whether retired items are shown.

    Returns:
        dict: The ``lead`` and ``detail`` sentences, and ``add`` - whether the
        box offers the Add cell button, which it does only when there is
        nothing in the project to filter.
    """
    if not has_items:
        return {
            "lead": "No items yet.",
            "detail": (
                "Add the things you want to rank. Each item can take a slot "
                "from the board."
            ),
            "add": True,
        }
    hidden = "" if show_retired else "Retired items are hidden. "
    if q:
        within = f"{category} items" if category else "items"
        return {
            "lead": f"No {within} match “{q}”.",
            "detail": f"{hidden}Clear the filter with Esc.",
            "add": False,
        }
    if category:
        return {
            "lead": (
                f"No {category} items." if show_retired
                else f"No {category} items are active."
            ),
            "detail": "Choose another category or All categories.",
            "add": False,
        }
    return {
        "lead": "No active items.",
        "detail": "Every item is retired. Show them with H.",
        "add": False,
    }


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}", name="items_sheet")
async def items_sheet(
    request: Request,
    project_id: str,
    q: str = Query("", description="the name filter"),
    category: str = Query("", description="the one category to draw"),
    retired: str = Query("", description="1 to draw retired items too"),
    selected: str = Query("", description="the row to arrive with selected"),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Draw one project's items as a parts list.

    The same address answers htmx's rows swap: the page is drawn whole and the
    filter and category controls pick the drawing area out of it, so there is
    one template and one set of rows, and what the swap lands is exactly what
    a reload of the new address would draw.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        q: Draw only items whose name contains this, ignoring case.
        category: Draw only items in this category. A category the project
            does not have reads as none: a stale address draws every item
            rather than a sheet that can never have rows on it.
        retired: "1" to draw retired items after the active ones.
        selected: The id of the row to arrive with selected.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The Items sheet.

    Raises:
        ProjectNotFoundError: If the id names no project in the directory.
        NewerFormatError: If the file was written by a newer application.
        ProjectFormatError: If the file's format version cannot be reached.
        ProjectUnreadableError: If the file will not read as a project.
    """
    entry = registry.open(project_id)
    session = entry.session
    project = session.project
    labels = project.slot_labels

    q = q.strip()
    show_retired = retired == SHOW_RETIRED
    categories = sorted({item.category for item in project.items}, key=str.casefold)
    if category not in categories:
        category = ""

    needle = q.casefold()
    shown = [
        item
        for item in project.items
        if (show_retired or item.is_active())
        and (not needle or needle in item.name.casefold())
        and (not category or item.category == category)
    ]
    slot_order = {slot: i for i, slot in enumerate(project.slots)}
    shown.sort(key=lambda item: _row_order(item, slot_order))

    active_count = len(project.active_items())
    items_url = project_url(request, entry.path.name, SHEET)
    context = {
        "project_id": entry.path.name,
        "project_name": project.name,
        "file_name": entry.path.name,
        "rows": [_row(item, labels) for item in shown],
        "columns": ITEM_COLUMNS,
        "keys": ITEM_KEYS,
        "empty": _empty_state(bool(project.items), q, category, show_retired),
        "slots": _slots_summary(session, labels),
        # Counts, named as counts: `active` and `retired` would read fine, but
        # a context of mappings named after what they count is how `row.items`
        # once rendered a bound method on every row of the register.
        "active_count": active_count,
        "retired_count": len(project.items) - active_count,
        "modified": project.modified.strftime(MODIFIED_FORMAT),
        "q": q,
        "category": category,
        "categories": categories,
        "show_retired": show_retired,
        "selected": selected,
        "items_url": items_url,
        "new_form": "new",
    }
    return _templates(request).TemplateResponse(request, "items.html", context)
