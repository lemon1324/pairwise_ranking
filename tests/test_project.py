"""Unit tests for the Project model."""

import unittest
from datetime import datetime
from pathlib import Path

from src.models.project import Project
from src.models.item import Item
from src.models.vote import Vote
from src.models.settings import Settings


class TestProject(unittest.TestCase):
    """Test cases for the Project dataclass."""

    def test_create_project_with_name_only(self):
        """Test creating a project with just a name."""
        project = Project(name="Test Project")
        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.items, [])
        self.assertEqual(project.votes, [])
        self.assertIsInstance(project.settings, Settings)
        self.assertIsNone(project.file_path)
        self.assertIsNotNone(project.created)
        self.assertIsNotNone(project.modified)

    def test_create_project_with_all_fields(self):
        """Test creating a project with all fields."""
        items = [Item(name="Item 1"), Item(name="Item 2")]
        votes = [Vote(winner_id=items[0].id, loser_id=items[1].id, weight=1.0)]
        settings = Settings(weight_uncertainty=2.0)
        created = datetime(2024, 1, 1)
        modified = datetime(2024, 1, 15)
        file_path = Path("/test/project.pairrank")

        project = Project(
            name="Test Project",
            items=items,
            votes=votes,
            settings=settings,
            created=created,
            modified=modified,
            file_path=file_path,
        )

        self.assertEqual(project.name, "Test Project")
        self.assertEqual(len(project.items), 2)
        self.assertEqual(len(project.votes), 1)
        self.assertEqual(project.settings.weight_uncertainty, 2.0)
        self.assertEqual(project.created, created)
        self.assertEqual(project.modified, modified)
        self.assertEqual(project.file_path, file_path)

    def test_project_name_stripped(self):
        """Test that project name is stripped of whitespace."""
        project = Project(name="  Test Project  ")
        self.assertEqual(project.name, "Test Project")

    def test_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with self.assertRaises(ValueError):
            Project(name="")

    def test_whitespace_only_name_raises_error(self):
        """Test that whitespace-only name raises ValueError."""
        with self.assertRaises(ValueError):
            Project(name="   ")

    def test_to_dict(self):
        """Test converting project to dictionary."""
        items = [Item(name="Item 1", id="item-1")]
        votes = [Vote(winner_id="item-1", loser_id="item-2", weight=1.0, id="vote-1")]
        settings = Settings(weight_uncertainty=2.0)
        created = datetime(2024, 1, 1, 12, 0, 0)
        modified = datetime(2024, 1, 15, 14, 30, 0)

        project = Project(
            name="Test Project",
            items=items,
            votes=votes,
            settings=settings,
            created=created,
            modified=modified,
        )

        result = project.to_dict()

        self.assertEqual(result["name"], "Test Project")
        self.assertEqual(result["created"], "2024-01-01T12:00:00")
        self.assertEqual(result["modified"], "2024-01-15T14:30:00")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["name"], "Item 1")
        self.assertEqual(len(result["votes"]), 1)
        self.assertEqual(result["votes"][0]["id"], "vote-1")
        self.assertEqual(result["settings"]["weight_uncertainty"], 2.0)

    def test_from_dict_full(self):
        """Test creating project from dictionary with all fields."""
        data = {
            "name": "Test Project",
            "created": "2024-01-01T12:00:00",
            "modified": "2024-01-15T14:30:00",
            "items": [{"id": "item-1", "name": "Item 1", "description": "", "identifier": ""}],
            "votes": [{"id": "vote-1", "winner_id": "item-1", "loser_id": "item-2", "weight": 1.0, "timestamp": "2024-01-10T10:00:00"}],
            "settings": {"weight_uncertainty": 2.0},
        }

        project = Project.from_dict(data)

        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.created, datetime(2024, 1, 1, 12, 0, 0))
        self.assertEqual(project.modified, datetime(2024, 1, 15, 14, 30, 0))
        self.assertEqual(len(project.items), 1)
        self.assertEqual(project.items[0].name, "Item 1")
        self.assertEqual(len(project.votes), 1)
        self.assertEqual(project.votes[0].id, "vote-1")
        self.assertEqual(project.settings.weight_uncertainty, 2.0)

    def test_from_dict_minimal(self):
        """Test creating project from dictionary with minimal fields."""
        data = {"name": "Test Project"}
        project = Project.from_dict(data)

        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.items, [])
        self.assertEqual(project.votes, [])
        self.assertIsInstance(project.settings, Settings)

    def test_from_dict_with_file_path(self):
        """Test creating project from dictionary with file path."""
        data = {"name": "Test Project"}
        file_path = Path("/test/project.pairrank")

        project = Project.from_dict(data, file_path=file_path)

        self.assertEqual(project.file_path, file_path)

    def test_roundtrip_dict_conversion(self):
        """Test that to_dict and from_dict are inverses."""
        items = [Item(name="Item 1", id="item-1"), Item(name="Item 2", id="item-2")]
        votes = [Vote(winner_id="item-1", loser_id="item-2", weight=2.0, id="vote-1")]
        settings = Settings(weight_uncertainty=1.5, decay_timescale_days=60.0)
        created = datetime(2024, 1, 1, 12, 0, 0)
        modified = datetime(2024, 1, 15, 14, 30, 0)

        original = Project(
            name="Test Project",
            items=items,
            votes=votes,
            settings=settings,
            created=created,
            modified=modified,
        )

        data = original.to_dict()
        restored = Project.from_dict(data)

        self.assertEqual(original.name, restored.name)
        self.assertEqual(original.created, restored.created)
        self.assertEqual(original.modified, restored.modified)
        self.assertEqual(len(original.items), len(restored.items))
        self.assertEqual(len(original.votes), len(restored.votes))
        self.assertEqual(original.settings.weight_uncertainty, restored.settings.weight_uncertainty)
        self.assertEqual(original.settings.decay_timescale_days, restored.settings.decay_timescale_days)

    def test_from_dict_with_empty_items_and_votes(self):
        """Test creating project with empty items and votes lists."""
        data = {
            "name": "Empty Project",
            "items": [],
            "votes": [],
            "settings": {},
        }

        project = Project.from_dict(data)

        self.assertEqual(project.name, "Empty Project")
        self.assertEqual(project.items, [])
        self.assertEqual(project.votes, [])

    def test_from_dict_missing_name_raises_value_error(self):
        """Test that from_dict raises ValueError (not KeyError) when name is missing."""
        with self.assertRaises(ValueError) as ctx:
            Project.from_dict({})

        self.assertIn("name", str(ctx.exception))

    def test_from_dict_non_dict_raises_value_error(self):
        """Test that from_dict raises ValueError when data is not a dictionary."""
        with self.assertRaises(ValueError):
            Project.from_dict([])


if __name__ == "__main__":
    unittest.main()
