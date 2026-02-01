"""Unit tests for the Vote model."""

import unittest
from datetime import datetime, timedelta
from src.models.vote import Vote, VOTE_WEIGHTS


class TestVote(unittest.TestCase):
    """Test cases for the Vote dataclass."""

    def test_create_vote_basic(self):
        """Test creating a basic vote."""
        vote = Vote(winner_id="item1", loser_id="item2", weight=2.0)
        self.assertEqual(vote.winner_id, "item1")
        self.assertEqual(vote.loser_id, "item2")
        self.assertEqual(vote.weight, 2.0)
        self.assertIsNotNone(vote.id)
        self.assertIsNotNone(vote.timestamp)

    def test_create_vote_with_custom_timestamp(self):
        """Test creating a vote with a custom timestamp."""
        ts = datetime(2024, 1, 15, 12, 0, 0)
        vote = Vote(winner_id="a", loser_id="b", weight=1.0, timestamp=ts)
        self.assertEqual(vote.timestamp, ts)

    def test_create_vote_with_custom_id(self):
        """Test creating a vote with a custom ID."""
        vote = Vote(winner_id="a", loser_id="b", weight=1.0, id="custom-id")
        self.assertEqual(vote.id, "custom-id")

    def test_same_winner_loser_raises_error(self):
        """Test that winner and loser cannot be the same item."""
        with self.assertRaises(ValueError):
            Vote(winner_id="item1", loser_id="item1", weight=1.0)

    def test_zero_weight_raises_error(self):
        """Test that zero weight raises ValueError."""
        with self.assertRaises(ValueError):
            Vote(winner_id="a", loser_id="b", weight=0.0)

    def test_negative_weight_raises_error(self):
        """Test that negative weight raises ValueError."""
        with self.assertRaises(ValueError):
            Vote(winner_id="a", loser_id="b", weight=-1.0)

    def test_vote_equality_by_id(self):
        """Test that votes are equal if they have the same ID."""
        vote1 = Vote(winner_id="a", loser_id="b", weight=1.0, id="same-id")
        vote2 = Vote(winner_id="c", loser_id="d", weight=2.0, id="same-id")
        self.assertEqual(vote1, vote2)

    def test_vote_inequality_by_id(self):
        """Test that votes are not equal if they have different IDs."""
        vote1 = Vote(winner_id="a", loser_id="b", weight=1.0, id="id-1")
        vote2 = Vote(winner_id="a", loser_id="b", weight=1.0, id="id-2")
        self.assertNotEqual(vote1, vote2)

    def test_vote_not_equal_to_non_vote(self):
        """Test that votes are not equal to non-Vote objects."""
        vote = Vote(winner_id="a", loser_id="b", weight=1.0)
        self.assertNotEqual(vote, "test")
        self.assertNotEqual(vote, None)

    def test_vote_hash_by_id(self):
        """Test that votes with same ID have same hash."""
        vote1 = Vote(winner_id="a", loser_id="b", weight=1.0, id="same-id")
        vote2 = Vote(winner_id="c", loser_id="d", weight=2.0, id="same-id")
        self.assertEqual(hash(vote1), hash(vote2))

    def test_involves_item_winner(self):
        """Test involves_item returns True for winner."""
        vote = Vote(winner_id="item1", loser_id="item2", weight=1.0)
        self.assertTrue(vote.involves_item("item1"))

    def test_involves_item_loser(self):
        """Test involves_item returns True for loser."""
        vote = Vote(winner_id="item1", loser_id="item2", weight=1.0)
        self.assertTrue(vote.involves_item("item2"))

    def test_involves_item_other(self):
        """Test involves_item returns False for uninvolved item."""
        vote = Vote(winner_id="item1", loser_id="item2", weight=1.0)
        self.assertFalse(vote.involves_item("item3"))

    def test_get_pair(self):
        """Test get_pair returns (winner_id, loser_id)."""
        vote = Vote(winner_id="a", loser_id="b", weight=1.0)
        self.assertEqual(vote.get_pair(), ("a", "b"))

    def test_get_pair_unordered(self):
        """Test get_pair_unordered returns frozenset of both IDs."""
        vote = Vote(winner_id="a", loser_id="b", weight=1.0)
        self.assertEqual(vote.get_pair_unordered(), frozenset(["a", "b"]))

    def test_get_pair_unordered_matches_reverse(self):
        """Test get_pair_unordered is same regardless of winner/loser order."""
        vote1 = Vote(winner_id="a", loser_id="b", weight=1.0)
        vote2 = Vote(winner_id="b", loser_id="a", weight=1.0)
        self.assertEqual(vote1.get_pair_unordered(), vote2.get_pair_unordered())


class TestVoteDecay(unittest.TestCase):
    """Test cases for vote weight decay."""

    def test_no_decay_for_new_vote(self):
        """Test that a brand new vote has no decay."""
        vote = Vote(winner_id="a", loser_id="b", weight=2.0)
        decayed = vote.get_decayed_weight(30.0)
        # Should be very close to original weight
        self.assertAlmostEqual(decayed, 2.0, places=2)

    def test_half_decay_at_timescale(self):
        """Test that weight is halved after exactly decay_timescale_days."""
        now = datetime.now()
        vote_time = now - timedelta(days=30)
        vote = Vote(winner_id="a", loser_id="b", weight=2.0, timestamp=vote_time)

        decayed = vote.get_decayed_weight(30.0, reference_time=now)
        self.assertAlmostEqual(decayed, 1.0, places=5)

    def test_quarter_decay_at_double_timescale(self):
        """Test that weight is quartered after 2x decay_timescale_days."""
        now = datetime.now()
        vote_time = now - timedelta(days=60)
        vote = Vote(winner_id="a", loser_id="b", weight=2.0, timestamp=vote_time)

        decayed = vote.get_decayed_weight(30.0, reference_time=now)
        self.assertAlmostEqual(decayed, 0.5, places=5)

    def test_zero_timescale_returns_original(self):
        """Test that zero timescale returns original weight (no decay)."""
        now = datetime.now()
        vote_time = now - timedelta(days=100)
        vote = Vote(winner_id="a", loser_id="b", weight=2.0, timestamp=vote_time)

        decayed = vote.get_decayed_weight(0.0, reference_time=now)
        self.assertEqual(decayed, 2.0)

    def test_negative_timescale_returns_original(self):
        """Test that negative timescale returns original weight."""
        now = datetime.now()
        vote_time = now - timedelta(days=100)
        vote = Vote(winner_id="a", loser_id="b", weight=2.0, timestamp=vote_time)

        decayed = vote.get_decayed_weight(-10.0, reference_time=now)
        self.assertEqual(decayed, 2.0)

    def test_future_vote_no_decay(self):
        """Test that a vote in the future has no decay."""
        now = datetime.now()
        vote_time = now + timedelta(days=10)
        vote = Vote(winner_id="a", loser_id="b", weight=2.0, timestamp=vote_time)

        decayed = vote.get_decayed_weight(30.0, reference_time=now)
        self.assertEqual(decayed, 2.0)


class TestVoteSerialization(unittest.TestCase):
    """Test cases for vote serialization."""

    def test_to_dict(self):
        """Test converting vote to dictionary."""
        ts = datetime(2024, 1, 15, 12, 30, 45)
        vote = Vote(
            winner_id="item1",
            loser_id="item2",
            weight=2.0,
            timestamp=ts,
            id="vote-id",
        )
        result = vote.to_dict()

        self.assertEqual(result["id"], "vote-id")
        self.assertEqual(result["winner_id"], "item1")
        self.assertEqual(result["loser_id"], "item2")
        self.assertEqual(result["weight"], 2.0)
        self.assertEqual(result["timestamp"], "2024-01-15T12:30:45")

    def test_from_dict_full(self):
        """Test creating vote from dictionary with all fields."""
        data = {
            "id": "vote-id",
            "winner_id": "item1",
            "loser_id": "item2",
            "weight": 2.0,
            "timestamp": "2024-01-15T12:30:45",
        }
        vote = Vote.from_dict(data)

        self.assertEqual(vote.id, "vote-id")
        self.assertEqual(vote.winner_id, "item1")
        self.assertEqual(vote.loser_id, "item2")
        self.assertEqual(vote.weight, 2.0)
        self.assertEqual(vote.timestamp, datetime(2024, 1, 15, 12, 30, 45))

    def test_from_dict_minimal(self):
        """Test creating vote from dictionary with only required fields."""
        data = {
            "winner_id": "item1",
            "loser_id": "item2",
            "weight": 1.0,
        }
        vote = Vote.from_dict(data)

        self.assertEqual(vote.winner_id, "item1")
        self.assertEqual(vote.loser_id, "item2")
        self.assertEqual(vote.weight, 1.0)
        self.assertIsNotNone(vote.id)
        self.assertIsNotNone(vote.timestamp)

    def test_from_dict_weight_as_string(self):
        """Test that from_dict converts string weight to float."""
        data = {
            "winner_id": "item1",
            "loser_id": "item2",
            "weight": "2.0",
        }
        vote = Vote.from_dict(data)
        self.assertEqual(vote.weight, 2.0)
        self.assertIsInstance(vote.weight, float)

    def test_roundtrip_dict_conversion(self):
        """Test that to_dict and from_dict are inverses."""
        ts = datetime(2024, 1, 15, 12, 30, 45)
        original = Vote(
            winner_id="item1",
            loser_id="item2",
            weight=2.0,
            timestamp=ts,
            id="vote-id",
        )
        data = original.to_dict()
        restored = Vote.from_dict(data)

        self.assertEqual(original.id, restored.id)
        self.assertEqual(original.winner_id, restored.winner_id)
        self.assertEqual(original.loser_id, restored.loser_id)
        self.assertEqual(original.weight, restored.weight)
        self.assertEqual(original.timestamp, restored.timestamp)


class TestVoteWeights(unittest.TestCase):
    """Test cases for vote weight constants."""

    def test_vote_weights_defined(self):
        """Test that expected vote weights are defined."""
        self.assertIn("much_better", VOTE_WEIGHTS)
        self.assertIn("better", VOTE_WEIGHTS)
        self.assertIn("slightly_better", VOTE_WEIGHTS)

    def test_vote_weight_values(self):
        """Test that vote weights have correct values."""
        self.assertEqual(VOTE_WEIGHTS["much_better"], 3.0)
        self.assertEqual(VOTE_WEIGHTS["better"], 2.0)
        self.assertEqual(VOTE_WEIGHTS["slightly_better"], 1.0)


if __name__ == "__main__":
    unittest.main()
