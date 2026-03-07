"""Project model for the pairwise ranking application."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models.item import Item
from src.models.vote import Vote
from src.models.settings import Settings


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
        file_path: Path to the .pairrank file, or None if not yet saved.
    """

    name: str
    created: datetime = field(default_factory=datetime.now)
    modified: datetime = field(default_factory=datetime.now)
    items: list[Item] = field(default_factory=list)
    votes: list[Vote] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    file_path: Optional[Path] = None

    def __post_init__(self):
        """Validate project data after initialization."""
        if not self.name or not self.name.strip():
            raise ValueError("Project name cannot be empty")
        self.name = self.name.strip()

    def to_dict(self) -> dict:
        """
        Convert project to a dictionary representation.

        Returns:
            dict: Dictionary suitable for JSON serialization.
        """
        return {
            "name": self.name,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat(),
            "items": [item.to_dict() for item in self.items],
            "votes": [vote.to_dict() for vote in self.votes],
            "settings": self.settings.to_dict(),
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
            KeyError: If required keys are missing from data.
        """
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

        return cls(
            name=data["name"],
            created=created,
            modified=modified,
            items=items,
            votes=votes,
            settings=settings,
            file_path=file_path,
        )
