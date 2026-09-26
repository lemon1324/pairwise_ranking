"""Item model for the pairwise ranking application."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import math
import uuid


# Category assigned to items that have no explicit category
DEFAULT_CATEGORY = "Default"

# Lifecycle status values for an item
STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"

# Every status an item may hold
VALID_STATUSES = (STATUS_ACTIVE, STATUS_RETIRED)


def _number_text(value) -> Optional[str]:
    """
    Write a JSON number as the text an id or a slot would hold.

    Args:
        value: A value read from a project file.

    Returns:
        Optional[str]: ``"1"`` for ``1`` and for ``1.0``, ``"1.5"`` for
        ``1.5``; None when the value is not a finite number (a bool is not
        one, though Python counts it as an int).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer():
            return str(int(value))
    return str(value)


def normalize_id(value, what: str) -> str:
    """
    Read an id out of a project file as the text every lookup compares.

    An id is compared with ``==`` in votes and replacement chains, and it is
    carried as text in a web address, so the number ``1`` and the text
    ``"1"`` must be one id. Numbers - which a hand-written or converted file
    may hold - are written as text; an id that is empty, null or not a
    scalar names nothing and the file is damaged.

    Args:
        value: The value as read.
        what: What it is, for the message, e.g. "An item's 'id'".

    Returns:
        str: The id as text.

    Raises:
        ValueError: If the value is empty, blank, null, or neither text nor a
            finite number.
    """
    text = value if isinstance(value, str) else _number_text(value)
    if text is None or not text.strip():
        raise ValueError(
            f"{what} must be a non-empty string or a number, got {value!r}"
        )
    return text


def normalize_id_reference(value, what: str) -> Optional[str]:
    """
    Read an optional reference to an id, such as ``replaced_by``.

    Args:
        value: The value as read.
        what: What it is, for the message.

    Returns:
        Optional[str]: The id as text, or None when nothing is referenced
        (null or empty).

    Raises:
        ValueError: If the value is neither empty, text nor a finite number.
    """
    if value is None or value == "":
        return None
    return normalize_id(value, what)


@dataclass
class Item:
    """
    Represents an item that can be ranked through pairwise comparisons.

    Items have a lifecycle: active items are offered for comparison, retired
    items keep their votes and ranking history but are never compared again.
    Retiring an item releases its identifier so another item can take the slot.

    Attributes:
        name: The display name of the item.
        description: An optional longer description of the item.
        identifier: An optional short label (e.g. a slot code) for the item.
        category: The category the item belongs to. Whitespace is stripped and
            an empty value is replaced with DEFAULT_CATEGORY.
        status: Lifecycle status, either STATUS_ACTIVE or STATUS_RETIRED.
        retired_at: When the item was retired, or None while it is active.
        replaced_by: The id of the item that took this item's place, set when
            the item was retired through the Replace flow; None otherwise.
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
    status: str = STATUS_ACTIVE
    retired_at: Optional[datetime] = None
    replaced_by: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        """
        Validate item data after initialization.

        Raises:
            ValueError: If name is empty or whitespace-only, or if status is
                not one of VALID_STATUSES.
        """
        if not self.name or not self.name.strip():
            raise ValueError("Item name cannot be empty")
        self.name = self.name.strip()
        self.description = self.description.strip() if self.description else ""
        self.identifier = self.identifier.strip() if self.identifier else ""
        self.category = self.category.strip() if self.category else ""
        if not self.category:
            self.category = DEFAULT_CATEGORY
        self.status = self.status.strip() if self.status else ""
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"Item status must be one of {VALID_STATUSES}, got {self.status!r}"
            )

    def has_identifier(self) -> bool:
        """
        Check if the item has a valid identifier assigned.

        Returns:
            bool: True if identifier is non-empty, False otherwise.
        """
        return bool(self.identifier)

    def is_active(self) -> bool:
        """
        Check whether the item is still in the active pool.

        Returns:
            bool: True if the item's status is active, False if it is retired.
        """
        return self.status == STATUS_ACTIVE

    def retire(
        self,
        now: Optional[datetime] = None,
        replaced_by: Optional[str] = None,
    ) -> None:
        """
        Retire the item, freeing its identifier but keeping its history.

        Args:
            now: Timestamp to record as the retirement time. Defaults to the
                current time.
            replaced_by: The id of the item taking this item's place, when the
                item is being retired through the Replace flow.
        """
        self.status = STATUS_RETIRED
        self.retired_at = now if now is not None else datetime.now()
        self.replaced_by = replaced_by
        self.identifier = ""

    def reactivate(self, identifier: str = "") -> None:
        """
        Return a retired item to the active pool.

        Args:
            identifier: Identifier to assign to the reactivated item. Defaults
                to no identifier.
        """
        self.status = STATUS_ACTIVE
        self.retired_at = None
        self.replaced_by = None
        self.identifier = identifier.strip() if identifier else ""

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
            dict: Dictionary with 'id', 'name', 'description', 'identifier',
            'category', 'status', 'retired_at' and 'replaced_by' keys.
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "identifier": self.identifier,
            "category": self.category,
            "status": self.status,
            "retired_at": self.retired_at.isoformat() if self.retired_at else None,
            "replaced_by": self.replaced_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        """
        Create an Item from a dictionary.

        A missing or empty 'status' is treated as active, which is what files
        written before the lifecycle feature existed contain.

        Args:
            data: Dictionary containing 'name' and optionally 'description',
                'identifier', 'category', 'status', 'retired_at',
                'replaced_by', and 'id'.

        Returns:
            Item: A new Item instance.

        Raises:
            KeyError: If 'name' key is missing from data.
            ValueError: If 'status' is not a known status, 'retired_at' is
                not valid ISO text, 'id' is present but empty, null or not
                text or a number (see :func:`normalize_id`), or 'replaced_by'
                or 'identifier' is neither empty, text nor a number.
        """
        retired_at = data.get("retired_at")
        if isinstance(retired_at, str) and retired_at:
            retired_at = datetime.fromisoformat(retired_at)
        elif not isinstance(retired_at, datetime):
            retired_at = None

        # A slot is text in the slot list, so a slot number written as a
        # number must become that text too, or it would match no slot.
        identifier = data.get("identifier")
        if identifier is not None and not isinstance(identifier, str):
            number = _number_text(identifier)
            if number is None:
                raise ValueError(
                    f"An item's 'identifier' must be a string or a number, got {identifier!r}"
                )
            identifier = number

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            identifier=identifier or "",
            category=data.get("category", DEFAULT_CATEGORY),
            status=data.get("status") or STATUS_ACTIVE,
            retired_at=retired_at,
            replaced_by=normalize_id_reference(
                data.get("replaced_by"), "An item's 'replaced_by'"
            ),
            id=(
                normalize_id(data["id"], "An item's 'id'")
                if "id" in data
                else str(uuid.uuid4())
            ),
        )
