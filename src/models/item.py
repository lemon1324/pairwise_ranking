"""Item model for the pairwise ranking application."""

from dataclasses import dataclass, field
import uuid


# Category assigned to items that have no explicit category
DEFAULT_CATEGORY = "Default"


@dataclass
class Item:
    """
    Represents an item that can be ranked through pairwise comparisons.

    Attributes:
        name: The display name of the item.
        description: An optional longer description of the item.
        identifier: An optional short label (e.g. a slot code) for the item.
        category: The category the item belongs to. Whitespace is stripped and
            an empty value is replaced with DEFAULT_CATEGORY.
        id: A unique identifier for the item. Auto-generated if not provided.

    Example:
        >>> item = Item(name="Python", description="A programming language")
        >>> print(item.name)
        Python
    """

    name: str
    description: str = ""
    identifier: str = ""
    category: str = DEFAULT_CATEGORY
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
        self.category = self.category.strip() if self.category else ""
        if not self.category:
            self.category = DEFAULT_CATEGORY

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
            dict: Dictionary with 'id', 'name', 'description', 'identifier', and 'category' keys.
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
            data: Dictionary containing 'name' and optionally 'description',
                'identifier', 'category', and 'id'.

        Returns:
            Item: A new Item instance.

        Raises:
            KeyError: If 'name' key is missing from data.
        """
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            identifier=data.get("identifier", ""),
            category=data.get("category", DEFAULT_CATEGORY),
            id=data.get("id", str(uuid.uuid4())),
        )
