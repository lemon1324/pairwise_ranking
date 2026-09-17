"""Unit tests for the Compare screen's confidence reading."""

import math
import unittest

import numpy as np

from src.app.confidence import (
    ELO_SPREAD,
    AdjacentNeighbourConfidence,
    ConfidenceReading,
)
from src.models.item import Item
from src.models.ranking import (
    BradleyTerryModel,
    RankingResult,
    assign_active_ranks,
)
from src.models.vote import Vote


# The z-score at which the default 0.8 threshold is met exactly.
Z_AT_EIGHTY_PERCENT = 0.8416212335729143


def build_result(
    index: int,
    log_strength: float,
    log_strength_se: float = 0.0,
    rank=None,
    retired: bool = False,
) -> RankingResult:
    """
    Build one ranking result with the log-strength and error under test.

    Args:
        index: Used for the item's id and name.
        log_strength: The log-strength to report.
        log_strength_se: The standard error to report.
        rank: The rank to report, or None for an unranked (retired) result.
        retired: Whether the underlying item is retired.

    Returns:
        RankingResult: The constructed result.
    """
    item = Item(name=f"Item {index}", id=f"item-{index}")
    if retired:
        item.retire()
    strength = math.exp(log_strength) if math.isfinite(log_strength) else 0.0
    return RankingResult(
        item=item,
        strength=strength,
        log_strength=log_strength,
        elo_rating=0.0,
        rank=rank,
        comparison_count=0,
        log_strength_se=log_strength_se,
    )


def build_rankings(*rows) -> list[RankingResult]:
    """
    Build a ranked run of results from (log_strength, se) pairs.

    Args:
        *rows: One (log_strength, standard error) pair per active item, best
            first.

    Returns:
        list[RankingResult]: The results, ranked from 1.
    """
    return [
        build_result(index, log_strength, se, rank=index + 1)
        for index, (log_strength, se) in enumerate(rows)
    ]


def fitted_rankings() -> list[RankingResult]:
    """
    Fit a real Bradley-Terry model so the reading can be checked end to end.

    Returns:
        list[RankingResult]: Ranked results over five active items and one
        retired one.
    """
    items = [Item(name=f"I{i}", id=f"i{i}") for i in range(6)]
    items[5].retire()
    votes = [
        Vote(winner_id=f"i{a}", loser_id=f"i{b}", weight=weight)
        for a, b, weight in [
            (0, 1, 2.0),
            (0, 2, 1.0),
            (1, 2, 3.0),
            (2, 3, 1.0),
            (3, 4, 2.0),
            (1, 4, 1.0),
            (0, 5, 2.0),
            (5, 4, 1.0),
        ]
    ]
    model = BradleyTerryModel(items)
    model.add_votes(votes)
    return assign_active_ranks(model.compute_rankings())


class TestConfidenceNoReading(unittest.TestCase):
    """Test cases for the situations that have no reading at all."""

    def setUp(self):
        """Set up test fixtures."""
        self.reader = AdjacentNeighbourConfidence()

    def test_none_rankings(self):
        """Test that the <2-items case a session reports as None reads as None."""
        self.assertIsNone(self.reader.read(None))

    def test_empty_rankings(self):
        """Test that an empty result list reads as None."""
        self.assertIsNone(self.reader.read([]))

    def test_one_active_item(self):
        """Test that a single ranked item has no adjacent pair to judge."""
        self.assertIsNone(self.reader.read(build_rankings((0.5, 0.1))))

    def test_one_active_item_beside_retired_ones(self):
        """Test that retired items do not make up the missing neighbour."""
        rankings = [
            build_result(0, 0.5, 0.1, rank=1),
            build_result(1, 0.2, 0.1, rank=None, retired=True),
            build_result(2, 0.1, 0.1, rank=None, retired=True),
        ]

        self.assertIsNone(self.reader.read(rankings))

    def test_no_active_items(self):
        """Test that a ranking of retired items alone reads as None."""
        rankings = [
            build_result(0, 0.5, 0.1, rank=None, retired=True),
            build_result(1, 0.2, 0.1, rank=None, retired=True),
        ]

        self.assertIsNone(self.reader.read(rankings))


class TestConfidenceSettledCount(unittest.TestCase):
    """Test cases for counting the adjacent pairs whose order is supported."""

    def setUp(self):
        """Set up test fixtures."""
        self.reader = AdjacentNeighbourConfidence()

    def test_neighbours_is_one_less_than_the_active_items(self):
        """Test that N active items give N-1 adjacent pairs."""
        rankings = build_rankings((3.0, 0.1), (2.0, 0.1), (1.0, 0.1), (0.0, 0.1))

        self.assertEqual(self.reader.read(rankings).neighbours, 3)

    def test_retired_items_are_not_neighbours(self):
        """Test that an unranked item between two ranked ones is skipped."""
        rankings = [
            build_result(0, 3.0, 0.1, rank=1),
            build_result(1, 2.0, 0.1, rank=None, retired=True),
            build_result(2, 1.0, 0.1, rank=2),
        ]

        self.assertEqual(self.reader.read(rankings).neighbours, 1)

    def test_a_wide_gap_is_settled(self):
        """Test that a gap far beyond the errors counts as settled."""
        rankings = build_rankings((5.0, 0.1), (0.0, 0.1))

        self.assertEqual(self.reader.read(rankings).settled, 1)

    def test_no_gap_is_not_settled(self):
        """Test that two items of equal strength are not in a settled order."""
        rankings = build_rankings((1.0, 0.1), (1.0, 0.1))

        self.assertEqual(self.reader.read(rankings).settled, 0)

    def test_the_threshold_is_inclusive(self):
        """Test that a pair landing exactly on 80% counts as settled."""
        gap = Z_AT_EIGHTY_PERCENT * math.sqrt(0.02)
        rankings = build_rankings((gap, 0.1), (0.0, 0.1))

        self.assertEqual(self.reader.read(rankings).settled, 1)

    def test_just_below_the_threshold_is_not_settled(self):
        """Test that a pair a hair under 80% does not count."""
        gap = (Z_AT_EIGHTY_PERCENT - 1e-6) * math.sqrt(0.02)
        rankings = build_rankings((gap, 0.1), (0.0, 0.1))

        self.assertEqual(self.reader.read(rankings).settled, 0)

    def test_settled_and_unsettled_pairs_together(self):
        """Test that only the supported pairs are counted."""
        rankings = build_rankings((10.0, 0.1), (5.0, 0.1), (5.0, 0.1), (0.0, 0.1))

        reading = self.reader.read(rankings)

        self.assertEqual((reading.settled, reading.neighbours), (2, 3))

    def test_a_larger_error_unsettles_a_pair(self):
        """Test that the same gap can be settled or not depending on the errors."""
        gap = 1.0
        tight = build_rankings((gap, 0.1), (0.0, 0.1))
        loose = build_rankings((gap, 5.0), (0.0, 5.0))

        self.assertEqual(self.reader.read(tight).settled, 1)
        self.assertEqual(self.reader.read(loose).settled, 0)

    def test_settled_fraction(self):
        """Test that the settled share is reported off the two counts."""
        reading = ConfidenceReading(settled=3, neighbours=4, tolerance=None)
        self.assertEqual(reading.settled_fraction, 0.75)


class TestConfidenceDegenerateCases(unittest.TestCase):
    """Test cases for the arithmetic that has no ordinary answer."""

    def setUp(self):
        """Set up test fixtures."""
        self.reader = AdjacentNeighbourConfidence()

    def test_zero_errors_and_a_gap_are_settled(self):
        """Test that a gap with no uncertainty at all settles the order."""
        rankings = build_rankings((1.0, 0.0), (0.0, 0.0))

        self.assertEqual(self.reader.read(rankings).settled, 1)

    def test_zero_errors_and_no_gap_are_not_settled(self):
        """Test that two identical items with no uncertainty stay tied."""
        rankings = build_rankings((1.0, 0.0), (1.0, 0.0))

        self.assertEqual(self.reader.read(rankings).settled, 0)

    def test_an_item_that_never_won_settles_its_pair(self):
        """Test that an infinite gap to a zero-strength item counts as settled."""
        rankings = build_rankings((1.0, 0.5), (float("-inf"), 0.5))

        self.assertEqual(self.reader.read(rankings).settled, 1)

    def test_two_items_that_never_won_are_not_settled(self):
        """Test that two zero-strength items have no order to support."""
        rankings = build_rankings(
            (float("-inf"), 0.5), (float("-inf"), 0.5)
        )

        self.assertEqual(self.reader.read(rankings).settled, 0)

    def test_an_item_that_never_won_is_left_out_of_the_tolerance(self):
        """Test that an infinite log-strength does not poison the tolerance."""
        rankings = build_rankings(
            (2.0, 0.2), (0.0, 0.2), (float("-inf"), 99.0)
        )

        tolerance = self.reader.read(rankings).tolerance

        self.assertIsNotNone(tolerance)
        self.assertTrue(math.isfinite(tolerance))
        self.assertEqual(tolerance, 0.2 * ELO_SPREAD / np.std([2.0, 0.0]))

    def test_no_spread_means_no_tolerance(self):
        """Test that the all-1500 case reports the tolerance as unavailable."""
        rankings = build_rankings((1.0, 0.3), (1.0, 0.3), (1.0, 0.3))

        reading = self.reader.read(rankings)

        self.assertIsNotNone(reading)
        self.assertIsNone(reading.tolerance)
        self.assertEqual(reading.neighbours, 2)

    def test_every_item_lost_everything(self):
        """Test that a ranking of nothing but zero strengths still reads."""
        rankings = build_rankings(
            (float("-inf"), 0.0), (float("-inf"), 0.0)
        )

        reading = self.reader.read(rankings)

        self.assertIsNotNone(reading)
        self.assertIsNone(reading.tolerance)
        self.assertEqual(reading.settled, 0)


class TestConfidenceTolerance(unittest.TestCase):
    """Test cases for converting the typical standard error to rating points."""

    def setUp(self):
        """Set up test fixtures."""
        self.reader = AdjacentNeighbourConfidence()

    def test_tolerance_uses_the_median_error(self):
        """Test that the middle error of an odd-sized run is the one used."""
        rankings = build_rankings((2.0, 0.1), (1.0, 0.5), (0.0, 0.9))
        divisor = np.std([2.0, 1.0, 0.0])

        tolerance = self.reader.read(rankings).tolerance

        self.assertAlmostEqual(tolerance, 0.5 * ELO_SPREAD / divisor)

    def test_tolerance_averages_the_middle_two_errors(self):
        """Test that an even-sized run takes the mean of the middle pair."""
        rankings = build_rankings(
            (3.0, 0.1), (2.0, 0.3), (1.0, 0.5), (0.0, 0.7)
        )
        divisor = np.std([3.0, 2.0, 1.0, 0.0])

        tolerance = self.reader.read(rankings).tolerance

        self.assertAlmostEqual(tolerance, 0.4 * ELO_SPREAD / divisor)

    def test_the_divisor_spans_the_retired_items_too(self):
        """Test that a retired item widens the spread the divisor is taken over."""
        active = [
            build_result(0, 1.0, 0.2, rank=1),
            build_result(1, 0.0, 0.2, rank=2),
        ]
        with_retired = active + [
            build_result(2, -10.0, 0.2, rank=None, retired=True)
        ]

        narrow = self.reader.read(active).tolerance
        wide = self.reader.read(with_retired).tolerance

        self.assertAlmostEqual(narrow, 0.2 * ELO_SPREAD / np.std([1.0, 0.0]))
        self.assertAlmostEqual(
            wide, 0.2 * ELO_SPREAD / np.std([1.0, 0.0, -10.0])
        )
        self.assertLess(wide, narrow)

    def test_the_median_ignores_the_retired_items(self):
        """Test that only the active items' errors feed the median."""
        rankings = [
            build_result(0, 2.0, 0.2, rank=1),
            build_result(1, 0.0, 0.2, rank=2),
            build_result(2, -1.0, 99.0, rank=None, retired=True),
        ]
        divisor = np.std([2.0, 0.0, -1.0])

        tolerance = self.reader.read(rankings).tolerance

        self.assertAlmostEqual(tolerance, 0.2 * ELO_SPREAD / divisor)

    def test_the_divisor_matches_the_elo_conversion(self):
        """Test that the tolerance is quoted on the same scale as the ratings."""
        rankings = fitted_rankings()
        first, second = rankings[0], rankings[1]
        points_per_log_unit = (first.elo_rating - second.elo_rating) / (
            first.log_strength - second.log_strength
        )

        active = sorted(
            (r.log_strength_se for r in rankings if r.rank is not None)
        )
        middle = len(active) // 2
        median = (
            active[middle]
            if len(active) % 2
            else (active[middle - 1] + active[middle]) / 2.0
        )

        tolerance = self.reader.read(rankings).tolerance

        self.assertAlmostEqual(tolerance, median * points_per_log_unit, places=9)

    def test_a_real_fit_reads(self):
        """Test that a real Bradley-Terry fit produces a usable reading."""
        reading = self.reader.read(fitted_rankings())

        self.assertEqual(reading.neighbours, 4)
        self.assertGreaterEqual(reading.settled, 0)
        self.assertLessEqual(reading.settled, reading.neighbours)
        self.assertGreater(reading.tolerance, 0.0)


class TestConfidenceSwappable(unittest.TestCase):
    """Test cases for the reader being a replaceable piece."""

    def test_a_stricter_threshold_settles_fewer_pairs(self):
        """Test that the settled probability is a parameter of the reader."""
        rankings = build_rankings((1.0, 0.5), (0.0, 0.5))

        lenient = AdjacentNeighbourConfidence(settled_probability=0.6)
        strict = AdjacentNeighbourConfidence(settled_probability=0.99)

        self.assertEqual(lenient.read(rankings).settled, 1)
        self.assertEqual(strict.read(rankings).settled, 0)

    def test_a_custom_reader_satisfies_the_interface(self):
        """Test that any object with read() can stand in for the default."""

        class AlwaysSettled:
            """A reader that declares everything settled."""

            def read(self, rankings):
                """Return a fixed reading."""
                return ConfidenceReading(settled=7, neighbours=7, tolerance=1.0)

        reading = AlwaysSettled().read(build_rankings((1.0, 0.1)))

        self.assertEqual(reading.settled, 7)
        self.assertEqual(reading.settled_fraction, 1.0)

    def test_the_reading_is_immutable(self):
        """Test that a screen cannot write through a reading it was handed."""
        reading = ConfidenceReading(settled=1, neighbours=2, tolerance=3.0)

        with self.assertRaises(Exception):
            reading.settled = 5


if __name__ == "__main__":
    unittest.main()
