"""The History sheet: every vote in a project, and the way to correct one.

One row per vote, newest first, numbered as Compare's Revisions box numbers
them - R1 is the first vote ever cast - with who won, by how much, and when it
was cast. A vote corrected after the fact carries a REVISED tag. The title
block filters by one item, and by one opponent of that item, which is the
address Rankings' weighted record links to: "every vote between these two".

**Correcting a vote is deliberately out of the way.** The sheet is not one of
the four tabs; it is reached from Compare's Revisions box and from a Rankings
record. No key reaches the revise form - not ↵, not the digits Compare votes
with - so it takes a row selected, "Revise R12…" pressed, an outcome chosen
and "Issue revision" pressed. The correction keeps the vote's id, place and
timestamp, so decay goes on counting it as the age it is
(:meth:`~src.app.session.ProjectSession.revise_vote`); "Withdraw" removes it
(:meth:`~src.app.session.ProjectSession.withdraw_vote`), which is what Equal
would have recorded.

**Restore instead of a confirmation.** Each correction is recorded on the
registry entry with what it replaced, and the Last change cell offers
"Restore" while that correction is still the project's last change. Restoring
puts the exact old vote back, and refuses if the file has moved on since
(:meth:`~src.app.session.ProjectSession.restore_revision`).

R numbers are positions, as on Compare: withdrawing R12 makes the old R13 the
new R12. Sentences about a correction therefore name the vote by its content,
fixed when it was made, as well as by its number then.

History shows item names whatever the blinded setting, as Rankings does: it is
the place an unblinded look at the record leads to.
"""

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.app.record import UNKNOWN_OPPONENT_NAME
from src.app.session import VoteNotFoundError
from src.models.project import Project
from src.models.vote import VOTE_WEIGHTS, Vote

from ..deps import Principal, get_current_user, get_registry
from ..registry import LastChange, OpenProject, ProjectRegistry
from ..urls import PROJECTS_PREFIX, project_url
from .compare import STRENGTH_WORDS


logger = logging.getLogger(__name__)

router = APIRouter()

# The slug this sheet is served under. Not one of the four tabs, so no tab is
# marked current while it is drawn.
SHEET = "history"

# The keys the title block lists. Revise is not among them, on purpose: no key
# reaches it.
HISTORY_KEYS = (
    (("↑", "↓"), "select"),
    (("Pg↑↓",), "sheet"),
    (("I",), "item"),
    (("Esc",), "deselect"),
)

# The sheet's columns, in the shape the parts-list macro wants them.
HISTORY_COLUMNS = (
    {"label": "Rev", "width": "3.5rem", "class": "c-find"},
    {"label": "Vote"},
    {"label": "Strength", "width": "8rem"},
    {"label": "Cast", "width": "10.5rem", "class": "n c-phone-hide"},
)

# How many of the newest votes the sheet draws before "Show all".
HISTORY_SHOWN = 50

# The value of `all` that draws every vote. Anything else draws the newest.
SHOW_ALL = "1"

# The tag a corrected vote carries.
TAG_REVISED = "Revised"

# Dates as the sheet and its callouts write them.
DATE_FORMAT = "%Y-%m-%d %H:%M"
CHANGE_TIME_FORMAT = "%H:%M"

# The strengths a revision can record, strongest first: Compare's three.
REVISION_WEIGHTS = tuple(sorted(VOTE_WEIGHTS.values(), reverse=True))

# What `done` says after each change, and the kind each records itself under
# on the registry entry.
DONE_REVISED = "revised"
DONE_WITHDRAWN = "withdrawn"
DONE_RESTORED = "restored"
RESTORABLE = (DONE_REVISED, DONE_WITHDRAWN)

# What `note` says when a post found nothing to do. The value is a key, never
# echoed: the page prints nothing from the query.
NOTE_GONE = "gone"
NOTE_STALE = "stale"
NOTE_SAME = "same"
NOTES = {
    NOTE_GONE: "That vote is no longer in the file, so nothing was changed.",
    NOTE_STALE: "Nothing restored: the vote has changed since.",
    NOTE_SAME: "Nothing changed: that is the outcome already recorded.",
}


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
    Which votes the sheet draws.

    Attributes:
        item: The one item whose votes are drawn, or empty for every vote.
        vs: With ``item``, the one opponent whose votes against it are drawn.
        show_all: Whether every vote is drawn, rather than the newest.
    """

    item: str = ""
    vs: str = ""
    show_all: bool = False

    def query(self) -> dict:
        """
        Spell the view as query parameters.

        Returns:
            dict: ``item``, ``vs`` and ``all``, each only when it is set.
        """
        pairs = (
            ("item", self.item),
            ("vs", self.vs),
            ("all", SHOW_ALL if self.show_all else ""),
        )
        return {key: value for key, value in pairs if value}

    def includes(self, vote: Vote) -> bool:
        """
        Check that the view draws one vote.

        Args:
            vote: The vote.

        Returns:
            bool: True when the vote is drawn, its place in the list aside.
        """
        if self.item and not vote.involves_item(self.item):
            return False
        return not self.vs or vote.involves_item(self.vs)


async def view_query(
    item: str = Query("", description="the one item whose votes to draw"),
    vs: str = Query("", description="with item, the one opponent to draw"),
    all: str = Query("", description="1 to draw every vote"),
) -> View:
    """
    Read the view from a query: the sheet's own, and every fragment's.

    Returns:
        View: The view, before it is checked against the project.
    """
    return View(item=item or "", vs=vs or "", show_all=all == SHOW_ALL)


async def view_form(
    item: str = Form(""),
    vs: str = Form(""),
    all: str = Form(""),
) -> View:
    """
    Read the view a callout's form carries back.

    Returns:
        View: The view, before it is checked against the project.
    """
    return View(item=item or "", vs=vs or "", show_all=all == SHOW_ALL)


def _checked(project: Project, view: View) -> View:
    """
    Drop filters naming items the project does not hold.

    A stale address draws more, never an error: an item that has gone draws
    every vote, and an opponent that has gone draws all of the item's.

    Args:
        project: The project.
        view: The view as the address gave it.

    Returns:
        View: The view the sheet is drawn with.
    """
    item = view.item if project.find_item(view.item) is not None else ""
    vs = (
        view.vs
        if item and view.vs != item and project.find_item(view.vs) is not None
        else ""
    )
    return View(item=item, vs=vs, show_all=view.show_all)


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


def history_url(request: Request, project_id: str, **query) -> str:
    """
    Build an address of the History sheet, for this sheet and its way in.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        **query: ``item``, ``vs``, ``selected``...; empty ones are left out.

    Returns:
        str: The address.
    """
    return project_url(request, project_id, SHEET) + _query_string(query)


def _vote_url(
    request: Request, project_id: str, vote_id: str, verb: str, view: View
) -> str:
    """
    Build the address of one vote's fragment or change.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        vote_id: The vote.
        verb: ``callout``, ``revise``, ``withdraw`` or ``restore``.
        view: The view to carry.

    Returns:
        str: ``.../history/<id>/<verb>``, with the view.
    """
    base = project_url(request, project_id, SHEET)
    return f"{base}/{quote(vote_id, safe='')}/{verb}" + _query_string(view.query())


def _name(project: Project, item_id: str) -> str:
    """
    Name an item a vote refers to.

    Args:
        project: The project.
        item_id: The item.

    Returns:
        str: Its name, or the record's word for an item that has gone.
    """
    item = project.find_item(item_id)
    return item.name if item is not None else UNKNOWN_OPPONENT_NAME


def _strength(weight: float) -> str:
    """
    Say how strong a vote was, in Compare's words.

    Args:
        weight: The vote's weight.

    Returns:
        str: "Much better", "Better", "Slightly better", or ``w 2.5`` for a
        weight Compare does not offer.
    """
    return STRENGTH_WORDS.get(float(weight), f"w {weight:g}")


def _sentence(project: Project, vote: Vote) -> str:
    """
    Say what a vote recorded, as a sentence a Last change cell can keep.

    Args:
        project: The project.
        vote: The vote.

    Returns:
        str: ``Kailh Box Jade over Gateron Oil King · Better``.
    """
    winner = _name(project, vote.winner_id)
    loser = _name(project, vote.loser_id)
    return f"{winner} over {loser} · {_strength(vote.weight)}"


def _numbered(project: Project) -> list:
    """
    Number every vote as Compare does, R1 first.

    Args:
        project: The project.

    Returns:
        list: ``(number, vote)`` pairs, in the order the votes were cast.
    """
    return list(enumerate(project.votes, start=1))


def _row(project: Project, number: int, vote: Vote, callout_url: str) -> dict:
    """
    Turn one vote into the row the template draws.

    Args:
        project: The project.
        number: Its R number.
        vote: The vote.
        callout_url: Where the row's callout comes from.

    Returns:
        dict: The row.
    """
    return {
        "id": vote.id,
        "number": f"R{number}",
        "winner": _name(project, vote.winner_id),
        "loser": _name(project, vote.loser_id),
        "strength": _strength(vote.weight),
        "cast": vote.timestamp.strftime(DATE_FORMAT),
        "revised": vote.revised_at is not None,
        "callout_url": callout_url,
    }


def _items(project: Project) -> list:
    """
    List the items the Item control offers, in name order.

    Args:
        project: The project.

    Returns:
        list: ``(id, label)`` pairs, retired items said so.
    """
    items = sorted(project.items, key=lambda item: (item.name.casefold(), item.id))
    return [
        (item.id, item.name if item.is_active() else f"{item.name} (retired)")
        for item in items
    ]


def _opponents(project: Project, item_id: str) -> list:
    """
    List the items one item has a vote against, for the Against control.

    Args:
        project: The project.
        item_id: The item, or empty when none is chosen.

    Returns:
        list: ``(id, name)`` pairs in name order; empty with no item.
    """
    if not item_id:
        return []
    met = {
        vote.loser_id if vote.winner_id == item_id else vote.winner_id
        for vote in project.votes
        if vote.involves_item(item_id)
    }
    return sorted(
        ((other, _name(project, other)) for other in met),
        key=lambda pair: (pair[1].casefold(), pair[0]),
    )


def _empty_state(project: Project, view: View) -> dict:
    """
    Choose what the drawing area says when no row is drawn.

    Args:
        project: The project.
        view: The view, already checked.

    Returns:
        dict: The ``lead`` and ``detail`` sentences, and whether the box
        offers the way to Compare.
    """
    if not project.votes:
        return {
            "lead": "No votes yet.",
            "detail": "Every vote Compare records is listed here.",
            "open_compare": True,
        }
    if view.vs:
        return {
            "lead": (
                f"{_name(project, view.item)} and {_name(project, view.vs)} "
                "have not been compared."
            ),
            "detail": "Choose another opponent, or All opponents.",
            "open_compare": False,
        }
    return {
        "lead": f"No votes involve {_name(project, view.item)}.",
        "detail": "Choose another item, or All items.",
        "open_compare": False,
    }


def _named_change(entry: OpenProject, done: str, vote_id: str) -> Optional[LastChange]:
    """
    Find the History change the address names, if it is the project's last.

    Args:
        entry: The open project.
        done: Which change the address says finished.
        vote_id: The vote it says it was about.

    Returns:
        Optional[LastChange]: The record, when it is this kind, about this
        vote; None for anything else, which draws no sentence.
    """
    change = entry.last_change
    if change is None or change.kind != done or change.item_id != vote_id:
        return None
    return change


def _find(entry: OpenProject, vote_id: str) -> tuple:
    """
    Find the vote a fragment is about, or answer 404.

    Args:
        entry: The open project.
        vote_id: The vote's id.

    Returns:
        tuple: Its R number and the vote.

    Raises:
        HTTPException: 404 when the project holds no such vote.
    """
    project = entry.session.project
    index = project.vote_index(vote_id)
    if index is None:
        raise HTTPException(status_code=404, detail="No such vote.")
    return index + 1, project.votes[index]


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}", name="history_sheet")
async def history_sheet(
    request: Request,
    project_id: str,
    view: View = Depends(view_query),
    selected: str = Query("", description="the vote to arrive on"),
    done: str = Query("", description="which change just finished"),
    vote: str = Query("", description="the vote that change was about"),
    note: str = Query("", description="why a post changed nothing"),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Draw one project's votes as a parts list, newest first.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        view: ``item``, ``vs`` and ``all``.
        selected: The id of the vote to arrive with selected, its callout
            open. A vote the view does not draw selects nothing.
        done: Which change the redirect that brought the page here made.
        vote: The vote it was about, which together with ``done`` must name
            the project's last change for the sentence to be drawn.
        note: A key of :data:`NOTES`, when a post changed nothing.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The History sheet.

    Raises:
        ProjectNotFoundError: If the id names no project in the directory.
        NewerFormatError: If the file was written by a newer application.
        ProjectFormatError: If the file's format version cannot be reached.
        ProjectUnreadableError: If the file will not read as a project.
    """
    entry = registry.open_fresh(project_id)
    project = entry.session.project
    pid = entry.path.name
    view = _checked(project, view)

    matching = [(n, v) for n, v in _numbered(project) if view.includes(v)]
    matching.reverse()
    drawn = matching if view.show_all else matching[:HISTORY_SHOWN]
    rows = [
        _row(project, n, v, _vote_url(request, pid, v.id, "callout", view))
        for n, v in drawn
    ]

    change = _named_change(entry, done, vote)
    restorable = change is not None and change.kind in RESTORABLE
    context = {
        "project_id": pid,
        "project_name": project.name,
        "file_name": pid,
        "rows": rows,
        "columns": HISTORY_COLUMNS,
        "keys": HISTORY_KEYS,
        "revised_tag": TAG_REVISED,
        "empty": _empty_state(project, view),
        "item": view.item,
        "vs": view.vs,
        "items": _items(project),
        "opponents": _opponents(project, view.item),
        "shown_count": len(drawn),
        "matching_count": len(matching),
        "show_all_params": {**view.query(), "all": SHOW_ALL},
        "last_change": change.label if change is not None else "",
        "change_time": change.time.strftime(CHANGE_TIME_FORMAT) if change else "",
        "restore_url": (
            _vote_url(request, pid, change.item_id, "restore", view)
            if restorable
            else ""
        ),
        "view_fields": view.query(),
        "note": NOTES.get(note, ""),
        "selected": selected if any(row["id"] == selected for row in rows) else "",
        "history_url": project_url(request, pid, SHEET),
        "compare_url": project_url(request, pid, "compare"),
    }
    return _templates(request).TemplateResponse(request, "history.html", context)


@router.get(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{vote_id}}/callout",
    name="history_callout",
)
async def history_callout(
    request: Request,
    project_id: str,
    vote_id: str,
    view: View = Depends(view_query),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return one row's callout: the vote in full, and the way to revise it.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        vote_id: The vote.
        view: The view the sheet is drawn with, carried into the form.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The callout.

    Raises:
        HTTPException: 404 when the project holds no such vote.
    """
    entry = registry.open_fresh(project_id)
    number, found = _find(entry, vote_id)
    project = entry.session.project
    # Restore here as well as in the Last change cell, which on a phone is
    # below every row: the callout is where the eye is after a revision.
    change = entry.last_change
    restorable = (
        change is not None and change.kind == DONE_REVISED and change.item_id == found.id
    )
    context = {
        "restore_url": (
            _vote_url(request, entry.path.name, found.id, "restore", View())
            if restorable
            else ""
        ),
        "view_fields": view.query(),
        "number": f"R{number}",
        "sentence": _sentence(project, found),
        "cast": found.timestamp.strftime(DATE_FORMAT),
        "revised": (
            found.revised_at.strftime(DATE_FORMAT) if found.revised_at else ""
        ),
        "revise_url": _vote_url(request, entry.path.name, found.id, "revise", view),
    }
    return _templates(request).TemplateResponse(
        request, "history/callout_actions.html", context
    )


def _stations(project: Project, vote: Vote) -> list:
    """
    Lay out the six outcomes a revision can choose between.

    Compare's scale without its middle: the vote's current winner is A, on the
    left, strongest first; then B, its loser, weakest first. Equal is not a
    station here - recording no vote is Withdraw, a button of its own.

    Args:
        project: The project.
        vote: The vote being revised.

    Returns:
        list: One mapping per station: the ``value`` posted, the ``side``,
        the ``weight`` in bars, the ``word`` drawn, the ``name`` it is about
        and whether it is what the file ``recorded``.
    """
    sides = (("a", vote.winner_id), ("b", vote.loser_id))
    stations = []
    for side, item_id in sides:
        weights = REVISION_WEIGHTS if side == "a" else tuple(reversed(REVISION_WEIGHTS))
        for weight in weights:
            stations.append({
                "value": f"{side}{weight:g}",
                "side": side,
                "bars": int(weight),
                "word": STRENGTH_WORDS[weight],
                "name": _name(project, item_id),
                "recorded": side == "a" and weight == vote.weight,
            })
    return stations


@router.get(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{vote_id}}/revise",
    name="revise_form",
)
async def revise_form(
    request: Request,
    project_id: str,
    vote_id: str,
    view: View = Depends(view_query),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Return the revise form for one vote, in place of its callout.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        vote_id: The vote.
        view: The view the sheet is drawn with, carried back by the form.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The form.

    Raises:
        HTTPException: 404 when the project holds no such vote.
    """
    entry = registry.open_fresh(project_id)
    number, found = _find(entry, vote_id)
    project = entry.session.project
    pid = entry.path.name
    context = {
        "number": f"R{number}",
        "a_name": _name(project, found.winner_id),
        "b_name": _name(project, found.loser_id),
        "recorded": _sentence(project, found),
        "cast": found.timestamp.strftime(DATE_FORMAT),
        "stations": _stations(project, found),
        "recorded_winner": found.winner_id,
        "revise_action": _vote_url(request, pid, found.id, "revise", View()),
        "withdraw_action": _vote_url(request, pid, found.id, "withdraw", View()),
        "cancel_url": history_url(request, pid, selected=found.id, **view.query()),
        "view_fields": view.query(),
    }
    return _templates(request).TemplateResponse(
        request, "history/callout_revise.html", context
    )


def _back(request: Request, project_id: str, view: View, **query) -> Response:
    """
    Answer a post: back to the sheet, with the view it was made from.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        view: The view the post came from.
        **query: ``selected``, ``done``, ``vote`` or ``note``.

    Returns:
        Response: A 303 to the sheet.
    """
    return RedirectResponse(
        history_url(request, project_id, **query, **view.query()), status_code=303
    )


def _outcome(vote: Vote, outcome: str) -> Optional[tuple]:
    """
    Read a posted station back into a winner and a weight.

    Args:
        vote: The vote as it stands in the file now.
        outcome: The station's value, ``a3`` .. ``b3``, A being the winner
            the form was drawn with.

    Returns:
        Optional[tuple]: ``(winner_id, weight)``, or None for anything that
        is not a station.
    """
    stations = {
        f"{side}{weight:g}": (item_id, weight)
        for side, item_id in (("a", vote.winner_id), ("b", vote.loser_id))
        for weight in REVISION_WEIGHTS
    }
    return stations.get(outcome)


@router.post(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{vote_id}}/revise",
    name="revise_vote",
)
async def revise_vote(
    request: Request,
    project_id: str,
    vote_id: str,
    outcome: str = Form(""),
    recorded: str = Form(""),
    view: View = Depends(view_form),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Record a corrected outcome for one vote.

    The form names its stations relative to the winner it was drawn with, and
    sends that winner back as ``recorded``. If the file's winner has changed
    since - a second tab revised it - the stations no longer mean what the
    person saw, so nothing is changed and the sheet comes back with the vote
    selected, its callout showing the outcome now on file.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        vote_id: The vote.
        outcome: The station chosen.
        recorded: The winner the form was drawn with.
        view: The view the form was opened from.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the sheet.
    """
    with registry.mutate(project_id) as mutation:
        pid = mutation.entry.path.name
        project = mutation.session.project
        index = project.vote_index(vote_id)
        if index is None:
            return _back(request, pid, view, note=NOTE_GONE)
        current = project.votes[index]
        chosen = _outcome(current, outcome)
        if chosen is None or recorded != current.winner_id:
            logger.info("Refused a revision of %r in %s", vote_id, pid)
            return _back(request, pid, view, selected=vote_id, note=NOTE_STALE)

        winner_id, weight = chosen
        revision = mutation.session.revise_vote(vote_id, winner_id, weight)
        if revision is None:
            return _back(request, pid, view, selected=vote_id, note=NOTE_SAME)
        label = (
            f"Revised R{index + 1}: {_sentence(project, revision.after)} "
            f"(was {_sentence(project, revision.before)})"
        )
        mutation.record_change(DONE_REVISED, vote_id, label, revision=revision)
    logger.info("Revised vote %s in %s", vote_id, pid)
    return _back(request, pid, view, selected=vote_id, done=DONE_REVISED, vote=vote_id)


@router.post(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{vote_id}}/withdraw",
    name="withdraw_vote",
)
async def withdraw_vote(
    request: Request,
    project_id: str,
    vote_id: str,
    view: View = Depends(view_form),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Remove one vote, as if Equal had been chosen when it was cast.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        vote_id: The vote.
        view: The view the form was opened from.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the sheet.
    """
    with registry.mutate(project_id) as mutation:
        pid = mutation.entry.path.name
        project = mutation.session.project
        try:
            revision = mutation.session.withdraw_vote(vote_id)
        except VoteNotFoundError:
            return _back(request, pid, view, note=NOTE_GONE)
        label = f"Withdrew R{revision.index + 1}: {_sentence(project, revision.before)}"
        mutation.record_change(DONE_WITHDRAWN, vote_id, label, revision=revision)
    logger.info("Withdrew vote %s from %s", vote_id, pid)
    return _back(request, pid, view, done=DONE_WITHDRAWN, vote=vote_id)


@router.post(
    f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{{vote_id}}/restore",
    name="restore_vote",
)
async def restore_vote(
    request: Request,
    project_id: str,
    vote_id: str,
    view: View = Depends(view_form),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Put back the vote the project's last change revised or withdrew.

    Only that change, and only while the file still shows it: anything since
    - another revision, an undo, a new vote - replaces the record, and the
    vote is then left as it is.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        vote_id: The vote.
        view: The view the sheet was drawn with.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the sheet.
    """
    with registry.mutate(project_id) as mutation:
        pid = mutation.entry.path.name
        project = mutation.session.project
        change = mutation.entry.last_change
        if (
            change is None
            or change.kind not in RESTORABLE
            or change.item_id != vote_id
            or change.revision is None
            or not mutation.session.restore_revision(change.revision)
        ):
            return _back(request, pid, view, selected=vote_id, note=NOTE_STALE)
        before = change.revision.before
        label = (
            f"Restored R{project.vote_index(vote_id) + 1}: {_sentence(project, before)}"
        )
        mutation.record_change(DONE_RESTORED, vote_id, label)
    logger.info("Restored vote %s in %s", vote_id, pid)
    return _back(request, pid, view, selected=vote_id, done=DONE_RESTORED, vote=vote_id)
