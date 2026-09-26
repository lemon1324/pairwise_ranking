"""Unit tests for the slot short labels and the slot list format."""

import unittest

from src.app.slots import (
    SlotLabelError,
    check_slot_labels,
    clean_slot_labels,
    entered_slot_labels,
    format_slot_list,
    label_collisions,
    label_owner,
    parse_slot_list,
    short_label,
    validate_slot_labels,
)
from src.models.project import Project


class TestShortLabel(unittest.TestCase):
    """Test cases for resolving a slot's two-character label."""

    def test_derived_from_the_first_two_characters(self):
        """Test that a slot with no explicit label uses its first two letters."""
        self.assertEqual(short_label("Apostrophe"), "Ap")

    def test_short_name_is_used_whole(self):
        """Test that a one-character slot name is its own label."""
        self.assertEqual(short_label("7"), "7")

    def test_explicit_label_wins(self):
        """Test that an entry in the label map beats the derived label."""
        self.assertEqual(short_label("Apostrophe", {"Apostrophe": "'"}), "'")

    def test_explicit_label_is_truncated(self):
        """Test that an over-long explicit label is cut to two characters."""
        self.assertEqual(short_label("A", {"A": "abcd"}), "ab")

    def test_blank_explicit_label_falls_back(self):
        """Test that a whitespace-only label is ignored."""
        self.assertEqual(short_label("Apex", {"Apex": "   "}), "Ap")

    def test_label_for_another_slot_is_ignored(self):
        """Test that only the slot's own entry is consulted."""
        self.assertEqual(short_label("Apex", {"Apostrophe": "'"}), "Ap")

    def test_slot_name_is_stripped(self):
        """Test that surrounding whitespace does not become part of the label."""
        self.assertEqual(short_label("  Apex  "), "Ap")

    def test_empty_slot_gives_an_empty_label(self):
        """Test that only an empty slot name yields an empty label."""
        for slot in ["", "   "]:
            with self.subTest(slot=slot):
                self.assertEqual(short_label(slot), "")

    def test_never_longer_than_two_characters(self):
        """Test that every resolved label fits the two-character budget."""
        cases = ["A", "Apex", "Apostrophe", "12345"]
        for slot in cases:
            with self.subTest(slot=slot):
                self.assertLessEqual(len(short_label(slot)), 2)

    def test_uses_a_project_label_map(self):
        """Test that a project's stored labels resolve its own slots."""
        project = Project(
            name="P",
            slots=["Apostrophe", "Apex"],
            slot_labels={"Apostrophe": "'"},
        )

        resolved = [
            short_label(slot, project.slot_labels) for slot in project.slots
        ]

        self.assertEqual(resolved, ["'", "Ap"])


class TestCleanSlotLabels(unittest.TestCase):
    """Test cases for stripping a raw label map down to the known slots."""

    def test_strips_keys_and_values(self):
        """Test that whitespace is removed from both sides of an entry."""
        self.assertEqual(clean_slot_labels(["A"], {" A ": " x "}), {"A": "x"})

    def test_drops_blank_labels(self):
        """Test that an empty label is dropped rather than kept empty."""
        self.assertEqual(clean_slot_labels(["A"], {"A": "  "}), {})

    def test_drops_labels_for_unknown_slots(self):
        """Test that a label naming no slot is dropped."""
        self.assertEqual(clean_slot_labels(["A"], {"Z": "z"}), {})

    def test_does_not_truncate(self):
        """Test that an over-long label survives cleaning so it can be rejected."""
        self.assertEqual(clean_slot_labels(["A"], {"A": "abcd"}), {"A": "abcd"})

    def test_follows_slot_order(self):
        """Test that the cleaned map is ordered by the slot list."""
        cleaned = clean_slot_labels(["A", "B"], {"B": "b", "A": "a"})
        self.assertEqual(list(cleaned), ["A", "B"])

    def test_empty_inputs(self):
        """Test that empty slots or labels produce an empty map."""
        for slots, labels in [([], {"A": "a"}), (["A"], {}), ([], {})]:
            with self.subTest(slots=slots, labels=labels):
                self.assertEqual(clean_slot_labels(slots, labels), {})


class TestValidateSlotLabels(unittest.TestCase):
    """Test cases for the explicit slot label validator."""

    def test_valid_labels_are_accepted(self):
        """Test that distinct two-character labels pass."""
        verdict = validate_slot_labels(["A", "B"], {"A": "a", "B": "b"})

        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.errors, {})
        self.assertEqual(verdict.labels, {"A": "a", "B": "b"})

    def test_no_labels_at_all_is_valid(self):
        """Test that a project with no explicit labels passes."""
        verdict = validate_slot_labels(["A", "B"], {})

        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.labels, {})

    def test_long_label_is_rejected(self):
        """Test that a label of three characters is too long."""
        verdict = validate_slot_labels(["A"], {"A": "abc"})

        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.errors, {"A": SlotLabelError.LABEL_TOO_LONG})

    def test_two_character_label_is_accepted(self):
        """Test that the length limit is inclusive."""
        verdict = validate_slot_labels(["A"], {"A": "ab"})
        self.assertTrue(verdict.ok)

    def test_duplicate_label_is_rejected(self):
        """Test that two slots cannot carry the same explicit label."""
        verdict = validate_slot_labels(
            ["Apex", "Apostrophe"], {"Apex": "Ax", "Apostrophe": "Ax"}
        )

        self.assertFalse(verdict.ok)
        self.assertEqual(
            verdict.errors, {"Apostrophe": SlotLabelError.LABEL_IN_USE}
        )

    def test_the_first_slot_keeps_the_label(self):
        """Test that the complaint lands on the later slot, in slot order."""
        verdict = validate_slot_labels(
            ["B", "A"], {"A": "x", "B": "x"}
        )
        self.assertEqual(list(verdict.errors), ["A"])

    def test_labels_differing_in_case_do_not_clash(self):
        """Test that comparison is exact, so 'ab' and 'AB' are two labels."""
        verdict = validate_slot_labels(["A", "B"], {"A": "ab", "B": "AB"})
        self.assertTrue(verdict.ok)

    def test_a_long_label_is_not_also_reported_as_duplicated(self):
        """Test that one slot carries at most one complaint."""
        verdict = validate_slot_labels(
            ["A", "B"], {"A": "abc", "B": "abc"}
        )

        self.assertEqual(
            verdict.errors,
            {"A": SlotLabelError.LABEL_TOO_LONG, "B": SlotLabelError.LABEL_TOO_LONG},
        )

    def test_labels_for_unknown_slots_are_ignored(self):
        """Test that a label for a dropped slot does not block a save."""
        verdict = validate_slot_labels(["A"], {"A": "a", "Gone": "a"})

        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.labels, {"A": "a"})

    def test_errors_are_in_slot_order(self):
        """Test that the errors arrive in the order the slots are defined."""
        verdict = validate_slot_labels(
            ["A", "B", "C"], {"C": "xyz", "A": "uvw"}
        )
        self.assertEqual(list(verdict.errors), ["A", "C"])


class TestEnteredSlotLabels(unittest.TestCase):
    """Test cases for keeping only the board labels worth storing."""

    def test_a_label_equal_to_the_derived_one_is_not_kept(self):
        """Test that typing a slot's own first two characters stores nothing."""
        labels = entered_slot_labels(["Apex", "7"], {"Apex": "Ap", "7": "7"})
        self.assertEqual(labels, {})

    def test_empty_and_unknown_labels_are_dropped(self):
        """Test that an empty tile and a slot no longer listed store nothing."""
        labels = entered_slot_labels(
            ["Apostrophe", "Enter"], {"Apostrophe": " ' ", "Enter": "", "Gone": "G"}
        )
        self.assertEqual(labels, {"Apostrophe": "'"})

    def test_a_long_label_is_kept_to_be_refused(self):
        """Test that nothing is truncated here."""
        self.assertEqual(entered_slot_labels(["A"], {"A": "abc"}), {"A": "abc"})


class TestCheckSlotLabels(unittest.TestCase):
    """Test cases for the board's check: unique among every drawn label."""

    def test_a_label_matching_another_slots_derived_label_is_refused(self):
        """Test that derived labels count, unlike validate_slot_labels."""
        verdict = check_slot_labels(["Enter", "Apostrophe"], {"Apostrophe": "En"})

        self.assertEqual(verdict.errors, {"Apostrophe": SlotLabelError.LABEL_IN_USE})
        self.assertEqual(label_owner(["Enter", "Apostrophe"], verdict.labels, "Apostrophe"), "Enter")

    def test_typing_the_shared_derived_label_changes_nothing(self):
        """Test that "Ap" on Apostrophe is its own derived label: not stored, not refused."""
        verdict = check_slot_labels(["Apex", "Apostrophe"], {"Apostrophe": "Ap"})

        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.labels, {})

    def test_a_label_matching_a_short_slot_name_is_refused(self):
        """Test that a slot named "1" is drawn "1", so "1" is taken."""
        verdict = check_slot_labels(["1", "Apostrophe"], {"Apostrophe": "1"})
        self.assertEqual(verdict.errors, {"Apostrophe": SlotLabelError.LABEL_IN_USE})

    def test_two_entered_labels_refuse_the_later(self):
        """Test that the first slot keeps a label two slots were given."""
        slots = ["Apex", "Apostrophe", "Enter"]
        verdict = check_slot_labels(slots, {"Enter": "x", "Apex": "x"})

        self.assertEqual(verdict.errors, {"Enter": SlotLabelError.LABEL_IN_USE})
        self.assertEqual(label_owner(slots, verdict.labels, "Enter"), "Apex")

    def test_derived_labels_colliding_are_not_refused(self):
        """Test that a collision nobody chose is a warning, not an error."""
        verdict = check_slot_labels(["Apex", "Apostrophe"], {})

        self.assertTrue(verdict.ok)
        self.assertEqual(label_collisions(["Apex", "Apostrophe"], verdict.labels), {"Ap": ["Apex", "Apostrophe"]})

    def test_a_label_resolving_a_collision_is_accepted(self):
        """Test the fix the board's warning asks for."""
        verdict = check_slot_labels(["Apex", "Apostrophe"], {"Apostrophe": "'"})

        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.labels, {"Apostrophe": "'"})

    def test_a_long_label_is_refused(self):
        """Test the length limit."""
        verdict = check_slot_labels(["Apex"], {"Apex": "abc"})
        self.assertEqual(verdict.errors, {"Apex": SlotLabelError.LABEL_TOO_LONG})

    def test_moving_a_label_between_slots_is_accepted(self):
        """Test that a label taken from one slot can go to another in one save."""
        verdict = check_slot_labels(["Apex", "Apostrophe"], {"Apex": "", "Apostrophe": "x"})
        self.assertTrue(verdict.ok)


class TestLabelCollisions(unittest.TestCase):
    """Test cases for reporting slots that resolve to the same short label."""

    def test_no_collision(self):
        """Test that distinct labels report nothing."""
        self.assertEqual(label_collisions(["Apex", "Boba"]), {})

    def test_shared_first_two_characters_collide(self):
        """Test that two slots sharing their first two letters are reported."""
        self.assertEqual(
            label_collisions(["Apex", "Apostrophe"]),
            {"Ap": ["Apex", "Apostrophe"]},
        )

    def test_an_explicit_label_resolves_the_collision(self):
        """Test that giving one slot a label clears the warning."""
        self.assertEqual(
            label_collisions(["Apex", "Apostrophe"], {"Apostrophe": "'"}), {}
        )

    def test_an_explicit_label_can_create_a_collision(self):
        """Test that a label clashing with a derived one is reported too."""
        self.assertEqual(
            label_collisions(["Apex", "Boba"], {"Boba": "Ap"}),
            {"Ap": ["Apex", "Boba"]},
        )

    def test_three_slots_in_one_group(self):
        """Test that more than two colliding slots come back in one group."""
        self.assertEqual(
            label_collisions(["Apex", "Apostrophe", "Apple"]),
            {"Ap": ["Apex", "Apostrophe", "Apple"]},
        )

    def test_two_separate_groups(self):
        """Test that unrelated collisions are reported separately."""
        self.assertEqual(
            label_collisions(["Apex", "Apple", "Bin", "Bit"]),
            {"Ap": ["Apex", "Apple"], "Bi": ["Bin", "Bit"]},
        )

    def test_members_follow_slot_order(self):
        """Test that a group lists its slots in the order they are defined."""
        self.assertEqual(
            label_collisions(["Apple", "Apex"]), {"Ap": ["Apple", "Apex"]}
        )

    def test_empty_slot_list(self):
        """Test that an empty or missing slot list reports nothing."""
        for slots in [[], None]:
            with self.subTest(slots=slots):
                self.assertEqual(label_collisions(slots), {})

    def test_case_differences_do_not_collide(self):
        """Test that 'apex' and 'Apex' resolve to two different labels."""
        self.assertEqual(label_collisions(["apex", "Apex"]), {})


class TestSlotListFormat(unittest.TestCase):
    """Test cases for the comma-separated slot line."""

    def test_format_joins_with_comma_space(self):
        """Test that the slot list renders as one comma-separated line."""
        self.assertEqual(format_slot_list(["A", "B", "C"]), "A, B, C")

    def test_format_of_an_empty_list(self):
        """Test that no slots render as an empty line."""
        for slots in [[], None]:
            with self.subTest(slots=slots):
                self.assertEqual(format_slot_list(slots), "")

    def test_parse_splits_on_commas(self):
        """Test that a comma-separated line splits into entries."""
        self.assertEqual(parse_slot_list("A,B,C"), ["A", "B", "C"])

    def test_parse_still_accepts_newlines(self):
        """Test that a pasted column of names still parses."""
        self.assertEqual(parse_slot_list("A\nB\nC"), ["A", "B", "C"])

    def test_parse_accepts_both_separators_at_once(self):
        """Test that commas and newlines can be mixed."""
        self.assertEqual(parse_slot_list("A, B\nC"), ["A", " B", "C"])

    def test_parse_does_not_clean(self):
        """Test that cleaning is left to normalize_slots."""
        self.assertEqual(parse_slot_list(" A , A ,, "), [" A ", " A ", "", " "])

    def test_parse_of_empty_text(self):
        """Test that empty text parses to no entries."""
        for text in ["", None]:
            with self.subTest(text=text):
                self.assertEqual(parse_slot_list(text), [])

    def test_round_trip_through_a_project(self):
        """Test that formatting and parsing a stored list is stable."""
        project = Project(name="P", slots=["Apex", "Apostrophe", "7"])

        project.set_slots(parse_slot_list(format_slot_list(project.slots)))

        self.assertEqual(project.slots, ["Apex", "Apostrophe", "7"])

    def test_parsed_line_normalizes_the_way_the_old_one_did(self):
        """Test that a messy line reaches the project cleaned by set_slots."""
        project = Project(name="P")

        project.set_slots(parse_slot_list("  A , B,, A \n C "))

        self.assertEqual(project.slots, ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
