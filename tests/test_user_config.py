"""Unit tests for the UserConfig class."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.data.user_config import UserConfig


class TestUserConfig(unittest.TestCase):
    """Test cases for the UserConfig class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = UserConfig(config_dir=self.temp_dir)

    def tearDown(self):
        """Clean up test files."""
        config_file = self.temp_dir / "config.json"
        if config_file.exists():
            config_file.unlink()
        if self.temp_dir.exists():
            self.temp_dir.rmdir()

    def test_config_dir_created(self):
        """Test that config directory is created on initialization."""
        new_dir = self.temp_dir / "subdir"
        config = UserConfig(config_dir=new_dir)
        self.assertTrue(new_dir.exists())
        new_dir.rmdir()

    def test_recent_projects_empty_initially(self):
        """Test that recent projects list is empty initially."""
        recent = self.config.get_recent_projects()
        self.assertEqual(recent, [])

    def test_add_recent_project(self):
        """Test adding a project to recent list."""
        test_path = self.temp_dir / "test.pairrank"
        test_path.touch()

        self.config.add_recent_project("Test Project", test_path)

        recent = self.config.get_recent_projects()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["name"], "Test Project")
        self.assertEqual(recent[0]["path"], str(test_path.resolve()))

        test_path.unlink()

    def test_add_recent_project_with_timestamp(self):
        """Test adding a project with custom modified timestamp."""
        test_path = self.temp_dir / "test.pairrank"
        test_path.touch()
        modified = datetime(2024, 1, 15, 14, 30, 0)

        self.config.add_recent_project("Test Project", test_path, modified)

        recent = self.config.get_recent_projects()
        self.assertEqual(recent[0]["modified"], "2024-01-15T14:30:00")

        test_path.unlink()

    def test_add_existing_moves_to_top(self):
        """Test that adding existing project moves it to top."""
        path1 = self.temp_dir / "project1.pairrank"
        path2 = self.temp_dir / "project2.pairrank"
        path1.touch()
        path2.touch()

        self.config.add_recent_project("Project 1", path1)
        self.config.add_recent_project("Project 2", path2)
        self.config.add_recent_project("Project 1 Updated", path1)

        recent = self.config.get_recent_projects()
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0]["name"], "Project 1 Updated")
        self.assertEqual(recent[1]["name"], "Project 2")

        path1.unlink()
        path2.unlink()

    def test_max_recent_projects(self):
        """Test that recent projects list is limited to MAX_RECENT_PROJECTS."""
        # Create more than MAX_RECENT_PROJECTS files
        paths = []
        for i in range(self.config.MAX_RECENT_PROJECTS + 5):
            path = self.temp_dir / f"project{i}.pairrank"
            path.touch()
            paths.append(path)
            self.config.add_recent_project(f"Project {i}", path)

        recent = self.config.get_recent_projects()
        self.assertEqual(len(recent), self.config.MAX_RECENT_PROJECTS)

        # Most recent should be first
        self.assertEqual(recent[0]["name"], f"Project {len(paths) - 1}")

        for path in paths:
            path.unlink()

    def test_remove_recent_project(self):
        """Test removing a project from recent list."""
        test_path = self.temp_dir / "test.pairrank"
        test_path.touch()

        self.config.add_recent_project("Test Project", test_path)
        result = self.config.remove_recent_project(test_path)

        self.assertTrue(result)
        recent = self.config.get_recent_projects()
        self.assertEqual(len(recent), 0)

        test_path.unlink()

    def test_remove_nonexistent_project(self):
        """Test removing a project that doesn't exist."""
        test_path = self.temp_dir / "nonexistent.pairrank"

        result = self.config.remove_recent_project(test_path)

        self.assertFalse(result)

    def test_get_recent_projects_filters_missing_files(self):
        """Test that missing files are filtered from recent projects."""
        path1 = self.temp_dir / "exists.pairrank"
        path2 = self.temp_dir / "missing.pairrank"
        path1.touch()
        path2.touch()

        self.config.add_recent_project("Exists", path1)
        self.config.add_recent_project("Missing", path2)

        # Delete one file
        path2.unlink()

        recent = self.config.get_recent_projects()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["name"], "Exists")

        path1.unlink()

    def test_get_default_projects_dir(self):
        """Test getting default projects directory."""
        default_dir = self.config.get_default_projects_dir()

        self.assertIsInstance(default_dir, Path)
        # Should be under home directory
        self.assertTrue(str(default_dir).startswith(str(Path.home())))

    def test_set_default_projects_dir(self):
        """Test setting custom default projects directory."""
        custom_dir = self.temp_dir / "custom_projects"

        self.config.set_default_projects_dir(custom_dir)
        result = self.config.get_default_projects_dir()

        self.assertEqual(result, custom_dir.resolve())

    def test_config_persists_across_instances(self):
        """Test that configuration persists when creating new instance."""
        test_path = self.temp_dir / "test.pairrank"
        test_path.touch()

        self.config.add_recent_project("Persistent", test_path)

        # Create new config instance with same directory
        new_config = UserConfig(config_dir=self.temp_dir)
        recent = new_config.get_recent_projects()

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["name"], "Persistent")

        test_path.unlink()

    def test_config_file_is_json(self):
        """Test that config file is valid JSON."""
        test_path = self.temp_dir / "test.pairrank"
        test_path.touch()

        self.config.add_recent_project("Test", test_path)

        config_file = self.temp_dir / "config.json"
        self.assertTrue(config_file.exists())

        with open(config_file) as f:
            data = json.load(f)

        self.assertIn("recent_projects", data)

        test_path.unlink()


if __name__ == "__main__":
    unittest.main()
