"""Weighted win/loss record of one item against each of its opponents.

This is the Qt-free core behind the Rankings detail view. It aggregates the
votes an item took part in by opponent **id** and reports both the raw weight
and the time-decayed weight, leaving every display decision - which of the two
weightings to show, how to format it, whether to merge opponents that share a
name - to the frontend.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from src.models.item import Item
from src.models.vote import Vote


# Name reported for an opponent that is no longer part of the project.
UNKNOWN_OPPONENT_NAME = "Unknown"


@dataclass(frozen=True)
class OpponentRecord:
    """
    The weight an item won or lost against one opponent.

    Attributes:
        opponent_id: Id of the opposing item.
        name: Name of the opposing item, or UNKNOWN_OPPONENT_NAME when the
            project no longer holds an item with that id.
        weight_raw: Sum of the raw vote weights against this opponent.
        weight_decayed: Sum of the same weights after time decay.
    """

    opponent_id: str
    name: str
    weight_raw: float
    weight_decayed: float


@dataclass(frozen=True)
class WeightedRecord:
    """
    An item's record against every opponent it has met.

    Attributes:
        wins: One entry per opponent the item has beaten, ordered by opponent
            name and then by opponent id.
        losses: One entry per opponent the item has lost to, in the same order.
    """

    wins: list[OpponentRecord]
    losses: list[OpponentRecord]


def _ordered(
    raw: dict[str, float],
    decayed: dict[str, float],
    names: dict[str, str],
) -> list[OpponentRecord]:
    """
    Turn the per-opponent sums into ordered records.

    Args:
        raw: Raw weight per opponent id.
        decayed: Decayed weight per opponent id.
        names: Item name per item id.

    Returns:
        list[OpponentRecord]: One record per opponent, ordered by name and then
        by id so that opponents sharing a name keep a stable order.
    """
    records = [
        OpponentRecord(
            opponent_id=opponent_id,
            name=names.get(opponent_id, UNKNOWN_OPPONENT_NAME),
            weight_raw=weight,
            weight_decayed=decayed[opponent_id],
        )
        for opponent_id, weight in raw.items()
    ]
    records.sort(key=lambda record: (record.name, record.opponent_id))
    return records


def weighted_record(
    item_id: str,
    votes: Iterable[Vote],
    items: Iterable[Item],
    decay_timescale_days: float = 0.0,
    reference_time: Optional[datetime] = None,
) -> WeightedRecord:
    """
    Build an item's weighted win/loss record, keyed by opponent id.

    Opponents are kept apart by id, so two items that happen to share a name
    stay separate; a frontend that wants them merged does that itself.

    Args:
        item_id: Id of the item whose record is wanted.
        votes: The votes to aggregate. Votes that do not involve the item are
            ignored.
        items: The items used to resolve opponent names, active and retired.
        decay_timescale_days: Half-life in days used for the decayed weights.
            Zero or less means no decay, so the decayed weight equals the raw
            one.
        reference_time: Time to measure decay from. Defaults to the current
            time; pass a fixed value for deterministic results.

    Returns:
        WeightedRecord: The item's wins and losses per opponent. Both lists are
        empty when the item has taken part in no votes.
    """
    if reference_time is None:
        reference_time = datetime.now()

    names = {item.id: item.name for item in items}

    wins_raw: dict[str, float] = {}
    wins_decayed: dict[str, float] = {}
    losses_raw: dict[str, float] = {}
    losses_decayed: dict[str, float] = {}

    for vote in votes:
        if vote.winner_id == item_id:
            opponent_id = vote.loser_id
            raw, decayed = wins_raw, wins_decayed
        elif vote.loser_id == item_id:
            opponent_id = vote.winner_id
            raw, decayed = losses_raw, losses_decayed
        else:
            continue

        raw[opponent_id] = raw.get(opponent_id, 0.0) + vote.weight
        decayed[opponent_id] = decayed.get(opponent_id, 0.0) + vote.get_decayed_weight(
            decay_timescale_days, reference_time
        )

    return WeightedRecord(
        wins=_ordered(wins_raw, wins_decayed, names),
        losses=_ordered(losses_raw, losses_decayed, names),
    )
