"""Unit tests for the LegacyCsvStorage read-only loader."""

import csv
import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.data.legacy_storage import LegacyCsvStorage
from src.models.settings import Settings


class LegacyStorageTestCase(unittest.TestCase):
    """Base class providing a temp directory and raw fixture writers."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = Path(tempfile.mkdtemp())
        self.storage = LegacyCsvStorage(self.tmpdir)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.tmpdir)

    def _write_items_csv(self, rows: list[dict]) -> None:
        """Write an items.csv fixture directly."""
        with open(self.storage.items_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LegacyCsvStorage.ITEMS_FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_votes_csv(self, rows: list[dict]) -> None:
        """Write a votes.csv fixture directly."""
        with open(self.storage.votes_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LegacyCsvStorage.VOTES_FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_settings_json(self, data: dict) -> None:
        """Write a settings.json fixture directly."""
        with open(self.storage.settings_file, "w", encoding="utf-8") as f:
            json.dump(data, f)


class TestLegacyCsvStorageInit(unittest.TestCase):
    """Test cases for LegacyCsvStorage initialization."""

    def test_does_not_create_data_directory(self):
        """Test that the loader has no directory-creating side effect."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "missing_data_dir"
            self.assertFalse(data_dir.exists())

            LegacyCsvStorage(data_dir)
            self.assertFalse(data_dir.exists())

    def test_uses_existing_directory(self):
        """Test that the loader works with an existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LegacyCsvStorage(tmpdir)
            self.assertEqual(storage.data_dir, Path(tmpdir))

    def test_file_paths_set_correctly(self):
        """Test that file paths are set correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LegacyCsvStorage(tmpdir)
            self.assertEqual(storage.items_file.name, "items.csv")
            self.assertEqual(storage.votes_file.name, "votes.csv")
            self.assertEqual(storage.settings_file.name, "settings.json")

    def test_missing_directory_loads_empty(self):
        """Test that a non-existent directory yields empty data and defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LegacyCsvStorage(Path(tmpdir) / "nope")

            self.assertEqual(storage.load_items(), [])
            self.assertEqual(storage.load_votes(), [])
            self.assertEqual(
                storage.load_settings().weight_uncertainty,
                Settings().weight_uncertainty,
            )


class TestLegacyCsvStorageItems(LegacyStorageTestCase):
    """Test cases for loading items."""

    def test_load_items_empty(self):
        """Test loading items when no file exists."""
        self.assertEqual(self.storage.load_items(), [])

    def test_load_items_header_only(self):
        """Test loading items from a file containing only the header."""
        self._write_items_csv([])
        self.assertEqual(self.storage.load_items(), [])

    def test_load_multiple_items(self):
        """Test loading multiple items."""
        self._write_items_csv([
            {"id": "id-1", "name": "Item 1", "identifier": "", "description": ""},
            {"id": "id-2", "name": "Item 2", "identifier": "", "description": "Desc 2"},
            {"id": "id-3", "name": "Item 3", "identifier": "", "description": ""},
        ])

        loaded = self.storage.load_items()
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0].id, "id-1")
        self.assertEqual(loaded[0].name, "Item 1")
        self.assertEqual(loaded[1].description, "Desc 2")

    def test_load_item_with_identifier(self):
        """Test loading an item that has an identifier."""
        self._write_items_csv([
            {"id": "test-id", "name": "Test Item", "identifier": "A-1", "description": "Test"},
        ])

        loaded = self.storage.load_items()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].identifier, "A-1")
        self.assertTrue(loaded[0].has_identifier())

    def test_load_item_without_identifier(self):
        """Test loading an item that has no identifier."""
        self._write_items_csv([
            {"id": "test-id", "name": "Test Item", "identifier": "", "description": "Test"},
        ])

        loaded = self.storage.load_items()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].identifier, "")
        self.assertFalse(loaded[0].has_identifier())

    def test_load_item_with_special_characters(self):
        """Test loading an item whose fields contain quotes, commas and newlines."""
        self._write_items_csv([
            {
                "id": "special-id",
                "name": 'Item with "quotes" and, commas',
                "identifier": "",
                "description": "Line 1\nLine 2",
            },
        ])

        loaded = self.storage.load_items()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, 'Item with "quotes" and, commas')
        self.assertEqual(loaded[0].description, "Line 1\nLine 2")

    def test_load_items_gets_default_category(self):
        """Test that legacy rows without a category get the default category."""
        self._write_items_csv([
            {"id": "id-1", "name": "Item 1", "identifier": "", "description": ""},
        ])

        loaded = self.storage.load_items()
        self.assertEqual(loaded[0].category, "Default")


class TestLegacyCsvStorageVotes(LegacyStorageTestCase):
    """Test cases for loading votes."""

    def test_load_votes_empty(self):
        """Test loading votes when no file exists."""
        self.assertEqual(self.storage.load_votes(), [])

    def test_load_votes_header_only(self):
        """Test loading votes from a file containing only the header."""
        self._write_votes_csv([])
        self.assertEqual(self.storage.load_votes(), [])

    def test_load_single_vote(self):
        """Test loading a single vote."""
        self._write_votes_csv([
            {
                "id": "vote-id",
                "winner_id": "item1",
                "loser_id": "item2",
                "timestamp": "2024-01-15T12:30:00",
                "weight": "2.0",
            },
        ])

        loaded = self.storage.load_votes()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "vote-id")
        self.assertEqual(loaded[0].winner_id, "item1")
        self.assertEqual(loaded[0].loser_id, "item2")
        self.assertEqual(loaded[0].weight, 2.0)
        self.assertEqual(loaded[0].timestamp, datetime(2024, 1, 15, 12, 30, 0))

    def test_load_multiple_votes(self):
        """Test loading multiple votes."""
        self._write_votes_csv([
            {"id": "v1", "winner_id": "a", "loser_id": "b",
             "timestamp": "2024-01-01T00:00:00", "weight": "1.0"},
            {"id": "v2", "winner_id": "b", "loser_id": "c",
             "timestamp": "2024-01-02T00:00:00", "weight": "2.0"},
            {"id": "v3", "winner_id": "c", "loser_id": "a",
             "timestamp": "2024-01-03T00:00:00", "weight": "3.0"},
        ])

        loaded = self.storage.load_votes()
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0].winner_id, "a")
        self.assertEqual(loaded[1].weight, 2.0)

    def test_load_votes_skips_invalid_rows(self):
        """Test that rows with an unparseable field are skipped, not fatal."""
        self._write_votes_csv([
            {"id": "v1", "winner_id": "a", "loser_id": "b",
             "timestamp": "not-a-timestamp", "weight": "1.0"},
            {"id": "v2", "winner_id": "b", "loser_id": "c",
             "timestamp": "2024-01-02T00:00:00", "weight": "2.0"},
        ])

        loaded = self.storage.load_votes()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "v2")


class TestLegacyCsvStorageSettings(LegacyStorageTestCase):
    """Test cases for loading settings."""

    def test_load_settings_default(self):
        """Test loading settings when no file exists returns defaults."""
        settings = self.storage.load_settings()
        default = Settings()

        self.assertEqual(settings.weight_uncertainty, default.weight_uncertainty)
        self.assertEqual(settings.top_tier_mode, default.top_tier_mode)

    def test_load_settings(self):
        """Test loading settings from JSON."""
        self._write_settings_json({
            "weight_uncertainty": 2.5,
            "top_tier_mode": True,
            "decay_timescale_days": 45.0,
        })

        loaded = self.storage.load_settings()
        self.assertEqual(loaded.weight_uncertainty, 2.5)
        self.assertTrue(loaded.top_tier_mode)
        self.assertEqual(loaded.decay_timescale_days, 45.0)

    def test_load_settings_partial(self):
        """Test that missing keys fall back to defaults."""
        self._write_settings_json({"weight_uncertainty": 2.0})

        loaded = self.storage.load_settings()
        default = Settings()
        self.assertEqual(loaded.weight_uncertainty, 2.0)
        self.assertEqual(loaded.weight_connectivity, default.weight_connectivity)

    def test_load_settings_invalid_json(self):
        """Test loading settings with invalid JSON returns defaults."""
        self.storage.settings_file.write_text("not valid json {", encoding="utf-8")

        settings = self.storage.load_settings()
        default = Settings()
        self.assertEqual(settings.weight_uncertainty, default.weight_uncertainty)


if __name__ == "__main__":
    unittest.main()
