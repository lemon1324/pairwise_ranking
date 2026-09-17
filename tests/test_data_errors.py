"""Unit tests for the typed project format errors.

The hierarchy exists so that the drawing register can tell a file from a newer
application apart from a file it simply cannot read, without matching on the
words in an error message. The tests below pin both halves of that: the types
are distinguishable, and they are still ValueErrors, which is what keeps every
``except (OSError, ValueError)`` handler in the desktop UI working.
"""

import unittest
from unittest.mock import patch

import src.data.format_version as format_version
from src.data.errors import (
    NewerFormatError,
    ProjectFormatError,
    UnsupportedUpgradeError,
)
from src.data.format_version import (
    CURRENT_FORMAT_VERSION,
    FORMAT_VERSION_KEY,
    upgrade,
)


def project_data(version=None) -> dict:
    """
    Build a minimal project dictionary.

    Args:
        version: The format version to stamp, or None to leave the key out.

    Returns:
        dict: The project data.
    """
    data = {"name": "Errors", "items": [], "votes": []}
    if version is not None:
        data[FORMAT_VERSION_KEY] = version
    return data


class TestErrorHierarchy(unittest.TestCase):
    """Test cases for how the format errors relate to one another."""

    def test_every_format_error_is_a_value_error(self):
        """Test that existing ValueError handlers still catch these."""
        cases = [ProjectFormatError, NewerFormatError, UnsupportedUpgradeError]
        for error_type in cases:
            with self.subTest(error_type=error_type.__name__):
                self.assertTrue(issubclass(error_type, ValueError))

    def test_subclasses_share_a_base(self):
        """Test that both specific errors can be caught as one kind."""
        for error_type in [NewerFormatError, UnsupportedUpgradeError]:
            with self.subTest(error_type=error_type.__name__):
                self.assertTrue(issubclass(error_type, ProjectFormatError))

    def test_the_two_specific_errors_are_distinct(self):
        """Test that catching one does not catch the other."""
        self.assertFalse(issubclass(NewerFormatError, UnsupportedUpgradeError))
        self.assertFalse(issubclass(UnsupportedUpgradeError, NewerFormatError))

    def test_newer_format_error_carries_its_versions(self):
        """Test that the error reports the versions without message parsing."""
        error = NewerFormatError("nope", file_version=9, supported_version=3)

        self.assertEqual(error.file_version, 9)
        self.assertEqual(error.supported_version, 3)

    def test_versions_are_optional(self):
        """Test that the errors can be raised with a message alone."""
        for error in [NewerFormatError("nope"), UnsupportedUpgradeError("nope")]:
            with self.subTest(error=type(error).__name__):
                self.assertIsNone(error.file_version)


class TestUpgradeRaisesTypedErrors(unittest.TestCase):
    """Test cases for the errors the upgrade walk raises."""

    def test_newer_file_raises_newer_format_error(self):
        """Test that a file from the future is typed, not just worded."""
        with self.assertRaises(NewerFormatError) as ctx:
            upgrade(project_data(CURRENT_FORMAT_VERSION + 1))

        self.assertEqual(ctx.exception.file_version, CURRENT_FORMAT_VERSION + 1)
        self.assertEqual(
            ctx.exception.supported_version, CURRENT_FORMAT_VERSION
        )

    def test_newer_file_message_is_unchanged(self):
        """Test that the wording users and older tests rely on still stands."""
        with self.assertRaises(ValueError) as ctx:
            upgrade(project_data(CURRENT_FORMAT_VERSION + 1))

        self.assertIn("newer", str(ctx.exception))

    def test_current_file_raises_nothing(self):
        """Test that a current file walks through without complaint."""
        upgraded, started = upgrade(project_data(CURRENT_FORMAT_VERSION))

        self.assertEqual(started, CURRENT_FORMAT_VERSION)
        self.assertEqual(upgraded[FORMAT_VERSION_KEY], CURRENT_FORMAT_VERSION)

    def test_missing_upgrade_step_raises_unsupported_upgrade_error(self):
        """Test that a gap in the upgrade chain is its own kind of error."""
        with patch.dict(format_version._UPGRADE_STEPS, clear=True):
            with self.assertRaises(UnsupportedUpgradeError) as ctx:
                upgrade(project_data())

        self.assertEqual(ctx.exception.file_version, 1)

    def test_missing_upgrade_step_message_is_unchanged(self):
        """Test that the gap's wording still names the version it stuck at."""
        with patch.dict(format_version._UPGRADE_STEPS, clear=True):
            with self.assertRaises(ValueError) as ctx:
                upgrade(project_data())

        self.assertIn("No upgrade path", str(ctx.exception))

    def test_unreadable_version_key_still_raises_value_error(self):
        """Test that a bad version key is rejected before any typing applies."""
        with self.assertRaises(ValueError):
            upgrade({"name": "Errors", FORMAT_VERSION_KEY: "three"})


if __name__ == "__main__":
    unittest.main()
