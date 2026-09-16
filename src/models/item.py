"""Item model for the pairwise ranking application."""

from dataclasses import dataclass, field
from typing import Optional
import uuid


@dataclass
class Item:
    """
    Represents an item that can be ranked through pairwise comparisons.

    Attributes:
        name: The display name of the item.
        description: An optional longer description of the item.
        id: A unique identifier for the item. Auto-generated if not provided.

    Example:
        >>> item = Item(name="Python", description="A programming language")
        >>> print(item.name)
        Python
    """

    name: str
    description: str = ""
    identifier: str = ""
    category: str = "Default"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        """
        Validate item data after initialization.

        Raises:
            ValueError: If name is empty or whitespace-only.
        """
        if not self.name or not self.name.strip():
            raise ValueError("Item name cannot be empty")
        self.name = self.name.strip()
        self.description = self.description.strip() if self.description else ""
        self.identifier = self.identifier.strip() if self.identifier else ""

    def has_identifier(self) -> bool:
        """
        Check if the item has a valid identifier assigned.

        Returns:
            bool: True if identifier is non-empty, False otherwise.
        """
        return bool(self.identifier)

    def __hash__(self):
        """
        Return hash based on item ID.

        Returns:
            int: Hash value of the item's ID.
        """
        return hash(self.id)

    def __eq__(self, other):
        """
        Check equality based on item ID.

        Args:
            other: Another object to compare with.

        Returns:
            bool: True if other is an Item with the same ID, False otherwise.
        """
        if not isinstance(other, Item):
            return False
        return self.id == other.id

    def to_dict(self) -> dict:
        """
        Convert item to a dictionary representation.

        Returns:
            dict: Dictionary with 'id', 'name', 'description', and 'identifier' keys.
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "identifier": self.identifier,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        """
        Create an Item from a dictionary.

        Args:
            data: Dictionary containing 'name' and optionally 'description', 'identifier', and 'id'.

        Returns:
            Item: A new Item instance.

        Raises:
            KeyError: If 'name' key is missing from data.
        """
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            identifier=data.get("identifier", ""),
            category=data.get("category", "Default"),
            id=data.get("id", str(uuid.uuid4())),
        )
