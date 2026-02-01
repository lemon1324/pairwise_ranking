"""Vote model for the pairwise ranking application."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


# Valid vote weights mapping preference strength to numerical weight
VOTE_WEIGHTS = {
    "much_better": 3.0,
    "better": 2.0,
    "slightly_better": 1.0,
}


@dataclass
class Vote:
    """
    Represents a single pairwise comparison vote.

    A vote records that the winner was preferred over the loser with a certain
    weight indicating the strength of preference.

    Attributes:
        winner_id: The ID of the item that was preferred.
        loser_id: The ID of the item that was not preferred.
        weight: The strength of preference (1.0=slightly, 2.0=better, 3.0=much better).
        timestamp: When the vote was recorded. Auto-set to current time if not provided.
        id: A unique identifier for the vote. Auto-generated if not provided.

    Example:
        >>> vote = Vote(winner_id="item1", loser_id="item2", weight=2.0)
        >>> print(vote.weight)
        2.0
    """

    winner_id: str
    loser_id: str
    weight: float
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        """
        Validate vote data after initialization.

        Raises:
            ValueError: If winner_id equals loser_id.
            ValueError: If weight is not positive.
        """
        if self.winner_id == self.loser_id:
            raise ValueError("Winner and loser cannot be the same item")
        if self.weight <= 0:
            raise ValueError("Vote weight must be positive")

    def __hash__(self):
        """
        Return hash based on vote ID.

        Returns:
            int: Hash value of the vote's ID.
        """
        return hash(self.id)

    def __eq__(self, other):
        """
        Check equality based on vote ID.

        Args:
            other: Another object to compare with.

        Returns:
            bool: True if other is a Vote with the same ID, False otherwise.
        """
        if not isinstance(other, Vote):
            return False
        return self.id == other.id

    def get_decayed_weight(self, decay_timescale_days: float, reference_time: Optional[datetime] = None) -> float:
        """
        Calculate the vote weight after time-based decay.

        Uses exponential decay based on time elapsed since the vote was recorded.

        Args:
            decay_timescale_days: The half-life of vote decay in days.
            reference_time: The time to measure decay from. Defaults to current time.

        Returns:
            float: The decayed weight, which is always positive but may be very small.

        Example:
            >>> vote = Vote(winner_id="a", loser_id="b", weight=2.0)
            >>> # After exactly decay_timescale_days, weight is halved
            >>> decayed = vote.get_decayed_weight(30.0)
        """
        if reference_time is None:
            reference_time = datetime.now()

        if decay_timescale_days <= 0:
            return self.weight

        elapsed_days = (reference_time - self.timestamp).total_seconds() / 86400.0
        if elapsed_days < 0:
            elapsed_days = 0

        # Exponential decay: weight * 0.5^(elapsed / half_life)
        decay_factor = 0.5 ** (elapsed_days / decay_timescale_days)
        return self.weight * decay_factor

    def involves_item(self, item_id: str) -> bool:
        """
        Check if this vote involves a specific item.

        Args:
            item_id: The ID of the item to check.

        Returns:
            bool: True if the item is either the winner or loser in this vote.
        """
        return item_id in (self.winner_id, self.loser_id)

    def get_pair(self) -> tuple[str, str]:
        """
        Get the pair of item IDs involved in this vote.

        Returns:
            tuple[str, str]: A tuple of (winner_id, loser_id).
        """
        return (self.winner_id, self.loser_id)

    def get_pair_unordered(self) -> frozenset[str]:
        """
        Get the pair of item IDs as an unordered set.

        Useful for comparing whether two votes involve the same pair regardless
        of which item won.

        Returns:
            frozenset[str]: An unordered set of the two item IDs.
        """
        return frozenset([self.winner_id, self.loser_id])

    def to_dict(self) -> dict:
        """
        Convert vote to a dictionary representation.

        Returns:
            dict: Dictionary with vote data including ISO format timestamp.
        """
        return {
            "id": self.id,
            "winner_id": self.winner_id,
            "loser_id": self.loser_id,
            "weight": self.weight,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Vote":
        """
        Create a Vote from a dictionary.

        Args:
            data: Dictionary containing vote data. Timestamp should be ISO format string.

        Returns:
            Vote: A new Vote instance.

        Raises:
            KeyError: If required keys are missing from data.
        """
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        return cls(
            winner_id=data["winner_id"],
            loser_id=data["loser_id"],
            weight=float(data["weight"]),
            timestamp=timestamp,
            id=data.get("id", str(uuid.uuid4())),
        )
