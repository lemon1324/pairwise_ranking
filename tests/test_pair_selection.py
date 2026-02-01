"""Unit tests for the PairSelector class."""

import unittest
from datetime import datetime, timedelta

from src.models.item import Item
from src.models.vote import Vote
from src.models.ranking import PairSelector, BradleyTerryModel, RankingResult
from src.models.settings import Settings


class TestPairSelectorBasic(unittest.TestCase):
    """Basic tests for PairSelector."""

    def test_no_items_returns_none(self):
        """Test that selector returns None with no items."""
        selector = PairSelector([], [], Settings())
        result = selector.select_pair()
        self.assertIsNone(result)

    def test_single_item_returns_none(self):
        """Test that selector returns None with single item."""
        items = [Item(name="Only Item", id="a")]
        selector = PairSelector(items, [], Settings())
        result = selector.select_pair()
        self.assertIsNone(result)

    def test_two_items_returns_pair(self):
        """Test that selector returns the only possible pair."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
        ]
        selector = PairSelector(items, [], Settings())
        result = selector.select_pair()

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        ids = {result[0].id, result[1].id}
        self.assertEqual(ids, {"a", "b"})

    def test_returns_tuple_of_items(self):
        """Test that selector returns tuple of Item objects."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
            Item(name="Item C", id="c"),
        ]
        selector = PairSelector(items, [], Settings())
        result = selector.select_pair()

        self.assertIsInstance(result, tuple)
        self.assertIsInstance(result[0], Item)
        self.assertIsInstance(result[1], Item)


class TestPairSelectorUncomparedPriority(unittest.TestCase):
    """Tests for uncompared item priority."""

    def test_prefers_uncompared_items(self):
        """Test that selector prefers items with no comparisons."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
            Item(name="Item C", id="c"),
        ]

        # A and B have been compared, C has not
        votes = [
            Vote(winner_id="a", loser_id="b", weight=2.0),
            Vote(winner_id="a", loser_id="b", weight=2.0),
        ]

        settings = Settings(weight_uncompared=5.0, weight_uncertainty=0.0)
        selector = PairSelector(items, votes, settings)
        result = selector.select_pair()

        # Result should include C (uncompared)
        result_ids = {result[0].id, result[1].id}
        self.assertIn("c", result_ids)

    def test_prefers_uncompared_pairs(self):
        """Test that selector prefers pairs that haven't been compared."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
            Item(name="Item C", id="c"),
        ]

        # A-B compared many times, A-C and B-C not compared
        votes = [
            Vote(winner_id="a", loser_id="b", weight=2.0),
            Vote(winner_id="a", loser_id="b", weight=2.0),
            Vote(winner_id="a", loser_id="b", weight=2.0),
        ]

        settings = Settings(weight_uncompared=5.0, weight_uncertainty=0.0)
        selector = PairSelector(items, votes, settings)
        result = selector.select_pair()

        # Result should NOT be A-B (already compared)
        result_ids = {result[0].id, result[1].id}
        self.assertNotEqual(result_ids, {"a", "b"})


class TestPairSelectorConnectivity(unittest.TestCase):
    """Tests for connectivity-based selection."""

    def test_connects_disconnected_components(self):
        """Test that selector prefers pairs connecting disconnected components."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
            Item(name="Item C", id="c"),
            Item(name="Item D", id="d"),
        ]

        # Component 1: A-B compared
        # Component 2: C-D compared
        votes = [
            Vote(winner_id="a", loser_id="b", weight=2.0),
            Vote(winner_id="c", loser_id="d", weight=2.0),
        ]

        settings = Settings(
            weight_connectivity=10.0,
            weight_uncertainty=0.0,
            weight_uncompared=0.1,  # Low to not interfere
        )
        selector = PairSelector(items, votes, settings)
        result = selector.select_pair()

        # Result should connect the two components
        result_ids = {result[0].id, result[1].id}

        # Should be a cross-component pair
        component1 = {"a", "b"}
        component2 = {"c", "d"}

        has_from_c1 = len(result_ids & component1) > 0
        has_from_c2 = len(result_ids & component2) > 0

        self.assertTrue(has_from_c1 and has_from_c2)


class TestPairSelectorFreshness(unittest.TestCase):
    """Tests for freshness-based selection."""

    def test_prefers_stale_pairs(self):
        """Test that selector prefers pairs with old votes."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
            Item(name="Item C", id="c"),
        ]

        now = datetime.now()
        old_time = now - timedelta(days=90)

        # A-B compared recently, A-C compared long ago
        votes = [
            Vote(winner_id="a", loser_id="b", weight=2.0, timestamp=now),
            Vote(winner_id="a", loser_id="c", weight=2.0, timestamp=old_time),
        ]

        settings = Settings(
            weight_freshness=10.0,
            weight_uncertainty=0.0,
            weight_uncompared=0.1,
            weight_connectivity=0.0,
            decay_timescale_days=30.0,
        )
        selector = PairSelector(items, votes, settings)
        result = selector.select_pair()

        # Should prefer A-C (stale) or B-C (never compared)
        result_ids = {result[0].id, result[1].id}
        # A-B should be less preferred due to being recent
        # Either A-C (stale) or B-C (uncompared) is good
        self.assertTrue("c" in result_ids or result_ids != {"a", "b"})


class TestPairSelectorUncertainty(unittest.TestCase):
    """Tests for uncertainty-based selection."""

    def test_prefers_high_uncertainty_items(self):
        """Test that selector prefers items with high estimation uncertainty (SE)."""
        items = [
            Item(name="Well-Known", id="known"),
            Item(name="Unknown A", id="unknown_a"),
            Item(name="Unknown B", id="unknown_b"),
        ]

        # known has many comparisons, unknowns have few
        votes = [
            Vote(winner_id="known", loser_id="unknown_a", weight=1.0),
            Vote(winner_id="known", loser_id="unknown_a", weight=1.0),
            Vote(winner_id="known", loser_id="unknown_a", weight=1.0),
            Vote(winner_id="known", loser_id="unknown_a", weight=1.0),
            Vote(winner_id="known", loser_id="unknown_b", weight=1.0),
            Vote(winner_id="known", loser_id="unknown_b", weight=1.0),
            Vote(winner_id="known", loser_id="unknown_b", weight=1.0),
            Vote(winner_id="known", loser_id="unknown_b", weight=1.0),
        ]
        # known: 8 comparisons, unknown_a: 4 comparisons, unknown_b: 4 comparisons

        # Compute rankings
        model = BradleyTerryModel(items)
        model.add_votes(votes)
        rankings = model.compute_rankings()

        settings = Settings(
            weight_uncertainty=10.0,
            weight_connectivity=0.0,
            weight_uncompared=0.0,
            weight_freshness=0.0,
        )
        selector = PairSelector(items, votes, settings)
        result = selector.select_pair(rankings)

        # With SE-based uncertainty, should prefer comparing the two unknowns
        # (highest combined SE) over pairs involving well-known item
        result_ids = {result[0].id, result[1].id}
        self.assertEqual(result_ids, {"unknown_a", "unknown_b"})


class TestPairSelectorTopTier(unittest.TestCase):
    """Tests for top-tier mode."""

    def test_top_tier_mode_prefers_top_items(self):
        """Test that top-tier mode prefers comparisons with top items."""
        items = [Item(name=f"Item {i}", id=str(i)) for i in range(10)]

        # Create clear ranking: 0 > 1 > 2 > ... > 9
        votes = []
        for i in range(9):
            for _ in range(3):
                votes.append(Vote(winner_id=str(i), loser_id=str(i + 1), weight=2.0))

        model = BradleyTerryModel(items)
        model.add_votes(votes)
        rankings = model.compute_rankings()

        settings = Settings(
            top_tier_mode=True,
            top_tier_count=3,
            top_tier_weight=10.0,
            weight_uncertainty=0.1,
            weight_connectivity=0.0,
            weight_uncompared=0.0,
        )
        selector = PairSelector(items, votes, settings)
        result = selector.select_pair(rankings)

        # Should involve top-tier items (0, 1, or 2)
        result_ids = {result[0].id, result[1].id}
        top_tier_ids = {"0", "1", "2"}

        has_top_tier = len(result_ids & top_tier_ids) > 0
        self.assertTrue(has_top_tier)


class TestPairSelectorStats(unittest.TestCase):
    """Tests for comparison statistics."""

    def test_stats_no_votes(self):
        """Test statistics with no votes."""
        items = [Item(name=f"Item {i}", id=str(i)) for i in range(5)]
        selector = PairSelector(items, [], Settings())

        stats = selector.get_comparison_stats()

        self.assertEqual(stats["total_items"], 5)
        self.assertEqual(stats["total_possible_pairs"], 10)  # 5 choose 2
        self.assertEqual(stats["compared_pairs"], 0)
        self.assertEqual(stats["uncompared_pairs"], 10)
        self.assertEqual(stats["total_votes"], 0)
        self.assertEqual(stats["uncompared_items"], 5)

    def test_stats_with_votes(self):
        """Test statistics with some votes."""
        items = [
            Item(name="A", id="a"),
            Item(name="B", id="b"),
            Item(name="C", id="c"),
        ]

        votes = [
            Vote(winner_id="a", loser_id="b", weight=2.0),
            Vote(winner_id="a", loser_id="b", weight=2.0),
            Vote(winner_id="b", loser_id="c", weight=2.0),
        ]

        selector = PairSelector(items, votes, Settings())
        stats = selector.get_comparison_stats()

        self.assertEqual(stats["total_items"], 3)
        self.assertEqual(stats["total_possible_pairs"], 3)  # 3 choose 2
        self.assertEqual(stats["compared_pairs"], 2)  # a-b and b-c
        self.assertEqual(stats["uncompared_pairs"], 1)  # a-c
        self.assertEqual(stats["total_votes"], 3)
        self.assertEqual(stats["uncompared_items"], 0)  # all items have votes


if __name__ == "__main__":
    unittest.main()
