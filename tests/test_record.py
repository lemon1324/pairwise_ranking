"""Unit tests for the Qt-free weighted win/loss record."""

import unittest
from datetime import datetime, timedelta

from src.app.record import UNKNOWN_OPPONENT_NAME, weighted_record
from src.models.item import Item
from src.models.vote import Vote


# Fixed clock so decayed weights are deterministic.
NOW = datetime(2026, 1, 1, 12, 0, 0)


def build_items() -> list[Item]:
    """
    Build four items, two of which deliberately share a name.

    Returns:
        list[Item]: The items, with stable ids "a" through "d".
    """
    return [
        Item(name="Alpha", id="a"),
        Item(name="Bravo", id="b"),
        Item(name="Shared", id="c"),
        Item(name="Shared", id="d"),
    ]


def vote(winner_id: str, loser_id: str, weight: float, days_ago: float = 0.0) -> Vote:
    """
    Build a vote at a fixed offset before the reference time.

    Args:
        winner_id: Id of the winning item.
        loser_id: Id of the losing item.
        weight: The vote weight.
        days_ago: How long before NOW the vote was cast.

    Returns:
        Vote: The constructed vote.
    """
    return Vote(
        winner_id=winner_id,
        loser_id=loser_id,
        weight=weight,
        timestamp=NOW - timedelta(days=days_ago),
    )


class TestWeightedRecordSplit(unittest.TestCase):
    """Test cases for how wins and losses are separated."""

    def setUp(self):
        """Set up test fixtures."""
        self.items = build_items()

    def test_item_with_no_votes_has_empty_record(self):
        """Test that an item that has never been compared has no records."""
        record = weighted_record("a", [], self.items, reference_time=NOW)
        self.assertEqual(record.wins, [])
        self.assertEqual(record.losses, [])

    def test_wins_and_losses_are_separated(self):
        """Test that a win and a loss land in their own lists."""
        votes = [vote("a", "b", 2.0), vote("c", "a", 3.0)]

        record = weighted_record("a", votes, self.items, reference_time=NOW)

        self.assertEqual([r.opponent_id for r in record.wins], ["b"])
        self.assertEqual([r.opponent_id for r in record.losses], ["c"])

    def test_votes_not_involving_the_item_are_ignored(self):
        """Test that other items' votes do not enter the record."""
        votes = [vote("b", "c", 2.0), vote("c", "d", 1.0)]

        record = weighted_record("a", votes, self.items, reference_time=NOW)

        self.assertEqual(record.wins, [])
        self.assertEqual(record.losses, [])

    def test_repeated_opponent_weights_are_summed(self):
        """Test that several votes against one opponent become one record."""
        votes = [vote("a", "b", 2.0), vote("a", "b", 3.0), vote("a", "b", 1.0)]

        record = weighted_record("a", votes, self.items, reference_time=NOW)

        self.assertEqual(len(record.wins), 1)
        self.assertEqual(record.wins[0].weight_raw, 6.0)


class TestWeightedRecordIdKeying(unittest.TestCase):
    """Test cases for keying the record by opponent id rather than name."""

    def setUp(self):
        """Set up test fixtures."""
        self.items = build_items()

    def test_same_named_opponents_stay_separate(self):
        """Test that two opponents sharing a name keep their own records."""
        votes = [vote("a", "c", 2.0), vote("a", "d", 3.0)]

        record = weighted_record("a", votes, self.items, reference_time=NOW)

        self.assertEqual([r.opponent_id for r in record.wins], ["c", "d"])
        self.assertEqual([r.name for r in record.wins], ["Shared", "Shared"])
        self.assertEqual([r.weight_raw for r in record.wins], [2.0, 3.0])

    def test_records_are_ordered_by_name_then_id(self):
        """Test that records come back alphabetically, ties broken by id."""
        votes = [vote("a", "d", 1.0), vote("a", "b", 1.0), vote("a", "c", 1.0)]

        record = weighted_record("a", votes, self.items, reference_time=NOW)

        self.assertEqual([r.opponent_id for r in record.wins], ["b", "c", "d"])

    def test_deleted_opponent_is_named_unknown(self):
        """Test that an opponent the project no longer holds has a fallback name."""
        votes = [vote("a", "gone", 2.0)]

        record = weighted_record("a", votes, self.items, reference_time=NOW)

        self.assertEqual(record.wins[0].opponent_id, "gone")
        self.assertEqual(record.wins[0].name, UNKNOWN_OPPONENT_NAME)

    def test_retired_opponent_keeps_its_name(self):
        """Test that retiring an opponent does not hide it from the record."""
        self.items[1].retire()
        votes = [vote("a", "b", 2.0)]

        record = weighted_record("a", votes, self.items, reference_time=NOW)

        self.assertEqual(record.wins[0].opponent_id, "b")
        self.assertEqual(record.wins[0].name, "Bravo")

    def test_a_retired_item_still_has_a_record(self):
        """Test that a retired item's own history is still reported."""
        self.items[0].retire()
        votes = [vote("a", "b", 2.0), vote("c", "a", 1.0)]

        record = weighted_record("a", votes, self.items, reference_time=NOW)

        self.assertEqual([r.opponent_id for r in record.wins], ["b"])
        self.assertEqual([r.opponent_id for r in record.losses], ["c"])

    def test_an_item_the_project_does_not_hold_has_an_empty_record(self):
        """Test that asking about an unknown id is an empty record, not an error."""
        votes = [vote("a", "b", 2.0)]

        record = weighted_record("nope", votes, self.items, reference_time=NOW)

        self.assertEqual(record.wins, [])
        self.assertEqual(record.losses, [])

    def test_one_opponent_can_appear_on_both_sides(self):
        """Test that an opponent beaten once and lost to once is in both lists."""
        votes = [vote("a", "b", 2.0), vote("b", "a", 3.0)]

        record = weighted_record("a", votes, self.items, reference_time=NOW)

        self.assertEqual([r.opponent_id for r in record.wins], ["b"])
        self.assertEqual([r.opponent_id for r in record.losses], ["b"])
        self.assertEqual(record.wins[0].weight_raw, 2.0)
        self.assertEqual(record.losses[0].weight_raw, 3.0)


class TestWeightedRecordDecay(unittest.TestCase):
    """Test cases for the raw and decayed weightings."""

    def setUp(self):
        """Set up test fixtures."""
        self.items = build_items()

    def test_without_decay_the_two_weightings_match(self):
        """Test that a zero half-life leaves the decayed weight equal to the raw one."""
        votes = [vote("a", "b", 2.0, days_ago=30.0)]

        record = weighted_record(
            "a", votes, self.items, decay_timescale_days=0.0, reference_time=NOW
        )

        self.assertEqual(record.wins[0].weight_raw, 2.0)
        self.assertEqual(record.wins[0].weight_decayed, 2.0)

    def test_one_half_life_halves_the_decayed_weight(self):
        """Test that a vote one half-life old counts half as much when decayed."""
        votes = [vote("a", "b", 2.0, days_ago=30.0)]

        record = weighted_record(
            "a", votes, self.items, decay_timescale_days=30.0, reference_time=NOW
        )

        self.assertEqual(record.wins[0].weight_raw, 2.0)
        self.assertAlmostEqual(record.wins[0].weight_decayed, 1.0)

    def test_decay_applies_to_losses_too(self):
        """Test that losses carry both weightings as well."""
        votes = [vote("b", "a", 4.0, days_ago=60.0)]

        record = weighted_record(
            "a", votes, self.items, decay_timescale_days=30.0, reference_time=NOW
        )

        self.assertEqual(record.losses[0].weight_raw, 4.0)
        self.assertAlmostEqual(record.losses[0].weight_decayed, 1.0)

    def test_decayed_weights_sum_per_opponent(self):
        """Test that each vote decays on its own before the sum is taken."""
        votes = [vote("a", "b", 2.0, days_ago=30.0), vote("a", "b", 2.0)]

        record = weighted_record(
            "a", votes, self.items, decay_timescale_days=30.0, reference_time=NOW
        )

        self.assertEqual(record.wins[0].weight_raw, 4.0)
        self.assertAlmostEqual(record.wins[0].weight_decayed, 3.0)

    def test_a_negative_half_life_means_no_decay(self):
        """Test that a nonsense half-life leaves the weights alone."""
        votes = [vote("a", "b", 2.0, days_ago=30.0)]

        record = weighted_record(
            "a", votes, self.items, decay_timescale_days=-5.0, reference_time=NOW
        )

        self.assertEqual(record.wins[0].weight_decayed, 2.0)

    def test_the_reference_time_defaults_to_now(self):
        """Test that the clock can be left to the caller's own."""
        votes = [vote("a", "b", 2.0)]

        record = weighted_record("a", votes, self.items)

        self.assertEqual(record.wins[0].weight_raw, 2.0)
        self.assertEqual(record.wins[0].weight_decayed, 2.0)

    def test_the_reference_time_is_what_decay_is_measured_from(self):
        """Test that moving the reference time changes the decayed weight."""
        votes = [vote("a", "b", 2.0, days_ago=30.0)]

        at_vote_time = weighted_record(
            "a",
            votes,
            self.items,
            decay_timescale_days=30.0,
            reference_time=NOW - timedelta(days=30.0),
        )

        self.assertAlmostEqual(at_vote_time.wins[0].weight_decayed, 2.0)


if __name__ == "__main__":
    unittest.main()
