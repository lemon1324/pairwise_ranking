"""Frontend-independent session over one open project.

:class:`ProjectSession` owns a single open :class:`~src.models.project.Project`
and everything derived from it: the rankings, the pair currently on offer and
the statistics that go with it. Every mutation saves the project, exactly as
the desktop window does today.

The session never prompts and never imports PyQt6: file dialogs, message boxes
and the wording of every message belong to the frontend, so the desktop and the
web can each word things their own way.
"""

import random
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from src.data.project_storage import ProjectStorage
from src.models.item import Item
from src.models.project import Project
from src.models.ranking import (
    BradleyTerryModel,
    PairSelector,
    RankingResult,
    assign_active_ranks,
)
from src.models.vote import Vote


# Rankings need at least this many items before the model is fitted at all.
MIN_RANKABLE_ITEMS = 2

# A comparison needs at least this many eligible items.
MIN_COMPARABLE_ITEMS = 2


class NoPairReason(Enum):
    """
    Why no pair could be offered.

    The frontend turns this into a message; the wording is deliberately not
    part of the session.

    Attributes:
        TOO_FEW_ITEMS: Fewer than two items can be compared right now.
        BLINDED_NO_IDENTIFIERS: There are enough active items, but blinded mode
            is on and fewer than two of them hold an identifier.
    """

    TOO_FEW_ITEMS = "too_few_items"
    BLINDED_NO_IDENTIFIERS = "blinded_no_identifiers"


@dataclass(frozen=True)
class PairOffer:
    """
    The result of asking the session what to compare next.

    Attributes:
        pair: The two items to compare, or None when none could be offered.
        stats: The selector's comparison statistics for this offer, or None
            when there is no pair.
        reason: Why there is no pair, or None when there is one.
        blinded: Whether blinded comparison mode was on when the offer was
            made, which decides how the frontend renders the two items.
    """

    pair: Optional[tuple[Item, Item]]
    stats: Optional[dict]
    reason: Optional[NoPairReason]
    blinded: bool

    def has_pair(self) -> bool:
        """
        Check whether the offer carries a pair.

        Returns:
            bool: True when there is a pair to render, False when the frontend
            should show the message for :attr:`reason` instead.
        """
        return self.pair is not None


@dataclass(frozen=True)
class UndoResult:
    """
    The outcome of undoing the most recent vote.

    Attributes:
        vote: The vote that was removed.
        offer: The pair the session picked once the vote was gone. The
            frontend renders this first, so that the screen is correct even
            when the undone pair cannot be put back.
        pair: The undone vote's pair as (winner, loser), or None when one of
            the two items is no longer eligible - it may have been retired,
            deleted or stripped of its identifier since the vote was cast. The
            winner comes first so it is always shown in the same place.
    """

    vote: Vote
    offer: PairOffer
    pair: Optional[tuple[Item, Item]]


class ProjectSession:
    """
    An open project plus the derived state a frontend needs to render it.

    The session autosaves: every mutating call writes the project back to its
    file when it has one, and does nothing when it does not (a project that has
    never been saved is held in memory until the frontend gives it a path).
    Recent-project bookkeeping is frontend business, so the session reports a
    successful save through the ``on_saved`` callback instead of knowing about
    user configuration.

    Rankings are computed lazily and memoised; any mutation drops the memo. The
    statistics of the most recent pair offer are memoised the same way, which
    is what lets :meth:`undo` re-offer a pair without recomputing them.

    Attributes:
        project: The project being edited.
    """

    def __init__(
        self,
        project: Project,
        on_saved: Optional[Callable[[Project], None]] = None,
        rng_factory: Optional[Callable[[], random.Random]] = None,
    ):
        """
        Initialize the session.

        Args:
            project: The project to work with. Opening files, Save As and
                switching projects stay with the frontend, so the session takes
                the project itself rather than a path.
            on_saved: Called with the project after every successful save.
            rng_factory: Builds the random source for one pair selection.
                Defaults to a fresh :class:`random.Random` per selection, which
                is what the desktop does today; pass a factory returning a
                seeded instance for deterministic tests.
        """
        self._project = project
        self._on_saved = on_saved
        self._rng_factory = rng_factory if rng_factory is not None else random.Random

        self._rankings: Optional[list[RankingResult]] = None
        self._rankings_valid = False

        # Statistics from the selector that chose the pair currently on offer,
        # reused when a specific pair has to be put back on screen after an
        # undo.
        self._comparison_stats: Optional[dict] = None

    @property
    def project(self) -> Project:
        """
        Return the project this session is editing.

        Returns:
            Project: The open project.
        """
        return self._project

    def _invalidate(self) -> None:
        """Drop the derived state so the next read recomputes it."""
        self._rankings = None
        self._rankings_valid = False
        self._comparison_stats = None

    def _persist(self) -> None:
        """
        Save the project if it has a file, and report the save.

        A project with no file path is simply kept in memory; saving it is the
        frontend's job, because only the frontend can ask for a location.
        """
        if not self._project.file_path:
            return

        ProjectStorage.save(self._project, self._project.file_path)
        if self._on_saved is not None:
            self._on_saved(self._project)

    def save(self) -> None:
        """
        Write the project to its file.

        Mutations save on their own, so this is only needed after the frontend
        changes something the session does not own - giving the project a file
        path through Save As, for instance.
        """
        self._persist()

    def rankings(self) -> Optional[list[RankingResult]]:
        """
        Return the current rankings, fitting the model if needed.

        Rankings are computed over **all** items, retired ones included, so
        that retiring an item does not change anybody's rating;
        :func:`~src.models.ranking.assign_active_ranks` then numbers the active
        items only. The result is memoised until the next mutation.

        Returns:
            Optional[list[RankingResult]]: The results ordered by strength, or
            None when the project holds fewer than two items and there is
            nothing to fit. The distinction between None and an empty list is
            deliberate: None means "no rankings at all", which frontends render
            as their empty state.
        """
        if self._rankings_valid:
            return self._rankings

        if len(self._project.items) < MIN_RANKABLE_ITEMS:
            self._rankings = None
        else:
            model = BradleyTerryModel(self._project.items)
            model.add_votes(
                self._project.votes,
                decay_timescale_days=self._project.settings.decay_timescale_days,
            )
            self._rankings = assign_active_ranks(model.compute_rankings())

        self._rankings_valid = True
        return self._rankings

    def _eligible_items(self) -> tuple[list[Item], list[Item]]:
        """
        Work out which items can be compared right now.

        Returns:
            tuple[list[Item], list[Item]]: The active items, and those of them
            that are eligible. Retired items keep their history but are never
            offered; in blinded mode an item also needs an identifier.
        """
        active = self._project.active_items()
        if self._project.settings.blinded_comparison_mode:
            return active, [item for item in active if item.has_identifier()]
        return active, active

    def next_pair(self) -> PairOffer:
        """
        Choose the next pair to compare.

        A fresh :class:`~src.models.ranking.PairSelector`, and so a fresh
        random source, is built for every selection.

        Returns:
            PairOffer: The chosen pair with its comparison statistics, or the
            reason no pair could be offered.
        """
        blinded = self._project.settings.blinded_comparison_mode
        self._comparison_stats = None

        active, eligible = self._eligible_items()

        if len(eligible) < MIN_COMPARABLE_ITEMS:
            blocked_by_identifiers = blinded and len(active) >= MIN_COMPARABLE_ITEMS
            return PairOffer(
                pair=None,
                stats=None,
                reason=(
                    NoPairReason.BLINDED_NO_IDENTIFIERS
                    if blocked_by_identifiers
                    else NoPairReason.TOO_FEW_ITEMS
                ),
                blinded=blinded,
            )

        selector = PairSelector(
            eligible,
            self._project.votes,
            self._project.settings,
            rng=self._rng_factory(),
        )
        pair = selector.select_pair(self.rankings())

        if pair is None:
            return PairOffer(
                pair=None,
                stats=None,
                reason=NoPairReason.TOO_FEW_ITEMS,
                blinded=blinded,
            )

        self._comparison_stats = selector.get_comparison_stats()
        return PairOffer(
            pair=pair,
            stats=self._comparison_stats,
            reason=None,
            blinded=blinded,
        )

    def comparison_stats(self) -> Optional[dict]:
        """
        Return the statistics of the pair currently on offer.

        Returns:
            Optional[dict]: The statistics from the most recent
            :meth:`next_pair`, or None when no pair has been offered since the
            last mutation or the last offer carried no pair.
        """
        return self._comparison_stats

    def skip(self) -> PairOffer:
        """
        Pass on the current pair and choose another.

        Skipping records nothing, so there is no state to change and nothing to
        save; the pair is simply chosen again.

        Returns:
            PairOffer: The next offer.
        """
        return self.next_pair()

    def vote(self, winner_id: str, loser_id: str, weight: float) -> Vote:
        """
        Record a comparison.

        Args:
            winner_id: Id of the item that was preferred.
            loser_id: Id of the item that was not preferred.
            weight: Strength of the preference.

        Returns:
            Vote: The recorded vote.

        Raises:
            ValueError: If the two ids are the same or the weight is not
                positive.
        """
        vote = self._project.add_vote(
            Vote(winner_id=winner_id, loser_id=loser_id, weight=weight)
        )
        self._invalidate()
        self._persist()
        return vote

    def undo(self) -> Optional[UndoResult]:
        """
        Remove the most recent vote and offer its pair again if possible.

        The next pair is chosen before the undone pair is looked up, so that a
        pair that can no longer be offered leaves a valid alternative on
        screen. The statistics of that selection are the ones that go with the
        re-offered pair: they are reused rather than recomputed, so the reading
        the frontend shows always matches the selection it came from.

        Returns:
            Optional[UndoResult]: The removed vote, the fresh offer and the
            undone pair when both its items are still eligible, or None when
            the project has no votes to undo.
        """
        vote = self._project.pop_last_vote()
        if vote is None:
            return None

        self._invalidate()
        self._persist()

        offer = self.next_pair()

        _, eligible = self._eligible_items()
        by_id = {item.id: item for item in eligible}
        winner = by_id.get(vote.winner_id)
        loser = by_id.get(vote.loser_id)

        pair = None if winner is None or loser is None else (winner, loser)
        return UndoResult(vote=vote, offer=offer, pair=pair)
