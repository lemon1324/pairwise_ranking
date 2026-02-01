"""Unit tests for the Storage class."""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.data.storage import Storage
from src.models.settings import Settings
from src.models.item import Item
from src.models.vote import Vote


class TestSettings(unittest.TestCase):
    """Test cases for the Settings dataclass."""

    def test_default_settings(self):
        """Test that default settings have expected values."""
        settings = Settings()
        self.assertEqual(settings.weight_uncertainty, 1.0)
        self.assertEqual(settings.weight_connectivity, 1.0)
        self.assertEqual(settings.weight_freshness, 0.5)
        self.assertEqual(settings.weight_uncompared, 2.0)
        self.assertEqual(settings.decay_timescale_days, 30.0)
        self.assertFalse(settings.top_tier_mode)
        self.assertEqual(settings.top_tier_count, 10)
        self.assertEqual(settings.top_tier_weight, 2.0)
        self.assertFalse(settings.blinded_comparison_mode)

    def test_custom_settings(self):
        """Test creating settings with custom values."""
        settings = Settings(
            weight_uncertainty=2.0,
            top_tier_mode=True,
            top_tier_count=5,
        )
        self.assertEqual(settings.weight_uncertainty, 2.0)
        self.assertTrue(settings.top_tier_mode)
        self.assertEqual(settings.top_tier_count, 5)

    def test_to_dict(self):
        """Test converting settings to dictionary."""
        settings = Settings(weight_uncertainty=1.5, top_tier_mode=True)
        result = settings.to_dict()

        self.assertEqual(result["weight_uncertainty"], 1.5)
        self.assertTrue(result["top_tier_mode"])
        self.assertIn("decay_timescale_days", result)

    def test_from_dict_full(self):
        """Test creating settings from complete dictionary."""
        data = {
            "weight_uncertainty": 2.0,
            "weight_connectivity": 1.5,
            "weight_freshness": 0.8,
            "weight_uncompared": 3.0,
            "decay_timescale_days": 60.0,
            "top_tier_mode": True,
            "top_tier_count": 15,
            "top_tier_weight": 2.5,
        }
        settings = Settings.from_dict(data)

        self.assertEqual(settings.weight_uncertainty, 2.0)
        self.assertEqual(settings.weight_connectivity, 1.5)
        self.assertEqual(settings.decay_timescale_days, 60.0)
        self.assertTrue(settings.top_tier_mode)
        self.assertEqual(settings.top_tier_count, 15)

    def test_from_dict_partial(self):
        """Test creating settings from partial dictionary uses defaults."""
        data = {"weight_uncertainty": 2.0}
        settings = Settings.from_dict(data)

        self.assertEqual(settings.weight_uncertainty, 2.0)
        self.assertEqual(settings.weight_connectivity, 1.0)  # default
        self.assertEqual(settings.decay_timescale_days, 30.0)  # default

    def test_from_dict_empty(self):
        """Test creating settings from empty dictionary uses all defaults."""
        settings = Settings.from_dict({})
        default = Settings()

        self.assertEqual(settings.weight_uncertainty, default.weight_uncertainty)
        self.assertEqual(settings.top_tier_mode, default.top_tier_mode)

    def test_roundtrip_dict_conversion(self):
        """Test that to_dict and from_dict are inverses."""
        original = Settings(
            weight_uncertainty=2.5,
            top_tier_mode=True,
            decay_timescale_days=45.0,
        )
        data = original.to_dict()
        restored = Settings.from_dict(data)

        self.assertEqual(original.weight_uncertainty, restored.weight_uncertainty)
        self.assertEqual(original.top_tier_mode, restored.top_tier_mode)
        self.assertEqual(original.decay_timescale_days, restored.decay_timescale_days)


class TestStorageInit(unittest.TestCase):
    """Test cases for Storage initialization."""

    def test_creates_data_directory(self):
        """Test that Storage creates the data directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "new_data_dir"
            self.assertFalse(data_dir.exists())

            storage = Storage(data_dir)
            self.assertTrue(data_dir.exists())

    def test_uses_existing_directory(self):
        """Test that Storage works with existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(tmpdir)
            self.assertEqual(storage.data_dir, Path(tmpdir))

    def test_file_paths_set_correctly(self):
        """Test that file paths are set correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(tmpdir)
            self.assertEqual(storage.items_file.name, "items.csv")
            self.assertEqual(storage.votes_file.name, "votes.csv")
            self.assertEqual(storage.settings_file.name, "settings.json")


class TestStorageItems(unittest.TestCase):
    """Test cases for item storage operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.storage = Storage(self.tmpdir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_load_items_empty(self):
        """Test loading items when no file exists."""
        items = self.storage.load_items()
        self.assertEqual(items, [])

    def test_save_and_load_single_item(self):
        """Test saving and loading a single item."""
        item = Item(name="Test Item", description="Test Description", id="test-id")
        self.storage.save_item(item)

        items = self.storage.load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "test-id")
        self.assertEqual(items[0].name, "Test Item")
        self.assertEqual(items[0].description, "Test Description")

    def test_save_and_load_multiple_items(self):
        """Test saving and loading multiple items."""
        items_to_save = [
            Item(name="Item 1", id="id-1"),
            Item(name="Item 2", description="Desc 2", id="id-2"),
            Item(name="Item 3", id="id-3"),
        ]
        self.storage.save_items(items_to_save)

        loaded = self.storage.load_items()
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0].name, "Item 1")
        self.assertEqual(loaded[1].description, "Desc 2")

    def test_save_items_overwrites(self):
        """Test that save_items overwrites existing content."""
        self.storage.save_item(Item(name="Old Item", id="old-id"))
        self.storage.save_items([Item(name="New Item", id="new-id")])

        items = self.storage.load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "new-id")

    def test_save_item_appends(self):
        """Test that save_item appends to existing content."""
        self.storage.save_item(Item(name="Item 1", id="id-1"))
        self.storage.save_item(Item(name="Item 2", id="id-2"))

        items = self.storage.load_items()
        self.assertEqual(len(items), 2)

    def test_update_item(self):
        """Test updating an existing item."""
        item = Item(name="Original", description="", id="test-id")
        self.storage.save_item(item)

        updated = Item(name="Updated", description="New desc", id="test-id")
        result = self.storage.update_item(updated)

        self.assertTrue(result)
        items = self.storage.load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "Updated")
        self.assertEqual(items[0].description, "New desc")

    def test_update_item_not_found(self):
        """Test updating a non-existent item returns False."""
        item = Item(name="Test", id="nonexistent-id")
        result = self.storage.update_item(item)
        self.assertFalse(result)

    def test_delete_item(self):
        """Test deleting an item."""
        self.storage.save_items([
            Item(name="Item 1", id="id-1"),
            Item(name="Item 2", id="id-2"),
        ])

        result = self.storage.delete_item("id-1")
        self.assertTrue(result)

        items = self.storage.load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "id-2")

    def test_delete_item_not_found(self):
        """Test deleting a non-existent item returns False."""
        result = self.storage.delete_item("nonexistent-id")
        self.assertFalse(result)

    def test_item_with_special_characters(self):
        """Test saving and loading items with special characters."""
        item = Item(
            name='Item with "quotes" and, commas',
            description="Line 1\nLine 2",
            id="special-id",
        )
        self.storage.save_item(item)

        items = self.storage.load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, 'Item with "quotes" and, commas')

    def test_save_and_load_item_with_identifier(self):
        """Test saving and loading an item with an identifier."""
        item = Item(name="Test Item", identifier="A-1", description="Test", id="test-id")
        self.storage.save_item(item)

        items = self.storage.load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].identifier, "A-1")
        self.assertTrue(items[0].has_identifier())

    def test_save_and_load_item_without_identifier(self):
        """Test saving and loading an item without an identifier."""
        item = Item(name="Test Item", description="Test", id="test-id")
        self.storage.save_item(item)

        items = self.storage.load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].identifier, "")
        self.assertFalse(items[0].has_identifier())

    def test_update_item_identifier(self):
        """Test updating an item's identifier."""
        item = Item(name="Test", id="test-id")
        self.storage.save_item(item)

        updated = Item(name="Test", identifier="B-2", id="test-id")
        self.storage.update_item(updated)

        items = self.storage.load_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].identifier, "B-2")


class TestStorageVotes(unittest.TestCase):
    """Test cases for vote storage operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.storage = Storage(self.tmpdir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_load_votes_empty(self):
        """Test loading votes when no file exists."""
        votes = self.storage.load_votes()
        self.assertEqual(votes, [])

    def test_save_and_load_single_vote(self):
        """Test saving and loading a single vote."""
        ts = datetime(2024, 1, 15, 12, 30, 0)
        vote = Vote(
            winner_id="item1",
            loser_id="item2",
            weight=2.0,
            timestamp=ts,
            id="vote-id",
        )
        self.storage.save_vote(vote)

        votes = self.storage.load_votes()
        self.assertEqual(len(votes), 1)
        self.assertEqual(votes[0].id, "vote-id")
        self.assertEqual(votes[0].winner_id, "item1")
        self.assertEqual(votes[0].loser_id, "item2")
        self.assertEqual(votes[0].weight, 2.0)
        self.assertEqual(votes[0].timestamp, ts)

    def test_save_and_load_multiple_votes(self):
        """Test saving and loading multiple votes."""
        votes_to_save = [
            Vote(winner_id="a", loser_id="b", weight=1.0, id="v1"),
            Vote(winner_id="b", loser_id="c", weight=2.0, id="v2"),
            Vote(winner_id="c", loser_id="a", weight=3.0, id="v3"),
        ]
        self.storage.save_votes(votes_to_save)

        loaded = self.storage.load_votes()
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0].winner_id, "a")
        self.assertEqual(loaded[1].weight, 2.0)

    def test_save_votes_overwrites(self):
        """Test that save_votes overwrites existing content."""
        self.storage.save_vote(Vote(winner_id="a", loser_id="b", weight=1.0, id="old"))
        self.storage.save_votes([Vote(winner_id="c", loser_id="d", weight=2.0, id="new")])

        votes = self.storage.load_votes()
        self.assertEqual(len(votes), 1)
        self.assertEqual(votes[0].id, "new")

    def test_save_vote_appends(self):
        """Test that save_vote appends to existing content."""
        self.storage.save_vote(Vote(winner_id="a", loser_id="b", weight=1.0, id="v1"))
        self.storage.save_vote(Vote(winner_id="c", loser_id="d", weight=2.0, id="v2"))

        votes = self.storage.load_votes()
        self.assertEqual(len(votes), 2)

    def test_delete_vote(self):
        """Test deleting a vote."""
        self.storage.save_votes([
            Vote(winner_id="a", loser_id="b", weight=1.0, id="v1"),
            Vote(winner_id="c", loser_id="d", weight=2.0, id="v2"),
        ])

        result = self.storage.delete_vote("v1")
        self.assertTrue(result)

        votes = self.storage.load_votes()
        self.assertEqual(len(votes), 1)
        self.assertEqual(votes[0].id, "v2")

    def test_delete_vote_not_found(self):
        """Test deleting a non-existent vote returns False."""
        result = self.storage.delete_vote("nonexistent-id")
        self.assertFalse(result)


class TestStorageSettings(unittest.TestCase):
    """Test cases for settings storage operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.storage = Storage(self.tmpdir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_load_settings_default(self):
        """Test loading settings when no file exists returns defaults."""
        settings = self.storage.load_settings()
        default = Settings()

        self.assertEqual(settings.weight_uncertainty, default.weight_uncertainty)
        self.assertEqual(settings.top_tier_mode, default.top_tier_mode)

    def test_save_and_load_settings(self):
        """Test saving and loading settings."""
        settings = Settings(
            weight_uncertainty=2.5,
            top_tier_mode=True,
            decay_timescale_days=45.0,
        )
        self.storage.save_settings(settings)

        loaded = self.storage.load_settings()
        self.assertEqual(loaded.weight_uncertainty, 2.5)
        self.assertTrue(loaded.top_tier_mode)
        self.assertEqual(loaded.decay_timescale_days, 45.0)

    def test_save_settings_overwrites(self):
        """Test that save_settings overwrites existing file."""
        self.storage.save_settings(Settings(weight_uncertainty=1.0))
        self.storage.save_settings(Settings(weight_uncertainty=2.0))

        loaded = self.storage.load_settings()
        self.assertEqual(loaded.weight_uncertainty, 2.0)

    def test_load_settings_invalid_json(self):
        """Test loading settings with invalid JSON returns defaults."""
        # Write invalid JSON
        with open(self.storage.settings_file, "w") as f:
            f.write("not valid json {")

        settings = self.storage.load_settings()
        default = Settings()
        self.assertEqual(settings.weight_uncertainty, default.weight_uncertainty)


class TestStorageClearAll(unittest.TestCase):
    """Test cases for clearing all data."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.storage = Storage(self.tmpdir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_clear_all(self):
        """Test clearing all data files."""
        # Create some data
        self.storage.save_item(Item(name="Test"))
        self.storage.save_vote(Vote(winner_id="a", loser_id="b", weight=1.0))
        self.storage.save_settings(Settings(weight_uncertainty=2.0))

        # Verify files exist
        self.assertTrue(self.storage.items_file.exists())
        self.assertTrue(self.storage.votes_file.exists())
        self.assertTrue(self.storage.settings_file.exists())

        # Clear all
        self.storage.clear_all()

        # Verify files are gone
        self.assertFalse(self.storage.items_file.exists())
        self.assertFalse(self.storage.votes_file.exists())
        self.assertFalse(self.storage.settings_file.exists())

    def test_clear_all_no_files(self):
        """Test clearing when no files exist doesn't raise error."""
        self.storage.clear_all()  # Should not raise


if __name__ == "__main__":
    unittest.main()
