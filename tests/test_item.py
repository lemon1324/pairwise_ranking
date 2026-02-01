"""Unit tests for the Item model."""

import unittest
from src.models.item import Item


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


if __name__ == "__main__":
    unittest.main()
