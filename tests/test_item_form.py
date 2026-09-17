"""Unit tests for the Qt-free item form validation in src/app/items.py."""

import unittest

from src.app.items import (
    FIELD_IDENTIFIER,
    FIELD_NAME,
    ItemFieldError,
    validate_item_form,
)
from src.models.item import DEFAULT_CATEGORY


class TestValidateItemFormCleaning(unittest.TestCase):
    """Test cases for the cleaned values a verdict carries."""

    #: (description, field name, entered value, expected cleaned value)
    STRIPPED_FIELDS = [
        ("name", "name", "  Switch  ", "Switch"),
        ("description", "description", "  quiet  ", "quiet"),
        ("identifier", "identifier", "  A1  ", "A1"),
        ("category", "category", "  Linear  ", "Linear"),
    ]

    def test_fields_are_stripped(self):
        """Test that surrounding whitespace is removed from every field."""
        for label, field, entered, expected in self.STRIPPED_FIELDS:
            with self.subTest(label):
                verdict = validate_item_form(**{"name": "Switch", field: entered})
                self.assertEqual(getattr(verdict.form, field), expected)

    def test_empty_category_falls_back_to_the_default(self):
        """Test that an item with no category joins the default one."""
        for entered in ("", "   "):
            with self.subTest(entered=repr(entered)):
                verdict = validate_item_form(name="Switch", category=entered)
                self.assertEqual(verdict.form.category, DEFAULT_CATEGORY)

    def test_cleaned_values_survive_an_invalid_form(self):
        """Test that a rejected form still reports what was entered."""
        verdict = validate_item_form(name="   ", identifier=" A1 ")

        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.form.identifier, "A1")


class TestValidateItemFormName(unittest.TestCase):
    """Test cases for the name rule."""

    def test_a_name_is_required(self):
        """Test that an empty name is rejected."""
        for entered in ("", "   ", "\t"):
            with self.subTest(entered=repr(entered)):
                verdict = validate_item_form(name=entered)

                self.assertFalse(verdict.ok)
                self.assertEqual(
                    verdict.errors[FIELD_NAME], ItemFieldError.NAME_REQUIRED
                )

    def test_a_name_is_all_that_is_required(self):
        """Test that a name on its own is a valid form."""
        verdict = validate_item_form(name="Switch")

        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.errors, {})

    def test_duplicate_names_are_accepted(self):
        """Test that names need not be unique."""
        verdict = validate_item_form(name="Switch", taken_identifiers={"A1"})

        self.assertTrue(verdict.ok)


class TestValidateItemFormIdentifier(unittest.TestCase):
    """Test cases for the identifier rule."""

    def test_an_identifier_in_use_is_rejected(self):
        """Test that another active item's identifier cannot be taken."""
        verdict = validate_item_form(
            name="Switch", identifier="A1", taken_identifiers={"A1", "A2"}
        )

        self.assertFalse(verdict.ok)
        self.assertEqual(
            verdict.errors[FIELD_IDENTIFIER], ItemFieldError.IDENTIFIER_IN_USE
        )

    def test_an_empty_identifier_is_never_in_use(self):
        """Test that leaving the identifier blank is always allowed."""
        verdict = validate_item_form(
            name="Switch", identifier="  ", taken_identifiers={"", "A1"}
        )

        self.assertTrue(verdict.ok)

    def test_a_free_identifier_is_accepted(self):
        """Test that an identifier nobody holds passes."""
        verdict = validate_item_form(
            name="Switch", identifier="A3", taken_identifiers={"A1", "A2"}
        )

        self.assertTrue(verdict.ok)

    def test_an_identifier_outside_the_slot_list_is_accepted(self):
        """Test that free text passes even when the project defines slots."""
        verdict = validate_item_form(
            name="Switch", identifier="somewhere else", taken_identifiers={"A1"}
        )

        self.assertTrue(verdict.ok)

    def test_no_taken_identifiers_means_nothing_is_taken(self):
        """Test that omitting the set of holders accepts any identifier."""
        verdict = validate_item_form(name="Switch", identifier="A1")

        self.assertTrue(verdict.ok)


class TestValidateItemFormErrorOrder(unittest.TestCase):
    """Test cases for how several errors are reported together."""

    def test_both_errors_are_reported_name_first(self):
        """Test that a form wrong in two ways reports the name before the identifier."""
        verdict = validate_item_form(
            name="", identifier="A1", taken_identifiers={"A1"}
        )

        self.assertEqual(list(verdict.errors), [FIELD_NAME, FIELD_IDENTIFIER])


if __name__ == "__main__":
    unittest.main()
