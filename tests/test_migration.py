"""Unit tests for the StorageMigration class."""

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.data.migration import StorageMigration
from src.data.project_storage import ProjectStorage


class TestStorageMigration(unittest.TestCase):
    """Test cases for the StorageMigration class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test files."""
        for file in self.temp_dir.iterdir():
            file.unlink()
        self.temp_dir.rmdir()

    def _create_old_format_files(self, items=None, votes=None, settings=None):
        """Helper to create old format CSV/JSON files."""
        # Create items.csv
        items_file = self.temp_dir / "items.csv"
        with open(items_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name", "identifier", "description"])
            writer.writeheader()
            for item in (items or []):
                writer.writerow(item)

        # Create votes.csv
        votes_file = self.temp_dir / "votes.csv"
        with open(votes_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "winner_id", "loser_id", "timestamp", "weight"])
            writer.writeheader()
            for vote in (votes or []):
                writer.writerow(vote)

        # Create settings.json
        settings_file = self.temp_dir / "settings.json"
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(settings or {}, f)

    def test_needs_migration_empty_dir(self):
        """Test that empty directory doesn't need migration."""
        result = StorageMigration.needs_migration(self.temp_dir)
        self.assertFalse(result)

    def test_needs_migration_nonexistent_dir(self):
        """Test that non-existent directory doesn't need migration."""
        nonexistent = self.temp_dir / "nonexistent"
        result = StorageMigration.needs_migration(nonexistent)
        self.assertFalse(result)

    def test_needs_migration_with_old_files(self):
        """Test that directory with old files needs migration."""
        self._create_old_format_files()
        result = StorageMigration.needs_migration(self.temp_dir)
        self.assertTrue(result)

    def test_needs_migration_false_if_pairrank_exists(self):
        """Test that migration not needed if .pairrank file exists."""
        self._create_old_format_files()
        # Create a .pairrank file
        pairrank_file = self.temp_dir / "project.pairrank"
        pairrank_file.write_text('{"name": "Test"}')

        result = StorageMigration.needs_migration(self.temp_dir)
        self.assertFalse(result)

    def test_migrate_empty_data(self):
        """Test migrating empty old format data."""
        self._create_old_format_files()

        project = StorageMigration.migrate(self.temp_dir)

        self.assertEqual(project.name, "Migrated Project")
        self.assertEqual(project.items, [])
        self.assertEqual(project.votes, [])
        self.assertIsNotNone(project.file_path)
        self.assertTrue(project.file_path.exists())

    def test_migrate_with_items(self):
        """Test migrating data with items."""
        items = [
            {"id": "item-1", "name": "Item 1", "identifier": "A", "description": "Desc 1"},
            {"id": "item-2", "name": "Item 2", "identifier": "", "description": ""},
        ]
        self._create_old_format_files(items=items)

        project = StorageMigration.migrate(self.temp_dir)

        self.assertEqual(len(project.items), 2)
        self.assertEqual(project.items[0].name, "Item 1")
        self.assertEqual(project.items[0].identifier, "A")
        self.assertEqual(project.items[1].name, "Item 2")

    def test_migrate_with_votes(self):
        """Test migrating data with votes."""
        votes = [
            {"id": "vote-1", "winner_id": "item-1", "loser_id": "item-2", "timestamp": "2024-01-15T12:00:00", "weight": "2.0"},
        ]
        self._create_old_format_files(votes=votes)

        project = StorageMigration.migrate(self.temp_dir)

        self.assertEqual(len(project.votes), 1)
        self.assertEqual(project.votes[0].winner_id, "item-1")
        self.assertEqual(project.votes[0].weight, 2.0)

    def test_migrate_with_settings(self):
        """Test migrating data with custom settings."""
        settings = {
            "weight_uncertainty": 2.5,
            "decay_timescale_days": 90.0,
        }
        self._create_old_format_files(settings=settings)

        project = StorageMigration.migrate(self.temp_dir)

        self.assertEqual(project.settings.weight_uncertainty, 2.5)
        self.assertEqual(project.settings.decay_timescale_days, 90.0)

    def test_migrate_creates_pairrank_file(self):
        """Test that migration creates .pairrank file in data directory."""
        self._create_old_format_files()

        project = StorageMigration.migrate(self.temp_dir)

        expected_path = self.temp_dir / "project.pairrank"
        self.assertEqual(project.file_path, expected_path)
        self.assertTrue(expected_path.exists())

    def test_migrate_custom_project_name(self):
        """Test migrating with custom project name."""
        self._create_old_format_files()

        project = StorageMigration.migrate(self.temp_dir, project_name="Custom Name")

        self.assertEqual(project.name, "Custom Name")

    def test_migrate_custom_output_filename(self):
        """Test migrating with custom output filename."""
        self._create_old_format_files()

        project = StorageMigration.migrate(self.temp_dir, output_filename="custom.pairrank")

        expected_path = self.temp_dir / "custom.pairrank"
        self.assertEqual(project.file_path, expected_path)
        self.assertTrue(expected_path.exists())

    def test_migrate_created_timestamp_from_votes(self):
        """Test that created timestamp comes from oldest vote."""
        votes = [
            {"id": "vote-1", "winner_id": "item-1", "loser_id": "item-2", "timestamp": "2024-01-15T12:00:00", "weight": "1.0"},
            {"id": "vote-2", "winner_id": "item-2", "loser_id": "item-1", "timestamp": "2024-01-10T10:00:00", "weight": "1.0"},
        ]
        self._create_old_format_files(votes=votes)

        project = StorageMigration.migrate(self.temp_dir)

        # Should use oldest vote timestamp as created time
        self.assertEqual(project.created, datetime(2024, 1, 10, 10, 0, 0))

    def test_cleanup_old_files(self):
        """Test cleaning up old format files after migration."""
        self._create_old_format_files()
        StorageMigration.migrate(self.temp_dir)

        deleted = StorageMigration.cleanup_old_files(self.temp_dir)

        self.assertEqual(len(deleted), 3)
        self.assertFalse((self.temp_dir / "items.csv").exists())
        self.assertFalse((self.temp_dir / "votes.csv").exists())
        self.assertFalse((self.temp_dir / "settings.json").exists())

    def test_cleanup_requires_pairrank_file(self):
        """Test that cleanup requires .pairrank file to exist."""
        self._create_old_format_files()

        with self.assertRaises(ValueError):
            StorageMigration.cleanup_old_files(self.temp_dir)

    def test_migrate_nonexistent_dir_raises_error(self):
        """Test that migrating non-existent directory raises error."""
        nonexistent = self.temp_dir / "nonexistent"

        with self.assertRaises(FileNotFoundError):
            StorageMigration.migrate(nonexistent)


if __name__ == "__main__":
    unittest.main()
