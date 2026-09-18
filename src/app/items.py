"""Qt-free validation of the item form.

Both frontends put the same form in front of the user - name, category,
identifier, description - and both have to reach the same verdict on it. The
rules live here; the wording of the complaints, and whether they arrive as a
message box or as inline text, belongs to the frontend.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

from src.models.item import DEFAULT_CATEGORY


# Field names used as the keys of a verdict's error mapping.
FIELD_NAME = "name"
FIELD_IDENTIFIER = "identifier"


class ItemFieldError(Enum):
    """
    What is wrong with one field of the item form.

    Attributes:
        NAME_REQUIRED: The name is empty once surrounding whitespace is
            stripped.
        IDENTIFIER_IN_USE: Another active item already holds the identifier.
    """

    NAME_REQUIRED = "name_required"
    IDENTIFIER_IN_USE = "identifier_in_use"


@dataclass(frozen=True)
class ItemForm:
    """
    The item form's values after cleaning.

    Attributes:
        name: The name with surrounding whitespace stripped.
        description: The description, stripped.
        identifier: The identifier, stripped. Empty means the item holds none.
        category: The category, stripped, or DEFAULT_CATEGORY when it was left
            empty.
    """

    name: str
    description: str
    identifier: str
    category: str


@dataclass(frozen=True)
class ItemFormVerdict:
    """
    The result of validating an item form.

    Attributes:
        form: The cleaned values, whether or not they are valid.
        errors: Field name to the error found there, in the order the fields
            are checked, so a frontend that reports one complaint at a time
            reports the name before the identifier.
    """

    form: ItemForm
    errors: dict[str, ItemFieldError] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """
        Check whether the form can be accepted.

        Returns:
            bool: True when no field carries an error.
        """
        return not self.errors


def validate_item_form(
    name: str,
    description: str = "",
    identifier: str = "",
    category: str = "",
    taken_identifiers: Optional[Iterable[str]] = None,
) -> ItemFormVerdict:
    """
    Check the values of an item form.

    Only two things can be wrong: a missing name, and an identifier that
    another active item already holds. In particular an identifier is checked
    only when it is given, and only against the identifiers the caller passes
    in; free text is accepted even when the project defines slots, because a
    slot list is a suggestion rather than a closed set. Names need not be
    unique.

    Args:
        name: The name as entered.
        description: The description as entered.
        identifier: The identifier as entered. An empty identifier is always
            allowed; it simply means the item holds none.
        category: The category as entered. An empty category becomes
            DEFAULT_CATEGORY.
        taken_identifiers: Identifiers held by the other active items, usually
            from :meth:`~src.app.session.ProjectSession.taken_identifiers`.

    Returns:
        ItemFormVerdict: The cleaned values and any field errors.
    """
    form = ItemForm(
        name=(name or "").strip(),
        description=(description or "").strip(),
        identifier=(identifier or "").strip(),
        category=(category or "").strip() or DEFAULT_CATEGORY,
    )

    errors: dict[str, ItemFieldError] = {}
    if not form.name:
        errors[FIELD_NAME] = ItemFieldError.NAME_REQUIRED
    if form.identifier and form.identifier in set(taken_identifiers or ()):
        errors[FIELD_IDENTIFIER] = ItemFieldError.IDENTIFIER_IN_USE

    return ItemFormVerdict(form=form, errors=errors)
