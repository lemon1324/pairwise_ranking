"""Project model for the pairwise ranking application."""

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
CURRENT_FORMAT_VERSION = 2


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
        file_path: Path to the .pairrank file, or None if not yet saved.
    """

    name: str
    created: datetime = field(default_factory=datetime.now)
    modified: datetime = field(default_factory=datetime.now)
    items: list[Item] = field(default_factory=list)
    votes: list[Vote] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    slots: list[str] = field(default_factory=list)
    file_path: Optional[Path] = None

    def __post_init__(self):
        """Validate project data after initialization."""
        if not self.name or not self.name.strip():
            raise ValueError("Project name cannot be empty")
        self.name = self.name.strip()
        self.slots = normalize_slots(self.slots)

    def active_items(self) -> list[Item]:
        """
        Return the items that are still being compared.

        Returns:
            list[Item]: Items whose status is active, in project order.
        """
        return [item for item in self.items if item.is_active()]

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

        Args:
            raw: Slot labels; stripped, with empty entries dropped and
                duplicates removed while preserving order.
        """
        self.slots = normalize_slots(raw)

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
                key is missing or empty, or if 'items', 'votes', 'settings'
                or 'slots' have the wrong shape.
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
        votes = [Vote.from_dict(vote_data) for vote_data in vote_entries]
        settings = Settings.from_dict(settings_data)
        slots = normalize_slots(slot_entries)

        return cls(
            name=name,
            created=created,
            modified=modified,
            items=items,
            votes=votes,
            settings=settings,
            slots=slots,
            file_path=file_path,
        )
