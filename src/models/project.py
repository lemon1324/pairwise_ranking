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

    def retired_items(self) -> list[Item]:
        """
        Return the items that have been retired.

        Returns:
            list[Item]: Items whose status is retired, in project order.
        """
        return [item for item in self.items if not item.is_active()]

    def active_identifiers(self) -> set[str]:
        """
        Return the identifiers currently held by active items.

        Returns:
            set[str]: Non-empty identifiers of active items.
        """
        return {item.identifier for item in self.active_items() if item.identifier}

    def identifier_in_use(
        self,
        identifier: str,
        exclude_item_id: Optional[str] = None,
    ) -> bool:
        """
        Check whether an identifier is already held by an active item.

        Retired items never hold an identifier, so uniqueness only has to be
        enforced among active items.

        Args:
            identifier: The identifier to check. An empty identifier is never
                considered in use.
            exclude_item_id: Id of an item to ignore, typically the item being
                edited.

        Returns:
            bool: True if another active item already holds the identifier.
        """
        wanted = identifier.strip() if identifier else ""
        if not wanted:
            return False

        for item in self.items:
            if not item.is_active():
                continue
            if exclude_item_id is not None and item.id == exclude_item_id:
                continue
            if item.identifier == wanted:
                return True
        return False

    def free_slots(self) -> list[str]:
        """
        Return the project's slots that no active item occupies.

        Returns:
            list[str]: Free slots in the order they are defined. Empty when the
            project defines no slots.
        """
        taken = self.active_identifiers()
        return [slot for slot in self.slots if slot not in taken]

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
            ValueError: If data is not a dictionary or the required 'name'
                key is missing.
            KeyError: If nested item or vote entries are missing required keys.
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"Project data must be a JSON object, got {type(data).__name__}"
            )
        if "name" not in data:
            raise ValueError("Project data is missing required 'name' field")

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

        items = [Item.from_dict(item_data) for item_data in data.get("items", [])]
        votes = [Vote.from_dict(vote_data) for vote_data in data.get("votes", [])]
        settings = Settings.from_dict(data.get("settings", {}))
        slots = normalize_slots(data.get("slots") or [])

        return cls(
            name=data["name"],
            created=created,
            modified=modified,
            items=items,
            votes=votes,
            settings=settings,
            slots=slots,
            file_path=file_path,
        )
