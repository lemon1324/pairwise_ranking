"""Unit tests for the web frontend's open-project cache.

Like the register's tests, these build real files on disk: the two properties
that matter here - that a file changed underneath the server is noticed, and
that the server's own writes are not mistaken for such a change - are
properties of the filesystem after the call, and a mocked stat would only
confirm that the mock was written to agree.
"""

import json
import logging
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from src.data.errors import NewerFormatError
from src.data.format_version import CURRENT_FORMAT_VERSION, FORMAT_VERSION_KEY
from src.data.project_storage import ProjectStorage
from src.web.registry import (
    ProjectNotFoundError,
    ProjectRegistry,
    ProjectUnreadableError,
)


# Names a browser must never be able to turn into a path of its own choosing.
REFUSED_IDS = [
    "",
    "   ",
    ".",
    "..",
    "../secrets.pairrank",
    "..\\secrets.pairrank",
    "sub/other.pairrank",
    "sub\\other.pairrank",
    "/etc/passwd.pairrank",
    "C:\\Windows\\other.pairrank",
    "notes.txt",
    ".pairrank",
]


class RegistryTestCase(unittest.TestCase):
    """Base case giving each test a data directory with one project in it."""

    def setUp(self):
        """Create a data directory holding a single saved project."""
        # The registry warns about every id it refuses, and these tests refuse
        # a dozen of them on purpose; without this each run prints the lot.
        # assertLogs still sees them, so nothing is being hidden from a test
        # that cares.
        self.registry_logger = logging.getLogger("src.web.registry")
        self.addCleanup(
            setattr, self.registry_logger, "propagate", self.registry_logger.propagate
        )
        sink = logging.NullHandler()
        self.addCleanup(self.registry_logger.removeHandler, sink)
        self.registry_logger.addHandler(sink)
        self.registry_logger.propagate = False

        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
        self.registry = ProjectRegistry(self.data_dir)

        self.project_id = "Tasting.pairrank"
        self.path = self.data_dir / self.project_id
        ProjectStorage.create_new("Tasting", self.path)

    def tearDown(self):
        """Remove the data directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def write_raw(self, data, file_name=None) -> Path:
        """
        Write arbitrary JSON into the data directory.

        Args:
            data: The value to serialize, or a str to write verbatim.
            file_name: The file to write, defaulting to the shared project.

        Returns:
            Path: The file written.
        """
        path = self.data_dir / (file_name or self.project_id)
        text = data if isinstance(data, str) else json.dumps(data)
        path.write_text(text, encoding="utf-8")
        return path

    def lock_in_use(self, path: Path) -> threading.RLock:
        """
        Fetch the lock object the registry is currently using for a path.

        Reaching into the registry rather than asking it: the lock is only ever
        handed out for the length of a ``with`` block now, so a test that needs
        the object itself - to contend for it from another thread, or to say
        that it is still the same one - has nowhere else to get it.

        Args:
            path: A resolved project path.

        Returns:
            threading.RLock: The lock, which must exist.
        """
        self.assertIn(path, self.registry._locks)
        return self.registry._locks[path]

    def rewrite_with_name(self, name: str) -> None:
        """
        Replace the shared project file with one carrying a different name.

        Stands in for the desktop app saving over the file while the server has
        it open, which is the case the mtime check exists for.

        Args:
            name: The project name to write.
        """
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["name"] = name
        self.write_raw(data)


class TestProjectIdValidation(RegistryTestCase):
    """Test cases for the boundary between a project id and a path."""

    def test_resolve_returns_the_path_in_the_data_directory(self):
        """Test that a plain file name resolves inside the data directory."""
        self.assertEqual(self.registry.resolve(self.project_id), self.path.resolve())

    def test_resolve_refuses_traversal_and_separators(self):
        """Test that no id can address a file outside the data directory."""
        for project_id in REFUSED_IDS:
            with self.subTest(project_id=project_id):
                with self.assertRaises(ProjectNotFoundError):
                    self.registry.resolve(project_id)

    def test_open_refuses_traversal_and_separators(self):
        """Test that the refusal is not something only resolve knows about."""
        for project_id in REFUSED_IDS:
            with self.subTest(project_id=project_id):
                with self.assertRaises(ProjectNotFoundError):
                    self.registry.open(project_id)

    def test_a_refused_id_is_logged(self):
        """Test that an attempt to name a file elsewhere leaves a trace."""
        with self.assertLogs("src.web.registry", "WARNING") as logged:
            with self.assertRaises(ProjectNotFoundError):
                self.registry.resolve("../secrets.pairrank")

        self.assertIn("../secrets.pairrank", logged.output[0])

    def test_a_missing_file_is_also_not_found(self):
        """Test that a well-formed name with no file behind it is a 404."""
        with self.assertRaises(ProjectNotFoundError):
            self.registry.open("Nothing.pairrank")


class TestRegistryCache(RegistryTestCase):
    """Test cases for holding one project open across requests."""

    def test_the_same_id_yields_the_same_entry(self):
        """Test that two requests share one open project rather than two."""
        first = self.registry.open(self.project_id)
        second = self.registry.open(self.project_id)

        self.assertIs(first, second)
        self.assertIs(first.session.project, second.session.project)

    def test_session_reaches_the_cached_project(self):
        """Test that the read path hands out the cached session."""
        entry = self.registry.open(self.project_id)

        self.assertIs(self.registry.session(self.project_id), entry.session)

    def test_forget_drops_the_entry(self):
        """Test that forgetting a project makes the next open re-read it."""
        first = self.registry.open(self.project_id)
        self.registry.forget(self.project_id)

        self.assertIsNot(self.registry.open(self.project_id), first)

    def test_an_open_project_keeps_its_lock(self):
        """Test that the lock lives as long as the project it guards."""
        entry = self.registry.open(self.project_id)
        lock = self.lock_in_use(entry.path)

        self.assertIs(self.lock_in_use(entry.path), lock)
        with self.registry.locked(entry.path):
            self.assertIs(self.lock_in_use(entry.path), lock)

    def test_different_projects_get_different_locks(self):
        """Test that a request about one project does not block another."""
        other = self.data_dir / "Other.pairrank"
        ProjectStorage.create_new("Other", other)

        self.registry.open(self.project_id)
        self.registry.open("Other.pairrank")

        self.assertIsNot(
            self.lock_in_use(self.registry.resolve(self.project_id)),
            self.lock_in_use(self.registry.resolve("Other.pairrank")),
        )


class TestRegistryLocks(RegistryTestCase):
    """Test cases for how long a project's lock lives."""

    def test_a_failed_open_leaves_no_lock_behind(self):
        """
        Test that names for files that are not there cannot hoard locks.

        Any client on the LAN can ask for a project that does not exist, as
        fast as it likes. The lock was minted before the load was attempted, so
        each of those asks used to leave one behind for a path that will never
        have an entry - a dictionary that grows for as long as the server runs.
        """
        for index in range(50):
            with self.assertRaises(ProjectNotFoundError):
                self.registry.open(f"Absent{index}.pairrank")

        self.assertEqual(self.registry._locks, {})
        self.assertEqual(self.registry._lock_users, {})

    def test_a_damaged_project_leaves_no_lock_behind(self):
        """Test that the other failing load path prunes as well."""
        self.write_raw("{ this is not json", "Broken.pairrank")

        with self.assertRaises(ProjectUnreadableError):
            self.registry.open("Broken.pairrank")

        self.assertEqual(self.registry._locks, {})

    def test_a_lock_in_use_is_not_taken_from_its_holder(self):
        """
        Test that pruning cannot split one path across two locks.

        The guarantee is that one path has one lock; dropping a lock that
        another caller is inside would hand the next caller a different object
        and let the two of them run over the same file at once.
        """
        path = self.registry.resolve("Absent.pairrank")

        with self.registry.locked(path):
            held = self.lock_in_use(path)
            with self.assertRaises(ProjectNotFoundError):
                self.registry.open("Absent.pairrank")

            self.assertIs(self.lock_in_use(path), held)

        self.assertNotIn(path, self.registry._locks)

    def test_a_failed_open_does_not_disturb_an_open_project(self):
        """Test that pruning one path leaves the projects that are open."""
        entry = self.registry.open(self.project_id)
        lock = self.lock_in_use(entry.path)

        with self.assertRaises(ProjectNotFoundError):
            self.registry.open("Absent.pairrank")

        self.assertIs(self.lock_in_use(entry.path), lock)
        self.assertIs(self.registry.open(self.project_id), entry)

    def test_a_forgotten_project_does_not_strand_its_lock(self):
        """Test that deleting a project does not leave its lock for ever."""
        self.registry.open(self.project_id)
        self.registry.forget(self.project_id)

        self.assertEqual(self.registry._locks, {})


class TestRegistryLoadFailures(RegistryTestCase):
    """Test cases for the failures the error pages are built around."""

    def test_a_newer_format_file_raises_the_typed_error(self):
        """Test that a future format version is not reported as damage."""
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data[FORMAT_VERSION_KEY] = CURRENT_FORMAT_VERSION + 1
        self.write_raw(data)

        with self.assertRaises(NewerFormatError) as caught:
            self.registry.open(self.project_id)

        self.assertEqual(caught.exception.file_version, CURRENT_FORMAT_VERSION + 1)
        self.assertEqual(caught.exception.supported_version, CURRENT_FORMAT_VERSION)

    def test_a_corrupt_file_raises_unreadable(self):
        """Test that JSON that will not parse is reported as damage."""
        self.write_raw("{ this is not json")

        with self.assertRaises(ProjectUnreadableError):
            self.registry.open(self.project_id)

    def test_a_deeply_faulty_file_raises_unreadable(self):
        """Test that a project-shaped file with a bad item is damage too."""
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["items"] = [{"no_id_here": True}]
        self.write_raw(data)

        with self.assertRaises(ProjectUnreadableError):
            self.registry.open(self.project_id)


class TestRegistryMutation(RegistryTestCase):
    """Test cases for the lock-check-mutate-save sequence."""

    def test_mutate_holds_the_lock(self):
        """Test that another thread cannot mutate the same project meanwhile."""
        entry = self.registry.open(self.project_id)
        lock = self.lock_in_use(entry.path)
        # From another thread, because the lock is reentrant and this one
        # would be let straight back in.
        acquired = []

        def try_acquire():
            got = lock.acquire(blocking=False)
            acquired.append(got)
            if got:
                lock.release()

        with self.registry.mutate(self.project_id):
            contender = threading.Thread(target=try_acquire)
            contender.start()
            contender.join()

        self.assertEqual(acquired, [False])

    def test_the_lock_is_released_after_a_failed_mutation(self):
        """Test that a route raising mid-edit does not wedge the project."""
        entry = self.registry.open(self.project_id)
        lock = self.lock_in_use(entry.path)

        with self.assertRaises(RuntimeError):
            with self.registry.mutate(self.project_id):
                raise RuntimeError("the route gave up")

        self.assertTrue(lock.acquire(blocking=False))
        lock.release()

    def test_an_untouched_file_reports_no_reload(self):
        """Test that the notice does not appear when nothing has changed."""
        self.registry.open(self.project_id)

        with self.registry.mutate(self.project_id) as mutation:
            self.assertFalse(mutation.reloaded)

    def test_a_file_changed_on_disk_is_reloaded(self):
        """Test that an edit from outside the process replaces the session."""
        first = self.registry.open(self.project_id)
        self.assertEqual(first.session.project.name, "Tasting")

        self.rewrite_with_name("Tasting, revised elsewhere")

        with self.registry.mutate(self.project_id) as mutation:
            self.assertTrue(mutation.reloaded)
            self.assertEqual(
                mutation.session.project.name, "Tasting, revised elsewhere"
            )

        # The entry survives the reload, so anything holding it sees the new
        # session rather than a project nobody else is reading.
        self.assertIs(self.registry.open(self.project_id), first)
        self.assertIs(first.session, mutation.session)

    def test_the_reload_notice_is_taken_once(self):
        """Test that the notice is cleared by whoever renders it."""
        entry = self.registry.open(self.project_id)
        self.rewrite_with_name("Changed")

        with self.registry.mutate(self.project_id):
            pass

        self.assertTrue(entry.take_reload_notice())
        self.assertFalse(entry.take_reload_notice())

    def test_the_registrys_own_save_is_not_a_change_on_disk(self):
        """Test that saving does not make the next mutation reload."""
        with self.registry.mutate(self.project_id) as mutation:
            mutation.session.rename("Tasting, renamed")

        with self.registry.mutate(self.project_id) as mutation:
            self.assertFalse(mutation.reloaded)
            self.assertEqual(mutation.session.project.name, "Tasting, renamed")

    def test_an_opening_migration_is_not_a_change_on_disk(self):
        """Test that upgrading a file on open does not look like an edit."""
        legacy = {
            "name": "Legacy",
            "created": "2024-01-01T12:00:00",
            "modified": "2024-01-01T12:00:00",
            "items": [],
            "votes": [],
            "settings": {},
        }
        self.write_raw(legacy, "Legacy.pairrank")

        self.registry.open("Legacy.pairrank")

        with self.registry.mutate("Legacy.pairrank") as mutation:
            self.assertFalse(mutation.reloaded)

    def test_a_mutation_is_written_to_the_file(self):
        """Test that the session's save reaches disk inside the lock."""
        with self.registry.mutate(self.project_id) as mutation:
            mutation.session.rename("Tasting, saved")

        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "Tasting, saved")

    def test_mutate_refuses_a_traversal_id(self):
        """Test that the mutation path shares the one traversal boundary."""
        with self.assertRaises(ProjectNotFoundError):
            with self.registry.mutate("../escape.pairrank"):
                pass


if __name__ == "__main__":
    unittest.main()
