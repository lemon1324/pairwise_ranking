"""Unit tests for the .pairrank format version upgrades."""

import copy
import unittest

from src.data.format_version import (
    CURRENT_FORMAT_VERSION,
    FORMAT_VERSION_KEY,
    detect_version,
    upgrade,
)
from src.models.item import STATUS_ACTIVE
from src.models.project import Project


def v1_project_dict() -> dict:
    """
    Build a dictionary shaped like a real version 1 project file.

    Items carry a category but no lifecycle fields, settings are present and
    there is no format_version key.

    Returns:
        dict: A version 1 project dictionary.
    """
    return {
        "name": "Keyswitches",
        "created": "2024-01-01T12:00:00",
        "modified": "2024-02-01T12:00:00",
        "items": [
            {
                "id": "item-1",
                "name": "TTC Venus",
                "description": "Linear",
                "identifier": "6",
                "category": "Linear",
            },
            {
                "id": "item-2",
                "name": "Boba U4T",
                "description": "Tactile",
                "identifier": "7",
                "category": "Tactile",
            },
        ],
        "votes": [
            {
                "id": "vote-1",
                "winner_id": "item-1",
                "loser_id": "item-2",
                "weight": 2.0,
                "timestamp": "2024-01-10T10:00:00",
            }
        ],
        "settings": {"weight_uncertainty": 1.5, "cross_category_rate": 0.2},
    }


class TestDetectVersion(unittest.TestCase):
    """Test cases for detect_version."""

    def test_missing_key_means_version_one(self):
        """Test that a file without a version key is version 1."""
        self.assertEqual(detect_version({"name": "P"}), 1)

    def test_explicit_version(self):
        """Test that an explicit version key is returned."""
        self.assertEqual(detect_version({FORMAT_VERSION_KEY: 2}), 2)

    def test_null_version_means_version_one(self):
        """Test that a null version key is treated as version 1."""
        self.assertEqual(detect_version({FORMAT_VERSION_KEY: None}), 1)

    def test_invalid_version_raises(self):
        """Test that a non-numeric version raises ValueError."""
        with self.assertRaises(ValueError):
            detect_version({FORMAT_VERSION_KEY: "two"})

    def test_zero_version_raises(self):
        """Test that a version below 1 raises ValueError."""
        with self.assertRaises(ValueError):
            detect_version({FORMAT_VERSION_KEY: 0})

    def test_non_dict_raises(self):
        """Test that non-object data raises ValueError."""
        with self.assertRaises(ValueError):
            detect_version([])


class TestUpgrade(unittest.TestCase):
    """Test cases for the upgrade function."""

    def test_v1_upgrades_to_current(self):
        """Test that a version 1 dictionary is upgraded with defaults."""
        upgraded, started_at = upgrade(v1_project_dict())

        self.assertEqual(started_at, 1)
        self.assertEqual(upgraded[FORMAT_VERSION_KEY], CURRENT_FORMAT_VERSION)
        self.assertEqual(upgraded["slots"], [])
        for item in upgraded["items"]:
            self.assertEqual(item["status"], STATUS_ACTIVE)
            self.assertIsNone(item["retired_at"])
            self.assertIsNone(item["replaced_by"])

    def test_v1_upgrade_keeps_existing_categories(self):
        """Test that the upgrade does not overwrite an existing category."""
        upgraded, _ = upgrade(v1_project_dict())
        self.assertEqual(upgraded["items"][0]["category"], "Linear")

    def test_v1_upgrade_adds_default_category(self):
        """Test that an item without a category gets the default one."""
        data = v1_project_dict()
        del data["items"][0]["category"]

        upgraded, _ = upgrade(data)
        self.assertEqual(upgraded["items"][0]["category"], "Default")

    def test_upgrade_does_not_modify_input(self):
        """Test that upgrade returns a copy and leaves the input alone."""
        data = v1_project_dict()
        original = copy.deepcopy(data)

        upgrade(data)

        self.assertEqual(data, original)

    def test_v2_passes_through_unchanged(self):
        """Test that a current-version dictionary is returned unchanged."""
        data = Project(name="Already Current", slots=["1", "2"]).to_dict()

        upgraded, started_at = upgrade(data)

        self.assertEqual(started_at, CURRENT_FORMAT_VERSION)
        self.assertEqual(upgraded, data)

    def test_newer_version_raises(self):
        """Test that a file from a newer application version is rejected."""
        data = {"name": "Future", FORMAT_VERSION_KEY: CURRENT_FORMAT_VERSION + 1}

        with self.assertRaises(ValueError) as ctx:
            upgrade(data)

        self.assertIn("newer", str(ctx.exception))

    def test_upgraded_v1_loads_as_all_active_project(self):
        """Test that real-shaped v1 data becomes an all-active project."""
        upgraded, _ = upgrade(v1_project_dict())
        project = Project.from_dict(upgraded)

        self.assertEqual(len(project.items), 2)
        self.assertEqual(len(project.active_items()), 2)
        self.assertTrue(all(item.is_active() for item in project.items))
        self.assertEqual(project.slots, [])
        self.assertEqual(project.active_identifiers(), {"6", "7"})
        self.assertEqual(project.settings.cross_category_rate, 0.2)
        self.assertEqual(len(project.votes), 1)


if __name__ == "__main__":
    unittest.main()
