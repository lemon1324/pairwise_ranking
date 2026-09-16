"""Versioned upgrades for the .pairrank project file format.

Project files carry a top-level ``format_version``. Files written before the
key existed are version 1. :func:`upgrade` walks a parsed file forward through
the registered upgrade steps to :data:`CURRENT_FORMAT_VERSION`;
:class:`~src.data.project_storage.ProjectStorage` performs the upgrade on load,
writes a one-time backup of the original file and re-saves it in the new
format so that the migration only happens once.

The version constant itself lives in :mod:`src.models.project`, beside the
serialization that writes it, and is re-exported here for convenience.
"""

import copy
from typing import Callable

from src.models.item import DEFAULT_CATEGORY, STATUS_ACTIVE
from src.models.project import CURRENT_FORMAT_VERSION

__all__ = [
    "CURRENT_FORMAT_VERSION",
    "FORMAT_VERSION_KEY",
    "detect_version",
    "upgrade",
]

# Top-level key holding the format version of a project file
FORMAT_VERSION_KEY = "format_version"


def detect_version(data: dict) -> int:
    """
    Determine which format version a parsed project file uses.

    Args:
        data: The parsed contents of a .pairrank file.

    Returns:
        int: The file's format version. A missing key means version 1, the
        format that existed before versioning was introduced.

    Raises:
        ValueError: If the data is not a JSON object, or if the version key is
            present but is not a positive whole number.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"Project data must be a JSON object, got {type(data).__name__}"
        )

    raw = data.get(FORMAT_VERSION_KEY)
    if raw is None:
        return 1

    if isinstance(raw, bool):
        raise ValueError(f"Invalid {FORMAT_VERSION_KEY}: {raw!r}")

    try:
        version = int(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid {FORMAT_VERSION_KEY}: {raw!r}") from e

    if version < 1:
        raise ValueError(f"Invalid {FORMAT_VERSION_KEY}: {raw!r}")

    return version


def _v1_to_v2(data: dict) -> dict:
    """
    Upgrade a version 1 project dictionary to version 2.

    Version 2 adds the project-level slot list and the item lifecycle fields.

    Args:
        data: A version 1 project dictionary. Modified in place.

    Returns:
        dict: The same dictionary, now in version 2 shape.
    """
    data[FORMAT_VERSION_KEY] = 2
    data["slots"] = data.get("slots") or []

    items = data.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            item.setdefault("category", DEFAULT_CATEGORY)
            item.setdefault("status", STATUS_ACTIVE)
            item.setdefault("retired_at", None)
            item.setdefault("replaced_by", None)

    return data


# Upgrade steps keyed by the version they upgrade from
_UPGRADE_STEPS: dict[int, Callable[[dict], dict]] = {
    1: _v1_to_v2,
}


def upgrade(data: dict) -> tuple[dict, int]:
    """
    Upgrade a parsed project file to the current format version.

    Args:
        data: The parsed contents of a .pairrank file. Not modified.

    Returns:
        tuple[dict, int]: An upgraded copy of the data and the version the
        data started at. When the data is already current the copy is
        unchanged and the starting version equals CURRENT_FORMAT_VERSION.

    Raises:
        ValueError: If the file's version is newer than this code understands,
            or if no upgrade step is registered for an intermediate version.
    """
    started_at = detect_version(data)

    if started_at > CURRENT_FORMAT_VERSION:
        raise ValueError(
            f"Project file format version {started_at} is newer than this "
            f"application supports (version {CURRENT_FORMAT_VERSION}). "
            "Please update the application."
        )

    upgraded = copy.deepcopy(data)
    version = started_at
    while version < CURRENT_FORMAT_VERSION:
        step = _UPGRADE_STEPS.get(version)
        if step is None:
            raise ValueError(
                f"No upgrade path from project file format version {version}"
            )
        upgraded = step(upgraded)
        version += 1

    return upgraded, started_at
