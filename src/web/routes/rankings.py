"""The Rankings sheet: one project's items in the order the votes put them.

One row per item, find-numbered by its rank, with its category, its rating and
the rating's standard error drawn as a tolerance, and how often it has been
compared; the title block carries the category (``C``), whether retired items
are shown (``H``), the CSV export (``X``) and a summary of what is drawn.
Ported from ``docs/mockups/rankings.html``.

**Nothing here ranks anything.** The order, the ranks, the ratings and the
standard errors are :meth:`~src.app.session.ProjectSession.rankings`' - the
Bradley-Terry fit with the project's decay, numbered by
:func:`~src.models.ranking.assign_active_ranks`, so retired items keep their
rating and carry no rank. The ± SE in rating points is the log-strength
standard error on the scale the Compare tolerance uses
(:func:`~src.app.confidence.rating_points_per_log_unit`). The detail's record
is :meth:`~src.app.session.ProjectSession.item_details`, which reports every
opponent's weight both raw and decayed; this sheet shows both (owner answer,
phase 8), the decayed one in brackets. The desktop tab shows raw only.

**Every view of the sheet has an address**, in the shape the Items sheet gave
it (§5c of the plan): ``category`` and ``retired`` are the query, the category
control swaps only the drawing area with htmx and carries the retired toggle,
the export cell and the summary out of band, and the retired toggle is a GET
form of its own. ``selected`` arrives with a row selected and its detail open,
which is the mockup's "row detail" state.

**The export is what the sheet shows.** ``GET {rankings}/export`` with the
view's ``category`` and ``retired`` answers ``text/csv``: the rows of
:meth:`~src.app.session.ProjectSession.export_rows`, written by
:class:`csv.writer` exactly as the desktop's Export button writes them, which
also exports the category and the retired items its tab is showing. A test
holds the two byte for byte.

**A row's callout is its detail**, fetched when the row is selected. The mockup
opens it on a click and toggles it with ↵, and arrows carry it along while it
is open; the page's boot script keeps that one flag and cancels a row's fetch
while the detail is closed. The detail has no actions and declares no keys.
"""

import csv
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from src.app.confidence import rating_points_per_log_unit
from src.app.record import WeightedRecord
from src.models.project import Project
from src.models.ranking import RankingResult

from ..deps import Principal, get_current_user, get_registry
from ..registry import ProjectRegistry
from ..urls import PROJECTS_PREFIX, project_url


logger = logging.getLogger(__name__)

router = APIRouter()

# The slug this sheet is served under, and the tab it marks as current.
SHEET = "rankings"

# The keys the title block lists: the mockup's five. Retired (H) and Export (X)
# are drawn on their own cells, and every key is declared on what it presses -
# except ↵, which the boot script handles, because the detail it toggles is not
# a button.
RANKING_KEYS = (
    (("↑", "↓"), "select"),
    (("Pg↑↓",), "sheet"),
    (("↵",), "detail"),
    (("C",), "category"),
    (("Esc",), "deselect"),
)

# The sheet's columns, in the shape the parts-list macro wants them.
RANKING_COLUMNS = (
    {"label": "Rank", "width": "3.5rem", "class": "c-find"},
    {"label": "Name"},
    {"label": "Category", "width": "6.5rem", "class": "c-cat"},
    {"label": "Rating", "width": "4.75rem", "class": "n"},
    {"label": "± SE", "width": "4.25rem", "class": "n"},
    {"label": "Compared", "width": "5.5rem", "class": "n c-phone-hide"},
)

# The tag a retired row carries: the words that go with ink 3.
TAG_RETIRED = "Retired"

# The value of `retired` that shows retired items. Anything else hides them: a
# mistyped address should draw the sheet, not an error page.
SHOW_RETIRED = "1"

# Rankings need this many active items before there is an order to draw.
MIN_RANKED_ITEMS = 2

# How many opponents the detail's record lists before it counts the rest.
RECORD_SHOWN = 7

# What a figure the sheet cannot give reads as: no votes, or no rank.
NO_FIGURE = "–"

# The name the export is downloaded under, after the project's file stem. The
# desktop offers "rankings.csv" in its save dialog; a browser has no dialog, so
# the project's name goes in front and two exports do not overwrite each other.
EXPORT_SUFFIX = "rankings.csv"


def _templates(request: Request) -> Jinja2Templates:
    """
    Reach the application's template environment.

    Args:
        request: The incoming request.

    Returns:
        Jinja2Templates: The environment the factory built.
    """
    return request.app.state.templates


@dataclass(frozen=True)
class View:
    """
    The two controls that decide which rows the sheet draws and exports.

    Attributes:
        category: The one category to draw, or empty for all of them.
        show_retired: Whether retired items are drawn.
    """

    category: str = ""
    show_retired: bool = False

    def query(self) -> dict:
        """
        Spell the view as query parameters.

        Returns:
            dict: ``category`` and ``retired``, each only when it is set, so a
            plain view adds nothing to an address.
        """
        pairs = (
            ("category", self.category),
            ("retired", SHOW_RETIRED if self.show_retired else ""),
        )
        return {key: value for key, value in pairs if value}


async def view_query(
    category: str = Query("", description="the one category to draw"),
    retired: str = Query("", description="1 to draw retired items too"),
) -> View:
    """
    Read the view from a query: the sheet's own, and the export's.

    Returns:
        View: The view, before the category is checked against the project.
    """
    return View(category=category or "", show_retired=retired == SHOW_RETIRED)


def _categories(project: Project) -> list:
    """
    List the project's categories, in the order the control offers them.

    Args:
        project: The project.

    Returns:
        list: Every category any item is in, sorted ignoring case - the Items
        sheet's order, so the two controls read the same.
    """
    return sorted({item.category for item in project.items}, key=str.casefold)


def _checked(project: Project, view: View) -> View:
    """
    Drop a category the project does not have, so a stale address draws all.

    Args:
        project: The project.
        view: The view as the address gave it.

    Returns:
        View: The view the sheet is drawn with.
    """
    if view.category in _categories(project):
        return view
    return View(category="", show_retired=view.show_retired)


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


def _detail_url(request: Request, project_id: str, item_id: str) -> str:
    """
    Build the address of one row's detail.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        item_id: The item.

    Returns:
        str: ``.../rankings/<id>/detail``.
    """
    base = project_url(request, project_id, SHEET)
    return f"{base}/{quote(item_id, safe='')}/detail"


def _in_view(result: RankingResult, view: View) -> bool:
    """
    Check that a view draws one result.

    Args:
        result: The result.
        view: The view, its category already checked.

    Returns:
        bool: True when the row is drawn.
    """
    item = result.item
    return (view.show_retired or item.is_active()) and (
        not view.category or item.category == view.category
    )


def _se_points(result: RankingResult, scale: Optional[float]) -> Optional[int]:
    """
    Put a result's standard error in rating points.

    Args:
        result: The result.
        scale: Rating points per unit of log-strength, or None when the
            ratings carry no spread.

    Returns:
        Optional[int]: The rounded standard error, or None when there is no
        scale to measure it on.
    """
    if scale is None:
        return None
    return round(result.log_strength_se * scale)


def _row(
    result: RankingResult, scale: Optional[float], voted: bool, callout_url: str
) -> dict:
    """
    Turn one ranking result into the row the template draws.

    Args:
        result: The result.
        scale: Rating points per unit of log-strength.
        voted: Whether the project has any votes; without them every figure is
            the fit's starting point and none is drawn.
        callout_url: Where the row's detail comes from.

    Returns:
        dict: The row. Named for what each value holds, never ``items`` or
        ``keys``: a template's dot reaches a mapping's own methods first.
    """
    item = result.item
    se = _se_points(result, scale) if voted else None
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "rank": result.rank if voted else None,
        "rating": f"{result.elo_rating:.0f}" if voted else NO_FIGURE,
        "se": f"±{se}" if se is not None else NO_FIGURE,
        "compared": result.comparison_count,
        "retired": not item.is_active(),
        "callout_url": callout_url,
    }


def _empty_state(active_count: int, view: View) -> dict:
    """
    Choose what the drawing area says when no row is drawn.

    Args:
        active_count: How many active items the project has.
        view: The view.

    Returns:
        dict: The ``lead`` and ``detail`` sentences, and ``open_items`` -
        whether the box offers the way to the Items sheet, which it does only
        when the project has too few items to rank.
    """
    if active_count < MIN_RANKED_ITEMS:
        plural = "" if active_count == 1 else "s"
        return {
            "lead": "Rankings need at least 2 items.",
            "detail": f"This project has {active_count} active item{plural}.",
            "open_items": True,
        }
    return {
        "lead": (
            f"No {view.category} items." if view.show_retired
            else f"No {view.category} items are active."
        ),
        "detail": "Choose another category or All categories.",
        "open_items": False,
    }


def _summary(project: Project, shown: list, view: View, voted: bool) -> dict:
    """
    Count what the Summary cell reports.

    Args:
        project: The project.
        shown: The results the sheet draws.
        view: The view, its category already checked.
        voted: Whether the project has any votes.

    Returns:
        dict: ``active_shown``; ``retired_count``, every retired item in the
        category whether shown or not, as the mockup counts it; whether they
        are shown; and whether the order means anything yet.
    """
    return {
        "active_shown": sum(1 for result in shown if result.item.is_active()),
        "retired_count": sum(
            1
            for item in project.items
            if not item.is_active()
            and (not view.category or item.category == view.category)
        ),
        "retired_shown": view.show_retired,
        "voted": voted,
    }


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}", name="rankings_sheet")
async def rankings_sheet(
    request: Request,
    project_id: str,
    view: View = Depends(view_query),
    selected: str = Query("", description="the row to arrive on, its detail open"),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Draw one project's rankings as a parts list.

    The same address answers htmx's rows swap: the page is drawn whole and the
    category control picks the drawing area out of it, as on the Items sheet.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        view: ``category``, where a category the project does not have reads
            as none; ``retired``, "1" to draw retired items among the active
            ones by rating, with no rank.
        selected: The id of the row to arrive with selected and its detail
            open. An id the view does not draw selects nothing.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The Rankings sheet.

    Raises:
        ProjectNotFoundError: If the id names no project in the directory.
        NewerFormatError: If the file was written by a newer application.
        ProjectFormatError: If the file's format version cannot be reached.
        ProjectUnreadableError: If the file will not read as a project.
    """
    entry = registry.open_fresh(project_id)
    session = entry.session
    project = session.project
    pid = entry.path.name
    view = _checked(project, view)

    active_count = len(project.active_items())
    rankings = session.rankings() or []
    voted = bool(project.votes)
    shown = (
        [result for result in rankings if _in_view(result, view)]
        if active_count >= MIN_RANKED_ITEMS
        else []
    )
    if not voted:
        # Every item starts level, so the fit's order is arbitrary; the mockup
        # lists them by name and draws no rank.
        shown.sort(key=lambda result: result.item.name.casefold())
    scale = rating_points_per_log_unit(rankings)
    rows = [
        _row(result, scale, voted, _detail_url(request, pid, result.item.id))
        for result in shown
    ]

    rankings_url = project_url(request, pid, SHEET)
    context = {
        "project_id": pid,
        "project_name": project.name,
        "file_name": pid,
        "rows": rows,
        "columns": RANKING_COLUMNS,
        "keys": RANKING_KEYS,
        "retired_tag": TAG_RETIRED,
        "no_figure": NO_FIGURE,
        "empty": _empty_state(active_count, view),
        "summary": _summary(project, shown, view, voted),
        "category": view.category,
        "categories": _categories(project),
        "show_retired": view.show_retired,
        "selected": selected if any(row["id"] == selected for row in rows) else "",
        "rankings_url": rankings_url,
        "items_url": project_url(request, pid, "items"),
        "export_url": f"{rankings_url}/export",
        "export_params": view.query(),
    }
    return _templates(request).TemplateResponse(request, "rankings.html", context)


def _weight(raw: float, decayed: float) -> dict:
    """
    Spell one cell of the record: the raw weight, and the decayed one beside it.

    Args:
        raw: The summed raw weight.
        decayed: The same weight after decay.

    Returns:
        dict: ``raw``, written without a needless ".0"; ``decayed`` to one
        place, or empty when there is no weight at all to decay.
    """
    return {
        "raw": f"{raw:g}",
        "decayed": f"{decayed:.1f}" if raw else "",
    }


def _record_rows(record: WeightedRecord) -> list:
    """
    Merge an item's wins and losses into one line per opponent.

    The core keeps the two apart and opponents apart by id; the mockup's table
    has a line per opponent with both columns, the opponents met most - by
    total raw weight - first.

    Args:
        record: The item's weighted record.

    Returns:
        list: One mapping per opponent: ``name``, ``won`` and ``lost``, each a
        :func:`_weight`.
    """
    lines: dict = {}
    for side, entries in (("won", record.wins), ("lost", record.losses)):
        for entry in entries:
            line = lines.setdefault(
                entry.opponent_id,
                {"name": entry.name, "won": (0.0, 0.0), "lost": (0.0, 0.0)},
            )
            line[side] = (entry.weight_raw, entry.weight_decayed)
    ordered = sorted(
        lines.items(),
        key=lambda pair: (
            -(pair[1]["won"][0] + pair[1]["lost"][0]),
            pair[1]["name"].casefold(),
            pair[0],
        ),
    )
    return [
        {"name": line["name"], "won": _weight(*line["won"]), "lost": _weight(*line["lost"])}
        for _, line in ordered
    ]


@router.get(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{item_id}}/detail",
    name="ranking_detail",
)
async def ranking_detail(
    request: Request,
    project_id: str,
    item_id: str,
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return one row's callout: the item's figures beside its weighted record.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        item_id: The item.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The callout.

    Raises:
        HTTPException: 404 when the project ranks no such item - there is no
            such item, or the project has too few to rank.
    """
    entry = registry.open_fresh(project_id)
    session = entry.session
    project = session.project
    rankings = session.rankings() or []
    result = next((r for r in rankings if r.item.id == item_id), None)
    if result is None or len(project.active_items()) < MIN_RANKED_ITEMS:
        raise HTTPException(status_code=404, detail="No such ranked item.")

    voted = bool(project.votes)
    rank = result.rank if voted else None
    item = result.item
    se = _se_points(result, rating_points_per_log_unit(rankings))
    lines = _record_rows(session.item_details(item.id)) if voted else []
    half_life = project.settings.decay_timescale_days
    context = {
        "label": f"#{rank} {item.name}" if rank else item.name,
        "voted": voted,
        "rating": f"{result.elo_rating:.0f}",
        "se": f" ±{se}" if se is not None else "",
        "strength": f"{result.strength:.3f}",
        "log_strength": f"{result.log_strength:.3f}",
        "se_log": f"{result.log_strength_se:.3f}",
        "compared": result.comparison_count,
        "description": item.description,
        "record": lines[:RECORD_SHOWN],
        "more": len(lines) - min(len(lines), RECORD_SHOWN),
        "half_life": f"{half_life:g}" if half_life > 0 else "",
    }
    return _templates(request).TemplateResponse(request, "rankings/detail.html", context)


def export_csv(rows: list) -> str:
    """
    Write export rows as the desktop's Export button writes them.

    :class:`csv.writer` with its defaults - minimal quoting and ``\\r\\n``
    line endings - which is what ``src/ui/results.py`` hands its file opened
    with ``newline=""``.

    Args:
        rows: The header and the data rows.

    Returns:
        str: The file's text.
    """
    buffer = io.StringIO(newline="")
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


def _download_name(project_id: str) -> str:
    """
    Name the downloaded export after its project.

    Args:
        project_id: The project's file name.

    Returns:
        str: ``<stem> rankings.csv``.
    """
    return f"{Path(project_id).stem} {EXPORT_SUFFIX}"


def _disposition(file_name: str) -> str:
    """
    Write a Content-Disposition that survives any project name.

    Args:
        file_name: The name to save under.

    Returns:
        str: An ASCII ``filename`` for old clients, with anything outside
        printable ASCII (and quotes and backslashes) replaced, and the exact
        name as an RFC 5987 ``filename*``.
    """
    fallback = "".join(
        ch if " " <= ch <= "~" and ch not in '"\\' else "_" for ch in file_name
    )
    return (
        f'attachment; filename="{fallback}"; '
        f"filename*=UTF-8''{quote(file_name, safe='')}"
    )


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/export", name="rankings_export")
async def rankings_export(
    request: Request,
    project_id: str,
    view: View = Depends(view_query),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Answer the rankings as a CSV file: what the sheet's view shows.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        view: ``category`` and ``retired``, read as the sheet reads them - so
            a stale category exports every category, as the sheet draws them.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The file, as an attachment. A project with nothing to rank
        exports the header alone.

    Raises:
        ProjectNotFoundError: If the id names no project in the directory.
        NewerFormatError: If the file was written by a newer application.
        ProjectFormatError: If the file's format version cannot be reached.
        ProjectUnreadableError: If the file will not read as a project.
    """
    entry = registry.open_fresh(project_id)
    session = entry.session
    view = _checked(session.project, view)
    rows = session.export_rows(
        category=view.category or None, include_retired=view.show_retired
    )
    return Response(
        content=export_csv(rows).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": _disposition(_download_name(entry.path.name))},
    )
