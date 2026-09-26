"""Project model for the pairwise ranking application."""

import copy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models.item import Item
from src.models.vote import Vote
from src.models.settings import Settings


# Version of the .pairrank file format written by this code. It lives here,
# next to the serialization that writes it, so that the data layer (which
# already imports the models) can read it without creating an import cycle.
CURRENT_FORMAT_VERSION = 3

# How many characters an explicit slot short label may hold. Short labels are
# drawn in the tight spaces of a board, so they are hard-capped rather than
# elided.
SLOT_LABEL_MAX_LENGTH = 2


def normalize_slots(raw: list[str]) -> list[str]:
    """
    Clean up a raw slot list.

    Each entry is stripped, empty entries are dropped and duplicates are
    removed while preserving the order of first appearance.

    Args:
        raw: Slot labels as entered or as read from a project file.

    Returns:
        list[str]: The normalized slot list.
    """
    slots: list[str] = []
    seen: set[str] = set()
    for value in raw or []:
        slot = str(value).strip()
        if not slot or slot in seen:
            continue
        seen.add(slot)
        slots.append(slot)
    return slots


def normalize_slot_labels(raw: dict, slots: list[str]) -> dict[str, str]:
    """
    Clean up a raw map of slot short labels.

    Keys and values are stripped, values are truncated to
    SLOT_LABEL_MAX_LENGTH characters and entries with an empty value are
    dropped. A label only means something next to the slot it belongs to, so
    keys that name no slot in ``slots`` are dropped too: that is what makes
    dropping or renaming a slot drop its label with it.

    Args:
        raw: Slot name to short label, as entered or as read from a project
            file.
        slots: The already-normalized slot list the labels belong to.

    Returns:
        dict[str, str]: The normalized labels, in the order the slots are
        defined.
    """
    if not raw:
        return {}

    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        slot = str(key).strip()
        label = str(value).strip()[:SLOT_LABEL_MAX_LENGTH]
        if not slot or not label:
            continue
        cleaned[slot] = label

    return {slot: cleaned[slot] for slot in slots if slot in cleaned}


def active_identifiers(items: list[Item]) -> set[str]:
    """
    Collect the identifiers currently held by active items.

    Args:
        items: The items to inspect, active and retired.

    Returns:
        set[str]: Non-empty identifiers of the active items.
    """
    return {item.identifier for item in items if item.is_active() and item.identifier}


def identifier_in_use(
    items: list[Item],
    identifier: str,
    exclude_item_id: Optional[str] = None,
) -> bool:
    """
    Check whether an identifier is already held by an active item.

    Retired items never hold an identifier, so uniqueness only has to be
    enforced among active items.

    Args:
        items: The items to inspect, active and retired.
        identifier: The identifier to check. An empty identifier is never
            considered in use.
        exclude_item_id: Id of an item to ignore, typically the item being
            edited or the item being replaced.

    Returns:
        bool: True if another active item already holds the identifier.
    """
    wanted = identifier.strip() if identifier else ""
    if not wanted:
        return False

    for item in items:
        if not item.is_active():
            continue
        if exclude_item_id is not None and item.id == exclude_item_id:
            continue
        if item.identifier == wanted:
            return True
    return False


def free_slots(slots: list[str], items: list[Item]) -> list[str]:
    """
    Work out which of a slot list's entries no active item occupies.

    Args:
        slots: The slot labels defined by the project.
        items: The items to inspect, active and retired.

    Returns:
        list[str]: Free slots in the order they are defined. Empty when no
        slots are defined.
    """
    taken = active_identifiers(items)
    return [slot for slot in slots if slot not in taken]


def _require_entry_list(data: dict, key: str) -> list[dict]:
    """
    Read a list of JSON objects out of a project dictionary.

    Args:
        data: The parsed project dictionary.
        key: The key to read, e.g. "items" or "votes".

    Returns:
        list[dict]: The entries, or an empty list when the key is absent.

    Raises:
        ValueError: If the value is present but is not a list of objects.
    """
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(e, dict) for e in value):
        raise ValueError(
            f"Project data key '{key}' must be a list of objects, "
            f"got {type(value).__name__}"
        )
    return value


@dataclass
class Project:
    """
    Represents a pairwise ranking project containing items, votes, and settings.

    A project encapsulates all data needed for a ranking session and can be
    saved/loaded from a .pairrank file.

    Attributes:
        name: The display name of the project.
        created: When the project was created.
        modified: When the project was last modified.
        items: List of items being ranked.
        votes: List of comparison votes.
        settings: Algorithm and display settings.
        slots: Optional list of slot labels available in this project. When
            empty, identifiers are free text.
        slot_labels: Optional short label per slot, for the places a screen has
            room for two characters and no more. Slots without an entry fall
            back to a label derived from the slot name; see
            :func:`src.app.slots.short_label`.
        file_path: Path to the .pairrank file, or None if not yet saved.
    """

    name: str
    created: datetime = field(default_factory=datetime.now)
    modified: datetime = field(default_factory=datetime.now)
    items: list[Item] = field(default_factory=list)
    votes: list[Vote] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    slots: list[str] = field(default_factory=list)
    slot_labels: dict[str, str] = field(default_factory=dict)
    file_path: Optional[Path] = None

    def __post_init__(self):
        """Validate project data after initialization."""
        if not self.name or not self.name.strip():
            raise ValueError("Project name cannot be empty")
        self.name = self.name.strip()
        self.slots = normalize_slots(self.slots)
        self.slot_labels = normalize_slot_labels(self.slot_labels, self.slots)

    def rename(self, name: str) -> None:
        """
        Change the project's display name.

        The file the project lives in is untouched; only the name stored
        inside it changes.

        Args:
            name: The new name. Surrounding whitespace is stripped.

        Raises:
            ValueError: If the new name is empty or only whitespace.
        """
        if not name or not name.strip():
            raise ValueError("Project name cannot be empty")
        self.name = name.strip()

    def copy_without_votes(self, name: str) -> "Project":
        """
        Return a new project with this project's setup but no votes.

        The items, settings and slots are carried over as independent copies,
        so editing either project leaves the other untouched. Item ids are
        preserved, which lets the same item be matched across the two
        projects. The copy starts with no votes and is not associated with a
        file; the storage layer assigns its path when it is saved.

        Args:
            name: Name for the new project. Surrounding whitespace is
                stripped.

        Returns:
            Project: The new project. This project is left unchanged.

        Raises:
            ValueError: If the new name is empty or only whitespace.
        """
        if not name or not name.strip():
            raise ValueError("Project name cannot be empty")

        now = datetime.now()
        return Project(
            name=name.strip(),
            created=now,
            modified=now,
            items=copy.deepcopy(self.items),
            votes=[],
            settings=copy.deepcopy(self.settings),
            slots=list(self.slots),
            slot_labels=dict(self.slot_labels),
            file_path=None,
        )

    def active_items(self) -> list[Item]:
        """
        Return the items that are still being compared.

        Returns:
            list[Item]: Items whose status is active, in project order.
        """
        return [item for item in self.items if item.is_active()]

    def find_item(self, item_id: str) -> Optional[Item]:
        """
        Look an item up by id.

        Args:
            item_id: The id to find.

        Returns:
            Optional[Item]: The item, or None if the project has no item with
            that id.
        """
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def add_item(self, item: Item) -> Item:
        """
        Add an item to the project.

        Args:
            item: The item to add. It is appended, so the project keeps the
                order items were created in.

        Returns:
            Item: The item that was added.

        Raises:
            ValueError: If the project already has an item with its id. A new
                item's id is a fresh UUID, so only a caller re-adding an item
                it already holds can meet this; a file with two such items
                would not load again.
        """
        if self.find_item(item.id) is not None:
            raise ValueError(f"The project already has an item with the id {item.id!r}")
        self.items.append(item)
        return item

    def remove_item(self, item_id: str) -> Optional[Item]:
        """
        Remove an item and every vote it took part in.

        Deleting an item discards its history; retiring it is the way to keep
        the history. The vote cascade runs whether or not the item was there:
        a file written elsewhere may hold votes naming an item the project has
        already lost, and those orphans have to go too or the ranking model
        keeps being fed them.

        Args:
            item_id: Id of the item to remove.

        Returns:
            Optional[Item]: The removed item, or None if there was no such
            item. The cascade has run in either case.
        """
        removed = self.find_item(item_id)

        if removed is not None:
            self.items[:] = [item for item in self.items if item.id != item_id]
        self.votes[:] = [
            vote for vote in self.votes if not vote.involves_item(item_id)
        ]
        return removed

    def add_vote(self, vote: Vote) -> Vote:
        """
        Record a vote.

        Args:
            vote: The vote to record. It is appended, so the votes stay in the
                order they were cast and :meth:`pop_last_vote` undoes the most
                recent one.

        Returns:
            Vote: The vote that was recorded.
        """
        self.votes.append(vote)
        return vote

    def active_identifiers(self) -> set[str]:
        """
        Return the identifiers currently held by active items.

        Returns:
            set[str]: Non-empty identifiers of active items.
        """
        return active_identifiers(self.items)

    def identifier_in_use(
        self,
        identifier: str,
        exclude_item_id: Optional[str] = None,
    ) -> bool:
        """
        Check whether an identifier is already held by an active item.

        Args:
            identifier: The identifier to check. An empty identifier is never
                considered in use.
            exclude_item_id: Id of an item to ignore, typically the item being
                edited.

        Returns:
            bool: True if another active item already holds the identifier.
        """
        return identifier_in_use(self.items, identifier, exclude_item_id)

    def free_slots(self) -> list[str]:
        """
        Return the project's slots that no active item occupies.

        Returns:
            list[str]: Free slots in the order they are defined. Empty when the
            project defines no slots.
        """
        return free_slots(self.slots, self.items)

    def set_slots(self, raw: list[str]) -> None:
        """
        Replace the project's slot list.

        Any short label belonging to a slot that is no longer in the list goes
        with it, so a slot never keeps a label the project cannot reach.

        Args:
            raw: Slot labels; stripped, with empty entries dropped and
                duplicates removed while preserving order.
        """
        self.slots = normalize_slots(raw)
        self.slot_labels = normalize_slot_labels(self.slot_labels, self.slots)

    def set_slot_labels(self, raw: dict) -> None:
        """
        Replace the project's short labels for its slots.

        Args:
            raw: Slot name to short label. Entries are stripped and truncated,
                and entries naming no current slot are dropped.
        """
        self.slot_labels = normalize_slot_labels(raw, self.slots)

    def pop_last_vote(self) -> Optional[Vote]:
        """
        Remove and return the most recently recorded vote.

        Votes are appended in the order they are cast, so the last entry is the
        most recent one. This backs the "undo last vote" action.

        Returns:
            Optional[Vote]: The removed vote, or None if the project has no
            votes.
        """
        if not self.votes:
            return None
        return self.votes.pop()

    def to_dict(self) -> dict:
        """
        Convert project to a dictionary representation.

        Returns:
            dict: Dictionary suitable for JSON serialization.
        """
        return {
            "format_version": CURRENT_FORMAT_VERSION,
            "name": self.name,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat(),
            "items": [item.to_dict() for item in self.items],
            "votes": [vote.to_dict() for vote in self.votes],
            "settings": self.settings.to_dict(),
            "slots": list(self.slots),
            "slot_labels": dict(self.slot_labels),
        }

    @classmethod
    def from_dict(cls, data: dict, file_path: Optional[Path] = None) -> "Project":
        """
        Create a Project from a dictionary.

        Args:
            data: Dictionary containing project data.
            file_path: Optional path to associate with the project.

        Returns:
            Project: A new Project instance.

        Raises:
            ValueError: If data is not a dictionary, if the required 'name'
                key is missing or empty, or if 'items', 'votes', 'settings',
                'slots' or 'slot_labels' have the wrong shape, if an id is
                empty, null or not text or a number (numbers are read as
                text; see :func:`~src.models.item.normalize_id`), or if two
                items share an id.
            KeyError: If nested item or vote entries are missing required keys.
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"Project data must be a JSON object, got {type(data).__name__}"
            )
        if "name" not in data:
            raise ValueError("Project data is missing required 'name' field")

        name = data["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Project data key 'name' must be a non-empty string")

        # Validate every nested shape before building any child object, so a
        # malformed file always surfaces as a ValueError naming the bad key.
        item_entries = _require_entry_list(data, "items")
        vote_entries = _require_entry_list(data, "votes")

        settings_data = data.get("settings")
        if settings_data is None:
            settings_data = {}
        elif not isinstance(settings_data, dict):
            raise ValueError(
                f"Project data key 'settings' must be an object, "
                f"got {type(settings_data).__name__}"
            )

        slot_entries = data.get("slots")
        if slot_entries is None:
            slot_entries = []
        elif not isinstance(slot_entries, list) or not all(
            isinstance(slot, str) for slot in slot_entries
        ):
            raise ValueError(
                f"Project data key 'slots' must be a list of strings, "
                f"got {type(slot_entries).__name__}"
            )

        label_entries = data.get("slot_labels")
        if label_entries is None:
            label_entries = {}
        elif not isinstance(label_entries, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in label_entries.items()
        ):
            raise ValueError(
                f"Project data key 'slot_labels' must be an object of strings, "
                f"got {type(label_entries).__name__}"
            )

        created = data.get("created")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        elif created is None:
            created = datetime.now()

        modified = data.get("modified")
        if isinstance(modified, str):
            modified = datetime.fromisoformat(modified)
        elif modified is None:
            modified = datetime.now()

        items = [Item.from_dict(item_data) for item_data in item_entries]
        # An id names one item everywhere - in votes, in a replacement chain,
        # in a web address - so two items sharing one leave every one of those
        # pointing at whichever is found first. Such a file is damaged. The
        # ids are already text here (Item.from_dict), so 1 and "1" collide.
        seen_ids = set()
        for item in items:
            if item.id in seen_ids:
                raise ValueError(f"Project data has more than one item with the id {item.id!r}")
            seen_ids.add(item.id)
        votes = [Vote.from_dict(vote_data) for vote_data in vote_entries]
        settings = Settings.from_dict(settings_data)
        slots = normalize_slots(slot_entries)
        slot_labels = normalize_slot_labels(label_entries, slots)

        return cls(
            name=name,
            created=created,
            modified=modified,
            items=items,
            votes=votes,
            settings=settings,
            slots=slots,
            slot_labels=slot_labels,
            file_path=file_path,
        )
