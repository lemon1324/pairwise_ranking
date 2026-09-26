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

**Every row has a callout, and every callout state has an address too.** The
shapes are the register's (``routes/projects.py``), for the same reasons:

- **The callout fragments** answer with the popover for one row and nothing
  around it: the row's actions, its edit, replace or reactivate form, or the
  delete confirmation. An action cell fetches the next fragment into the same
  host with ``hx-get``. Add has no row, so ``form=new`` draws a ghost row at
  the top of the sheet and selects it, which is what fetches its form.
- **The page answers for every one of those states as well.** ``form`` and
  ``item`` open a form on a row, and ``submitted`` with the draft's fields
  (``name``, ``cat``, ``slot``, ``desc``) draws it as it was refused. That is
  what a refused post redirects to, so a form with its inline error survives a
  reload and can be photographed.
- **The mutations are ordinary form posts answered with a 303.** Each runs in
  :meth:`~src.web.registry.ProjectRegistry.mutate` - the file's lock, and a
  re-read first if the file changed on disk - validates *inside* it, and lands
  back on the sheet with the view it was made from and the right row selected:
  the item made or changed, or after Retire and Delete the row that followed
  the one that went. ``done`` and ``item`` name what happened for the Last
  change cell, which prints nothing from the query: each mutation records its
  sentence's words and time on the project's registry entry
  (:class:`~src.web.registry.LastChange`), and the cell writes them only when
  the address names that very change. Any other address - an older change, a
  deletion's item that still exists, a restarted server - shows the stored
  modified time.

Validation is :func:`src.app.items.validate_item_form`'s, the desktop dialog's
own: a name, and an identifier no other active item holds. Slots are a
suggestion rather than a closed set, as on the desktop.

Row actions need JavaScript (owner ruling, §5b of the plan): with the engine
off the sheet lists rows and the forms still post, but nothing opens them.
"""

import logging
import re
from dataclasses import dataclass
from dataclasses import replace as replace_fields
from typing import Optional
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.app.items import FIELD_IDENTIFIER, FIELD_NAME, validate_item_form
from src.app.slots import short_label
from src.models.item import Item
from src.models.project import Project

from ..deps import Principal, get_current_user, get_registry
from ..registry import LastChange, OpenProject, ProjectRegistry
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

# How the Last change cell writes the time of a change it names. The date is
# today's, and the sentence beside it is the news.
CHANGE_TIME_FORMAT = "%H:%M"

# The row Add hangs its form on. Item ids are UUIDs, so no item can be this.
GHOST_ROW_ID = "__new"
GHOST_LABEL = "New item"
TAG_NEW = "New"

# The forms and the one immediate action. Each is also the last segment of its
# fragment's address - `items/new`, `items/<id>/edit` - and `form` on the page.
FORM_NEW = "new"
FORM_EDIT = "edit"
FORM_REPLACE = "replace"
FORM_REACTIVATE = "reactivate"
FORM_DELETE = "delete"
ACTION_RETIRE = "retire"

# Which items each row verb is offered to: True for active ones, False for
# retired ones, None for both. The mockup's callouts, and the desktop's
# enabled buttons: a retired item can be reactivated or deleted, nothing else.
OFFERED_TO = {
    FORM_EDIT: True,
    FORM_REPLACE: True,
    ACTION_RETIRE: True,
    FORM_REACTIVATE: False,
    FORM_DELETE: None,
}

# The forms `form=` can open on the page. Anything else is no form at all.
ROW_FORMS = (FORM_EDIT, FORM_REPLACE, FORM_REACTIVATE, FORM_DELETE)

# What the Last change cell says after a mutation, keyed by the `done` it
# redirected with and recorded under: the verb, before the label the mutation
# recorded. Filled from the registry's record, never from the query.
DONE_ADDED = "added"
DONE_EDITED = "edited"
DONE_RETIRED = "retired"
DONE_REPLACED = "replaced"
DONE_REACTIVATED = "reactivated"
DONE_DELETED = "deleted"
DONE_VERBS = {
    DONE_ADDED: "Added",
    DONE_EDITED: "Edited",
    DONE_RETIRED: "Retired",
    DONE_REPLACED: "Replaced",
    DONE_REACTIVATED: "Reactivated",
    DONE_DELETED: "Deleted",
}

# Said after the Last change sentence when the mutation it describes found the
# file changed on disk and read it again first: the registry's reload notice,
# taken by the page the mutation redirected to.
RELOADED_NOTE = "The file had changed on disk, so it was read again first."

# The two field errors, as the mockup words them.
NAME_REQUIRED = "Name is required."


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


def _row(item: Item, labels: dict, callout_url: str) -> dict:
    """
    Turn one item into the row the template draws.

    Args:
        item: The item.
        labels: The project's explicit slot short labels.
        callout_url: Where the row's callout comes from when it is selected.

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
        "callout_url": callout_url,
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


@dataclass(frozen=True)
class View:
    """
    The three controls that decide which rows the sheet draws.

    Carried through every address a callout builds - its fragments, its forms'
    hidden fields, its Cancel, the 303 a post answers with - so that acting on
    a row never resets the sheet it was acted on from.

    Attributes:
        q: The name filter, stripped.
        category: The one category to draw, or empty for all of them.
        show_retired: Whether retired items are drawn.
    """

    q: str = ""
    category: str = ""
    show_retired: bool = False

    def query(self) -> dict:
        """
        Spell the view as query parameters.

        Returns:
            dict: ``q``, ``category`` and ``retired``, each only when it is
            set, so a plain view adds nothing to an address.
        """
        pairs = (
            ("q", self.q),
            ("category", self.category),
            ("retired", SHOW_RETIRED if self.show_retired else ""),
        )
        return {key: value for key, value in pairs if value}


def _view(q: str, category: str, retired: str) -> View:
    """
    Read a view from the three values a query or a form carries.

    Args:
        q: The name filter.
        category: The category.
        retired: "1" to show retired items; anything else hides them.

    Returns:
        View: The view.
    """
    return View(
        q=(q or "").strip(),
        category=category or "",
        show_retired=retired == SHOW_RETIRED,
    )


async def view_query(
    q: str = Query("", description="the name filter"),
    category: str = Query("", description="the one category to draw"),
    retired: str = Query("", description="1 to draw retired items too"),
) -> View:
    """
    Read the view from a query: the sheet's own, and every fragment's.

    Returns:
        View: The view.
    """
    return _view(q, category, retired)


async def view_form(
    q: str = Form("", description="the name filter"),
    category: str = Form("", description="the one category to draw"),
    retired: str = Form("", description="1 to draw retired items too"),
) -> View:
    """
    Read the view from a posted form's hidden fields.

    Returns:
        View: The view the form was opened from.
    """
    return _view(q, category, retired)


@dataclass(frozen=True)
class Draft:
    """
    What was typed into an item form.

    Named as the mockup names the fields. ``cat`` rather than ``category``,
    because ``category`` is already the view's, and a refused form's address
    carries both.

    Attributes:
        name: The name.
        cat: The category.
        slot: The slot, or free-text identifier.
        desc: The description.
    """

    name: str = ""
    cat: str = ""
    slot: str = ""
    desc: str = ""

    def query(self) -> dict:
        """
        Spell the draft as the query of a refused form.

        Returns:
            dict: The fields, with ``submitted`` - which is what says the
            fields are the draft's rather than absent.
        """
        return {
            "submitted": 1,
            "name": self.name,
            "cat": self.cat,
            "slot": self.slot,
            "desc": self.desc,
        }


def _draft(name: str, cat: str, slot: str, desc: str) -> Draft:
    """
    Build a draft from raw field values, stripped as the validator strips them.

    Returns:
        Draft: The draft.
    """
    return Draft(
        name=(name or "").strip(),
        cat=(cat or "").strip(),
        slot=(slot or "").strip(),
        desc=(desc or "").strip(),
    )


async def draft_query(
    submitted: int = Query(0, description="whether the draft has been posted"),
    name: str = Query("", description="the drafted name"),
    cat: str = Query("", description="the drafted category"),
    slot: str = Query("", description="the drafted slot"),
    desc: str = Query("", description="the drafted description"),
) -> Optional[Draft]:
    """
    Read a refused draft from a query.

    Returns:
        Optional[Draft]: The draft, or None when nothing has been posted - an
        empty field is only an error once someone has pressed Save on it.
    """
    return _draft(name, cat, slot, desc) if submitted else None


async def draft_form(
    name: str = Form("", description="the item's name"),
    cat: str = Form("", description="the item's category"),
    slot: str = Form("", description="the item's slot"),
    desc: str = Form("", description="the item's description"),
) -> Draft:
    """
    Read a draft from a posted item form.

    Returns:
        Draft: The draft.
    """
    return _draft(name, cat, slot, desc)


def _query_string(query: dict) -> str:
    """
    Write a query string, leaving out the empty parameters.

    Args:
        query: The parameters.

    Returns:
        str: ``?a=1&b=2``, or an empty string.
    """
    pairs = [(key, str(value)) for key, value in query.items() if value]
    return f"?{urlencode(pairs)}" if pairs else ""


def _sheet_url(request: Request, project_id: str, view: View, **query) -> str:
    """
    Build an address of the sheet itself.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        view: The view to keep.
        **query: The state on top of it: ``selected``, ``form``, ``done``...

    Returns:
        str: The address.
    """
    base = project_url(request, project_id, SHEET)
    return base + _query_string({**query, **view.query()})


def _item_url(
    request: Request, project_id: str, item_id: str, verb: str, view: View, **query
) -> str:
    """
    Build the address of one item's fragment or mutation.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        item_id: The item.
        verb: ``callout``, or one of the forms and actions.
        view: The view to carry.
        **query: A draft, for a refused form's fragment.

    Returns:
        str: ``.../items/<id>/<verb>``, with the query.
    """
    base = project_url(request, project_id, SHEET)
    item = quote(item_id, safe="")
    return f"{base}/{item}/{verb}" + _query_string({**query, **view.query()})


def _new_url(request: Request, project_id: str, view: View, **query) -> str:
    """
    Build the address of the Add form's fragment and of its post.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        view: The view to carry.
        **query: A draft, for a refused form.

    Returns:
        str: ``.../items/new``, with the query.
    """
    base = project_url(request, project_id, SHEET)
    return f"{base}/{FORM_NEW}" + _query_string({**query, **view.query()})


def _categories(project: Project) -> list:
    """
    List the project's categories, in the order the controls offer them.

    Args:
        project: The project.

    Returns:
        list: Every category any item is in, sorted ignoring case.
    """
    return sorted({item.category for item in project.items}, key=str.casefold)


def _shown(project: Project, view: View) -> list:
    """
    Choose and order the items a view draws.

    Args:
        project: The project.
        view: The view. A category the project does not have reads as none.

    Returns:
        list: The items, in the sheet's order.
    """
    category = view.category if view.category in _categories(project) else ""
    needle = view.q.casefold()
    shown = [
        item
        for item in project.items
        if (view.show_retired or item.is_active())
        and (not needle or needle in item.name.casefold())
        and (not category or item.category == category)
    ]
    slot_order = {slot: i for i, slot in enumerate(project.slots)}
    shown.sort(key=lambda item: _row_order(item, slot_order))
    return shown


def _following(rows: list, item_id: str) -> str:
    """
    Choose the row the selection moves to when one leaves the sheet.

    The mockup's rule: the row after it, or the one before it when it was the
    last.

    Args:
        rows: The items the sheet draws, in order.
        item_id: The item leaving.

    Returns:
        str: The id to select, or empty when nothing is left to select.
    """
    ids = [item.id for item in rows]
    if item_id not in ids:
        return ""
    i = ids.index(item_id)
    following = ids[i + 1 : i + 2] or (ids[i - 1 : i] if i else [])
    return following[0] if following else ""


def _label(item: Item) -> str:
    """
    Name an item the way a sentence about it does: "(21) Kailh Box White".

    Args:
        item: The item.

    Returns:
        str: Its slot in brackets before its name, or just its name.
    """
    return f"({item.identifier}) {item.name}" if item.identifier else item.name


def _with_votes(count: int) -> str:
    """
    Say how many votes go with a deleted item.

    Args:
        count: The votes it took part in.

    Returns:
        str: " and its 12 votes", " and its 1 vote", or nothing for none.
    """
    if not count:
        return ""
    return f" and its {count} vote{'' if count == 1 else 's'}"


def _offered(item: Item, verb: str) -> bool:
    """
    Check that a row verb applies to an item in its current state.

    Args:
        item: The item.
        verb: A key of :data:`OFFERED_TO`.

    Returns:
        bool: True when the item's callout offers the verb.
    """
    wanted = OFFERED_TO[verb]
    return wanted is None or item.is_active() == wanted


def _find(entry: OpenProject, item_id: str, verb: str) -> Item:
    """
    Find the item a fragment is about, or answer 404.

    Args:
        entry: The open project.
        item_id: The item's id.
        verb: The fragment being asked for, or "callout" for the actions.

    Returns:
        Item: The item.

    Raises:
        HTTPException: 404 when there is no such item, or when its callout
            does not offer this verb - a retired item has no edit form.
    """
    item = entry.session.project.find_item(item_id)
    if item is None or (verb in OFFERED_TO and not _offered(item, verb)):
        raise HTTPException(status_code=404, detail="No such item form.")
    return item


def _last_change(entry: OpenProject, done: str, subject_id: str) -> Optional[LastChange]:
    """
    Find the change the address names, if it is the project's last one.

    The query only says which mutation it was and which item it was about; the
    words and the time come from the record the mutation left on the registry
    entry. An address naming anything else - an older change, whose time a
    later edit would otherwise relabel; a deletion of an item that is still
    there; a change a restarted server never saw - gets no sentence, and the
    cell shows the project's modified time.

    Args:
        entry: The open project.
        done: Which mutation the address says finished.
        subject_id: The item it says it was about.

    Returns:
        Optional[LastChange]: The record, when the address names it.
    """
    change = entry.last_change
    if change is None or change.kind != done or change.item_id != subject_id:
        return None
    return change


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}", name="items_sheet")
async def items_sheet(
    request: Request,
    project_id: str,
    view: View = Depends(view_query),
    selected: str = Query("", description="the row to arrive with selected"),
    form: str = Query("", description="the form open on the sheet"),
    item: str = Query("", description="the item the form or change is about"),
    draft: Optional[Draft] = Depends(draft_query),
    done: str = Query("", description="which mutation just finished"),
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
        view: ``q``, the name filter, ignoring case; ``category``, where a
            category the project does not have reads as none, so a stale
            address draws every item rather than a sheet that can never have
            rows on it; ``retired``, "1" to draw retired items after the active
            ones.
        selected: The id of the row to arrive with selected.
        form: "new" for the Add form on a ghost row; "edit", "replace",
            "reactivate" or "delete" for that callout on the row of ``item``.
            Anything else, or a form the item's row is not drawn for or does
            not offer, is no form: the sheet is drawn with the row selected.
        item: The item ``form`` opens on, or the one ``done`` is about.
        draft: The draft of a refused form: ``submitted=1`` with ``name``,
            ``cat``, ``slot`` and ``desc``.
        done: Which mutation just finished, for the Last change cell.
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
    pid = entry.path.name

    categories = _categories(project)
    if view.category not in categories:
        view = replace_fields(view, category="")
    q, category, show_retired = view.q, view.category, view.show_retired
    shown = _shown(project, view)

    # The form open on a row, if the row is drawn and its callout offers it;
    # otherwise the row is merely selected. Add hangs off the ghost row.
    drafted = draft.query() if draft is not None else {}
    subject = project.find_item(item) if item else None
    if form in ROW_FORMS:
        if subject is None or subject not in shown or not _offered(subject, form):
            form = ""
        else:
            selected = subject.id
    elif form == FORM_NEW:
        selected = GHOST_ROW_ID
    else:
        form = ""

    # Every row asks for its actions. The form the address opens is fetched
    # once, by the selection the page arrives with, and never again: selecting
    # the row later - after another, or after a filter - shows its actions, as
    # the mockup's does. Built into the row's hx-get, a refused form came back
    # on every re-selection, and a delete question with Delete focused.
    rows = [
        _row(shown_item, labels, _item_url(request, pid, shown_item.id, "callout", view))
        for shown_item in shown
    ]
    opening_url = (
        _item_url(request, pid, subject.id, form, view, **drafted)
        if form in ROW_FORMS
        else None
    )

    # Taken only by a page drawn whole. A rows swap is drawn whole too, but
    # htmx keeps the drawing area and drops the Last change cell, so a notice
    # taken there would be taken and never shown.
    reloaded = (
        request.headers.get("HX-Request") != "true" and entry.take_reload_notice()
    )

    active_count = len(project.active_items())
    items_url = project_url(request, pid, SHEET)
    change = _last_change(entry, done, item)
    context = {
        "project_id": pid,
        "project_name": project.name,
        "file_name": pid,
        "rows": rows,
        "ghost_id": GHOST_ROW_ID,
        "ghost_label": GHOST_LABEL,
        "ghost_tag": TAG_NEW,
        "ghost_callout_url": (
            _new_url(request, pid, view, **drafted) if form == FORM_NEW else None
        ),
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
        # The recorded time of the change named, not the project's modified
        # time, which every later edit or vote moves on.
        "last_change": (
            f"{DONE_VERBS[change.kind]} {change.label}{_with_votes(change.votes)}"
            if change is not None
            else None
        ),
        "change_time": change.time.strftime(CHANGE_TIME_FORMAT) if change is not None else "",
        "reloaded_note": RELOADED_NOTE if reloaded else "",
        "q": q,
        "category": category,
        "categories": categories,
        "show_retired": show_retired,
        "selected": selected,
        "opening_url": opening_url,
        "items_url": items_url,
        "new_form": FORM_NEW,
        # What the Add cell carries besides `form=new`, so adding from a
        # filtered sheet comes back to it.
        "add_params": {"form": FORM_NEW, **view.query()},
    }
    return _templates(request).TemplateResponse(request, "items.html", context)


def _fragment(request: Request, name: str, context: dict) -> Response:
    """
    Render one callout fragment.

    Args:
        request: The incoming request.
        name: The template under ``items/``.
        context: Its context.

    Returns:
        Response: The popover and nothing around it.
    """
    return _templates(request).TemplateResponse(request, f"items/{name}", context)


@router.get(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{item_id}}/callout",
    name="item_callout",
)
async def item_callout(
    request: Request,
    project_id: str,
    item_id: str,
    view: View = Depends(view_query),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return one row's callout: the actions its item is offered.

    An active item: Edit, Retire, Replace, Delete. A retired one: Reactivate
    and Delete, as the mockup and the desktop's enabled buttons both have it.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        item_id: The item.
        view: The view the sheet is drawn with, carried into every action.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The callout.

    Raises:
        HTTPException: 404 when the project holds no such item.
    """
    entry = registry.open(project_id)
    found = _find(entry, item_id, "callout")
    pid = entry.path.name

    def url(verb: str) -> str:
        return _item_url(request, pid, found.id, verb, view)

    context = {
        "label": _label(found),
        "retired": not found.is_active(),
        "edit_url": url(FORM_EDIT),
        "replace_url": url(FORM_REPLACE),
        "reactivate_url": url(FORM_REACTIVATE),
        "delete_url": url(FORM_DELETE),
        # Posted to without the view in the address: the form carries it.
        "retire_url": _item_url(request, pid, found.id, ACTION_RETIRE, View()),
        "view_fields": view.query(),
    }
    return _fragment(request, "callout_actions.html", context)


def _form_context(
    request: Request,
    entry: OpenProject,
    verb: str,
    subject: Optional[Item],
    draft: Optional[Draft],
    view: View,
) -> dict:
    """
    Build the context of the item form, in any of its four uses.

    The check a refused draft is drawn with is the one its post was refused by
    - the same validator, over the same session - so the error a user reads is
    the one that stopped the write.

    Args:
        request: The incoming request.
        entry: The open project.
        verb: "new", "edit", "replace" or "reactivate".
        subject: The item the form is about; None for Add.
        draft: The refused draft, or None for a fresh form.
        view: The view to carry.

    Returns:
        dict: The template context of ``items/callout_form.html``.
    """
    session = entry.session
    project = session.project
    pid = entry.path.name
    # The item's own slot counts as free: an edit keeps it, a replacement
    # inherits it, and a retired item holds none to begin with.
    exclude = subject.id if subject is not None else None
    free = session.free_slots(exclude)
    first_free = free[0] if free else ""

    if draft is not None:
        values = draft
    elif verb == FORM_EDIT:
        values = Draft(subject.name, subject.category, subject.identifier, subject.description)
    elif verb == FORM_REPLACE:
        values = Draft("", subject.category, subject.identifier, "")
    else:
        values = Draft(slot=first_free)

    errors = {}
    if draft is not None:
        verdict = _validate(session, draft, verb, subject)
        if FIELD_NAME in verdict.errors:
            errors["name"] = {"lead": NAME_REQUIRED}
        if FIELD_IDENTIFIER in verdict.errors:
            taken = verdict.form.identifier
            holder = next(
                (
                    held
                    for held in project.active_items()
                    if held.identifier == taken and held.id != exclude
                ),
                None,
            )
            errors["slot"] = {
                "slot": taken,
                "holder": holder.name if holder is not None else "",
                "free": free,
            }

    slot_only = verb == FORM_REACTIVATE
    fields = ["slot"] if slot_only else ["name", "slot"]
    focus = next((field for field in fields if field in errors), fields[0])

    if verb == FORM_NEW:
        title = "New item"
        action = _new_url(request, pid, View())
        cancel_url = _sheet_url(request, pid, view)
    else:
        title = {
            FORM_EDIT: f"Edit {_label(subject)}",
            FORM_REPLACE: f"Replace {_label(subject)}",
            FORM_REACTIVATE: f"Reactivate {subject.name}",
        }[verb]
        action = _item_url(request, pid, subject.id, verb, View())
        # Back to the row's actions, with the row selected: closing a form
        # returns the focus to its row.
        cancel_url = _sheet_url(request, pid, view, selected=subject.id)

    return {
        "title": title,
        "action": action,
        "cancel_url": cancel_url,
        "values": values,
        "errors": errors,
        "focus": focus,
        "slot_only": slot_only,
        "submit_label": "Reactivate" if slot_only else "Save",
        "note": (
            f"Saving retires {subject.name} (its votes are kept) and adds this "
            "item in its slot."
            if verb == FORM_REPLACE
            else ""
        ),
        "has_slot_list": bool(project.slots),
        "free_slots": free,
        "categories": _categories(project),
        "view_fields": view.query(),
    }


def _validate(session, draft: Draft, verb: str, subject: Optional[Item]):
    """
    Check a draft the way the desktop's item dialog does.

    Args:
        session: The project's session.
        draft: The draft.
        verb: The form it came from. Reactivate has only a slot field, so the
            name checked is the item's own.
        subject: The item the form is about; None for Add.

    Returns:
        ItemFormVerdict: The cleaned values and the field errors.
    """
    exclude = subject.id if subject is not None else None
    name = subject.name if verb == FORM_REACTIVATE else draft.name
    return validate_item_form(
        name=name,
        description=draft.desc,
        identifier=draft.slot,
        category=draft.cat,
        taken_identifiers=session.taken_identifiers(exclude),
    )


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{FORM_NEW}", name="new_item_form")
async def new_item_form(
    request: Request,
    project_id: str,
    view: View = Depends(view_query),
    draft: Optional[Draft] = Depends(draft_query),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return the Add form, as a fragment for the ghost row's callout.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        view: The view to come back to.
        draft: A refused draft to draw with its errors.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The callout.
    """
    entry = registry.open(project_id)
    context = _form_context(request, entry, FORM_NEW, None, draft, view)
    return _fragment(request, "callout_form.html", context)


@router.get(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{item_id}}/{{verb}}",
    name="item_form",
)
async def item_form(
    request: Request,
    project_id: str,
    item_id: str,
    verb: str,
    view: View = Depends(view_query),
    draft: Optional[Draft] = Depends(draft_query),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return one row's form or its delete confirmation, as a callout fragment.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        item_id: The item.
        verb: "edit", "replace", "reactivate" or "delete".
        view: The view to come back to.
        draft: A refused draft to draw with its errors.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The callout.

    Raises:
        HTTPException: 404 for another verb, for an item the project does not
            hold, or for a form the item's row does not offer.
    """
    if verb not in ROW_FORMS:
        raise HTTPException(status_code=404, detail="No such item form.")
    entry = registry.open(project_id)
    found = _find(entry, item_id, verb)
    if verb != FORM_DELETE:
        context = _form_context(request, entry, verb, found, draft, view)
        return _fragment(request, "callout_form.html", context)

    project = entry.session.project
    pid = entry.path.name
    votes = sum(1 for vote in project.votes if vote.involves_item(found.id))
    context = {
        "label": _label(found),
        "question": f"Delete {_label(found)}{_with_votes(votes)}?",
        # Retiring is offered as the gentler way only to an item that can
        # still be retired.
        "consequence": (
            "This can’t be undone. Retire keeps the votes and frees the slot instead."
            if found.is_active()
            else "This can’t be undone."
        ),
        "action": _item_url(request, pid, found.id, FORM_DELETE, View()),
        "cancel_url": _sheet_url(request, pid, view, selected=found.id),
        "view_fields": view.query(),
    }
    return _fragment(request, "callout_delete.html", context)


def _landed(
    request: Request, project_id: str, view: View, selected: str, done: str,
    subject_id: str,
) -> Response:
    """
    Answer a mutation that went through: back to the sheet, with the view.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        view: The view the mutation was made from.
        selected: The row to arrive on, or empty for none.
        done: Which mutation finished, as it recorded itself.
        subject_id: The item it was about.

    Returns:
        Response: A 303 to the sheet.
    """
    return RedirectResponse(
        _sheet_url(
            request, project_id, view, selected=selected, done=done, item=subject_id
        ),
        status_code=303,
    )


def _refused(
    request: Request, project_id: str, view: View, verb: str,
    subject_id: str, draft: Draft,
) -> Response:
    """
    Answer a form whose draft was refused: back to the form, with the draft.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        view: The view the form was opened from.
        verb: The form.
        subject_id: The item it is about; empty for Add.
        draft: What was typed.

    Returns:
        Response: A 303 to the address that draws the form with its errors.
    """
    logger.info("Refused the %s form for %r in %s", verb, subject_id, project_id)
    return RedirectResponse(
        _sheet_url(
            request, project_id, view, form=verb, item=subject_id, **draft.query()
        ),
        status_code=303,
    )


def _not_offered(
    request: Request, project_id: str, view: View, item_id: str, found: bool
) -> Response:
    """
    Answer a post about an item that is gone, or in the wrong state for it.

    Not an error page. The usual cause is a second tab that deleted or retired
    the item first, and the honest answer is the sheet as it now is - with the
    item selected when it is still there, so its callout shows what can be done
    with it instead. Nothing is changed.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        view: The view the post came from.
        item_id: The item.
        found: Whether the project still holds it.

    Returns:
        Response: A 303 to the sheet.
    """
    logger.info("Ignored a post about %r in %s: not offered", item_id, project_id)
    return RedirectResponse(
        _sheet_url(request, project_id, view, selected=item_id if found else ""),
        status_code=303,
    )


@router.post(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{FORM_NEW}", name="add_item")
async def add_item(
    request: Request,
    project_id: str,
    draft: Draft = Depends(draft_form),
    view: View = Depends(view_form),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Add an item, and come back with it selected.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        draft: The form.
        view: The view the form was opened from.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the sheet, or back to the form with its errors.
    """
    with registry.mutate(project_id) as mutation:
        pid = mutation.entry.path.name
        verdict = _validate(mutation.session, draft, FORM_NEW, None)
        if not verdict.ok:
            return _refused(request, pid, view, FORM_NEW, "", draft)
        cleaned = verdict.form
        added = mutation.session.add_item(
            Item(
                name=cleaned.name,
                description=cleaned.description,
                identifier=cleaned.identifier,
                category=cleaned.category,
            )
        )
        mutation.record_change(DONE_ADDED, added.id, _label(added))
    logger.info("Added %s to %s", added.id, pid)
    return _landed(request, pid, view, added.id, DONE_ADDED, added.id)


@router.post(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{item_id}}/{FORM_EDIT}",
    name="edit_item",
)
async def edit_item(
    request: Request,
    project_id: str,
    item_id: str,
    draft: Draft = Depends(draft_form),
    view: View = Depends(view_form),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Save an edited item, and come back with it still selected.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        item_id: The item.
        draft: The form.
        view: The view the form was opened from.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the sheet, or back to the form with its errors.
    """
    with registry.mutate(project_id) as mutation:
        pid = mutation.entry.path.name
        found = mutation.session.project.find_item(item_id)
        if found is None or not _offered(found, FORM_EDIT):
            return _not_offered(request, pid, view, item_id, found is not None)
        verdict = _validate(mutation.session, draft, FORM_EDIT, found)
        if not verdict.ok:
            return _refused(request, pid, view, FORM_EDIT, found.id, draft)
        cleaned = verdict.form
        edited = replace_fields(
            found,
            name=cleaned.name,
            description=cleaned.description,
            identifier=cleaned.identifier,
            category=cleaned.category,
        )
        mutation.session.update_item(edited)
        mutation.record_change(DONE_EDITED, item_id, _label(edited))
    logger.info("Edited %s in %s", item_id, pid)
    return _landed(request, pid, view, item_id, DONE_EDITED, item_id)


@router.post(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{item_id}}/{FORM_REPLACE}",
    name="replace_item",
)
async def replace_item(
    request: Request,
    project_id: str,
    item_id: str,
    draft: Draft = Depends(draft_form),
    view: View = Depends(view_form),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Retire an item and add its successor, and come back with the successor.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        item_id: The item being replaced.
        draft: The successor's form.
        view: The view the form was opened from.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the sheet, or back to the form with its errors.
    """
    with registry.mutate(project_id) as mutation:
        pid = mutation.entry.path.name
        found = mutation.session.project.find_item(item_id)
        if found is None or not _offered(found, FORM_REPLACE):
            return _not_offered(request, pid, view, item_id, found is not None)
        verdict = _validate(mutation.session, draft, FORM_REPLACE, found)
        if not verdict.ok:
            return _refused(request, pid, view, FORM_REPLACE, found.id, draft)
        cleaned = verdict.form
        successor = mutation.session.replace(
            found.id,
            Item(
                name=cleaned.name,
                description=cleaned.description,
                identifier=cleaned.identifier,
                category=cleaned.category,
            ),
        )
        mutation.record_change(
            DONE_REPLACED, successor.id, f"{found.name} with {_label(successor)}"
        )
    logger.info("Replaced %s with %s in %s", item_id, successor.id, pid)
    return _landed(request, pid, view, successor.id, DONE_REPLACED, successor.id)


@router.post(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{item_id}}/{FORM_REACTIVATE}",
    name="reactivate_item",
)
async def reactivate_item(
    request: Request,
    project_id: str,
    item_id: str,
    draft: Draft = Depends(draft_form),
    view: View = Depends(view_form),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return a retired item to the active pool, in the slot the form gives it.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        item_id: The item.
        draft: The form; only its slot is read.
        view: The view the form was opened from.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the sheet, or back to the form with its errors.
    """
    with registry.mutate(project_id) as mutation:
        pid = mutation.entry.path.name
        found = mutation.session.project.find_item(item_id)
        if found is None or not _offered(found, FORM_REACTIVATE):
            return _not_offered(request, pid, view, item_id, found is not None)
        verdict = _validate(mutation.session, draft, FORM_REACTIVATE, found)
        if not verdict.ok:
            return _refused(request, pid, view, FORM_REACTIVATE, found.id, draft)
        mutation.session.reactivate(found.id, verdict.form.identifier)
        reactivated = mutation.session.project.find_item(found.id)
        mutation.record_change(DONE_REACTIVATED, item_id, _label(reactivated))
    logger.info("Reactivated %s in %s", item_id, pid)
    return _landed(request, pid, view, item_id, DONE_REACTIVATED, item_id)


@router.post(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{item_id}}/{ACTION_RETIRE}",
    name="retire_item",
)
async def retire_item(
    request: Request,
    project_id: str,
    item_id: str,
    view: View = Depends(view_form),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Retire an item at once: its votes are kept and its slot is freed.

    No confirmation, as in the mockup: nothing is lost, and Reactivate puts it
    back. The selection stays on the item when retired items are shown, and
    otherwise moves to the row that followed it.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        item_id: The item.
        view: The view the callout was opened from.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the sheet.
    """
    with registry.mutate(project_id) as mutation:
        pid = mutation.entry.path.name
        project = mutation.session.project
        found = project.find_item(item_id)
        if found is None or not _offered(found, ACTION_RETIRE):
            return _not_offered(request, pid, view, item_id, found is not None)
        freed = found.identifier
        selected = (
            found.id if view.show_retired else _following(_shown(project, view), found.id)
        )
        mutation.session.retire(found.id)
        slot = f" · slot {freed} freed" if freed else ""
        mutation.record_change(DONE_RETIRED, item_id, f"{found.name}{slot}")
    logger.info("Retired %s in %s", item_id, pid)
    return _landed(request, pid, view, selected, DONE_RETIRED, item_id)


@router.post(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{item_id}}/{FORM_DELETE}",
    name="delete_item",
)
async def delete_item(
    request: Request,
    project_id: str,
    item_id: str,
    view: View = Depends(view_form),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Delete an item and every vote it took part in, after the confirmation.

    The selection moves to the row that followed it. Its name and votes are
    recorded for the Last change cell, like every change's, and here because
    the project no longer holds them.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        item_id: The item.
        view: The view the callout was opened from.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the sheet.
    """
    with registry.mutate(project_id) as mutation:
        pid = mutation.entry.path.name
        project = mutation.session.project
        found = project.find_item(item_id)
        if found is None:
            return _not_offered(request, pid, view, item_id, False)
        votes = sum(1 for vote in project.votes if vote.involves_item(found.id))
        label = _label(found)
        selected = _following(_shown(project, view), found.id)
        mutation.session.delete_item(found.id)
        mutation.record_change(DONE_DELETED, item_id, label, votes)
    logger.info("Deleted %s and %d votes from %s", item_id, votes, pid)
    return _landed(request, pid, view, selected, DONE_DELETED, item_id)
