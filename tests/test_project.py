"""Unit tests for the Project model."""

import unittest
from datetime import datetime
from pathlib import Path

from src.models.project import (
    CURRENT_FORMAT_VERSION,
    Project,
    active_identifiers,
    free_slots,
    identifier_in_use,
)
from src.models.item import Item
from src.models.vote import Vote
from src.models.ranking import PairSelector
from src.models.settings import Settings


class TestProject(unittest.TestCase):
    """Test cases for the Project dataclass."""

    def test_create_project_with_name_only(self):
        """Test creating a project with just a name."""
        project = Project(name="Test Project")
        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.items, [])
        self.assertEqual(project.votes, [])
        self.assertIsInstance(project.settings, Settings)
        self.assertIsNone(project.file_path)
        self.assertIsNotNone(project.created)
        self.assertIsNotNone(project.modified)

    def test_create_project_with_all_fields(self):
        """Test creating a project with all fields."""
        items = [Item(name="Item 1"), Item(name="Item 2")]
        votes = [Vote(winner_id=items[0].id, loser_id=items[1].id, weight=1.0)]
        settings = Settings(weight_uncertainty=2.0)
        created = datetime(2024, 1, 1)
        modified = datetime(2024, 1, 15)
        file_path = Path("/test/project.pairrank")

        project = Project(
            name="Test Project",
            items=items,
            votes=votes,
            settings=settings,
            created=created,
            modified=modified,
            file_path=file_path,
        )

        self.assertEqual(project.name, "Test Project")
        self.assertEqual(len(project.items), 2)
        self.assertEqual(len(project.votes), 1)
        self.assertEqual(project.settings.weight_uncertainty, 2.0)
        self.assertEqual(project.created, created)
        self.assertEqual(project.modified, modified)
        self.assertEqual(project.file_path, file_path)

    def test_project_name_stripped(self):
        """Test that project name is stripped of whitespace."""
        project = Project(name="  Test Project  ")
        self.assertEqual(project.name, "Test Project")

    def test_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with self.assertRaises(ValueError):
            Project(name="")

    def test_whitespace_only_name_raises_error(self):
        """Test that whitespace-only name raises ValueError."""
        with self.assertRaises(ValueError):
            Project(name="   ")

    def test_to_dict(self):
        """Test converting project to dictionary."""
        items = [Item(name="Item 1", id="item-1")]
        votes = [Vote(winner_id="item-1", loser_id="item-2", weight=1.0, id="vote-1")]
        settings = Settings(weight_uncertainty=2.0)
        created = datetime(2024, 1, 1, 12, 0, 0)
        modified = datetime(2024, 1, 15, 14, 30, 0)

        project = Project(
            name="Test Project",
            items=items,
            votes=votes,
            settings=settings,
            created=created,
            modified=modified,
        )

        result = project.to_dict()

        self.assertEqual(result["name"], "Test Project")
        self.assertEqual(result["created"], "2024-01-01T12:00:00")
        self.assertEqual(result["modified"], "2024-01-15T14:30:00")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["name"], "Item 1")
        self.assertEqual(len(result["votes"]), 1)
        self.assertEqual(result["votes"][0]["id"], "vote-1")
        self.assertEqual(result["settings"]["weight_uncertainty"], 2.0)

    def test_from_dict_full(self):
        """Test creating project from dictionary with all fields."""
        data = {
            "name": "Test Project",
            "created": "2024-01-01T12:00:00",
            "modified": "2024-01-15T14:30:00",
            "items": [{"id": "item-1", "name": "Item 1", "description": "", "identifier": ""}],
            "votes": [{"id": "vote-1", "winner_id": "item-1", "loser_id": "item-2", "weight": 1.0, "timestamp": "2024-01-10T10:00:00"}],
            "settings": {"weight_uncertainty": 2.0},
        }

        project = Project.from_dict(data)

        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.created, datetime(2024, 1, 1, 12, 0, 0))
        self.assertEqual(project.modified, datetime(2024, 1, 15, 14, 30, 0))
        self.assertEqual(len(project.items), 1)
        self.assertEqual(project.items[0].name, "Item 1")
        self.assertEqual(len(project.votes), 1)
        self.assertEqual(project.votes[0].id, "vote-1")
        self.assertEqual(project.settings.weight_uncertainty, 2.0)

    def test_from_dict_minimal(self):
        """Test creating project from dictionary with minimal fields."""
        data = {"name": "Test Project"}
        project = Project.from_dict(data)

        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.items, [])
        self.assertEqual(project.votes, [])
        self.assertIsInstance(project.settings, Settings)

    def test_from_dict_with_file_path(self):
        """Test creating project from dictionary with file path."""
        data = {"name": "Test Project"}
        file_path = Path("/test/project.pairrank")

        project = Project.from_dict(data, file_path=file_path)

        self.assertEqual(project.file_path, file_path)

    def test_roundtrip_dict_conversion(self):
        """Test that to_dict and from_dict are inverses."""
        items = [Item(name="Item 1", id="item-1"), Item(name="Item 2", id="item-2")]
        votes = [Vote(winner_id="item-1", loser_id="item-2", weight=2.0, id="vote-1")]
        settings = Settings(weight_uncertainty=1.5, decay_timescale_days=60.0)
        created = datetime(2024, 1, 1, 12, 0, 0)
        modified = datetime(2024, 1, 15, 14, 30, 0)

        original = Project(
            name="Test Project",
            items=items,
            votes=votes,
            settings=settings,
            created=created,
            modified=modified,
        )

        data = original.to_dict()
        restored = Project.from_dict(data)

        self.assertEqual(original.name, restored.name)
        self.assertEqual(original.created, restored.created)
        self.assertEqual(original.modified, restored.modified)
        self.assertEqual(len(original.items), len(restored.items))
        self.assertEqual(len(original.votes), len(restored.votes))
        self.assertEqual(original.settings.weight_uncertainty, restored.settings.weight_uncertainty)
        self.assertEqual(original.settings.decay_timescale_days, restored.settings.decay_timescale_days)

    def test_from_dict_with_empty_items_and_votes(self):
        """Test creating project with empty items and votes lists."""
        data = {
            "name": "Empty Project",
            "items": [],
            "votes": [],
            "settings": {},
        }

        project = Project.from_dict(data)

        self.assertEqual(project.name, "Empty Project")
        self.assertEqual(project.items, [])
        self.assertEqual(project.votes, [])

    def test_from_dict_missing_name_raises_value_error(self):
        """Test that from_dict raises ValueError (not KeyError) when name is missing."""
        with self.assertRaises(ValueError) as ctx:
            Project.from_dict({})

        self.assertIn("name", str(ctx.exception))

    def test_from_dict_non_dict_raises_value_error(self):
        """Test that from_dict raises ValueError when data is not a dictionary."""
        with self.assertRaises(ValueError):
            Project.from_dict([])

    def test_to_dict_includes_format_version(self):
        """Test that to_dict stamps the current format version."""
        project = Project(name="Test Project")
        self.assertEqual(project.to_dict()["format_version"], CURRENT_FORMAT_VERSION)

    def test_to_dict_includes_slots(self):
        """Test that to_dict includes the slot list."""
        project = Project(name="Test Project", slots=["1", "2"])
        self.assertEqual(project.to_dict()["slots"], ["1", "2"])

    def test_roundtrip_slots(self):
        """Test that slots survive to_dict/from_dict."""
        project = Project(name="Test Project", slots=["A", "B", "C"])
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.slots, ["A", "B", "C"])

    def test_from_dict_without_slots(self):
        """Test that a project dict without slots yields an empty slot list."""
        project = Project.from_dict({"name": "Test Project"})
        self.assertEqual(project.slots, [])


class TestProjectRename(unittest.TestCase):
    """Test cases for Project.rename."""

    def test_rename_changes_the_name(self):
        """Test that renaming replaces the display name."""
        project = Project(name="Old Name")
        project.rename("New Name")
        self.assertEqual(project.name, "New Name")

    def test_rename_strips_surrounding_whitespace(self):
        """Test that a name with surrounding whitespace is stripped."""
        project = Project(name="Old Name")
        project.rename("  New Name  ")
        self.assertEqual(project.name, "New Name")

    def test_rename_to_empty_raises_value_error(self):
        """Test that an empty name is rejected and the old name survives."""
        project = Project(name="Old Name")
        with self.assertRaises(ValueError):
            project.rename("")
        self.assertEqual(project.name, "Old Name")

    def test_rename_to_whitespace_raises_value_error(self):
        """Test that a whitespace-only name is rejected."""
        project = Project(name="Old Name")
        with self.assertRaises(ValueError):
            project.rename("   ")
        self.assertEqual(project.name, "Old Name")

    def test_rename_leaves_other_fields_untouched(self):
        """Test that renaming touches nothing but the name."""
        item = Item(name="Item 1", identifier="A")
        other = Item(name="Item 2", identifier="B")
        vote = Vote(winner_id=item.id, loser_id=other.id, weight=1.0)
        created = datetime(2024, 1, 1)
        modified = datetime(2024, 1, 15)
        project = Project(
            name="Old Name",
            created=created,
            modified=modified,
            items=[item, other],
            votes=[vote],
            settings=Settings(weight_uncertainty=2.0),
            slots=["A", "B"],
            file_path=Path("/tmp/project.pairrank"),
        )

        project.rename("New Name")

        self.assertEqual(project.created, created)
        self.assertEqual(project.modified, modified)
        self.assertEqual(project.items, [item, other])
        self.assertEqual(project.votes, [vote])
        self.assertEqual(project.settings.weight_uncertainty, 2.0)
        self.assertEqual(project.slots, ["A", "B"])
        self.assertEqual(project.file_path, Path("/tmp/project.pairrank"))


class TestProjectCopyWithoutVotes(unittest.TestCase):
    """Test cases for Project.copy_without_votes."""

    def setUp(self):
        """Set up a project with items, a retired item, votes and slots."""
        self.active = Item(name="Item 1", identifier="A", category="Cats")
        self.retired = Item(name="Item 2", id="retired-id")
        self.retired.retire(now=datetime(2024, 3, 1), replaced_by=self.active.id)
        self.third = Item(name="Item 3", identifier="B")
        self.project = Project(
            name="Source",
            items=[self.active, self.retired, self.third],
            votes=[
                Vote(winner_id=self.active.id, loser_id=self.third.id, weight=1.0),
                Vote(winner_id=self.third.id, loser_id=self.active.id, weight=2.0),
            ],
            settings=Settings(weight_uncertainty=2.5, top_tier_count=7),
            slots=["A", "B"],
            file_path=Path("/tmp/source.pairrank"),
        )

    def test_copy_has_no_votes(self):
        """Test that the copy starts with an empty vote list."""
        copied = self.project.copy_without_votes("Copy")
        self.assertEqual(copied.votes, [])

    def test_source_keeps_its_votes(self):
        """Test that copying leaves the source project's votes in place."""
        self.project.copy_without_votes("Copy")
        self.assertEqual(len(self.project.votes), 2)

    def test_copy_uses_the_new_name(self):
        """Test that the copy carries the requested name."""
        copied = self.project.copy_without_votes("Copy")
        self.assertEqual(copied.name, "Copy")
        self.assertEqual(self.project.name, "Source")

    def test_copy_strips_surrounding_whitespace(self):
        """Test that a name with surrounding whitespace is stripped."""
        copied = self.project.copy_without_votes("  Copy  ")
        self.assertEqual(copied.name, "Copy")

    def test_empty_name_raises_value_error(self):
        """Test that an empty name is rejected."""
        with self.assertRaises(ValueError):
            self.project.copy_without_votes("")

    def test_whitespace_only_name_raises_value_error(self):
        """Test that a whitespace-only name is rejected."""
        with self.assertRaises(ValueError):
            self.project.copy_without_votes("   ")

    def test_items_match_by_count_order_and_id(self):
        """Test that the copy holds the same items in the same order."""
        copied = self.project.copy_without_votes("Copy")
        self.assertEqual(
            [item.id for item in copied.items],
            [item.id for item in self.project.items],
        )
        self.assertEqual(
            [item.name for item in copied.items],
            ["Item 1", "Item 2", "Item 3"],
        )

    def test_retired_item_survives_intact(self):
        """Test that a retired item keeps its lifecycle fields."""
        copied = self.project.copy_without_votes("Copy")
        retired = copied.items[1]
        self.assertEqual(retired.id, "retired-id")
        self.assertFalse(retired.is_active())
        self.assertEqual(retired.retired_at, datetime(2024, 3, 1))
        self.assertEqual(retired.replaced_by, self.active.id)

    def test_items_are_distinct_instances(self):
        """Test that editing a copied item leaves the source item alone."""
        copied = self.project.copy_without_votes("Copy")
        self.assertIsNot(copied.items, self.project.items)
        self.assertIsNot(copied.items[0], self.active)

        copied.items[0].name = "Renamed"
        copied.items.append(Item(name="Extra"))

        self.assertEqual(self.active.name, "Item 1")
        self.assertEqual(len(self.project.items), 3)

    def test_settings_values_match_the_source(self):
        """Test that the copy's settings hold the source's values."""
        copied = self.project.copy_without_votes("Copy")
        self.assertEqual(copied.settings.to_dict(), self.project.settings.to_dict())

    def test_settings_are_a_distinct_instance(self):
        """Test that editing the copy's settings leaves the source alone."""
        copied = self.project.copy_without_votes("Copy")
        self.assertIsNot(copied.settings, self.project.settings)

        copied.settings.weight_uncertainty = 9.0

        self.assertEqual(self.project.settings.weight_uncertainty, 2.5)

    def test_slots_match_the_source(self):
        """Test that the copy defines the same slots."""
        copied = self.project.copy_without_votes("Copy")
        self.assertEqual(copied.slots, ["A", "B"])

    def test_slots_are_a_distinct_list(self):
        """Test that editing the copy's slot list leaves the source alone."""
        copied = self.project.copy_without_votes("Copy")
        self.assertIsNot(copied.slots, self.project.slots)

        copied.slots.append("C")

        self.assertEqual(self.project.slots, ["A", "B"])

    def test_copy_has_no_file_path(self):
        """Test that the copy is not associated with a file."""
        copied = self.project.copy_without_votes("Copy")
        self.assertIsNone(copied.file_path)
        self.assertEqual(self.project.file_path, Path("/tmp/source.pairrank"))


class TestProjectSlots(unittest.TestCase):
    """Test cases for the project slot list helpers."""

    def test_default_slots_empty(self):
        """Test that a new project defines no slots."""
        self.assertEqual(Project(name="P").slots, [])

    def test_set_slots_strips_and_drops_empty(self):
        """Test that set_slots strips entries and drops empty ones."""
        project = Project(name="P")
        project.set_slots(["  A  ", "", "   ", "B"])
        self.assertEqual(project.slots, ["A", "B"])

    def test_set_slots_dedupes_preserving_order(self):
        """Test that set_slots removes duplicates but keeps the first order."""
        project = Project(name="P")
        project.set_slots(["B", "A", "B", "C", "A"])
        self.assertEqual(project.slots, ["B", "A", "C"])

    def test_constructor_normalizes_slots(self):
        """Test that slots passed to the constructor are normalized."""
        project = Project(name="P", slots=[" A ", "A", ""])
        self.assertEqual(project.slots, ["A"])

    def test_free_slots_excludes_active_identifiers(self):
        """Test that slots held by active items are not free."""
        project = Project(
            name="P",
            slots=["1", "2", "3"],
            items=[Item(name="X", identifier="2")],
        )
        self.assertEqual(project.free_slots(), ["1", "3"])

    def test_free_slots_ignores_retired_items(self):
        """Test that retiring an item releases its slot."""
        item = Item(name="X", identifier="2")
        project = Project(name="P", slots=["1", "2", "3"], items=[item])
        item.retire()
        self.assertEqual(project.free_slots(), ["1", "2", "3"])

    def test_free_slots_empty_without_slot_list(self):
        """Test that a project with no slots has no free slots."""
        project = Project(name="P", items=[Item(name="X", identifier="2")])
        self.assertEqual(project.free_slots(), [])

    def test_free_slots_ignores_identifiers_outside_the_list(self):
        """Test that identifiers not in the slot list do not affect free slots."""
        project = Project(
            name="P",
            slots=["1", "2"],
            items=[Item(name="X", identifier="99")],
        )
        self.assertEqual(project.free_slots(), ["1", "2"])


class TestProjectItemLifecycle(unittest.TestCase):
    """Test cases for the active/retired item helpers on Project."""

    def setUp(self):
        """Build a project with one active and one retired item."""
        self.active = Item(name="Active", identifier="1", id="active-id")
        self.retired = Item(name="Retired", identifier="2", id="retired-id")
        self.retired.retire()
        self.project = Project(name="P", items=[self.active, self.retired])

    def test_active_items(self):
        """Test that active_items returns only active items."""
        self.assertEqual(self.project.active_items(), [self.active])

    def test_active_identifiers(self):
        """Test that active_identifiers only reports active, non-empty ids."""
        self.assertEqual(self.project.active_identifiers(), {"1"})

    def test_identifier_in_use_true(self):
        """Test that an identifier held by an active item is reported in use."""
        self.assertTrue(self.project.identifier_in_use("1"))

    def test_identifier_in_use_excludes_item(self):
        """Test that the item being edited does not block its own identifier."""
        self.assertFalse(
            self.project.identifier_in_use("1", exclude_item_id="active-id")
        )

    def test_identifier_in_use_empty_is_false(self):
        """Test that an empty identifier is never considered in use."""
        self.assertFalse(self.project.identifier_in_use(""))
        self.assertFalse(self.project.identifier_in_use("   "))

    def test_identifier_in_use_strips_whitespace(self):
        """Test that the checked identifier is stripped before comparison."""
        self.assertTrue(self.project.identifier_in_use("  1  "))

    def test_identifier_of_retired_item_is_free(self):
        """Test that a retired item never holds an identifier."""
        self.assertEqual(self.retired.identifier, "")
        self.assertFalse(self.project.identifier_in_use("2"))

    def test_active_items_is_the_comparison_pool(self):
        """Test that only active items feed the pair selector."""
        selector = PairSelector(
            self.project.active_items(), self.project.votes, self.project.settings
        )
        self.assertEqual(selector.items, [self.active])
        self.assertIsNone(selector.select_pair())


class TestProjectFromDictValidation(unittest.TestCase):
    """Test cases for the shape validation done by Project.from_dict."""

    def assert_rejects(self, data: dict, key: str):
        """Assert that from_dict rejects data with a message naming a key."""
        with self.assertRaises(ValueError) as ctx:
            Project.from_dict(data)
        self.assertIn(key, str(ctx.exception))

    def test_items_must_be_a_list_of_objects(self):
        """Test that a non-object entry in 'items' raises ValueError."""
        self.assert_rejects({"name": "x", "items": [1]}, "items")

    def test_items_must_not_be_a_scalar(self):
        """Test that a scalar 'items' value raises ValueError."""
        self.assert_rejects({"name": "x", "items": "nope"}, "items")

    def test_votes_must_be_a_list_of_objects(self):
        """Test that a non-object entry in 'votes' raises ValueError."""
        self.assert_rejects({"name": "x", "votes": [1]}, "votes")

    def test_settings_must_be_an_object(self):
        """Test that a non-object 'settings' value raises ValueError."""
        self.assert_rejects({"name": "x", "settings": "x"}, "settings")

    def test_slots_must_be_a_list(self):
        """Test that a string 'slots' value raises ValueError."""
        self.assert_rejects({"name": "x", "slots": "abc"}, "slots")

    def test_slots_must_hold_strings(self):
        """Test that a non-string slot entry raises ValueError."""
        self.assert_rejects({"name": "x", "slots": [1, 2]}, "slots")

    def test_name_must_be_a_non_empty_string(self):
        """Test that an empty or non-string name raises ValueError."""
        self.assert_rejects({"name": ""}, "name")
        self.assert_rejects({"name": "   "}, "name")
        self.assert_rejects({"name": 5}, "name")

    def test_null_optional_keys_are_treated_as_absent(self):
        """Test that explicit nulls fall back to the empty defaults."""
        project = Project.from_dict(
            {"name": "x", "items": None, "votes": None, "settings": None, "slots": None}
        )

        self.assertEqual(project.items, [])
        self.assertEqual(project.votes, [])
        self.assertEqual(project.slots, [])
        self.assertEqual(project.settings, Settings())


class TestSlotModuleFunctions(unittest.TestCase):
    """Test cases for the module-level slot helpers shared with the UI."""

    def setUp(self):
        """Build a mixed list of active and retired items."""
        self.active = Item(name="Active", identifier="1", id="active-id")
        self.other = Item(name="Other", identifier="3", id="other-id")
        self.blank = Item(name="Blank", id="blank-id")
        self.retired = Item(name="Retired", identifier="2", id="retired-id")
        self.retired.retire()
        self.items = [self.active, self.other, self.blank, self.retired]

    def test_active_identifiers_skips_retired_and_blank(self):
        """Test that only non-empty identifiers of active items are reported."""
        self.assertEqual(active_identifiers(self.items), {"1", "3"})

    def test_active_identifiers_of_empty_list(self):
        """Test that an empty item list yields no identifiers."""
        self.assertEqual(active_identifiers([]), set())

    def test_identifier_in_use_true(self):
        """Test that an identifier held by an active item is in use."""
        self.assertTrue(identifier_in_use(self.items, "1"))

    def test_identifier_in_use_strips_and_ignores_empty(self):
        """Test that the checked identifier is stripped and blanks are free."""
        self.assertTrue(identifier_in_use(self.items, "  1  "))
        self.assertFalse(identifier_in_use(self.items, ""))
        self.assertFalse(identifier_in_use(self.items, "   "))

    def test_identifier_in_use_excludes_item(self):
        """Test that an item does not block its own identifier."""
        self.assertFalse(
            identifier_in_use(self.items, "1", exclude_item_id="active-id")
        )

    def test_identifier_of_retired_item_is_free(self):
        """Test that a retired item's old identifier is not in use."""
        self.assertFalse(identifier_in_use(self.items, "2"))

    def test_free_slots_excludes_taken(self):
        """Test that slots held by active items are not free."""
        self.assertEqual(free_slots(["1", "2", "3", "4"], self.items), ["2", "4"])

    def test_free_slots_preserves_definition_order(self):
        """Test that free slots come back in the order they were defined."""
        self.assertEqual(free_slots(["4", "2"], self.items), ["4", "2"])

    def test_free_slots_of_empty_slot_list(self):
        """Test that a project without slots has no free slots."""
        self.assertEqual(free_slots([], self.items), [])

    def test_project_methods_delegate(self):
        """Test that the Project methods agree with the module functions."""
        project = Project(name="P", items=self.items, slots=["1", "2", "4"])

        self.assertEqual(project.active_identifiers(), active_identifiers(self.items))
        self.assertEqual(project.free_slots(), free_slots(project.slots, self.items))
        self.assertEqual(
            project.identifier_in_use("3"), identifier_in_use(self.items, "3")
        )


class TestProjectPopLastVote(unittest.TestCase):
    """Test cases for undoing the most recent vote."""

    def setUp(self):
        """Build a project with two items and no votes yet."""
        self.a = Item(name="A", id="a")
        self.b = Item(name="B", id="b")
        self.project = Project(name="P", items=[self.a, self.b])

    def _vote(self, weight: float) -> Vote:
        """Append a vote of the given weight and return it."""
        vote = Vote(winner_id="a", loser_id="b", weight=weight)
        self.project.votes.append(vote)
        return vote

    def test_pop_from_empty_returns_none(self):
        """Test that popping with no votes returns None."""
        self.assertIsNone(self.project.pop_last_vote())
        self.assertEqual(self.project.votes, [])

    def test_pop_returns_most_recent_vote(self):
        """Test that the last appended vote is the one returned."""
        self._vote(1.0)
        last = self._vote(3.0)

        popped = self.project.pop_last_vote()

        self.assertIs(popped, last)

    def test_pop_removes_the_vote(self):
        """Test that the popped vote is gone from the project."""
        first = self._vote(1.0)
        self._vote(3.0)

        self.project.pop_last_vote()

        self.assertEqual(self.project.votes, [first])

    def test_repeated_pop_empties_the_project(self):
        """Test that popping repeatedly removes votes newest-first."""
        first = self._vote(1.0)
        second = self._vote(2.0)
        third = self._vote(3.0)

        popped = [
            self.project.pop_last_vote(),
            self.project.pop_last_vote(),
            self.project.pop_last_vote(),
        ]

        self.assertEqual(popped, [third, second, first])
        self.assertEqual(self.project.votes, [])
        self.assertIsNone(self.project.pop_last_vote())

    def test_pop_mutates_the_shared_list(self):
        """Test that a caller holding the votes list sees the removal."""
        votes = self.project.votes
        self._vote(2.0)

        self.project.pop_last_vote()

        self.assertEqual(votes, [])
        self.assertIs(self.project.votes, votes)

    def test_pop_leaves_items_untouched(self):
        """Test that undoing a vote does not touch the items."""
        self._vote(2.0)

        self.project.pop_last_vote()

        self.assertEqual(self.project.items, [self.a, self.b])


if __name__ == "__main__":
    unittest.main()
