"""Settings model for the pairwise ranking application."""

import logging
import math
from dataclasses import dataclass, replace
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Limit:
    """
    The range one numeric setting must stay in.

    Only sanity: nothing negative, a rate that is a rate, a count that counts.
    There are no upper caps; the desktop's spin boxes keep tighter ranges of
    their own, which are a matter of that editor, not of the file.

    Attributes:
        minimum: The smallest value allowed.
        maximum: The largest value allowed, or None for no cap.
        whole: Whether the value must be a whole number.
    """

    minimum: float
    maximum: Optional[float] = None
    whole: bool = False

    def allows(self, value) -> bool:
        """
        Check one value against the range.

        Args:
            value: The value, already a number.

        Returns:
            bool: True when it is finite, in range, and whole if it has to be.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not math.isfinite(value):
            return False
        if self.whole and value != int(value):
            return False
        if value < self.minimum:
            return False
        return self.maximum is None or value <= self.maximum

    def clamp(self, value, default):
        """
        Bring a value into the range.

        Args:
            value: The value, already a number.
            default: What a value that is no number at all (NaN, infinite)
                becomes.

        Returns:
            The nearest allowed value: the bound it crossed, or the default.
        """
        if not math.isfinite(value):
            value = default
        value = max(value, self.minimum)
        if self.maximum is not None:
            value = min(value, self.maximum)
        return max(int(value), int(self.minimum)) if self.whole else value


# The numeric settings and their ranges. A half-life of 0 still means no decay,
# and the booleans have nothing to check.
LIMITS = {
    "weight_uncertainty": Limit(0.0),
    "weight_connectivity": Limit(0.0),
    "weight_freshness": Limit(0.0),
    "weight_uncompared": Limit(0.0),
    "decay_timescale_days": Limit(0.0),
    "top_tier_count": Limit(1, whole=True),
    "top_tier_weight": Limit(0.0),
    "cross_category_rate": Limit(0.0, 1.0),
}


@dataclass
class Settings:
    """
    Application settings for pair selection algorithm.

    Attributes:
        weight_uncertainty: Weight for uncertainty factor in pair selection.
        weight_connectivity: Weight for connectivity factor in pair selection.
        weight_freshness: Weight for freshness factor in pair selection.
        weight_uncompared: Weight for uncompared items factor in pair selection.
        decay_timescale_days: Half-life of vote decay in days.
        top_tier_mode: Whether to prioritize top-tier item comparisons.
        top_tier_count: Number of items considered "top tier".
        top_tier_weight: Additional weight for top-tier comparisons.
    """

    weight_uncertainty: float = 1.0
    weight_connectivity: float = 1.0
    weight_freshness: float = 0.5
    weight_uncompared: float = 2.0
    decay_timescale_days: float = 30.0
    top_tier_mode: bool = False
    top_tier_count: int = 10
    top_tier_weight: float = 2.0
    blinded_comparison_mode: bool = False
    cross_category_rate: float = 0.1

    def invalid_fields(self) -> list[str]:
        """
        Name the settings that are outside their range.

        Returns:
            list[str]: The field names, in declaration order; empty when every
            setting is sane.
        """
        return [
            name for name, limit in LIMITS.items() if not limit.allows(getattr(self, name))
        ]

    def validate(self) -> None:
        """
        Refuse settings that are outside their range.

        Raises:
            ValueError: If any setting is negative, not finite, a rate outside
                0 to 1, or a top-tier count that is not a whole number of at
                least 1. The message names every such field.
        """
        invalid = self.invalid_fields()
        if invalid:
            raise ValueError(f"Settings out of range: {', '.join(invalid)}")

    def clamped(self) -> "Settings":
        """
        Return a copy with every setting brought into its range.

        Returns:
            Settings: The copy. A value below its range becomes the bound, a
            value that is no number at all becomes the default, and the top-tier
            count becomes a whole number.
        """
        defaults = Settings()
        changes = {
            name: limit.clamp(getattr(self, name), getattr(defaults, name))
            for name, limit in LIMITS.items()
        }
        return replace(self, **changes)

    def to_dict(self) -> dict:
        """
        Convert settings to a dictionary.

        Returns:
            dict: Dictionary representation of settings.
        """
        return {
            "weight_uncertainty": self.weight_uncertainty,
            "weight_connectivity": self.weight_connectivity,
            "weight_freshness": self.weight_freshness,
            "weight_uncompared": self.weight_uncompared,
            "decay_timescale_days": self.decay_timescale_days,
            "top_tier_mode": self.top_tier_mode,
            "top_tier_count": self.top_tier_count,
            "top_tier_weight": self.top_tier_weight,
            "blinded_comparison_mode": self.blinded_comparison_mode,
            "cross_category_rate": self.cross_category_rate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """
        Create Settings from a dictionary.

        A value out of range - a negative weight, a rate above 1, a top-tier
        count of 0 - is brought into range rather than refused, and a warning
        is logged: the file still opens, and saving writes the sane value back.
        A value that is not a number at all is still an error.

        Args:
            data: Dictionary containing settings values.

        Returns:
            Settings: A new Settings instance with values from the dictionary.
        """
        loaded = cls(
            weight_uncertainty=float(data.get("weight_uncertainty", 1.0)),
            weight_connectivity=float(data.get("weight_connectivity", 1.0)),
            weight_freshness=float(data.get("weight_freshness", 0.5)),
            weight_uncompared=float(data.get("weight_uncompared", 2.0)),
            decay_timescale_days=float(data.get("decay_timescale_days", 30.0)),
            top_tier_mode=bool(data.get("top_tier_mode", False)),
            # Read as a float first: int() of an infinity raises OverflowError,
            # not the ValueError a malformed file answers with.
            top_tier_count=float(data.get("top_tier_count", 10)),
            top_tier_weight=float(data.get("top_tier_weight", 2.0)),
            blinded_comparison_mode=bool(data.get("blinded_comparison_mode", False)),
            cross_category_rate=float(data.get("cross_category_rate", 0.1)),
        )
        changed = loaded.invalid_fields()
        if changed:
            logger.warning("Settings out of range were brought into range: %s", ", ".join(changed))
        return loaded.clamped()
