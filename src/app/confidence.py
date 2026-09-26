"""How settled a ranking is, as the Compare screen reads it.

The reading is two numbers: how many adjacent pairs of the active ranking are
in an order the data actually supports, and how wide a band of rating points a
typical item's uncertainty covers. A screen renders them as "Order settled
31/41" and "Tolerance +/-38".

**The reading is hidden entirely in blinded comparison mode.** It is a
statement about the ranking, and the whole point of a blinded comparison is
that the ranking is not on screen. Nothing here enforces that - a reader has no
idea what mode a screen is in - so a blinded view must simply not ask for it.

**The reading is approximate.** Each adjacent pair is judged as if the two
items' standard errors were independent, which they are not: the Bradley-Terry
fit ties neighbouring items together, most strongly when they have compared
against each other, and the covariance that expresses that is thrown away here.
The reading is a reading, not an inference.

The formula is deliberately swappable. :class:`ConfidenceReader` is the
interface a screen depends on and :class:`AdjacentNeighbourConfidence` is the
one implementation today, so a better formula can be dropped in without any
screen changing.
"""

import math
from dataclasses import dataclass
from typing import Optional, Protocol

import numpy as np

from src.models.ranking import RankingResult


# How likely a pair's order has to be before it counts as settled.
DEFAULT_SETTLED_PROBABILITY = 0.8

# Rating points one standard deviation of log-strength is worth. This is the
# spread of the z-score conversion in
# :meth:`~src.models.ranking.BradleyTerryModel._compute_elo_ratings`, which is
# what makes the tolerance comparable with the +/- SE shown on a rankings row.
ELO_SPREAD = 200.0

# Below this, the log-strengths are all the same number and the conversion to
# rating points has no meaning. The same guard as _compute_elo_ratings uses
# before it gives every item 1500.
MIN_LOG_STRENGTH_SPREAD = 1e-10

# Rankings need at least this many active ranked items before there is an
# adjacent pair to judge.
MIN_READABLE_ITEMS = 2


@dataclass(frozen=True)
class ConfidenceReading:
    """
    How settled a ranking is.

    Attributes:
        settled: How many adjacent pairs of the active ranking are in an order
            the data supports.
        neighbours: How many adjacent pairs there are, one less than the number
            of active ranked items. Always at least 1.
        tolerance: The typical uncertainty of an item in rating points, or None
            when the ranking carries no meaningful spread and rating points
            therefore mean nothing.
    """

    settled: int
    neighbours: int
    tolerance: Optional[float]

    @property
    def settled_fraction(self) -> float:
        """
        Report the settled share of the adjacent pairs.

        Returns:
            float: Between 0.0 and 1.0. A reading always holds at least one
            neighbour, so this never divides by zero.
        """
        return self.settled / self.neighbours


class ConfidenceReader(Protocol):
    """
    Anything that can read a confidence off a set of rankings.

    Screens depend on this rather than on a formula, so the formula can be
    replaced without touching them.
    """

    def read(
        self, rankings: Optional[list[RankingResult]]
    ) -> Optional[ConfidenceReading]:
        """
        Read the confidence off a set of rankings.

        Args:
            rankings: The rankings to read, or None when there are none.

        Returns:
            Optional[ConfidenceReading]: The reading, or None when there is
            nothing to read. Never raises: "no reading" is an answer.
        """
        ...


def _normal_cdf(z: float) -> float:
    """
    Evaluate the standard normal cumulative distribution.

    scipy is not a dependency and does not need to become one: ``math.erf`` is
    exact, scalar and in the standard library, and this is called once per
    adjacent pair.

    Args:
        z: The z-score.

    Returns:
        float: The probability that a standard normal draw is at most z.
    """
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _pair_is_settled(
    gap: float, se_a: float, se_b: float, threshold: float
) -> bool:
    """
    Decide whether one adjacent pair's order is supported by the data.

    Args:
        gap: The higher item's log-strength minus the lower item's. Never
            negative, because the pairs come from a sorted ranking, but may be
            infinite when the lower item has never won, or NaN when neither
            has.
        se_a: Standard error of the higher item's log-strength.
        se_b: Standard error of the lower item's.
        threshold: How likely the order has to be.

    Returns:
        bool: True when the order is at least ``threshold`` likely.
    """
    if math.isnan(gap):
        # Both items have a strength of zero, so there is no order to support.
        return False

    spread = math.sqrt(se_a * se_a + se_b * se_b)
    if spread == 0.0:
        # No uncertainty at all: any gap settles the order, no gap leaves the
        # two items genuinely tied.
        return gap > 0.0

    return _normal_cdf(gap / spread) >= threshold


@dataclass(frozen=True)
class AdjacentNeighbourConfidence:
    """
    The default confidence formula.

    A pair of neighbours in the active ranking is settled when the normal
    approximation puts their order at least :attr:`settled_probability` likely,
    given the gap between their log-strengths and the standard errors of both.
    The tolerance is the median standard error of those same items, converted
    to rating points.

    Attributes:
        settled_probability: How likely a pair's order has to be before it
            counts as settled.
    """

    settled_probability: float = DEFAULT_SETTLED_PROBABILITY

    def read(
        self, rankings: Optional[list[RankingResult]]
    ) -> Optional[ConfidenceReading]:
        """
        Read the confidence off a set of rankings.

        Args:
            rankings: The rankings as
                :meth:`~src.app.session.ProjectSession.rankings` returns them,
                retired items included, or None when there are none.

        Returns:
            Optional[ConfidenceReading]: The reading, or None when fewer than
            two active items are ranked and there is no adjacent pair to judge.
        """
        if not rankings:
            return None

        active = sorted(
            (result for result in rankings if result.rank is not None),
            key=lambda result: result.rank,
        )
        if len(active) < MIN_READABLE_ITEMS:
            return None

        settled = 0
        for higher, lower in zip(active, active[1:]):
            if _pair_is_settled(
                higher.log_strength - lower.log_strength,
                higher.log_strength_se,
                lower.log_strength_se,
                self.settled_probability,
            ):
                settled += 1

        return ConfidenceReading(
            settled=settled,
            neighbours=len(active) - 1,
            tolerance=self._tolerance(rankings, active),
        )

    def _tolerance(
        self,
        rankings: list[RankingResult],
        active: list[RankingResult],
    ) -> Optional[float]:
        """
        Convert the typical standard error into rating points.

        The rating of an item is ``1500 + 200 * z``, where ``z`` is the z-score
        of its log-strength across **every** item the model was given, retired
        ones included. So one unit of log-strength is worth
        ``200 / std(log-strengths)`` rating points, and the divisor has to be
        taken over the same population, with the same population standard
        deviation, as
        :meth:`~src.models.ranking.BradleyTerryModel._compute_elo_ratings`
        takes it over - otherwise this +/- and the +/- on a rankings row would
        be quoting two different scales. The *median* is taken over the active
        ranked items alone, because those are the items the reading is about.

        One small discrepancy: ``_compute_elo_ratings`` computes its own
        ``log(pi + 1e-300)``, so an item with a strength of zero enters its
        standard deviation as about -690 rather than as minus infinity. Here
        such an item is dropped from both the median and the divisor instead,
        because minus infinity cannot be averaged. A converged fit has no such
        item - every strength is positive - so the two agree in practice.

        Args:
            rankings: Every result the model produced, retired items included.
            active: The active ranked results.

        Returns:
            Optional[float]: The tolerance in rating points, or None when the
            log-strengths carry no spread and rating points mean nothing.
        """
        scale = rating_points_per_log_unit(rankings)
        if scale is None:
            return None

        standard_errors = sorted(
            result.log_strength_se
            for result in active
            if math.isfinite(result.log_strength)
        )
        if not standard_errors:
            return None

        middle = len(standard_errors) // 2
        if len(standard_errors) % 2:
            median = standard_errors[middle]
        else:
            median = (standard_errors[middle - 1] + standard_errors[middle]) / 2.0

        return median * scale


def rating_points_per_log_unit(rankings: list[RankingResult]) -> Optional[float]:
    """
    Say how many rating points one unit of log-strength is worth.

    The rating of an item is ``1500 + 200 * z``, where ``z`` is the z-score of
    its log-strength across every item the model was given, retired ones
    included, so one unit of log-strength is ``200 / std(log-strengths)``
    points. The Compare tolerance and the +/- SE on a Rankings row are both a
    log-strength standard error times this, which is what keeps them on one
    scale. An item whose log-strength is not finite is left out (see
    :meth:`AdjacentNeighbourConfidence._tolerance`).

    Args:
        rankings: Every result the model produced, retired items included.

    Returns:
        Optional[float]: The points per unit, or None when there is nothing to
        measure or the log-strengths carry no spread, so rating points mean
        nothing.
    """
    log_strengths = [
        result.log_strength
        for result in rankings
        if math.isfinite(result.log_strength)
    ]
    if not log_strengths:
        return None

    spread = float(np.std(log_strengths))
    if spread < MIN_LOG_STRENGTH_SPREAD:
        return None

    return ELO_SPREAD / spread


# The reader a screen gets when it asks for no particular one.
DEFAULT_CONFIDENCE_READER: ConfidenceReader = AdjacentNeighbourConfidence()
