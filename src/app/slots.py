"""Qt-free rules for a project's slots and their short labels.

A slot is identified by its plain name. Some screens have room for the name and
some do not: the slot board and the item balloons have room for two characters,
so every slot also resolves to a *short label*, taken from the project's
optional ``slot_labels`` map when it holds one and derived from the slot name
otherwise.

Two short labels can collide - "Apex" and "Apostrophe" both start "Ap" - and no
rule here can prevent that, because a slot list is free text. What this module
does is make a collision visible, so a screen can offer the user an explicit
label instead. :func:`validate_slot_labels` checks labels the user has entered
and :func:`label_collisions` reports the collisions that survive.

The slot list itself is edited as one comma-separated line
(:func:`format_slot_list`, :func:`parse_slot_list`). Parsing also accepts
newlines, because that is how the list used to be written and because pasting a
column of names should work.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.models.project import SLOT_LABEL_MAX_LENGTH


class SlotLabelError(Enum):
    """
    What is wrong with one slot's short label.

    Attributes:
        LABEL_TOO_LONG: The label holds more than SLOT_LABEL_MAX_LENGTH
            characters.
        LABEL_IN_USE: Another slot already carries the same explicit label.
    """

    LABEL_TOO_LONG = "label_too_long"
    LABEL_IN_USE = "label_in_use"


@dataclass(frozen=True)
class SlotLabelVerdict:
    """
    The result of validating a project's explicit slot labels.

    Attributes:
        labels: The labels after cleaning, whether or not they are valid. Keys
            and values are stripped, empty labels are dropped and labels for
            slots that are not in the slot list are dropped. Values are *not*
            truncated, so an over-long label survives long enough to be
            complained about.
        errors: Slot name to the error found on its label, in slot order, so a
            frontend reporting one complaint at a time reports them top to
            bottom.
    """

    labels: dict[str, str]
    errors: dict[str, SlotLabelError] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """
        Check whether the labels can be accepted.

        Returns:
            bool: True when no slot carries an error.
        """
        return not self.errors


def short_label(slot: str, labels: Optional[dict[str, str]] = None) -> str:
    """
    Work out the two-character label a slot is drawn with.

    Args:
        slot: The slot name.
        labels: The project's explicit labels, usually
            :attr:`~src.models.project.Project.slot_labels`. An entry here wins
            over the derived label.

    Returns:
        str: At most SLOT_LABEL_MAX_LENGTH characters. Empty only when the slot
        name is empty, which a normalized slot list never holds.
    """
    name = (slot or "").strip()
    explicit = ((labels or {}).get(name) or "").strip()
    if explicit:
        return explicit[:SLOT_LABEL_MAX_LENGTH]
    return name[:SLOT_LABEL_MAX_LENGTH]


def clean_slot_labels(slots: list[str], labels: dict) -> dict[str, str]:
    """
    Strip a raw label map down to the slots it can apply to.

    Unlike :func:`~src.models.project.normalize_slot_labels` this does not
    truncate, so validation can still see that a label is too long.

    Args:
        slots: The slot names the labels belong to.
        labels: Slot name to short label, as entered.

    Returns:
        dict[str, str]: The stripped labels, in the order the slots are given.
    """
    cleaned: dict[str, str] = {}
    for key, value in (labels or {}).items():
        slot = str(key).strip()
        label = str(value).strip()
        if not slot or not label:
            continue
        cleaned[slot] = label

    known = [slot.strip() for slot in slots or []]
    return {slot: cleaned[slot] for slot in known if slot in cleaned}


def validate_slot_labels(slots: list[str], labels: dict) -> SlotLabelVerdict:
    """
    Check the explicit short labels entered for a project's slots.

    Only two things can be wrong: a label that does not fit, and a label
    another slot has already taken. A slot with no explicit label is never a
    complaint - it simply falls back to the first two characters of its name,
    and any collision that causes is reported by :func:`label_collisions`
    rather than blocked here.

    Args:
        slots: The slot names, as stored on the project.
        labels: Slot name to short label, as entered. Entries for slots that
            are not in the list are ignored rather than rejected, because
            dropping a slot is how a label is meant to disappear.

    Returns:
        SlotLabelVerdict: The cleaned labels and any per-slot errors.
    """
    cleaned = clean_slot_labels(slots, labels)

    errors: dict[str, SlotLabelError] = {}
    seen: dict[str, str] = {}
    for slot, label in cleaned.items():
        if len(label) > SLOT_LABEL_MAX_LENGTH:
            errors[slot] = SlotLabelError.LABEL_TOO_LONG
            continue
        if label in seen:
            errors[slot] = SlotLabelError.LABEL_IN_USE
            continue
        seen[label] = slot

    return SlotLabelVerdict(labels=cleaned, errors=errors)


def entered_slot_labels(slots: list[str], labels: dict) -> dict[str, str]:
    """
    Keep only the labels worth storing from what was entered on a slot board.

    Cleaned as :func:`clean_slot_labels` cleans them, and a label equal to the
    one the slot would be drawn with anyway is dropped too: it says nothing the
    slot name does not, and storing it would stop the label following a later
    rename of the slot.

    Args:
        slots: The slot names the labels belong to.
        labels: Slot name to short label, as entered; an empty label means
            "use the first two characters".

    Returns:
        dict[str, str]: The labels to store, in slot order, not truncated.
    """
    cleaned = clean_slot_labels(slots, labels)
    return {
        slot: label
        for slot, label in cleaned.items()
        if label != short_label(slot)
    }


def _label_precedence(
    names: list[str], entered: dict[str, str], saved: Optional[dict[str, str]]
) -> dict[str, tuple[bool, int]]:
    """
    Order the slots for keeping a label two of them were given.

    A slot whose label is unchanged from its saved one comes before a slot
    whose label changed, so the label just typed is the one refused; between
    two changed labels, or two unchanged ones, the earlier slot comes first.

    Args:
        names: The slot names, in list order.
        entered: The entered labels, as :func:`entered_slot_labels` keeps them.
        saved: The saved labels, kept the same way, or None when there are
            none to compare with (every label then counts as changed).

    Returns:
        dict[str, tuple[bool, int]]: Slot name to a key that sorts the slot
        keeping a shared label first.
    """
    saved = saved or {}
    return {
        name: (entered.get(name) != saved.get(name), position)
        for position, name in enumerate(names)
    }


def check_slot_labels(
    slots: list[str], labels: dict, saved: Optional[dict] = None
) -> SlotLabelVerdict:
    """
    Check the labels entered on a slot board before they are stored.

    Stricter than :func:`validate_slot_labels`: an entered label must also
    differ from every label the *other* slots are drawn with, derived ones
    included, because a label the user typed is a choice and a choice that
    collides can be refused. Two derived labels colliding is still no error
    (nobody chose them); :func:`label_collisions` reports it as a warning.

    When two entered labels are the same and only one of them differs from
    its saved label, the one that changed is refused (owner ruling R8-2): the
    label just typed gives way to the one already there. When both changed,
    or neither did, the first slot keeps it and the later one is refused, as
    :func:`validate_slot_labels` does. Whether anything is refused does not
    depend on ``saved``; only which slot is.

    Args:
        slots: The slot names, already normalized.
        labels: Slot name to short label, as entered.
        saved: The saved labels, as :func:`entered_slot_labels` keeps them,
            or None to refuse by position alone.

    Returns:
        SlotLabelVerdict: ``labels`` as :func:`entered_slot_labels` keeps them
        and an error for each slot whose label is refused.
    """
    entered = entered_slot_labels(slots, labels)
    names = [slot.strip() for slot in slots or [] if slot.strip()]
    precedence = _label_precedence(names, entered, saved)

    errors: dict[str, SlotLabelError] = {}
    for slot in names:
        label = entered.get(slot)
        if label is None:
            continue
        if len(label) > SLOT_LABEL_MAX_LENGTH:
            errors[slot] = SlotLabelError.LABEL_TOO_LONG
            continue
        for other in names:
            if other == slot:
                continue
            if other in entered and precedence[other] > precedence[slot]:
                # That entered label gives way to this one, so it is the one refused.
                continue
            if short_label(other, entered) == label:
                errors[slot] = SlotLabelError.LABEL_IN_USE
                break

    return SlotLabelVerdict(labels=entered, errors=errors)


def label_owner(
    slots: list[str], labels: dict, slot: str, saved: Optional[dict] = None
) -> Optional[str]:
    """
    Name the slot whose label a refused label collides with.

    Args:
        slots: The slot names.
        labels: The entered labels, as :func:`entered_slot_labels` keeps them.
        slot: A slot whose label was refused as in use.
        saved: The saved labels, as :func:`check_slot_labels` was given them.

    Returns:
        Optional[str]: The other slot that keeps the label: the first slot
        drawn with it by its derived label (which is never refused), else the
        entered one first by :func:`check_slot_labels`'s order. None when
        there is none.
    """
    labels = labels or {}
    label = labels.get(slot)
    names = list(slots or [])
    precedence = _label_precedence(names, labels, saved)
    candidates = [
        other
        for other in names
        if other != slot
        and not (other in labels and slot in precedence and precedence[other] > precedence[slot])
        and short_label(other, labels) == label
    ]
    derived = [other for other in candidates if other not in labels]
    if derived:
        return derived[0]
    return min(candidates, key=precedence.__getitem__, default=None)


def label_collisions(
    slots: list[str], labels: Optional[dict[str, str]] = None
) -> dict[str, list[str]]:
    """
    Find the slots that end up drawn with the same short label.

    This is what a slot board warns about. It looks at the *resolved* labels,
    so it catches the case the explicit map is there to fix: two slot names
    sharing their first two characters. Comparison is exact, so labels that
    differ only in case do not collide.

    Args:
        slots: The slot names, as stored on the project.
        labels: The project's explicit labels.

    Returns:
        dict[str, list[str]]: Short label to the two or more slots resolving to
        it, in the order the slots are given. Empty when every slot resolves to
        a label of its own.
    """
    groups: dict[str, list[str]] = {}
    for slot in slots or []:
        name = (slot or "").strip()
        if not name:
            continue
        groups.setdefault(short_label(name, labels), []).append(name)

    return {
        label: members for label, members in groups.items() if len(members) > 1
    }


def format_slot_list(slots: list[str]) -> str:
    """
    Render a slot list as the single line the editors show.

    Args:
        slots: The slot names, as stored on the project.

    Returns:
        str: The names separated by ", ". Empty when there are no slots.
    """
    return ", ".join(slot for slot in slots or [])


def parse_slot_list(text: str) -> list[str]:
    """
    Split an edited slot line back into entries.

    Commas are the separator, but newlines are accepted too, so a pasted
    column of names and a file written before the editors became one line both
    still work. Nothing is cleaned here: stripping, dropping blanks and
    removing duplicates belong to
    :func:`~src.models.project.normalize_slots`, which
    :meth:`~src.models.project.Project.set_slots` applies. Keeping them apart
    means what the user typed reaches one normalizer, not two.

    Args:
        text: The contents of the slot editor.

    Returns:
        list[str]: The entries exactly as typed, split up.
    """
    return [
        part
        for line in (text or "").splitlines()
        for part in line.split(",")
    ]
