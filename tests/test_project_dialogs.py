"""Unit tests for the pure helpers behind the shared project file dialogs.

The helpers live in :mod:`src.data.project_storage` so they can be tested
without importing Qt; :mod:`src.ui.project_dialogs` re-exports them.
"""

import unittest
from pathlib import Path

from src.data.project_storage import (
    ProjectStorage,
    ensure_pairrank_suffix,
    safe_project_filename,
)


class TestSafeProjectFilename(unittest.TestCase):
    """Test cases for safe_project_filename."""

    def test_plain_name_unchanged(self):
        """Test that an already-safe name passes through untouched."""
        self.assertEqual(safe_project_filename("My Rankings"), "My Rankings")

    def test_keeps_allowed_punctuation(self):
        """Test that spaces, underscores and hyphens are preserved."""
        self.assertEqual(
            safe_project_filename("switch_test-2024 v1"),
            "switch_test-2024 v1",
        )

    def test_replaces_path_separators(self):
        """Test that path separators cannot escape the target directory."""
        self.assertEqual(safe_project_filename("a/b\\c"), "a_b_c")

    def test_replaces_other_punctuation(self):
        """Test that other punctuation becomes underscores."""
        self.assertEqual(safe_project_filename("Tasting: flight #3!"), "Tasting_ flight _3_")

    def test_empty_name(self):
        """Test that an empty name yields an empty stem."""
        self.assertEqual(safe_project_filename(""), "")

    def test_keeps_unicode_alphanumerics(self):
        """Test that non-ASCII letters and digits are kept."""
        self.assertEqual(safe_project_filename("Clé 5"), "Clé 5")


class TestEnsurePairrankSuffix(unittest.TestCase):
    """Test cases for ensure_pairrank_suffix."""

    def test_adds_missing_suffix(self):
        """Test that a path with no suffix gains .pairrank."""
        result = ensure_pairrank_suffix(Path("/tmp/project"))
        self.assertEqual(result, Path("/tmp/project.pairrank"))

    def test_keeps_existing_suffix(self):
        """Test that a correct path is returned unchanged."""
        path = Path("/tmp/project.pairrank")
        self.assertEqual(ensure_pairrank_suffix(path), path)

    def test_replaces_wrong_suffix(self):
        """Test that a different suffix is replaced."""
        result = ensure_pairrank_suffix(Path("/tmp/project.json"))
        self.assertEqual(result, Path("/tmp/project.pairrank"))

    def test_result_is_accepted_by_project_storage(self):
        """Test that the result always carries the extension ProjectStorage requires."""
        for raw in ["notes", "notes.txt", "notes.pairrank"]:
            with self.subTest(raw=raw):
                result = ensure_pairrank_suffix(Path(raw))
                self.assertEqual(result.suffix, ProjectStorage.FILE_EXTENSION)

    def test_preserves_parent_directory(self):
        """Test that only the filename changes."""
        result = ensure_pairrank_suffix(Path("/a/b/c/project.dat"))
        self.assertEqual(result.parent, Path("/a/b/c"))


if __name__ == "__main__":
    unittest.main()
