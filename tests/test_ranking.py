"""Unit tests for the Bradley-Terry ranking model."""

import random
import unittest
from datetime import datetime, timedelta

import numpy as np

from src.models.item import Item
from src.models.vote import Vote
from src.models.ranking import BradleyTerryModel, RankingResult


def fisher_information_reference(W: np.ndarray, pi: np.ndarray) -> np.ndarray:
    """
    Straightforward loop implementation of the Fisher Information matrix.

    Kept here as an independent reference for the vectorized implementation in
    :meth:`BradleyTerryModel._compute_fisher_information`.

    Args:
        W: Regularized win matrix.
        pi: Array of strength parameters.

    Returns:
        np.ndarray: Fisher Information matrix (n x n).
    """
    n = len(pi)
    info = np.zeros((n, n), dtype=np.float64)

    for i in range(n):
        for j in range(n):
            if i == j:
                for k in range(n):
                    if k != i:
                        n_ik = W[i, k] + W[k, i]
                        pq = pi[i] * pi[k] / (pi[i] + pi[k]) ** 2
                        info[i, i] += n_ik * pq
            else:
                n_ij = W[i, j] + W[j, i]
                pq = pi[i] * pi[j] / (pi[i] + pi[j]) ** 2
                info[i, j] = -n_ij * pq

    return info


class TestBradleyTerryModelBasic(unittest.TestCase):
    """Basic tests for BradleyTerryModel."""

    def test_empty_items(self):
        """Test model with no items returns empty results."""
        model = BradleyTerryModel([])
        results = model.compute_rankings()
        self.assertEqual(results, [])

    def test_single_item(self):
        """Test model with single item returns that item ranked first."""
        items = [Item(name="Only Item", id="item1")]
        model = BradleyTerryModel(items)
        results = model.compute_rankings()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].rank, 1)
        self.assertEqual(results[0].elo_rating, 1500.0)

    def test_two_items_no_votes(self):
        """Test model with two items and no votes gives equal ratings."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
        ]
        model = BradleyTerryModel(items)
        results = model.compute_rankings()

        self.assertEqual(len(results), 2)
        # With regularization only, ratings should be similar
        self.assertAlmostEqual(results[0].elo_rating, results[1].elo_rating, delta=10)

    def test_n_items_property(self):
        """Test n_items property."""
        items = [Item(name=f"Item {i}", id=str(i)) for i in range(5)]
        model = BradleyTerryModel(items)
        self.assertEqual(model.n_items, 5)


class TestBradleyTerryModelRanking(unittest.TestCase):
    """Tests for ranking computation."""

    def setUp(self):
        """Set up test fixtures."""
        self.items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
            Item(name="Item C", id="c"),
        ]

    def test_clear_winner(self):
        """Test that item with all wins is ranked first."""
        model = BradleyTerryModel(self.items)

        # A beats B and C multiple times
        votes = [
            Vote(winner_id="a", loser_id="b", weight=3.0),
            Vote(winner_id="a", loser_id="b", weight=3.0),
            Vote(winner_id="a", loser_id="c", weight=3.0),
            Vote(winner_id="a", loser_id="c", weight=3.0),
            Vote(winner_id="b", loser_id="c", weight=2.0),
        ]
        model.add_votes(votes)
        results = model.compute_rankings()

        # A should be ranked first
        self.assertEqual(results[0].item.id, "a")
        self.assertEqual(results[0].rank, 1)

    def test_clear_loser(self):
        """Test that item with all losses is ranked last."""
        model = BradleyTerryModel(self.items)

        # C loses to everyone
        votes = [
            Vote(winner_id="a", loser_id="c", weight=3.0),
            Vote(winner_id="a", loser_id="c", weight=3.0),
            Vote(winner_id="b", loser_id="c", weight=3.0),
            Vote(winner_id="b", loser_id="c", weight=3.0),
            Vote(winner_id="a", loser_id="b", weight=1.0),
        ]
        model.add_votes(votes)
        results = model.compute_rankings()

        # C should be ranked last
        last_result = results[-1]
        self.assertEqual(last_result.item.id, "c")
        self.assertEqual(last_result.rank, 3)

    def test_vote_weight_matters(self):
        """Test that higher vote weights have more impact."""
        model = BradleyTerryModel(self.items[:2])  # Just A and B

        # A beats B once strongly, B beats A twice weakly
        votes = [
            Vote(winner_id="a", loser_id="b", weight=3.0),  # A much better
            Vote(winner_id="b", loser_id="a", weight=1.0),  # B slightly better
            Vote(winner_id="b", loser_id="a", weight=1.0),  # B slightly better
        ]
        model.add_votes(votes)
        results = model.compute_rankings()

        # Total weight: A wins 3.0, B wins 2.0
        # A should be ranked higher
        self.assertEqual(results[0].item.id, "a")

    def test_transitive_ranking(self):
        """Test that A > B > C implies A > C in rankings."""
        model = BradleyTerryModel(self.items)

        votes = [
            Vote(winner_id="a", loser_id="b", weight=2.0),
            Vote(winner_id="a", loser_id="b", weight=2.0),
            Vote(winner_id="b", loser_id="c", weight=2.0),
            Vote(winner_id="b", loser_id="c", weight=2.0),
        ]
        model.add_votes(votes)
        results = model.compute_rankings()

        # Order should be A, B, C
        self.assertEqual(results[0].item.id, "a")
        self.assertEqual(results[1].item.id, "b")
        self.assertEqual(results[2].item.id, "c")

    def test_elo_ratings_centered(self):
        """Test that average ELO rating is approximately 1500."""
        items = [Item(name=f"Item {i}", id=str(i)) for i in range(5)]
        model = BradleyTerryModel(items)

        # Add some random-ish votes
        votes = [
            Vote(winner_id="0", loser_id="1", weight=2.0),
            Vote(winner_id="1", loser_id="2", weight=2.0),
            Vote(winner_id="2", loser_id="3", weight=2.0),
            Vote(winner_id="3", loser_id="4", weight=2.0),
            Vote(winner_id="0", loser_id="4", weight=2.0),
        ]
        model.add_votes(votes)
        results = model.compute_rankings()

        avg_elo = sum(r.elo_rating for r in results) / len(results)
        self.assertAlmostEqual(avg_elo, 1500.0, delta=1.0)


class TestBradleyTerryModelDecay(unittest.TestCase):
    """Tests for vote decay."""

    def test_decay_reduces_old_vote_weight(self):
        """Test that old votes have less impact with decay enabled."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
        ]

        now = datetime.now()
        old_time = now - timedelta(days=60)

        # Old vote: A beats B strongly
        old_vote = Vote(winner_id="a", loser_id="b", weight=3.0, timestamp=old_time)
        # New vote: B beats A slightly
        new_vote = Vote(winner_id="b", loser_id="a", weight=1.0, timestamp=now)

        # Without decay: A should win (3.0 vs 1.0)
        model_no_decay = BradleyTerryModel(items)
        model_no_decay.add_votes([old_vote, new_vote], decay_timescale_days=0)
        results_no_decay = model_no_decay.compute_rankings()

        # With decay (30 day half-life): old vote decayed to ~0.75
        model_decay = BradleyTerryModel(items)
        model_decay.add_votes([old_vote, new_vote], decay_timescale_days=30, reference_time=now)
        results_decay = model_decay.compute_rankings()

        # Without decay, A wins
        self.assertEqual(results_no_decay[0].item.id, "a")

        # With decay, B might win or ratings closer
        # The decayed weight for A is 3.0 * 0.25 = 0.75 (60 days = 2 half-lives)
        # So B's total is 1.0 vs A's 0.75
        self.assertEqual(results_decay[0].item.id, "b")


class TestBradleyTerryModelProbability(unittest.TestCase):
    """Tests for win probability calculation."""

    def test_equal_items_50_percent(self):
        """Test that equal items have 50% win probability."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
        ]
        model = BradleyTerryModel(items)
        model.compute_rankings()

        prob = model.get_win_probability("a", "b")
        self.assertAlmostEqual(prob, 0.5, delta=0.01)

    def test_stronger_item_higher_probability(self):
        """Test that stronger item has higher win probability."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
        ]
        model = BradleyTerryModel(items)

        votes = [
            Vote(winner_id="a", loser_id="b", weight=3.0),
            Vote(winner_id="a", loser_id="b", weight=3.0),
            Vote(winner_id="a", loser_id="b", weight=3.0),
        ]
        model.add_votes(votes)
        model.compute_rankings()

        prob_a_beats_b = model.get_win_probability("a", "b")
        self.assertGreater(prob_a_beats_b, 0.5)

        prob_b_beats_a = model.get_win_probability("b", "a")
        self.assertLess(prob_b_beats_a, 0.5)

        # Probabilities should sum to 1
        self.assertAlmostEqual(prob_a_beats_b + prob_b_beats_a, 1.0, places=5)

    def test_unknown_item_returns_50_percent(self):
        """Test that unknown items return 50% probability."""
        items = [Item(name="Item A", id="a")]
        model = BradleyTerryModel(items)
        model.compute_rankings()

        prob = model.get_win_probability("a", "unknown")
        self.assertEqual(prob, 0.5)

    def test_probability_before_compute(self):
        """Test probability before compute_rankings returns 50%."""
        items = [
            Item(name="Item A", id="a"),
            Item(name="Item B", id="b"),
        ]
        model = BradleyTerryModel(items)

        prob = model.get_win_probability("a", "b")
        self.assertEqual(prob, 0.5)


class TestFisherInformation(unittest.TestCase):
    """Tests comparing the vectorized Fisher matrix to a loop reference."""

    def test_matches_loop_reference(self):
        """Vectorized Fisher Information matches the loop reference."""
        rng = random.Random(20240115)
        items = [Item(name=f"Item {i}", id=str(i)) for i in range(6)]

        votes = []
        for _ in range(30):
            winner, loser = rng.sample(range(6), 2)
            votes.append(
                Vote(
                    winner_id=str(winner),
                    loser_id=str(loser),
                    weight=rng.choice([1.0, 2.0, 3.0]),
                )
            )

        model = BradleyTerryModel(items)
        model.add_votes(votes)
        model.compute_rankings()

        pi = model._strengths
        W = model._apply_regularization()

        expected = fisher_information_reference(W, pi)
        actual = model._compute_fisher_information(pi)

        self.assertEqual(actual.shape, expected.shape)
        self.assertLess(float(np.max(np.abs(actual - expected))), 1e-9)


class TestRankingResult(unittest.TestCase):
    """Tests for RankingResult dataclass."""

    def test_ranking_result_fields(self):
        """Test that RankingResult has all expected fields."""
        item = Item(name="Test", id="test")
        result = RankingResult(
            item=item,
            strength=2.0,
            log_strength=0.693,
            elo_rating=1600.0,
            rank=1,
            comparison_count=5,
        )

        self.assertEqual(result.item, item)
        self.assertEqual(result.strength, 2.0)
        self.assertAlmostEqual(result.log_strength, 0.693, places=2)
        self.assertEqual(result.elo_rating, 1600.0)
        self.assertEqual(result.rank, 1)
        self.assertEqual(result.comparison_count, 5)


if __name__ == "__main__":
    unittest.main()
