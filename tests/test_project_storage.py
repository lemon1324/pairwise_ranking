"""Unit tests for the ProjectStorage class."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.data.project_storage import ProjectStorage
from src.models.project import Project
from src.models.item import Item
from src.models.vote import Vote
from src.models.settings import Settings


class TestProjectStorage(unittest.TestCase):
    """Test cases for the ProjectStorage class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / "test.pairrank"

    def tearDown(self):
        """Clean up test files."""
        if self.test_file.exists():
            self.test_file.unlink()
        Path(self.temp_dir).rmdir()

    def test_save_and_load_empty_project(self):
        """Test saving and loading an empty project."""
        project = Project(name="Empty Project")
        project.file_path = self.test_file

        ProjectStorage.save(project, self.test_file)
        loaded = ProjectStorage.load(self.test_file)

        self.assertEqual(loaded.name, "Empty Project")
        self.assertEqual(loaded.items, [])
        self.assertEqual(loaded.votes, [])
        self.assertEqual(loaded.file_path, self.test_file)

    def test_save_and_load_full_project(self):
        """Test saving and loading a project with items, votes, and settings."""
        items = [Item(name="Item 1", id="item-1"), Item(name="Item 2", id="item-2")]
        votes = [Vote(winner_id="item-1", loser_id="item-2", weight=2.0, id="vote-1")]
        settings = Settings(weight_uncertainty=1.5, decay_timescale_days=60.0)

        project = Project(
            name="Full Project",
            items=items,
            votes=votes,
            settings=settings,
            file_path=self.test_file,
        )

        ProjectStorage.save(project, self.test_file)
        loaded = ProjectStorage.load(self.test_file)

        self.assertEqual(loaded.name, "Full Project")
        self.assertEqual(len(loaded.items), 2)
        self.assertEqual(loaded.items[0].name, "Item 1")
        self.assertEqual(len(loaded.votes), 1)
        self.assertEqual(loaded.votes[0].weight, 2.0)
        self.assertEqual(loaded.settings.weight_uncertainty, 1.5)
        self.assertEqual(loaded.settings.decay_timescale_days, 60.0)

    def test_save_updates_modified_timestamp(self):
        """Test that saving updates the modified timestamp."""
        project = Project(name="Test Project")
        original_modified = project.modified

        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.01)

        ProjectStorage.save(project, self.test_file)

        self.assertGreater(project.modified, original_modified)

    def test_save_sets_file_path(self):
        """Test that saving sets the project's file_path."""
        project = Project(name="Test Project")
        self.assertIsNone(project.file_path)

        ProjectStorage.save(project, self.test_file)

        self.assertEqual(project.file_path, self.test_file)

    def test_save_invalid_extension_raises_error(self):
        """Test that saving with wrong extension raises ValueError."""
        project = Project(name="Test Project")
        invalid_path = Path(self.temp_dir) / "test.json"

        with self.assertRaises(ValueError):
            ProjectStorage.save(project, invalid_path)

    def test_load_nonexistent_file_raises_error(self):
        """Test that loading non-existent file raises FileNotFoundError."""
        nonexistent = Path(self.temp_dir) / "nonexistent.pairrank"

        with self.assertRaises(FileNotFoundError):
            ProjectStorage.load(nonexistent)

    def test_load_invalid_extension_raises_error(self):
        """Test that loading file with wrong extension raises ValueError."""
        invalid_path = Path(self.temp_dir) / "test.json"
        invalid_path.write_text("{}")

        try:
            with self.assertRaises(ValueError):
                ProjectStorage.load(invalid_path)
        finally:
            invalid_path.unlink()

    def test_load_sets_file_path(self):
        """Test that loading sets the project's file_path."""
        project = Project(name="Test Project")
        ProjectStorage.save(project, self.test_file)

        loaded = ProjectStorage.load(self.test_file)

        self.assertEqual(loaded.file_path, self.test_file)

    def test_create_new_project(self):
        """Test creating a new empty project."""
        project = ProjectStorage.create_new("New Project", self.test_file)

        self.assertEqual(project.name, "New Project")
        self.assertEqual(project.items, [])
        self.assertEqual(project.votes, [])
        self.assertEqual(project.file_path, self.test_file)
        self.assertTrue(self.test_file.exists())

    def test_create_new_saves_to_file(self):
        """Test that create_new actually saves the file."""
        ProjectStorage.create_new("New Project", self.test_file)

        # Verify file exists and contains valid JSON
        self.assertTrue(self.test_file.exists())
        with open(self.test_file) as f:
            data = json.load(f)
        self.assertEqual(data["name"], "New Project")

    def test_save_creates_parent_directory(self):
        """Test that saving creates parent directories if needed."""
        nested_path = Path(self.temp_dir) / "subdir" / "test.pairrank"
        project = Project(name="Test Project")

        ProjectStorage.save(project, nested_path)

        self.assertTrue(nested_path.exists())
        nested_path.unlink()
        nested_path.parent.rmdir()

    def test_file_format_is_json(self):
        """Test that saved files are valid JSON."""
        project = Project(name="JSON Test")
        ProjectStorage.save(project, self.test_file)

        with open(self.test_file) as f:
            data = json.load(f)

        self.assertIn("name", data)
        self.assertIn("items", data)
        self.assertIn("votes", data)
        self.assertIn("settings", data)
        self.assertIn("created", data)
        self.assertIn("modified", data)

    def test_file_format_is_human_readable(self):
        """Test that saved files are formatted with indentation."""
        project = Project(name="Format Test")
        ProjectStorage.save(project, self.test_file)

        content = self.test_file.read_text()

        # Should have newlines and indentation
        self.assertIn("\n", content)
        self.assertIn("  ", content)


if __name__ == "__main__":
    unittest.main()
