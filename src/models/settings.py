"""Settings model for the pairwise ranking application."""

from dataclasses import dataclass


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
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """
        Create Settings from a dictionary.

        Args:
            data: Dictionary containing settings values.

        Returns:
            Settings: A new Settings instance with values from the dictionary.
        """
        return cls(
            weight_uncertainty=float(data.get("weight_uncertainty", 1.0)),
            weight_connectivity=float(data.get("weight_connectivity", 1.0)),
            weight_freshness=float(data.get("weight_freshness", 0.5)),
            weight_uncompared=float(data.get("weight_uncompared", 2.0)),
            decay_timescale_days=float(data.get("decay_timescale_days", 30.0)),
            top_tier_mode=bool(data.get("top_tier_mode", False)),
            top_tier_count=int(data.get("top_tier_count", 10)),
            top_tier_weight=float(data.get("top_tier_weight", 2.0)),
            blinded_comparison_mode=bool(data.get("blinded_comparison_mode", False)),
        )
