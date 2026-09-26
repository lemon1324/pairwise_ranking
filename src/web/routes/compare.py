"""The Compare sheet: two views, a seven-station scale, and the readings.

One pair of items is drawn as View A and View B of a component datasheet, with
the dimensioned scale under them - stations 1 to 7, A much better through
Equal to B much better - and the title block saying how settled the ranking is,
how many votes it rests on, and what the last vote recorded. Ported from
``docs/mockups/compare.html``.

**Every pair on screen has an address.** The pair is the query - ``a`` and
``b``, the ids of the items in View A and View B - so a reload shows the same
pair rather than choosing again, and a vote names the pair it was made on. The
pair is chosen by the session (:meth:`~src.app.session.ProjectSession.next_pair`)
and never here: the sheet asked for with no pair, or with one that can no
longer be compared - an item retired, deleted, or without a slot in blinded
mode - answers with a 303 to the pair the session chooses. When no pair can be
offered the sheet is drawn in its empty state instead.

**The mutations are ordinary form posts answered with a 303**, as on the
register and Items (owner ruling A, §5c of the plan): a vote and an undo each
run in :meth:`~src.web.registry.ProjectRegistry.mutate` and land on the address
of the pair that follows, with ``done`` naming what happened for the receipt.
With JavaScript, htmx sends the same posts, follows the same redirect, and
swaps the frame out of the answer - so the views, the stations and the title
block are replaced in place while the keys, which ``static/js/compare.js``
handles, live outside what is swapped. With JavaScript off the forms post and
the page reloads, which is the same thing drawn whole.

**Skip and Equal record nothing.** Skip is a GET of the sheet with no pair,
which is the session's :meth:`~src.app.session.ProjectSession.skip`; station 4
posts like the others and is answered the same way, without taking the lock.

**The receipt is drawn from the file, and from the registry's memory.** The
last two votes are the file's; which of them the address just recorded, and
the vote an undo just removed, come from the :class:`~src.web.registry.LastChange`
each mutation leaves on the project's entry (ruling C). An address naming any
other change draws the plain receipt.

**A save the file refuses records nothing, and says so.** The registry reads
the project back from the file when a mutation raises, so a vote or undo whose
save failed is gone from memory as well; the route lands on the same pair with
``refused=save`` (or ``undo-save``), the station and a cause from a short fixed
list, and the sheet draws the save warning in place of the receipt, with Retry
posting the same vote or undo again.

**A file another program saved is announced once.** A vote or undo re-reads
a changed file before it writes (the registry's mtime check), and the page it
lands on takes the notice and draws the strip under the bar, full load or htmx
swap alike: the forms carry ``#notice`` out of band.

**Blinded mode draws slots only**: no names, no descriptions, no categories,
and no readings - the settled order and tolerance are not asked for at all.
"""

import errno
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.app.session import NoPairReason, PairOffer, ProjectSession
from src.models.item import Item
from src.models.project import Project
from src.models.vote import Vote

from ..deps import Principal, get_current_user, get_registry
from ..registry import LastChange, OpenProject, ProjectRegistry
from ..urls import PROJECTS_PREFIX, project_url


logger = logging.getLogger(__name__)

router = APIRouter()

# The slug this sheet is served under, and the tab it marks as current.
SHEET = "compare"

# The two mutations' own segments, after the sheet's.
ACTION_VOTE = "vote"
ACTION_UNDO = "undo"

# The keys the title block lists, as the mockup lists them. Each is declared on
# the control it presses and handled by static/js/compare.js.
COMPARE_KEYS = (
    (("1–7",), "vote"),
    (("S",), "skip"),
    (("Ctrl Z",), "undo"),
)

# Which side of the pair a station prefers.
SIDE_A = "a"
SIDE_B = "b"
SIDE_EQUAL = "equal"


@dataclass(frozen=True)
class Station:
    """
    One station of the scale.

    Attributes:
        key: Its number, 1 to 7, which is also its key.
        side: Which view it prefers, or neither.
        weight: The vote weight it records; 0 for Equal, which records none.
        name: What the station says.
    """

    key: int
    side: str
    weight: int
    name: str

    @property
    def shortcuts(self) -> str:
        """
        Spell the station's keys for aria-keyshortcuts.

        Returns:
            str: Its number, and S as well for Equal, which Skip also presses.
        """
        return f"{self.key} S" if self.side == SIDE_EQUAL else str(self.key)

    @property
    def weight_text(self) -> str:
        """
        Write the station's weight as its cell shows it.

        Returns:
            str: ``w 3.0``, or Equal's "no vote · skips".
        """
        return "no vote · skips" if self.side == SIDE_EQUAL else f"w {self.weight:.1f}"


# The scale, strength stepping outward from Equal. The weights are the
# desktop's 3/2/1 (src/models/vote.py's VOTE_WEIGHTS).
STATIONS = (
    Station(1, SIDE_A, 3, "A much better"),
    Station(2, SIDE_A, 2, "A better"),
    Station(3, SIDE_A, 1, "A slightly better"),
    Station(4, SIDE_EQUAL, 0, "Equal"),
    Station(5, SIDE_B, 1, "B slightly better"),
    Station(6, SIDE_B, 2, "B better"),
    Station(7, SIDE_B, 3, "B much better"),
)
STATION_BY_KEY = {station.key: station for station in STATIONS}

# How a receipt row names a vote's weight. A weight the web never records - a
# file written elsewhere - is written as a figure instead.
STRENGTH_WORDS = {3.0: "Much better", 2.0: "Better", 1.0: "Slightly better"}

# What `done` says after each mutation, and the kind each records itself under
# on the registry entry. Deliberately not among Items' DONE_VERBS: after a vote
# the Items Last change cell falls back to the modified time, which is right -
# the vote was the last change.
DONE_VOTED = "voted"
DONE_UNDONE = "undone"

# The value of `refused` a vote with no such station lands on. The station
# itself is never echoed: the page prints nothing from the query.
REFUSED_STATION = "station"
REFUSED_STATION_NOTE = "Nothing recorded: the scale runs from 1 to 7."

# The values of `refused` a vote and an undo land on when the file would not
# take the save. The registry has already put the open project back to what
# the file holds, so the page is drawn from the truth and says what did not
# happen. A vote's address also carries its `station`, which Retry posts again.
REFUSED_SAVE = "save"
REFUSED_UNDO_SAVE = "undo-save"

# Why a save failed, as the address says it (`cause`) and as the warning words
# it. Only these are ever printed: the address chooses among them and never
# supplies text of its own. Any other failure is described without a cause.
CAUSE_DENIED = "denied"
CAUSE_FULL = "full"
CAUSE_WORDS = {
    CAUSE_DENIED: "permission denied",
    CAUSE_FULL: "the disk is full",
}

# The save warning, by what failed: its lead, and what it says was not done.
SAVE_FAILURES = {
    REFUSED_SAVE: ("Vote not saved.", "Nothing was recorded; the pair is still open."),
    REFUSED_UNDO_SAVE: ("Undo not saved.", "Nothing was undone; the vote still stands."),
}

# How many votes the receipt shows: the latest and the one before it.
RECEIPT_ROWS = 2

# How the receipt writes a vote's time.
RECEIPT_TIME_FORMAT = "%H:%M"

# A reading with nothing to read: no votes yet, or fewer than two ranked items.
NO_READING = "—"

# What the receipt says when it has no rows, by why.
RECEIPT_NO_VOTES = "No votes yet. The first vote you record appears here."
RECEIPT_NO_PAIR = "No pair to compare, so there is nothing to record or undo."

# The empty state's lead, by the session's reason.
EMPTY_LEADS = {
    NoPairReason.TOO_FEW_ITEMS: "Add at least 2 items to start comparing.",
    NoPairReason.BLINDED_NO_IDENTIFIERS: "Give at least 2 items a slot to compare blinded.",
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


def _sheet_url(
    request: Request, project_id: str, pair: Optional[tuple] = None, **query
) -> str:
    """
    Build an address of the sheet.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        pair: The two items to draw, in View A and View B order, or None for
            the sheet with no pair - which chooses one.
        **query: Further parameters; empty ones are left out.

    Returns:
        str: The path, with the proxy prefix and the query.
    """
    pairs = []
    if pair is not None:
        pairs = [("a", pair[0].id), ("b", pair[1].id)]
    pairs += [(key, str(value)) for key, value in query.items() if value]
    suffix = f"?{urlencode(pairs)}" if pairs else ""
    return f"{project_url(request, project_id, SHEET)}{suffix}"


def _redirect(url: str) -> Response:
    """
    Answer with a 303 to one of this sheet's addresses.

    Args:
        url: The address.

    Returns:
        Response: The redirect.
    """
    return RedirectResponse(url, status_code=303)


def _station(raw: str) -> Optional[Station]:
    """
    Read a station from a form, leniently.

    Surrounding space and a whole-number spelling such as ``3.0`` are
    accepted; anything else, or a number off the scale, is no station.

    Args:
        raw: The posted value.

    Returns:
        Optional[Station]: The station, or None.
    """
    try:
        number = float((raw or "").strip())
    except ValueError:
        return None
    if not number.is_integer():
        return None
    return STATION_BY_KEY.get(int(number))


def _view(item: Item, blinded: bool) -> dict:
    """
    Describe one item as its view draws it.

    Args:
        item: The item.
        blinded: Whether only its slot may be shown.

    Returns:
        dict: The slot, and in open mode the name, description and category.
        Blinded, the name is not in the context at all, so no template can
        print it by mistake.
    """
    if blinded:
        return {"slot": item.identifier}
    return {
        "slot": item.identifier,
        "name": item.name,
        "description": item.description,
        "category": item.category,
    }


def _mention(item: Optional[Item], blinded: bool, first: bool) -> str:
    """
    Name one item in a receipt row.

    Args:
        item: The item, or None when the project no longer holds it.
        blinded: Whether it may only be named by its slot.
        first: Whether it opens the sentence.

    Returns:
        str: Its name, or ``Slot 12`` / ``slot 12`` in blinded mode.
    """
    if item is None:
        return "A deleted item" if first else "a deleted item"
    if not blinded:
        return item.name
    if not item.identifier:
        return "An item with no slot" if first else "an item with no slot"
    return f"{'Slot' if first else 'slot'} {item.identifier}"


def _strength(weight: float) -> str:
    """
    Name a vote's weight as the receipt does.

    Args:
        weight: The vote's weight.

    Returns:
        str: "Much better", "Better", "Slightly better", or ``w 2.5``.
    """
    return STRENGTH_WORDS.get(float(weight), f"w {weight:g}")


def _receipt_row(project: Project, vote: Vote, number: int, blinded: bool) -> dict:
    """
    Describe one revision row.

    Args:
        project: The project, for the items' names.
        vote: The vote.
        number: Its revision number, from 1.
        blinded: Whether items are named by slot only.

    Returns:
        dict: The row's number, sentence, strength and time.
    """
    winner = project.find_item(vote.winner_id)
    loser = project.find_item(vote.loser_id)
    return {
        "number": f"R{number}",
        "text": f"{_mention(winner, blinded, True)} over {_mention(loser, blinded, False)}",
        "strength": _strength(vote.weight),
        "time": vote.timestamp.strftime(RECEIPT_TIME_FORMAT),
        "previous": False,
        "new": False,
        "undone": False,
        "reoffered": False,
    }


def _named_change(entry: OpenProject, done: str, vote_id: str) -> Optional[LastChange]:
    """
    Find the Compare change the address names, if it is the project's last.

    Args:
        entry: The open project.
        done: Which mutation the address says finished.
        vote_id: The vote it says it recorded or removed.

    Returns:
        Optional[LastChange]: The record, when it is this kind, about this
        vote, and still describes the file: a vote that is still the file's
        last, or an undo whose vote is still gone.
    """
    change = entry.last_change
    if (
        change is None
        or change.kind != done
        or change.vote is None
        or change.vote.id != vote_id
    ):
        return None
    votes = entry.session.project.votes
    if done == DONE_VOTED and votes and votes[-1].id == change.vote.id:
        return change
    if done == DONE_UNDONE and all(vote.id != change.vote.id for vote in votes):
        return change
    return None


def _receipt(
    entry: OpenProject, done: str, vote_id: str, pair: Optional[tuple], blinded: bool
) -> list:
    """
    Build the revision rows: the file's last two votes, or the undone one.

    Args:
        entry: The open project.
        done: Which mutation the address says finished.
        vote_id: The vote the address says it recorded or removed.
        pair: The pair on screen, or None.
        blinded: Whether items are named by slot only.

    Returns:
        list: Up to two rows, oldest first. After a vote the latest is new;
        after an undo the latest is the vote that went, struck through, tagged
        as re-offered when the pair on screen is its pair.
    """
    project = entry.session.project
    votes = project.votes
    change = _named_change(entry, done, vote_id)

    rows = [
        _receipt_row(project, vote, number, blinded)
        for number, vote in enumerate(votes, start=1)
    ]
    if change is not None and done == DONE_UNDONE:
        undone = _receipt_row(project, change.vote, len(votes) + 1, blinded)
        undone["undone"] = True
        on_screen = {item.id for item in pair} if pair is not None else set()
        undone["reoffered"] = on_screen == {change.vote.winner_id, change.vote.loser_id}
        rows.append(undone)
    elif change is not None:
        rows[-1]["new"] = True

    rows = rows[-RECEIPT_ROWS:]
    for row in rows[:-1]:
        row["previous"] = True
    return rows


def _readings(session: ProjectSession, blinded: bool) -> Optional[dict]:
    """
    Read how settled the ranking is, for the two reading cells.

    Args:
        session: The session.
        blinded: Whether the readings are hidden.

    Returns:
        Optional[dict]: ``settled`` as ``31/41`` and ``tolerance`` as ``±38``,
        each a dash when there is nothing to read; or None in blinded mode,
        where the reading is never taken at all.
    """
    if blinded:
        return None
    reading = session.confidence() if session.project.votes else None
    if reading is None:
        return {"settled": NO_READING, "tolerance": NO_READING}
    return {
        "settled": f"{reading.settled}/{reading.neighbours}",
        "tolerance": (
            f"±{round(reading.tolerance)}" if reading.tolerance is not None else NO_READING
        ),
    }


def _empty_state(project: Project, reason: NoPairReason) -> dict:
    """
    Say why there is no pair, and what would make one.

    Args:
        project: The project.
        reason: The session's reason.

    Returns:
        dict: The lead sentence and the detail under it.
    """
    active = project.active_items()
    count = len(active)
    if reason == NoPairReason.BLINDED_NO_IDENTIFIERS:
        slotted = sum(1 for item in active if item.has_identifier())
        detail = f"This project has {count} active items; {slotted} of them have a slot."
    elif count == 0:
        detail = "This project has no active items."
    else:
        detail = f"This project has {count} active item{'s' if count != 1 else ''}."
    return {"lead": EMPTY_LEADS[reason], "detail": detail}


def _cause(error: OSError) -> str:
    """
    Name why a save failed, in the address's own few words.

    Args:
        error: What the save raised.

    Returns:
        str: ``denied``, ``full``, or an empty string for anything else.
    """
    if isinstance(error, PermissionError):
        return CAUSE_DENIED
    if error.errno == errno.ENOSPC:
        return CAUSE_FULL
    return ""


def _save_failure(
    refused: str, cause: str, station: str, file_name: str, vote_url: str, undo_url: str
) -> Optional[dict]:
    """
    Describe the save warning an address asks for, and what Retry sends.

    Args:
        refused: The address's ``refused``.
        cause: Its ``cause``: one of the CAUSE_WORDS keys, or anything else
            for a warning with no cause in it.
        station: Its ``station``, which a failed vote's Retry posts again.
        file_name: The project's file name, which the warning names.
        vote_url: Where a vote posts.
        undo_url: Where an undo posts.

    Returns:
        Optional[dict]: The warning's lead and sentence, and Retry's action and
        station (None when the station is not one a vote records, in which
        case the warning has no Retry: the stations themselves try again); or
        None when the address names no failed save.
    """
    if refused not in SAVE_FAILURES:
        return None
    lead, outcome = SAVE_FAILURES[refused]
    words = CAUSE_WORDS.get(cause)
    written = f"Couldn’t write {file_name}{': ' + words if words else ''}."
    retry = None
    if refused == REFUSED_UNDO_SAVE:
        retry = {"url": undo_url, "station": None}
    else:
        chosen = _station(station)
        if chosen is not None and chosen.side != SIDE_EQUAL:
            retry = {"url": vote_url, "station": chosen.key}
    return {"lead": lead, "text": f"{written} {outcome}", "retry": retry}


def _notice(file_name: str, votes_changed: int, pair_is_new: bool) -> dict:
    """
    Word the changed-on-disk notice.

    Args:
        file_name: The project's file name.
        votes_changed: How many votes the reload added, less those it removed.
        pair_is_new: Whether the pair drawn is not the one the page posted
            from, which is so after every vote and undo that was carried out.

    Returns:
        dict: The notice's lead and sentence.
    """
    if votes_changed:
        count = abs(votes_changed)
        change = f": {count} vote{'s' if count != 1 else ''} {'added' if votes_changed > 0 else 'removed'}"
    else:
        change = ""
    text = f"{file_name} was saved by another program and has been reloaded{change}."
    if pair_is_new:
        text += " The pair below is new."
    return {"lead": "File changed on disk.", "text": text}


def _pairs_compared(stats: Optional[dict]) -> str:
    """
    Write the Pairs compared figure.

    Args:
        stats: The offer's comparison statistics, or None with no pair.

    Returns:
        str: ``118 of 861``, or a dash.
    """
    if not stats:
        return NO_READING
    return f"{stats['compared_pairs']} of {stats['total_possible_pairs']}"


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}", name="compare_sheet")
async def compare_sheet(
    request: Request,
    project_id: str,
    a: str = Query("", description="the item in View A"),
    b: str = Query("", description="the item in View B"),
    done: str = Query("", description="which mutation just finished"),
    vote_id: str = Query("", alias="vote", description="the vote it recorded or removed"),
    refused: str = Query("", description="what a refused vote got wrong"),
    station: str = Query("", description="the station a vote that failed to save pressed"),
    cause: str = Query("", description="why a save failed"),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Draw one pair, or choose one and redirect to it.

    Every page drawn here takes the registry's changed-on-disk notice, full
    load or htmx swap alike: the notice strip sits outside the frame, and the
    sheet's forms carry it into the page out of band.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        a: The id of the item in View A.
        b: The id of the item in View B.
        done: "voted" or "undone", for the receipt; anything else, or a change
            that is no longer the project's last, draws the plain receipt.
        vote_id: ``vote``, the id of the vote ``done`` is about. The address
            has to name it: "the last vote" names a different one after every
            vote.
        refused: "station" after a vote with no such station; "save" or
            "undo-save" after a vote or an undo the file would not take.
        station: After a failed vote, its station, which Retry posts again.
        cause: After a failed save, "denied" or "full"; anything else says
            no cause.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The sheet; a 303 to the session's pair when the address
        names none that can be compared; or the empty state when there is no
        pair to offer at all.

    Raises:
        ProjectNotFoundError: If the id names no project in the directory.
        NewerFormatError: If the file was written by a newer application.
        ProjectFormatError: If the file's format version cannot be reached.
        ProjectUnreadableError: If the file will not read as a project.
    """
    entry = registry.open(project_id)
    session = entry.session
    project = session.project
    pid = entry.path.name

    offer: Optional[PairOffer] = session.offer_pair(a, b) if a and b else None
    if offer is None:
        offer = session.next_pair()
        if offer.has_pair:
            return _redirect(_sheet_url(request, pid, offer.pair))

    blinded = project.settings.blinded_comparison_mode
    pair = offer.pair
    votes = project.votes
    today = datetime.now().date()
    vote_url = project_url(request, pid, f"{SHEET}/{ACTION_VOTE}")
    undo_url = project_url(request, pid, f"{SHEET}/{ACTION_UNDO}")
    save_failure = (
        _save_failure(refused, cause, station, pid, vote_url, undo_url) if pair else None
    )
    # Read before taking: taking the notice clears the count that goes with it.
    votes_changed = entry.votes_changed_on_disk
    notice = (
        _notice(pid, votes_changed, pair_is_new=save_failure is None)
        if entry.take_reload_notice()
        else None
    )
    context = {
        "project_id": pid,
        "project_name": project.name,
        "file_name": pid,
        "keys": COMPARE_KEYS,
        "stations": STATIONS,
        "side_a": SIDE_A,
        "side_b": SIDE_B,
        "side_equal": SIDE_EQUAL,
        "blinded": blinded,
        "pair_ids": {"a": pair[0].id, "b": pair[1].id} if pair else {"a": "", "b": ""},
        "views": [_view(item, blinded) for item in pair] if pair else [],
        "empty": _empty_state(project, offer.reason) if pair is None else None,
        "readings": _readings(session, blinded),
        "vote_count": len(votes),
        "today_count": sum(1 for vote in votes if vote.timestamp.date() == today),
        "pairs_compared": _pairs_compared(offer.stats),
        "receipt": _receipt(entry, done, vote_id, pair, blinded) if pair else [],
        "receipt_empty": RECEIPT_NO_VOTES if pair else RECEIPT_NO_PAIR,
        "refused_note": REFUSED_STATION_NOTE if pair and refused == REFUSED_STATION else "",
        "can_undo": bool(pair) and bool(votes),
        "save_failure": save_failure,
        "notice": notice,
        "here_url": _sheet_url(request, pid, pair) if pair else project_url(request, pid, SHEET),
        "compare_url": project_url(request, pid, SHEET),
        "vote_url": vote_url,
        "undo_url": undo_url,
        "items_url": project_url(request, pid, "items"),
        "settings_url": project_url(request, pid, "settings"),
    }
    return _templates(request).TemplateResponse(request, "compare.html", context)


@router.post(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{ACTION_VOTE}", name="vote")
async def vote(
    request: Request,
    project_id: str,
    a: str = Form("", description="the item in View A"),
    b: str = Form("", description="the item in View B"),
    station: str = Form("", description="the station pressed, 1 to 7"),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Record a vote on the pair a page was drawn with, and move to the next.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        a: The id of the item in View A.
        b: The id of the item in View B.
        station: The station, 1 to 7. Equal (4) records nothing and moves on,
            as Skip does. Anything off the scale records nothing and lands back
            on the same pair with ``refused=station``.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the next pair with ``done=voted``; to the session's
        pair when the posted one can no longer be compared - a second tab
        retired one of its items, say - with nothing recorded; or, when the
        file would not take the save, back to the same pair with
        ``refused=save``, the station and the cause, nothing recorded in the
        file or in memory.
    """
    chosen = _station(station)
    if chosen is None or chosen.side == SIDE_EQUAL:
        entry = registry.open(project_id)
        pid = entry.path.name
        if chosen is None:
            logger.info("Refused a vote on station %r in %s", station, pid)
            offer = entry.session.offer_pair(a, b) if a and b else None
            pair = offer.pair if offer is not None else None
            return _redirect(_sheet_url(request, pid, pair, refused=REFUSED_STATION))
        offer = entry.session.skip()
        return _redirect(_sheet_url(request, pid, offer.pair if offer.has_pair else None))

    pid = registry.resolve(project_id).name
    drawn = None
    try:
        with registry.mutate(project_id) as mutation:
            offer = mutation.session.offer_pair(a, b) if a and b else None
            if offer is None:
                logger.info("Ignored a vote on %r and %r in %s: not comparable", a, b, pid)
                return _redirect(_sheet_url(request, pid))
            drawn = offer.pair
            first, second = drawn
            winner, loser = (first, second) if chosen.side == SIDE_A else (second, first)
            recorded = mutation.session.vote(winner.id, loser.id, float(chosen.weight))
            mutation.record_change(
                DONE_VOTED,
                winner.id,
                f"{winner.name} over {loser.name}",
                vote=recorded,
                sides=(first.id, second.id),
            )
            following = mutation.session.next_pair()
    except OSError as error:
        # The registry has already read the project back from the file, so
        # the vote is gone from memory as it never reached the disk.
        logger.warning("Could not save a vote in %s: %s", pid, error)
        return _redirect(
            _sheet_url(
                request,
                pid,
                drawn,
                refused=REFUSED_SAVE,
                station=chosen.key,
                cause=_cause(error),
            )
        )
    logger.info("Recorded %s over %s in %s", winner.id, loser.id, pid)
    return _redirect(
        _sheet_url(
            request,
            pid,
            following.pair if following.has_pair else None,
            done=DONE_VOTED,
            vote=recorded.id,
        )
    )


def _undone_sides(change: Optional[LastChange], undone: Vote, pair: tuple) -> tuple:
    """
    Put an undone vote's pair back the way it was drawn.

    The session re-offers the pair winner first, because a vote knows only
    who won. When the vote was recorded here, its record says which item was
    in View A, and the pair goes back on those sides: pressing 7 and undoing
    it should not swap the views.

    Args:
        change: The project's last change, before the undo replaces it.
        undone: The vote the undo removed.
        pair: The session's re-offered pair, winner first.

    Returns:
        tuple: The pair, in View A and View B order.
    """
    if (
        change is not None
        and change.kind == DONE_VOTED
        and change.vote is not None
        and change.vote.id == undone.id
        and change.sides == (pair[1].id, pair[0].id)
    ):
        return (pair[1], pair[0])
    return pair


@router.post(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}/{ACTION_UNDO}", name="undo")
async def undo(
    request: Request,
    project_id: str,
    a: str = Form("", description="the item in View A"),
    b: str = Form("", description="the item in View B"),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Remove the project's most recent vote and offer its pair again.

    Undo is global per project, as on the desktop: it takes back the last vote
    in the file, whichever tab or program recorded it.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        a: The id of the item in View A of the page it was pressed on.
        b: The id of the item in View B.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to the undone vote's pair with ``done=undone`` - or to
        the session's next pair when that one can no longer be compared; with
        nothing to undo, back to the pair it was pressed on; and when the file
        would not take the save, back to that pair with ``refused=undo-save``
        and the cause, the vote still standing.
    """
    pid = registry.resolve(project_id).name
    try:
        with registry.mutate(project_id) as mutation:
            before = mutation.entry.last_change
            result = mutation.session.undo()
            if result is None:
                logger.info("Nothing to undo in %s", pid)
                offer = mutation.session.offer_pair(a, b) if a and b else None
                return _redirect(
                    _sheet_url(request, pid, offer.pair if offer is not None else None)
                )
            if result.pair is not None:
                pair = _undone_sides(before, result.vote, result.pair)
            else:
                pair = result.offer.pair
            project = mutation.session.project
            winner = project.find_item(result.vote.winner_id)
            loser = project.find_item(result.vote.loser_id)
            mutation.record_change(
                DONE_UNDONE,
                result.vote.winner_id,
                f"{_mention(winner, False, True)} over {_mention(loser, False, False)}",
                vote=result.vote,
                sides=tuple(item.id for item in pair) if pair else (),
            )
    except OSError as error:
        # As for a vote: the registry has put the vote back from the file.
        logger.warning("Could not save an undo in %s: %s", pid, error)
        offer = registry.open(project_id).session.offer_pair(a, b) if a and b else None
        return _redirect(
            _sheet_url(
                request,
                pid,
                offer.pair if offer is not None else None,
                refused=REFUSED_UNDO_SAVE,
                cause=_cause(error),
            )
        )
    logger.info("Undid vote %s in %s", result.vote.id, pid)
    return _redirect(
        _sheet_url(request, pid, pair, done=DONE_UNDONE, vote=result.vote.id)
    )
