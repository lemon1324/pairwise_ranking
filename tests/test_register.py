"""Unit tests for the drawing register's data layer.

The tests build real files on disk rather than mocking the filesystem, because
the property that matters most here - that listing a directory never changes
anything in it - is a property of the filesystem after the call.
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.app.register import (
    DEFAULT_FILE_STEM,
    MAX_FILE_STEM_LENGTH,
    ProjectCondition,
    duplicate_without_votes,
    import_file,
    probe_project_file,
    scan_directory,
    unique_file_name,
)
from src.data.format_version import CURRENT_FORMAT_VERSION
from src.data.project_storage import ProjectStorage


# A format version this code has never heard of, for the "newer format" tag.
FUTURE_VERSION = CURRENT_FORMAT_VERSION + 1


def project_data(
    version=CURRENT_FORMAT_VERSION,
    name="Register Test",
    items=2,
    votes=1,
) -> dict:
    """
    Build a project dictionary in a given format version.

    Args:
        version: The format version to stamp, or None to leave the key out,
            which is how a version 1 file looks.
        name: The project name.
        items: How many items to build.
        votes: How many votes to build.

    Returns:
        dict: The project data, ready to be written as JSON.
    """
    data = {
        "name": name,
        "created": "2024-01-01T12:00:00",
        "modified": "2024-02-01T12:00:00",
        "items": [
            {
                "id": f"item-{n}",
                "name": f"Item {n}",
                "description": "",
                "identifier": str(n),
                "category": "General",
            }
            for n in range(1, items + 1)
        ],
        "votes": [
            {
                "id": f"vote-{n}",
                "winner_id": "item-1",
                "loser_id": "item-2",
                "weight": 2.0,
                "timestamp": "2024-01-10T10:00:00",
            }
            for n in range(1, votes + 1)
        ],
        "settings": {"weight_uncertainty": 1.5},
    }
    if version is not None:
        data["format_version"] = version
    return data


def write_project(path: Path, **kwargs) -> bytes:
    """
    Write a project file and return its exact bytes.

    Args:
        path: Where to write.
        **kwargs: Passed to :func:`project_data`.

    Returns:
        bytes: The bytes written.
    """
    path.write_text(json.dumps(project_data(**kwargs), indent=2), encoding="utf-8")
    return path.read_bytes()


class RegisterTestCase(unittest.TestCase):
    """Base fixture giving each test an empty data directory."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TestProbeProjectFile(RegisterTestCase):
    """Test cases for reading one file's register row."""

    def test_current_file_is_ok(self):
        """Test that a file in the current format carries no tag."""
        path = self.temp_dir / "current.pairrank"
        write_project(path)

        info = probe_project_file(path)

        self.assertEqual(info.condition, ProjectCondition.OK)
        self.assertEqual(info.reason, "")

    def test_old_files_are_tagged_old_format(self):
        """Test that every format below the current one is tagged as old."""
        for version in [None, 1, 2]:
            with self.subTest(version=version):
                path = self.temp_dir / f"old-{version}.pairrank"
                write_project(path, version=version)

                info = probe_project_file(path)

                self.assertEqual(info.condition, ProjectCondition.OLD_FORMAT)
                self.assertIn("upgrade", info.reason)

    def test_newer_file_is_tagged_newer_format(self):
        """Test that a file from a newer application is tagged, not rejected."""
        path = self.temp_dir / "future.pairrank"
        write_project(path, version=FUTURE_VERSION)

        info = probe_project_file(path)

        self.assertEqual(info.condition, ProjectCondition.NEWER_FORMAT)
        self.assertIn(str(FUTURE_VERSION), info.reason)

    def test_newer_file_still_reports_its_counts(self):
        """Test that a newer-format row still shows what the file holds."""
        path = self.temp_dir / "future.pairrank"
        write_project(path, version=FUTURE_VERSION, items=3, votes=2)

        info = probe_project_file(path)

        self.assertEqual(info.name, "Register Test")
        self.assertEqual(info.item_count, 3)
        self.assertEqual(info.vote_count, 2)

    def test_counts_come_from_the_file(self):
        """Test that the item and vote counts are read off the file."""
        path = self.temp_dir / "counts.pairrank"
        write_project(path, items=5, votes=4)

        info = probe_project_file(path)

        self.assertEqual(info.item_count, 5)
        self.assertEqual(info.vote_count, 4)

    def test_missing_items_key_counts_zero(self):
        """Test that an absent items key is read as an empty project."""
        path = self.temp_dir / "bare.pairrank"
        data = project_data()
        del data["items"]
        del data["votes"]
        path.write_text(json.dumps(data), encoding="utf-8")

        info = probe_project_file(path)

        self.assertEqual(info.condition, ProjectCondition.OK)
        self.assertEqual(info.item_count, 0)
        self.assertEqual(info.vote_count, 0)

    def test_name_and_file_name_are_both_reported(self):
        """Test that the row carries the project name and the file name."""
        path = self.temp_dir / "on-disk.pairrank"
        write_project(path, name="In The File")

        info = probe_project_file(path)

        self.assertEqual(info.name, "In The File")
        self.assertEqual(info.file_name, "on-disk.pairrank")
        self.assertEqual(info.path, path)

    def test_modified_is_the_file_time(self):
        """Test that the row reports when the file was last written."""
        path = self.temp_dir / "timed.pairrank"
        write_project(path)

        info = probe_project_file(path)

        self.assertIsInstance(info.modified, datetime)
        self.assertEqual(
            info.modified, datetime.fromtimestamp(path.stat().st_mtime)
        )

    def test_invalid_json_is_unreadable(self):
        """Test that a file that is not JSON reports a cause instead of raising."""
        path = self.temp_dir / "broken.pairrank"
        path.write_text("{not json at all", encoding="utf-8")

        info = probe_project_file(path)

        self.assertEqual(info.condition, ProjectCondition.UNREADABLE)
        self.assertIn("JSON", info.reason)

    def test_json_that_is_not_an_object_is_unreadable(self):
        """Test that a JSON list is not mistaken for a project."""
        path = self.temp_dir / "list.pairrank"
        path.write_text('["not", "a", "project"]', encoding="utf-8")

        info = probe_project_file(path)

        self.assertEqual(info.condition, ProjectCondition.UNREADABLE)
        self.assertIn("list", info.reason)

    def test_object_without_a_name_is_unreadable(self):
        """Test that a JSON object that is not a project is unreadable."""
        path = self.temp_dir / "other.pairrank"
        path.write_text('{"unrelated": true}', encoding="utf-8")

        info = probe_project_file(path)

        self.assertEqual(info.condition, ProjectCondition.UNREADABLE)
        self.assertIn("name", info.reason)

    def test_misshapen_entry_lists_are_unreadable(self):
        """Test that items and votes of the wrong shape are rejected."""
        cases = [("items", "not a list"), ("votes", [1, 2, 3])]
        for key, value in cases:
            with self.subTest(key=key):
                path = self.temp_dir / f"bad-{key}.pairrank"
                data = project_data()
                data[key] = value
                path.write_text(json.dumps(data), encoding="utf-8")

                info = probe_project_file(path)

                self.assertEqual(info.condition, ProjectCondition.UNREADABLE)
                self.assertIn(key, info.reason)

    def test_unusable_version_key_is_unreadable(self):
        """Test that a version key that is not a version is unreadable."""
        path = self.temp_dir / "weird.pairrank"
        data = project_data()
        data["format_version"] = "three"
        path.write_text(json.dumps(data), encoding="utf-8")

        info = probe_project_file(path)

        self.assertEqual(info.condition, ProjectCondition.UNREADABLE)

    def test_missing_file_is_unreadable(self):
        """Test that probing a file that is not there returns a row, not an error."""
        info = probe_project_file(self.temp_dir / "absent.pairrank")

        self.assertEqual(info.condition, ProjectCondition.UNREADABLE)
        self.assertIsNone(info.modified)

    def test_file_that_cannot_be_read_is_unreadable(self):
        """Test that a permission failure becomes a cause on the row."""
        path = self.temp_dir / "locked.pairrank"
        write_project(path)
        os.chmod(path, 0o000)
        try:
            try:
                path.read_bytes()
            except OSError:
                pass
            else:
                self.skipTest("file permissions are not enforced here")

            info = probe_project_file(path)

            self.assertEqual(info.condition, ProjectCondition.UNREADABLE)
        finally:
            os.chmod(path, 0o600)

    def test_openable_matches_the_condition(self):
        """Test that only current and old-format files report as openable."""
        cases = [
            ("ok.pairrank", CURRENT_FORMAT_VERSION, True),
            ("old.pairrank", 1, True),
            ("new.pairrank", FUTURE_VERSION, False),
        ]
        for file_name, version, expected in cases:
            with self.subTest(file_name=file_name):
                path = self.temp_dir / file_name
                write_project(path, version=version)

                self.assertEqual(probe_project_file(path).openable, expected)

    def test_unreadable_file_is_not_openable(self):
        """Test that a file with no project in it is never openable."""
        path = self.temp_dir / "broken.pairrank"
        path.write_text("nonsense", encoding="utf-8")

        self.assertFalse(probe_project_file(path).openable)

    def test_display_name_falls_back_to_the_file_name(self):
        """Test that a row with no project name shows the file name instead."""
        path = self.temp_dir / "nameless.pairrank"
        path.write_text("nonsense", encoding="utf-8")

        self.assertEqual(probe_project_file(path).display_name, "nameless.pairrank")


class TestScanDirectory(RegisterTestCase):
    """Test cases for listing a data directory."""

    def test_lists_every_project_file(self):
        """Test that each .pairrank file becomes one row."""
        for name in ["alpha", "beta", "gamma"]:
            write_project(self.temp_dir / f"{name}.pairrank", name=name)

        rows = scan_directory(self.temp_dir)

        self.assertEqual(len(rows), 3)

    def test_ignores_everything_that_is_not_a_project_file(self):
        """Test that backups and stray files are not listed."""
        write_project(self.temp_dir / "real.pairrank")
        (self.temp_dir / "real.pairrank.bak").write_text("{}", encoding="utf-8")
        (self.temp_dir / "real.pairrank.v1.bak").write_text("{}", encoding="utf-8")
        (self.temp_dir / "notes.txt").write_text("hello", encoding="utf-8")

        rows = scan_directory(self.temp_dir)

        self.assertEqual([row.file_name for row in rows], ["real.pairrank"])

    def test_ordering_is_deterministic(self):
        """Test that rows come back in a stable, case-insensitive name order."""
        for name in ["zeta", "Alpha", "middle"]:
            write_project(self.temp_dir / f"{name}.pairrank", name=name)

        rows = scan_directory(self.temp_dir)

        self.assertEqual(
            [row.file_name for row in rows],
            ["Alpha.pairrank", "middle.pairrank", "zeta.pairrank"],
        )

    def test_empty_directory_is_empty(self):
        """Test that a directory with no projects yields the empty state."""
        self.assertEqual(scan_directory(self.temp_dir), [])

    def test_missing_directory_is_empty(self):
        """Test that a directory that does not exist yields no rows, not an error."""
        self.assertEqual(scan_directory(self.temp_dir / "nowhere"), [])

    def test_file_in_place_of_a_directory_is_empty(self):
        """Test that being handed a file instead of a directory yields no rows."""
        path = self.temp_dir / "real.pairrank"
        write_project(path)

        self.assertEqual(scan_directory(path), [])

    def test_conditions_are_reported_per_row(self):
        """Test that a mixed directory tags each file on its own."""
        write_project(self.temp_dir / "a-current.pairrank")
        write_project(self.temp_dir / "b-old.pairrank", version=1)
        write_project(self.temp_dir / "c-future.pairrank", version=FUTURE_VERSION)
        (self.temp_dir / "d-broken.pairrank").write_text("{", encoding="utf-8")

        rows = scan_directory(self.temp_dir)

        self.assertEqual(
            [row.condition for row in rows],
            [
                ProjectCondition.OK,
                ProjectCondition.OLD_FORMAT,
                ProjectCondition.NEWER_FORMAT,
                ProjectCondition.UNREADABLE,
            ],
        )

    def test_scanning_leaves_an_old_file_byte_identical(self):
        """Test that listing a directory never migrates the files in it."""
        path = self.temp_dir / "legacy.pairrank"
        original = write_project(path, version=1)
        before = path.stat().st_mtime_ns

        scan_directory(self.temp_dir)

        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_scanning_creates_no_backup_files(self):
        """Test that listing a directory of old files scatters no backups."""
        write_project(self.temp_dir / "one.pairrank", version=1)
        write_project(self.temp_dir / "two.pairrank", version=2)

        scan_directory(self.temp_dir)

        self.assertEqual(
            sorted(path.name for path in self.temp_dir.iterdir()),
            ["one.pairrank", "two.pairrank"],
        )

    def test_scanning_twice_gives_the_same_rows(self):
        """Test that a scan has no effect on what the next scan sees."""
        write_project(self.temp_dir / "legacy.pairrank", version=1)

        first = scan_directory(self.temp_dir)
        second = scan_directory(self.temp_dir)

        self.assertEqual(first, second)


class TestUniqueFileName(RegisterTestCase):
    """Test cases for choosing a file name nothing holds yet."""

    def test_plain_name(self):
        """Test that a safe name becomes itself plus the extension."""
        self.assertEqual(
            unique_file_name(self.temp_dir, "My Rankings"),
            "My Rankings.pairrank",
        )

    def test_unsafe_characters_are_replaced(self):
        """Test that punctuation and separators cannot reach the file name."""
        name = unique_file_name(self.temp_dir, "a/b: flight #3")

        self.assertNotIn("/", name)
        self.assertNotIn(":", name)
        self.assertTrue(name.endswith(".pairrank"))

    def test_name_that_sanitizes_away_gets_a_default(self):
        """Test that a name with nothing usable in it still yields a file name."""
        for name in ["", " ", "     "]:
            with self.subTest(name=name):
                self.assertEqual(
                    unique_file_name(self.temp_dir, name),
                    f"{DEFAULT_FILE_STEM}.pairrank",
                )

    def test_name_of_only_punctuation_is_kept_as_underscores(self):
        """Test that punctuation sanitizes to a usable stem rather than nothing."""
        self.assertEqual(unique_file_name(self.temp_dir, "///"), "___.pairrank")

    def test_long_name_is_capped(self):
        """Test that a very long project name cannot build an unusable path."""
        name = unique_file_name(self.temp_dir, "x" * 500)

        self.assertEqual(len(Path(name).stem), MAX_FILE_STEM_LENGTH)

    def test_collision_gets_a_suffix(self):
        """Test that an existing file is never the answer."""
        write_project(self.temp_dir / "Taken.pairrank")

        self.assertEqual(
            unique_file_name(self.temp_dir, "Taken"), "Taken (2).pairrank"
        )

    def test_repeated_collisions_count_up(self):
        """Test that the suffix rises until it finds a free name."""
        write_project(self.temp_dir / "Taken.pairrank")
        write_project(self.temp_dir / "Taken (2).pairrank")
        write_project(self.temp_dir / "Taken (3).pairrank")

        self.assertEqual(
            unique_file_name(self.temp_dir, "Taken"), "Taken (4).pairrank"
        )

    def test_collisions_ignore_case(self):
        """Test that a name differing only in case still counts as taken."""
        write_project(self.temp_dir / "Taken.pairrank")

        self.assertEqual(
            unique_file_name(self.temp_dir, "taken"), "taken (2).pairrank"
        )

    def test_missing_directory_is_tolerated(self):
        """Test that naming a file for a directory yet to exist works."""
        self.assertEqual(
            unique_file_name(self.temp_dir / "nowhere", "Fresh"),
            "Fresh.pairrank",
        )


class TestImportFile(RegisterTestCase):
    """Test cases for taking an uploaded project into the directory."""

    def test_writes_the_bytes_verbatim(self):
        """Test that an import stores exactly what arrived."""
        raw = json.dumps(project_data()).encode("utf-8")

        info = import_file(self.temp_dir, "incoming.pairrank", raw)

        self.assertEqual(info.path.read_bytes(), raw)
        self.assertEqual(info.condition, ProjectCondition.OK)

    def test_old_format_import_is_not_migrated(self):
        """Test that importing an old file leaves it old until it is opened."""
        raw = json.dumps(project_data(version=1)).encode("utf-8")

        info = import_file(self.temp_dir, "legacy.pairrank", raw)

        self.assertEqual(info.condition, ProjectCondition.OLD_FORMAT)
        self.assertEqual(info.path.read_bytes(), raw)
        self.assertEqual(
            sorted(path.name for path in self.temp_dir.iterdir()),
            ["legacy.pairrank"],
        )

    def test_newer_format_import_is_accepted(self):
        """Test that a file from a newer application is taken in and tagged."""
        raw = json.dumps(project_data(version=FUTURE_VERSION)).encode("utf-8")

        info = import_file(self.temp_dir, "future.pairrank", raw)

        self.assertEqual(info.condition, ProjectCondition.NEWER_FORMAT)

    def test_existing_file_is_never_overwritten(self):
        """Test that importing over a taken name writes beside it instead."""
        original = write_project(self.temp_dir / "incoming.pairrank", name="Original")
        raw = json.dumps(project_data(name="Incoming")).encode("utf-8")

        info = import_file(self.temp_dir, "incoming.pairrank", raw)

        self.assertEqual(info.file_name, "incoming (2).pairrank")
        self.assertEqual(
            (self.temp_dir / "incoming.pairrank").read_bytes(), original
        )

    def test_directory_is_created(self):
        """Test that importing into a directory that is not there yet works."""
        target = self.temp_dir / "fresh"
        raw = json.dumps(project_data()).encode("utf-8")

        info = import_file(target, "incoming.pairrank", raw)

        self.assertTrue(info.path.exists())

    def test_names_that_escape_the_directory_are_refused(self):
        """Test that a file name cannot address anything but this directory."""
        raw = json.dumps(project_data()).encode("utf-8")
        cases = [
            "../escape.pairrank",
            "..\\escape.pairrank",
            "/etc/escape.pairrank",
            "sub/dir.pairrank",
            "C:escape.pairrank",
            "..",
            "",
            "   ",
        ]
        for file_name in cases:
            with self.subTest(file_name=file_name):
                with self.assertRaises(ValueError):
                    import_file(self.temp_dir, file_name, raw)

    def test_wrong_extension_is_refused(self):
        """Test that only .pairrank files can be imported."""
        raw = json.dumps(project_data()).encode("utf-8")

        with self.assertRaises(ValueError):
            import_file(self.temp_dir, "project.json", raw)

    def test_unreadable_content_is_refused(self):
        """Test that bytes that are not a project are not written at all."""
        for raw in [b"{not json", b'["a", "list"]', b'{"unrelated": true}']:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    import_file(self.temp_dir, "incoming.pairrank", raw)

        self.assertEqual(list(self.temp_dir.iterdir()), [])


class TestDuplicateWithoutVotes(RegisterTestCase):
    """Test cases for copying a project in the register."""

    def test_copy_keeps_items_and_drops_votes(self):
        """Test that the copy carries the items with no history."""
        write_project(self.temp_dir / "source.pairrank", items=3, votes=2)

        info = duplicate_without_votes(self.temp_dir, "source.pairrank", "Copy")

        self.assertEqual(info.item_count, 3)
        self.assertEqual(info.vote_count, 0)
        self.assertEqual(info.name, "Copy")

    def test_copy_is_written_in_the_current_format(self):
        """Test that the copy needs no upgrade of its own."""
        write_project(self.temp_dir / "source.pairrank", version=1)

        info = duplicate_without_votes(self.temp_dir, "source.pairrank", "Copy")

        self.assertEqual(info.condition, ProjectCondition.OK)

    def test_source_is_left_with_its_votes(self):
        """Test that copying does not disturb the project copied from."""
        source = self.temp_dir / "source.pairrank"
        write_project(source, items=3, votes=2)

        duplicate_without_votes(self.temp_dir, "source.pairrank", "Copy")

        self.assertEqual(probe_project_file(source).vote_count, 2)

    def test_copy_gets_a_free_file_name(self):
        """Test that a copy named after an existing file writes beside it."""
        write_project(self.temp_dir / "source.pairrank")
        write_project(self.temp_dir / "Copy.pairrank")

        info = duplicate_without_votes(self.temp_dir, "source.pairrank", "Copy")

        self.assertEqual(info.file_name, "Copy (2).pairrank")

    def test_missing_source_raises(self):
        """Test that copying a file that is not there is an error."""
        with self.assertRaises(FileNotFoundError):
            duplicate_without_votes(self.temp_dir, "absent.pairrank", "Copy")

    def test_escaping_source_name_is_refused(self):
        """Test that the source is addressed by file name alone."""
        with self.assertRaises(ValueError):
            duplicate_without_votes(self.temp_dir, "../source.pairrank", "Copy")

    def test_empty_new_name_is_refused(self):
        """Test that a copy needs a name of its own."""
        write_project(self.temp_dir / "source.pairrank")

        with self.assertRaises(ValueError):
            duplicate_without_votes(self.temp_dir, "source.pairrank", "   ")

    def test_unreadable_source_is_refused(self):
        """Test that a file the register cannot read cannot be copied."""
        (self.temp_dir / "broken.pairrank").write_text("{", encoding="utf-8")

        with self.assertRaises(ValueError):
            duplicate_without_votes(self.temp_dir, "broken.pairrank", "Copy")

    def test_copy_uses_the_storage_extension(self):
        """Test that the copy is a project file like any other."""
        write_project(self.temp_dir / "source.pairrank")

        info = duplicate_without_votes(self.temp_dir, "source.pairrank", "Copy")

        self.assertEqual(info.path.suffix, ProjectStorage.FILE_EXTENSION)


if __name__ == "__main__":
    unittest.main()
