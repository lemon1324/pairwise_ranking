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
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from src.data.project_storage import ProjectStorage
from src.models.export import build_export_rows
from src.models.item import Item
from src.models.project import (
    Project,
    active_identifiers as active_identifiers_of,
    free_slots as free_slots_of,
    normalize_slots,
)
from src.models.ranking import (
    BradleyTerryModel,
    PairSelector,
    RankingResult,
    assign_active_ranks,
)
from src.models.settings import Settings
from src.models.vote import Vote

from .confidence import (
    DEFAULT_CONFIDENCE_READER,
    ConfidenceReader,
    ConfidenceReading,
)
from .record import WeightedRecord, weighted_record
from .slots import check_slot_labels, entered_slot_labels


# Rankings need at least this many items before the model is fitted at all.
MIN_RANKABLE_ITEMS = 2

# A comparison needs at least this many eligible items.
MIN_COMPARABLE_ITEMS = 2


class DuplicateTargetError(ValueError):
    """
    Raised when a project would be duplicated over its own file.

    The save dialog only warns about overwriting in general terms, and writing
    a vote-free copy over the original would destroy the original's votes.
    """


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

    def __post_init__(self):
        """Take a copy of the statistics so the offer cannot be written through."""
        if self.stats is not None:
            object.__setattr__(self, "stats", dict(self.stats))

    @property
    def has_pair(self) -> bool:
        """
        Check whether the offer carries a pair.

        Returns:
            bool: True when there is a pair to render, False when the frontend
            should show the message for :attr:`reason` instead.
        """
        return self.pair is not None


@dataclass(frozen=True)
class SlotSummary:
    """
    How much of a project's slot list is occupied.

    Attributes:
        total: How many slots the project defines.
        used: How many of them an active item occupies.
        free: The slots no active item occupies, in the order they are defined.
    """

    total: int
    used: int
    free: list[str]

    def __post_init__(self):
        """Take a copy of the free slots so the summary cannot be written through."""
        object.__setattr__(self, "free", list(self.free))


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
        confidence_reader: Optional[ConfidenceReader] = None,
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
            confidence_reader: Reads how settled the ranking is. Defaults to
                :data:`~src.app.confidence.DEFAULT_CONFIDENCE_READER`; the
                formula is meant to be swappable without a screen noticing.
        """
        self._project = project
        self._on_saved = on_saved
        self._rng_factory = rng_factory if rng_factory is not None else random.Random
        self._confidence_reader = (
            confidence_reader
            if confidence_reader is not None
            else DEFAULT_CONFIDENCE_READER
        )

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

    def _changed(self) -> None:
        """Drop the derived state and save, after any edit to the project."""
        self._invalidate()
        self._persist()

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

    def confidence(self) -> Optional[ConfidenceReading]:
        """
        Report how settled the current ranking is.

        This is the Compare screen's reading. It must not be shown in blinded
        comparison mode, where the ranking itself is deliberately off screen;
        that is the screen's decision, not the session's.

        Returns:
            Optional[ConfidenceReading]: The reading, or None when there is
            nothing to read - fewer than two items ranked, for instance. A
            missing reading is never an error.
        """
        return self._confidence_reader.read(self.rankings())

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

    def next_pair(self, exclude: Optional[tuple[str, str]] = None) -> PairOffer:
        """
        Choose the next pair to compare.

        A fresh :class:`~src.models.ranking.PairSelector`, and so a fresh
        random source, is built for every selection.

        Args:
            exclude: Two item ids naming a pair to pass over when any other
                can be offered. See :meth:`skip`.

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
        pair = selector.select_pair(self.rankings(), exclude=exclude)

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

    def offer_pair(self, first_id: str, second_id: str) -> Optional[PairOffer]:
        """
        Offer one particular pair, if both of its items can be compared now.

        This is how a frontend that addresses its pairs puts one back on
        screen - a reloaded page, a vote arriving from a page drawn a while
        ago - without choosing again. Nothing is selected: the statistics are
        the selector's for the current items and votes, which do not depend on
        the pair, and they become the memo :meth:`comparison_stats` reads.

        Args:
            first_id: Id of the item to show first.
            second_id: Id of the item to show second.

        Returns:
            Optional[PairOffer]: The pair in the order given, or None when the
            two ids are the same, either item is missing, or either is not
            eligible right now - retired, or without an identifier in blinded
            mode.
        """
        if first_id == second_id:
            return None

        _, eligible = self._eligible_items()
        by_id = {item.id: item for item in eligible}
        first = by_id.get(first_id)
        second = by_id.get(second_id)
        if first is None or second is None:
            return None

        selector = PairSelector(
            eligible,
            self._project.votes,
            self._project.settings,
            rng=self._rng_factory(),
        )
        self._comparison_stats = selector.get_comparison_stats()
        return PairOffer(
            pair=(first, second),
            stats=self._comparison_stats,
            reason=None,
            blinded=self._project.settings.blinded_comparison_mode,
        )

    def comparison_stats(self) -> Optional[dict]:
        """
        Return the statistics of the pair currently on offer.

        Returns:
            Optional[dict]: A copy of the statistics from the most recent
            :meth:`next_pair`, or None when no pair has been offered since the
            last mutation or the last offer carried no pair. It is a copy so
            that a caller cannot write through it into the session's memo.
        """
        if self._comparison_stats is None:
            return None
        return dict(self._comparison_stats)

    def skip(self, exclude: Optional[tuple[str, str]] = None) -> PairOffer:
        """
        Pass on the current pair and choose another.

        Skipping records nothing, so there is no state to change and nothing to
        save. Selection is mostly deterministic, so without ``exclude`` the
        same pair usually comes straight back; with it, the best pair other
        than the one passed on is offered, or that one again when it is the
        only pair there is. Nothing is remembered between calls, so a second
        skip may bounce back to the first pair.

        Args:
            exclude: The two item ids of the pair being skipped, in either
                order.

        Returns:
            PairOffer: The next offer.
        """
        return self.next_pair(exclude=exclude)

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
        self._changed()
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

        self._changed()

        offer = self.next_pair()

        _, eligible = self._eligible_items()
        by_id = {item.id: item for item in eligible}
        winner = by_id.get(vote.winner_id)
        loser = by_id.get(vote.loser_id)

        pair = None if winner is None or loser is None else (winner, loser)
        return UndoResult(vote=vote, offer=offer, pair=pair)

    def add_item(self, item: Item) -> Item:
        """
        Add an item to the project.

        The item is taken as it is. Form input should be checked with
        :func:`~src.app.items.validate_item_form` before it gets here, which is
        where the frontend can still put the complaint next to the field it
        belongs to.

        Args:
            item: The item to add.

        Returns:
            Item: The item that was added.
        """
        self._project.add_item(item)
        self._changed()
        return item

    def update_item(self, item: Item) -> Optional[Item]:
        """
        Replace an item with an edited version of itself.

        An id the project does not hold is tolerated: nothing is changed, but
        the project is still saved, because that is what the desktop has always
        done and a caller cannot tell the two cases apart anyway.

        Args:
            item: The edited item, carrying the id of the item it replaces.

        Returns:
            Optional[Item]: The stored item, or None when the project holds no
            item with that id.
        """
        stored: Optional[Item] = None
        for index, existing in enumerate(self._project.items):
            if existing.id == item.id:
                self._project.items[index] = item
                stored = item
                break

        self._changed()
        return stored

    def retire(self, item_id: str) -> Optional[Item]:
        """
        Retire an item, keeping its history but freeing its identifier.

        A missing item is tolerated, as for :meth:`update_item`.

        Args:
            item_id: Id of the item to retire.

        Returns:
            Optional[Item]: The retired item, or None when there is no such
            item.
        """
        item = self._project.find_item(item_id)
        if item is not None:
            item.retire()

        self._changed()
        return item

    def replace(self, old_item_id: str, new_item: Item) -> Item:
        """
        Retire an item and add the item that takes its place.

        The old item is retired **before** the successor is added, because
        retiring clears the old item's identifier and the successor usually
        arrives holding it; the other order would have two active items in one
        slot. A missing predecessor is tolerated: the successor is still added.

        Args:
            old_item_id: Id of the item being replaced.
            new_item: The item taking its place.

        Returns:
            Item: The item that was added.
        """
        old_item = self._project.find_item(old_item_id)
        if old_item is not None:
            old_item.retire(replaced_by=new_item.id)
        self._project.add_item(new_item)

        self._changed()
        return new_item

    def reactivate(self, item_id: str, identifier: str = "") -> Optional[Item]:
        """
        Return a retired item to the active pool.

        Args:
            item_id: Id of the item to reactivate.
            identifier: Identifier to give it, or empty for none.

        Returns:
            Optional[Item]: The reactivated item, or None when there is no such
            item.
        """
        item = self._project.find_item(item_id)
        if item is not None:
            item.reactivate(identifier)

        self._changed()
        return item

    def delete_item(self, item_id: str) -> Optional[Item]:
        """
        Delete an item and every vote it took part in.

        Deleting discards history; retiring is the way to keep it. A missing
        item is tolerated.

        Args:
            item_id: Id of the item to delete.

        Returns:
            Optional[Item]: The deleted item, or None when there is no such
            item.
        """
        removed = self._project.remove_item(item_id)
        self._changed()
        return removed

    def _items_except(self, exclude_item_id: Optional[str]) -> list[Item]:
        """
        Return the project's items with one of them left out.

        Args:
            exclude_item_id: Id of the item to leave out, or None to keep all.

        Returns:
            list[Item]: The remaining items, active and retired.
        """
        if exclude_item_id is None:
            return list(self._project.items)
        return [item for item in self._project.items if item.id != exclude_item_id]

    def taken_identifiers(self, exclude_item_id: Optional[str] = None) -> set[str]:
        """
        Return the identifiers active items already hold.

        Args:
            exclude_item_id: Id of an item to ignore, typically the item being
                edited or the item being replaced, so that its own identifier
                does not count as taken.

        Returns:
            set[str]: The non-empty identifiers in use.
        """
        return active_identifiers_of(self._items_except(exclude_item_id))

    def free_slots(self, exclude_item_id: Optional[str] = None) -> list[str]:
        """
        Return the project's slots that no active item occupies.

        Args:
            exclude_item_id: Id of an item whose slot should count as free.

        Returns:
            list[str]: Free slots in the order they are defined. Empty when the
            project defines no slots at all - a frontend that has to tell those
            two cases apart reads :meth:`slot_summary` instead.
        """
        return free_slots_of(self._project.slots, self._items_except(exclude_item_id))

    def slot_summary(self) -> SlotSummary:
        """
        Summarize how much of the slot list is occupied.

        Returns:
            SlotSummary: The slot counts and the free slots. A total of zero
            means the project defines no slots and identifiers are free text.
        """
        free = self._project.free_slots()
        total = len(self._project.slots)
        return SlotSummary(total=total, used=total - len(free), free=free)

    def apply_settings(
        self,
        settings: Settings,
        raw_slots: list[str],
        slot_labels: Optional[dict] = None,
    ) -> list[str]:
        """
        Apply the settings, the slot list and its short labels from one Save.

        The slot list arrives raw, as the user typed it, and is normalized on
        the way in; the normalized list comes back so the caller can show what
        was actually stored. Taking everything in one call is what makes one
        Save exactly one save.

        Args:
            settings: The settings as entered.
            raw_slots: Slot labels as entered. They are stripped, emptied
                entries are dropped and duplicates are removed.
            slot_labels: The short labels entered on the slot board, slot
                name to label, or None to keep the stored ones (the desktop
                does not edit them). Kept as
                :func:`~src.app.slots.entered_slot_labels` keeps them: empty
                labels, labels equal to the derived one and labels for slots
                not in the new list are dropped. A label for a slot that goes
                is dropped either way.

        Returns:
            list[str]: The slot list as it was stored.

        Raises:
            ValueError: If a setting is out of range
                (:meth:`~src.models.settings.Settings.validate`), or a label
                is refused by :func:`~src.app.slots.check_slot_labels`. Nothing
                is applied or saved.
        """
        settings.validate()
        labels = None
        if slot_labels is not None:
            saved = entered_slot_labels(self._project.slots, self._project.slot_labels)
            verdict = check_slot_labels(normalize_slots(raw_slots), slot_labels, saved)
            if not verdict.ok:
                refused = ", ".join(
                    f"{slot} ({error.value})" for slot, error in verdict.errors.items()
                )
                raise ValueError(f"Slot labels refused: {refused}")
            labels = verdict.labels
        self._project.settings = settings
        self._project.set_slots(raw_slots)
        if labels is not None:
            self._project.set_slot_labels(labels)
        self._changed()
        return list(self._project.slots)

    def reset_settings(self) -> Settings:
        """
        Return the algorithm settings to their defaults.

        The slot list describes the project rather than the algorithm, so it is
        deliberately left alone.

        Nothing calls this yet: the desktop's Reset button only fills its form
        with defaults and waits for a Save, which is a different gesture, so
        wiring it here would start persisting a reset the user has not
        confirmed. It is here for the web Settings screen, whose Reset does
        apply immediately.

        Returns:
            Settings: The freshly applied default settings.
        """
        self._project.settings = Settings()
        self._changed()
        return self._project.settings

    def rename(self, name: str) -> str:
        """
        Change the project's display name.

        The file keeps its path; only the name stored inside it changes.

        Args:
            name: The new name. Surrounding whitespace is stripped.

        Returns:
            str: The stored name.

        Raises:
            ValueError: If the new name is empty or only whitespace.
        """
        self._project.rename(name)
        self._changed()
        return self._project.name

    def duplicate_without_votes(self, name: str, file_path: Path) -> Project:
        """
        Save a vote-free copy of this project to another file.

        The copy carries the items, settings and slots, with item ids
        preserved, and starts with no votes. This session keeps editing the
        original; opening the copy is the frontend's business.

        Args:
            name: Name for the copy.
            file_path: Where to write the copy.

        Returns:
            Project: The copy, already saved.

        Raises:
            DuplicateTargetError: If the copy would be written over this
                project's own file, which would destroy its votes.
            ValueError: If the name is empty or the path is not a project file.
            OSError: If the file cannot be written.
        """
        source_path = self._project.file_path
        if source_path is not None and file_path.resolve() == source_path.resolve():
            raise DuplicateTargetError(
                "A copy cannot be written over the project it was copied from"
            )

        return ProjectStorage.create_copy(self._project, name, file_path)

    def export_rows(
        self,
        category: Optional[str] = None,
        include_retired: bool = False,
    ) -> list[list[str]]:
        """
        Build the rows of a rankings export.

        Args:
            category: Category to restrict the export to, or None for every
                category.
            include_retired: Whether retired items are exported too.

        Returns:
            list[list[str]]: The header row followed by one row per exported
            result. A project with nothing to rank exports the header alone.
        """
        return build_export_rows(
            self.rankings() or [],
            include_retired=include_retired,
            category=category,
        )

    def item_details(
        self,
        item_id: str,
        reference_time: Optional[datetime] = None,
    ) -> WeightedRecord:
        """
        Return an item's weighted record against each opponent.

        Opponents are kept apart by id, and both the raw and the decayed weight
        are reported, so the frontend decides which to show and whether to
        merge opponents that share a name.

        Args:
            item_id: Id of the item whose record is wanted.
            reference_time: Time to measure decay from. Defaults to the current
                time.

        Returns:
            WeightedRecord: The item's wins and losses per opponent. Both lists
            are empty when the item has no votes, or no such item exists.
        """
        return weighted_record(
            item_id,
            self._project.votes,
            self._project.items,
            decay_timescale_days=self._project.settings.decay_timescale_days,
            reference_time=reference_time,
        )
