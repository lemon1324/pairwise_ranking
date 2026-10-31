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

    def test_plain_name_becomes_slug(self):
        """Test that a plain name is lowercased with spaces as hyphens."""
        self.assertEqual(safe_project_filename("My Rankings"), "my-rankings")

    def test_separators_collapse_to_one_hyphen(self):
        """Test that runs of spaces, underscores and hyphens become one hyphen."""
        self.assertEqual(
            safe_project_filename("switch_test - 2024  v1"),
            "switch-test-2024-v1",
        )

    def test_replaces_path_separators(self):
        """Test that path separators cannot escape the target directory."""
        self.assertEqual(safe_project_filename("a/b\\c"), "a-b-c")

    def test_trims_leading_and_trailing_punctuation(self):
        """Test that punctuation at either end leaves no hyphen behind."""
        self.assertEqual(
            safe_project_filename("  Tasting: Flight #3 (Clé)! "),
            "tasting-flight-3-cle",
        )

    def test_empty_name(self):
        """Test that an empty name yields an empty stem."""
        self.assertEqual(safe_project_filename(""), "")

    def test_folds_accents_to_ascii(self):
        """Test that accented letters fold to their base letter."""
        self.assertEqual(safe_project_filename("Clé 5"), "cle-5")

    def test_drops_unfoldable_characters(self):
        """Test that characters with no ASCII form are dropped."""
        self.assertEqual(safe_project_filename("日本 tea"), "tea")
        self.assertEqual(safe_project_filename("日本"), "")

    def test_slug_is_idempotent(self):
        """Test that slugging a slug changes nothing."""
        slug = safe_project_filename("Tasting: Flight #3")
        self.assertEqual(safe_project_filename(slug), slug)


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
