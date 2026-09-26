"""The Settings sheet: a specification sheet of the project's parameters.

One ruled table of the algorithm's parameters, grouped as the mockup groups
them, each with its value, its default and its range; the slot list in a panel
of its own; and a title block whose Status cell says what is saved, what has
changed and what must be fixed. Ported from ``docs/mockups/settings.html``.

**Every state of the sheet has an address**, because Save is a plain form post
that answers 303 (ruling A) and a refused draft has to come back drawn:

- ``GET {settings}`` draws the saved values.
- ``GET {settings}?draft=1&<field>=<value>...`` draws a draft: each numeric
  field as typed (a field left out reads as its saved value) and each switch on
  only when present - a form's own semantics. Every value is validated as it is
  drawn, so a refused post and a hand-written address draw the same error. A
  refused post adds ``submitted=1``, which also puts the caret in the first
  field in error, as the mockup's Save does; without it the page stays at the
  top, so the state can be photographed.
- ``GET {settings}?reset=1`` fills every parameter with its default and leaves
  the slot list alone, saving nothing: the mockup's Reset. With JavaScript the
  Reset cell does this in place; without it the cell is a GET submit here.
- ``GET {settings}?done=saved`` is where a save lands. It says "Saved." only
  while the registry's last change for the project is that save (ruling C).

**Validation is the model's range with the mockup's words.** A value is read
leniently from text (:func:`parse_value`), must be a number, a whole number for
the top-tier size, and inside :data:`src.models.settings.LIMITS`: nothing
negative, the cross-category rate from 0 to 1, a top-tier size of at least 1,
no upper caps. The session refuses anything else again on the way in.

**Change marks are computed against the saved values embedded in the page.**
The server draws them for the address it was asked for, and every input carries
its saved value, its default and its two error sentences, so
``static/js/settings.js`` redraws the marks, the errors and the Status cell as
the values are typed, and disables Save while there is nothing to save or
something to fix. It never validates by rules of its own beyond those sentences
and :data:`NUMBER_PATTERN`.

**The slot table** (phase 8c) is the comma-separated list, plain names only,
and a board of one tile per listed slot. Each tile is a small input holding the
slot's short label (owner answer 1): empty, it shows the first two characters
as its placeholder and stores nothing. Tiles post as ``label:<slot name>``. A
draft carries the list as ``slots`` and each label that differs from the saved
one under the same names; a slot with no ``label:`` entry keeps its saved
label, so a slot added without JavaScript (no tile yet) gets none, and a tile
posted for a slot no longer listed is dropped. The labels are checked by
:func:`~src.app.slots.check_slot_labels`: at most two characters, and never a
label another slot is drawn with, derived ones included. Two *derived* labels
colliding is a warning on the tiles, not a refusal. A slot listed twice is a
warning too; saving drops the repeat.
"""

import json
import logging
import math
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.app.slots import (
    SlotLabelError,
    check_slot_labels,
    entered_slot_labels,
    format_slot_list,
    label_collisions,
    label_owner,
    parse_slot_list,
    short_label,
)
from src.models.project import SLOT_LABEL_MAX_LENGTH, Project
from src.models.settings import LIMITS, Limit, Settings

from ..deps import Principal, get_current_user, get_registry
from ..registry import LastChange, OpenProject, ProjectRegistry
from ..urls import PROJECTS_PREFIX, project_url


logger = logging.getLogger(__name__)

router = APIRouter()

# The slug this sheet is served under, and the tab it marks as current.
SHEET = "settings"

# The keys the title block lists: the mockup's three.
SETTINGS_KEYS = (
    (("Tab",), "next"),
    (("Ctrl S",), "save"),
    (("Esc",), "leave"),
)

# How a field's value is typed: a weight (×), a half-life in days, the
# top-tier size (a whole number), the cross-category rate, or a switch.
KIND_WEIGHT = "weight"
KIND_DAYS = "days"
KIND_COUNT = "count"
KIND_RATE = "rate"
KIND_SWITCH = "switch"


@dataclass(frozen=True)
class Field:
    """
    One parameter row of the table.

    Attributes:
        key: The setting's attribute name, which is also the form field's.
        name: The parameter's name, as the table and the Status cell say it.
        help: The one-line explanation under the name.
        kind: How the value is typed and written (``KIND_*``).
        unit: The unit the Range column writes after the bound, if any.
    """

    key: str
    name: str
    help: str
    kind: str
    unit: str = ""

    @property
    def limit(self) -> Optional[Limit]:
        """The model's range for the field, or None for a switch."""
        return LIMITS.get(self.key)


# The table, as the mockup groups it. Names and help are the mockup's, which
# are the README's.
GROUPS = (
    ("Pair selection weights", (
        Field("weight_uncertainty", "Uncertainty", "Prefer pairs whose order is least certain.", KIND_WEIGHT),
        Field("weight_connectivity", "Connectivity", "Bonus for pairs that join groups never compared with each other.", KIND_WEIGHT),
        Field("weight_freshness", "Freshness", "Revisit pairs whose last vote is old.", KIND_WEIGHT),
        Field("weight_uncompared", "Uncompared", "Bonus for items with few comparisons.", KIND_WEIGHT),
    )),
    ("Vote decay", (
        Field("decay_timescale_days", "Half-life", "A vote counts half after this long. 0 turns decay off.", KIND_DAYS, "days"),
    )),
    ("Top-tier focus", (
        Field("top_tier_mode", "Top-tier focus", "Spend more comparisons near the top of the ranking.", KIND_SWITCH),
        Field("top_tier_count", "Top-tier size", "How many top-ranked items count as the top tier.", KIND_COUNT, "items"),
        Field("top_tier_weight", "Top-tier weight", "Extra weight for pairs involving the top tier.", KIND_WEIGHT),
    )),
    ("Category comparisons", (
        Field("cross_category_rate", "Cross-category rate", "Share of comparisons that may cross categories. 0 never, 1 ignores categories.", KIND_RATE),
    )),
    ("Comparison mode", (
        Field("blinded_comparison_mode", "Blinded", "Show only slot identifiers when comparing. Items without a slot are skipped.", KIND_SWITCH),
    )),
)
FIELDS = tuple(field for _, group in GROUPS for field in group)

# What a number may look like when typed: digits with an optional point and
# exponent. Deliberately narrower than float(), which also takes "nan", "inf"
# and "1_000"; settings.js tests the same pattern, so the two agree on what a
# number is.
NUMBER_PATTERN = r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$"
_NUMBER = re.compile(NUMBER_PATTERN)

# The two errors that do not depend on the field. settings.js writes the same
# sentences; the per-field ones travel on each input.
ERROR_NUMBER = "Enter a number."
ERROR_WHOLE = "Enter a whole number."

# The values a switch reads as on, from a form ("on") or an address ("1").
SWITCH_ON = frozenset({"1", "on", "true"})

# The value of `draft` and `reset` that means yes. Anything else is ignored:
# a mistyped address draws the saved values, not an error page.
YES = "1"

# What a save records itself as, and what the address it lands on says.
DONE_SAVED = "saved"

# How the Status cell writes the project's modified time, and a save's time.
MODIFIED_FORMAT = "%Y-%m-%d %H:%M"
CHANGE_TIME_FORMAT = "%H:%M"

# The sentences the Status cell leads with after a save and after Reset.
NOTE_SAVED = "Saved."
NOTE_RESET = "Defaults filled in; the slot list is unchanged. Save to apply."

# What the Status cell calls the slot table when its list or labels changed.
SLOTS_NAME = "Slots"

# A tile's field name is this followed by the slot's name.
LABEL_PREFIX = "label:"

# The two ways a tile's label is refused. settings.js reads both from the
# board and fills in the same names.
ERROR_LABEL_LONG = f"Use at most {SLOT_LABEL_MAX_LENGTH} characters."
ERROR_LABEL_TAKEN = "Slot {slot} already shows {label}."


def _templates(request: Request) -> Jinja2Templates:
    """
    Reach the application's template environment.

    Args:
        request: The incoming request.

    Returns:
        Jinja2Templates: The environment the factory built.
    """
    return request.app.state.templates


def _bound(value: float) -> str:
    """
    Write a range's bound without a needless ".0".

    Args:
        value: The bound.

    Returns:
        str: ``0``, ``1``, ``0.5``.
    """
    return f"{value:g}"


def format_value(field: Field, value) -> str:
    """
    Write a value as its input and the Default column show it.

    Every form must read back as the same number, or saving an unchanged
    form would change it: the mockup's rate to two places becomes the value's
    own spelling when two places would round it.

    Args:
        field: The field.
        value: Its value.

    Returns:
        str: "On"/"Off" for a switch; a whole number for the size, and for a
        whole half-life; the rate to two places; a weight as Python spells a
        float, which keeps one place for a whole one (1.0, 2.0).
    """
    if field.kind == KIND_SWITCH:
        return "On" if value else "Off"
    if field.kind == KIND_COUNT:
        return str(int(value))
    number = float(value)
    if field.kind == KIND_DAYS and number.is_integer():
        return str(int(number))
    if field.kind == KIND_RATE and float(f"{number:.2f}") == number:
        return f"{number:.2f}"
    return repr(number)


def range_text(field: Field) -> str:
    """
    Write the Range column.

    Args:
        field: The field.

    Returns:
        str: "on / off", "0–1", or "≥ 0" with the unit when it is not "×".
    """
    limit = field.limit
    if limit is None:
        return "on / off"
    if limit.maximum is not None:
        return f"{_bound(limit.minimum)}–{_bound(limit.maximum)}"
    unit = f" {field.unit}" if field.unit else ""
    return f"≥ {_bound(limit.minimum)}{unit}"


def empty_error(field: Field) -> str:
    """
    Say what an empty field needs.

    Args:
        field: A numeric field.

    Returns:
        str: "Enter a value from 0 to 1." or "Enter a value of 0 or more."
    """
    limit = field.limit
    if limit.maximum is not None:
        return f"Enter a value from {_bound(limit.minimum)} to {_bound(limit.maximum)}."
    return f"Enter a value of {_bound(limit.minimum)} or more."


def range_error(field: Field) -> str:
    """
    Say what a number outside the range must be.

    Args:
        field: A numeric field.

    Returns:
        str: "Must be between 0 and 1." or "Must be 0 or more."
    """
    limit = field.limit
    if limit.maximum is not None:
        return f"Must be between {_bound(limit.minimum)} and {_bound(limit.maximum)}."
    return f"Must be {_bound(limit.minimum)} or more."


def parse_value(field: Field, raw: str):
    """
    Read one typed value, leniently: surrounding space is ignored.

    Args:
        field: The field.
        raw: The text as typed; for a switch, the posted value or empty.

    Returns:
        tuple: ``(value, error)``, exactly one of them set: a number (an int
        for the size) or a bool, or the sentence saying what is wrong.
    """
    if field.kind == KIND_SWITCH:
        return raw.strip().lower() in SWITCH_ON, None
    text = raw.strip()
    if not text:
        return None, empty_error(field)
    if not _NUMBER.match(text):
        return None, ERROR_NUMBER
    number = float(text)
    if not math.isfinite(number):
        # "1e999" matches the pattern and overflows to infinity.
        return None, ERROR_NUMBER
    limit = field.limit
    if limit.whole and not number.is_integer():
        return None, ERROR_WHOLE
    if not limit.allows(number):
        return None, range_error(field)
    return (int(number) if limit.whole else number), None


@dataclass(frozen=True)
class Row:
    """
    One parameter as the table draws it.

    Attributes:
        field: The parameter.
        raw: What its input holds: the text typed, or "1"/"" for a switch.
        value: The value read from it, or None when it is in error.
        error: The sentence under it, or empty.
        changed: Whether it differs from the saved value.
        saved: The saved value, written as an input would hold it.
        default: The default, written as the Default column shows it.
        default_raw: The default, written as an input would hold it, which
            is what Reset puts there.
    """

    field: Field
    raw: str
    value: object
    error: str
    changed: bool
    saved: str
    default: str
    default_raw: str

    @property
    def checked(self) -> bool:
        """Whether a switch is drawn on."""
        return bool(self.value)


def _raw_of(field: Field, value) -> str:
    """
    Put a value in its input: formatted, or "1"/"" for a switch.

    Args:
        field: The field.
        value: The value.

    Returns:
        str: What the input holds.
    """
    if field.kind == KIND_SWITCH:
        return YES if value else ""
    return format_value(field, value)


def build_rows(saved: Settings, draft: dict) -> list:
    """
    Read every field against the saved settings.

    Args:
        saved: The settings in the file.
        draft: Each field's raw text, for every field the draft holds; a field
            left out holds its saved value.

    Returns:
        list: One :class:`Row` per field, in table order.
    """
    defaults = Settings()
    rows = []
    for field in FIELDS:
        stored = getattr(saved, field.key)
        saved_raw = _raw_of(field, stored)
        raw = draft.get(field.key, saved_raw)
        value, error = parse_value(field, raw)
        if error:
            changed = raw.strip() != saved_raw
        else:
            changed = value != stored
        rows.append(
            Row(
                field=field,
                raw=raw,
                value=value,
                error=error or "",
                changed=changed,
                saved=saved_raw,
                default=format_value(field, getattr(defaults, field.key)),
                default_raw=_raw_of(field, getattr(defaults, field.key)),
            )
        )
    return rows


def status_of(rows: list, note: str, last_saved: str, panel: Optional["SlotPanel"] = None) -> dict:
    """
    Write the Status cell: errors first, then changes, then all saved.

    Args:
        rows: The table's rows.
        note: A sentence leading the cell ("Saved.", the reset note), dropped
            while there are errors.
        last_saved: When the file was last saved, as the cell writes it.
        panel: The slot table, whose refused labels count as values to fix
            and whose changes are named "Slots"; None leaves it out.

    Returns:
        dict: ``lead`` in bold and ``text`` after it; ``error`` when the cell
        reports values to fix.
    """
    errors = [f"{row.field.name}: {row.error}" for row in rows if row.error]
    changed = [row.field.name for row in rows if row.changed]
    if panel is not None:
        errors += [f"Slot {tile.name}: {tile.error}" for tile in panel.tiles if tile.error]
        if panel.changed:
            changed.append(SLOTS_NAME)
    if errors:
        count = len(errors)
        return {
            "lead": f"Fix {count} {'value' if count == 1 else 'values'} before saving.",
            "text": " ".join(errors),
            "note": "",
            "error": True,
        }
    if changed:
        count = len(changed)
        names = ", ".join(changed)
        return {
            "lead": f"{count} unsaved {'change' if count == 1 else 'changes'}:",
            "text": f"{names}. Changed values are marked with a triangle.",
            "note": note,
            "error": False,
        }
    return {
        "lead": "",
        "text": f"No unsaved changes. Last saved {last_saved}.",
        "note": note,
        "error": False,
    }


def _saved_change(entry: OpenProject, done: str) -> Optional[LastChange]:
    """
    Find the save the address names, if it is the project's last change.

    Args:
        entry: The open project.
        done: What the address says finished.

    Returns:
        Optional[LastChange]: The record, when the address names it.
    """
    change = entry.last_change
    if done != DONE_SAVED or change is None or change.kind != DONE_SAVED:
        return None
    return change


def _draft_query(form, project: Project) -> dict:
    """
    Spell a draft as the address that draws it.

    Args:
        form: The posted form, or any mapping of field names to text.
        project: The project, whose saved labels a tile need not repeat.

    Returns:
        dict: ``draft=1``, every numeric field posted, each switch that is
        on as "1", the slot text when it was posted, and each tile's label
        that differs from the saved one (an emptied one as empty).
    """
    query = {"draft": YES, "submitted": YES}
    for field in FIELDS:
        raw = form.get(field.key)
        if raw is None:
            continue
        if field.kind == KIND_SWITCH:
            if parse_value(field, str(raw))[0]:
                query[field.key] = YES
        else:
            query[field.key] = str(raw)
    if form.get("slots") is not None:
        query["slots"] = str(form.get("slots"))
    for name, label in label_fields(form).items():
        if label.strip() != project.slot_labels.get(name, ""):
            query[f"{LABEL_PREFIX}{name}"] = label
    return query


def _sheet_url(request: Request, project_id: str, query: Optional[dict] = None) -> str:
    """
    Build an address of the sheet.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        query: The query, or None for the saved values.

    Returns:
        str: The address.
    """
    base = project_url(request, project_id, SHEET)
    return f"{base}?{urlencode(query)}" if query else base


@dataclass(frozen=True)
class Tile:
    """
    One slot on the board.

    Attributes:
        name: The slot's name.
        label: What its label input holds: the label typed or saved, or empty.
        derived: The label the slot is drawn with when its input is empty.
        used: Whether an active item holds the slot.
        dup: Whether the list names the slot more than once.
        clash: Whether another slot is drawn with the same label.
        error: The sentence refusing its label, or empty.
    """

    name: str
    label: str
    derived: str
    used: bool
    dup: bool
    clash: bool
    error: str

    @property
    def field_name(self) -> str:
        """The name its input posts under."""
        return f"{LABEL_PREFIX}{self.name}"

    @property
    def title(self) -> str:
        """What the tile says of itself on hover and to a screen reader."""
        state = "in use" if self.used else "free"
        return f"Slot {self.name}, {state}{', listed twice' if self.dup else ''}"


@dataclass(frozen=True)
class SlotPanel:
    """
    The slot table as drawn.

    Attributes:
        text: What the list's textarea holds.
        saved_text: The saved list as one line, for settings.js's marks.
        saved_labels: The saved labels worth storing, for the same.
        used_slots: Every slot an active item holds, for the board's fills.
        tiles: One per distinct slot listed, in list order.
        dups: The slots listed more than once.
        collisions: Label to the slots drawn with it, for each label two or
            more slots share and none of them is refused.
        changed: Whether the list or the labels differ from the saved ones.
    """

    text: str
    saved_text: str
    saved_labels: dict
    used_slots: list
    tiles: list
    dups: list
    collisions: dict
    changed: bool

    @property
    def total(self) -> int:
        """How many slots the list names."""
        return len(self.tiles)

    @property
    def used(self) -> int:
        """How many of them an active item holds."""
        return sum(1 for tile in self.tiles if tile.used)


def label_fields(form) -> dict:
    """
    Pick the tiles' labels out of a form or a query.

    Args:
        form: The posted form or the query parameters.

    Returns:
        dict: Slot name to the label as typed, for every tile it carries.
    """
    return {
        key[len(LABEL_PREFIX):]: str(value)
        for key, value in form.items()
        if key.startswith(LABEL_PREFIX)
    }


def build_slot_panel(project: Project, text: Optional[str], labels: dict) -> SlotPanel:
    """
    Read the slot table against the saved list and labels.

    Args:
        project: The project, holding the saved list and labels.
        text: The list as typed, or None for the saved list.
        labels: Slot name to label for each tile the draft carries; a slot
            without one holds its saved label.

    Returns:
        SlotPanel: The table, its tiles' states and whether it changed.
    """
    saved_text = format_slot_list(project.slots)
    if text is None:
        text = saved_text
    names: list[str] = []
    dups: list[str] = []
    for entry in parse_slot_list(text):
        name = entry.strip()
        if not name:
            continue
        if name in names:
            if name not in dups:
                dups.append(name)
            continue
        names.append(name)

    typed = {name: labels.get(name, project.slot_labels.get(name, "")) for name in names}
    verdict = check_slot_labels(names, typed)
    used = project.active_identifiers()
    groups = label_collisions(names, verdict.labels)
    clashing = {name for members in groups.values() for name in members}

    tiles = []
    for name in names:
        error = ""
        problem = verdict.errors.get(name)
        if problem is SlotLabelError.LABEL_TOO_LONG:
            error = ERROR_LABEL_LONG
        elif problem is SlotLabelError.LABEL_IN_USE:
            owner = label_owner(names, verdict.labels, name) or ""
            error = ERROR_LABEL_TAKEN.format(slot=owner, label=verdict.labels[name])
        tiles.append(
            Tile(
                name=name,
                label=typed[name].strip(),
                derived=short_label(name),
                used=name in used,
                dup=name in dups,
                clash=name in clashing,
                error=error,
            )
        )

    saved_labels = entered_slot_labels(project.slots, project.slot_labels)
    return SlotPanel(
        text=text,
        saved_text=saved_text,
        saved_labels=saved_labels,
        used_slots=sorted(used),
        tiles=tiles,
        dups=dups,
        collisions={
            label: members
            for label, members in groups.items()
            if not any(member in verdict.errors for member in members)
        },
        changed=names != list(project.slots) or verdict.labels != saved_labels,
    )


@router.get(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}", name="settings_sheet")
async def settings_sheet(
    request: Request,
    project_id: str,
    draft: str = Query("", description="1 when the query holds the form's values"),
    reset: str = Query("", description="1 to fill every parameter with its default"),
    submitted: str = Query("", description="1 when a save refused the draft"),
    done: str = Query("", description="what just finished: saved"),
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Draw one project's settings as a specification sheet.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        draft: "1" to draw the query's field values as a draft.
        reset: "1" to draw the defaults, unsaved, over the saved values.
        submitted: "1" on the draft a refused save lands on, which puts the
            caret in the first field in error.
        done: "saved" on the address a save lands on.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: The Settings sheet.

    Raises:
        ProjectNotFoundError: If the id names no project in the directory.
        NewerFormatError: If the file was written by a newer application.
        ProjectFormatError: If the file's format version cannot be reached.
        ProjectUnreadableError: If the file will not read as a project.
    """
    entry = registry.open_fresh(project_id)
    project = entry.session.project
    pid = entry.path.name
    saved = project.settings

    # The slot table is drawn from the draft on a draft and after Reset, which
    # without JavaScript carries the form's fields, slots and tiles included.
    params = request.query_params
    if draft == YES or reset == YES:
        panel = build_slot_panel(project, params.get("slots"), label_fields(params))
    else:
        panel = build_slot_panel(project, None, {})

    note = ""
    if reset == YES:
        defaults = Settings()
        values = {field.key: _raw_of(field, getattr(defaults, field.key)) for field in FIELDS}
        note = NOTE_RESET
    elif draft == YES:
        values = {
            field.key: params.get(field.key, "")
            for field in FIELDS
            if field.kind == KIND_SWITCH or field.key in params
        }
    else:
        values = {}

    change = _saved_change(entry, done) if not values and not panel.changed else None
    if change is not None:
        note = NOTE_SAVED
        last_saved = change.time.strftime(CHANGE_TIME_FORMAT)
    else:
        last_saved = project.modified.strftime(MODIFIED_FORMAT)

    rows = build_rows(saved, values)
    groups = []
    position = 0
    for title, fields in GROUPS:
        groups.append({"title": title, "rows": rows[position:position + len(fields)]})
        position += len(fields)
    # A refused save puts the caret in the first field to fix, as the mockup's
    # Save does; a draft merely drawn at its address is left at the top.
    first_error = ""
    if submitted == YES:
        first_error = next((row.field.key for row in rows if row.error), "")
        if not first_error:
            first_error = next(
                (tile.field_name for tile in panel.tiles if tile.error), ""
            )

    context = {
        "project_id": pid,
        "project_name": project.name,
        "file_name": pid,
        "groups": groups,
        "keys": SETTINGS_KEYS,
        "status": status_of(rows, note, last_saved, panel),
        "last_saved": last_saved,
        "first_error": first_error,
        "slots": panel,
        "saved_labels_json": json.dumps(panel.saved_labels, ensure_ascii=False),
        "used_slots_json": json.dumps(panel.used_slots, ensure_ascii=False),
        "label_max": SLOT_LABEL_MAX_LENGTH,
        "error_label_long": ERROR_LABEL_LONG,
        "error_label_taken": ERROR_LABEL_TAKEN,
        "settings_url": project_url(request, pid, SHEET),
        "number_pattern": NUMBER_PATTERN,
        "error_number": ERROR_NUMBER,
        "error_whole": ERROR_WHOLE,
        "empty_error": empty_error,
        "range_error": range_error,
        "range_text": range_text,
        "kind_switch": KIND_SWITCH,
    }
    return _templates(request).TemplateResponse(request, "settings.html", context)


@router.post(f"{PROJECTS_PREFIX}/{{project_id}}/{SHEET}", name="settings_save")
async def settings_save(
    request: Request,
    project_id: str,
    registry: ProjectRegistry = Depends(get_registry),
    user: Principal = Depends(get_current_user),
) -> Response:
    """
    Save the settings, and the slot list when the form carries one.

    Read from the form as text, every field: nothing here can answer FastAPI's
    422. A numeric field left out keeps its saved value; a switch left out is
    off, as a form sends it.

    Args:
        request: The incoming request.
        project_id: The project's file name.
        registry: The open-project cache.
        user: The signed-in principal.

    Returns:
        Response: A 303 to ``done=saved``, or to the draft's address when a
        value is refused - which changes nothing.
    """
    form = await request.form()
    with registry.mutate(project_id) as mutation:
        pid = mutation.entry.path.name
        project = mutation.session.project
        draft = {
            field.key: str(form.get(field.key, ""))
            for field in FIELDS
            if field.kind == KIND_SWITCH or field.key in form
        }
        rows = build_rows(project.settings, draft)
        text = str(form.get("slots")) if form.get("slots") is not None else None
        posted_labels = label_fields(form)
        panel = build_slot_panel(project, text, posted_labels)
        if any(row.error for row in rows) or any(tile.error for tile in panel.tiles):
            logger.info("Refused the settings of %s", pid)
            return RedirectResponse(
                _sheet_url(request, pid, _draft_query(form, project)), status_code=303
            )
        settings = Settings(**{row.field.key: row.value for row in rows})
        slots = parse_slot_list(text) if text is not None else list(project.slots)
        labels = None
        if text is not None or posted_labels:
            # A slot with no tile posted keeps its saved label; a tile posted
            # for a slot no longer listed is dropped by the session.
            labels = {**project.slot_labels, **posted_labels}
        mutation.session.apply_settings(settings, slots, labels)
        mutation.record_change(DONE_SAVED, "", "Settings")
    logger.info("Saved the settings of %s", pid)
    return RedirectResponse(_sheet_url(request, pid, {"done": DONE_SAVED}), status_code=303)
