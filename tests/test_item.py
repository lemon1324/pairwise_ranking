"""Unit tests for the Item model."""

import unittest
from datetime import datetime

from src.models.item import (
    DEFAULT_CATEGORY,
    STATUS_ACTIVE,
    STATUS_RETIRED,
    Item,
)


class TestItem(unittest.TestCase):
    """Test cases for the Item dataclass."""

    def test_create_item_with_name_only(self):
        """Test creating an item with just a name."""
        item = Item(name="Test Item")
        self.assertEqual(item.name, "Test Item")
        self.assertEqual(item.description, "")
        self.assertEqual(item.identifier, "")
        self.assertIsNotNone(item.id)

    def test_create_item_with_description(self):
        """Test creating an item with name and description."""
        item = Item(name="Test Item", description="A test description")
        self.assertEqual(item.name, "Test Item")
        self.assertEqual(item.description, "A test description")

    def test_create_item_with_custom_id(self):
        """Test creating an item with a custom ID."""
        item = Item(name="Test Item", id="custom-id-123")
        self.assertEqual(item.id, "custom-id-123")

    def test_item_name_stripped(self):
        """Test that item name is stripped of whitespace."""
        item = Item(name="  Test Item  ")
        self.assertEqual(item.name, "Test Item")

    def test_item_description_stripped(self):
        """Test that item description is stripped of whitespace."""
        item = Item(name="Test", description="  Description  ")
        self.assertEqual(item.description, "Description")

    def test_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with self.assertRaises(ValueError):
            Item(name="")

    def test_whitespace_only_name_raises_error(self):
        """Test that whitespace-only name raises ValueError."""
        with self.assertRaises(ValueError):
            Item(name="   ")

    def test_item_equality_by_id(self):
        """Test that items are equal if they have the same ID."""
        item1 = Item(name="Item 1", id="same-id")
        item2 = Item(name="Item 2", id="same-id")
        self.assertEqual(item1, item2)

    def test_item_inequality_by_id(self):
        """Test that items are not equal if they have different IDs."""
        item1 = Item(name="Item 1", id="id-1")
        item2 = Item(name="Item 1", id="id-2")
        self.assertNotEqual(item1, item2)

    def test_item_not_equal_to_non_item(self):
        """Test that items are not equal to non-Item objects."""
        item = Item(name="Test")
        self.assertNotEqual(item, "Test")
        self.assertNotEqual(item, None)
        self.assertNotEqual(item, 123)

    def test_item_hash_by_id(self):
        """Test that items with same ID have same hash."""
        item1 = Item(name="Item 1", id="same-id")
        item2 = Item(name="Item 2", id="same-id")
        self.assertEqual(hash(item1), hash(item2))

    def test_item_usable_in_set(self):
        """Test that items can be used in a set."""
        item1 = Item(name="Item 1", id="id-1")
        item2 = Item(name="Item 2", id="id-2")
        item3 = Item(name="Item 3", id="id-1")  # Same ID as item1

        item_set = {item1, item2, item3}
        self.assertEqual(len(item_set), 2)

    def test_create_item_with_identifier(self):
        """Test creating an item with an identifier."""
        item = Item(name="Test Item", identifier="A-1")
        self.assertEqual(item.name, "Test Item")
        self.assertEqual(item.identifier, "A-1")

    def test_item_identifier_stripped(self):
        """Test that item identifier is stripped of whitespace."""
        item = Item(name="Test", identifier="  A-1  ")
        self.assertEqual(item.identifier, "A-1")

    def test_has_identifier_true(self):
        """Test has_identifier returns True when identifier is set."""
        item = Item(name="Test", identifier="A-1")
        self.assertTrue(item.has_identifier())

    def test_has_identifier_false_empty(self):
        """Test has_identifier returns False when identifier is empty."""
        item = Item(name="Test", identifier="")
        self.assertFalse(item.has_identifier())

    def test_has_identifier_false_default(self):
        """Test has_identifier returns False for default item."""
        item = Item(name="Test")
        self.assertFalse(item.has_identifier())

    def test_to_dict(self):
        """Test converting item to dictionary."""
        item = Item(name="Test", description="Desc", identifier="A-1", id="test-id")
        result = item.to_dict()

        self.assertEqual(result["id"], "test-id")
        self.assertEqual(result["name"], "Test")
        self.assertEqual(result["description"], "Desc")
        self.assertEqual(result["identifier"], "A-1")

    def test_from_dict_full(self):
        """Test creating item from dictionary with all fields."""
        data = {
            "id": "test-id",
            "name": "Test Item",
            "description": "Test Description",
            "identifier": "A-1",
        }
        item = Item.from_dict(data)

        self.assertEqual(item.id, "test-id")
        self.assertEqual(item.name, "Test Item")
        self.assertEqual(item.description, "Test Description")
        self.assertEqual(item.identifier, "A-1")

    def test_from_dict_minimal(self):
        """Test creating item from dictionary with only required fields."""
        data = {"name": "Test Item"}
        item = Item.from_dict(data)

        self.assertEqual(item.name, "Test Item")
        self.assertEqual(item.description, "")
        self.assertIsNotNone(item.id)

    def test_from_dict_missing_name_raises_error(self):
        """Test that from_dict raises KeyError if name is missing."""
        data = {"description": "No name"}
        with self.assertRaises(KeyError):
            Item.from_dict(data)

    def test_roundtrip_dict_conversion(self):
        """Test that to_dict and from_dict are inverses."""
        original = Item(name="Test", description="Desc", identifier="A-1", id="test-id")
        data = original.to_dict()
        restored = Item.from_dict(data)

        self.assertEqual(original, restored)
        self.assertEqual(original.name, restored.name)
        self.assertEqual(original.description, restored.description)
        self.assertEqual(original.identifier, restored.identifier)

    def test_from_dict_without_identifier(self):
        """Test creating item from dictionary without identifier field."""
        data = {
            "id": "test-id",
            "name": "Test Item",
            "description": "Test Description",
        }
        item = Item.from_dict(data)

        self.assertEqual(item.identifier, "")
        self.assertFalse(item.has_identifier())

    def test_category_default(self):
        """Test that category defaults to 'Default'."""
        item = Item(name="Test")
        self.assertEqual(item.category, "Default")

    def test_create_item_with_category(self):
        """Test creating an item with an explicit category."""
        item = Item(name="Test", category="Linear")
        self.assertEqual(item.category, "Linear")

    def test_to_dict_includes_category(self):
        """Test that to_dict includes the category field."""
        item = Item(name="Test", category="Tactile", id="test-id")
        result = item.to_dict()
        self.assertEqual(result["category"], "Tactile")

    def test_roundtrip_category(self):
        """Test that category survives to_dict/from_dict round-trip."""
        original = Item(name="Test", category="Clicky", id="test-id")
        restored = Item.from_dict(original.to_dict())
        self.assertEqual(restored.category, "Clicky")

    def test_from_dict_without_category(self):
        """Test that from_dict without a category key yields 'Default'."""
        data = {
            "id": "test-id",
            "name": "Test Item",
            "description": "Test Description",
            "identifier": "A-1",
        }
        item = Item.from_dict(data)
        self.assertEqual(item.category, "Default")

    def test_default_category_constant(self):
        """Test that the module constant matches the default field value."""
        self.assertEqual(DEFAULT_CATEGORY, "Default")
        self.assertEqual(Item(name="x").category, DEFAULT_CATEGORY)

    def test_whitespace_category_becomes_default(self):
        """Test that a whitespace-only category is normalized to the default."""
        item = Item(name="x", category="  ")
        self.assertEqual(item.category, "Default")

    def test_empty_category_becomes_default(self):
        """Test that an empty category is normalized to the default."""
        item = Item(name="x", category="")
        self.assertEqual(item.category, "Default")

    def test_category_is_stripped(self):
        """Test that surrounding whitespace is stripped from the category."""
        item = Item(name="x", category=" Linear ")
        self.assertEqual(item.category, "Linear")

    def test_from_dict_blank_category_becomes_default(self):
        """Test that from_dict normalizes a blank category to the default."""
        item = Item.from_dict({"name": "x", "category": "   "})
        self.assertEqual(item.category, "Default")


class TestItemLifecycle(unittest.TestCase):
    """Test cases for the active/retired item lifecycle."""

    def test_new_item_is_active(self):
        """Test that a freshly created item is active with no retirement data."""
        item = Item(name="Test")
        self.assertEqual(item.status, STATUS_ACTIVE)
        self.assertTrue(item.is_active())
        self.assertIsNone(item.retired_at)
        self.assertIsNone(item.replaced_by)

    def test_invalid_status_raises_error(self):
        """Test that an unknown status raises ValueError."""
        with self.assertRaises(ValueError):
            Item(name="Test", status="dormant")

    def test_retire_sets_status_and_timestamp(self):
        """Test that retire marks the item retired and records the time."""
        item = Item(name="Test", identifier="A-1")
        item.retire()

        self.assertEqual(item.status, STATUS_RETIRED)
        self.assertFalse(item.is_active())
        self.assertIsInstance(item.retired_at, datetime)

    def test_retire_clears_identifier(self):
        """Test that retiring an item frees its identifier."""
        item = Item(name="Test", identifier="A-1")
        item.retire()

        self.assertEqual(item.identifier, "")
        self.assertFalse(item.has_identifier())

    def test_retire_accepts_explicit_time(self):
        """Test that retire records the timestamp it is given."""
        when = datetime(2024, 5, 1, 9, 30, 0)
        item = Item(name="Test")
        item.retire(now=when)

        self.assertEqual(item.retired_at, when)

    def test_retire_records_replacement(self):
        """Test that retire stores the id of the replacing item."""
        item = Item(name="Test", identifier="A-1")
        item.retire(replaced_by="successor-id")

        self.assertEqual(item.replaced_by, "successor-id")

    def test_reactivate_restores_active_state(self):
        """Test that reactivate clears the retirement fields."""
        item = Item(name="Test", identifier="A-1")
        item.retire(replaced_by="successor-id")
        item.reactivate()

        self.assertEqual(item.status, STATUS_ACTIVE)
        self.assertTrue(item.is_active())
        self.assertIsNone(item.retired_at)
        self.assertIsNone(item.replaced_by)
        self.assertEqual(item.identifier, "")

    def test_reactivate_with_identifier(self):
        """Test that reactivate assigns the identifier it is given."""
        item = Item(name="Test", identifier="A-1")
        item.retire()
        item.reactivate("B-2")

        self.assertEqual(item.identifier, "B-2")

    def test_reactivate_strips_identifier(self):
        """Test that reactivate strips whitespace from the identifier."""
        item = Item(name="Test")
        item.retire()
        item.reactivate("  B-2  ")

        self.assertEqual(item.identifier, "B-2")

    def test_to_dict_includes_lifecycle_fields(self):
        """Test that to_dict writes status, retired_at and replaced_by."""
        item = Item(name="Test", id="test-id")
        result = item.to_dict()

        self.assertEqual(result["status"], STATUS_ACTIVE)
        self.assertIsNone(result["retired_at"])
        self.assertIsNone(result["replaced_by"])

    def test_to_dict_writes_retired_at_as_iso(self):
        """Test that a retired item serializes retired_at as ISO text."""
        item = Item(name="Test", id="test-id")
        item.retire(now=datetime(2024, 5, 1, 9, 30, 0), replaced_by="next-id")
        result = item.to_dict()

        self.assertEqual(result["status"], STATUS_RETIRED)
        self.assertEqual(result["retired_at"], "2024-05-01T09:30:00")
        self.assertEqual(result["replaced_by"], "next-id")
        self.assertEqual(result["identifier"], "")

    def test_from_dict_without_status_is_active(self):
        """Test that a dict without a status key yields an active item."""
        item = Item.from_dict({"name": "Test", "identifier": "A-1"})

        self.assertEqual(item.status, STATUS_ACTIVE)
        self.assertTrue(item.is_active())
        self.assertIsNone(item.retired_at)
        self.assertIsNone(item.replaced_by)

    def test_from_dict_parses_retired_at(self):
        """Test that from_dict parses retired_at from ISO text."""
        item = Item.from_dict({
            "name": "Test",
            "status": STATUS_RETIRED,
            "retired_at": "2024-05-01T09:30:00",
            "replaced_by": "next-id",
        })

        self.assertEqual(item.status, STATUS_RETIRED)
        self.assertEqual(item.retired_at, datetime(2024, 5, 1, 9, 30, 0))
        self.assertEqual(item.replaced_by, "next-id")

    def test_from_dict_null_retired_at(self):
        """Test that a null retired_at is read as None."""
        item = Item.from_dict({"name": "Test", "status": STATUS_ACTIVE, "retired_at": None})
        self.assertIsNone(item.retired_at)

    def test_from_dict_invalid_status_raises_error(self):
        """Test that from_dict rejects an unknown status."""
        with self.assertRaises(ValueError):
            Item.from_dict({"name": "Test", "status": "archived"})

    def test_retired_item_roundtrip(self):
        """Test that a retired item survives to_dict/from_dict unchanged."""
        original = Item(name="Test", description="Desc", category="Linear", id="test-id")
        original.retire(now=datetime(2024, 5, 1, 9, 30, 0), replaced_by="next-id")

        restored = Item.from_dict(original.to_dict())

        self.assertEqual(restored.status, original.status)
        self.assertEqual(restored.retired_at, original.retired_at)
        self.assertEqual(restored.replaced_by, original.replaced_by)
        self.assertEqual(restored.identifier, "")
        self.assertEqual(restored.category, "Linear")


if __name__ == "__main__":
    unittest.main()
