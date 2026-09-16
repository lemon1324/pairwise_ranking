"""Unit tests for the ProjectStorage class."""

import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import src.data.project_storage as project_storage_module
from src.data.format_version import CURRENT_FORMAT_VERSION, FORMAT_VERSION_KEY
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
        shutil.rmtree(self.temp_dir, ignore_errors=True)

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

    def test_save_leaves_no_tmp_file(self):
        """Test that a successful save leaves no temporary file behind."""
        project = Project(name="Atomic Test")
        ProjectStorage.save(project, self.test_file)

        self.assertTrue(self.test_file.exists())
        tmp_path = self.test_file.with_name(self.test_file.name + ".tmp")
        self.assertFalse(tmp_path.exists())
        self.assertEqual(
            sorted(p.name for p in Path(self.temp_dir).iterdir()),
            ["test.pairrank"],
        )

    def test_second_save_creates_backup_of_previous_content(self):
        """Test that saving over an existing file backs up the previous content."""
        project = Project(name="Backup Test")
        ProjectStorage.save(project, self.test_file)
        first_content = self.test_file.read_bytes()

        backup_path = self.test_file.with_suffix(".pairrank.bak")
        self.assertFalse(backup_path.exists())

        project.name = "Backup Test Modified"
        project.items.append(Item(name="New Item", id="new-item"))
        ProjectStorage.save(project, self.test_file)

        self.assertTrue(backup_path.exists())
        self.assertEqual(backup_path.read_bytes(), first_content)
        self.assertNotEqual(self.test_file.read_bytes(), first_content)
        self.assertEqual(ProjectStorage.load(self.test_file).name, "Backup Test Modified")

    def test_failed_save_leaves_original_untouched(self):
        """Test that a failure during serialization leaves the original file intact."""
        project = Project(name="Failure Test")
        ProjectStorage.save(project, self.test_file)
        original_content = self.test_file.read_bytes()

        project.name = "Should Not Be Written"

        def boom(*args, **kwargs):
            raise RuntimeError("simulated serialization failure")

        with patch.object(project_storage_module.json, "dump", side_effect=boom):
            with self.assertRaises(RuntimeError):
                ProjectStorage.save(project, self.test_file)

        self.assertEqual(self.test_file.read_bytes(), original_content)
        tmp_path = self.test_file.with_name(self.test_file.name + ".tmp")
        self.assertFalse(tmp_path.exists())
        self.assertFalse(self.test_file.with_suffix(".pairrank.bak").exists())

    def test_load_empty_object_raises_value_error(self):
        """Test that loading a JSON file with no project data raises ValueError."""
        self.test_file.write_text("{}", encoding="utf-8")

        with self.assertRaises(ValueError):
            ProjectStorage.load(self.test_file)

    def test_load_non_json_raises_value_error(self):
        """Test that loading a file that is not JSON raises ValueError."""
        self.test_file.write_text("this is not json", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            ProjectStorage.load(self.test_file)

        self.assertIn("Invalid project file", str(ctx.exception))

    def test_load_missing_vote_field_raises_value_error(self):
        """Test that a vote entry missing required keys raises ValueError, not KeyError."""
        data = {"name": "Bad Votes", "items": [], "votes": [{"winner_id": "a"}]}
        self.test_file.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            ProjectStorage.load(self.test_file)

        self.assertIn("Invalid project file", str(ctx.exception))


class TestProjectStorageCreateCopy(unittest.TestCase):
    """Test cases for ProjectStorage.create_copy."""

    def setUp(self):
        """Set up a saved source project to copy."""
        self.temp_dir = tempfile.mkdtemp()
        self.source_file = Path(self.temp_dir) / "source.pairrank"
        self.copy_file = Path(self.temp_dir) / "copy.pairrank"

        items = [Item(name="Item 1", id="item-1"), Item(name="Item 2", id="item-2")]
        votes = [Vote(winner_id="item-1", loser_id="item-2", weight=2.0, id="vote-1")]
        self.source = Project(
            name="Source Project",
            items=items,
            votes=votes,
            settings=Settings(weight_uncertainty=1.5, decay_timescale_days=60.0),
            slots=["A", "B"],
        )
        ProjectStorage.save(self.source, self.source_file)

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_copy_writes_the_new_file(self):
        """Test that the copy is written to the requested path."""
        ProjectStorage.create_copy(self.source, "Copy Project", self.copy_file)
        self.assertTrue(self.copy_file.exists())

    def test_create_copy_sets_file_path(self):
        """Test that the returned project points at the new file."""
        copied = ProjectStorage.create_copy(
            self.source, "Copy Project", self.copy_file
        )
        self.assertEqual(copied.file_path, self.copy_file)

    def test_created_copy_round_trips(self):
        """Test that loading the copy yields the source's setup and no votes."""
        ProjectStorage.create_copy(self.source, "Copy Project", self.copy_file)

        loaded = ProjectStorage.load(self.copy_file)

        self.assertEqual(loaded.name, "Copy Project")
        self.assertEqual(loaded.votes, [])
        self.assertEqual([item.id for item in loaded.items], ["item-1", "item-2"])
        self.assertEqual(loaded.settings.weight_uncertainty, 1.5)
        self.assertEqual(loaded.settings.decay_timescale_days, 60.0)
        self.assertEqual(loaded.slots, ["A", "B"])

    def test_source_file_is_unchanged(self):
        """Test that the source project's file keeps its votes."""
        ProjectStorage.create_copy(self.source, "Copy Project", self.copy_file)

        reloaded = ProjectStorage.load(self.source_file)

        self.assertEqual(reloaded.name, "Source Project")
        self.assertEqual(len(reloaded.votes), 1)
        self.assertEqual(reloaded.votes[0].id, "vote-1")


class TestProjectStorageMalformedFiles(unittest.TestCase):
    """Test cases for rejecting files whose nested shapes are wrong."""

    #: (description, project dictionary, key expected in the error message)
    BAD_SHAPES = [
        ("items_not_objects", {"name": "x", "items": [1]}, "items"),
        ("settings_not_object", {"name": "x", "settings": "x"}, "settings"),
        ("votes_not_objects", {"name": "x", "votes": [1]}, "votes"),
        ("slots_not_a_list", {"name": "x", "slots": "abc"}, "slots"),
    ]

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / "test.pairrank"

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_from_dict_rejects_bad_shapes(self):
        """Test that Project.from_dict raises ValueError naming the bad key."""
        for label, data, key in self.BAD_SHAPES:
            with self.subTest(label):
                with self.assertRaises(ValueError) as ctx:
                    Project.from_dict(data)
                self.assertIn(key, str(ctx.exception))

    def test_load_rejects_bad_shapes(self):
        """Test that loading a file with a bad shape raises ValueError."""
        for label, data, key in self.BAD_SHAPES:
            with self.subTest(label):
                self.test_file.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError) as ctx:
                    ProjectStorage.load(self.test_file)
                self.assertIn(key, str(ctx.exception))

    def test_load_wraps_unexpected_errors(self):
        """Test that a non-ValueError failure becomes an Invalid project file."""
        self.test_file.write_text(json.dumps({"name": "x"}), encoding="utf-8")

        def boom(*args, **kwargs):
            raise RuntimeError("simulated upgrade failure")

        with patch.object(project_storage_module, "upgrade", side_effect=boom):
            with self.assertRaises(ValueError) as ctx:
                ProjectStorage.load(self.test_file)

        self.assertIn("Invalid project file", str(ctx.exception))


class TestProjectStorageMigration(unittest.TestCase):
    """Test cases for the load-time format migration."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / "test.pairrank"
        self.v1_backup = Path(self.temp_dir) / "test.pairrank.v1.bak"

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_v1_file(self) -> bytes:
        """Write a version 1 project file and return its exact bytes."""
        data = {
            "name": "Legacy Project",
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
            "settings": {"weight_uncertainty": 1.5},
        }
        self.test_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return self.test_file.read_bytes()

    def test_load_v1_creates_backup_with_original_bytes(self):
        """Test that loading a v1 file backs the original bytes up once."""
        original = self._write_v1_file()

        ProjectStorage.load(self.test_file)

        self.assertTrue(self.v1_backup.exists())
        self.assertEqual(self.v1_backup.read_bytes(), original)

    def test_load_v1_rewrites_file_as_current_version(self):
        """Test that loading a v1 file saves it back in the current format."""
        self._write_v1_file()

        ProjectStorage.load(self.test_file)

        with open(self.test_file, encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data[FORMAT_VERSION_KEY], CURRENT_FORMAT_VERSION)
        self.assertEqual(data["slots"], [])
        for item in data["items"]:
            self.assertEqual(item["status"], "active")
            self.assertIsNone(item["retired_at"])
            self.assertIsNone(item["replaced_by"])

    def test_load_v1_yields_all_active_project(self):
        """Test that real-shaped v1 data loads as an all-active project."""
        self._write_v1_file()

        project = ProjectStorage.load(self.test_file)

        self.assertEqual(len(project.items), 2)
        self.assertEqual(len(project.active_items()), 2)
        self.assertTrue(all(item.is_active() for item in project.items))
        self.assertEqual(project.slots, [])
        self.assertEqual(len(project.votes), 1)

    def test_second_load_creates_no_second_backup(self):
        """Test that reloading a migrated file does not back it up again."""
        self._write_v1_file()
        ProjectStorage.load(self.test_file)
        backup_bytes = self.v1_backup.read_bytes()
        migrated_bytes = self.test_file.read_bytes()

        ProjectStorage.load(self.test_file)

        self.assertEqual(self.v1_backup.read_bytes(), backup_bytes)
        self.assertEqual(self.test_file.read_bytes(), migrated_bytes)

    def test_load_current_version_writes_nothing(self):
        """Test that loading an up-to-date file touches no files at all."""
        project = Project(name="Current", items=[Item(name="A", id="a")])
        ProjectStorage.save(project, self.test_file)
        before = self.test_file.read_bytes()

        loaded = ProjectStorage.load(self.test_file)

        self.assertEqual(loaded.name, "Current")
        self.assertEqual(self.test_file.read_bytes(), before)
        self.assertEqual(
            sorted(p.name for p in Path(self.temp_dir).iterdir()),
            ["test.pairrank"],
        )

    def test_load_newer_version_raises_value_error(self):
        """Test that a file from a newer application version is rejected."""
        data = {"name": "Future", FORMAT_VERSION_KEY: CURRENT_FORMAT_VERSION + 1}
        self.test_file.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            ProjectStorage.load(self.test_file)

        self.assertIn("newer", str(ctx.exception))
        self.assertFalse(self.v1_backup.exists())

    def test_migration_preserves_retired_items_on_resave(self):
        """Test that lifecycle data survives a save/load round trip."""
        item = Item(name="Old", identifier="1", id="old-id")
        item.retire(replaced_by="new-id")
        project = Project(
            name="Lifecycle",
            items=[item, Item(name="New", identifier="1", id="new-id")],
            slots=["1", "2"],
        )
        ProjectStorage.save(project, self.test_file)

        loaded = ProjectStorage.load(self.test_file)

        self.assertEqual(loaded.slots, ["1", "2"])
        retired = [i for i in loaded.items if not i.is_active()]
        self.assertEqual([i.id for i in retired], ["old-id"])
        self.assertEqual(retired[0].replaced_by, "new-id")
        self.assertEqual(loaded.active_identifiers(), {"1"})

    def test_migration_preserves_modified_timestamp(self):
        """Test that migrating a v1 file does not look like a user edit."""
        self._write_v1_file()

        project = ProjectStorage.load(self.test_file)

        expected = datetime(2024, 2, 1, 12, 0, 0)
        self.assertEqual(project.modified, expected)
        with open(self.test_file, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["modified"], expected.isoformat())

    def test_migration_writes_no_regular_backup(self):
        """Test that migrating writes only the .v1.bak, not a .pairrank.bak."""
        self._write_v1_file()

        ProjectStorage.load(self.test_file)

        self.assertEqual(
            sorted(p.name for p in Path(self.temp_dir).iterdir()),
            ["test.pairrank", "test.pairrank.v1.bak"],
        )

    def test_migration_survives_a_read_only_file(self):
        """Test that a failed re-save still yields the upgraded project."""
        self._write_v1_file()

        def deny(*args, **kwargs):
            raise PermissionError("simulated read-only project file")

        with patch.object(ProjectStorage, "save", side_effect=deny):
            project = ProjectStorage.load(self.test_file)

        self.assertEqual(project.name, "Legacy Project")
        self.assertEqual(project.to_dict()[FORMAT_VERSION_KEY], CURRENT_FORMAT_VERSION)
        self.assertEqual(len(project.active_items()), 2)

    def test_migration_survives_an_unwritable_backup(self):
        """Test that a failed backup still yields the upgraded project."""
        self._write_v1_file()

        def deny(*args, **kwargs):
            raise PermissionError("simulated read-only directory")

        with patch.object(Path, "write_bytes", side_effect=deny):
            project = ProjectStorage.load(self.test_file)

        self.assertEqual(project.to_dict()[FORMAT_VERSION_KEY], CURRENT_FORMAT_VERSION)
        self.assertFalse(self.v1_backup.exists())


if __name__ == "__main__":
    unittest.main()
